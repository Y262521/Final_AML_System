"""
Transaction API routes.

Serves processed transactions from MySQL and graph edges from Neo4j.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Literal, Any

from fastapi import APIRouter, HTTPException, Query

from db.mysql import fetch_all, fetch_one, get_pool
from db.neo4j import get_driver
from settings import get_env

router = APIRouter()
NEO4J_DATABASE = get_env("NEO4J_DATABASE", default="neo4j")
MIN_CLUSTER_SIZE = int(get_env("CLUSTER_MIN_CLUSTER_SIZE", default="2") or "2")


def _threshold_eth() -> float:
    raw = get_env("HIGH_VALUE_THRESHOLD_ETH", "AML_HIGH_VALUE_THRESHOLD", default="10")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 10.0


def _risk_score(value_eth: float, threshold: float) -> float:
    if threshold <= 0 or value_eth <= 0:
        return 0.0

    ratio = value_eth / threshold
    if ratio >= 2.0:
        return 100.0
    if ratio >= 1.0:
        return round(75.0 + 25.0 * (ratio - 1.0), 1)
    return round(max(0.0, min(75.0, 75.0 * ratio)), 1)


def _risk_label(value_eth: float, threshold: float) -> str:
    score = _risk_score(value_eth, threshold)
    if score > 75:
        return "High"
    if score > 40:
        return "Medium"
    return "Low"


def _format_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _require_mysql():
    if get_pool() is None:
        raise HTTPException(
            status_code=503,
            detail="MySQL is not connected. Transactions are unavailable.",
        )


def _latest_transactions_sql(sort_by: str = "amount_desc", chain: str | None = None) -> str:
    order_clause = {
        "value_usd_desc": "ORDER BY COALESCE(usd_at_execution, 0) DESC, value_eth DESC, block_number DESC, tx_hash DESC",
        "amount_desc":    "ORDER BY value_eth DESC, block_number DESC, tx_hash DESC",
        "latest":         "ORDER BY block_number DESC, tx_hash DESC",
    }.get(sort_by, "ORDER BY value_eth DESC, block_number DESC, tx_hash DESC")

    where_clause = ""
    if chain and chain != "all":
        where_clause = "WHERE (chain_name = %s OR (chain_name IS NULL AND %s = 'ethereum'))"

    return f"""
        SELECT tx_hash, from_address, to_address, value_eth, timestamp, block_number,
               is_contract_call, gas_used, status,
               usd_at_execution,
               COALESCE(chain_name,      'ethereum') AS chain_name,
               COALESCE(chain_id,        1)          AS chain_id,
               COALESCE(blockchain_type, 'EVM')      AS blockchain_type,
               COALESCE(native_asset,    'ETH')      AS native_asset
        FROM transactions
        {where_clause}
        {order_clause}
        LIMIT %s OFFSET %s
        """


@router.get("/")
async def get_latest_transactions(
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    sort_by: Literal["value_usd_desc", "amount_desc", "latest"] = Query("amount_desc"),
    chain: str | None = Query(None),
):
    _require_mysql()
    threshold = _threshold_eth()

    if chain and chain != "all":
        total_row = await fetch_one(
            "SELECT COUNT(*) AS total FROM transactions "
            "WHERE chain_name = %s OR (chain_name IS NULL AND %s = 'ethereum')",
            (chain, chain),
        ) or {}
        rows = await fetch_all(
            _latest_transactions_sql(sort_by, chain),
            (chain, chain, limit, offset),
        )
    else:
        total_row = await fetch_one("SELECT COUNT(*) AS total FROM transactions") or {}
        rows = await fetch_all(_latest_transactions_sql(sort_by), (limit, offset))

    # Live current market prices
    def _get_live_rates() -> dict:
        try:
            from services.live_prices import get_live_prices
            return get_live_prices()
        except Exception:
            return {}

    live_rates = _get_live_rates()

    results = []
    for row in rows:
        value_eth    = float(row.get("value_eth") or 0.0)
        native_asset = row.get("native_asset") or "ETH"
        chain_name   = row.get("chain_name") or "ethereum"
        score        = _risk_score(value_eth, threshold)

        # Historical USD at execution time (Chainlink oracle stored at ETL time)
        usd_stored = row.get("usd_at_execution")
        usd_at_execution = float(usd_stored) if usd_stored is not None and float(usd_stored) > 0 else 0.0

        # Current market USD value (live price × amount)
        current_rate      = live_rates.get(native_asset, 0.0)
        current_usd_value = round(value_eth * current_rate, 2) if current_rate > 0 else 0.0

        # Displayed USD: prefer historical oracle value, fall back to current price
        display_usd = usd_at_execution if usd_at_execution > 0 else current_usd_value

        results.append({
            "hash":           row.get("tx_hash"),
            "sender":         row.get("from_address"),
            "receiver":       row.get("to_address"),
            "amount":         f"{value_eth:.6f}",
            "timestamp":      _format_ts(row.get("timestamp")),
            "blockNumber":    int(row.get("block_number") or 0),
            "isContractCall": bool(row.get("is_contract_call")),
            "gasUsed":        row.get("gas_used"),
            "status":         row.get("status"),
            "riskScore":      round(score, 1),
            "riskLabel":      _risk_label(value_eth, threshold),
            # Chain identity
            "chain":           chain_name,
            "chainId":         int(row.get("chain_id") or 1),
            "blockchainType":  row.get("blockchain_type") or "EVM",
            "nativeAsset":     native_asset,
            # USD values
            "usdValue":        round(display_usd, 2),
            "usdAtExecution":  round(usd_at_execution, 2),
            "currentUsdValue": current_usd_value,
        })

    total = int(total_row.get("total") or 0)
    return {
        "items":   results,
        "total":   total,
        "limit":   limit,
        "offset":  offset,
        "sortBy":  sort_by,
        "chain":   chain or "all",
        "hasMore": offset + len(results) < total,
    }


@router.get("/analytics")
async def get_analytics():
    _require_mysql()
    threshold = _threshold_eth()

    totals = await fetch_one(
        "SELECT COUNT(*) AS total, COALESCE(SUM(value_eth), 0) AS total_eth FROM transactions"
    ) or {}
    total_tx = int(totals.get("total") or 0)
    total_eth = float(totals.get("total_eth") or 0.0)

    high_value = await fetch_one(
        "SELECT COUNT(*) AS high_value FROM transactions WHERE value_eth >= %s",
        (threshold,),
    ) or {}
    high_value_tx = int(high_value.get("high_value") or 0)

    buckets = await fetch_one(
        """
        SELECT
            SUM(CASE WHEN value_eth < 0.1 THEN 1 ELSE 0 END) AS b1,
            SUM(CASE WHEN value_eth >= 0.1 AND value_eth < 1 THEN 1 ELSE 0 END) AS b2,
            SUM(CASE WHEN value_eth >= 1 AND value_eth < 10 THEN 1 ELSE 0 END) AS b3,
            SUM(CASE WHEN value_eth >= 10 AND value_eth < 50 THEN 1 ELSE 0 END) AS b4,
            SUM(CASE WHEN value_eth >= 50 THEN 1 ELSE 0 END) AS b5
        FROM transactions
        """
    ) or {}

    top_clusters_balance = await fetch_all(
        """
        SELECT c.id, COUNT(a.address) AS cluster_size, c.total_balance
        FROM wallet_clusters c
        JOIN addresses a ON a.cluster_id = c.id
        GROUP BY c.id, c.total_balance
        HAVING COUNT(a.address) >= %s
        ORDER BY c.total_balance DESC, COUNT(a.address) DESC
        LIMIT 5
        """,
        (MIN_CLUSTER_SIZE,),
    )
    top_clusters_size = await fetch_all(
        """
        SELECT c.id, COUNT(a.address) AS cluster_size, c.total_balance
        FROM wallet_clusters c
        JOIN addresses a ON a.cluster_id = c.id
        GROUP BY c.id, c.total_balance
        HAVING COUNT(a.address) >= %s
        ORDER BY COUNT(a.address) DESC, c.total_balance DESC
        LIMIT 5
        """,
        (MIN_CLUSTER_SIZE,),
    )

    return {
        "totalTransactions": total_tx,
        "totalEth": round(total_eth, 6),
        "highValueTransactions": high_value_tx,
        "amountBuckets": [
            {"range": "0-0.1", "count": int(buckets.get("b1") or 0)},
            {"range": "0.1-1", "count": int(buckets.get("b2") or 0)},
            {"range": "1-10", "count": int(buckets.get("b3") or 0)},
            {"range": "10-50", "count": int(buckets.get("b4") or 0)},
            {"range": "50+", "count": int(buckets.get("b5") or 0)},
        ],
        "topClustersByBalance": [
            {
                "cluster_id": row.get("id"),
                "cluster_size": int(row.get("cluster_size") or 0),
                "total_balance": float(row.get("total_balance") or 0.0),
            }
            for row in top_clusters_balance
        ],
        "topClustersBySize": [
            {
                "cluster_id": row.get("id"),
                "cluster_size": int(row.get("cluster_size") or 0),
                "total_balance": float(row.get("total_balance") or 0.0),
            }
            for row in top_clusters_size
        ],
    }


def _require_neo4j():
    driver = get_driver()
    if not driver:
        return None   # Soft fail — MySQL fallback used instead
    return driver


@router.get("/graph")
async def get_graph_data(
    search: str | None = None,
    center: str | None = None,
    hops: int = Query(2, ge=1, le=4),
    max_edges: int = Query(300, ge=50, le=3000),
    min_value: float = Query(0, ge=0),
    chain: str | None = Query(None),
):
    """
    Return transaction graph edges for visualization.
    Primary: Neo4j (EVM chains, when available).
    Fallback: MySQL transactions table (all chains including BTC/SOL/UTXO).
    """
    driver = get_driver()

    # Try Neo4j first for EVM address searches (0x...)
    if driver and center and center.startswith('0x'):
        try:
            hops_clamped = max(1, min(int(hops), 4))
            query = f"""
            MATCH p = (a:Address {{address: $center}})-[:TRANSFER*1..{hops_clamped}]-(b:Address)
            UNWIND relationships(p) AS r
            WITH DISTINCT r
            WHERE r.value_eth >= $min_value
            RETURN startNode(r).address AS from_address,
                   endNode(r).address AS to_address,
                   r.value_eth AS value_eth,
                   r.block_number AS block_number,
                   r.tx_hash AS tx_hash
            LIMIT $max_edges
            """
            params = {"center": center.lower(), "min_value": min_value, "max_edges": max_edges}
            async with driver.session(database=NEO4J_DATABASE) as session:
                result = await session.run(query, params)
                rows = [record.data() async for record in result]
            if rows:
                return [
                    {
                        "sender": row.get("from_address"),
                        "receiver": row.get("to_address"),
                        "amount": float(row.get("value_eth") or 0.0),
                        "blockNumber": int(row.get("block_number") or 0),
                        "txHash": row.get("tx_hash"),
                        "nativeAsset": "ETH",
                        "chain": "ethereum",
                    }
                    for row in rows
                ]
        except Exception:
            pass  # Fall through to MySQL

    # MySQL fallback — works for ALL chains (ETH, BTC, SOL, LTC, DOGE, BCH, BNB, POL)
    _require_mysql()

    chain_filter = ""
    chain_params: list = []
    if chain and chain != "all":
        chain_filter = " AND (chain_name = %s OR (chain_name IS NULL AND %s = 'ethereum'))"
        chain_params = [chain, chain]

    if center:
        # Direct address lookup — works for any address format (0x..., bc1..., sol...)
        addr = center.lower().strip()
        rows = await fetch_all(
            f"""
            SELECT from_address, to_address, value_eth, block_number, tx_hash,
                   COALESCE(native_asset, 'ETH') AS native_asset,
                   COALESCE(chain_name, 'ethereum') AS chain_name
            FROM transactions
            WHERE (LOWER(from_address) = %s OR LOWER(to_address) = %s)
              AND value_eth >= %s
              {chain_filter}
            ORDER BY block_number DESC
            LIMIT %s
            """,
            tuple([addr, addr, min_value] + chain_params + [max_edges]),
        )
    elif search:
        # Partial address search
        rows = await fetch_all(
            f"""
            SELECT from_address, to_address, value_eth, block_number, tx_hash,
                   COALESCE(native_asset, 'ETH') AS native_asset,
                   COALESCE(chain_name, 'ethereum') AS chain_name
            FROM transactions
            WHERE (LOWER(from_address) LIKE %s OR LOWER(to_address) LIKE %s)
              AND value_eth >= %s
              {chain_filter}
            ORDER BY block_number DESC
            LIMIT %s
            """,
            tuple([f"%{search.lower()}%", f"%{search.lower()}%", min_value] + chain_params + [max_edges]),
        )
    else:
        # Default: latest transactions
        rows = await fetch_all(
            f"""
            SELECT from_address, to_address, value_eth, block_number, tx_hash,
                   COALESCE(native_asset, 'ETH') AS native_asset,
                   COALESCE(chain_name, 'ethereum') AS chain_name
            FROM transactions
            WHERE value_eth >= %s
              {chain_filter}
            ORDER BY block_number DESC
            LIMIT %s
            """,
            tuple([min_value] + chain_params + [max_edges]),
        )

    return [
        {
            "sender": row.get("from_address"),
            "receiver": row.get("to_address"),
            "amount": float(row.get("value_eth") or 0.0),
            "blockNumber": int(row.get("block_number") or 0),
            "txHash": row.get("tx_hash"),
            "nativeAsset": row.get("native_asset") or "ETH",
            "chain": row.get("chain_name") or "ethereum",
        }
        for row in (rows or [])
    ]


@router.post("/refresh")
async def refresh_pipeline():
    """Optional manual refresh: run ETL plus analytics once."""
    try:
        import sys
        from pathlib import Path
        from dotenv import load_dotenv

        aml_root = Path(__file__).resolve().parents[3] / "AML"
        aml_src = str(aml_root / "src")
        if aml_src not in sys.path:
            sys.path.insert(0, aml_src)
        load_dotenv(aml_root / ".env")

        from aml_pipeline.config import load_config
        from aml_pipeline.pipelines.daily_pipeline import run_daily_pipeline

        cfg = load_config()
        summary = await asyncio.to_thread(
            run_daily_pipeline,
            cfg=cfg,
            run_clustering=True,
            skip_mongo_backup=True,
        )
        return {"status": "ok", "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline refresh failed: {exc}") from exc

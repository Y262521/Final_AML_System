"""
fetch_wallet_history_free.py
==============================
Extracts a SINGLE WALLET's historical transactions starting from a given
date, using AWS Public Blockchain Data (S3) or SQD (Subsquid Portal) --
both free, no billing account, no API key.

Why these two instead of BigQuery
-----------------------------------
BigQuery is the only one of the three new sources with a true server-side
address filter, but it bills your GCP project per query. These two don't:

  --source aws_s3 (recommended, default)
    Already date-partitioned: s3://aws-public-blockchain/v1.0/eth/transactions/date=YYYY-MM-DD/
    We read one day's Parquet partition at a time and filter client-side
    (pandas boolean mask) for the wallet address -- free, unsigned S3
    request, no credentials. This lines up naturally with "from a starting
    date" since the bucket is already organized by date.
    Supported chains here: bitcoin, ethereum, arbitrum, base.

  --source sqd
    No native date filter -- SQD streams by BLOCK NUMBER, not date. This
    script first binary-searches SQD's own block timestamps to convert
    your --start-date/--end-date into a block range (using the same
    ~12s/block estimate refined by real probes), then streams that block
    range and filters client-side for the wallet address. Slower to set
    up than aws_s3 for date-based queries, but covers far more chains
    (200+, including ones aws_s3 doesn't: bnb, polygon, solana, tron...).

Both approaches scan every transaction in range and discard non-matches
client-side (neither source supports pushing an address filter down to
the server, unlike BigQuery) -- so a wide date range on a busy chain
means scanning a lot of data. Use --limit and a narrow date range first.

Where the data goes
--------------------
Same as the BigQuery version: rows are written directly into the
`transactions` table (+ `addresses` summary), matching the exact schema
in schemas/mariadb_tables.sql and the read contract in
evm_adapter.py::_iter_from_mariadb -- Placement/Layering/Integration can
read them immediately with source="mariadb", no extra transform step.

NOT yet run against live data
--------------------------------
This sandbox has no network route to s3.amazonaws.com or portal.sqd.dev,
so this has not been executed end-to-end. Column names for aws_s3 are
inferred from the BigQuery version of the same public dataset (AWS's
docs state it mirrors that schema) -- please run with --dry-run and a
narrow 1-day range first to confirm the column names resolve correctly
before a full historical pull.

Usage
-----
    set PYTHONPATH=src

    REM AWS S3 (recommended)
    python scripts/fetch_wallet_history_free.py --source aws_s3 ^
        --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 ^
        --start-date 2026-01-01 --chain ethereum --limit 5000 --dry-run

    REM SQD (wider chain coverage, block-range based)
    python scripts/fetch_wallet_history_free.py --source sqd ^
        --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 ^
        --start-date 2026-01-01 --chain ethereum --limit 5000 --dry-run

Drop --dry-run once the output looks right.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

logger = logging.getLogger(__name__)

WEI_PER_ETH = Decimal("1000000000000000000")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", choices=["aws_s3", "sqd"], default="aws_s3")
    parser.add_argument("--address", required=True, help="Wallet address to fetch history for")
    parser.add_argument("--start-date", required=True, help="Start date, e.g. 2026-01-01 (UTC)")
    parser.add_argument("--end-date", default=None, help="End date, e.g. 2026-06-30 (UTC). Defaults to today.")
    parser.add_argument("--chain", default="ethereum", help="Chain name (aws_s3: bitcoin/ethereum/arbitrum/base; sqd: 200+, see SQD docs)")
    parser.add_argument("--limit", type=int, default=5000, help="Stop after this many matching transactions")
    parser.add_argument("--max-scan-blocks", type=int, default=2_000_000, help="[sqd only] safety cap on how many blocks to scan before giving up")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and print, but do not write to MariaDB")
    return parser.parse_args()


def _col(df, *candidates):
    """Return the first column name from `candidates` that exists in df."""
    for name in candidates:
        if name in df.columns:
            return name
    raise KeyError(f"None of {candidates} found in columns: {list(df.columns)}")


# ──────────────────────────────────────────────────────────────────────────
# AWS S3 path -- date-partitioned, filter client-side per day
# ──────────────────────────────────────────────────────────────────────────

_AWS_CHAIN_PATHS = {
    "bitcoin": "v1.0/btc",
    "ethereum": "v1.0/eth",
    "arbitrum": "v1.1/sonarx/arbitrum",
    "base": "v1.1/sonarx/base",
}


def fetch_wallet_transactions_aws_s3(address: str, start_date: str, end_date: str, chain: str, limit: int) -> list[dict]:
    import os
    import pandas as pd
    import pyarrow.dataset as ds
    import s3fs
    from botocore import UNSIGNED
    from botocore.config import Config as BotoConfig

    if chain not in _AWS_CHAIN_PATHS:
        raise ValueError(f"aws_s3 source does not support chain={chain!r}. Supported: {sorted(_AWS_CHAIN_PATHS)}")

    bucket = os.getenv("AWS_PUBLIC_BLOCKCHAIN_BUCKET", "aws-public-blockchain")
    region = os.getenv("AWS_PUBLIC_BLOCKCHAIN_REGION", "us-east-2")
    prefix = _AWS_CHAIN_PATHS[chain]
    fs = s3fs.S3FileSystem(anon=True, config_kwargs={"region_name": region})
    address = address.lower().strip()

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()

    results: list[dict] = []
    day = start
    while day <= end and len(results) < limit:
        # NOTE: when an explicit `filesystem=` is supplied, pyarrow expects a
        # filesystem-relative path (no "s3://" scheme) -- s3fs's directory
        # listing returns paths without the scheme, and passing a URI with
        # the scheme causes a "yielded path ... outside base dir" error.
        uri = f"{bucket}/{prefix}/transactions/date={day.isoformat()}/"
        try:
            dataset = ds.dataset(uri, format="parquet", filesystem=fs)
            df = dataset.to_table().to_pandas()
        except (FileNotFoundError, OSError) as exc:
            logger.info("No data for %s (%s) -- skipping", day, exc)
            day += timedelta(days=1)
            continue

        if df.empty:
            day += timedelta(days=1)
            continue

        from_col = _col(df, "from_address", "sender")
        to_col = _col(df, "to_address", "receiver")
        hash_col = _col(df, "hash", "transaction_hash", "tx_hash")
        value_col = _col(df, "value", "value_wei")
        block_col = _col(df, "block_number", "number")
        ts_col = _col(df, "block_timestamp", "timestamp")
        gas_col = _col(df, "gas", "gas_used") if "gas" in df.columns or "gas_used" in df.columns else None
        status_col = _col(df, "receipt_status", "status") if "receipt_status" in df.columns or "status" in df.columns else None

        mask = (df[from_col].astype(str).str.lower() == address) | (df[to_col].astype(str).str.lower() == address)
        matches = df[mask]

        logger.info("%s: %d transactions, %d matching wallet", day, len(df), len(matches))

        for _, row in matches.iterrows():
            value_raw = row[value_col]
            value_eth = Decimal(str(value_raw)) / WEI_PER_ETH if value_raw is not None else Decimal("0")
            ts = row[ts_col]
            if not isinstance(ts, datetime):
                ts = pd.to_datetime(ts, utc=True).to_pydatetime()

            results.append({
                "tx_hash": row[hash_col],
                "block_number": int(row[block_col]),
                "timestamp": ts,
                "from_address": str(row[from_col]).lower(),
                "to_address": str(row[to_col]).lower(),
                "value_eth": value_eth,
                "is_contract_call": bool(row[gas_col] and row[gas_col] > 21000) if gas_col else False,
                "gas_used": int(row[gas_col]) if gas_col and row[gas_col] else None,
                "status": 1 if (status_col is None or row[status_col] in (1, None)) else 0,
            })
            if len(results) >= limit:
                break

        day += timedelta(days=1)

    return results


# ──────────────────────────────────────────────────────────────────────────
# SQD path -- block-range based; convert dates to blocks via binary search
# ──────────────────────────────────────────────────────────────────────────

_SQD_NETWORKS = {
    "ethereum": "ethereum-mainnet",
    "bnb": "binance-mainnet",
    "polygon": "polygon-mainnet",
    "arbitrum": "arbitrum-one",
    "base": "base-mainnet",
    "bitcoin": "bitcoin-mainnet",
    "solana": "solana-mainnet",
    "tron": "tron-mainnet",
}


def _sqd_setup(chain: str):
    import os
    import requests

    network = _SQD_NETWORKS.get(chain, chain)
    portal_url = os.getenv("SQD_PORTAL_URL", "https://portal.sqd.dev").rstrip("/")
    stream_url = f"{portal_url}/datasets/{network}/stream"
    session = requests.Session()
    return session, portal_url, stream_url, network


def _sqd_latest_block(session, portal_url: str, network: str) -> int:
    resp = session.get(f"{portal_url}/datasets/{network}/head", timeout=15)
    resp.raise_for_status()
    return int(resp.json()["number"])


def _sqd_block_timestamp(session, stream_url: str, block_number: int) -> datetime:
    """Probe a single block's timestamp with a minimal-fields request."""
    body = {
        "type": "evm",
        "fromBlock": block_number,
        "toBlock": block_number,
        "includeAllBlocks": True,
        "fields": {"block": {"number": True, "timestamp": True}},
    }
    with session.post(stream_url, json=body, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            block = json.loads(line)
            header = block.get("header", block)
            ts = header.get("timestamp")
            if isinstance(ts, (int, float)):
                return datetime.fromtimestamp(ts, tz=timezone.utc)
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    raise ValueError(f"SQD returned no data probing block {block_number}")


def _sqd_date_to_block(session, stream_url: str, target: datetime, low: int, high: int) -> int:
    """Binary search for the first block whose timestamp >= target."""
    while low < high:
        mid = (low + high) // 2
        ts = _sqd_block_timestamp(session, stream_url, mid)
        if ts < target:
            low = mid + 1
        else:
            high = mid
    return low


def fetch_wallet_transactions_sqd(address: str, start_date: str, end_date: str, chain: str, limit: int, max_scan_blocks: int) -> list[dict]:
    session, portal_url, stream_url, network = _sqd_setup(chain)
    address = address.lower().strip()

    latest_block = _sqd_latest_block(session, portal_url, network)
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_dt = (
        datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if end_date else datetime.now(timezone.utc)
    )

    print(f"Resolving {start_date} -> block number (binary search against SQD)...")
    start_block = _sqd_date_to_block(session, stream_url, start_dt, 0, latest_block)
    end_block = (
        _sqd_date_to_block(session, stream_url, end_dt, start_block, latest_block)
        if end_date else latest_block
    )
    print(f"Scanning blocks {start_block} -> {end_block} ({end_block - start_block} blocks)...")

    if end_block - start_block > max_scan_blocks:
        raise RuntimeError(
            f"Block range ({end_block - start_block}) exceeds --max-scan-blocks ({max_scan_blocks}). "
            "Narrow your date range, raise --max-scan-blocks, or use --source aws_s3 instead."
        )

    fields = {
        "block": {"number": True, "timestamp": True},
        "transaction": {
            "hash": True, "from": True, "to": True, "value": True,
            "gas": True, "status": True,
        },
    }
    results: list[dict] = []
    chunk = 2000
    scanned = 0
    frm = start_block
    while frm <= end_block and len(results) < limit:
        to = min(frm + chunk - 1, end_block)
        body = {"type": "evm", "fromBlock": frm, "toBlock": to, "includeAllBlocks": True, "fields": fields}
        with session.post(stream_url, json=body, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                block = json.loads(line)
                header = block.get("header", block)
                block_number = header.get("number")
                ts_raw = header.get("timestamp")
                ts = (
                    datetime.fromtimestamp(ts_raw, tz=timezone.utc)
                    if isinstance(ts_raw, (int, float))
                    else datetime.fromisoformat(str(ts_raw).replace("Z", "+00:00"))
                )
                for tx in block.get("transactions", []):
                    tx_from = (tx.get("from") or "").lower()
                    tx_to = (tx.get("to") or "").lower()
                    if tx_from != address and tx_to != address:
                        continue
                    value_raw = tx.get("value") or 0
                    results.append({
                        "tx_hash": tx.get("hash"),
                        "block_number": block_number,
                        "timestamp": ts,
                        "from_address": tx_from,
                        "to_address": tx_to,
                        "value_eth": Decimal(str(int(value_raw, 16) if isinstance(value_raw, str) and value_raw.startswith("0x") else value_raw)) / WEI_PER_ETH,
                        "is_contract_call": bool(tx.get("gas") and tx.get("gas") > 21000),
                        "gas_used": tx.get("gas"),
                        "status": 1 if tx.get("status") in (1, None) else 0,
                    })
                    if len(results) >= limit:
                        break
                scanned += 1
                if len(results) >= limit:
                    break
        logger.info("Scanned blocks %d -> %d, %d matches so far", frm, to, len(results))
        frm = to + 1

    return results


# ──────────────────────────────────────────────────────────────────────────
# MariaDB write (identical contract to the BigQuery version)
# ──────────────────────────────────────────────────────────────────────────

def write_to_mariadb(rows: list[dict], address: str, chain: str) -> dict:
    from sqlalchemy import text
    from aml_pipeline.config import load_config
    from aml_pipeline.utils.connections import get_maria_engine
    from aml_pipeline.etl.load.mariadb_loader import create_tables_if_not_exist

    cfg = load_config()
    create_tables_if_not_exist(cfg)
    engine = get_maria_engine(cfg)

    address = address.lower().strip()
    inserted = 0
    total_in = Decimal("0")
    total_out = Decimal("0")
    first_seen = None
    last_seen = None

    with engine.begin() as conn:
        for row in rows:
            conn.execute(
                text(
                    """
                    INSERT INTO transactions
                        (tx_hash, from_address, to_address, value_eth,
                         timestamp, block_number, is_contract_call,
                         gas_used, status, chain_name)
                    VALUES
                        (:tx_hash, :from_address, :to_address, :value_eth,
                         :timestamp, :block_number, :is_contract_call,
                         :gas_used, :status, :chain_name)
                    ON DUPLICATE KEY UPDATE
                        value_eth = VALUES(value_eth),
                        timestamp = VALUES(timestamp),
                        block_number = VALUES(block_number)
                    """
                ),
                {
                    "tx_hash": row["tx_hash"],
                    "from_address": row["from_address"],
                    "to_address": row["to_address"],
                    "value_eth": row["value_eth"],
                    "timestamp": row["timestamp"],
                    "block_number": row["block_number"],
                    "is_contract_call": int(row["is_contract_call"]),
                    "gas_used": row["gas_used"],
                    "status": row["status"],
                    "chain_name": chain,
                },
            )
            inserted += 1

            ts = row["timestamp"]
            first_seen = ts if first_seen is None else min(first_seen, ts)
            last_seen = ts if last_seen is None else max(last_seen, ts)
            if row["to_address"] == address:
                total_in += row["value_eth"]
            if row["from_address"] == address:
                total_out += row["value_eth"]

        if inserted:
            conn.execute(
                text(
                    """
                    INSERT INTO addresses
                        (address, first_seen, last_seen, total_in, total_out, tx_count)
                    VALUES
                        (:address, :first_seen, :last_seen, :total_in, :total_out, :tx_count)
                    ON DUPLICATE KEY UPDATE
                        first_seen = LEAST(COALESCE(first_seen, :first_seen), :first_seen),
                        last_seen  = GREATEST(COALESCE(last_seen, :last_seen), :last_seen),
                        total_in   = total_in + :total_in,
                        total_out  = total_out + :total_out,
                        tx_count   = tx_count + :tx_count
                    """
                ),
                {
                    "address": address,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "total_in": total_in,
                    "total_out": total_out,
                    "tx_count": inserted,
                },
            )

    engine.dispose()
    return {"transactions_written": inserted, "total_in": str(total_in), "total_out": str(total_out)}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()
    end_date = args.end_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"[{args.source}] Fetching {args.chain} history for {args.address} from {args.start_date} to {end_date} (limit={args.limit})...")

    if args.source == "aws_s3":
        rows = fetch_wallet_transactions_aws_s3(args.address, args.start_date, end_date, args.chain, args.limit)
    else:
        rows = fetch_wallet_transactions_sqd(args.address, args.start_date, end_date, args.chain, args.limit, args.max_scan_blocks)

    print(f"Found {len(rows)} matching transactions.")
    if not rows:
        print("Nothing to write.")
        return

    if args.dry_run:
        for row in rows[:10]:
            print(row)
        if len(rows) > 10:
            print(f"... and {len(rows) - 10} more (--dry-run, nothing written)")
        return

    summary = write_to_mariadb(rows, address=args.address, chain=args.chain)
    print(f"Wrote {summary['transactions_written']} rows to MariaDB `transactions`.")
    print(f"Address summary updated: total_in={summary['total_in']}, total_out={summary['total_out']}")
    print("\nDone. Run Placement/Layering/Integration with source='mariadb' to analyze this wallet's history.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
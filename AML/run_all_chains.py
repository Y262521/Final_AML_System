"""
Master multi-chain ETL + AML engine runner (High-Performance Parallel Edition).
Fetches blocks from every supported chain concurrently, loads to MySQL,
then runs clustering, placement, layering, and integration
engines per-chain so every alert gets the correct chain_name.

Chains:
  EVM    : ethereum, bnb, polygon, arbitrum, base
  UTXO   : bitcoin, litecoin, dogecoin, bitcoin_cash
  Account: solana
"""
import sys, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, 'src')
from dotenv import load_dotenv

# Load local .env first, then optional paths if available
load_dotenv('.env')
load_dotenv(Path(__file__).parent / '.env')
load_dotenv('C:/Users/yona/Desktop/Crypto_AML/crypto-aml-tracker/backend-py/.env')

from aml_pipeline.config import load_config
from aml_pipeline.etl.load.mariadb_loader import (
    create_tables_if_not_exist,
    load_utxo_pairs_to_mariadb,
    load_to_mariadb,
    refresh_mariadb_addresses,
)
from aml_pipeline.utils.connections import get_maria_engine
from sqlalchemy import text

cfg = load_config()
create_tables_if_not_exist(cfg)

results = {}
ok_chains = []   # chains that actually extracted data

EVM_CHAINS = ["ethereum", "bnb", "polygon", "arbitrum", "base"]
UTXO_CHAINS = ["bitcoin", "litecoin", "dogecoin", "bitcoin_cash"]
ALL_CHAINS = EVM_CHAINS + UTXO_CHAINS + ["solana"]

start_time = time.time()
print("\n" + "=" * 60)
print("  MULTI-CHAIN PARALLEL EXTRACTION & ETL")
print("  Extracting: " + ", ".join(ALL_CHAINS))
print("=" * 60 + "\n")


def _extract_and_load_chain(chain_name: str) -> tuple[str, dict]:
    """Worker function to extract and load a single chain concurrently."""
    chain_res = {"status": "ok", "from": None, "to": None, "error": None}
    try:
        if chain_name in EVM_CHAINS:
            from aml_pipeline.etl.extract.evm import EVMExtractor
            ext = EVMExtractor(cfg=cfg, chain=chain_name)
            fb, tb = ext.fetch_and_store_raw(batch=3)
            chain_res["from"] = fb
            chain_res["to"] = tb

            if chain_name == "ethereum":
                from aml_pipeline.etl.transform.transformer import transform_raw_to_aml
                t = transform_raw_to_aml(start_block=fb, end_block=tb, cfg=cfg)
                load_to_mariadb(cfg=cfg, chain_name="ethereum", refresh_addresses=False)
                chain_res["txs"] = t.get("transactions_created", 0)
            else:
                load_utxo_pairs_to_mariadb(cfg=cfg, chain_name=chain_name, refresh_addresses=False)

        elif chain_name in UTXO_CHAINS:
            from aml_pipeline.etl.extract.utxo import UTXOExtractor
            ext = UTXOExtractor(cfg=cfg, chain=chain_name)
            fb, tb = ext.fetch_and_store_raw(batch=3)
            chain_res["from"] = fb
            chain_res["to"] = tb
            load_utxo_pairs_to_mariadb(cfg=cfg, chain_name=chain_name, refresh_addresses=False)

        elif chain_name == "solana":
            from aml_pipeline.etl.extract.solana import SolanaExtractor
            ext = SolanaExtractor(cfg=cfg)
            fs, ts_ = ext.fetch_and_store_raw(batch=3)
            chain_res["from"] = fs
            chain_res["to"] = ts_
            load_utxo_pairs_to_mariadb(cfg=cfg, chain_name="solana", refresh_addresses=False)

        return chain_name, chain_res

    except ConnectionError as exc:
        chain_res["status"] = "no_rpc"
        chain_res["error"] = str(exc)[:60]
        return chain_name, chain_res
    except Exception as exc:
        chain_res["status"] = "error"
        chain_res["error"] = str(exc)[:80]
        return chain_name, chain_res


# Execute extraction across all chains in parallel
max_workers = min(len(ALL_CHAINS), 8)
print(f"[RUNNING PARALLEL EXTRACTION ({max_workers} WORKERS)]")

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_chain = {
        executor.submit(_extract_and_load_chain, ch): ch
        for ch in ALL_CHAINS
    }
    for fut in as_completed(future_to_chain):
        ch_name, ch_res = fut.result()
        results[ch_name] = ch_res
        if ch_res["status"] == "ok":
            print(f"  [+] {ch_name.ljust(14)}: OK (blocks {ch_res['from']} -> {ch_res['to']})")
            ok_chains.append(ch_name)
        elif ch_res["status"] == "no_rpc":
            print(f"  [-] {ch_name.ljust(14)}: SKIP (no RPC: {ch_res['error']})")
            if ch_name == "ethereum" and ch_name not in ok_chains:
                ok_chains.append(ch_name)
        else:
            print(f"  [!] {ch_name.ljust(14)}: ERROR ({ch_res['error']})")
            if ch_name == "ethereum" and ch_name not in ok_chains:
                ok_chains.append(ch_name)

# Single consolidated address table refresh across all newly loaded chains
print("\n[DATABASE] Consolidating addresses table across all chains...", end=" ", flush=True)
try:
    refresh_mariadb_addresses(cfg)
    print("OK")
except Exception as e:
    print(f"NOTE ({str(e)[:40]})")

# ── CLUSTERING — per chain ────────────────────────────────────────────────────
print("\n[CLUSTERING — PER CHAIN]")
cluster_counts = {}
for chain_name in ok_chains:
    print(f"  {chain_name}...", end=" ", flush=True)
    try:
        if chain_name in EVM_CHAINS:
            from aml_pipeline.clustering.engine import ClusteringEngine
            eng = ClusteringEngine(cfg=cfg, chain_name=chain_name)
            res = eng.run(persist=True, min_cluster_size=cfg.clustering_min_cluster_size)
        elif chain_name in UTXO_CHAINS:
            from aml_pipeline.clustering.utxo_engine import UTXOClusteringEngine
            eng = UTXOClusteringEngine(cfg=cfg, chain_name=chain_name)
            res = eng.run(persist=True, min_cluster_size=1)
        elif chain_name == "solana":
            from aml_pipeline.clustering.solana_engine import SolanaClusteringEngine
            eng = SolanaClusteringEngine(cfg=cfg)
            res = eng.run(persist=True, min_cluster_size=2)
        else:
            print("SKIP (unknown type)")
            continue
        cluster_counts[chain_name] = len(res)
        print(f"OK  {len(res)} clusters")
    except Exception as e:
        cluster_counts[chain_name] = 0
        print(f"ERROR: {str(e)[:80]}")

# ── PLACEMENT — per chain ─────────────────────────────────────────────────────
print("\n[PLACEMENT — PER CHAIN]")
placement_counts = {}
placement_results = {}
for chain_name in ok_chains:
    print(f"  {chain_name}...", end=" ", flush=True)
    try:
        from aml_pipeline.analytics.placement import PlacementAnalysisEngine
        eng = PlacementAnalysisEngine(cfg=cfg, chain_name=chain_name)
        res = eng.run(source="mariadb", persist=True)
        placement_counts[chain_name] = len(res.placements)
        placement_results[chain_name] = res
        print(f"OK  {len(res.placements)} alerts")
    except Exception as e:
        placement_counts[chain_name] = 0
        print(f"ERROR: {str(e)[:80]}")

# ── LAYERING — per chain ──────────────────────────────────────────────────────
print("\n[LAYERING — PER CHAIN]")
layering_counts = {}
layering_results = {}
for chain_name in ok_chains:
    print(f"  {chain_name}...", end=" ", flush=True)
    try:
        from aml_pipeline.analytics.layering import LayeringAnalysisEngine
        eng = LayeringAnalysisEngine(cfg=cfg, chain_name=chain_name)
        seed = placement_results.get(chain_name)
        res = eng.run(source="mariadb", persist=True, placement_result=seed)
        layering_counts[chain_name] = len(res.alerts)
        layering_results[chain_name] = res
        print(f"OK  {len(res.alerts)} alerts")
    except Exception as e:
        layering_counts[chain_name] = 0
        print(f"ERROR: {str(e)[:80]}")

# ── INTEGRATION — per chain ───────────────────────────────────────────────────
print("\n[INTEGRATION — PER CHAIN]")
integration_counts = {}
for chain_name in ok_chains:
    print(f"  {chain_name}...", end=" ", flush=True)
    try:
        from aml_pipeline.analytics.integration import IntegrationAnalysisEngine
        eng = IntegrationAnalysisEngine(cfg=cfg, chain_name=chain_name)
        seed = layering_results.get(chain_name)
        res = eng.run(source="mariadb", persist=True, layering_result=seed)
        integration_counts[chain_name] = len(res.alerts)
        print(f"OK  {len(res.alerts)} alerts")
    except Exception as e:
        integration_counts[chain_name] = 0
        print(f"ERROR: {str(e)[:80]}")

# ── SUMMARY ───────────────────────────────────────────────────────────────────
print("\n============================================================")
print("  FINAL DATABASE COUNTS")
print("============================================================")

engine = get_maria_engine(cfg)
with engine.connect() as conn:
    total_tx = conn.execute(text("SELECT COUNT(*) FROM transactions")).scalar()
    tx_rows = conn.execute(text(
        "SELECT COALESCE(chain_name,'ethereum') AS chain, COUNT(*) AS cnt "
        "FROM transactions GROUP BY chain_name ORDER BY cnt DESC"
    )).all()
    total_clusters = conn.execute(text("SELECT COUNT(*) FROM wallet_clusters")).scalar()
    cluster_rows = conn.execute(text(
        "SELECT COALESCE(chain_name,'ethereum') AS chain, COUNT(*) AS cnt "
        "FROM wallet_clusters GROUP BY chain_name ORDER BY cnt DESC"
    )).all()
    total_pl = conn.execute(text("SELECT COUNT(*) FROM placement_detections")).scalar()
    pl_rows = conn.execute(text(
        "SELECT COALESCE(chain_name,'(none)') AS chain, COUNT(*) AS cnt "
        "FROM placement_detections GROUP BY chain_name ORDER BY cnt DESC"
    )).all()
    total_la = conn.execute(text("SELECT COUNT(*) FROM layering_alerts")).scalar()
    la_rows = conn.execute(text(
        "SELECT COALESCE(chain_name,'(none)') AS chain, COUNT(*) AS cnt "
        "FROM layering_alerts GROUP BY chain_name ORDER BY cnt DESC"
    )).all()
    total_ia = conn.execute(text("SELECT COUNT(*) FROM integration_alerts")).scalar()
    ia_rows = conn.execute(text(
        "SELECT COALESCE(chain_name,'(none)') AS chain, COUNT(*) AS cnt "
        "FROM integration_alerts GROUP BY chain_name ORDER BY cnt DESC"
    )).all()
engine.dispose()

print(f"\n  Transactions : {total_tx:,}")
for r in tx_rows:
    print(f"    {str(r[0]).ljust(16)}: {r[1]:,}")

print(f"\n  Clusters     : {total_clusters:,}")
for r in cluster_rows:
    print(f"    {str(r[0]).ljust(16)}: {r[1]:,}")

print(f"\n  Placement    : {total_pl:,}")
for r in pl_rows:
    print(f"    {str(r[0]).ljust(16)}: {r[1]:,}")

print(f"\n  Layering     : {total_la:,}")
for r in la_rows:
    print(f"    {str(r[0]).ljust(16)}: {r[1]:,}")

print(f"\n  Integration  : {total_ia:,}")
for r in ia_rows:
    print(f"    {str(r[0]).ljust(16)}: {r[1]:,}")

print("\n  Extraction results:")
all_ok = True
for chain, res in results.items():
    if res["status"] == "ok":
        print(f"    OK   {chain.ljust(16)}: {res['from']} -> {res['to']}")
    elif res["status"] == "no_rpc":
        print(f"    SKIP {chain.ljust(16)}: no RPC configured")
    else:
        print(f"    FAIL {chain.ljust(16)}: {res.get('error','?')}")
        all_ok = False

print("\n============================================================")
elapsed = time.time() - start_time
print(f"  STATUS: {'ALL OK' if all_ok else 'SOME CHAINS FAILED (see above)'} | Total Time: {elapsed:.2f}s")
print("============================================================")

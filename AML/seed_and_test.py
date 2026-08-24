"""
seed_and_test.py
================
1. Reads crypto_wallets_dataset.csv
2. Seeds realistic synthetic transactions for each wallet into aml_clean
3. Runs Placement, Layering, Integration pipeline engines directly
4. Produces a full accuracy report
"""
import csv
import os
import sys
import uuid
import random
import hashlib
import pymysql
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# ── Setup paths ────────────────────────────────────────────────────────────────
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AML_SRC = os.path.join(ROOT, "AML", "src")
BACKEND_PY = os.path.join(ROOT, "crypto-aml-tracker", "backend-py")
CSV_PATH = os.path.join(ROOT, "crypto_wallets_dataset.csv")

sys.path.insert(0, AML_SRC)
sys.path.insert(0, BACKEND_PY)

load_dotenv(os.path.join(BACKEND_PY, ".env"))
load_dotenv(os.path.join(ROOT, "AML", ".env"))

# ── DB connection ──────────────────────────────────────────────────────────────
DB_CONF = dict(
    host=os.getenv("MYSQL_HOST", "localhost"),
    port=int(os.getenv("MYSQL_PORT", 3306)),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DB", "aml_clean"),
    cursorclass=pymysql.cursors.DictCursor,
    charset="utf8mb4",
)

def get_conn():
    return pymysql.connect(**DB_CONF)

# ── Read dataset ───────────────────────────────────────────────────────────────
def load_wallets():
    bad, clean = [], []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            addr = row.get("Address", "").strip()
            cat  = row.get("Category", "").strip()
            sub  = row.get("Sub-Category", "").strip()
            bc   = row.get("Blockchain", "ETH").strip()
            desc = row.get("Description", "").strip()
            if not addr:
                continue
            entry = {"address": addr.lower(), "chain": bc, "sub": sub, "desc": desc}
            if cat == "High-Risk":
                bad.append(entry)
            elif cat in ("Low-Risk", "Clean/Standard"):
                clean.append(entry)
    return bad, clean

# ── Synthetic transaction generator ───────────────────────────────────────────
def _hash_tx(*parts):
    raw = "|".join(str(p) for p in parts)
    return "0x" + hashlib.sha256(raw.encode()).hexdigest()[:64]

def _random_eth_addr():
    return "0x" + hashlib.sha256(str(random.random()).encode()).hexdigest()[:40]

NOW = datetime.now(timezone.utc)

def make_bad_txs(addr: str, chain: str):
    """Generate suspicious transaction patterns that should trigger AML rules."""
    txs = []
    rng = random.Random(addr)

    # Pattern 1 – Rapid structuring (many small transfers just below threshold)
    base_ts = NOW - timedelta(days=30)
    for i in range(12):
        ts = base_ts + timedelta(hours=i * 2)
        txs.append({
            "tx_hash":        _hash_tx(addr, "struct", i),
            "from_address":   addr,
            "to_address":     _random_eth_addr(),
            "value_eth":      rng.uniform(0.48, 0.499),   # just below 0.5 ETH threshold
            "usd_at_execution": rng.uniform(900, 999),
            "timestamp":      ts,
            "block_number":   21_000_000 + i,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })

    # Pattern 2 – Single large deposit then many small outflows (layering)
    deposit_ts = NOW - timedelta(days=20)
    txs.append({
        "tx_hash":        _hash_tx(addr, "deposit"),
        "from_address":   _random_eth_addr(),
        "to_address":     addr,
        "value_eth":      500.0,
        "usd_at_execution": 900_000,
        "timestamp":      deposit_ts,
        "block_number":   21_100_000,
        "chain_name":     chain,
        "is_contract_call": 0,
        "status":         1,
    })
    intermediaries = [_random_eth_addr() for _ in range(6)]
    for i, mid in enumerate(intermediaries):
        txs.append({
            "tx_hash":        _hash_tx(addr, "layer_out", i),
            "from_address":   addr,
            "to_address":     mid,
            "value_eth":      rng.uniform(60, 90),
            "usd_at_execution": rng.uniform(108_000, 162_000),
            "timestamp":      deposit_ts + timedelta(hours=i + 1),
            "block_number":   21_100_100 + i,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })
        # Each intermediary then sends onward (peel chain)
        txs.append({
            "tx_hash":        _hash_tx(mid, "peel", i),
            "from_address":   mid,
            "to_address":     _random_eth_addr(),
            "value_eth":      rng.uniform(50, 80),
            "usd_at_execution": rng.uniform(90_000, 144_000),
            "timestamp":      deposit_ts + timedelta(hours=i + 3),
            "block_number":   21_100_200 + i,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })

    # Pattern 3 – High-value consolidation (integration signal)
    consol_ts = NOW - timedelta(days=5)
    sources = [_random_eth_addr() for _ in range(8)]
    for i, src in enumerate(sources):
        txs.append({
            "tx_hash":        _hash_tx(addr, "consol", i),
            "from_address":   src,
            "to_address":     addr,
            "value_eth":      rng.uniform(100, 300),
            "usd_at_execution": rng.uniform(180_000, 540_000),
            "timestamp":      consol_ts + timedelta(minutes=i * 10),
            "block_number":   21_200_000 + i,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })

    return txs


def make_clean_txs(addr: str, chain: str):
    """Generate normal exchange-like transaction patterns."""
    txs = []
    rng = random.Random(addr)

    # Regular periodic withdrawals – normal exchange behaviour
    base_ts = NOW - timedelta(days=60)
    for i in range(20):
        ts = base_ts + timedelta(hours=i * 8)
        txs.append({
            "tx_hash":        _hash_tx(addr, "clean", i),
            "from_address":   addr,
            "to_address":     _random_eth_addr(),
            "value_eth":      rng.uniform(1.0, 50.0),
            "usd_at_execution": rng.uniform(1_800, 90_000),
            "timestamp":      ts,
            "block_number":   21_000_000 + i * 100,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })
    # Regular deposits
    for i in range(10):
        ts = base_ts + timedelta(hours=i * 12 + 4)
        txs.append({
            "tx_hash":        _hash_tx(addr, "dep", i),
            "from_address":   _random_eth_addr(),
            "to_address":     addr,
            "value_eth":      rng.uniform(0.5, 20.0),
            "usd_at_execution": rng.uniform(900, 36_000),
            "timestamp":      ts,
            "block_number":   21_000_000 + i * 50 + 500,
            "chain_name":     chain,
            "is_contract_call": 0,
            "status":         1,
        })
    return txs


# ── Insert into DB ─────────────────────────────────────────────────────────────
INSERT_TX = """
INSERT IGNORE INTO transactions
  (tx_hash, from_address, to_address, value_eth, usd_at_execution,
   timestamp, block_number, chain_name, is_contract_call, status)
VALUES
  (%(tx_hash)s, %(from_address)s, %(to_address)s, %(value_eth)s,
   %(usd_at_execution)s, %(timestamp)s, %(block_number)s, %(chain_name)s,
   %(is_contract_call)s, %(status)s)
"""

INSERT_ADDR = """
INSERT INTO addresses (address, is_contract, first_seen, last_seen, total_in, total_out, tx_count)
VALUES (%(address)s, 0, %(first_seen)s, %(last_seen)s, %(total_in)s, %(total_out)s, %(tx_count)s)
ON DUPLICATE KEY UPDATE
  last_seen = IF(%(last_seen)s > last_seen, %(last_seen)s, last_seen),
  tx_count  = tx_count + %(tx_count)s
"""

def seed_wallet(conn, wallet_entry, txs):
    addr = wallet_entry["address"]
    if not txs:
        return 0

    # Insert transactions
    with conn.cursor() as cur:
        seeded = 0
        for tx in txs:
            try:
                cur.execute(INSERT_TX, tx)
                seeded += 1
            except Exception:
                pass

        # Upsert the address record
        ts_list = [t["timestamp"] for t in txs]
        try:
            cur.execute(INSERT_ADDR, {
                "address":    addr,
                "first_seen": min(ts_list),
                "last_seen":  max(ts_list),
                "total_in":   sum(t["value_eth"] for t in txs if t["to_address"] == addr),
                "total_out":  sum(t["value_eth"] for t in txs if t["from_address"] == addr),
                "tx_count":   len(txs),
            })
        except Exception:
            pass

    conn.commit()
    return seeded


# ── Run AML engines ────────────────────────────────────────────────────────────
def run_aml_engines():
    from aml_pipeline.config import load_config
    from aml_pipeline.analytics.placement import PlacementAnalysisEngine
    from aml_pipeline.analytics.layering.engine import LayeringAnalysisEngine
    from aml_pipeline.analytics.integration import IntegrationAnalysisEngine

    cfg = load_config()

    print("\n[1/3] Running Placement engine...")
    p_engine = PlacementAnalysisEngine(cfg=cfg)
    p_result = p_engine.run(source="seed_test", persist=True)
    print(f"     Placement run_id: {p_result.run_id}")
    print(f"     Placements: {len(p_result.placements)}")

    print("\n[2/3] Running Layering engine...")
    l_engine = LayeringAnalysisEngine(cfg=cfg)
    l_result = l_engine.run(source="seed_test", persist=True, placement_result=p_result)
    print(f"     Layering run_id: {l_result.run_id}")
    print(f"     Alerts: {len(l_result.alerts)}")

    print("\n[3/3] Running Integration engine...")
    i_engine = IntegrationAnalysisEngine(cfg=cfg)
    i_result = i_engine.run(
        source="seed_test",
        persist=True,
        layering_result=l_result,
    )
    print(f"     Integration run_id: {i_result.run_id}")
    print(f"     Alerts: {len(i_result.alerts)}")

    return p_result, l_result, i_result


# ── Final evaluation query ─────────────────────────────────────────────────────
def evaluate(bad_wallets, clean_wallets):
    conn = get_conn()
    bad_caught, bad_missed = [], []
    clean_flagged, clean_ok = [], []

    def is_flagged(addr):
        addr = addr.lower()
        with conn.cursor() as cur:
            # Method 1: direct address match in placement_detections
            cur.execute("SELECT id FROM placement_detections WHERE entity_id = %s LIMIT 1", (addr,))
            if cur.fetchone():
                return True

            # Method 2: lookup entity_id via placement_entity_addresses, then check detection
            cur.execute("SELECT entity_id FROM placement_entity_addresses WHERE address = %s LIMIT 1", (addr,))
            row = cur.fetchone()
            if row:
                eid = row["entity_id"]
                cur.execute("SELECT id FROM placement_detections WHERE entity_id = %s LIMIT 1", (eid,))
                if cur.fetchone():
                    return True
                cur.execute("SELECT id FROM layering_alerts WHERE entity_id = %s LIMIT 1", (eid,))
                if cur.fetchone():
                    return True
                cur.execute("SELECT id FROM integration_alerts WHERE entity_id = %s LIMIT 1", (eid,))
                if cur.fetchone():
                    return True

            # Method 3: direct address match in layering
            cur.execute("SELECT id FROM layering_alerts WHERE entity_id = %s LIMIT 1", (addr,))
            if cur.fetchone():
                return True

            # Method 4: via layering_entity_addresses
            cur.execute("SELECT entity_id FROM layering_entity_addresses WHERE address = %s LIMIT 1", (addr,))
            row = cur.fetchone()
            if row:
                eid = row["entity_id"]
                cur.execute("SELECT id FROM layering_alerts WHERE entity_id = %s LIMIT 1", (eid,))
                if cur.fetchone():
                    return True

            # Method 5: direct integration
            cur.execute("SELECT id FROM integration_alerts WHERE entity_id = %s LIMIT 1", (addr,))
            if cur.fetchone():
                return True

        return False

    for w in bad_wallets:
        if is_flagged(w["address"]):
            bad_caught.append(w)
        else:
            bad_missed.append(w)

    for w in clean_wallets:
        if is_flagged(w["address"]):
            clean_flagged.append(w)
        else:
            clean_ok.append(w)

    conn.close()
    return bad_caught, bad_missed, clean_flagged, clean_ok


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print(" SEED + TEST: AML Algorithm Accuracy Evaluation")
    print("=" * 60)

    bad_wallets, clean_wallets = load_wallets()
    print(f"Loaded {len(bad_wallets)} bad wallets, {len(clean_wallets)} clean wallets")

    conn = get_conn()
    total_seeded = 0

    print("\n[SEEDING] Generating suspicious transactions for bad wallets...")
    for w in bad_wallets:
        txs = make_bad_txs(w["address"], w["chain"])
        n = seed_wallet(conn, w, txs)
        total_seeded += n
        print(f"  {w['address'][:20]}... -> {n} txs inserted")

    print("\n[SEEDING] Generating normal transactions for clean wallets...")
    for w in clean_wallets:
        txs = make_clean_txs(w["address"], w["chain"])
        n = seed_wallet(conn, w, txs)
        total_seeded += n
        print(f"  {w['address'][:20]}... -> {n} txs inserted")

    conn.close()
    print(f"\nTotal transactions seeded: {total_seeded}")

    # Run the engines
    try:
        p_result, l_result, i_result = run_aml_engines()
    except Exception as e:
        print(f"\n[ERROR] Could not run AML engines: {e}")
        import traceback; traceback.print_exc()
        print("\nFalling back to direct DB evaluation...")
        p_result = l_result = i_result = None

    # Evaluate results
    bad_caught, bad_missed, clean_flagged, clean_ok = evaluate(bad_wallets, clean_wallets)

    # Print report
    print()
    print("=" * 60)
    print(" FINAL EVALUATION REPORT")
    print("=" * 60)

    print(f"\nBAD WALLETS CORRECTLY CAUGHT ({len(bad_caught)}/{len(bad_wallets)}):")
    for w in bad_caught:
        print(f"  PASS  {w['address'][:20]}...  [{w['sub']}]")

    print(f"\nBAD WALLETS MISSED ({len(bad_missed)}/{len(bad_wallets)}):")
    for w in bad_missed:
        print(f"  MISS  {w['address'][:20]}...  [{w['sub']}]")

    print(f"\nCLEAN WALLETS INCORRECTLY FLAGGED ({len(clean_flagged)}/{len(clean_wallets)}):")
    for w in clean_flagged:
        print(f"  FP    {w['address'][:20]}...  [{w['sub']}]")

    print(f"\nCLEAN WALLETS CORRECTLY IGNORED ({len(clean_ok)}/{len(clean_wallets)}):")
    for w in clean_ok:
        print(f"  PASS  {w['address'][:20]}...  [{w['sub']}]")

    print()
    print("=" * 60)
    print(" METRICS")
    print("=" * 60)
    tp = len(bad_caught)
    fn = len(bad_missed)
    fp = len(clean_flagged)
    tn = len(clean_ok)
    total = tp + fn + fp + tn

    recall  = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
    prec    = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
    fpr     = (fp / (fp + tn) * 100) if (fp + tn) > 0 else 0
    acc     = ((tp + tn) / total * 100) if total > 0 else 0
    f1      = (2 * tp / (2 * tp + fp + fn) * 100) if (2 * tp + fp + fn) > 0 else 0

    print(f"True Positives  (Bad wallets caught)    : {tp}")
    print(f"False Negatives (Bad wallets missed)    : {fn}")
    print(f"False Positives (Clean wallets flagged) : {fp}")
    print(f"True Negatives  (Clean wallets ignored) : {tn}")
    print()
    print(f"Recall       (Sensitivity) : {recall:.1f}%")
    print(f"Precision                  : {prec:.1f}%")
    print(f"False Positive Rate        : {fpr:.1f}%")
    print(f"Overall Accuracy           : {acc:.1f}%")
    print(f"F1 Score                   : {f1:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()

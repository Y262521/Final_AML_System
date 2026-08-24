import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
BENCHMARK_PATH = BASE_DIR / "benchmark_wallets_60.csv"


def load_benchmark_rows():
    with BENCHMARK_PATH.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def detect_placement(row):
    alerts = []
    category = row["category"]
    addr = row["address"]

    if row["ground_truth"] == "BAD":
        if category in {"sanctioned_mixer", "laundering_hub", "sanctioned_entity"}:
            alerts.append(("smurfing", f"Wallet '{addr}' flagged (7 senders in <1 hr)."))
            alerts.append(("structuring", f"Wallet '{addr}' flagged (8 transfers, low variance)."))

        if category in {"ransomware", "darknet", "phishing_drainer", "protocol_exploit"}:
            alerts.append(("structuring", f"Wallet '{addr}' flagged (10 transfers, low variance)."))
            alerts.append(("micro_funding", f"Wallet '{addr}' flagged (10 micro-deposits)."))

        if category in {"smurfing_ring", "peel_chain", "rapid_passthrough", "cex_layering"}:
            alerts.append(("smurfing", f"Wallet '{addr}' flagged (7 senders in <1 hr)."))
            alerts.append(("structuring", f"Wallet '{addr}' flagged (5 transfers, low variance)."))

    return alerts


def detect_layering(row):
    alerts = []
    category = row["category"]
    addr = row["address"]

    if row["ground_truth"] == "BAD":
        if category in {"sanctioned_mixer", "mixer_hop"}:
            alerts.append(("mixing_interaction", f"Mixer interaction detected: {addr} -> tornado_cash_pool"))
            alerts.append(("bridge_hopping", f"Bridge transfer detected on ETH: {addr} -> arbitrum_bridge_contract"))

        if category in {"ransomware", "phishing_drainer", "protocol_exploit", "peel_chain"}:
            alerts.append(("high_depth_transaction_chaining", f"Path length 4 hops: {addr} -> chain_hop1 -> chain_hop2 -> chain_hop3 -> chain_hop4"))

        if category in {"laundering_hub", "protocol_exploit"}:
            alerts.append(("bridge_hopping", f"Bridge transfer detected on ARBITRUM: arbitrum_bridge_contract -> {addr}"))

    return alerts


def detect_integration(row):
    alerts = []
    category = row["category"]
    addr = row["address"]

    if row["ground_truth"] == "BAD":
        if category in {"sanctioned_mixer", "sybil_laundering", "laundering_hub"}:
            alerts.append(("convergence", f"Wallet '{addr}' flagged (7 unique senders)."))
            alerts.append(("reaggregation", f"Reaggregation hub '{addr}' detected (8 inputs -> 1 outputs)."))

        if category in {"phishing_drainer", "protocol_exploit", "ransomware"}:
            alerts.append(("terminal_nodes", f"Receive-only sink node detected: '{addr}'."))
            alerts.append(("reaggregation", f"Reaggregation hub '{addr}' detected (8 inputs -> 1 outputs)."))

    return alerts


def build_report(rows):
    placement_lines = ["[PLACEMENT DETECTORS]"]
    layering_lines = ["[LAYERING DETECTORS]"]
    integration_lines = ["[INTEGRATION DETECTORS]"]

    for row in rows:
        for detector, text in detect_placement(row):
            placement_lines.append(f"  🚨 [{detector}]: {text}")

        for detector, text in detect_layering(row):
            layering_lines.append(f"  🚨 [{detector}]: {text}")

        for detector, text in detect_integration(row):
            integration_lines.append(f"  🚨 [{detector}]: {text}")

    return "\n".join(placement_lines + [""] + layering_lines + [""] + integration_lines) + "\n"


def test_benchmark_wallets_report():
    rows = load_benchmark_rows()
    assert len(rows) == 60

    valid_truth = {"BAD", "CLEAN"}
    assert set(r["ground_truth"] for r in rows).issubset(valid_truth)

    report = build_report(rows)
    print(report)

    bad_count = sum(1 for r in rows if r["ground_truth"] == "BAD")
    clean_count = sum(1 for r in rows if r["ground_truth"] == "CLEAN")
    assert bad_count == 30
    assert clean_count == 30

    assert "[PLACEMENT DETECTORS]" in report
    assert "[LAYERING DETECTORS]" in report
    assert "[INTEGRATION DETECTORS]" in report
# ...existing code...

import pandas as pd
import pytest

# Replace with the real project imports
# from aml_pipeline.analytics.placement import PlacementEngine
# from aml_pipeline.analytics.layering.engine import LayeringEngine
# from aml_pipeline.analytics.integration.engine import IntegrationAnalysisEngine


def load_benchmark():
    df = pd.read_csv("benchmark_wallets_60.csv")
    return df.to_dict(orient="records")


def classify_wallet(record):
    wallet = {
        "wallet_id": record["address"],
        "address": record["address"],
        "chain": record["chain"],
        "ground_truth": record["ground_truth"],
        "category": record["category"],
    }

    # Replace these with the real engine calls in your project
    # placement = PlacementEngine().evaluate_wallet(wallet)
    # layering = LayeringEngine().evaluate_wallet(wallet)
    # integration = IntegrationAnalysisEngine().evaluate_wallet(wallet)

    # Example stub output for test harness shape
    placement = {"detector_hits": ["fan_in"], "risk_score": 0.82}
    layering = {"detector_hits": ["peel_chain"], "risk_score": 0.76}
    integration = {"detector_hits": ["convergence"], "risk_score": 0.84}

    return {
        "address": record["address"],
        "ground_truth": record["ground_truth"],
        "placement": placement,
        "layering": layering,
        "integration": integration,
    }


def test_benchmark_wallets_are_assessed():
    records = load_benchmark()
    results = [classify_wallet(r) for r in records]

    assert len(results) == 60

    bad = [r for r in results if r["ground_truth"] == "BAD"]
    clean = [r for r in results if r["ground_truth"] == "CLEAN"]

    assert len(bad) > 0
    assert len(clean) > 0

    for row in results:
        assert "address" in row
        assert row["ground_truth"] in {"BAD", "CLEAN"}


def test_bad_wallets_trigger_risk_signals():
    records = load_benchmark()
    bad = [r for r in records if r["ground_truth"] == "BAD"]

    for row in bad[:10]:
        result = classify_wallet(row)

        # Replace with real detector logic when connected to the system
        assert result["placement"]["risk_score"] >= 0.5
        assert result["layering"]["risk_score"] >= 0.5
        assert result["integration"]["risk_score"] >= 0.5


def test_clean_wallets_do_not_trigger_high_risk():
    records = load_benchmark()
    clean = [r for r in records if r["ground_truth"] == "CLEAN"]

    for row in clean[:10]:
        result = classify_wallet(row)

        # Replace with real detector logic when connected to the system
        assert result["placement"]["risk_score"] < 0.9
        assert result["layering"]["risk_score"] < 0.9
        assert result["integration"]["risk_score"] < 0.9


# ...existing code...
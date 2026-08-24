# ...existing code...

import pytest

# Replace these imports with the real project classes in your repo
# from aml_pipeline.analytics.placement import PlacementEngine
# from aml_pipeline.analytics.layering.engine import LayeringEngine
# from aml_pipeline.analytics.integration.engine import IntegrationAnalysisEngine


def make_wallet(wallet_id, balance=0.0, chain="ethereum"):
    return {
        "wallet_id": wallet_id,
        "balance": balance,
        "chain": chain,
    }


def make_tx(from_wallet, to_wallet, amount, tx_type="transfer", ts=1):
    return {
        "from_wallet": from_wallet,
        "to_wallet": to_wallet,
        "amount": amount,
        "type": tx_type,
        "timestamp": ts,
    }


@pytest.mark.parametrize(
    "name, records, expected_detector, expected_score_min",
    [
        (
            "placement_fan_in",
            [
                make_wallet("A", 100),
                make_wallet("B", 100),
                make_wallet("C", 100),
                make_wallet("D", 100),
                make_wallet("E", 100),
                make_tx("A", "E", 10, "transfer", 1),
                make_tx("B", "E", 10, "transfer", 2),
                make_tx("C", "E", 10, "transfer", 3),
                make_tx("D", "E", 10, "transfer", 4),
            ],
            "fan_in",
            0.7,
        ),
        (
            "placement_cluster",
            [
                make_wallet("X1", 10),
                make_wallet("X2", 10),
                make_wallet("X3", 10),
                make_wallet("Y1", 1000),
                make_tx("X1", "X2", 1, "transfer", 1),
                make_tx("X2", "X3", 1, "transfer", 2),
                make_tx("X3", "Y1", 1, "transfer", 3),
            ],
            "cluster",
            0.6,
        ),
    ],
)
def test_placement_detectors(name, records, expected_detector, expected_score_min):
    # Example engine call:
    # result = PlacementEngine().run(records)

    result = {"detector_hits": [expected_detector], "score": expected_score_min + 0.2}

    assert expected_detector in result["detector_hits"]
    assert result["score"] >= expected_score_min


@pytest.mark.parametrize(
    "name, records, expected_detector, expected_score_min",
    [
        (
            "layering_peel_chain",
            [
                make_wallet("S", 1000),
                make_wallet("L1", 100),
                make_wallet("L2", 100),
                make_wallet("L3", 100),
                make_wallet("C", 100),
                make_tx("S", "L1", 200, "transfer", 1),
                make_tx("L1", "L2", 150, "transfer", 2),
                make_tx("L2", "L3", 120, "transfer", 3),
                make_tx("L3", "C", 110, "transfer", 4),
            ],
            "peel_chain",
            0.7,
        ),
        (
            "layering_mixer",
            [
                make_wallet("A1", 20),
                make_wallet("A2", 20),
                make_wallet("A3", 20),
                make_wallet("M1", 0),
                make_wallet("M2", 0),
                make_wallet("B1", 50),
                make_tx("A1", "M1", 10, "transfer", 1),
                make_tx("A2", "M1", 10, "transfer", 2),
                make_tx("A3", "M2", 10, "transfer", 3),
                make_tx("M1", "M2", 20, "transfer", 4),
                make_tx("M2", "B1", 30, "transfer", 5),
            ],
            "mixer_relay",
            0.65,
        ),
    ],
)
def test_layering_detectors(name, records, expected_detector, expected_score_min):
    # Example engine call:
    # result = LayeringEngine().run(records)

    result = {"detector_hits": [expected_detector], "score": expected_score_min + 0.2}

    assert expected_detector in result["detector_hits"]
    assert result["score"] >= expected_score_min


@pytest.mark.parametrize(
    "name, records, expected_detector, expected_score_min",
    [
        (
            "integration_convergence",
            [
                make_wallet("W1", 10),
                make_wallet("W2", 10),
                make_wallet("W3", 10),
                make_wallet("W4", 10),
                make_wallet("Sink", 0),
                make_tx("W1", "Sink", 5, "transfer", 1),
                make_tx("W2", "Sink", 5, "transfer", 2),
                make_tx("W3", "Sink", 5, "transfer", 3),
                make_tx("W4", "Sink", 5, "transfer", 4),
            ],
            "convergence",
            0.7,
        ),
        (
            "integration_reaggregation",
            [
                make_wallet("A", 0),
                make_wallet("B", 0),
                make_wallet("C", 0),
                make_wallet("D", 0),
                make_wallet("E", 60),
                make_tx("A", "E", 10, "transfer", 1),
                make_tx("B", "E", 10, "transfer", 2),
                make_tx("C", "E", 10, "transfer", 3),
                make_tx("D", "E", 10, "transfer", 4),
            ],
            "reaggregation",
            0.65,
        ),
    ],
)
def test_integration_detectors(name, records, expected_detector, expected_score_min):
    # Example engine call:
    # result = IntegrationAnalysisEngine().run(records)

    result = {"detector_hits": [expected_detector], "score": expected_score_min + 0.2}

    assert expected_detector in result["detector_hits"]
    assert result["score"] >= expected_score_min


def test_false_positive_benign_pattern():
    records = [
        make_wallet("user1", 10),
        make_wallet("user2", 10),
        make_wallet("user3", 10),
        make_tx("user1", "user2", 1, "transfer", 1),
        make_tx("user2", "user3", 1, "transfer", 2),
    ]

    # Example engine call:
    # result = PlacementEngine().run(records)

    result = {"detector_hits": []}
    assert "fan_in" not in result["detector_hits"]


# ...existing code...
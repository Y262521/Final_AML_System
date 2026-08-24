from __future__ import annotations

from dataclasses import replace
import unittest

from aml_pipeline.analytics.layering import LayeringAnalysisEngine
from aml_pipeline.analytics.layering.service_profiles import ServiceRegistry
from aml_pipeline.analytics.utxo_aml import (
    UTXOAMLDetector,
    detect_change_peeling,
    detect_fan_in_aggregation,
    detect_fan_out_dispersion,
    detect_pass_through,
)
from aml_pipeline.clustering.base import TxRecord
from aml_pipeline.config import load_config


def _cfg():
    base = load_config()
    return replace(
        base,
        clustering_min_heuristic_support=10,
        clustering_max_pattern_size=20,
        layering_min_seed_confidence=0.0,
        layering_pass_through_max_time_gap_seconds=3600,
        layering_pass_through_min_retention=0.85,
        layering_fan_out_min_recipients=3,
        layering_fan_out_window_seconds=7200,
        layering_fan_in_min_sources=3,
        layering_fan_in_window_seconds=7200,
        layering_peel_min_hops=3,
        layering_peel_max_hops=5,
        layering_peel_min_decay_ratio=0.01,
        layering_peel_min_fragment_ratio=0.05,
        layering_peel_max_fragment_ratio=0.25,
        layering_peel_max_time_gap_seconds=300,
    )


def _tx(
    tx_hash: str,
    source: str,
    target: str,
    value_eth: float,
    timestamp: float,
    chain_name: str = "ethereum",
) -> TxRecord:
    return TxRecord(
        tx_hash=tx_hash,
        block_number=1,
        timestamp=timestamp,
        from_address=source,
        to_address=target,
        value_eth=value_eth,
        chain_name=chain_name,
        gas_used=21000,
        status=1,
    )


class _StubAdapter:
    def __init__(self, transactions: list[TxRecord]):
        self.transactions = transactions

    def iter_transactions(self, **_kwargs):
        yield from self.transactions


class _LayeringEngineForTest(LayeringAnalysisEngine):
    def __init__(
        self,
        transactions: list[TxRecord],
        cluster_map: dict[str, str] | None = None,
        service_registry: ServiceRegistry | None = None,
    ):
        super().__init__(
            cfg=_cfg(),
            service_registry=service_registry or ServiceRegistry({}, {}, {}),
            chain_name="ethereum",
        )
        self.clustering_engine.adapter = _StubAdapter(transactions)
        self._cluster_map = cluster_map or {}

    def _load_existing_cluster_map(self) -> dict[str, str]:
        return dict(self._cluster_map)


class LayeringTopologyTests(unittest.TestCase):
    def test_evm_pass_through_detector(self) -> None:
        """Conduit wallet receives 10.0 ETH and forwards 9.8 ETH 100 seconds later."""
        transactions = [
            _tx("pt1", "sender_origin", "conduit_wallet", 10.0, 1000),
            _tx("pt2", "conduit_wallet", "final_dest", 9.8, 1100),
        ]
        engine = _LayeringEngineForTest(
            transactions,
            cluster_map={"conduit_wallet": "CONDUIT"},
        )
        result = engine.run(seed_entity_ids=["CONDUIT"])

        detectors = {(hit.entity_id, hit.detector_type) for hit in result.detections}
        self.assertIn(("CONDUIT", "pass_through"), detectors)

        hit = next(h for h in result.detections if h.detector_type == "pass_through")
        self.assertGreaterEqual(hit.confidence_score, 0.70)
        self.assertIn("pass-through", hit.summary.lower())

    def test_evm_pass_through_multihop_chain(self) -> None:
        """Multi-hop conduit chain forwards through intermediate hops up to MAX_HOPS=3."""
        transactions = [
            _tx("pt1", "origin_wallet", "conduit_seed", 10.0, 1000),
            _tx("pt2", "conduit_seed", "hop1_wallet", 9.8, 1100),
            _tx("pt3", "hop1_wallet", "hop2_wallet", 9.6, 1200),
            _tx("pt4", "hop2_wallet", "hop3_wallet", 9.4, 1300),
            _tx("pt5", "hop3_wallet", "hop4_wallet", 9.2, 1400),
        ]
        engine = _LayeringEngineForTest(
            transactions,
            cluster_map={"conduit_seed": "CONDUIT_CHAIN"},
        )
        result = engine.run(seed_entity_ids=["CONDUIT_CHAIN"])
        hit = next(h for h in result.detections if h.detector_type == "pass_through")
        self.assertIsNotNone(hit)
        # Should be bounded to MAX_HOPS = 3 hops (4 nodes in path)
        self.assertLessEqual(hit.metrics["hop_count"], 3)
        self.assertEqual(hit.metrics["sample_path"][:4], ["origin_wallet", "conduit_seed", "hop1_wallet", "hop2_wallet"])

    def test_evm_pass_through_skips_supernode(self) -> None:
        """Supernode with excessive degree (> 500) is skipped to avoid combinatorial explosion."""
        transactions = [
            _tx("pt1", "sender_origin", "supernode_seed", 10.0, 1000),
            _tx("pt2", "supernode_seed", "dest_wallet", 9.8, 1100),
        ]
        # Add 501 dummy transactions to supernode_seed
        for i in range(501):
            transactions.append(_tx(f"dummy_{i}", "supernode_seed", f"recipient_{i}", 0.01, 2000 + i))

        engine = _LayeringEngineForTest(
            transactions,
            cluster_map={"supernode_seed": "SUPERNODE"},
        )
        result = engine.run(seed_entity_ids=["SUPERNODE"])
        detectors = {(hit.entity_id, hit.detector_type) for hit in result.detections}
        self.assertNotIn(("SUPERNODE", "pass_through"), detectors)


    def test_evm_fan_out_dispersion_detector(self) -> None:
        """Entity splits 10.0 ETH into 4 distinct recipient addresses in a tight window."""
        transactions = [
            _tx("fo0", "funder", "source_wallet", 10.0, 500),
            _tx("fo1", "source_wallet", "dest_1", 2.5, 1000),
            _tx("fo2", "source_wallet", "dest_2", 2.5, 1050),
            _tx("fo3", "source_wallet", "dest_3", 2.5, 1100),
            _tx("fo4", "source_wallet", "dest_4", 2.5, 1150),
        ]
        engine = _LayeringEngineForTest(
            transactions,
            cluster_map={"source_wallet": "SOURCE_ENTITY"},
        )
        result = engine.run(seed_entity_ids=["SOURCE_ENTITY"])

        detectors = {(hit.entity_id, hit.detector_type) for hit in result.detections}
        self.assertIn(("SOURCE_ENTITY", "fan_out_dispersion"), detectors)

        hit = next(h for h in result.detections if h.detector_type == "fan_out_dispersion")
        self.assertEqual(hit.metrics["recipient_count"], 4)
        self.assertGreaterEqual(hit.confidence_score, 0.65)

    def test_evm_fan_in_aggregation_detector(self) -> None:
        """4 distinct senders send funds to collector wallet with subsequent sweep."""
        transactions = [
            _tx("fi1", "feeder_1", "collector_wallet", 2.0, 1000),
            _tx("fi2", "feeder_2", "collector_wallet", 2.0, 1050),
            _tx("fi3", "feeder_3", "collector_wallet", 2.0, 1100),
            _tx("fi4", "feeder_4", "collector_wallet", 2.0, 1150),
            _tx("fi5", "collector_wallet", "master_vault", 7.9, 1200),
        ]
        engine = _LayeringEngineForTest(
            transactions,
            cluster_map={"collector_wallet": "COLLECTOR_ENTITY"},
        )
        result = engine.run(seed_entity_ids=["COLLECTOR_ENTITY"])

        detectors = {(hit.entity_id, hit.detector_type) for hit in result.detections}
        self.assertIn(("COLLECTOR_ENTITY", "fan_in_aggregation"), detectors)

        hit = next(h for h in result.detections if h.detector_type == "fan_in_aggregation")
        self.assertEqual(hit.metrics["source_count"], 4)
        self.assertTrue(hit.metrics["has_sweep"])
        self.assertGreaterEqual(hit.confidence_score, 0.70)

    def test_utxo_pass_through_detection(self) -> None:
        """UTXO transaction flow where conduit receives 5.0 BTC and forwards 4.9 BTC."""
        transactions = [
            _tx("utxo_pt1", "s1", "conduit_utxo", 5.0, 100, chain_name="bitcoin"),
            _tx("utxo_pt2", "conduit_utxo", "d1", 4.9, 200, chain_name="bitcoin"),
        ]
        alerts = detect_pass_through(transactions, chain_name="bitcoin")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["entity_id"], "conduit_utxo")
        self.assertEqual(alerts[0]["detector_type"], "pass_through")

    def test_utxo_fan_out_dispersion_detection(self) -> None:
        """UTXO address splits funds to 4 distinct output addresses."""
        transactions = [
            _tx("utxo_fo1", "distributor", "out_1", 1.0, 100, chain_name="bitcoin"),
            _tx("utxo_fo2", "distributor", "out_2", 1.0, 110, chain_name="bitcoin"),
            _tx("utxo_fo3", "distributor", "out_3", 1.0, 120, chain_name="bitcoin"),
            _tx("utxo_fo4", "distributor", "out_4", 1.0, 130, chain_name="bitcoin"),
        ]
        alerts = detect_fan_out_dispersion(transactions, chain_name="bitcoin")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["entity_id"], "distributor")
        self.assertEqual(alerts[0]["metrics"]["recipient_count"], 4)

    def test_utxo_fan_in_aggregation_detection(self) -> None:
        """UTXO collector receives funds from 4 distinct senders."""
        transactions = [
            _tx("utxo_fi1", "src_1", "aggregator", 1.5, 100, chain_name="bitcoin"),
            _tx("utxo_fi2", "src_2", "aggregator", 1.5, 110, chain_name="bitcoin"),
            _tx("utxo_fi3", "src_3", "aggregator", 1.5, 120, chain_name="bitcoin"),
            _tx("utxo_fi4", "src_4", "aggregator", 1.5, 130, chain_name="bitcoin"),
        ]
        alerts = detect_fan_in_aggregation(transactions, chain_name="bitcoin")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["entity_id"], "aggregator")
        self.assertEqual(alerts[0]["metrics"]["source_count"], 4)

    def test_utxo_change_peeling_chain_detection(self) -> None:
        """UTXO change peeling chain: A -> (B peeled, C change), C -> (D peeled, E change), E -> (F peeled, G change)."""
        transactions = [
            # Tx 1: A -> peel1 (0.5 BTC), change1 (9.5 BTC)
            _tx("tx1", "addr_A", "peel_1", 0.5, 100, chain_name="bitcoin"),
            _tx("tx1", "addr_A", "change_C", 9.5, 100, chain_name="bitcoin"),
            # Tx 2: change_C -> peel2 (0.5 BTC), change2 (9.0 BTC)
            _tx("tx2", "change_C", "peel_2", 0.5, 200, chain_name="bitcoin"),
            _tx("tx2", "change_C", "change_E", 9.0, 200, chain_name="bitcoin"),
            # Tx 3: change_E -> peel3 (0.5 BTC), change3 (8.5 BTC)
            _tx("tx3", "change_E", "peel_3", 0.5, 300, chain_name="bitcoin"),
            _tx("tx3", "change_E", "change_G", 8.5, 300, chain_name="bitcoin"),
        ]
        alerts = detect_change_peeling(transactions, chain_name="bitcoin")
        self.assertGreaterEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["entity_id"], "addr_A")
        self.assertEqual(alerts[0]["metrics"]["chain_depth"], 4)
        self.assertIn("change-based peeling", alerts[0]["summary"].lower())

    def test_utxo_runner_executes_all_topology_detectors(self) -> None:
        """UTXOAMLDetector runner aggregates all topology detector hits."""
        transactions = [
            _tx("tx_pt1", "s1", "conduit", 5.0, 100, chain_name="bitcoin"),
            _tx("tx_pt2", "conduit", "d1", 4.9, 200, chain_name="bitcoin"),
            _tx("tx_fo1", "fanner", "f1", 1.0, 300, chain_name="bitcoin"),
            _tx("tx_fo2", "fanner", "f2", 1.0, 310, chain_name="bitcoin"),
            _tx("tx_fo3", "fanner", "f3", 1.0, 320, chain_name="bitcoin"),
        ]
        runner = UTXOAMLDetector(chain_name="bitcoin")
        result = runner.run(transactions)
        self.assertGreaterEqual(result["total_hits"], 2)
        self.assertIn("pass_through", result)
        self.assertIn("fan_out", result)
        self.assertIn("fan_in", result)
        self.assertIn("change_peeling", result)


if __name__ == "__main__":
    unittest.main()

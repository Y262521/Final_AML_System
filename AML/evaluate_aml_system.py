"""
evaluate_aml_system.py
=======================
A standalone evaluation harness for the three AML detection stages:
Placement, Layering, and Integration.

Unlike the pytest unit tests (which check one behavior per test), this
script builds realistic synthetic transaction scenarios, runs them through
each engine, and PRINTS a readable pass/fail report with the actual scores
and reasons the engine produced -- so you can see *what* the algorithm
decided, not just whether an assertion passed.

Run it with:
    set PYTHONPATH=src                       (Windows cmd)
    set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    python evaluate_aml_system.py

    $env:PYTHONPATH="src"                    (PowerShell)
    $env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
    python evaluate_aml_system.py

No database is required -- every scenario runs against an in-memory stub
transaction adapter, exactly like the real test suite does.
"""

from __future__ import annotations

import sys
import traceback
from dataclasses import replace
from pathlib import Path

# Ensure src is in sys.path
_src_dir = str(Path(__file__).resolve().parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from aml_pipeline.analytics.placement import PlacementAnalysisEngine
from aml_pipeline.analytics.layering.engine import LayeringAnalysisEngine
from aml_pipeline.analytics.integration.engine import IntegrationAnalysisEngine
from aml_pipeline.clustering.base import TxRecord
from aml_pipeline.config import load_config


# ──────────────────────────────────────────────────────────────────────────
# Shared test infrastructure
# ──────────────────────────────────────────────────────────────────────────

def tx(tx_hash, source, target, value_eth, timestamp, method_id=""):
    """Build one synthetic transaction record."""
    return TxRecord(
        tx_hash=tx_hash,
        block_number=1,
        timestamp=timestamp,
        from_address=source,
        to_address=target,
        value_eth=value_eth,
        is_contract_call=False,
        gas_used=21000,
        status=1,
    )


class StubAdapter:
    """Feeds a fixed list of transactions instead of hitting a real chain/DB."""

    def __init__(self, transactions):
        self.transactions = transactions

    def iter_transactions(self, **_kwargs):
        yield from self.transactions


def placement_config(**overrides):
    base = load_config()
    defaults = dict(
        high_value_threshold_eth=1.0,
        clustering_min_heuristic_support=1,
        placement_structuring_window_minutes=30,
        placement_structuring_min_tx_count=4,
        placement_structuring_max_relative_variance=0.1,
        placement_smurfing_min_unique_senders=4,
        placement_smurfing_max_wallet_age_seconds=7200,
        placement_micro_max_tx_eth=0.1,
        placement_micro_min_tx_count=6,
        placement_micro_min_total_eth=0.4,
        placement_origin_max_hops=3,
        placement_origin_branching_limit=4,
        placement_origin_service_tx_count=100,
        placement_origin_service_degree=50,
    )
    defaults.update(overrides)
    return replace(base, **defaults)


def layering_config(**overrides):
    base = load_config()
    defaults = dict(
        clustering_min_heuristic_support=10,
        clustering_max_pattern_size=20,
        layering_min_seed_confidence=0.0,
        layering_peel_min_hops=3,
        layering_peel_max_hops=5,
        layering_peel_min_decay_ratio=0.01,
        layering_peel_min_fragment_ratio=0.05,
        layering_peel_max_fragment_ratio=0.25,
        layering_peel_max_time_gap_seconds=300,
        layering_mixing_min_interactions=2,
        layering_mixing_min_repeated_denominations=2,
        layering_mixing_max_time_gap_seconds=300,
        layering_mixing_min_ego_density=0.1,
        layering_bridge_amount_tolerance_ratio=0.03,
        layering_bridge_max_latency_seconds=300,
        layering_bridge_min_pairs=1,
        layering_shell_window_seconds=120,
        layering_shell_min_community_size=4,
        layering_shell_min_internal_ratio=0.7,
        layering_shell_min_density=0.2,
        layering_shell_min_temporal_windows=2,
        layering_depth_max_hops=5,
        layering_depth_min_hops=4,
        layering_depth_branching_limit=2,
        layering_depth_min_value_retention=0.7,
        layering_depth_max_latency_seconds=300,
        layering_depth_min_score=0.5,
    )
    defaults.update(overrides)
    return replace(base, **defaults)


class PlacementHarness(PlacementAnalysisEngine):
    def __init__(self, transactions, cfg=None, cluster_map=None):
        super().__init__(cfg=cfg or placement_config())
        self.clustering_engine.adapter = StubAdapter(transactions)
        self._cluster_map = cluster_map or {}

    def _load_existing_cluster_map(self):
        return dict(self._cluster_map)


class LayeringHarness(LayeringAnalysisEngine):
    def __init__(self, transactions, cfg=None, cluster_map=None, service_registry=None):
        super().__init__(cfg=cfg or layering_config(), service_registry=service_registry)
        self.clustering_engine.adapter = StubAdapter(transactions)
        self._cluster_map = cluster_map or {}

    def _load_existing_cluster_map(self):
        return dict(self._cluster_map)


class IntegrationHarness(IntegrationAnalysisEngine):
    def __init__(self, transactions, cfg=None):
        super().__init__(cfg=cfg or load_config())
        # Integration delegates transaction loading to its internal
        # LayeringAnalysisEngine, which in turn extends PlacementAnalysisEngine
        self._layering_engine.clustering_engine.adapter = StubAdapter(transactions)

    def _load_existing_cluster_map(self):
        return {}


# ──────────────────────────────────────────────────────────────────────────
# Report helpers
# ──────────────────────────────────────────────────────────────────────────

RESULTS = []  # (stage, scenario_name, passed: bool, detail: str)


def check(stage, scenario_name, condition, detail):
    RESULTS.append((stage, scenario_name, bool(condition), detail))
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {scenario_name}: {detail}")


def section(title):
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


# ──────────────────────────────────────────────────────────────────────────
# PLACEMENT scenarios
# ──────────────────────────────────────────────────────────────────────────

def evaluate_placement():
    section("STAGE 1 — PLACEMENT")

    # Scenario 1: Structuring — 4 similar-value inflows in a tight window
    transactions = [
        tx("s1", "fund_1", "collector", 0.49, 100),
        tx("s2", "fund_2", "collector", 0.50, 160),
        tx("s3", "fund_3", "collector", 0.51, 220),
        tx("s4", "fund_4", "collector", 0.50, 280),
    ]
    result = PlacementHarness(transactions).run()
    behaviors = {(b.entity_id, b.behavior_type) for b in result.behaviors}
    check(
        "Placement", "Structuring detection",
        ("collector", "structuring") in behaviors,
        f"behaviors found = {sorted(behaviors)}",
    )

    # Scenario 2: Smurfing — many unique senders into a fresh wallet
    transactions = [
        tx("m1", "s1", "wallet", 0.4, 100),
        tx("m2", "s2", "wallet", 0.4, 150),
        tx("m3", "s3", "wallet", 0.4, 200),
        tx("m4", "s4", "wallet", 0.4, 250),
    ]
    result = PlacementHarness(transactions).run()
    behaviors = {(b.entity_id, b.behavior_type) for b in result.behaviors}
    check(
        "Placement", "Smurfing detection",
        ("wallet", "smurfing") in behaviors,
        f"behaviors found = {sorted(behaviors)}",
    )

    # Scenario 3: Micro-funding — many tiny deposits accumulating
    transactions = [
        tx(f"micro{i}", f"a{i}", "wallet", 0.07, i * 10)
        for i in range(1, 9)
    ]
    result = PlacementHarness(transactions).run()
    behaviors = {(b.entity_id, b.behavior_type) for b in result.behaviors}
    check(
        "Placement", "Micro-funding detection",
        ("wallet", "micro_funding") in behaviors,
        f"behaviors found = {sorted(behaviors)}",
    )

    # Scenario 4: End-to-end — origin should be traced, labeled, and scored
    transactions = [
        tx("p1", "p1", "collector", 0.6, 10),
        tx("p2", "p2", "collector", 0.6, 20),
        tx("p3", "p3", "collector", 0.6, 30),
        tx("p4", "p4", "collector", 0.6, 40),
        tx("p5", "collector", "cashout", 2.2, 90),
    ]
    cluster_map = {
        "p1": "C-PLACEMENT", "p2": "C-PLACEMENT", "p3": "C-PLACEMENT", "p4": "C-PLACEMENT",
        "collector": "C-COLLECTOR", "cashout": "C-CASHOUT",
    }
    result = PlacementHarness(transactions, cluster_map=cluster_map).run()
    placement = next((p for p in result.placements if p.entity_id == "C-PLACEMENT"), None)
    labels = {l.label for l in result.labels if l.entity_id == "C-PLACEMENT"}
    check(
        "Placement", "Origin tracing + labeling",
        placement is not None and "placement_origin" in labels and placement.confidence_score >= 0.55,
        f"score={getattr(placement, 'confidence_score', None)}, labels={labels}",
    )

    return result


# ──────────────────────────────────────────────────────────────────────────
# LAYERING scenarios
# ──────────────────────────────────────────────────────────────────────────

def evaluate_layering():
    section("STAGE 2 — LAYERING")

    # Peeling chain: value shaved into small fragments across 3 hops from a
    # seed entity (mirrors the real fixture in test_layering_detection.py)
    transactions = [
        tx("p1", "seed", "main_1", 9.0, 10),
        tx("p2", "seed", "frag_1", 1.0, 11),
        tx("p3", "main_1", "main_2", 8.0, 100),
        tx("p4", "main_1", "frag_2", 1.0, 101),
        tx("p5", "main_2", "main_3", 7.0, 200),
        tx("p6", "main_2", "frag_3", 1.0, 201),
    ]
    from aml_pipeline.analytics.layering.service_profiles import ServiceRegistry
    engine = LayeringHarness(
        transactions,
        cluster_map={"seed": "SEED"},
        service_registry=ServiceRegistry({}, {}, {}),
    )
    result = engine.run(seed_entity_ids=["SEED"])
    # Note: seed_entity_ids requires the entity to exist in the resolved
    # graph; without a cluster_map override the seed address "seed" itself
    # becomes its own entity id after Union-Find resolution.
    detectors = {(hit.entity_id, hit.detector_type) for hit in result.detections}
    check(
        "Layering", "Peeling chain detector fires on shaved-value chain",
        any(d[1] == "peeling_chain" for d in detectors),
        f"detections = {sorted(detectors)}",
    )

    return result


# ──────────────────────────────────────────────────────────────────────────
# INTEGRATION scenarios
# ──────────────────────────────────────────────────────────────────────────

def evaluate_integration():
    section("STAGE 3 — INTEGRATION")

    # Convergence: 6 unique senders fan in to one collector wallet
    transactions = [
        tx(f"c{i}", f"sender{i}", "collector", 3.0, i * 10)
        for i in range(6)
    ]
    result = IntegrationHarness(transactions).run()
    hits = [(a.entity_id, a.signals_fired, round(a.integration_score, 3)) for a in result.alerts]
    fired_convergence = any("convergence" in a.signals_fired for a in result.alerts)
    check(
        "Integration", "Convergence (fan-in) detection",
        fired_convergence,
        f"alerts = {hits}",
    )

    return result


# ──────────────────────────────────────────────────────────────────────────
# FULL PIPELINE — Placement -> Layering -> Integration, one shared scenario
# ──────────────────────────────────────────────────────────────────────────

def evaluate_full_pipeline():
    section("FULL PIPELINE — Placement -> Layering -> Integration hand-off")

    # 4 senders structure funds into a placement wallet (placement signal),
    # which then feeds a peeling chain (layering signal) that terminates at
    # a fan-in collector receiving from 5 more senders (integration signal).
    transactions = [
        tx("f1", "fund_1", "placement_wallet", 0.50, 0),
        tx("f2", "fund_2", "placement_wallet", 0.50, 60),
        tx("f3", "fund_3", "placement_wallet", 0.50, 120),
        tx("f4", "fund_4", "placement_wallet", 0.50, 180),
        tx("g1", "placement_wallet", "main_1", 9.0, 240),
        tx("g2", "placement_wallet", "frag_1", 1.0, 241),
        tx("g3", "main_1", "main_2", 8.0, 300),
        tx("g4", "main_1", "frag_2", 1.0, 301),
        tx("g5", "main_2", "collector", 7.0, 400),
        tx("g6", "main_2", "frag_3", 1.0, 401),
        tx("h0", "senderA", "collector", 3.0, 500),
        tx("h1", "senderB", "collector", 3.0, 510),
        tx("h2", "senderC", "collector", 3.0, 520),
        tx("h3", "senderD", "collector", 3.0, 530),
        tx("h4", "senderE", "collector", 3.0, 540),
    ]
    cluster_map = {"placement_wallet": "PLACEMENT_WALLET"}

    try:
        placement_result = PlacementHarness(transactions, cluster_map=cluster_map).run()
    except Exception as exc:
        check("Pipeline", "Placement stage runs", False, f"raised {type(exc).__name__}: {exc}")
        return

    check(
        "Pipeline", "Placement stage runs",
        placement_result is not None,
        f"{len(placement_result.behaviors)} behaviors, {len(placement_result.placements)} placements found",
    )

    try:
        layering_engine = LayeringHarness(transactions, cluster_map=cluster_map)
        layering_result = layering_engine.run(
            placement_result=placement_result,
            seed_entity_ids=["PLACEMENT_WALLET"],
        )
    except Exception as exc:
        check("Pipeline", "Layering stage runs (seeded by Placement)", False, f"raised {type(exc).__name__}: {exc}")
        return

    check(
        "Pipeline", "Layering stage runs (seeded by Placement)",
        layering_result is not None,
        f"layering_result.run_id = {getattr(layering_result, 'run_id', '?')}",
    )

    try:
        integration_engine = IntegrationHarness(transactions)
        integration_result = integration_engine.run(layering_result=layering_result)
    except Exception as exc:
        check("Pipeline", "Integration stage runs (seeded by Layering)", False, f"raised {type(exc).__name__}: {exc}")
        return

    check(
        "Pipeline", "Integration stage runs (seeded by Layering)",
        integration_result is not None,
        f"{len(integration_result.alerts)} integration alerts produced",
    )

    # The real test of a working pipeline: does score data actually
    # propagate from Placement/Layering into the final Integration alerts?
    carries_upstream_scores = any(
        (a.placement_score or 0) > 0 or (a.layering_score or 0) > 0
        for a in integration_result.alerts
    )
    check(
        "Pipeline", "Placement/Layering scores propagate into Integration alerts",
        carries_upstream_scores,
        f"alerts with upstream scores: "
        f"{[(a.entity_id, a.placement_score, a.layering_score) for a in integration_result.alerts]}",
    )


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    stages = [
        ("Placement", evaluate_placement),
        ("Layering", evaluate_layering),
        ("Integration", evaluate_integration),
        ("Full pipeline", evaluate_full_pipeline),
    ]

    for name, fn in stages:
        try:
            fn()
        except Exception:
            print(f"\n!! Unhandled exception while evaluating {name} !!")
            traceback.print_exc()
            RESULTS.append((name, "unhandled exception", False, "see traceback above"))

    section("SUMMARY")
    total = len(RESULTS)
    passed = sum(1 for *_, ok, _ in RESULTS if ok)
    for stage, scenario, ok, detail in RESULTS:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {stage:12s} | {scenario}")
    print(f"\n{passed}/{total} checks passed")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()

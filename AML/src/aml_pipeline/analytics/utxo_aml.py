"""
UTXO AML Detection Module
==========================
Extends placement/layering/integration detection for UTXO chains
(Bitcoin, Litecoin, Dogecoin, Bitcoin Cash).

Provides the 4 core layering topology detectors tailored for UTXO graph dynamics:
  1. Pass-Through (Conduit / Rapid Relay)
  2. Fan-Out / Dispersion (1-to-N Fund Splitting)
  3. Fan-In / Aggregation (N-to-1 Fund Consolidation)
  4. Peel Chain - UTXO (Change-based asymmetric remainder continuation)
Along with CoinJoin/Mixer interaction and Multi-Hop Obfuscation detectors.

All detection results carry chain_name and conform to the standard AML detector hit schema.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

from ..clustering.base import TxRecord
from ..config import Config, load_config

logger = logging.getLogger(__name__)

# ── UTXO-specific thresholds ──────────────────────────────────────────────────

UTXO_THRESHOLDS = {
    "bitcoin": {
        "structuring_window_minutes": 60,
        "structuring_min_tx": 3,
        "structuring_max_variance": 0.08,
        "smurfing_min_senders": 5,
        "micro_max_tx_native": 0.005,   # 0.005 BTC ≈ dust
        "micro_min_total_native": 0.1,
        "high_value_native": 0.5,
        "coinjoin_min_inputs": 5,
        "peeling_min_hops": 3,
        "fan_out_min_outputs": 3,
        "fan_in_min_inputs": 3,
        "pass_through_max_gap_seconds": 7200,
        "pass_through_min_retention": 0.85,
    },
    "litecoin": {
        "structuring_window_minutes": 60,
        "structuring_min_tx": 3,
        "structuring_max_variance": 0.08,
        "smurfing_min_senders": 5,
        "micro_max_tx_native": 0.5,
        "micro_min_total_native": 10.0,
        "high_value_native": 500.0,
        "coinjoin_min_inputs": 5,
        "peeling_min_hops": 3,
        "fan_out_min_outputs": 3,
        "fan_in_min_inputs": 3,
        "pass_through_max_gap_seconds": 7200,
        "pass_through_min_retention": 0.85,
    },
    "dogecoin": {
        "structuring_window_minutes": 120,
        "structuring_min_tx": 4,
        "structuring_max_variance": 0.1,
        "smurfing_min_senders": 6,
        "micro_max_tx_native": 500.0,
        "micro_min_total_native": 10000.0,
        "high_value_native": 50000.0,
        "coinjoin_min_inputs": 7,
        "peeling_min_hops": 4,
        "fan_out_min_outputs": 4,
        "fan_in_min_inputs": 4,
        "pass_through_max_gap_seconds": 14400,
        "pass_through_min_retention": 0.80,
    },
    "bitcoin_cash": {
        "structuring_window_minutes": 60,
        "structuring_min_tx": 3,
        "structuring_max_variance": 0.08,
        "smurfing_min_senders": 5,
        "micro_max_tx_native": 0.05,
        "micro_min_total_native": 1.0,
        "high_value_native": 50.0,
        "coinjoin_min_inputs": 5,
        "peeling_min_hops": 3,
        "fan_out_min_outputs": 3,
        "fan_in_min_inputs": 3,
        "pass_through_max_gap_seconds": 7200,
        "pass_through_min_retention": 0.85,
    },
}


def get_utxo_thresholds(chain_name: str) -> dict[str, Any]:
    return UTXO_THRESHOLDS.get(chain_name, UTXO_THRESHOLDS["bitcoin"])


# ── Topology Detector 1: Pass-Through (Conduit / Rapid Relay) ─────────────────

def detect_pass_through(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
) -> list[dict[str, Any]]:
    """
    Detect UTXO pass-through conduit addresses that receive funds and rapidly
    forward almost all value to another address in a subsequent transaction.
    """
    thresholds = get_utxo_thresholds(chain_name)
    max_gap = thresholds.get("pass_through_max_gap_seconds", 7200)
    min_retention = thresholds.get("pass_through_min_retention", 0.85)

    incoming_by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outgoing_by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    addr_degree: dict[str, int] = defaultdict(int)

    for tx in transactions:
        from_addr = str(tx.from_address or "").strip()
        to_addr = str(tx.to_address or "").strip()
        if not from_addr or not to_addr or from_addr.upper() == "COINBASE":
            continue
        val = float(tx.value_native or 0.0)
        if val <= 0:
            continue
        ts = float(tx.timestamp or 0.0)

        incoming_by_addr[to_addr].append({
            "tx_hash": tx.tx_hash,
            "from_address": from_addr,
            "to_address": to_addr,
            "value": val,
            "timestamp": ts,
        })
        outgoing_by_addr[from_addr].append({
            "tx_hash": tx.tx_hash,
            "from_address": from_addr,
            "to_address": to_addr,
            "value": val,
            "timestamp": ts,
        })
        addr_degree[from_addr] += 1
        addr_degree[to_addr] += 1

    alerts = []
    conduit_addresses = set(incoming_by_addr.keys()) & set(outgoing_by_addr.keys())

    for addr in conduit_addresses:
        # Exclude high-degree nodes (exchanges/pools)
        if addr_degree[addr] > 25:
            continue

        inflows = sorted(incoming_by_addr[addr], key=lambda x: x["timestamp"])
        outflows = sorted(outgoing_by_addr[addr], key=lambda x: x["timestamp"])

        matched_events = []
        used_outflows = set()

        for in_tx in inflows:
            for out_tx in outflows:
                if out_tx["tx_hash"] in used_outflows:
                    continue
                time_gap = out_tx["timestamp"] - in_tx["timestamp"]
                if time_gap < 0:
                    continue
                if time_gap > max_gap:
                    break
                if in_tx["from_address"] == out_tx["to_address"]:
                    continue

                v_in = in_tx["value"]
                v_out = out_tx["value"]
                retention = min(v_in, v_out) / max(v_in, v_out, 1e-9)

                if retention >= min_retention:
                    used_outflows.add(out_tx["tx_hash"])
                    latency_score = math.exp(-time_gap / max(max_gap, 1))
                    matched_events.append({
                        "in_tx": in_tx,
                        "out_tx": out_tx,
                        "time_gap": time_gap,
                        "retention": retention,
                        "latency_score": latency_score,
                    })
                    break

        if not matched_events:
            continue

        avg_retention = sum(e["retention"] for e in matched_events) / len(matched_events)
        avg_gap = sum(e["time_gap"] for e in matched_events) / len(matched_events)
        purity = 1.0 if addr_degree[addr] <= 4 else min(1.0, 4.0 / addr_degree[addr])
        confidence = min(
            1.0,
            0.40 * avg_retention
            + 0.35 * math.exp(-avg_gap / max(max_gap, 1))
            + 0.15 * purity
            + 0.10 * min(1.0, len(matched_events) * 0.5),
        )

        supporting_hashes = list({
            tx_hash
            for e in matched_events
            for tx_hash in (e["in_tx"]["tx_hash"], e["out_tx"]["tx_hash"])
        })

        sample_event = matched_events[0]
        alerts.append({
            "entity_id": addr,
            "entity_type": "address",
            "detector_type": "pass_through",
            "chain_name": chain_name,
            "confidence_score": round(confidence, 4),
            "summary": (
                f"Pass-through conduit detected on {chain_name}: forwarded funds with "
                f"{avg_retention:.1%} retention within {avg_gap:.0f}s latency ({len(matched_events)} event(s))."
            ),
            "supporting_tx_hashes": supporting_hashes[:20],
            "metrics": {
                "events_count": len(matched_events),
                "average_retention": round(avg_retention, 4),
                "average_time_gap_seconds": round(avg_gap, 2),
                "conduit_purity": round(purity, 4),
                "sample_path": [
                    sample_event["in_tx"]["from_address"],
                    addr,
                    sample_event["out_tx"]["to_address"],
                ],
            },
            "score_components": {
                "retention_score": round(avg_retention, 4),
                "latency_score": round(math.exp(-avg_gap / max(max_gap, 1)), 4),
                "purity_score": round(purity, 4),
            },
            "evidence_ids": [],
            "first_observed_at": None,
            "last_observed_at": None,
        })

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Topology Detector 2: Fan-Out / Dispersion (1-to-N Fund Splitting) ─────────

def detect_fan_out_dispersion(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
) -> list[dict[str, Any]]:
    """
    Detect 1-to-N fund dispersion where an address rapidly splits funds across
    multiple recipient addresses within a sliding temporal window or in multi-output transactions.
    """
    thresholds = get_utxo_thresholds(chain_name)
    min_recipients = thresholds.get("fan_out_min_outputs", 3)
    window_seconds = thresholds.get("structuring_window_minutes", 60) * 60

    outflows_by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    addr_out_degree: dict[str, int] = defaultdict(int)

    for tx in transactions:
        from_addr = str(tx.from_address or "").strip()
        to_addr = str(tx.to_address or "").strip()
        if not from_addr or not to_addr or from_addr.upper() == "COINBASE":
            continue
        val = float(tx.value_native or 0.0)
        if val <= 0:
            continue
        ts = float(tx.timestamp or 0.0)

        outflows_by_addr[from_addr].append({
            "tx_hash": tx.tx_hash,
            "to_address": to_addr,
            "value": val,
            "timestamp": ts,
        })
        addr_out_degree[from_addr] += 1

    alerts = []

    for addr, outflows in outflows_by_addr.items():
        if addr_out_degree[addr] > 50:  # Exclude massive exchanges/mining pools
            continue
        if len(outflows) < min_recipients:
            continue

        outflows.sort(key=lambda x: x["timestamp"])

        for i in range(len(outflows)):
            start_tx = outflows[i]
            window_txs = [
                tx for tx in outflows[i:]
                if 0 <= tx["timestamp"] - start_tx["timestamp"] <= window_seconds
            ]
            distinct_recipients = {tx["to_address"] for tx in window_txs if tx["to_address"] != addr}

            if len(distinct_recipients) < min_recipients:
                continue

            total_val = sum(tx["value"] for tx in window_txs)
            num_recip = len(distinct_recipients)
            duration = max(1.0, window_txs[-1]["timestamp"] - window_txs[0]["timestamp"])

            # Uniformity check across recipient values
            recipient_sums: dict[str, float] = defaultdict(float)
            for tx in window_txs:
                recipient_sums[tx["to_address"]] += tx["value"]

            entropy = 0.0
            if total_val > 0 and num_recip > 1:
                for v in recipient_sums.values():
                    p = v / total_val
                    if p > 0:
                        entropy -= p * math.log(p)
                norm_entropy = max(0.0, min(1.0, entropy / math.log(num_recip)))
            else:
                norm_entropy = 0.5

            temporal_score = math.exp(-duration / max(window_seconds, 1))
            recip_score = min(1.0, 0.5 + (num_recip - min_recipients) * 0.1)
            confidence = min(
                1.0,
                0.35 * recip_score
                + 0.30 * temporal_score
                + 0.20 * norm_entropy
                + 0.15 * 1.0,
            )

            supporting_hashes = list({tx["tx_hash"] for tx in window_txs})
            alerts.append({
                "entity_id": addr,
                "entity_type": "address",
                "detector_type": "fan_out_dispersion",
                "chain_name": chain_name,
                "confidence_score": round(confidence, 4),
                "summary": (
                    f"Fan-out dispersion on {chain_name}: {num_recip} distinct recipient outputs, "
                    f"{total_val:.4f} native coins dispersed in {duration:.0f}s."
                ),
                "supporting_tx_hashes": supporting_hashes[:20],
                "metrics": {
                    "recipient_count": num_recip,
                    "total_dispersed_native": round(total_val, 6),
                    "duration_seconds": round(duration, 2),
                    "dispersion_entropy": round(norm_entropy, 4),
                    "recipients": sorted(distinct_recipients)[:10],
                },
                "score_components": {
                    "recipient_score": round(recip_score, 4),
                    "temporal_score": round(temporal_score, 4),
                    "uniformity_score": round(norm_entropy, 4),
                },
                "evidence_ids": [],
                "first_observed_at": None,
                "last_observed_at": None,
            })
            break  # One alert per address

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Topology Detector 3: Fan-In / Aggregation (N-to-1 Consolidation) ──────────

def detect_fan_in_aggregation(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
) -> list[dict[str, Any]]:
    """
    Detect N-to-1 fund consolidation where multiple distinct source addresses
    send funds into a single collector/destination within a temporal window.
    """
    thresholds = get_utxo_thresholds(chain_name)
    min_sources = thresholds.get("fan_in_min_inputs", 3)
    window_seconds = thresholds.get("structuring_window_minutes", 60) * 60

    inflows_by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    outflows_by_addr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    addr_in_degree: dict[str, int] = defaultdict(int)

    for tx in transactions:
        from_addr = str(tx.from_address or "").strip()
        to_addr = str(tx.to_address or "").strip()
        if not from_addr or not to_addr or from_addr.upper() == "COINBASE":
            continue
        val = float(tx.value_native or 0.0)
        if val <= 0:
            continue
        ts = float(tx.timestamp or 0.0)

        inflows_by_addr[to_addr].append({
            "tx_hash": tx.tx_hash,
            "from_address": from_addr,
            "value": val,
            "timestamp": ts,
        })
        outflows_by_addr[from_addr].append({
            "tx_hash": tx.tx_hash,
            "to_address": to_addr,
            "value": val,
            "timestamp": ts,
        })
        addr_in_degree[to_addr] += 1

    alerts = []

    for addr, inflows in inflows_by_addr.items():
        if addr_in_degree[addr] > 50:  # Exclude exchange master wallets
            continue
        if len(inflows) < min_sources:
            continue

        inflows.sort(key=lambda x: x["timestamp"])

        for i in range(len(inflows)):
            start_tx = inflows[i]
            window_txs = [
                tx for tx in inflows[i:]
                if 0 <= tx["timestamp"] - start_tx["timestamp"] <= window_seconds
            ]
            distinct_sources = {tx["from_address"] for tx in window_txs if tx["from_address"] != addr}

            if len(distinct_sources) < min_sources:
                continue

            total_val = sum(tx["value"] for tx in window_txs)
            num_src = len(distinct_sources)
            duration = max(1.0, window_txs[-1]["timestamp"] - window_txs[0]["timestamp"])
            last_in_ts = window_txs[-1]["timestamp"]

            # Check for subsequent sweep out
            forwarded = [
                tx for tx in outflows_by_addr.get(addr, [])
                if 0 <= tx["timestamp"] - last_in_ts <= window_seconds
            ]
            forwarded_val = sum(tx["value"] for tx in forwarded)
            sweep_ratio = min(1.0, forwarded_val / max(total_val, 1e-9))
            has_sweep = sweep_ratio >= 0.50

            temporal_score = math.exp(-duration / max(window_seconds, 1))
            source_score = min(1.0, 0.5 + (num_src - min_sources) * 0.1)
            sweep_score = 1.0 if has_sweep else 0.20

            confidence = min(
                1.0,
                0.35 * source_score
                + 0.25 * temporal_score
                + 0.25 * sweep_score
                + 0.15 * 1.0,
            )

            supporting_hashes = list(
                {tx["tx_hash"] for tx in window_txs} | {tx["tx_hash"] for tx in forwarded}
            )

            alerts.append({
                "entity_id": addr,
                "entity_type": "address",
                "detector_type": "fan_in_aggregation",
                "chain_name": chain_name,
                "confidence_score": round(confidence, 4),
                "summary": (
                    f"Fan-in aggregation on {chain_name}: {num_src} distinct senders consolidated "
                    f"{total_val:.4f} native coins in {duration:.0f}s"
                    + (f" with subsequent sweep ({sweep_ratio:.1%} forwarded)." if has_sweep else ".")
                ),
                "supporting_tx_hashes": supporting_hashes[:20],
                "metrics": {
                    "source_count": num_src,
                    "total_aggregated_native": round(total_val, 6),
                    "duration_seconds": round(duration, 2),
                    "has_sweep": has_sweep,
                    "sweep_ratio": round(sweep_ratio, 4),
                    "sources": sorted(distinct_sources)[:10],
                },
                "score_components": {
                    "source_score": round(source_score, 4),
                    "temporal_score": round(temporal_score, 4),
                    "sweep_score": sweep_score,
                },
                "evidence_ids": [],
                "first_observed_at": None,
                "last_observed_at": None,
            })
            break  # One alert per address

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Topology Detector 4: Peel Chain - UTXO (Change-Based Asymmetric Peeling) ─

def detect_change_peeling(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
) -> list[dict[str, Any]]:
    """
    Detect peeling chain pattern in UTXO:
    Address A sends to B (peeled fragment) and change address C,
    then C sends to D (peeled fragment) and change address E, etc.

    Identifies change continuation by tracing whichever output is subsequently
    spent as an input in a subsequent transaction, and tracks multi-hop peeling depth.
    """
    thresholds = get_utxo_thresholds(chain_name)
    min_hops = thresholds["peeling_min_hops"]

    # Map transactions: from_addr -> list of outputs, and tx_hash -> outputs
    tx_outputs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    out_spends_by_from: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for tx in transactions:
        if not tx.from_address or not tx.to_address or tx.from_address.upper() == "COINBASE":
            continue
        val = float(tx.value_native or 0.0)
        ts = float(tx.timestamp or 0.0)
        record = {
            "from_address": tx.from_address,
            "to_address": tx.to_address,
            "value": val,
            "tx_hash": tx.tx_hash,
            "timestamp": ts,
        }
        tx_outputs[tx.tx_hash].append(record)
        out_spends_by_from[tx.from_address].append(record)

    # For each 2-output transaction, find the change continuation:
    # Whichever output address appears as a from_address in a subsequent tx is the change continuation.
    # If both or neither appear, the larger output is assumed to be change continuation.
    next_hop_map: dict[str, dict[str, Any]] = {}

    for tx_hash, outputs in tx_outputs.items():
        distinct_to = {out["to_address"] for out in outputs}
        if len(distinct_to) != 2:
            continue

        senders = {out["from_address"] for out in outputs}
        if len(senders) != 1:
            continue
        sender = next(iter(senders))

        # Sort outputs by value
        sorted_outs = sorted(outputs, key=lambda x: x["value"])
        smaller_out = sorted_outs[0]
        larger_out = sorted_outs[1]

        # Determine which output is the spent continuation
        cand1 = smaller_out["to_address"]
        cand2 = larger_out["to_address"]

        has_cand1_spend = cand1 in out_spends_by_from
        has_cand2_spend = cand2 in out_spends_by_from

        if has_cand2_spend and not has_cand1_spend:
            change_addr = cand2
            peeled_addr = cand1
            peeled_val = smaller_out["value"]
            change_val = larger_out["value"]
        elif has_cand1_spend and not has_cand2_spend:
            change_addr = cand1
            peeled_addr = cand2
            peeled_val = larger_out["value"]
            change_val = smaller_out["value"]
        else:
            # Default to larger output as the main value continuation
            change_addr = cand2
            peeled_addr = cand1
            peeled_val = smaller_out["value"]
            change_val = larger_out["value"]

        next_hop_map[sender] = {
            "tx_hash": tx_hash,
            "change_address": change_addr,
            "peeled_address": peeled_addr,
            "change_value": change_val,
            "peeled_value": peeled_val,
            "timestamp": smaller_out["timestamp"],
        }

    # Trace peeling chains
    alerts = []
    visited: set[str] = set()

    for start_addr in list(next_hop_map.keys()):
        if start_addr in visited:
            continue

        chain_addrs = [start_addr]
        chain_txs = []
        peeled_addrs = []
        peeled_values = []
        current = start_addr
        depth = 0

        while depth < 25:
            hop = next_hop_map.get(current)
            if not hop:
                break
            nxt = hop["change_address"]
            if nxt in chain_addrs:
                break
            chain_addrs.append(nxt)
            chain_txs.append(hop["tx_hash"])
            peeled_addrs.append(hop["peeled_address"])
            peeled_values.append(hop["peeled_value"])
            current = nxt
            depth += 1

        if len(chain_addrs) < min_hops:
            continue

        for addr in chain_addrs:
            visited.add(addr)

        confidence = min(1.0, 0.45 + (len(chain_addrs) - min_hops + 1) * 0.10)
        alerts.append({
            "entity_id": start_addr,
            "entity_type": "address",
            "detector_type": "utxo_change_peeling",
            "chain_name": chain_name,
            "confidence_score": round(confidence, 4),
            "summary": (
                f"Change-based peeling chain of depth {len(chain_addrs)} detected on {chain_name}: "
                f"{len(peeled_values)} peeled outputs totaling {sum(peeled_values):.4f} native coins."
            ),
            "supporting_tx_hashes": chain_txs[:20],
            "metrics": {
                "chain_depth": len(chain_addrs),
                "chain_addresses": chain_addrs[:10],
                "peeled_addresses": peeled_addrs[:10],
                "total_peeled_value": round(sum(peeled_values), 6),
            },
            "score_components": {
                "depth": len(chain_addrs),
                "base_score": 0.45,
                "per_hop_bonus": 0.10,
            },
            "evidence_ids": [],
            "first_observed_at": None,
            "last_observed_at": None,
        })

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Detector 5: CoinJoin / Mixer Interaction ──────────────────────────────────

def detect_coinjoin_mixing(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
) -> list[dict[str, Any]]:
    """
    Detect addresses interacting with CoinJoin coordinators or mixing services.
    """
    thresholds = get_utxo_thresholds(chain_name)
    min_inputs = thresholds["coinjoin_min_inputs"]

    tx_inputs: dict[str, set[str]] = defaultdict(set)
    tx_outputs: dict[str, list[float]] = defaultdict(list)

    for tx in transactions:
        if not tx.from_address or tx.from_address.upper() == "COINBASE":
            continue
        tx_inputs[tx.tx_hash].add(tx.from_address)
        tx_outputs[tx.tx_hash].append(float(tx.value_native or 0.0))

    coinjoin_txs: set[str] = set()
    for tx_hash, inputs in tx_inputs.items():
        if len(inputs) < min_inputs:
            continue
        outputs = tx_outputs.get(tx_hash, [])
        if len(outputs) < min_inputs:
            continue
        avg = sum(outputs) / len(outputs) if outputs else 0
        if avg <= 0:
            continue
        equal_count = sum(
            1 for v in outputs
            if abs(v - avg) / avg < 0.02
        )
        if equal_count >= len(outputs) * 0.6:
            coinjoin_txs.add(tx_hash)

    addr_coinjoin_count: dict[str, int] = defaultdict(int)
    addr_tx_hashes: dict[str, list[str]] = defaultdict(list)

    for tx in transactions:
        if tx.tx_hash in coinjoin_txs and tx.from_address:
            addr_coinjoin_count[tx.from_address] += 1
            addr_tx_hashes[tx.from_address].append(tx.tx_hash)

    alerts = []
    for addr, count in addr_coinjoin_count.items():
        if count < 1:
            continue
        confidence = min(1.0, 0.5 + count * 0.1)
        alerts.append({
            "entity_id": addr,
            "entity_type": "address",
            "detector_type": "coinjoin_mixing",
            "chain_name": chain_name,
            "confidence_score": round(confidence, 4),
            "summary": (
                f"Address participated in {count} suspected CoinJoin "
                f"transaction(s) on {chain_name}."
            ),
            "supporting_tx_hashes": list(set(addr_tx_hashes[addr]))[:20],
            "metrics": {
                "coinjoin_tx_count": count,
                "total_coinjoin_txs_detected": len(coinjoin_txs),
            },
            "score_components": {
                "participation_count": count,
                "base_score": 0.5,
                "per_tx_bonus": 0.1,
            },
            "first_observed_at": None,
            "last_observed_at": None,
            "evidence_ids": [],
        })

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Detector 6: Multi-Hop UTXO Obfuscation ────────────────────────────────────

def detect_multihop_obfuscation(
    transactions: list[TxRecord],
    chain_name: str = "bitcoin",
    min_hops: int = 4,
) -> list[dict[str, Any]]:
    """
    Detect addresses that route funds through many intermediate hops,
    retaining value at each step (classic layering via UTXO chain).
    """
    thresholds = get_utxo_thresholds(chain_name)
    eff_min_hops = max(min_hops, thresholds["peeling_min_hops"])
    value_retention = 0.80

    best_out: dict[str, tuple[str, float, str]] = {}
    addr_total_in: dict[str, float] = defaultdict(float)
    addr_out_degree: dict[str, int] = defaultdict(int)

    for tx in transactions:
        if not tx.from_address or not tx.to_address:
            continue
        val = float(tx.value_native or 0.0)
        if val <= 0:
            continue
        addr_total_in[tx.to_address] += val
        addr_out_degree[tx.from_address] += 1
        existing = best_out.get(tx.from_address)
        if existing is None or val > existing[1]:
            best_out[tx.from_address] = (tx.to_address, val, tx.tx_hash)

    high_degree = {
        addr for addr, deg in addr_out_degree.items()
        if deg >= 20
    }

    alerts = []
    visited: set[str] = set()

    for start_addr in list(best_out.keys()):
        if start_addr in visited or start_addr in high_degree:
            continue

        path_addrs = [start_addr]
        path_txs = []
        current = start_addr
        prev_val = addr_total_in.get(start_addr, 0.0)

        for _ in range(30):
            nxt = best_out.get(current)
            if not nxt:
                break
            to_addr, val, tx_hash = nxt
            if to_addr in path_addrs or to_addr in high_degree:
                break
            if prev_val > 0 and val / prev_val < value_retention:
                break
            path_addrs.append(to_addr)
            path_txs.append(tx_hash)
            current = to_addr
            prev_val = val

        if len(path_addrs) < eff_min_hops:
            continue

        for addr in path_addrs:
            visited.add(addr)

        confidence = min(1.0, 0.45 + len(path_addrs) * 0.06)
        alerts.append({
            "entity_id": start_addr,
            "entity_type": "address",
            "detector_type": "utxo_multihop_obfuscation",
            "chain_name": chain_name,
            "confidence_score": round(confidence, 4),
            "summary": (
                f"Multi-hop UTXO obfuscation: {len(path_addrs)}-hop chain "
                f"with >= {int(value_retention*100)}% value retention on {chain_name}."
            ),
            "supporting_tx_hashes": path_txs[:20],
            "metrics": {
                "hop_count": len(path_addrs),
                "path_addresses": path_addrs[:10],
                "value_retention_threshold": value_retention,
            },
            "score_components": {
                "depth": len(path_addrs),
                "base_score": 0.45,
                "per_hop_bonus": 0.06,
            },
            "evidence_ids": [],
            "first_observed_at": None,
            "last_observed_at": None,
        })

    return sorted(alerts, key=lambda a: a["confidence_score"], reverse=True)


# ── Unified UTXO AML runner ────────────────────────────────────────────────────

class UTXOAMLDetector:
    """
    Runs all UTXO-specific AML detectors on a set of TxRecords.

    Output format mirrors the EVM LayeringAnalysisEngine detector hits
    so they can be persisted to the same layering_detector_hits table.
    """

    def __init__(self, cfg: Optional[Config] = None, chain_name: str = "bitcoin"):
        self.cfg = cfg or load_config()
        self.chain_name = chain_name

    def run(self, transactions: list[TxRecord]) -> dict[str, Any]:
        """Run all UTXO layering and topology detectors."""
        chain_txs = [
            tx for tx in transactions
            if getattr(tx, "chain_name", "bitcoin") == self.chain_name
        ] or transactions

        logger.info(
            "UTXOAMLDetector[%s]: running on %d transactions",
            self.chain_name, len(chain_txs),
        )

        pass_through_hits = detect_pass_through(chain_txs, self.chain_name)
        fan_out_hits = detect_fan_out_dispersion(chain_txs, self.chain_name)
        fan_in_hits = detect_fan_in_aggregation(chain_txs, self.chain_name)
        peeling_hits = detect_change_peeling(chain_txs, self.chain_name)
        coinjoin_hits = detect_coinjoin_mixing(chain_txs, self.chain_name)
        multihop_hits = detect_multihop_obfuscation(chain_txs, self.chain_name)

        all_hits = (
            pass_through_hits
            + fan_out_hits
            + fan_in_hits
            + peeling_hits
            + coinjoin_hits
            + multihop_hits
        )

        logger.info(
            "UTXOAMLDetector[%s]: %d pass_through  %d fan_out  %d fan_in  %d peeling  %d coinjoin  %d multihop",
            self.chain_name,
            len(pass_through_hits),
            len(fan_out_hits),
            len(fan_in_hits),
            len(peeling_hits),
            len(coinjoin_hits),
            len(multihop_hits),
        )

        return {
            "chain_name": self.chain_name,
            "total_hits": len(all_hits),
            "pass_through": pass_through_hits,
            "fan_out": fan_out_hits,
            "fan_in": fan_in_hits,
            "change_peeling": peeling_hits,
            "coinjoin": coinjoin_hits,
            "multihop": multihop_hits,
            "all_hits": all_hits,
        }

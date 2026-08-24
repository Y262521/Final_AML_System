"""Pass-through (conduit / rapid forwarding) detector."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any

from ..types import (
    DetectorHit,
    DetectorOutput,
    EvidenceRecord,
    LayeringContext,
    clamp,
    iso_from_ts,
    stable_evidence_id,
)

# Limit DFS/BFS search depth to 3 or 4 hops max
MAX_HOPS = 3
MAX_NEIGHBORS_PER_NODE = 50

# Skip addresses with excessive degree (DEXes, CEX hot wallets, token contracts)
MAX_DEGREE_THRESHOLD = 500


class PassThroughDetector:
    detector_type = "pass_through"

    def detect(self, context: LayeringContext) -> DetectorOutput:
        output = DetectorOutput()
        max_hops = max(1, min(4, int(getattr(context.cfg, "layering_pass_through_max_hops", MAX_HOPS) or MAX_HOPS)))
        max_neighbors = max(1, int(getattr(context.cfg, "layering_pass_through_max_neighbors", MAX_NEIGHBORS_PER_NODE) or MAX_NEIGHBORS_PER_NODE))
        max_degree_threshold = max(10, int(getattr(context.cfg, "layering_pass_through_max_degree", MAX_DEGREE_THRESHOLD) or MAX_DEGREE_THRESHOLD))
        max_gap = max(60, int(getattr(context.cfg, "layering_pass_through_max_time_gap_seconds", 7200) or 7200))
        min_retention = max(0.10, float(getattr(context.cfg, "layering_pass_through_min_retention", 0.85) or 0.85))

        # Fast index acquisition: use pre-indexed artifacts if present, or index once in O(|T|)
        if context.artifacts and context.artifacts.incoming_edges and context.artifacts.outgoing_edges:
            incoming_index = context.artifacts.incoming_edges
            outgoing_index = context.artifacts.outgoing_edges
        else:
            incoming_index = defaultdict(list)
            outgoing_index = defaultdict(list)
            for tx in context.transactions:
                val = float(tx.value_eth or 0.0)
                if val <= 0:
                    continue
                frm = str(tx.from_address or "").lower().strip()
                to = str(tx.to_address or "").lower().strip()
                if not frm or not to:
                    continue
                edge = {
                    "tx_hash": tx.tx_hash,
                    "from_address": frm,
                    "to_address": to,
                    "value_eth": val,
                    "timestamp": float(tx.timestamp or 0.0),
                }
                incoming_index[to].append(edge)
                outgoing_index[frm].append(edge)

            for edges in incoming_index.values():
                edges.sort(key=lambda e: (float(e.get("timestamp") or 0.0), str(e.get("tx_hash") or "")))
            for edges in outgoing_index.values():
                edges.sort(key=lambda e: (float(e.get("timestamp") or 0.0), str(e.get("tx_hash") or "")))

        for seed in sorted(context.seeds.values(), key=lambda item: item.entity_id):
            seed_addresses = {addr.lower().strip() for addr in seed.addresses if addr}
            incoming_txs: list[dict[str, Any]] = []
            outgoing_txs: list[dict[str, Any]] = []

            for addr in seed_addresses:
                if not addr or context.is_service_address(addr):
                    continue

                in_degree, out_degree = self._get_node_degrees(context, addr, incoming_index, outgoing_index)
                if in_degree > max_degree_threshold or out_degree > max_degree_threshold:
                    continue  # Skip supernodes to avoid combinatorial explosion

                # Collect incoming transactions up to MAX_NEIGHBORS_PER_NODE
                in_edges = incoming_index.get(addr, [])
                for edge in in_edges[:max_neighbors]:
                    val = float(edge.get("value_eth") or 0.0)
                    if val <= 0:
                        continue
                    from_addr = str(edge.get("from_address") or "").lower().strip()
                    if from_addr in seed_addresses or context.is_service_address(from_addr):
                        continue
                    incoming_txs.append({
                        "tx_hash": str(edge.get("tx_hash") or ""),
                        "from_address": from_addr,
                        "to_address": addr,
                        "value": val,
                        "timestamp": float(edge.get("timestamp") or 0.0),
                    })

                # Collect outgoing transactions up to MAX_NEIGHBORS_PER_NODE
                out_edges = outgoing_index.get(addr, [])
                for edge in out_edges[:max_neighbors]:
                    val = float(edge.get("value_eth") or 0.0)
                    if val <= 0:
                        continue
                    to_addr = str(edge.get("to_address") or "").lower().strip()
                    if to_addr in seed_addresses:
                        continue
                    outgoing_txs.append({
                        "tx_hash": str(edge.get("tx_hash") or ""),
                        "from_address": addr,
                        "to_address": to_addr,
                        "value": val,
                        "timestamp": float(edge.get("timestamp") or 0.0),
                    })

            if not incoming_txs or not outgoing_txs:
                continue

            incoming_txs.sort(key=lambda item: (item["timestamp"], item["tx_hash"]))
            outgoing_txs.sort(key=lambda item: (item["timestamp"], item["tx_hash"]))

            matched_events: list[dict[str, Any]] = []
            used_outgoing: set[str] = set()

            for in_tx in incoming_txs:
                best_match = None
                best_score = -1.0

                for out_tx in outgoing_txs:
                    if out_tx["tx_hash"] in used_outgoing:
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

                    if retention < min_retention:
                        continue

                    latency_score = math.exp(-time_gap / max(max_gap, 1))
                    match_score = 0.6 * retention + 0.4 * latency_score

                    if match_score > best_score:
                        best_score = match_score
                        best_match = {
                            "in_tx": in_tx,
                            "out_tx": out_tx,
                            "time_gap": time_gap,
                            "retention": retention,
                            "latency_score": latency_score,
                            "match_score": match_score,
                        }

                if best_match is not None:
                    used_outgoing.add(best_match["out_tx"]["tx_hash"])

                    # DFS / BFS trace forward up to MAX_HOPS
                    visited_nodes = {
                        best_match["in_tx"]["from_address"],
                        best_match["in_tx"]["to_address"],
                        best_match["out_tx"]["to_address"],
                    }
                    extended_nodes, extended_txs = self._trace_forward_conduit(
                        context=context,
                        start_address=best_match["out_tx"]["to_address"],
                        current_value=best_match["out_tx"]["value"],
                        current_ts=best_match["out_tx"]["timestamp"],
                        max_hops=max_hops,
                        max_neighbors=max_neighbors,
                        max_degree_threshold=max_degree_threshold,
                        max_gap=max_gap,
                        min_retention=min_retention,
                        outgoing_index=outgoing_index,
                        incoming_index=incoming_index,
                        visited=visited_nodes,
                    )
                    best_match["extended_nodes"] = extended_nodes
                    best_match["extended_txs"] = extended_txs
                    best_match["path"] = [
                        best_match["in_tx"]["from_address"],
                        best_match["in_tx"]["to_address"],
                        best_match["out_tx"]["to_address"],
                    ] + extended_nodes
                    matched_events.append(best_match)

            if not matched_events:
                continue

            # Compute entity conduit purity (low total degree = dedicated pass-through)
            entity_degree = max((context.address_degree.get(addr, 0) for addr in seed.addresses), default=2)
            purity = 1.0 if entity_degree <= 4 else clamp(4.0 / max(entity_degree, 1))

            best_event = max(matched_events, key=lambda e: e["match_score"])
            avg_retention = sum(e["retention"] for e in matched_events) / len(matched_events)
            avg_gap = sum(e["time_gap"] for e in matched_events) / len(matched_events)
            confidence = clamp(
                0.40 * avg_retention
                + 0.35 * best_event["latency_score"]
                + 0.15 * purity
                + 0.10 * min(1.0, len(matched_events) * 0.5)
            )

            all_supporting_hashes: list[str] = []
            for e in matched_events:
                all_supporting_hashes.extend([e["in_tx"]["tx_hash"], e["out_tx"]["tx_hash"]])
                if e.get("extended_txs"):
                    all_supporting_hashes.extend(e["extended_txs"])
            all_supporting_hashes = sorted(set(all_supporting_hashes))

            first_seen_ts = min(e["in_tx"]["timestamp"] for e in matched_events)
            last_seen_ts = max(e["out_tx"]["timestamp"] for e in matched_events)

            sample_path = best_event.get("path", [
                best_event["in_tx"]["from_address"],
                best_event["in_tx"]["to_address"],
                best_event["out_tx"]["to_address"],
            ])
            hop_count = max(1, len(sample_path) - 2)

            evidence_id = stable_evidence_id(seed.entity_id, self.detector_type, 1)

            output.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    entity_id=seed.entity_id,
                    detector_type=self.detector_type,
                    evidence_type="path",
                    title="Rapid pass-through conduit",
                    summary=(
                        f"Entity forwarded incoming value with {avg_retention:.1%} retention "
                        f"within {avg_gap:.0f}s transit latency ({len(matched_events)} occurrence(s))."
                    ),
                    entity_ids=[seed.entity_id],
                    tx_hashes=all_supporting_hashes,
                    path=sample_path,
                    metrics={
                        "event_count": len(matched_events),
                        "average_retention": round(avg_retention, 4),
                        "average_time_gap_seconds": round(avg_gap, 2),
                        "conduit_purity": round(purity, 4),
                        "hop_count": hop_count,
                        "sample_inflow_tx": best_event["in_tx"]["tx_hash"],
                        "sample_outflow_tx": best_event["out_tx"]["tx_hash"],
                    },
                    first_seen_at=iso_from_ts(first_seen_ts),
                    last_seen_at=iso_from_ts(last_seen_ts),
                )
            )

            output.hits.append(
                DetectorHit(
                    entity_id=seed.entity_id,
                    entity_type=seed.entity_type,
                    detector_type=self.detector_type,
                    confidence_score=round(confidence, 4),
                    summary=(
                        f"Pass-through conduit behavior detected with {avg_retention:.1%} retention "
                        f"and {avg_gap:.0f}s transit time."
                    ),
                    score_components={
                        "retention_score": round(avg_retention, 4),
                        "latency_score": round(best_event["latency_score"], 4),
                        "purity_score": round(purity, 4),
                        "event_count": len(matched_events),
                        "hop_score": round(min(1.0, hop_count / float(max_hops)), 4),
                    },
                    metrics={
                        "events_detected": len(matched_events),
                        "average_retention": round(avg_retention, 4),
                        "average_time_gap_seconds": round(avg_gap, 2),
                        "hop_count": hop_count,
                        "sample_path": sample_path,
                    },
                    supporting_tx_hashes=all_supporting_hashes,
                    evidence_ids=[evidence_id],
                    first_observed_at=iso_from_ts(first_seen_ts),
                    last_observed_at=iso_from_ts(last_seen_ts),
                )
            )

        return output

    def _get_node_degrees(
        self,
        context: LayeringContext,
        address: str,
        incoming_index: dict[str, list[dict[str, Any]]],
        outgoing_index: dict[str, list[dict[str, Any]]],
    ) -> tuple[int, int]:
        """Return (in_degree, out_degree) for an address."""
        addr = address.lower().strip()
        if context.artifacts and context.artifacts.graph is not None and context.artifacts.graph.has_node(addr):
            return (
                int(context.artifacts.graph.in_degree(addr)),
                int(context.artifacts.graph.out_degree(addr)),
            )
        in_deg = len(incoming_index.get(addr, []))
        out_deg = len(outgoing_index.get(addr, []))
        return in_deg, out_deg

    def _trace_forward_conduit(
        self,
        context: LayeringContext,
        start_address: str,
        current_value: float,
        current_ts: float,
        max_hops: int,
        max_neighbors: int,
        max_degree_threshold: int,
        max_gap: int,
        min_retention: float,
        outgoing_index: dict[str, list[dict[str, Any]]],
        incoming_index: dict[str, list[dict[str, Any]]],
        visited: set[str],
    ) -> tuple[list[str], list[str]]:
        """DFS/BFS bounded forward search for subsequent pass-through hops up to max_hops."""
        current_node = start_address.lower().strip()
        extended_nodes: list[str] = []
        extended_txs: list[str] = []

        # The initial conduit is 1 hop (in -> seed -> out_tx.to). We allow up to max_hops total.
        remaining_hops = max_hops - 1

        while remaining_hops > 0:
            if not current_node or context.is_service_address(current_node):
                break

            in_degree, out_degree = self._get_node_degrees(context, current_node, incoming_index, outgoing_index)
            if in_degree > max_degree_threshold or out_degree > max_degree_threshold:
                break  # Skip supernodes to avoid combinatorial explosion

            candidate_edges = outgoing_index.get(current_node, [])[:max_neighbors]
            best_hop = None
            best_hop_score = -1.0

            for edge in candidate_edges:
                next_to = str(edge.get("to_address") or "").lower().strip()
                if not next_to or next_to in visited:
                    continue
                next_ts = float(edge.get("timestamp") or 0.0)
                time_gap = next_ts - current_ts
                if time_gap < 0:
                    continue
                if time_gap > max_gap:
                    break

                next_val = float(edge.get("value_eth") or 0.0)
                if next_val <= 0:
                    continue

                retention = min(current_value, next_val) / max(current_value, next_val, 1e-9)
                if retention < min_retention:
                    continue

                latency_score = math.exp(-time_gap / max(max_gap, 1))
                score = 0.6 * retention + 0.4 * latency_score

                if score > best_hop_score:
                    best_hop_score = score
                    best_hop = (next_to, str(edge.get("tx_hash") or ""), next_val, next_ts)

            if best_hop is not None:
                next_to, next_tx, next_val, next_ts = best_hop
                visited.add(next_to)
                extended_nodes.append(next_to)
                if next_tx:
                    extended_txs.append(next_tx)
                current_node = next_to
                current_value = next_val
                current_ts = next_ts
                remaining_hops -= 1
            else:
                break

        return extended_nodes, extended_txs

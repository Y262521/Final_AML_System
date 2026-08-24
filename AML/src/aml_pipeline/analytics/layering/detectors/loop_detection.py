"""Circular Routing & Wash Loop detector."""

from __future__ import annotations

import math
from typing import Any

import networkx as nx

from ..types import DetectorHit, DetectorOutput, EvidenceRecord, LayeringContext, clamp, iso_from_ts, stable_evidence_id


class LoopDetectionDetector:
    detector_type = "loop_detection"

    def detect(self, context: LayeringContext) -> DetectorOutput:
        output = DetectorOutput()
        min_hops = 3
        max_hops = 6
        min_score = 0.55

        # Build directed graph from context transactions
        G = nx.DiGraph()
        tx_lookup = {}
        for edge in context.entity_edges.values():
            G.add_edge(edge.source_entity_id, edge.target_entity_id, weight=edge.total_value_eth, tx_count=edge.tx_count)
            tx_lookup[(edge.source_entity_id, edge.target_entity_id)] = edge.tx_hashes

        if G.number_of_edges() == 0:
            return output

        # Find simple cycles
        try:
            cycles = list(nx.simple_cycles(G))
        except Exception:
            cycles = []

        for seed in sorted(context.seeds.values(), key=lambda item: item.entity_id):
            seed_entity = seed.entity_id
            qualifying_cycles = []

            for cycle in cycles:
                if seed_entity in cycle and min_hops <= len(cycle) <= max_hops:
                    cycle_edges = [(cycle[i], cycle[(i+1)%len(cycle)]) for i in range(len(cycle))]
                    edge_values = [G[u][v].get("weight", 0.0) for u, v in cycle_edges if G.has_edge(u, v)]
                    if edge_values:
                        min_val = min(edge_values)
                        max_val = max(edge_values)
                        retention = min_val / max_val if max_val > 0 else 0.8
                    else:
                        retention = 0.8

                    hop_factor = min(1.0, len(cycle) / 4.0)
                    score = clamp(0.50 + 0.30 * retention + 0.20 * hop_factor)
                    if score >= min_score:
                        qualifying_cycles.append({
                            "cycle": cycle,
                            "hops": len(cycle),
                            "score": score,
                            "retention": round(retention, 4),
                        })

            if not qualifying_cycles:
                continue

            qualifying_cycles.sort(key=lambda item: (item["score"], item["hops"]), reverse=True)
            top_cycle = qualifying_cycles[0]
            cycle_nodes = top_cycle["cycle"]
            
            cycle_txs = []
            for i in range(len(cycle_nodes)):
                u = cycle_nodes[i]
                v = cycle_nodes[(i+1) % len(cycle_nodes)]
                cycle_txs.extend(tx_lookup.get((u, v), []))

            evidence_id = stable_evidence_id(seed.entity_id, self.detector_type, 1)
            metrics = {
                "hops": top_cycle["hops"],
                "cycle_path": cycle_nodes,
                "value_retention_ratio": top_cycle["retention"],
                "cycle_count": len(qualifying_cycles),
            }

            output.hits.append(
                DetectorHit(
                    seed_entity_id=seed.entity_id,
                    detector_type=self.detector_type,
                    score=round(top_cycle["score"], 4),
                    evidence_ids=[evidence_id],
                )
            )

            output.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    seed_entity_id=seed.entity_id,
                    detector_type=self.detector_type,
                    confidence=round(top_cycle["score"], 4),
                    supporting_tx_hashes=cycle_txs[:25],
                    metrics=metrics,
                    summary=f"Closed circular routing cycle of {top_cycle['hops']} hops with {round(top_cycle['retention']*100, 1)}% retention.",
                    first_observed_at=iso_from_ts(seed.first_seen_at),
                    last_observed_at=iso_from_ts(seed.last_seen_at),
                )
            )

        return output

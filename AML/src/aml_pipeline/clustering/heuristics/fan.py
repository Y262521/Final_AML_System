"""
Fan-In / Fan-Out Heuristic
============================
Fan-out: one address distributes funds to many addresses.
Fan-in:  many addresses consolidate funds into one.

Addresses on the "many" side of a fan are linked together because they
often share a common controller, campaign, or operational purpose.
"""

from __future__ import annotations

from typing import List

import networkx as nx

from ...config import Config
from .base_heuristic import BaseHeuristic, ClusterEdge


class FanPatternHeuristic(BaseHeuristic):
    name = "fan_pattern"
    description = (
        "Addresses on the receiving end of a fan-out (or sending end of a "
        "fan-in) are grouped as likely related."
    )

    def __init__(self, cfg: Config):
        super().__init__(cfg)
        self.threshold = cfg.clustering_fan_threshold
        self.max_pattern_size = getattr(cfg, "clustering_max_fan_pattern_size", 6)
        self.window = getattr(cfg, "clustering_pass_through_window_seconds", 7200)

    def find_links(self, G: nx.MultiDiGraph) -> List[ClusterEdge]:
        links: List[ClusterEdge] = []
        seen: set = set()
        
        # Track edge metadata for temporal/value correlation
        out_edges_by_node: dict[str, list[tuple[str, float, float]]] = {}
        in_edges_by_node: dict[str, list[tuple[str, float, float]]] = {}

        for u, v, data in G.edges(data=True):
            if not self.is_meaningful_edge(data):
                continue
            ts = float(data.get("timestamp", 0.0) or 0.0)
            val = float(data.get("value_eth", 0.0) or 0.0)
            out_edges_by_node.setdefault(u, []).append((v, ts, val))
            in_edges_by_node.setdefault(v, []).append((u, ts, val))

        # Fan-out: node distributing funds to tightly-coordinated burner nodes
        for node, targets in out_edges_by_node.items():
            unique_targets = list({t[0] for t in targets})
            # Over-clustering guard: If out-degree exceeds pattern size, it is a CEX/service hub
            if len(unique_targets) < self.threshold or len(unique_targets) > self.max_pattern_size:
                continue

            # Verify temporal coordination: burst within the time window
            timestamps = [t[1] for t in targets if t[1] > 0]
            if timestamps and (max(timestamps) - min(timestamps) > self.window):
                continue

            unique_targets.sort()
            for i in range(len(unique_targets)):
                for j in range(i + 1, len(unique_targets)):
                    pair = (unique_targets[i], unique_targets[j])
                    if pair not in seen:
                        links.append(pair)
                        seen.add(pair)

        # Fan-in: tightly-coordinated burner nodes consolidating into single collector
        for node, senders in in_edges_by_node.items():
            unique_senders = list({s[0] for s in senders})
            # Over-clustering guard: If in-degree exceeds pattern size, it is a CEX deposit hub/pool
            if len(unique_senders) < self.threshold or len(unique_senders) > self.max_pattern_size:
                continue

            timestamps = [s[1] for s in senders if s[1] > 0]
            if timestamps and (max(timestamps) - min(timestamps) > self.window):
                continue

            unique_senders.sort()
            for i in range(len(unique_senders)):
                for j in range(i + 1, len(unique_senders)):
                    pair = (unique_senders[i], unique_senders[j])
                    if pair not in seen:
                        links.append(pair)
                        seen.add(pair)

        return links


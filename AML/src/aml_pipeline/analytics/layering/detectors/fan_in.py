"""Fan-in (aggregation / fund consolidation) detector."""

from __future__ import annotations

import math
from collections import defaultdict
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


class FanInAggregationDetector:
    detector_type = "fan_in_aggregation"

    def detect(self, context: LayeringContext) -> DetectorOutput:
        output = DetectorOutput()
        min_sources = max(2, int(getattr(context.cfg, "layering_fan_in_min_sources", 3) or 3))
        window_seconds = max(300, int(getattr(context.cfg, "layering_fan_in_window_seconds", 86400) or 86400))

        for seed in sorted(context.seeds.values(), key=lambda item: item.entity_id):
            seed_addresses = set(seed.addresses)

            # Exclude known services (exchanges, protocols)
            if any(context.is_service_address(addr) for addr in seed_addresses):
                continue

            incoming_txs = []
            outgoing_txs = []

            for tx in context.transactions:
                from_addr = str(tx.from_address or "").lower().strip()
                to_addr = str(tx.to_address or "").lower().strip()
                val = float(tx.value_eth or 0.0)
                ts = float(tx.timestamp or 0.0)

                if to_addr in seed_addresses and from_addr not in seed_addresses and val > 0:
                    if not context.is_service_address(from_addr):
                        incoming_txs.append({
                            "tx_hash": tx.tx_hash,
                            "from_address": from_addr,
                            "to_address": to_addr,
                            "value": val,
                            "timestamp": ts,
                        })
                elif from_addr in seed_addresses and to_addr not in seed_addresses and val > 0:
                    outgoing_txs.append({
                        "tx_hash": tx.tx_hash,
                        "from_address": from_addr,
                        "to_address": to_addr,
                        "value": val,
                        "timestamp": ts,
                    })

            if len(incoming_txs) < min_sources:
                continue

            incoming_txs.sort(key=lambda item: item["timestamp"])

            # Find aggregation clusters within sliding temporal window
            aggregation_candidates: list[dict[str, Any]] = []

            for i in range(len(incoming_txs)):
                start_tx = incoming_txs[i]
                window_txs = [
                    tx for tx in incoming_txs[i:]
                    if 0 <= tx["timestamp"] - start_tx["timestamp"] <= window_seconds
                ]
                distinct_sources = {tx["from_address"] for tx in window_txs}

                if len(distinct_sources) < min_sources:
                    continue

                total_aggregated = sum(tx["value"] for tx in window_txs)
                num_sources = len(distinct_sources)
                duration = max(1.0, window_txs[-1]["timestamp"] - window_txs[0]["timestamp"])
                last_inflow_ts = window_txs[-1]["timestamp"]

                # Check if there is subsequent consolidation sweep / outflow after inflows
                subsequent_outflows = [
                    tx for tx in outgoing_txs
                    if 0 <= tx["timestamp"] - last_inflow_ts <= window_seconds
                ]
                total_forwarded = sum(tx["value"] for tx in subsequent_outflows)
                forward_ratio = min(1.0, total_forwarded / max(total_aggregated, 1e-9))
                has_sweep = forward_ratio >= 0.50

                temporal_score = math.exp(-duration / window_seconds)
                source_score = clamp(min(1.0, 0.5 + (num_sources - min_sources) * 0.1))
                volume_score = 1.0 if total_aggregated >= 0.1 else clamp(total_aggregated / 0.1)
                sweep_score = 1.0 if has_sweep else 0.20

                confidence = clamp(
                    0.35 * source_score
                    + 0.25 * temporal_score
                    + 0.25 * sweep_score
                    + 0.15 * volume_score
                )

                aggregation_candidates.append({
                    "in_txs": window_txs,
                    "out_txs": subsequent_outflows,
                    "sources": sorted(distinct_sources),
                    "total_value": total_aggregated,
                    "num_sources": num_sources,
                    "duration_seconds": duration,
                    "has_sweep": has_sweep,
                    "forward_ratio": forward_ratio,
                    "temporal_score": temporal_score,
                    "source_score": source_score,
                    "confidence": confidence,
                    "first_seen_ts": window_txs[0]["timestamp"],
                    "last_seen_ts": subsequent_outflows[-1]["timestamp"] if subsequent_outflows else window_txs[-1]["timestamp"],
                })

            if not aggregation_candidates:
                continue

            best = max(
                aggregation_candidates,
                key=lambda c: (c["confidence"], c["num_sources"], -c["duration_seconds"]),
            )

            supporting_hashes = sorted(
                set(tx["tx_hash"] for tx in best["in_txs"])
                | set(tx["tx_hash"] for tx in best["out_txs"])
            )
            evidence_id = stable_evidence_id(seed.entity_id, self.detector_type, 1)

            output.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    entity_id=seed.entity_id,
                    detector_type=self.detector_type,
                    evidence_type="subgraph",
                    title="N-to-1 fund aggregation (fan-in)",
                    summary=(
                        f"Entity consolidated {best['total_value']:.4f} ETH from "
                        f"{best['num_sources']} distinct source addresses "
                        f"within {best['duration_seconds']:.0f}s"
                        + (f" with subsequent sweep ({best['forward_ratio']:.1%} forwarded)." if best['has_sweep'] else ".")
                    ),
                    entity_ids=[seed.entity_id],
                    tx_hashes=supporting_hashes,
                    path=best["sources"][:8] + [seed.addresses[0]],
                    metrics={
                        "source_count": best["num_sources"],
                        "total_aggregated_eth": round(best["total_value"], 6),
                        "duration_seconds": round(best["duration_seconds"], 2),
                        "has_sweep": best["has_sweep"],
                        "forward_ratio": round(best["forward_ratio"], 4),
                        "sample_sources": best["sources"][:10],
                    },
                    first_seen_at=iso_from_ts(best["first_seen_ts"]),
                    last_seen_at=iso_from_ts(best["last_seen_ts"]),
                )
            )

            output.hits.append(
                DetectorHit(
                    entity_id=seed.entity_id,
                    entity_type=seed.entity_type,
                    detector_type=self.detector_type,
                    confidence_score=round(best["confidence"], 4),
                    summary=(
                        f"Fan-in aggregation detected: {best['num_sources']} sources, "
                        f"{best['total_value']:.4f} ETH consolidated in {best['duration_seconds']:.0f}s."
                    ),
                    score_components={
                        "source_score": round(best["source_score"], 4),
                        "temporal_score": round(best["temporal_score"], 4),
                        "sweep_bonus": 0.20 if best["has_sweep"] else 0.05,
                        "source_count": best["num_sources"],
                    },
                    metrics={
                        "source_count": best["num_sources"],
                        "total_aggregated_eth": round(best["total_value"], 6),
                        "duration_seconds": round(best["duration_seconds"], 2),
                        "has_sweep": best["has_sweep"],
                        "forward_ratio": round(best["forward_ratio"], 4),
                        "sources": best["sources"][:10],
                    },
                    supporting_tx_hashes=supporting_hashes,
                    evidence_ids=[evidence_id],
                    first_observed_at=iso_from_ts(best["first_seen_ts"]),
                    last_observed_at=iso_from_ts(best["last_seen_ts"]),
                )
            )

        return output

"""Fan-out (dispersion / fund splitting) detector."""

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


class FanOutDispersionDetector:
    detector_type = "fan_out_dispersion"

    def detect(self, context: LayeringContext) -> DetectorOutput:
        output = DetectorOutput()
        min_recipients = max(2, int(getattr(context.cfg, "layering_fan_out_min_recipients", 3) or 3))
        window_seconds = max(300, int(getattr(context.cfg, "layering_fan_out_window_seconds", 86400) or 86400))

        for seed in sorted(context.seeds.values(), key=lambda item: item.entity_id):
            seed_addresses = set(seed.addresses)

            # Exclude known service addresses / high-traffic entities
            if any(context.is_service_address(addr) for addr in seed_addresses):
                continue

            outgoing_txs = []
            for tx in context.transactions:
                from_addr = str(tx.from_address or "").lower().strip()
                to_addr = str(tx.to_address or "").lower().strip()
                val = float(tx.value_eth or 0.0)

                if from_addr in seed_addresses and to_addr not in seed_addresses and val > 0:
                    if not context.is_service_address(to_addr):
                        outgoing_txs.append({
                            "tx_hash": tx.tx_hash,
                            "from_address": from_addr,
                            "to_address": to_addr,
                            "value": val,
                            "timestamp": float(tx.timestamp or 0.0),
                        })

            if len(outgoing_txs) < min_recipients:
                continue

            outgoing_txs.sort(key=lambda item: item["timestamp"])

            # Find dispersion bursts within sliding temporal window
            dispersion_candidates: list[dict[str, Any]] = []

            for i in range(len(outgoing_txs)):
                start_tx = outgoing_txs[i]
                window_txs = [
                    tx for tx in outgoing_txs[i:]
                    if 0 <= tx["timestamp"] - start_tx["timestamp"] <= window_seconds
                ]
                distinct_recipients = {tx["to_address"] for tx in window_txs}

                if len(distinct_recipients) < min_recipients:
                    continue

                total_dispersed = sum(tx["value"] for tx in window_txs)
                recipient_values: dict[str, float] = defaultdict(float)
                for tx in window_txs:
                    recipient_values[tx["to_address"]] += tx["value"]

                num_recipients = len(recipient_values)
                duration = max(1.0, window_txs[-1]["timestamp"] - window_txs[0]["timestamp"])

                # Normalized Shannon entropy to measure distribution uniformity
                entropy = 0.0
                if total_dispersed > 0 and num_recipients > 1:
                    for val in recipient_values.values():
                        p = val / total_dispersed
                        if p > 0:
                            entropy -= p * math.log(p)
                    normalized_entropy = clamp(entropy / math.log(num_recipients))
                else:
                    normalized_entropy = 0.5

                temporal_score = math.exp(-duration / window_seconds)
                recipient_score = clamp(min_recipients / max(num_recipients, 1) if num_recipients < min_recipients else min(1.0, 0.5 + (num_recipients - min_recipients) * 0.1))
                volume_score = 1.0 if total_dispersed >= 0.1 else clamp(total_dispersed / 0.1)

                confidence = clamp(
                    0.35 * recipient_score
                    + 0.30 * temporal_score
                    + 0.20 * normalized_entropy
                    + 0.15 * volume_score
                )

                dispersion_candidates.append({
                    "txs": window_txs,
                    "recipients": sorted(distinct_recipients),
                    "total_value": total_dispersed,
                    "num_recipients": num_recipients,
                    "duration_seconds": duration,
                    "normalized_entropy": normalized_entropy,
                    "temporal_score": temporal_score,
                    "recipient_score": recipient_score,
                    "confidence": confidence,
                    "first_seen_ts": window_txs[0]["timestamp"],
                    "last_seen_ts": window_txs[-1]["timestamp"],
                })

            if not dispersion_candidates:
                continue

            best = max(
                dispersion_candidates,
                key=lambda c: (c["confidence"], c["num_recipients"], -c["duration_seconds"]),
            )

            supporting_hashes = sorted(set(tx["tx_hash"] for tx in best["txs"]))
            evidence_id = stable_evidence_id(seed.entity_id, self.detector_type, 1)

            output.evidence.append(
                EvidenceRecord(
                    evidence_id=evidence_id,
                    entity_id=seed.entity_id,
                    detector_type=self.detector_type,
                    evidence_type="subgraph",
                    title="1-to-N fund dispersion (fan-out)",
                    summary=(
                        f"Entity dispersed {best['total_value']:.4f} ETH across "
                        f"{best['num_recipients']} distinct recipient addresses "
                        f"within {best['duration_seconds']:.0f}s."
                    ),
                    entity_ids=[seed.entity_id],
                    tx_hashes=supporting_hashes,
                    path=[seed.addresses[0]] + best["recipients"][:8],
                    metrics={
                        "recipient_count": best["num_recipients"],
                        "total_dispersed_eth": round(best["total_value"], 6),
                        "duration_seconds": round(best["duration_seconds"], 2),
                        "dispersion_entropy": round(best["normalized_entropy"], 4),
                        "sample_recipients": best["recipients"][:10],
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
                        f"Fan-out dispersion detected: {best['num_recipients']} recipients, "
                        f"{best['total_value']:.4f} ETH dispersed in {best['duration_seconds']:.0f}s."
                    ),
                    score_components={
                        "recipient_score": round(best["recipient_score"], 4),
                        "temporal_score": round(best["temporal_score"], 4),
                        "uniformity_score": round(best["normalized_entropy"], 4),
                        "recipient_count": best["num_recipients"],
                    },
                    metrics={
                        "recipient_count": best["num_recipients"],
                        "total_dispersed_eth": round(best["total_value"], 6),
                        "duration_seconds": round(best["duration_seconds"], 2),
                        "recipients": best["recipients"][:10],
                    },
                    supporting_tx_hashes=supporting_hashes,
                    evidence_ids=[evidence_id],
                    first_observed_at=iso_from_ts(best["first_seen_ts"]),
                    last_observed_at=iso_from_ts(best["last_seen_ts"]),
                )
            )

        return output

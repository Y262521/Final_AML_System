"""
Run one full extraction pass across every chain in your ledger, choosing
exactly ONE data source per chain -- so no chain is ever fetched twice in
the same run and there's nothing to de-duplicate afterward.

Place this in AML/scripts/run_all_chains_etl.py.

Routing logic (see build_chain_source_map()):
    1. If the chain is already covered by your existing default pipeline
       (source="alchemy" -> EVM / UTXO / ACCOUNT extractors), keep using
       that -- it's already live in production for that chain.
    2. Otherwise, fill the gap with the first of [sqd, aws_s3, bigquery]
       that supports the chain, in that priority order:
         - sqd:      broadest coverage (200+ networks), free, closest to
                     real-time of the three new sources
         - aws_s3:   free, but batch/date-partitioned (not block-numbered)
         - bigquery: broadest SQL coverage but bills your GCP project, so
                     it's the last resort

The map is built dynamically from each extractor module's own supported-
chain list, so if you extend any of the 4 sources later, this script picks
it up automatically -- you don't need to edit a hardcoded table here.

Usage:
    # default ledger chains, using each chain's routed source
    python scripts/run_all_chains_etl.py \\
        --from-block 19000000 --to-block 19000100 --date 2026-08-09

    # just a subset
    python scripts/run_all_chains_etl.py --chains ethereum,bitcoin,tron \\
        --from-block 19000000 --to-block 19000100 --date 2026-08-09
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aml_pipeline.config import load_config
from aml_pipeline.etl.extract.factories import get_extractor
from aml_pipeline.chains.registry import (
    EVM_CHAIN_NAMES,
    UTXO_CHAIN_NAMES,
    ACCOUNT_CHAIN_NAMES,
)
from aml_pipeline.etl.extract.sqd import _DEFAULT_NETWORKS as SQD_CHAINS
from aml_pipeline.etl.extract.aws_s3 import _CHAIN_PATHS as AWS_S3_CHAINS
from aml_pipeline.etl.extract.bigquery import _DATASETS as BIGQUERY_CHAINS

ALCHEMY_CHAINS = set(EVM_CHAIN_NAMES) | set(UTXO_CHAIN_NAMES) | set(ACCOUNT_CHAIN_NAMES)

# Priority order: prefer whatever's already live (alchemy), then fill gaps.
SOURCE_PRIORITY = ["alchemy", "sqd", "aws_s3", "bigquery"]

SOURCE_CHAIN_SETS = {
    "alchemy": ALCHEMY_CHAINS,
    "sqd": set(SQD_CHAINS),
    "aws_s3": set(AWS_S3_CHAINS),
    "bigquery": set(BIGQUERY_CHAINS),
}

# Your current ledger chains (from the ETH/SOL/BASE/POL/BNB/BCH/LTC/DOGE/
# BTC/TRON/ARB chips) -- edit if the set changes.
DEFAULT_LEDGER_CHAINS = [
    "ethereum", "solana", "base", "polygon", "bnb",
    "bitcoin_cash", "litecoin", "dogecoin", "bitcoin", "tron", "arbitrum",
]


def build_chain_source_map(chains: list[str]) -> dict[str, str]:
    """Pick exactly one source per chain, in SOURCE_PRIORITY order.

    Guarantees no chain appears twice in the plan -> no cross-source
    duplication is possible for this run.
    """
    mapping: dict[str, str] = {}
    unsupported = []
    for chain in chains:
        for source in SOURCE_PRIORITY:
            if chain in SOURCE_CHAIN_SETS[source]:
                mapping[chain] = source
                break
        else:
            unsupported.append(chain)
    if unsupported:
        print(f"WARNING: no source covers these chains, skipping: {unsupported}")
    return mapping


def run_chain(chain: str, source: str, cfg, args: argparse.Namespace) -> int:
    extractor = get_extractor(chain, cfg=cfg, source=source)

    if source == "alchemy":
        stored, _ = extractor.fetch_and_store_raw(batch=args.batch)
        return stored

    if source == "sqd":
        if args.from_block is None or args.to_block is None:
            print("  skipped: --from-block/--to-block required for sqd-routed chains")
            return 0
        return extractor.fetch_and_store_range(args.from_block, args.to_block)

    if source == "aws_s3":
        day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        return extractor.fetch_and_store_range(day, day)

    if source == "bigquery":
        if args.from_block is None or args.to_block is None:
            print("  skipped: --from-block/--to-block required for bigquery-routed chains")
            return 0
        return extractor.fetch_and_store_range(args.from_block, args.to_block)

    raise ValueError(f"Unhandled source: {source}")


from concurrent.futures import ThreadPoolExecutor, as_completed


def main():
    parser = argparse.ArgumentParser(
        description="Run all chains in one pass, one source per chain (no duplication)"
    )
    parser.add_argument("--chains", help="Comma-separated chain list (default: ledger chains)")
    parser.add_argument("--from-block", type=int, help="For chains routed to sqd/bigquery")
    parser.add_argument("--to-block", type=int, help="For chains routed to sqd/bigquery")
    parser.add_argument("--date", help="YYYY-MM-DD, for chains routed to aws_s3 (default: today)")
    parser.add_argument("--batch", type=int, default=5, help="For chains routed to alchemy")
    parser.add_argument("--workers", type=int, default=6, help="Max parallel workers for multi-chain extraction (default: 6)")
    args = parser.parse_args()

    chains = args.chains.split(",") if args.chains else DEFAULT_LEDGER_CHAINS
    cfg = load_config()

    chain_source_map = build_chain_source_map(chains)
    print("Routing plan (one source per chain):", flush=True)
    for chain, source in chain_source_map.items():
        print(f"  {chain:15s} -> {source}", flush=True)
    print(flush=True)

    results: dict[str, object] = {}

    if args.workers > 1 and len(chain_source_map) > 1:
        max_w = min(args.workers, len(chain_source_map))
        print(f"[PARALLEL EXTRACTION ({max_w} WORKERS)]", flush=True)
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_chain = {
                executor.submit(run_chain, ch, src, cfg, args): (ch, src)
                for ch, src in chain_source_map.items()
            }
            for fut in as_completed(future_to_chain):
                chain, source = future_to_chain[fut]
                try:
                    stored = fut.result()
                    results[chain] = stored
                    print(f"  [+] {chain:15s} ({source}): stored {stored} blocks", flush=True)
                except Exception as exc:
                    results[chain] = f"ERROR: {exc}"
                    print(f"  [!] {chain:15s} ({source}): ERROR: {exc}", flush=True)
    else:
        for chain, source in chain_source_map.items():
            print(f"[{chain}] extracting via {source} ...", flush=True)
            try:
                stored = run_chain(chain, source, cfg, args)
                results[chain] = stored
                print(f"  stored {stored} blocks\n", flush=True)
            except Exception as exc:  # keep going -- one bad chain shouldn't kill the run
                results[chain] = f"ERROR: {exc}"
                print(f"  ERROR: {exc}\n", flush=True)

    print("=" * 50, flush=True)
    print("Summary:", flush=True)
    for chain, result in results.items():
        print(f"  {chain:15s} {result}", flush=True)

    print("\nNext: run transform + load + analytics as usual:", flush=True)
    print("  python -m aml_pipeline.pipelines.run_etl", flush=True)
    print("  python scripts/run_analytics_only.py", flush=True)


if __name__ == "__main__":
    main()

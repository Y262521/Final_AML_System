"""
Run the ETL against any of the 4 sources: alchemy, sqd, aws_s3, bigquery.

Place this in AML/scripts/ alongside run_analytics_only.py.

Examples:
    # Widest chain coverage, fastest to test with (public endpoint, no signup):
    python scripts/run_multi_source_etl.py --source sqd --chain ethereum --from-block 19000000 --to-block 19000050

    # AWS Open Data (no credentials needed, date-based):
    python scripts/run_multi_source_etl.py --source aws_s3 --chain bitcoin --date 2026-07-01

    # BigQuery (requires GOOGLE_APPLICATION_CREDENTIALS + BIGQUERY_PROJECT):
    python scripts/run_multi_source_etl.py --source bigquery --chain ethereum --from-block 19000000 --to-block 19000050

    # Unchanged default (Alchemy RPC), same as before:
    python scripts/run_multi_source_etl.py --source alchemy --chain ethereum --batch 5
"""
import argparse
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aml_pipeline.config import load_config
from aml_pipeline.etl.extract.factories import get_extractor


def main():
    parser = argparse.ArgumentParser(description="Multi-source blockchain ETL")
    parser.add_argument("--source", choices=["alchemy", "sqd", "aws_s3", "bigquery"], default="alchemy")
    parser.add_argument("--chain", default="ethereum")
    parser.add_argument("--from-block", type=int)
    parser.add_argument("--to-block", type=int)
    parser.add_argument("--date", help="YYYY-MM-DD, for --source aws_s3")
    parser.add_argument("--batch", type=int, default=5, help="For --source alchemy only")
    args = parser.parse_args()

    cfg = load_config()
    extractor = get_extractor(args.chain, cfg=cfg, source=args.source)

    if args.source == "alchemy":
        stored, block_count = extractor.fetch_and_store_raw(batch=args.batch)
        print(f"Alchemy: stored {stored} blocks starting review, {block_count} total processed")

    elif args.source == "sqd":
        if args.from_block is None or args.to_block is None:
            parser.error("--from-block and --to-block are required for --source sqd")
        stored = extractor.fetch_and_store_range(args.from_block, args.to_block)
        print(f"SQD: stored {stored} blocks")

    elif args.source == "aws_s3":
        day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
        stored = extractor.fetch_and_store_range(day, day)
        print(f"AWS S3: stored {stored} blocks for {day}")

    elif args.source == "bigquery":
        if args.from_block is None or args.to_block is None:
            parser.error("--from-block and --to-block are required for --source bigquery")
        stored = extractor.fetch_and_store_range(args.from_block, args.to_block)
        print(f"BigQuery: stored {stored} blocks")

    print("\nNext: run the transform + load + analytics stages as usual:")
    print("  python -m aml_pipeline.pipelines.run_etl   # transform + load only, reads what's now in Mongo")
    print("  python scripts/run_analytics_only.py")


if __name__ == "__main__":
    main()

"""
AWS Public Blockchain Data extractor (S3, Parquet, no-sign-request).

Source: https://registry.opendata.aws/aws-public-blockchain/
Bucket layout (public, unsigned, region us-east-2):
    s3://aws-public-blockchain/v1.0/btc/blocks/date=YYYY-MM-DD/*.parquet
    s3://aws-public-blockchain/v1.0/btc/transactions/date=YYYY-MM-DD/*.parquet
    s3://aws-public-blockchain/v1.0/eth/blocks/date=YYYY-MM-DD/*.parquet
    s3://aws-public-blockchain/v1.0/eth/transactions/date=YYYY-MM-DD/*.parquet
    (SonarX-maintained chains — arbitrum, base, aptos, xrp, provenance —
     live under v1.1/sonarx/<chain>/ with the same blocks/transactions layout)

This dataset is batch/date-partitioned, not per-block-RPC, so unlike the
Alchemy extractor this class resolves "which date holds this block number"
first, then filters the day's Parquet files down to that block. It is best
used for backfilling a date range rather than one block at a time — use
`fetch_date_range()` for real workloads, `fetch_block()` exists only to
satisfy the common BaseExtractor interface used by the rest of the pipeline.

No AWS credentials are required (public dataset, --no-sign-request).

Env vars (all optional, sensible defaults shown):
    AWS_PUBLIC_BLOCKCHAIN_BUCKET = aws-public-blockchain
    AWS_PUBLIC_BLOCKCHAIN_REGION = us-east-2
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

import pandas as pd

from .base import BaseExtractor
from .connections import get_flat_transaction_collection, get_raw_collection
from .utils import build_flat_transaction_documents, to_jsonable

logger = logging.getLogger(__name__)

_CHAIN_PATHS = {
    "bitcoin": "v1.0/btc",
    "ethereum": "v1.0/eth",
    "arbitrum": "v1.1/sonarx/arbitrum",
    "base": "v1.1/sonarx/base",
}


class AWSPublicBlockchainExtractor(BaseExtractor):
    """Reads Bitcoin/Ethereum (and SonarX EVM chains) from the AWS Open Data S3 bucket."""

    def __init__(self, cfg=None, chain: str = "ethereum"):
        super().__init__(cfg)
        self.chain = chain.lower().strip()
        if self.chain not in _CHAIN_PATHS:
            raise ValueError(
                f"AWS Public Blockchain source does not support chain={chain!r}. "
                f"Supported: {sorted(_CHAIN_PATHS)}"
            )
        self.bucket = os.getenv("AWS_PUBLIC_BLOCKCHAIN_BUCKET", "aws-public-blockchain")
        self.region = os.getenv("AWS_PUBLIC_BLOCKCHAIN_REGION", "us-east-2")
        self.prefix = _CHAIN_PATHS[self.chain]

        try:
            import boto3
            from botocore import UNSIGNED
            from botocore.config import Config as BotoConfig
        except ImportError as err:
            raise ImportError(
                "boto3 is required for AWSPublicBlockchainExtractor. "
                "Install it with: pip install boto3 pyarrow"
            ) from err

        self.s3 = boto3.client(
            "s3", region_name=self.region, config=BotoConfig(signature_version=UNSIGNED)
        )
        self.raw_collection = get_raw_collection(self.cfg)
        self.transaction_collection = get_flat_transaction_collection(self.cfg)

    # ------------------------------------------------------------------ #
    # Discovery helpers
    # ------------------------------------------------------------------ #
    def _dataset_uri(self, table: str, day: date) -> str:
        return f"s3://{self.bucket}/{self.prefix}/{table}/date={day.isoformat()}/"

    def _read_day(self, table: str, day: date) -> pd.DataFrame:
        """Read one day's partition of a table (blocks or transactions) as a DataFrame."""
        uri = self._dataset_uri(table, day)
        try:
            import pyarrow.dataset as ds
            dataset = ds.dataset(
                uri, format="parquet", filesystem=_anon_s3fs(self.region)
            )
        except ImportError as err:
            raise ImportError("pyarrow and s3fs are required for reading AWS Open Data. Install with: pip install pyarrow s3fs") from err
        except FileNotFoundError:
            logger.warning("No AWS Public Blockchain data for %s on %s", table, day)
            return pd.DataFrame()
        return dataset.to_table().to_pandas()

    def get_latest_block(self) -> int:
        """Return the highest block number found in yesterday's/today's partitions."""
        for day in (date.today(), date.today() - timedelta(days=1)):
            df = self._read_day("blocks", day)
            if not df.empty:
                col = "number" if "number" in df.columns else "block_number"
                return int(df[col].max())
        raise RuntimeError("Could not resolve latest block from AWS Public Blockchain data")

    # ------------------------------------------------------------------ #
    # Per-block interface (kept for BaseExtractor compatibility)
    # ------------------------------------------------------------------ #
    def fetch_block(self, block_number: int) -> dict:
        """Resolve which day holds this block, then pull just that block's rows.

        Inefficient for scattered single blocks (scans a day's partition each
        call) — for real backfills use fetch_date_range() instead.
        """
        for days_back in range(0, 14):
            day = date.today() - timedelta(days=days_back)
            blocks_df = self._read_day("blocks", day)
            if blocks_df.empty:
                continue
            col = "number" if "number" in blocks_df.columns else "block_number"
            match = blocks_df[blocks_df[col] == block_number]
            if not match.empty:
                tx_df = self._read_day("transactions", day)
                return self._to_raw_document(block_number, match.iloc[0], tx_df, day)
        raise ValueError(f"Block {block_number} not found in the last 14 days of partitions")

    def fetch_date_range(self, start: date, end: date) -> Iterable[dict]:
        """Preferred entry point: yields one raw document per block for each day in range."""
        day = start
        while day <= end:
            blocks_df = self._read_day("blocks", day)
            if blocks_df.empty:
                day += timedelta(days=1)
                continue
            tx_df = self._read_day("transactions", day)
            col = "number" if "number" in blocks_df.columns else "block_number"
            for _, block_row in blocks_df.iterrows():
                yield self._to_raw_document(int(block_row[col]), block_row, tx_df, day)
            day += timedelta(days=1)

    def _to_raw_document(self, block_number: int, block_row, tx_df: pd.DataFrame, day: date) -> dict:
        num_col = "number" if "number" in tx_df.columns else "block_number"
        block_txs = tx_df[tx_df[num_col] == block_number] if not tx_df.empty else tx_df
        transactions = block_txs.to_dict(orient="records") if not block_txs.empty else []

        return to_jsonable({
            "block_number": block_number,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "network": f"{self.chain}-aws-public-blockchain",
            "chain_name": self.chain,
            "source": "aws_s3",
            "transaction_count": len(transactions),
            "receipt_count": 0,
            "log_count": 0,
            "block": {**block_row.to_dict(), "transactions": transactions},
            "transactions": transactions,
            "receipts": [],
            "logs": [],
        })

    def save_to_db(self, data: dict) -> int:
        block_number = data.get("block_number")
        if block_number is None:
            raise ValueError("Raw block data is missing block_number")
        self.raw_collection.replace_one(
            {"block_number": block_number, "chain_name": self.chain}, data, upsert=True
        )

        flat_documents = build_flat_transaction_documents(data, data.get("network", self.chain))
        if flat_documents:
            from pymongo import ReplaceOne
            ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in flat_documents]
            self.transaction_collection.bulk_write(ops, ordered=False)
        return len(flat_documents)

    def fetch_and_store_range(self, start: date, end: date) -> int:
        """Convenience: pull a date range and persist every block found."""
        stored = 0
        for raw_doc in self.fetch_date_range(start, end):
            self.save_to_db(raw_doc)
            stored += 1
        logger.info("AWS S3 (%s): stored %s blocks for %s -> %s", self.chain, stored, start, end)
        return stored


def _anon_s3fs(region: str):
    import s3fs
    return s3fs.S3FileSystem(anon=True, config_kwargs={"region_name": region})

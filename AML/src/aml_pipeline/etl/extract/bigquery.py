"""
Google BigQuery public blockchain dataset extractor.

Source datasets (public, queried against your own billing project):
    bigquery-public-data.crypto_ethereum.{blocks,transactions}
    bigquery-public-data.crypto_bitcoin.{blocks,transactions}
    bigquery-public-data.crypto_litecoin.{blocks,transactions}
    bigquery-public-data.crypto_dogecoin.{blocks,transactions}

BigQuery itself is not free — the datasets are public, but every query
runs against (and is billed to) a GCP project of your own. Use block-range
filters and LIMIT to keep query cost down; a query without a WHERE clause
on these tables can scan hundreds of GB.

Env vars:
    GOOGLE_APPLICATION_CREDENTIALS = path to a service-account JSON key
    BIGQUERY_PROJECT               = your GCP project ID (billing project)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Iterator

from .base import BaseExtractor
from .connections import get_flat_transaction_collection, get_raw_collection
from .utils import build_flat_transaction_documents, to_jsonable

logger = logging.getLogger(__name__)

_DATASETS = {
    "ethereum": "bigquery-public-data.crypto_ethereum",
    "bitcoin": "bigquery-public-data.crypto_bitcoin",
    "litecoin": "bigquery-public-data.crypto_litecoin",
    "dogecoin": "bigquery-public-data.crypto_dogecoin",
}


class BigQueryExtractor(BaseExtractor):
    """Reads chain history from Google's public BigQuery blockchain datasets."""

    def __init__(self, cfg=None, chain: str = "ethereum"):
        super().__init__(cfg)
        self.chain = chain.lower().strip()
        if self.chain not in _DATASETS:
            raise ValueError(
                f"BigQuery source does not support chain={chain!r}. Supported: {sorted(_DATASETS)}"
            )
        self.dataset = _DATASETS[self.chain]
        project = os.getenv("BIGQUERY_PROJECT")
        if not project:
            raise RuntimeError(
                "BIGQUERY_PROJECT env var is required (your GCP billing project). "
                "GOOGLE_APPLICATION_CREDENTIALS must also point to a service-account key."
            )
        try:
            from google.cloud import bigquery
        except ImportError as err:
            raise ImportError(
                "google-cloud-bigquery is required for BigQueryExtractor. "
                "Install it with: pip install google-cloud-bigquery"
            ) from err
        self.client = bigquery.Client(project=project)

        self.raw_collection = get_raw_collection(self.cfg)
        self.transaction_collection = get_flat_transaction_collection(self.cfg)

    # ------------------------------------------------------------------ #
    def get_latest_block(self) -> int:
        query = f"SELECT MAX(number) AS max_block FROM `{self.dataset}.blocks`"
        row = next(iter(self.client.query(query).result()))
        return int(row["max_block"])

    def fetch_block(self, block_number: int) -> dict:
        for raw_doc in self.fetch_block_range(block_number, block_number):
            return raw_doc
        raise ValueError(f"BigQuery returned no data for block {block_number} on {self.chain}")

    def fetch_block_range(self, start_block: int, end_block: int) -> Iterator[dict]:
        """Preferred entry point — issues exactly 2 billed queries for the whole range."""
        blocks_query = f"""
            SELECT number, `hash`, timestamp, parent_hash, miner, difficulty,
                   gas_limit, gas_used, transaction_count
            FROM `{self.dataset}.blocks`
            WHERE number BETWEEN @start_block AND @end_block
            ORDER BY number
        """
        tx_query = f"""
            SELECT `hash`, nonce, block_number, from_address, to_address,
                   value, gas, gas_price, input, receipt_status
            FROM `{self.dataset}.transactions`
            WHERE block_number BETWEEN @start_block AND @end_block
        """
        job_config = bigquery.QueryJobConfig(query_parameters=[
            bigquery.ScalarQueryParameter("start_block", "INT64", start_block),
            bigquery.ScalarQueryParameter("end_block", "INT64", end_block),
        ])

        blocks = {row["number"]: dict(row) for row in self.client.query(blocks_query, job_config=job_config).result()}
        transactions_by_block: dict[int, list[dict]] = {}
        for row in self.client.query(tx_query, job_config=job_config).result():
            transactions_by_block.setdefault(row["block_number"], []).append(dict(row))

        for block_number, block_row in blocks.items():
            txs = transactions_by_block.get(block_number, [])
            yield self._to_raw_document(block_number, block_row, txs)

    def _to_raw_document(self, block_number: int, block_row: dict, transactions: list[dict]) -> dict:
        return to_jsonable({
            "block_number": block_number,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "network": f"{self.chain}-bigquery",
            "chain_name": self.chain,
            "source": "bigquery",
            "transaction_count": len(transactions),
            "receipt_count": 0,
            "log_count": 0,
            "block": {**block_row, "transactions": transactions},
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

    def fetch_and_store_range(self, start_block: int, end_block: int) -> int:
        stored = 0
        for raw_doc in self.fetch_block_range(start_block, end_block):
            self.save_to_db(raw_doc)
            stored += 1
        logger.info("BigQuery (%s): stored %s blocks [%s -> %s]", self.chain, stored, start_block, end_block)
        return stored

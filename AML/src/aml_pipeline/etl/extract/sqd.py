"""
SQD (Subsquid) Portal extractor.

Source: https://docs.sqd.ai/ (Portal streaming HTTP API)
Public portal endpoint (free for development, no API key required):
    https://portal.sqd.dev/datasets/<network>/stream

Request shape (confirmed against subsquid/sqd-portal):
    POST /datasets/<network>/stream
    {
        "type": "evm",
        "fromBlock": 19000000,
        "toBlock": 19000100,
        "includeAllBlocks": true,
        "fields": {
            "block": {"number": true, "timestamp": true, "hash": true},
            "transaction": {
                "hash": true, "from": true, "to": true, "value": true,
                "gas": true, "gasPrice": true, "status": true, "input": true
            }
        }
    }
Response is newline-delimited JSON (NDJSON): one JSON object per block,
each containing a "transactions" array. This makes SQD chain-agnostic —
the same request shape works across the 200+ networks SQD indexes
(Ethereum, BNB, Polygon, Arbitrum, Base, Solana, Tron, Bitcoin, etc.),
so it's the best of these three sources for maximizing chain coverage.

Env vars:
    SQD_PORTAL_URL   = https://portal.sqd.dev   (or your self-hosted portal)
    SQD_NETWORK_MAP  = optional override, see _DEFAULT_NETWORKS below
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Iterator, Optional

import requests

from .base import BaseExtractor
from .connections import get_flat_transaction_collection, get_raw_collection
from .utils import build_flat_transaction_documents, to_jsonable

logger = logging.getLogger(__name__)

# SQD "dataset" (network) slugs — see https://docs.sqd.ai for the full list.
_DEFAULT_NETWORKS = {
    "ethereum": "ethereum-mainnet",
    "bnb": "binance-mainnet",
    "polygon": "polygon-mainnet",
    "arbitrum": "arbitrum-one",
    "base": "base-mainnet",
    "bitcoin": "bitcoin-mainnet",
    "solana": "solana-mainnet",
    "tron": "tron-mainnet",
}

_DEFAULT_FIELDS = {
    "block": {"number": True, "timestamp": True, "hash": True},
    "transaction": {
        "hash": True, "from": True, "to": True, "value": True,
        "gas": True, "gasPrice": True, "gasUsed": True,
        "status": True, "input": True, "nonce": True,
    },
}


class SQDExtractor(BaseExtractor):
    """Chain-agnostic extractor backed by the SQD (Subsquid) Portal streaming API."""

    def __init__(self, cfg=None, chain: str = "ethereum"):
        super().__init__(cfg)
        self.chain = chain.lower().strip()
        self.network = _DEFAULT_NETWORKS.get(self.chain, self.chain)
        self.portal_url = os.getenv("SQD_PORTAL_URL", "https://portal.sqd.dev").rstrip("/")
        self.stream_url = f"{self.portal_url}/datasets/{self.network}/stream"
        self.session = requests.Session()

        self.raw_collection = get_raw_collection(self.cfg)
        self.transaction_collection = get_flat_transaction_collection(self.cfg)

    # ------------------------------------------------------------------ #
    def get_latest_block(self) -> int:
        """SQD portals typically lag chain head by minutes-to-hours; ask its /head endpoint."""
        resp = self.session.get(f"{self.portal_url}/datasets/{self.network}/head", timeout=15)
        resp.raise_for_status()
        return int(resp.json()["number"])

    def _stream(self, from_block: int, to_block: int) -> Iterator[dict]:
        body = {
            "type": "evm",
            "fromBlock": from_block,
            "toBlock": to_block,
            "includeAllBlocks": True,
            "fields": _DEFAULT_FIELDS,
        }
        with self.session.post(self.stream_url, json=body, stream=True, timeout=120) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                yield json.loads(line)

    def fetch_block(self, block_number: int) -> dict:
        """Fetch a single block via a 1-block stream request."""
        for block in self._stream(block_number, block_number):
            return self._to_raw_document(block)
        raise ValueError(f"SQD portal returned no data for block {block_number} on {self.network}")

    def fetch_block_range(self, from_block: int, to_block: int) -> Iterator[dict]:
        """Preferred entry point — SQD is built for efficient batch streaming, not 1-at-a-time calls."""
        for block in self._stream(from_block, to_block):
            yield self._to_raw_document(block)

    def _to_raw_document(self, block: dict) -> dict:
        block_number = block.get("header", block).get("number", block.get("number"))
        header = block.get("header", block)
        transactions = block.get("transactions", [])

        return to_jsonable({
            "block_number": block_number,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "network": self.network,
            "chain_name": self.chain,
            "source": "sqd",
            "transaction_count": len(transactions),
            "receipt_count": 0,
            "log_count": len(block.get("logs", [])),
            "block": {**header, "transactions": transactions},
            "transactions": transactions,
            "receipts": [],
            "logs": block.get("logs", []),
        })

    def save_to_db(self, data: dict) -> int:
        block_number = data.get("block_number")
        if block_number is None:
            raise ValueError("Raw block data is missing block_number")
        self.raw_collection.replace_one(
            {"block_number": block_number, "chain_name": self.chain}, data, upsert=True
        )

        flat_documents = build_flat_transaction_documents(data, self.network)
        if flat_documents:
            from pymongo import ReplaceOne
            ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in flat_documents]
            self.transaction_collection.bulk_write(ops, ordered=False)
        return len(flat_documents)

    def fetch_and_store_range(self, from_block: int, to_block: int) -> int:
        stored = 0
        for raw_doc in self.fetch_block_range(from_block, to_block):
            self.save_to_db(raw_doc)
            stored += 1
        logger.info("SQD (%s): stored %s blocks [%s -> %s]", self.network, stored, from_block, to_block)
        return stored

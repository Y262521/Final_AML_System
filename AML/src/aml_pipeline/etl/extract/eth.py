"""Ethereum raw block extractor implementation."""

import logging
import time
from datetime import datetime, timezone
from typing import Optional, Tuple

from pymongo import ReplaceOne

from .base import BaseExtractor
from .connections import (
    get_flat_transaction_collection,
    get_raw_collection,
    get_web3,
    prepare_extraction_collections,
)
from .utils import build_flat_transaction_documents, rpc_call_with_retry, to_jsonable

from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

_MAX_FETCH_BLOCKS_PER_RUN = 5


class EthereumExtractor(BaseExtractor):
    """Ethereum-specific extractor that pulls blocks, txs, receipts, and logs."""

    def __init__(self, cfg=None):
        """Initialize Web3 and Mongo connections."""
        super().__init__(cfg)
        self.w3 = get_web3(self.cfg)
        self._rpc_url = getattr(self.cfg, "eth_rpc_url", "")
        self.session = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=3)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.raw_collection = get_raw_collection(self.cfg)
        self.transaction_collection = get_flat_transaction_collection(self.cfg)
        self.collection = self.raw_collection
        prep_summary = prepare_extraction_collections(self.cfg)
        if prep_summary["duplicate_docs_deleted"] > 0:
            logger.warning(
                "Deleted %s duplicate raw block documents before extraction",
                prep_summary["duplicate_docs_deleted"],
            )

    def get_latest_block(self) -> int:
        """Return the latest Ethereum block number from the RPC."""
        return self.w3.eth.block_number

    def get_latest_saved_block(self) -> Optional[int]:
        """Return the latest Ethereum block number already saved to MongoDB."""
        latest = self.raw_collection.find_one(
            {
                "$or": [
                    {"chain_name": "ethereum"},
                    {"chain_name": {"$exists": False}},   # legacy docs without chain_name
                    {"network": "ethereum-mainnet"},
                ]
            },
            sort=[("block_number", -1)],
        )
        if not latest:
            return None
        return int(latest.get("block_number"))

    def _save_flat_transaction_documents(self, block_number: int, flat_documents: list[dict]) -> int:
        """Upsert flattened transaction documents for a single block."""
        tx_hashes = [document["_id"] for document in flat_documents]
        delete_query = {"block.number": block_number}
        if tx_hashes:
            delete_query["_id"] = {"$nin": tx_hashes}
        self.transaction_collection.delete_many(delete_query)

        if flat_documents:
            operations = [
                ReplaceOne({"_id": document["_id"]}, document, upsert=True)
                for document in flat_documents
            ]
            self.transaction_collection.bulk_write(operations, ordered=False)

        return len(flat_documents)

    def fetch_block(self, block_number: int) -> dict:
        """Fetch a full block, receipts, and logs as a raw document using concurrent receipt resolution."""
        block = rpc_call_with_retry(lambda: self.w3.eth.get_block(block_number, full_transactions=True))

        tx_list = block.get("transactions", []) or []
        receipts = []
        logs = []

        # Try fast batch receipt fetch if using Alchemy endpoint (1 single HTTP call for entire block)
        if self._rpc_url and "alchemy.com" in self._rpc_url:
            try:
                hex_b = hex(block_number)
                payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "alchemy_getTransactionReceipts",
                    "params": [{"blockNumber": hex_b}],
                }
                resp = self.session.post(self._rpc_url, json=payload, timeout=30)
                if resp.status_code == 200:
                    res_json = resp.json()
                    alchemy_receipts = res_json.get("result", {}).get("receipts")
                    if alchemy_receipts and isinstance(alchemy_receipts, list):
                        receipts = alchemy_receipts
                        for r in alchemy_receipts:
                            logs.extend(r.get("logs", []))
            except Exception as exc:
                logger.debug("[ethereum] alchemy_getTransactionReceipts fallback note: %s", exc)

        if tx_list and not receipts:
            def _fetch_single_receipt(tx):
                tx_hash = tx.get("hash")
                if not tx_hash:
                    return None
                try:
                    return rpc_call_with_retry(lambda: self.w3.eth.get_transaction_receipt(tx_hash))
                except Exception as exc:
                    logger.warning("[ethereum] Failed to get receipt for %s: %s", tx_hash, exc)
                    return None

            max_workers = min(10, max(2, len(tx_list)))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                receipt_results = list(executor.map(_fetch_single_receipt, tx_list))

            for r in receipt_results:
                if r:
                    receipts.append(r)
                    logs.extend(r.get("logs", []))

        raw_document = {
            "block_number": block_number,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "network": self.cfg.eth_network,
            "transaction_count": len(tx_list),
            "receipt_count": len(receipts),
            "log_count": len(logs),
            "block": block,
            "transactions": tx_list,
            "receipts": receipts,
            "logs": logs,
        }

        return to_jsonable(raw_document)

    def save_to_db(self, data: dict) -> int:
        """Upsert the raw block and its flattened transactions into MongoDB."""
        block_number = data.get("block_number")
        if block_number is None:
            raise ValueError("Raw block data is missing block_number")
        self.raw_collection.replace_one({"block_number": block_number}, data, upsert=True)

        flat_documents = build_flat_transaction_documents(data, self.cfg.eth_network)
        return self._save_flat_transaction_documents(block_number, flat_documents)

    def fetch_and_store_raw(
        self,
        start_block: Optional[int] = None,
        batch: Optional[int] = None,
    ) -> Tuple[int, int]:
        """Fetch a batch of blocks and store them in MongoDB + local backup."""
        latest_saved = self.get_latest_saved_block()
        if start_block is None:
            start_block = (latest_saved + 1) if latest_saved is not None else self.cfg.eth_start_block

        batch_size = batch or self.cfg.eth_batch_size
        if batch_size > _MAX_FETCH_BLOCKS_PER_RUN:
            logger.warning(
                "Batch size capped at %s blocks per run (requested %s)",
                _MAX_FETCH_BLOCKS_PER_RUN,
                batch_size,
            )
            batch_size = _MAX_FETCH_BLOCKS_PER_RUN

        latest_available = self.get_latest_block()
        if start_block > latest_available:
            logger.info(
                "No new blocks available to fetch (start_block=%s, latest=%s)",
                start_block,
                latest_available,
            )
            return start_block, latest_available

        from_block = start_block
        to_block = min(from_block + batch_size - 1, latest_available)

        logger.info("Fetching blocks %s -> %s", from_block, to_block)

        total_transactions = 0
        blocks_to_fetch = list(range(from_block, to_block + 1))
        fetched_docs = []

        if len(blocks_to_fetch) > 1:
            with ThreadPoolExecutor(max_workers=min(batch_size, 5)) as block_exec:
                future_to_b = {
                    block_exec.submit(self.fetch_block, b): b
                    for b in blocks_to_fetch
                }
                for fut in as_completed(future_to_b):
                    b_num = future_to_b[fut]
                    try:
                        raw_data = fut.result()
                        fetched_docs.append((b_num, raw_data))
                    except Exception as exc:
                        logger.error("[ethereum] Block %d fetch failed: %s", b_num, exc)
            fetched_docs.sort(key=lambda x: x[0])
        else:
            raw_data = self.fetch_block(from_block)
            fetched_docs.append((from_block, raw_data))

        for block_number, raw_data in fetched_docs:
            # Save backup before Mongo insert to avoid _id serialization issues.
            self.save_to_local_backup(raw_data, block_number)
            flattened_count = self.save_to_db(raw_data)
            total_transactions += flattened_count
            logger.info(
                "Saved block %s with %s txs to raw_blocks and %s flattened tx docs",
                block_number,
                len(raw_data.get("transactions", [])),
                flattened_count,
            )

        fetched_blocks = len(fetched_docs)
        message = f"Saved blocks {from_block} -> {to_block} ({fetched_blocks} blocks)"
        print(message)
        logger.info(message)
        logger.info("Saved %s flattened transaction documents", total_transactions)

        return from_block, to_block


def test_connection(cfg=None) -> None:
    """Quick health check for Web3 + Mongo connections."""
    extractor = EthereumExtractor(cfg)
    _ = extractor.get_latest_block()
    _ = extractor.collection
    logger.info("Web3 and MongoDB connections look healthy")


def backfill_flat_transactions_from_raw_blocks(
    cfg=None,
    start_block: Optional[int] = None,
    end_block: Optional[int] = None,
) -> dict:
    """Populate the flattened raw transaction collection from existing raw block docs."""
    extractor = EthereumExtractor(cfg)
    query = {}
    if start_block is not None and end_block is not None:
        query["block_number"] = {"$gte": start_block, "$lte": end_block}

    summary = {"blocks_processed": 0, "transactions_written": 0}
    cursor = extractor.raw_collection.find(query).sort("block_number", 1)
    for raw_block in cursor:
        block_number = raw_block.get("block_number")
        if block_number is None:
            continue
        flat_documents = build_flat_transaction_documents(raw_block, extractor.cfg.eth_network)
        summary["transactions_written"] += extractor._save_flat_transaction_documents(
            block_number,
            flat_documents,
        )
        summary["blocks_processed"] += 1

    logger.info(
        "Backfilled %s flattened transactions from %s raw blocks",
        summary["transactions_written"],
        summary["blocks_processed"],
    )
    return summary

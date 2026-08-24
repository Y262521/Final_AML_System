"""
Factory helpers to resolve the correct chain extractor.

EVM chains (ethereum, bnb, polygon, arbitrum, base):
    → EVMExtractor (generic, configurable)

UTXO chains (bitcoin, litecoin, dogecoin, bitcoin_cash):
    → UTXOExtractor (Phase 3)

Account-based chains (solana):
    → SolanaExtractor (Phase 4)

Data sources (source= param, default "alchemy" preserves original behavior):
    alchemy   → RPC-based extractors above (EVMExtractor / UTXOExtractor / SolanaExtractor)
    sqd       → SQDExtractor (Subsquid Portal — 200+ networks, no API key)
    aws_s3    → AWSPublicBlockchainExtractor (AWS Open Data, no credentials)
    bigquery  → BigQueryExtractor (Google BigQuery public datasets, needs GCP project)
"""

from __future__ import annotations

from typing import Optional

from ...chains.registry import (
    EVM_CHAIN_NAMES,
    UTXO_CHAIN_NAMES,
    ACCOUNT_CHAIN_NAMES,
    get_chain,
)
from ...config import Config
from .base import BaseExtractor

SUPPORTED_SOURCES = {"alchemy", "aws_s3", "sqd", "bigquery"}


def get_extractor(chain: str, cfg: Optional[Config] = None, source: str = "alchemy") -> BaseExtractor:
    """
    Return a chain-specific extractor instance by chain name and data source.

    source="alchemy" (default): unchanged original behavior — RPC-based
    extractors below.
        Supported EVM chains (all use EVMExtractor):
            ethereum, bnb, polygon, arbitrum, base
        UTXO chains (Phase 3):
            bitcoin, litecoin, dogecoin, bitcoin_cash
        Account-based (Phase 4):
            solana

    source="sqd": SQDExtractor — widest chain coverage (200+ networks),
        no API key required.

    source="aws_s3": AWSPublicBlockchainExtractor — bitcoin, ethereum,
        arbitrum, base; no credentials required (public dataset).

    source="bigquery": BigQueryExtractor — ethereum, bitcoin, litecoin,
        dogecoin; requires BIGQUERY_PROJECT + GOOGLE_APPLICATION_CREDENTIALS.

    Raises ValueError for unknown chains or unknown sources.
    """
    source = source.lower().strip()
    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"Unknown source: {source!r}. Supported: {sorted(SUPPORTED_SOURCES)}")

    chain = chain.lower().strip()

    _alias_map = {
        "eth":     "ethereum",
        "bsc":     "bnb",
        "binance": "bnb",
        "matic":   "polygon",
        "pol":     "polygon",
        "btc":     "bitcoin",
        "ltc":     "litecoin",
        "doge":    "dogecoin",
        "bch":     "bitcoin_cash",
        "sol":     "solana",
    }
    canonical = _alias_map.get(chain, chain)

    # ── Non-Alchemy sources ──────────────────────────────────────────────────
    if source == "sqd":
        from .sqd import SQDExtractor
        return SQDExtractor(cfg=cfg, chain=canonical)

    if source == "aws_s3":
        from .aws_s3 import AWSPublicBlockchainExtractor
        return AWSPublicBlockchainExtractor(cfg=cfg, chain=canonical)

    if source == "bigquery":
        from .bigquery import BigQueryExtractor
        return BigQueryExtractor(cfg=cfg, chain=canonical)

    # ── source == "alchemy" -> original RPC-based routing, unchanged ────────

    # ── EVM chains ────────────────────────────────────────────────────────────
    if chain in EVM_CHAIN_NAMES or chain in {"eth", "binance", "bsc", "matic", "pol"}:
        from .evm import EVMExtractor
        return EVMExtractor(cfg=cfg, chain=canonical)

    # ── UTXO chains ───────────────────────────────────────────────────────────
    if chain in UTXO_CHAIN_NAMES or chain in {"btc", "ltc", "doge", "bch"}:
        try:
            from .utxo import UTXOExtractor
            return UTXOExtractor(cfg=cfg, chain=canonical)
        except ImportError:
            raise NotImplementedError(
                f"UTXO extractor for {canonical!r} will be available in Phase 3. "
                "Install Phase 3 first."
            )

    # ── Account-based non-EVM ─────────────────────────────────────────────────
    if chain in ACCOUNT_CHAIN_NAMES or chain == "sol":
        try:
            from .solana import SolanaExtractor
            return SolanaExtractor(cfg=cfg)
        except ImportError:
            raise NotImplementedError(
                f"Solana extractor requires Phase 4."
            )

    # ── Unknown ───────────────────────────────────────────────────────────────
    supported = sorted(
        list(EVM_CHAIN_NAMES) + list(UTXO_CHAIN_NAMES) + list(ACCOUNT_CHAIN_NAMES)
    )
    raise ValueError(
        f"Unsupported chain: {chain!r}. Supported: {supported}"
    )


def get_adapter(chain: str, cfg: Optional[Config] = None):
    """
    Return a clustering adapter for any supported chain.

    Used by the ClusteringEngine and AML analytics engines to read
    normalized TxRecord objects regardless of chain type.
    """
    chain = chain.lower().strip()

    _alias_map = {
        "eth":     "ethereum",
        "bsc":     "bnb",
        "binance": "bnb",
        "matic":   "polygon",
        "pol":     "polygon",
        "btc":     "bitcoin",
        "ltc":     "litecoin",
        "doge":    "dogecoin",
        "bch":     "bitcoin_cash",
        "sol":     "solana",
    }
    canonical = _alias_map.get(chain, chain)

    if canonical in EVM_CHAIN_NAMES:
        from ...clustering.evm_adapter import EVMAdapter
        return EVMAdapter(cfg=cfg, chain_name=canonical)

    if canonical in UTXO_CHAIN_NAMES:
        try:
            from ...clustering.utxo_adapter import UTXOAdapter
            return UTXOAdapter(cfg=cfg, chain_name=canonical)
        except ImportError:
            raise NotImplementedError(
                f"UTXO adapter for {canonical!r} requires Phase 3."
            )

    if canonical in ACCOUNT_CHAIN_NAMES:
        from ...clustering.solana_adapter import SolanaAdapter
        return SolanaAdapter(cfg=cfg)

    supported = sorted(
        list(EVM_CHAIN_NAMES) + list(UTXO_CHAIN_NAMES) + list(ACCOUNT_CHAIN_NAMES)
    )
    raise ValueError(f"Unsupported chain: {canonical!r}. Supported: {supported}")

"""
fetch_wallet_history_free.py
=============================

Extract a SINGLE WALLET's historical transactions from:

    --source aws_s3
        AWS Public Blockchain Data
        Date-partitioned Parquet
        No AWS credentials required.

    --source sqd
        Subsquid / SQD Portal
        Block-range based
        Public access.

The extracted rows can be written directly to MariaDB.

IMPORTANT:
    Start with --dry-run.

For SQD debugging use:

    python scripts/fetch_wallet_history_free.py ^
        --source sqd ^
        --address 0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045 ^
        --start-date 2026-01-01 ^
        --end-date 2026-01-02 ^
        --chain ethereum ^
        --limit 10 ^
        --dry-run ^
        --debug

"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)

WEI_PER_ETH = Decimal("1000000000000000000")


# ======================================================================
# ARGUMENTS
# ======================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch historical wallet transactions from AWS S3 or SQD.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--source",
        choices=["aws_s3", "sqd"],
        default="aws_s3",
        help="Data source.",
    )

    parser.add_argument(
        "--address",
        required=True,
        help="Wallet address to fetch.",
    )

    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date, e.g. 2026-01-01.",
    )

    parser.add_argument(
        "--end-date",
        default=None,
        help="End date, e.g. 2026-01-02.",
    )

    parser.add_argument(
        "--chain",
        default="ethereum",
        help="Chain name.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum matching transactions.",
    )

    parser.add_argument(
        "--max-scan-blocks",
        type=int,
        default=2_000_000,
        help="Maximum SQD blocks allowed to scan.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and print results but do not write to MariaDB.",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print detailed SQD response/debug information.",
    )

    parser.add_argument(
        "--debug-blocks",
        type=int,
        default=3,
        help="Number of SQD blocks for which detailed debug information is printed.",
    )

    return parser.parse_args()


# ======================================================================
# GENERAL HELPERS
# ======================================================================

def _col(df, *candidates):
    """
    Return the first column from candidates that exists.
    """
    for name in candidates:
        if name in df.columns:
            return name

    raise KeyError(
        f"None of {candidates} found in columns: {list(df.columns)}"
    )


def _normalize_address(value) -> str:
    """
    Normalize an Ethereum address for comparison.
    """
    if value is None:
        return ""

    return str(value).strip().lower()


def _safe_decimal_wei_to_eth(value) -> Decimal:
    """
    Convert Wei to ETH safely.

    Handles:
        integer
        decimal string
        hex string
        None
    """
    if value is None:
        return Decimal("0")

    try:
        if isinstance(value, str):
            value = value.strip()

            if value.startswith(("0x", "0X")):
                value = int(value, 16)

        return Decimal(str(value)) / WEI_PER_ETH

    except (ValueError, InvalidOperation, TypeError):
        return Decimal("0")


def _safe_int(value, default=None):
    """
    Safely convert a value to int.
    """
    if value is None:
        return default

    try:
        if isinstance(value, str):
            value = value.strip()

            if value.startswith(("0x", "0X")):
                return int(value, 16)

        return int(value)

    except (ValueError, TypeError):
        return default


# ======================================================================
# AWS S3
# ======================================================================

_AWS_CHAIN_PATHS = {
    "bitcoin": "v1.0/btc",
    "ethereum": "v1.0/eth",
    "arbitrum": "v1.1/sonarx/arbitrum",
    "base": "v1.1/sonarx/base",
}


def fetch_wallet_transactions_aws_s3(
    address: str,
    start_date: str,
    end_date: str,
    chain: str,
    limit: int,
    debug: bool = False,
) -> list[dict]:

    import os

    import pandas as pd
    import pyarrow.dataset as ds
    import s3fs

    if chain not in _AWS_CHAIN_PATHS:
        raise ValueError(
            f"aws_s3 does not support chain={chain!r}. "
            f"Supported: {sorted(_AWS_CHAIN_PATHS)}"
        )

    bucket = os.getenv(
        "AWS_PUBLIC_BLOCKCHAIN_BUCKET",
        "aws-public-blockchain",
    )

    region = os.getenv(
        "AWS_PUBLIC_BLOCKCHAIN_REGION",
        "us-east-2",
    )

    prefix = _AWS_CHAIN_PATHS[chain]

    fs = s3fs.S3FileSystem(
        anon=True,
        config_kwargs={"region_name": region},
    )

    address = _normalize_address(address)

    start = datetime.strptime(
        start_date,
        "%Y-%m-%d",
    ).date()

    end = (
        datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).date()
        if end_date
        else date.today()
    )

    results: list[dict] = []

    day = start

    while day <= end and len(results) < limit:

        uri = (
            f"{bucket}/{prefix}/transactions/"
            f"date={day.isoformat()}/"
        )

        if debug:
            print()
            print("=" * 70)
            print("AWS S3 DEBUG")
            print("=" * 70)
            print("Dataset:", uri)

        try:
            dataset = ds.dataset(
                uri,
                format="parquet",
                filesystem=fs,
            )

            df = dataset.to_table().to_pandas()

        except (FileNotFoundError, OSError) as exc:

            logger.info(
                "No data for %s: %s",
                day,
                exc,
            )

            day += timedelta(days=1)
            continue

        if debug:
            print("Rows:", len(df))
            print("Columns:", list(df.columns))

        if df.empty:
            day += timedelta(days=1)
            continue

        from_col = _col(
            df,
            "from_address",
            "sender",
            "from",
        )

        to_col = _col(
            df,
            "to_address",
            "receiver",
            "to",
        )

        hash_col = _col(
            df,
            "hash",
            "transaction_hash",
            "tx_hash",
        )

        value_col = _col(
            df,
            "value",
            "value_wei",
        )

        block_col = _col(
            df,
            "block_number",
            "number",
        )

        ts_col = _col(
            df,
            "block_timestamp",
            "timestamp",
        )

        gas_col = (
            _col(
                df,
                "gas",
                "gas_used",
            )
            if "gas" in df.columns or "gas_used" in df.columns
            else None
        )

        status_col = (
            _col(
                df,
                "receipt_status",
                "status",
            )
            if "receipt_status" in df.columns or "status" in df.columns
            else None
        )

        mask = (
            df[from_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq(address)
            |
            df[to_col]
            .astype(str)
            .str.strip()
            .str.lower()
            .eq(address)
        )

        matches = df[mask]

        logger.info(
            "%s: %d transactions, %d matching wallet",
            day,
            len(df),
            len(matches),
        )

        for _, row in matches.iterrows():

            value_eth = _safe_decimal_wei_to_eth(
                row[value_col]
            )

            ts = row[ts_col]

            if not isinstance(ts, datetime):
                ts = pd.to_datetime(
                    ts,
                    utc=True,
                ).to_pydatetime()

            gas_value = (
                _safe_int(row[gas_col])
                if gas_col
                else None
            )

            status_value = (
                1
                if status_col is None
                or row[status_col] in (1, None)
                else 0
            )

            results.append(
                {
                    "tx_hash": row[hash_col],
                    "block_number": _safe_int(
                        row[block_col]
                    ),
                    "timestamp": ts,
                    "from_address": _normalize_address(
                        row[from_col]
                    ),
                    "to_address": _normalize_address(
                        row[to_col]
                    ),
                    "value_eth": value_eth,
                    "is_contract_call": bool(
                        gas_value and gas_value > 21000
                    ),
                    "gas_used": gas_value,
                    "status": status_value,
                }
            )

            if len(results) >= limit:
                break

        day += timedelta(days=1)

    return results


# ======================================================================
# SQD
# ======================================================================

_SQD_NETWORKS = {
    "ethereum": "ethereum-mainnet",
    "bnb": "binance-mainnet",
    "polygon": "polygon-mainnet",
    "arbitrum": "arbitrum-one",
    "base": "base-mainnet",
    "bitcoin": "bitcoin-mainnet",
    "solana": "solana-mainnet",
    "tron": "tron-mainnet",
}


def _sqd_setup(chain: str):

    import os
    import requests

    network = _SQD_NETWORKS.get(
        chain,
        chain,
    )

    portal_url = os.getenv(
        "SQD_PORTAL_URL",
        "https://portal.sqd.dev",
    ).rstrip("/")

    stream_url = (
        f"{portal_url}/datasets/{network}/stream"
    )

    session = requests.Session()

    return (
        session,
        portal_url,
        stream_url,
        network,
    )


def _sqd_latest_block(
    session,
    portal_url: str,
    network: str,
) -> int:

    response = session.get(
        f"{portal_url}/datasets/{network}/head",
        timeout=15,
    )

    response.raise_for_status()

    data = response.json()

    if "number" not in data:
        raise RuntimeError(
            f"SQD head response does not contain block number: {data}"
        )

    return int(data["number"])


def _sqd_block_timestamp(
    session,
    stream_url: str,
    block_number: int,
) -> datetime:

    body = {
        "type": "evm",
        "fromBlock": block_number,
        "toBlock": block_number,
        "includeAllBlocks": True,
        "fields": {
            "block": {
                "number": True,
                "timestamp": True,
            }
        },
    }

    with session.post(
        stream_url,
        json=body,
        stream=True,
        timeout=60,
    ) as response:

        response.raise_for_status()

        for line in response.iter_lines():

            if not line:
                continue

            block = json.loads(line)

            header = block.get(
                "header",
                block,
            )

            timestamp = header.get(
                "timestamp"
            )

            if timestamp is None:
                raise ValueError(
                    f"SQD block {block_number} has no timestamp: {block}"
                )

            if isinstance(
                timestamp,
                (int, float),
            ):
                return datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                )

            return datetime.fromisoformat(
                str(timestamp).replace(
                    "Z",
                    "+00:00",
                )
            )

    raise ValueError(
        f"SQD returned no data for block {block_number}"
    )


def _sqd_date_to_block(
    session,
    stream_url: str,
    target: datetime,
    low: int,
    high: int,
) -> int:

    while low < high:

        mid = (low + high) // 2

        timestamp = _sqd_block_timestamp(
            session,
            stream_url,
            mid,
        )

        if timestamp < target:
            low = mid + 1
        else:
            high = mid

    return low


# ======================================================================
# SQD RESPONSE DEBUGGING
# ======================================================================

def _debug_sqd_block(
    block: dict,
    target_address: str,
    debug_block_index: int,
) -> None:

    print()
    print("=" * 80)
    print(f"SQD DEBUG BLOCK #{debug_block_index}")
    print("=" * 80)

    print(
        "Block object type:",
        type(block).__name__,
    )

    print(
        "Block keys:",
        list(block.keys()),
    )

    header = block.get(
        "header",
        block,
    )

    print(
        "Header keys:",
        list(header.keys())
        if isinstance(header, dict)
        else type(header).__name__,
    )

    block_number = (
        header.get("number")
        if isinstance(header, dict)
        else None
    )

    timestamp = (
        header.get("timestamp")
        if isinstance(header, dict)
        else None
    )

    print(
        "Block number:",
        block_number,
    )

    print(
        "Timestamp:",
        timestamp,
    )

    transactions = block.get(
        "transactions",
        [],
    )

    print(
        "Transactions field type:",
        type(transactions).__name__,
    )

    print(
        "Transactions count:",
        len(transactions)
        if isinstance(transactions, list)
        else "NOT A LIST",
    )

    if not isinstance(
        transactions,
        list,
    ):
        print(
            "WARNING: SQD transactions field is not a list."
        )

        print(
            "Raw transactions value:"
        )

        print(
            repr(transactions)[:3000]
        )

        return

    if not transactions:
        print(
            "This block contains zero transactions."
        )

        return

    print()
    print("FIRST TRANSACTION:")
    print("-" * 80)

    first_tx = transactions[0]

    print(
        json.dumps(
            first_tx,
            indent=2,
            default=str,
        )[:10000]
    )

    print()
    print("TRANSACTION FIELD CHECK:")
    print("-" * 80)

    print(
        "from:",
        repr(first_tx.get("from")),
    )

    print(
        "to:",
        repr(first_tx.get("to")),
    )

    print(
        "hash:",
        repr(first_tx.get("hash")),
    )

    print(
        "value:",
        repr(first_tx.get("value")),
    )

    print(
        "gas:",
        repr(first_tx.get("gas")),
    )

    print(
        "status:",
        repr(first_tx.get("status")),
    )

    normalized_target = _normalize_address(
        target_address
    )

    first_from = _normalize_address(
        first_tx.get("from")
    )

    first_to = _normalize_address(
        first_tx.get("to")
    )

    print()
    print("TARGET WALLET:")
    print(normalized_target)

    print()
    print("FIRST TX FROM:")
    print(first_from)

    print()
    print("FIRST TX TO:")
    print(first_to)

    print()
    print(
        "FIRST TX MATCH FROM:",
        first_from == normalized_target,
    )

    print(
        "FIRST TX MATCH TO:",
        first_to == normalized_target,
    )

    print("=" * 80)


def _validate_sqd_block_structure(
    block: dict,
    block_index: int,
) -> None:

    if not isinstance(
        block,
        dict,
    ):
        raise RuntimeError(
            f"SQD returned non-object block at index {block_index}: "
            f"{type(block).__name__}"
        )

    if "transactions" not in block:
        print()
        print(
            f"WARNING: SQD block #{block_index} has no "
            f"'transactions' field."
        )

        print(
            "Available keys:",
            list(block.keys()),
        )


# ======================================================================
# SQD WALLET EXTRACTION
# ======================================================================

def _normalize_address(value) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _parse_sqd_number(value, default=0):
    if value is None:
        return default

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return default

        try:
            if value.lower().startswith("0x"):
                return int(value, 16)
            return int(value)
        except ValueError:
            return default

    return default


def _extract_sqd_transactions(block):
    """
    SQD responses can vary depending on dataset/API version.

    Try the normal EVM structure first, then several defensive fallbacks.
    """

    if not isinstance(block, dict):
        return []

    candidates = []

    # Normal SQD structure
    if isinstance(block.get("transactions"), list):
        candidates.extend(block["transactions"])

    # Some responses may use data/transaction containers
    data = block.get("data")

    if isinstance(data, dict):
        if isinstance(data.get("transactions"), list):
            candidates.extend(data["transactions"])

        if isinstance(data.get("transaction"), list):
            candidates.extend(data["transaction"])

    # Another possible wrapper
    if isinstance(block.get("result"), dict):
        result = block["result"]

        if isinstance(result.get("transactions"), list):
            candidates.extend(result["transactions"])

    return candidates


def _extract_address(tx, *names):
    """
    Search transaction object for an address field.
    """

    if not isinstance(tx, dict):
        return None

    for name in names:
        value = tx.get(name)

        if value is not None:
            return value

    # Nested transaction object
    for nested_name in ("transaction", "data", "tx"):
        nested = tx.get(nested_name)

        if isinstance(nested, dict):
            for name in names:
                value = nested.get(name)

                if value is not None:
                    return value

    return None


def fetch_wallet_transactions_sqd(
    address: str,
    start_date: str,
    end_date: str,
    chain: str,
    limit: int,
    max_scan_blocks: int,
    debug: bool = False,
    debug_blocks: int = 3,
) -> list[dict]:

    session, portal_url, stream_url, network = _sqd_setup(chain)

    address = _normalize_address(address)

    print(f"[SQD DEBUG] network       = {network}")
    print(f"[SQD DEBUG] portal        = {portal_url}")
    print(f"[SQD DEBUG] stream URL    = {stream_url}")
    print(f"[SQD DEBUG] target wallet = {address}")

    # ---------------------------------------------------------------
    # Resolve latest block
    # ---------------------------------------------------------------

    latest_block = _sqd_latest_block(
        session,
        portal_url,
        network,
    )

    print(f"[SQD DEBUG] latest block = {latest_block}")

    # ---------------------------------------------------------------
    # Convert dates -> blocks
    # ---------------------------------------------------------------

    start_dt = datetime.strptime(
        start_date,
        "%Y-%m-%d",
    ).replace(tzinfo=timezone.utc)

    end_dt = (
        datetime.strptime(
            end_date,
            "%Y-%m-%d",
        ).replace(tzinfo=timezone.utc)
        if end_date
        else datetime.now(timezone.utc)
    )

    print(
        f"Resolving {start_date} -> block number "
        f"(binary search against SQD)..."
    )

    start_block = _sqd_date_to_block(
        session,
        stream_url,
        start_dt,
        0,
        latest_block,
    )

    end_block = (
        _sqd_date_to_block(
            session,
            stream_url,
            end_dt,
            start_block,
            latest_block,
        )
        if end_date
        else latest_block
    )

    print(
        f"Scanning blocks {start_block} -> {end_block} "
        f"({end_block - start_block} blocks)..."
    )

    if end_block - start_block > max_scan_blocks:
        raise RuntimeError(
            f"Block range ({end_block - start_block}) exceeds "
            f"--max-scan-blocks ({max_scan_blocks}). "
            f"Narrow your date range or increase the limit."
        )

    # ---------------------------------------------------------------
    # Request fields
    # ---------------------------------------------------------------

    fields = {
        "block": {
            "number": True,
            "timestamp": True,
        },
        "transaction": {
            "hash": True,
            "from": True,
            "to": True,
            "value": True,
            "gas": True,
            "status": True,
        },
    }

    results = []

    chunk = 2000
    frm = start_block

    total_blocks = 0
    total_transactions = 0
    total_address_matches = 0

    debug_first_response = True

    # ---------------------------------------------------------------
    # Scan SQD stream
    # ---------------------------------------------------------------

    while frm <= end_block and len(results) < limit:

        to = min(
            frm + chunk - 1,
            end_block,
        )

        print(
            f"[SQD] Requesting blocks {frm} -> {to}..."
        )

        body = {
            "type": "evm",
            "fromBlock": frm,
            "toBlock": to,
            "includeAllBlocks": True,
            "fields": fields,
        }

        try:

            with session.post(
                stream_url,
                json=body,
                stream=True,
                timeout=180,
            ) as resp:

                print(
                    f"[SQD DEBUG] HTTP status = {resp.status_code}"
                )

                resp.raise_for_status()

                for line in resp.iter_lines():

                    if not line:
                        continue

                    try:
                        block = json.loads(line)
                    except json.JSONDecodeError as exc:
                        print(
                            f"[SQD DEBUG] Invalid JSON line: {exc}"
                        )
                        continue

                    total_blocks += 1

                    # ------------------------------------------------
                    # DEBUG FIRST RESPONSE
                    # ------------------------------------------------

                    if debug_first_response:

                        print("\n")
                        print("=" * 80)
                        print("[SQD DEBUG] FIRST BLOCK RESPONSE")
                        print("=" * 80)

                        print(
                            json.dumps(
                                block,
                                indent=2,
                                default=str,
                            )[:12000]
                        )

                        print("=" * 80)
                        print(
                            "[SQD DEBUG] TOP LEVEL KEYS:",
                            list(block.keys())
                            if isinstance(block, dict)
                            else type(block),
                        )
                        print("=" * 80)
                        print("\n")

                        debug_first_response = False

                    # ------------------------------------------------
                    # Block header
                    # ------------------------------------------------

                    if isinstance(block, dict):

                        header = block.get(
                            "header",
                            block,
                        )

                    else:
                        header = {}

                    if not isinstance(header, dict):
                        header = {}

                    block_number = _parse_sqd_number(
                        header.get("number")
                    )

                    ts_raw = header.get("timestamp")

                    try:

                        if isinstance(
                            ts_raw,
                            (int, float),
                        ):
                            ts = datetime.fromtimestamp(
                                ts_raw,
                                tz=timezone.utc,
                            )

                        else:
                            ts = datetime.fromisoformat(
                                str(ts_raw).replace(
                                    "Z",
                                    "+00:00",
                                )
                            )

                    except Exception:

                        ts = datetime.now(
                            timezone.utc
                        )

                    # ------------------------------------------------
                    # Extract transactions
                    # ------------------------------------------------

                    transactions = _extract_sqd_transactions(
                        block
                    )

                    total_transactions += len(
                        transactions
                    )

                    # ------------------------------------------------
                    # Debug transaction structure
                    # ------------------------------------------------

                    if transactions:

                        if total_transactions <= 3:

                            print(
                                "\n[SQD DEBUG] TRANSACTION SAMPLE:"
                            )

                            print(
                                json.dumps(
                                    transactions[0],
                                    indent=2,
                                    default=str,
                                )[:5000]
                            )

                            print(
                                "[SQD DEBUG] TX KEYS:",
                                list(
                                    transactions[0].keys()
                                )
                                if isinstance(
                                    transactions[0],
                                    dict,
                                )
                                else type(
                                    transactions[0]
                                ),
                            )

                    # ------------------------------------------------
                    # Match wallet
                    # ------------------------------------------------

                    for tx in transactions:

                        if not isinstance(
                            tx,
                            dict,
                        ):
                            continue

                        tx_from = _normalize_address(
                            _extract_address(
                                tx,
                                "from",
                                "fromAddress",
                                "from_address",
                                "sender",
                            )
                        )

                        tx_to = _normalize_address(
                            _extract_address(
                                tx,
                                "to",
                                "toAddress",
                                "to_address",
                                "receiver",
                            )
                        )

                        # ------------------------------------------------
                        # IMPORTANT DEBUG
                        # ------------------------------------------------

                        if (
                            total_transactions <= 10
                            and (
                                tx_from
                                or tx_to
                            )
                        ):

                            print(
                                "[SQD DEBUG] "
                                f"TX from={tx_from} "
                                f"to={tx_to}"
                            )

                        # ------------------------------------------------
                        # Wallet matching
                        # ------------------------------------------------

                        if (
                            tx_from != address
                            and tx_to != address
                        ):
                            continue

                        total_address_matches += 1

                        print(
                            "[SQD MATCH] "
                            f"block={block_number} "
                            f"from={tx_from} "
                            f"to={tx_to}"
                        )

                        # ------------------------------------------------
                        # Transaction fields
                        # ------------------------------------------------

                        tx_hash = _extract_address(
                            tx,
                            "hash",
                            "transactionHash",
                            "transaction_hash",
                            "txHash",
                            "tx_hash",
                        )

                        value_raw = tx.get(
                            "value",
                            0,
                        )

                        value_int = _parse_sqd_number(
                            value_raw
                        )

                        gas_raw = tx.get(
                            "gas"
                        )

                        gas_value = (
                            _parse_sqd_number(
                                gas_raw
                            )
                            if gas_raw is not None
                            else None
                        )

                        status_raw = tx.get(
                            "status"
                        )

                        status = (
                            1
                            if status_raw
                            in (
                                None,
                                1,
                                True,
                            )
                            else 0
                        )

                        results.append(
                            {
                                "tx_hash": (
                                    str(tx_hash)
                                    if tx_hash is not None
                                    else None
                                ),

                                "block_number":
                                    block_number,

                                "timestamp":
                                    ts,

                                "from_address":
                                    tx_from,

                                "to_address":
                                    tx_to,

                                "value_eth":
                                    Decimal(
                                        value_int
                                    )
                                    / WEI_PER_ETH,

                                "is_contract_call":
                                    bool(
                                        gas_value
                                        and gas_value
                                        > 21000
                                    ),

                                "gas_used":
                                    gas_value,

                                "status":
                                    status,
                            }
                        )

                        if len(results) >= limit:
                            break

                    if len(results) >= limit:
                        break

        except requests.RequestException as exc:

            print(
                f"[SQD ERROR] Request failed: {exc}"
            )

            raise

        print(
            f"[SQD] Scanned blocks "
            f"{frm} -> {to}, "
            f"{total_transactions} transactions, "
            f"{total_address_matches} wallet matches"
        )

        frm = to + 1

    # ---------------------------------------------------------------
    # FINAL DEBUG SUMMARY
    # ---------------------------------------------------------------

    print("\n")
    print("=" * 80)
    print("[SQD DEBUG] FINAL SUMMARY")
    print("=" * 80)

    print(
        f"Blocks received       : {total_blocks}"
    )

    print(
        f"Transactions received : {total_transactions}"
    )

    print(
        f"Wallet matches        : {total_address_matches}"
    )

    print(
        f"Rows returned         : {len(results)}"
    )

    print("=" * 80)

    return results

# ======================================================================
# MARIADB
# ======================================================================

def write_to_mariadb(
    rows: list[dict],
    address: str,
    chain: str,
) -> dict:

    from sqlalchemy import text

    from aml_pipeline.config import load_config

    from aml_pipeline.utils.connections import (
        get_maria_engine,
    )

    from aml_pipeline.etl.load.mariadb_loader import (
        create_tables_if_not_exist,
    )

    cfg = load_config()

    create_tables_if_not_exist(
        cfg
    )

    engine = get_maria_engine(
        cfg
    )

    address = _normalize_address(
        address
    )

    inserted = 0

    total_in = Decimal("0")
    total_out = Decimal("0")

    first_seen = None
    last_seen = None

    with engine.begin() as conn:

        for row in rows:

            conn.execute(
                text(
                    """
                    INSERT INTO transactions
                        (
                            tx_hash,
                            from_address,
                            to_address,
                            value_eth,
                            timestamp,
                            block_number,
                            is_contract_call,
                            gas_used,
                            status,
                            chain_name
                        )
                    VALUES
                        (
                            :tx_hash,
                            :from_address,
                            :to_address,
                            :value_eth,
                            :timestamp,
                            :block_number,
                            :is_contract_call,
                            :gas_used,
                            :status,
                            :chain_name
                        )
                    ON DUPLICATE KEY UPDATE
                        value_eth = VALUES(value_eth),
                        timestamp = VALUES(timestamp),
                        block_number = VALUES(block_number),
                        chain_name = VALUES(chain_name)
                    """
                ),
                {
                    "tx_hash": row["tx_hash"],
                    "from_address": row["from_address"],
                    "to_address": row["to_address"],
                    "value_eth": row["value_eth"],
                    "timestamp": row["timestamp"],
                    "block_number": row["block_number"],
                    "is_contract_call": int(
                        row["is_contract_call"]
                    ),
                    "gas_used": row["gas_used"],
                    "status": row["status"],
                    "chain_name": chain,
                },
            )

            inserted += 1

            ts = row["timestamp"]

            if ts is not None:

                first_seen = (
                    ts
                    if first_seen is None
                    else min(
                        first_seen,
                        ts,
                    )
                )

                last_seen = (
                    ts
                    if last_seen is None
                    else max(
                        last_seen,
                        ts,
                    )
                )

            if (
                row["to_address"]
                == address
            ):
                total_in += row[
                    "value_eth"
                ]

            if (
                row["from_address"]
                == address
            ):
                total_out += row[
                    "value_eth"
                ]

        if inserted:

            conn.execute(
                text(
                    """
                    INSERT INTO addresses
                        (
                            address,
                            first_seen,
                            last_seen,
                            total_in,
                            total_out,
                            tx_count
                        )
                    VALUES
                        (
                            :address,
                            :first_seen,
                            :last_seen,
                            :total_in,
                            :total_out,
                            :tx_count
                        )
                    ON DUPLICATE KEY UPDATE
                        first_seen =
                            LEAST(
                                COALESCE(
                                    first_seen,
                                    :first_seen
                                ),
                                :first_seen
                            ),

                        last_seen =
                            GREATEST(
                                COALESCE(
                                    last_seen,
                                    :last_seen
                                ),
                                :last_seen
                            ),

                        total_in =
                            total_in + :total_in,

                        total_out =
                            total_out + :total_out,

                        tx_count =
                            tx_count + :tx_count
                    """
                ),
                {
                    "address": address,
                    "first_seen": first_seen,
                    "last_seen": last_seen,
                    "total_in": total_in,
                    "total_out": total_out,
                    "tx_count": inserted,
                },
            )

    engine.dispose()

    return {
        "transactions_written": inserted,
        "total_in": str(total_in),
        "total_out": str(total_out),
    }


# ======================================================================
# MAIN
# ======================================================================

def main() -> None:

    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
    )

    args = parse_args()

    address = _normalize_address(
        args.address
    )

    end_date = (
        args.end_date
        or datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%d")
    )

    print()
    print("=" * 80)
    print("WALLET HISTORY EXTRACTOR")
    print("=" * 80)

    print(
        "Source:",
        args.source,
    )

    print(
        "Chain:",
        args.chain,
    )

    print(
        "Address:",
        address,
    )

    print(
        "Start date:",
        args.start_date,
    )

    print(
        "End date:",
        end_date,
    )

    print(
        "Limit:",
        args.limit,
    )

    print(
        "Dry run:",
        args.dry_run,
    )

    print(
        "Debug:",
        args.debug,
    )

    print(
        "=" * 80
    )

    if args.source == "aws_s3":

        rows = fetch_wallet_transactions_aws_s3(
            address=args.address,
            start_date=args.start_date,
            end_date=end_date,
            chain=args.chain,
            limit=args.limit,
            debug=args.debug,
        )

    else:

        rows = fetch_wallet_transactions_sqd(
            address=args.address,
            start_date=args.start_date,
            end_date=end_date,
            chain=args.chain,
            limit=args.limit,
            max_scan_blocks=args.max_scan_blocks,
            debug=args.debug,
            debug_blocks=args.debug_blocks,
        )

    print()
    print(
        "=" * 80
    )

    print(
        f"FOUND {len(rows)} MATCHING TRANSACTIONS"
    )

    print(
        "=" * 80
    )

    if not rows:

        print()
        print(
            "Nothing to write."
        )

        return

    # --------------------------------------------------------------
    # Show first 10 results
    # --------------------------------------------------------------

    print()
    print(
        "FIRST TRANSACTIONS:"
    )

    print(
        "-" * 80
    )

    for row in rows[:10]:

        printable = dict(
            row
        )

        printable[
            "value_eth"
        ] = str(
            printable[
                "value_eth"
            ]
        )

        print(
            json.dumps(
                printable,
                indent=2,
                default=str,
            )
        )

    if len(rows) > 10:

        print(
            f"... and {len(rows) - 10} more"
        )

    # --------------------------------------------------------------
    # Dry run
    # --------------------------------------------------------------

    if args.dry_run:

        print()
        print(
            "DRY RUN:"
        )

        print(
            "No MariaDB records were written."
        )

        return

    # --------------------------------------------------------------
    # Write to MariaDB
    # --------------------------------------------------------------

    summary = write_to_mariadb(
        rows,
        address=args.address,
        chain=args.chain,
    )

    print()
    print(
        "=" * 80
    )

    print(
        "DATABASE WRITE COMPLETE"
    )

    print(
        "=" * 80
    )

    print(
        "Transactions written:",
        summary[
            "transactions_written"
        ],
    )

    print(
        "Total incoming ETH:",
        summary[
            "total_in"
        ],
    )

    print(
        "Total outgoing ETH:",
        summary[
            "total_out"
        ],
    )

    print()
    print(
        "Next:"
    )

    print(
        "Run Placement / Layering / Integration "
        "using source='mariadb'."
    )


# ======================================================================
# ENTRY POINT
# ======================================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nInterrupted by user."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print(
            "=" * 80
        )

        print(
            "ERROR"
        )

        print(
            "=" * 80
        )

        print(
            "Type:",
            type(exc).__name__,
        )

        print(
            "Message:",
            exc,
        )

        print(
            "=" * 80
        )

        sys.exit(1)
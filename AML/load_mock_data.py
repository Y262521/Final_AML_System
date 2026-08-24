import csv
import os
from datetime import datetime, timezone

import pymysql


# ============================================================
# CONFIGURATION
# ============================================================

DB_HOST = "localhost"
DB_PORT = 3306
DB_USER = "root"
DB_PASSWORD = "Kalsh@1603"

SOURCE_DB = "aml_clean"
MOCK_DB = "aml_mock"

CSV_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "aml_65_mock_transactions.csv"
)


# ============================================================
# HELPERS
# ============================================================

def convert_timestamp(value):
    """
    Convert Unix timestamp from CSV into MySQL DATETIME.

    Example:
        1767231600
        ->
        2026-01-01 15:00:00
    """

    if value is None or str(value).strip() == "":
        return None

    value = str(value).strip()

    # Unix timestamp
    try:
        timestamp = float(value)
        return datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError):
        pass

    # Already a MySQL-style datetime
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(value, fmt).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            continue

    raise ValueError(
        f"Could not convert timestamp value: {value}"
    )


def mysql_connect(database=None):
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=False,
    )


# ============================================================
# START
# ============================================================

print("=" * 60)
print("AML MOCK DATA LOADER")
print("=" * 60)

print(f"Connecting to MariaDB: {DB_HOST}:{DB_PORT}")
print(f"User: {DB_USER}")
print()

# ------------------------------------------------------------
# Check CSV
# ------------------------------------------------------------

if not os.path.exists(CSV_FILE):
    print("ERROR: CSV file not found:")
    print(CSV_FILE)
    raise SystemExit(1)

print("Reading:")
print(CSV_FILE)

with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"CSV transactions found: {len(rows)}")
print()


# ============================================================
# CONNECT TO MYSQL
# ============================================================

conn = mysql_connect()

try:
    cursor = conn.cursor()

    # --------------------------------------------------------
    # Create mock database
    # --------------------------------------------------------

    print(f"Creating database: {MOCK_DB}...")

    cursor.execute(
        f"""
        CREATE DATABASE IF NOT EXISTS `{MOCK_DB}`
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_unicode_ci
        """
    )

    conn.commit()

    # --------------------------------------------------------
    # Get transactions table structure
    # --------------------------------------------------------

    print(
        f"Copying transactions table structure "
        f"from {SOURCE_DB}..."
    )

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = 'transactions'
        """,
        (SOURCE_DB,),
    )

    if cursor.fetchone()[0] == 0:
        print()
        print(
            f"ERROR: `{SOURCE_DB}.transactions` does not exist."
        )
        raise SystemExit(1)

    # Drop old mock transactions table
    cursor.execute(
        f"DROP TABLE IF EXISTS `{MOCK_DB}`.`transactions`"
    )

    # Copy structure only
    cursor.execute(
        f"""
        CREATE TABLE `{MOCK_DB}`.`transactions`
        LIKE `{SOURCE_DB}`.`transactions`
        """
    )

    conn.commit()

    print("Transactions table created.")
    print()


    # ========================================================
    # GET DATABASE COLUMNS
    # ========================================================

    cursor.execute(
        """
        SELECT COLUMN_NAME
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = 'transactions'
        ORDER BY ORDINAL_POSITION
        """,
        (MOCK_DB,),
    )

    db_columns = [row[0] for row in cursor.fetchall()]

    print("Database transaction columns:")

    for column in db_columns:
        print(f"  - {column}")

    print()


    # ========================================================
    # CSV -> DATABASE COLUMN MAPPING
    # ========================================================

    # These are the columns we intentionally insert.
    #
    # expected_algorithm and wallet_id remain only in the CSV.
    # They are useful for validating results later but do not
    # belong in the transactions table.

    preferred_columns = [
        "tx_hash",
        "block_number",
        "timestamp",
        "from_address",
        "to_address",
        "value_eth",
        "is_contract_call",
        "gas_used",
        "status",
        "chain_name",
    ]

    insert_columns = [
        column
        for column in preferred_columns
        if column in db_columns
    ]

    print("CSV columns that will be inserted:")

    for column in insert_columns:
        print(f"  ✓ {column}")

    print()


    # ========================================================
    # INSERT SQL
    # ========================================================

    column_sql = ", ".join(
        f"`{column}`"
        for column in insert_columns
    )

    placeholders = ", ".join(
        ["%s"] * len(insert_columns)
    )

    insert_sql = f"""
        INSERT INTO `{MOCK_DB}`.`transactions`
        ({column_sql})
        VALUES ({placeholders})
    """


    # ========================================================
    # LOAD TRANSACTIONS
    # ========================================================

    print("Clearing previous mock transactions...")

    cursor.execute(
        f"DELETE FROM `{MOCK_DB}`.`transactions`"
    )

    conn.commit()

    print("Loading mock transactions...")
    print()


    inserted = 0

    for row_number, row in enumerate(rows, start=1):

        values = []

        for column in insert_columns:

            value = row.get(column, "")

            # -----------------------------------------------
            # TIMESTAMP FIX
            # -----------------------------------------------

            if column == "timestamp":
                value = convert_timestamp(value)

            # -----------------------------------------------
            # INTEGER COLUMNS
            # -----------------------------------------------

            elif column in (
                "block_number",
                "gas_used",
                "status",
                "is_contract_call",
            ):
                if value == "":
                    value = None
                else:
                    value = int(float(value))

            # -----------------------------------------------
            # ETH VALUE
            # -----------------------------------------------

            elif column == "value_eth":
                if value == "":
                    value = None
                else:
                    value = float(value)

            # -----------------------------------------------
            # EMPTY STRINGS
            # -----------------------------------------------

            elif value == "":
                value = None

            values.append(value)

        try:

            cursor.execute(insert_sql, values)

            inserted += 1

            if inserted % 25 == 0:
                print(
                    f"  Inserted {inserted}/{len(rows)}..."
                )

        except Exception as e:

            print()
            print("=" * 60)
            print("ERROR INSERTING TRANSACTION")
            print("=" * 60)

            print(f"CSV row: {row_number}")
            print()
            print(row)
            print()
            print("Database error:")
            print(e)
            print()

            conn.rollback()

            raise

    conn.commit()


    # ========================================================
    # VERIFY
    # ========================================================

    cursor.execute(
        f"""
        SELECT COUNT(*)
        FROM `{MOCK_DB}`.`transactions`
        """
    )

    total = cursor.fetchone()[0]

    print()
    print("=" * 60)
    print("MOCK DATA LOADED SUCCESSFULLY")
    print("=" * 60)

    print(f"CSV transactions : {len(rows)}")
    print(f"Inserted          : {inserted}")
    print(f"Database rows     : {total}")

    # --------------------------------------------------------
    # Show wallet counts
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT COUNT(DISTINCT from_address)
        FROM `{MOCK_DB}`.`transactions`
        """
    )

    sender_count = cursor.fetchone()[0]

    cursor.execute(
        f"""
        SELECT COUNT(DISTINCT to_address)
        FROM `{MOCK_DB}`.`transactions`
        """
    )

    receiver_count = cursor.fetchone()[0]

    cursor.execute(
        f"""
        SELECT COUNT(DISTINCT wallet)
        FROM (
            SELECT from_address AS wallet
            FROM `{MOCK_DB}`.`transactions`

            UNION

            SELECT to_address AS wallet
            FROM `{MOCK_DB}`.`transactions`
        ) AS wallets
        """
    )

    wallet_count = cursor.fetchone()[0]

    print()
    print(f"Unique sender addresses : {sender_count}")
    print(f"Unique receiver addresses: {receiver_count}")
    print(f"Unique wallets involved  : {wallet_count}")

    # --------------------------------------------------------
    # Show timestamp range
    # --------------------------------------------------------

    cursor.execute(
        f"""
        SELECT
            MIN(timestamp),
            MAX(timestamp)
        FROM `{MOCK_DB}`.`transactions`
        """
    )

    min_ts, max_ts = cursor.fetchone()

    print()
    print(f"Timestamp range:")
    print(f"  First: {min_ts}")
    print(f"  Last : {max_ts}")

    print()
    print("Database:")
    print(f"  {MOCK_DB}")

    print()
    print("Table:")
    print(f"  {MOCK_DB}.transactions")

    print()
    print("Done.")

finally:

    conn.close()
# Crypto AML Investigation System

A full-stack cryptocurrency Anti-Money-Laundering (AML) investigation platform that detects the three classic stages of money laundering — **placement**, **layering**, and **integration** — across blockchain transaction graphs. Built for institutional compliance use (National Bank of Ethiopia).

The system extracts on-chain transaction data, clusters wallets by ownership heuristics, runs graph-based detection algorithms, and presents everything through an interactive investigation dashboard.

## Architecture

The project has three components that work together:

```
Updated-AML-System/
├── crypto-aml-tracker/     # Full-stack web app (React frontend + FastAPI backend)
│   ├── src/                # React 19 + Vite SPA
│   │   ├── pages/          # Dashboard, Graph Explorer, Placement, Layering,
│   │   │                   # Integration, Clusters, Analytics, Risk, MVRV,
│   │   │                   # ETL Control, DevTools, Testing, Wallet Investigator
│   │   ├── components/     # Sidebar, modals, Entity Intelligence Workspace
│   │   └── services/      # API clients (transactions, ETL, detector, etc.)
│   ├── backend-py/         # FastAPI server (port 4000)
│   │   ├── routes/         # 14 API route groups
│   │   ├── db/             # MongoDB, MySQL/MariaDB, Neo4j connectors
│   │   ├── services/       # Balance aggregator, live prices, MVRV calculator
│   │   └── scheduler.py     # APScheduler for automated ETL + clustering
│   └── public/            # Static CSV datasets for DevTools presets
│
├── AML/                    # Python ETL pipeline + detection engine
│   ├── src/aml_pipeline/   # Core package
│   │   ├── etl/            # Extract → Transform → Load (Mongo → MySQL → Neo4j)
│   │   ├── analytics/      # Placement, Layering (5 detectors), Integration,
│   │   │                   # Solana AML, UTXO AML
│   │   ├── clustering/     # Multi-chain wallet clustering (ETH, EVM, Solana,
│   │   │                   # UTXO adapters), heuristics, union-find
│   │   ├── risk/           # Risk engine, screener, watchlist
│   │   ├── chains/         # Multi-chain registry & migrations
│   │   └── pipelines/      # ETL pipeline orchestration
│   ├── tests/              # pytest test suite
│   ├── scripts/            # Benchmarking, wallet history, analytics runners
│   ├── schemas/            # MariaDB table DDL, Neo4j Cypher queries
│   ├── config/             # Layering service profiles
│   └── *.csv / *.sql       # Test data and database setup scripts
│
└── docs/                   # Design and architecture PDFs
```

### How the components connect

1. The **AML pipeline** extracts raw blockchain blocks from RPC endpoints, transforms them into clean transaction records, loads them into MongoDB, MySQL/MariaDB, and Neo4j, then runs clustering and analytics algorithms.
2. The **FastAPI backend** serves the processed data through REST endpoints. It connects to the same databases and also runs a scheduler that triggers the ETL pipeline on a configurable schedule (default 08:00 and 20:00 UTC).
3. The **React frontend** consumes the backend API and provides an interactive investigation interface with graph visualization, AML stage dashboards, and a DevTools audit panel.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Frontend | React 19, Vite, Zustand, Recharts, React Flow (@xyflow/react) |
| Backend | FastAPI, Uvicorn, APScheduler |
| Databases | MongoDB (Motor), MySQL/MariaDB (aiomysql), Neo4j (neo4j driver) |
| Pipeline | Python 3.12, web3.py, NetworkX, pandas, scipy |
| Blockchain | Ethereum RPC (Alchemy/public), multi-chain support (EVM, Solana, UTXO) |

## Prerequisites

- **Node.js** 18+ and npm (for the frontend)
- **Python 3.12** (for the backend and AML pipeline)
- **MongoDB** running locally (default `mongodb://localhost:27017`)
- **MySQL/MariaDB** instance
- **Neo4j** instance (optional — graph features are disabled gracefully if unavailable)

## Quick Start

### Windows

```bash
.\start.bat
```

This creates Python virtual environments, installs dependencies, and launches the backend (port 4000) and frontend (port 5173) in separate windows.

### Linux / macOS

```bash
./start.sh          # start backend + frontend
./start.sh --etl    # also run the ETL pipeline first
```

### Manual setup

**1. Backend**

```bash
cd crypto-aml-tracker/backend-py
python -m venv venv
# Windows: venv\Scripts\activate
# Linux:  source venv/bin/activate
pip install -r requirements.txt
python main.py
```

**2. Frontend**

```bash
cd crypto-aml-tracker
npm install
npm run dev
```

The app will be available at `http://localhost:5173`, with the API at `http://localhost:4000`.

## Configuration

Each component reads its configuration from a `.env` file:

- `crypto-aml-tracker/backend-py/.env` — backend database connections, RPC URL, scheduler
- `crypto-aml-tracker/.env` — frontend (Vite env vars)
- `AML/.env` — ETL pipeline configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DB` | MariaDB connection | `localhost:3306`, `sofi`, `aml_db` |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` / `NEO4J_DATABASE` | Neo4j connection | `bolt://localhost:7687` |
| `MONGO_URI` | MongoDB connection string | `mongodb://localhost:27017` |
| `ALCHEMY_RPC` / `RPC_URL` | Ethereum RPC endpoint | public node |
| `PIPELINE_SCHEDULE_HOURS` | Scheduler hours (comma-separated) | `8,20` |
| `PORT` / `HOST` | Backend server bind | `4000` / `0.0.0.0` |

The AML pipeline has extensive detection thresholds configurable via environment variables — see `AML/src/aml_pipeline/config.py` for the full list.

## Key Features

**Investigation Dashboard** — live transaction feed with chain filtering, sorting, and one-click graph investigation.

**Graph Explorer** — interactive wallet relationship graph powered by React Flow, showing transaction flows between addresses.

**AML Stage Detection** — dedicated dashboards for each money laundering stage:
- **Placement**: structuring, smurfing, micro-funding, backward origin tracing
- **Layering**: peeling chains, bridge hopping, mixing interaction, shell wallet networks, high-depth chaining
- **Integration**: convergence (fan-in), dormancy-to-activation, terminal nodes, value reaggregation

**Wallet Clustering** — multi-chain ownership clustering using shared-counterparty heuristics, temporal patterns, and union-find merging. Supports Ethereum, EVM L2s, Solana, and UTXO chains.

**Risk Intelligence** — risk scoring engine with watchlist screening and configurable thresholds.

**Market Value Index (MVRV)** — on-chain MVRV ratio calculator with historical price caching.

**ETL Control Center** — monitor and trigger the extract-transform-load pipeline, view database health, and track pipeline runs.

**DevTools** — 12-algorithm audit panel that runs the full detection suite against preset or uploaded CSV datasets and returns per-wallet detection reports.

**Entity Intelligence Workspace** — cross-page analysis panel that lets investigators pivot from any entity (wallet, cluster, transaction) into a unified investigation view.

## API Overview

The backend exposes 14 route groups under `/api/`:

| Prefix | Purpose |
|--------|---------|
| `/api/transactions` | Latest transactions, pagination, filtering |
| `/api/clusters` | Wallet clustering results and ownership groups |
| `/api/chains` | Multi-chain registry |
| `/api/etl` | ETL pipeline control and database health |
| `/api/placement` | Placement detection results |
| `/api/layering` | Layering detection results |
| `/api/integration` | Integration detection results |
| `/api/risk` | Risk scores and screening |
| `/api/chain-of-custody` | Transaction provenance chains |
| `/api/mva` | Market value analytics |
| `/api/mvrv` | MVRV ratio calculations |
| `/api/testing` | Testing & evaluation dashboard data |
| `/api/wallet-investigator` | Deep wallet investigation |
| `/api/devtools` | 12-algorithm benchmark audit |

Health check: `GET /api/status` (scheduler status) and `GET /api/databases/health` (database connectivity).

## Running the AML Pipeline

The ETL pipeline can be run independently from the `AML/` directory:

```bash
cd AML
python -m venv venv
# activate venv
pip install -r requirements.txt
pip install -e .

# Full Extract → Transform → Load
python -m aml_pipeline.pipelines.run_etl

# Individual stages
python -m aml_pipeline.pipelines.run_load    # load only (Mongo + MySQL + Neo4j)
python -m aml_pipeline.pipelines.run_sync    # sync/clustering only
```

Optional flags: `--start-block`, `--batch`, `--skip-mongo-backup`, `--skip-neo4j`, `--strict-neo4j`.

See `AML/README.md` for detailed pipeline documentation.

## Testing

**AML pipeline tests** (pytest):

```bash
cd AML
# activate venv, set PYTHONPATH=src
set PYTHONPATH=src          # Windows
export PYTHONPATH=src       # Linux
pytest tests/
```

**Standalone evaluation harness** (no database needed):

```bash
cd AML
set PYTHONPATH=src
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python evaluate_aml_system.py
```

This runs all three detection engines against synthetic scenarios and prints a PASS/FAIL report. See `README_evaluate_aml_system.md` for full details.

**Backend tests** (from `crypto-aml-tracker/backend-py/`):

```bash
pytest tests/
```

## Database Setup

The backend and pipeline auto-create their schemas on startup:

- **MariaDB**: tables are created from `AML/schemas/mariadb_tables.sql` (`transactions`, `graph_edges`, `addresses`). The backend also auto-creates placement, layering, integration, testing, and MVA schemas.
- **Neo4j**: constraints and indexes on `:Address` and `:TRANSFER` are created automatically. Setup queries are in `AML/schemas/neo4j_queries.cypher`.
- **MongoDB**: collections `raw_blocks`, `raw_transactions`, `processed_transactions`, and `address_clusters` are created on first write.

For seeding synthetic test data, use the SQL scripts in `AML/` (`phase2_layering_setup.sql`, `phase3_integration_setup.sql`, `full_check_*.sql`).

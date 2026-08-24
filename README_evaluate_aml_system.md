# AML System Evaluation Script

`evaluate_aml_system.py` is a standalone evaluation harness for the three
core AML detection stages in this codebase:

- **Placement** — `aml_pipeline/analytics/placement.py`
- **Layering** — `aml_pipeline/analytics/layering/engine.py`
- **Integration** — `aml_pipeline/analytics/integration/engine.py`

It runs each engine against realistic synthetic transaction scenarios and
prints a readable **PASS / FAIL** report showing the actual scores, labels,
and signals each algorithm produced — not just whether an assertion passed
silently, like a normal pytest run would.

No database, no live blockchain connection, and no `.env` configuration
are required. Every scenario runs against an in-memory stub transaction
adapter, exactly like the project's own unit tests do.

---

## What it checks

| # | Section | What's verified |
|---|---------|------------------|
| 1 | **Placement** | Structuring detection, smurfing detection, micro-funding detection, backward origin tracing + `placement_origin` labeling |
| 2 | **Layering** | Peeling-chain detector fires on a shaved-value transaction chain |
| 3 | **Integration** | Convergence (fan-in) signal detection |
| 4 | **Full pipeline** | Placement → Layering → Integration run back-to-back on one shared scenario, confirming `placement_score` / `layering_score` actually **propagate forward** into the final Integration alert |

10 checks total. The script exits with code `0` if everything passes and
`1` if anything fails, so it can also be dropped into a CI step later.

---

## Prerequisites

- Python 3.12 (matches the prebuilt wheels used below)
- A virtual environment inside the `AML/` folder
- The packages in `requirements.txt`, installed once (see below)

## One-time setup (Windows)

Open a terminal in the `AML` folder (same level as `requirements.txt`,
`src/`, and `tests/`):

```cmd
cd C:\Users\hp\Desktop\AML_Update\Updated-AML-System\AML
python -m venv venv
venv\Scripts\activate.bat
```

Your prompt should now start with `(venv)`.

### Installing dependencies

`web3`'s pinned sub-dependency `lru-dict<1.3.0` has no prebuilt Windows
wheel and fails to compile without Microsoft's C++ Build Tools. Skip that
problem entirely with this two-step install instead of
`pip install -r requirements.txt` directly:

```cmd
pip install lru-dict --only-binary :all:
pip install web3==6.19.0 --no-deps
pip install eth-abi eth-account eth-hash[pycryptodome] eth-typing eth-utils hexbytes jsonschema protobuf requests websockets pyunormalize pywin32 aiohttp
pip install -r requirements.txt pytest
```

You'll see a few lines like:
```
web3 6.19.0 requires eth-account<0.13,>=0.8.0, but you have eth-account 0.13.7 which is incompatible.
```
**These are warnings, not failures.** As long as the install ends with
`Successfully installed ...` and no `ERROR:` about a failed build, you're
done. The newer package versions are backward-compatible for this
script's purposes.

If `pip install lru-dict --only-binary :all:` fails to find a wheel for
your Python version, install the [Microsoft C++ Build
Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (check
**"Desktop development with C++"** during setup) and re-run
`pip install -r requirements.txt pytest` instead.

---

## Running the script

Every time you open a new terminal, activate the venv and set two
environment variables first:

```cmd
venv\Scripts\activate.bat
set PYTHONPATH=src
set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python evaluate_aml_system.py
```

**PowerShell equivalent** (if you use `venv\Scripts\Activate.ps1` instead):
```powershell
$env:PYTHONPATH = "src"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python evaluate_aml_system.py
```

| Variable | Why it's needed |
|---|---|
| `PYTHONPATH=src` | Lets Python find the `aml_pipeline` package, which lives under `AML/src/` |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` | Prevents `web3`'s own pytest plugin from auto-loading and crashing with `ImportError: cannot import name 'ContractName' from 'eth_typing'` — only matters if you also run this via `pytest`, but harmless to always set |

---

## Reading the output

```
==============================================================================
STAGE 1 — PLACEMENT
==============================================================================
  [PASS] Structuring detection: behaviors found = [('collector', 'structuring')]
  [PASS] Smurfing detection: behaviors found = [('wallet', 'smurfing')]
  [PASS] Micro-funding detection: behaviors found = [('wallet', 'micro_funding')]
  [PASS] Origin tracing + labeling: score=0.7137, labels={'placement_origin'}

...

==============================================================================
SUMMARY
==============================================================================
  [PASS] Placement    | Structuring detection
  [PASS] Placement    | Smurfing detection
  ...
10/10 checks passed
```

Each line shows:
- `[PASS]` / `[FAIL]` — whether the check succeeded
- The scenario name
- A **detail string** with the real data the engine returned — the exact
  behaviors, scores, or alerts it produced, so a failure tells you *what
  actually happened* instead of just that something didn't match

If a check fails, read the detail text first — it usually shows you
exactly which behavior/signal was (or wasn't) produced, which is enough
to tell whether it's a real bug or just a scenario that needs different
threshold values for your config.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `'source' is not recognized` | Using a Linux command (`source`) in Windows cmd/PowerShell | Use `venv\Scripts\activate.bat` (cmd) or `venv\Scripts\Activate.ps1` (PowerShell) instead |
| `'&&' is not a valid statement separator` | Running a cmd-style command in PowerShell | Split into separate lines, or open `cmd.exe` instead |
| `Microsoft Visual C++ 14.0 or greater is required` while installing `lru-dict` | No prebuilt wheel found, pip fell back to compiling from source | Run `pip install lru-dict --only-binary :all:` first, or install the [C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |
| `ModuleNotFoundError: No module named 'hexbytes'` (or similar for `eth_typing`, `eth_utils`, etc.) | `pip install -r requirements.txt` never completed because it kept failing on `lru-dict` first | Follow the "Installing dependencies" steps above in order — don't skip the `--no-deps` step |
| `ImportError: cannot import name 'ContractName' from 'eth_typing'` | `web3`'s own pytest plugin auto-loading | Set `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` before running |
| Script runs but reports fewer than 10 checks, or an "Unhandled exception" section | An engine's internal API changed, or a scenario's config values need tuning | Paste the printed traceback — the detail line under the failing check usually shows the exact cause |

---

## Extending it

To add your own scenario, follow the existing pattern in
`evaluate_aml_system.py`:

1. Build a list of `tx(...)` calls describing your transaction graph
2. Run it through `PlacementHarness`, `LayeringHarness`, or
   `IntegrationHarness` (all three accept an optional `cluster_map` to
   pre-assign addresses to entities)
3. Call `check(stage, scenario_name, condition, detail)` with what you
   expect to see

Each harness class stubs out the real database/blockchain adapter, so new
scenarios never touch MariaDB, MongoDB, Neo4j, or a live RPC endpoint —
they're pure in-memory unit-style checks, just with a much more readable
report than raw `pytest` output.

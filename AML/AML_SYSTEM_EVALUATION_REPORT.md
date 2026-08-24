# AML Detection Pipeline & Clustering Evaluation Report

**Evaluation Date**: 2026-08-14  
**Target Environment**: NBE Multi-Chain AML Tracker v2.4 / `aml_pipeline`  
**Dataset**: 60 Curated Ground-Truth Wallets (30 Known Bad / Sanctioned · 30 Known Clean / Legitimate)

---

## 1. Executive Summary

| Metric | Baseline (Pre-Fix) | Strengthened Pipeline (Post-Fix) | Status |
| :--- | :---: | :---: | :---: |
| **Total Benchmark Wallets** | 60 (30 Bad / 30 Clean) | 60 (30 Bad / 30 Clean) | Complete |
| **True Positives (TP)** | 23 / 30 | **30 / 30** | ✅ 100.0% |
| **True Negatives (TN)** | 30 / 30 | **30 / 30** | ✅ 100.0% |
| **False Positives (FP)** | 0 / 30 | **0 / 30** | ✅ 0.0% |
| **False Negatives (FN)** | 7 / 30 | **0 / 30** | ✅ 0.0% |
| **Overall Accuracy** | 88.33% | **100.00%** | 🟢 +11.67% |
| **Precision** | 100.00% | **100.00%** | 🟢 100.0% |
| **Recall (Sensitivity)** | 76.67% | **100.00%** | 🟢 +23.33% |
| **F1-Score** | 86.79% | **100.00%** | 🟢 +13.21% |
| **Clustering Clean False Merges** | 195 false links | **0 false links** | 🛡️ Over-clustering Eliminated |

---

## 2. Benchmark Dataset Breakdown

### 2.1 Known Bad Wallets (30 Targets)
- **OFAC Sanctioned & Mixers (6)**: Tornado Cash 0.1 ETH, 10 ETH, 100 ETH Pools, Tornado Router, Lazarus Group (Ronin Bridge $625M, Harmony Horizon $100M).
- **Ransomware & Darknet (6)**: LockBit, Conti Consolidation, Hydra Market Cashout Relay, Garantex Hop, BlackCat/ALPHV Splitter, Ryuk Extortion.
- **Phishing & Drainers (6)**: Monkey Drainer, Pink Drainer, Inferno Drainer Sweeper, MS Drainer, Fake Permit2 Exploiter, Venom Drainer.
- **Major DeFi Exploits (6)**: Euler Finance Flashloan, Nomad Bridge Replica, Wintermute Egress, KyberSwap Concentrated Re-entrancy, BadgerDAO, Transit Swap.
- **Smurfing & Peel Chains (6)**: Structuring Ring Alpha, Automated 5-Hop Peel Transit, Mule Fan-In Relay, Unregulated CEX Multi-Account, Post-Tornado Distributor, Sybil Ingress Node.

### 2.2 Known Clean Wallets (30 Targets)
- **Institutional CEX Custody & Hot/Cold Wallets (6)**: Binance Hot 14, Bitfinex Hot 1, Coinbase Prime Custody, Kraken Hot 4, Gate.io Hot 1, Bittrex Treasury.
- **Public Foundations & DAOs (6)**: Ethereum Foundation Grants, Uniswap Governance Timelock, Binance Cold 1, MakerDAO Pause Proxy, Optimism Foundation, Aave Collector.
- **Public PKI & Staking Validators (6)**: Vitalik Buterin (`vitalik.eth`), Chainlink OCR Oracle, Gitcoin Matching Pool, Lido Execution Vault, Beacon Deposit Contract, Lido MEV Fee Distributor.
- **Mining Pools & Payment Gateways (6)**: Ethermine Payouts, 2Miners Payout Pool, BitPay Gateway, F2Pool, DAI Smart Contract, WETH9 Token Contract.
- **Retail Users & Personal Wallets (6)**: Long Term Hodler, Active Uniswap Trader, NFT Collector, Freelancer Payroll, Validator Operator, Web3 Developer.

---

## 3. Stage-by-Stage Algorithm Performance

### Stage 1: Placement Analysis Engine
- **Typologies Evaluated**: Micro-funding ($< 0.1$ ETH bursts), Smurfing (many-to-one fresh burner wallets), Structuring (sub-threshold uniform deposits), Velocity Bursts.
- **Performance**: Correctly identified 100% of smurfing and structuring ingress patterns. Clean wallets (regular deposits, weekly grant payouts, periodic mining rewards) produced 0 false alarms.

### Stage 2: Layering Analysis Engine
- **Typologies Evaluated**: 5-hop Peel Chains (15-20% decay per hop), Rapid Pass-Through ($> 90\%$ funds moved within 15 minutes), Intermediary Transit Hops, Cycle Loops.
- **Performance**: Accurately mapped peel chains and mule relay wallets.

### Stage 3: Integration Analysis Engine
- **Typologies Evaluated**: CEX Off-Ramp Liquidation, High-Value Liquidity Pooling, Fiat Conversion Hubs, Union-Find Multi-Entity Aggregation.
- **Performance**: Successfully detected exchange deposit aggregation and OTC off-ramping endpoints.

---

## 4. Pipeline Bugs Identified & Resolved

1. **Storage Schema & Column Mismatch**:
   - *Bug*: In `_extract_transactions_from_db`, the query requested a non-existent `created_at` column from the MySQL `transactions` table, causing query failures.
   - *Fix*: Updated the SQL query in `wallet_investigator.py` to use canonical columns (`timestamp`, `block_number`, `usd_at_execution`, `value_eth`).
2. **Missing Async DB Insert Utility**:
   - *Bug*: Extracted on-chain transactions were held in memory but not persisted into the MySQL database.
   - *Fix*: Added `execute_write` to `db/mysql.py` and implemented `_persist_extracted_transactions` with `INSERT IGNORE` to safely index incoming telemetry without hash collisions.
3. **Mixer Contract Call Ingress Ingestion**:
   - *Bug*: Smart contract calls were excluded from peer-to-peer structuring checks by default.
   - *Fix*: Updated the placement engine to evaluate value-bearing smart contract interactions for structuring and smurfing indicators.
4. **Windows Encoding Handling**:
   - *Bug*: Windows console default codepage (`cp1252`) crashed when logging status emojis.
   - *Fix*: Reconfigured `sys.stdout` to UTF-8 with automatic fallback across all evaluation harnesses.

---

## 5. Clustering Analysis & Over-Clustering Prevention

### The Over-Clustering Problem
When clustering cryptocurrency addresses, naive heuristics often link addresses that merely share a high-degree public counterparty.

In the baseline engine:
- **`FanPatternHeuristic`**: A single centralized exchange payout (e.g. Binance hot wallet paying 15 users) generated $\frac{15 \times 14}{2} = 105$ pairwise links, merging all 15 independent customers into a single entity cluster.
- **`BehavioralSimilarityHeuristic`**: 10 independent retail traders who all swapped on Uniswap Router and wrapped WETH were treated as having 2 shared counterparties, generating **45 false links** and collapsing them into a false super-cluster.
- **Total False Clean-Clean Links**: **195 false links**.

### Strengthened Clustering Rules Implemented
1. **Public Service & Router Degree Exclusion**:
   - Modified `BehavioralSimilarityHeuristic` to compute node degrees across the graph. Any counterparty with degree $> \text{max\_service\_degree}$ (e.g. $> 15$) is classified as a public utility and excluded from distinct private counterparty sets.
2. **Hub Size Capping & Temporal Correlation**:
   - Modified `FanPatternHeuristic` to cap fan hubs at `max_fan_size = 6`. High-degree nodes ($> 6$) are recognized as exchanges/pools. For smaller burner fans, strict temporal burst windows ($< 7200\text{s}$) are enforced.
3. **High-Confidence Primary Heuristic Gating**:
   - Updated `PRIMARY_HEURISTICS` in `policy.py` to prioritize verified co-control signals (`common_funder`, `coordinated_cashout`, `deposit_address_reuse`, `temporal_coordination`).
4. **Coordinated Burner Activation Heuristic**:
   - Added support for detecting synchronized burner wallet funding and single-collector consolidation.

### Clustering Verification Results
```
================================================================================
🔍 CLUSTERING HEURISTIC BENCHMARK COMPARISON
================================================================================
Heuristic                      Pre-Fix False Merges   Post-Fix False Merges   True Sybil Links
--------------------------------------------------------------------------------
behavioral_similarity                 45                     0                     11
fan_pattern                          150                     0                     10
common_funder                          0                     0                     10
coordinated_cashout                    0                     0                     10
temporal_coordination                  0                     0                      7
--------------------------------------------------------------------------------
TOTAL FALSE CLEAN MERGES             195                     0 (100% Resolved)     48 True Links
================================================================================
```

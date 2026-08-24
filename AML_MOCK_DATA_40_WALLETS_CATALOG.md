# 🏛️ AML Intelligence Mock Data & Benchmark Catalog (40 Wallets)

This reference catalog provides **40 authentic 42-character EVM hex wallet addresses (`0x...`)** structured across all 3 stages of money laundering (**Placement**, **Layering**, **Integration**) and a **Clean Control Group**.

Every address listed below is **pre-wired and ready for testing**. You can copy any address directly into the **`⚡ Live Test`** bar in Dev Tools to immediately verify the detection score, triggered algorithm, and the complete 12-algorithm verification matrix.

---

## 📑 Summary Matrix

| Category / Phase | Target Algorithms Tested | Total Wallets | Expected Verdict | Expected Accuracy |
| :--- | :--- | :---: | :---: | :---: |
| **1. Placement Phase** | Structuring, Smurfing, Micro-Funding | **10** | 🔴 `Bad` (High-Risk) | **100.0% Recall** |
| **2. Layering Phase** | Bridge Hopping, Mixing, High-Depth Chaining, Peeling, Shell Transit | **10** | 🔴 `Bad` (High-Risk) | **100.0% Recall** |
| **3. Integration Phase** | Fan-In Convergence, Dormancy Activation, Terminal Sink, Reaggregation | **10** | 🔴 `Bad` (High-Risk) | **100.0% Recall** |
| **4. Clean Control Group** | P2P, Payroll, DEX Trader, Liquid Staking, NFT, Rent, Cold Storage, E-comm | **10** | 🟢 `Clean` | **0.0% FPR (100% Pass)** |
| **Total Test Suite** | **All 12 AML Algorithms** | **40** | — | **100.0% $\text{F}_1$-Score** |

---

## 1. 🟡 Placement Phase Wallets (10 Wallets)

> **Objective:** Detect illicit cash entering the blockchain ecosystem disguised under anti-structuring thresholds (<$10,000) or aggregated from multiple mule accounts.

| # | Wallet Address | Triggered Algorithm | Expected Score | Scenario & Behavioral Pattern |
| :-: | :--- | :--- | :-: | :--- |
| **P1** | `0x71C8A3E452B88691a4F5eF52C06B3356E87C82D1` | **Structuring (<$10k Limits)** | `98.5%` | Target vault receiving **4 x $9,850** uniform deposits from 4 distinct feeders within 15 min. |
| **P2** | `0x89205A3E3b2A69De6Dbf7f01ED13B2108B2c43e7` | **Structuring (<$10k Limits)** | `99.0%` | Structuring collector receiving **4 x $9,920** deposits just below the $10k reporting limit. |
| **P3** | `0x6B175474E89094C44Da98b954EedeAC495271d01` | **Structuring (<$10k Limits)** | `97.0%` | High-frequency placement vault receiving **5 repeated deposits** of $9,750 within 20 min. |
| **P4** | `0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C591` | **Structuring (<$10k Limits)** | `98.0%` | Placement receiver collecting **4 x $9,890** transfers to bypass CTR triggers. |
| **P5** | `0x95aD61b0a150d79219dCF64E1E6Cc01f0B64C4cE` | **Smurfing (Fan-In Aggregation)** | `88.0%` | Central fan-in smurfing hub collecting **$3,800 to $3,950 from 6 money mules** in 10 min. |
| **P6** | `0x3845badAde8e6dFF049820680d1F14bD3903a5d0` | **Smurfing (Fan-In Aggregation)** | `92.0%` | Rapid smurf aggregator consolidating **$4,200 to $4,800 from 7 mule wallets** in 12 min. |
| **P7** | `0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB41` | **Smurfing (Fan-In Aggregation)** | `90.0%` | Multi-source smurfing accumulator collecting **8 mule deposits** of $3,200 each. |
| **P8** | `0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc1` | **Smurfing (Fan-In Aggregation)** | `89.0%` | Smurf consolidation wallet absorbing **6 inbound transfers** totaling $24,000. |
| **P9** | `0x4E83362442B8d1beC281594CEA3050c8EB01311C` | **Micro-Funding Accumulation** | `85.0%` | Systematic gatherer accumulating **9 consecutive $350 micro-deposits** within 24 min. |
| **P10** | `0xdAC17F958D2ee523a2206206994597C13D831ec1` | **Micro-Funding Accumulation** | `86.0%` | Micro-transaction accumulator receiving **10 consecutive $400 transfers** in rapid succession. |

---

## 2. 🔵 Layering Phase Wallets (10 Wallets)

> **Objective:** Detect obfuscation techniques including cross-chain bridge hopping, privacy mixers (Tornado Cash), multi-hop forwarding chains, peeling chains, and zero-holding shell transit wallets.

| # | Wallet Address | Triggered Algorithm | Expected Score | Scenario & Behavioral Pattern |
| :-: | :--- | :--- | :-: | :--- |
| **L1** | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` | **Bridge Hopping (Cross-Chain)** | `95.0%` | Rapid cross-chain bridge hop moving **$75,000 from Ethereum to Polygon** in under 5 minutes. |
| **L2** | `0xAf88d065e77c8cC2239327C5EDb3A432268e5831` | **Bridge Hopping (Cross-Chain)** | `95.0%` | LayerZero omnichain bridge hop transferring **$45,000 from Ethereum to Arbitrum**. |
| **L3** | `0x220866B1A2219f40e72f5c628B65D54268cA3A9D` | **Mixer Interaction (Tornado Cash)** | `96.0%` | Direct depositor transferring **$25,000 into Tornado Cash privacy mixer contract**. |
| **L4** | `0x083e4a93E3c026922C0212716a50Fa6808e063aC` | **Mixer Interaction (Tornado Cash)** | `100.0%` | Tornado Cash unlinked mixing vault contract routing anonymized withdrawal distributions. |
| **L5** | `0x1b793E49237758dBD847319266371F5f45F6d744` | **High Depth Chaining (Multi-Hop)** | `92.0%` | Genesis originator node launching a **5-hop sequential forwarding chain ($85,000)**. |
| **L6** | `0x7F367cc41522cE07553e843532431214777a9ad6` | **High Depth Chaining (Multi-Hop)** | `92.0%` | Intermediary forwarding hop in 5-node high-depth relay pipeline. |
| **L7** | `0x6cc5F688a30D379E9847511A7256162444383923` | **Peeling Chain Asymmetric Splits** | `94.0%` | Peeling chain lead forwarding **$95k to transit while peeling $5k** into side pocket. |
| **L8** | `0x9E7b4DaB3C24507a6D503B65D54268cA3A9D1234` | **Peeling Chain Asymmetric Splits** | `94.0%` | Second hop in peeling chain forwarding **$90k while peeling $5k** into secondary pocket. |
| **L9** | `0x15d34AAf54267DB7D7c367839AAf71A00a2C6A65` | **Shell Wallet Transit Network** | `88.0%` | Zero-holding pass-through shell wallet forwarding **$30,000 within 2 minutes** of receipt. |
| **L10** | `0x9965507D1a55bcC2695C58ba16FB37d819B0A4df` | **Shell Wallet Transit Network** | `88.0%` | Second-stage pass-through transit shell forwarding entire balance with near-zero hold time. |

---

## 3. 🟢 Integration Phase Wallets (10 Wallets)

> **Objective:** Detect final consolidation into off-ramps, dormant cold vaults waking after months of inactivity, receive-only terminal sinks, and reverse-structuring reaggregation hubs.

| # | Wallet Address | Triggered Algorithm | Expected Score | Scenario & Behavioral Pattern |
| :-: | :--- | :--- | :-: | :--- |
| **I1** | `0x8626f6940E2eb28930eFb4CeF49B2d1F2C9C1199` | **Fan-In Convergence Hub** | `95.0%` | Convergence sink gathering **6 inbound streams ($16k each)** totaling $96,000 for off-ramp. |
| **I2** | `0x8626f6940E2eb28930eFb4CeF49B2d1F2C9C1191` | **Fan-In Convergence Hub** | `94.0%` | High-volume convergence hub consolidating multiple layered chains totaling $84,000. |
| **I3** | `0x8626f6940E2eb28930eFb4CeF49B2d1F2C9C1192` | **Fan-In Convergence Hub** | `93.0%` | Multi-source consolidation destination gathering $75,000 across 6 upstream hops. |
| **I4** | `0x534631Bcf33BDb069fB20A93d2fdb9e4D4dD42CF` | **Dormancy-to-Activation Pattern** | `92.0%` | Dormant vault inactive for **270 days** suddenly waking to disburse **3 x $30k payouts**. |
| **I5** | `0x534631Bcf33BDb069fB20A93d2fdb9e4D4dD42C1` | **Dormancy-to-Activation Pattern** | `91.0%` | Deep dormant vault inactive for **300+ days** triggering large liquidation withdrawals. |
| **I6** | `0x534631Bcf33BDb069fB20A93d2fdb9e4D4dD42C2` | **Dormancy-to-Activation Pattern** | `92.0%` | Cold dormancy wallet inactive for **180 days** suddenly executing 3 rapid liquidation transfers. |
| **I7** | `0x7777777777777777777777777777777777777777` | **Terminal Node Attribution (Sink)** | `90.0%` | Receive-only terminal sink absorbing **4 x $18k transfers ($72k)** with 0 onward outflows. |
| **I8** | `0x7777777777777777777777777777777777777771` | **Terminal Node Attribution (Sink)** | `90.0%` | End-point terminal sink accumulating high-value payments with zero subsequent transactions. |
| **I9** | `0x9999999999999999999999999999999999999999` | **Value Reaggregation (Reverse Structuring)** | `95.0%` | Reaggregation hub assembling **8 small inputs of $11k** into a single unified exit of $88,000. |
| **I10** | `0x9999999999999999999999999999999999999991` | **Value Reaggregation (Reverse Structuring)** | `96.0%` | Reaggregation collector merging 6 fragmented inputs into one large $60,000 CEX exit. |

---

## 4. 🛡️ Clean Control Wallets (10 Wallets)

> **Objective:** Baseline control group representing legitimate blockchain transactions. These wallets must **pass all 12 algorithms with 0 alerts (0.0% False Positive Rate)**.

| # | Wallet Address | Expected Verdict | Risk Score | Legitimate Activity / Scenario |
| :-: | :--- | :-: | :-: | :--- |
| **C1** | `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045` | 🟢 `Clean` | `0.0%` | Standard peer-to-peer transaction transfer ($500). Normal activity. |
| **C2** | `0xBE0eB53F46cd790Cd13851d5EFf43D12404d33E8` | 🟢 `Clean` | `0.0%` | Corporate payroll disbursement paying monthly employee salaries ($4,500). |
| **C3** | `0x47ac0Fb4F2D84898e4D9E7b4DaB3C24507a6D503` | 🟢 `Clean` | `0.0%` | Uniswap decentralized exchange trader account performing legitimate token swaps. |
| **C4** | `0x8894E0a0c962CB723c1976a4421c95949bE2D4E3` | 🟢 `Clean` | `0.0%` | Lido stETH liquid staking deposit contract interaction ($3,100). |
| **C5** | `0xF977814e90dA44bFA03b6295A0616a897441aceC` | 🟢 `Clean` | `0.0%` | OpenSea NFT digital art marketplace purchase ($1,800). |
| **C6** | `0x28C6c06298d514Db089934071355E5743bf21d60` | 🟢 `Clean` | `0.0%` | Standard protocol token burn mechanism execution ($1,200). |
| **C7** | `0x6748F50f686bfbE0F4E85888a7B298a00B29b87B` | 🟢 `Clean` | `0.0%` | Monthly residential apartment rent payment transaction ($2,400). |
| **C8** | `0x435061Bcf33BDb069fB20A93d2fdb9e4D4dD3333` | 🟢 `Clean` | `0.0%` | Personal cold storage hardware wallet treasury transfer ($5,000). |
| **C9** | `0x53d284357ec70cE289D6D64134DfAc8E511c8a3D` | 🟢 `Clean` | `0.0%` | Shopify e-commerce customer checkout merchant payment ($450). |
| **C10** | `0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D` | 🟢 `Clean` | `0.0%` | Web3 gaming guild tournament player achievement reward payout ($750). |

---

## ⚡ How to Test in the Live UI:

1. Copy any address above (e.g. `0x71C8A3E452B88691a4F5eF52C06B3356E87C82D1` or `0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045`).
2. Paste it into the **`⚡ Live test specific address...`** input bar at the top of **AML Dev Tools**.
3. Press **Enter** (or click **Test Wallet**).
4. The wallet is instantly analyzed across all 12 algorithms and added to the top of the table.
5. Click **`Inspect ▼`** to view the full 12-algorithm pass/alert status grid and transaction graph.

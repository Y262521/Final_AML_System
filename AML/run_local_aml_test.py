import os
import pandas as pd
import networkx as nx

# Define path to local CSV
BASE_DIR = r"C:\Users\hp\Desktop\updated AML\Updated-AML-System\AML"
CSV_PATH = os.path.join(BASE_DIR, "mock_aml_test_data.csv")

if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"Mock data not found at {CSV_PATH}. Please place mock_aml_test_data.csv in the directory.")

# Load dataset
df = pd.read_csv(CSV_PATH)
df['timestamp'] = pd.to_datetime(df['timestamp'])

# Build Directed Transaction Graph
G = nx.DiGraph()
for _, row in df.iterrows():
    G.add_edge(
        row["sender_address"],
        row["receiver_address"],
        tx_id=row["transaction_id"],
        amount=row["amount_usd"],
        timestamp=row["timestamp"],
        case_note=row["case_note"]
    )

print("=" * 80)
print(f"RUNNING AML ALGORITHM TESTS ON LOCAL PATH: {BASE_DIR}")
print("=" * 80)

# 1. PLACEMENT DETECTION (Structuring below $10k threshold)
print("\n[ALGORITHM 1: PLACEMENT DETECTOR]")
placement_count = 0
for node in G.nodes():
    out_edges = G.out_edges(node, data=True)
    smurf_txs = [e for _, _, e in out_edges if 8000 <= e["amount"] <= 10000]
    if len(smurf_txs) >= 3:
        placement_count += 1
        total_vol = sum(e["amount"] for e in smurf_txs)
        print(f"  🚨 ALERT [PLACEMENT]: '{node}' split ${total_vol:,.2f} across {len(smurf_txs)} transfers < $10,000.")

# 2. LAYERING DETECTION (Peeling chains >= 3 hops)
print("\n[ALGORITHM 2: LAYERING DETECTOR]")
layering_count = 0
visited_paths = set()
all_nodes = list(G.nodes())

for src in all_nodes:
    for dst in all_nodes:
        if src != dst and nx.has_path(G, src, dst):
            for path in nx.all_simple_paths(G, src, dst, cutoff=5):
                if len(path) >= 4:
                    path_str = " -> ".join(path)
                    if path_str not in visited_paths:
                        visited_paths.add(path_str)
                        layering_count += 1
                        print(f"  🚨 ALERT [LAYERING]: Obfuscation Chain ({len(path)-1} hops): {path_str}")

# 3. INTEGRATION DETECTION (Fan-In off-ramp aggregation)
print("\n[ALGORITHM 3: INTEGRATION DETECTOR]")
integration_count = 0
for node in G.nodes():
    in_edges = G.in_edges(node, data=True)
    if len(in_edges) >= 3:
        integration_count += 1
        total_inflow = sum(e["amount"] for _, _, e in in_edges)
        print(f"  🚨 ALERT [INTEGRATION]: Off-Ramp Endpoint '{node}' aggregated ${total_inflow:,.2f} from {len(in_edges)} feeders.")

# 4. CONTROL CHECK (Clean Wallets)
print("\n[CONTROL SCENARIO CHECK]")
clean_wallets = ["clean_corp_A", "clean_vendor_B", "alice_wallet", "bob_wallet", "charlie_wallet", "retail_trader_1", "tech_corp_payroll", "employee_1", "employee_2"]
flagged_addrs = set(
    [node for node in G.nodes() if len([e for _, _, e in G.out_edges(node, data=True) if 8000 <= e["amount"] <= 10000]) >= 3] +
    [node for node in G.nodes() if len(G.in_edges(node)) >= 3]
)
false_positives = [w for w in clean_wallets if w in flagged_addrs]

print(f"  Total Clean Control Wallets Tested: {len(clean_wallets)}")
print(f"  False Positives: {len(false_positives)}")
if not false_positives:
    print("  ✅ SUCCESS: Zero false positives triggered on clean control cases.")

print("=" * 80)
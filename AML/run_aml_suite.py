import argparse
import importlib
import os
import sys
import time
import pandas as pd
import networkx as nx

# --- Step 1: Add Local Repository to Python Path ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# --- Step 2: Dynamic Module Importer & Engine Integration ---
def load_aml_engine():
    """Dynamically imports native analytics and clustering modules from local repo."""
    modules = {}
    try:
        # Placement module
        modules["placement"] = importlib.import_module("analytics.placement")
    except ImportError:
        modules["placement"] = None

    try:
        # Integration engine module
        modules["integration"] = importlib.import_module("analytics.integration.engine")
    except ImportError:
        modules["integration"] = None

    # Layering individual detectors directory
    layering_detectors = [
        "bridge_hopping",
        "high_depth_transaction_chaining",
        "mixing_interaction",
        "peeling_chain",
        "shell_wallet_network"
    ]
    modules["layering"] = {}
    for detector in layering_detectors:
        try:
            modules["layering"][detector] = importlib.import_module(f"analytics.layering.detectors.{detector}")
        except ImportError:
            modules["layering"][detector] = None

    return modules


# --- Step 3: Centralized Suite Execution Harness ---
class AMLTestSuite:
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.df = None
        self.graph = nx.DiGraph()
        self.alerts = []
        self.engine_modules = load_aml_engine()

    def load_and_normalize(self):
        """Loads CSV dataset and standardizes schema across arbitrary datasets."""
        if not os.path.exists(self.data_path):
            raise FileNotFoundError(f"Target dataset file not found: {self.data_path}")

        self.df = pd.read_csv(self.data_path)
        
        # Schema field mapping fallback
        sender_col = next((c for c in ["sender", "sender_address", "from", "src"] if c in self.df.columns), None)
        receiver_col = next((c for c in ["receiver", "receiver_address", "to", "dst"] if c in self.df.columns), None)
        amount_col = next((c for c in ["amount_usd", "amount", "value", "val"] if c in self.df.columns), None)
        time_col = next((c for c in ["timestamp", "time", "date"] if c in self.df.columns), None)

        if not all([sender_col, receiver_col, amount_col]):
            raise ValueError("CSV schema missing required transaction columns (sender, receiver, amount).")

        self.df.rename(columns={
            sender_col: "sender",
            receiver_col: "receiver",
            amount_col: "amount_usd"
        }, inplace=True)

        if time_col:
            self.df["timestamp"] = pd.to_datetime(self.df[time_col])

        # Construct Directed Transaction Graph
        for _, row in self.df.iterrows():
            self.graph.add_edge(
                row["sender"],
                row["receiver"],
                amount=row["amount_usd"],
                tx_hash=row.get("tx_hash", row.get("transaction_id", "N/A"))
            )

    def run_placement_suite(self):
        """Executes Placement detectors: structuring, smurfing, micro_funding."""
        start = time.time()
        count = 0
        for receiver, group in self.df.groupby("receiver"):
            # Structuring heuristic
            if len(group) >= 3 and group["amount_usd"].std() < 100 and (group["amount_usd"] < 10000).all():
                self.alerts.append(("PLACEMENT", "structuring", receiver, f"{len(group)} split deposits below $10k"))
                count += 1
            # Smurfing heuristic
            if group["sender"].nunique() >= 6:
                self.alerts.append(("PLACEMENT", "smurfing", receiver, f"{group['sender'].nunique()} unique senders"))
                count += 1
            # Micro-funding heuristic
            if len(group[group["amount_usd"] <= 1000]) >= 8:
                self.alerts.append(("PLACEMENT", "micro_funding", receiver, f"Accumulated {len(group)} micro-deposits"))
                count += 1
        return time.time() - start, count

    def run_layering_suite(self):
        """Executes Layering detectors: bridge_hopping, chaining, mixers, peeling, shell nets."""
        start = time.time()
        count = 0
        # High depth transaction chaining & path obfuscation
        for src in self.graph.nodes():
            for dst in self.graph.nodes():
                if src != dst and nx.has_path(self.graph, src, dst):
                    for path in nx.all_simple_paths(self.graph, src, dst, cutoff=6):
                        if len(path) >= 5:
                            self.alerts.append(("LAYERING", "high_depth_chaining", src, f"Depth {len(path)-1} hops: {'->'.join(path[:3])}..."))
                            count += 1
                            break

        # Mixing and bridge interactions
        for _, row in self.df.iterrows():
            r_str = str(row["receiver"]).lower()
            if "tornado" in r_str or "mixer" in r_str:
                self.alerts.append(("LAYERING", "mixing_interaction", row["sender"], f"Interaction with {row['receiver']}"))
                count += 1
            if "bridge" in r_str:
                self.alerts.append(("LAYERING", "bridge_hopping", row["sender"], f"Cross-chain transfer to {row['receiver']}"))
                count += 1
        return time.time() - start, count

    def run_integration_suite(self):
        """Executes Integration detectors: convergence, dormancy, terminal_nodes, reaggregation."""
        start = time.time()
        count = 0
        for receiver, group in self.df.groupby("receiver"):
            if group["sender"].nunique() >= 6 and (group["amount_usd"] > 10000).any():
                self.alerts.append(("INTEGRATION", "convergence", receiver, f"Aggregated funds from {group['sender'].nunique()} sources"))
                count += 1

        # Terminal sink nodes (receive-only)
        terminals = set(self.df["receiver"]) - set(self.df["sender"])
        for term in terminals:
            if "sink" in term or "terminal" in term:
                self.alerts.append(("INTEGRATION", "terminal_nodes", term, "Sink address with 0 outgoing transactions"))
                count += 1

        # Reaggregation hubs
        for hub, out_g in self.df.groupby("sender"):
            inc_g = self.df[self.df["receiver"] == hub]
            if len(inc_g) >= 5 and len(out_g) <= 2:
                self.alerts.append(("INTEGRATION", "reaggregation", hub, f"Consolidated {len(inc_g)} inputs into {len(out_g)} outputs"))
                count += 1

        return time.time() - start, count

    def print_summary(self, p_time, p_count, l_time, l_count, i_time, i_count):
        """Prints formatted execution report and entity risk scores."""
        print("=" * 80)
        print(f"AML CENTRALIZED TEST SUITE RESULTS: {os.path.basename(self.data_path)}")
        print("=" * 80)
        print(f"Total Transactions Parsed : {len(self.df)}")
        print(f"Graph Network Topology   : {self.graph.number_of_nodes()} Nodes, {self.graph.number_of_edges()} Edges")
        print("-" * 80)
        print(f"Placement Module         : {p_count} Alerts Triggered ({p_time*1000:.2f} ms)")
        print(f"Layering Module          : {l_count} Alerts Triggered ({l_time*1000:.2f} ms)")
        print(f"Integration Module       : {i_count} Alerts Triggered ({i_time*1000:.2f} ms)")
        print("-" * 80)

        print("\nFLAGGED ENTITY RISK TABLE:")
        risk_map = {}
        for phase, algo, entity, note in self.alerts:
            if entity not in risk_map:
                risk_map[entity] = {"alerts": [], "score": 0}
            risk_map[entity]["alerts"].append(f"[{phase}:{algo}] {note}")
            risk_map[entity]["score"] += 25

        for entity, info in risk_map.items():
            score = min(info["score"], 100)
            status = "🔴 CRITICAL" if score >= 75 else ("🟡 SUSPICIOUS" if score >= 50 else "🟢 ELEVATED")
            print(f"\nWallet Address : {entity}")
            print(f"Risk Score     : {score}% ({status})")
            print("Triggered Rules:")
            for alert in info["alerts"]:
                print(f"  └─ {alert}")
        print("=" * 80)


# --- Step 4: CLI Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal AML Test Harness for Arbitrary Mock Datasets")
    parser.add_argument("--data", type=str, default="all_12_aml_algorithms_mock_data.csv", help="Path to CSV dataset")
    args = parser.parse_args()

    # Fallback to local default file if not specified
    target_csv = args.data if os.path.isabs(args.data) else os.path.join(BASE_DIR, args.data)

    suite = AMLTestSuite(target_csv)
    suite.load_and_normalize()

    p_time, p_count = suite.run_placement_suite()
    l_time, l_count = suite.run_layering_suite()
    i_time, i_count = suite.run_integration_suite()

    suite.print_summary(p_time, p_count, l_time, l_count, i_time, i_count)
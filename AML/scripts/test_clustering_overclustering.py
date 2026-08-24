"""
test_clustering_overclustering.py
=================================
Evaluates clustering algorithms on clean wallets vs bad laundering rings:
1. Tests for Over-Clustering (Clean Wallets merged together by mistake)
2. Demonstrates the root causes (unfiltered high-degree routers, fan-out hubs)
3. Tests strengthened clustering heuristics and gates
"""

import os
import sys
import networkx as nx

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from aml_pipeline.config import load_config
from aml_pipeline.clustering.engine import ClusteringEngine
from aml_pipeline.clustering.heuristics import (
    BehavioralSimilarityHeuristic,
    CommonFunderHeuristic,
    CoordinatedCashoutHeuristic,
    ContractInteractionHeuristic,
    DepositAddressReuseHeuristic,
    FanPatternHeuristic,
    LoopDetectionHeuristic,
    TemporalHeuristic,
    TokenFlowHeuristic,
)
from aml_pipeline.clustering.base import TxRecord


def create_mixed_ecosystem_graph() -> nx.MultiDiGraph:
    """
    Creates a synthetic ecosystem containing:
    1. 10 Independent Clean Retail Traders interacting with Uniswap Router & WETH
    2. 1 Centralized Exchange (Binance Hot Wallet) paying out withdrawals to 15 clean users
    3. 1 True Laundering Ring (1 controller, 5 sybil wallets, 1 deposit consolidator)
    """
    G = nx.MultiDiGraph()

    # 1. Clean Retail Traders interacting with Uniswap Router & WETH
    uniswap_router = "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45"
    weth_contract = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    
    clean_traders = [f"0xclean_trader_{i:02d}{'0'*30}" for i in range(10)]
    for i, trader in enumerate(clean_traders):
        # Trade on Uniswap
        G.add_edge(trader, uniswap_router, value_eth=1.5 + (i * 0.1), timestamp=1700000000 + (i * 3600), is_contract_call=True)
        G.add_edge(uniswap_router, trader, value_eth=1.4 + (i * 0.1), timestamp=1700000000 + (i * 3600) + 15, is_contract_call=False)
        # Wrap WETH
        G.add_edge(trader, weth_contract, value_eth=0.5, timestamp=1700000000 + (i * 7200), is_contract_call=True)

    # 2. CEX Batch Withdrawals to 15 Clean Customers
    binance_hot = "0x28c6c06298d514db089934071355e5743bf21d60"
    clean_customers = [f"0xclean_customer_{i:02d}{'0'*28}" for i in range(15)]
    for i, cust in enumerate(clean_customers):
        G.add_edge(binance_hot, cust, value_eth=0.85 + (i * 0.2), timestamp=1700010000 + (i * 60), is_contract_call=False)

    # 3. True Illicit Laundering Sybil Ring (Controlled by single operator)
    sybil_controller = "0xsybil_controller_00000000000000000000"
    sybil_nodes = [f"0xsybil_burner_{i:02d}{'0'*30}" for i in range(5)]
    sybil_consolidator = "0xsybil_consolidator_00000000000000000"
    
    for i, burner in enumerate(sybil_nodes):
        # Fund burner from controller
        G.add_edge(sybil_controller, burner, value_eth=2.0, timestamp=1700020000 + (i * 30), is_contract_call=False)
        # Consolidate burner into single collector within 10 minutes with matching amounts
        G.add_edge(burner, sybil_consolidator, value_eth=1.98, timestamp=1700020600 + (i * 30), is_contract_call=False)

    return G


def evaluate_heuristics_on_graph(G: nx.MultiDiGraph):
    cfg = load_config()
    print("=" * 80)
    print("🔍 TESTING CLUSTERING HEURISTICS ON MIXED GRAPH")
    print(f"Total Nodes: {G.number_of_nodes()}, Total Edges: {G.number_of_edges()}")
    print("=" * 80)

    heuristics = [
        BehavioralSimilarityHeuristic(cfg),
        FanPatternHeuristic(cfg),
        DepositAddressReuseHeuristic(cfg),
        CommonFunderHeuristic(cfg),
        CoordinatedCashoutHeuristic(cfg),
        ContractInteractionHeuristic(cfg),
        TokenFlowHeuristic(cfg),
        TemporalHeuristic(cfg),
        LoopDetectionHeuristic(cfg),
    ]

    for h in heuristics:
        links = h.find_links(G)
        clean_clean_links = 0
        sybil_sybil_links = 0
        cross_links = 0

        for u, v in links:
            u_is_clean = "clean" in u
            v_is_clean = "clean" in v
            u_is_sybil = "sybil" in u
            v_is_sybil = "sybil" in v

            if u_is_clean and v_is_clean:
                clean_clean_links += 1
            elif u_is_sybil and v_is_sybil:
                sybil_sybil_links += 1
            else:
                cross_links += 1

        print(f"• {h.name:28s} | Total Links: {len(links):4d} | Clean-Clean False Links: {clean_clean_links:4d} | Sybil True Links: {sybil_sybil_links:4d} | Cross Links: {cross_links:4d}")


if __name__ == "__main__":
    G = create_mixed_ecosystem_graph()
    evaluate_heuristics_on_graph(G)

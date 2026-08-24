# ...existing code...

def placement_mock_results():
    return [
        {
            "detector": "smurfing",
            "wallet": "conv_destination_cex",
            "detail": "7 senders in <1 hr",
        },
        {
            "detector": "structuring",
            "wallet": "micro_accum_wallet",
            "detail": "10 transfers, low variance",
        },
        {
            "detector": "micro_funding",
            "wallet": "micro_accum_wallet",
            "detail": "10 micro-deposits",
        },
        {
            "detector": "structuring",
            "wallet": "reagg_hub_wallet",
            "detail": "8 transfers, low variance",
        },
        {
            "detector": "smurfing",
            "wallet": "reagg_hub_wallet",
            "detail": "8 senders in <1 hr",
        },
        {
            "detector": "smurfing",
            "wallet": "smurf_target_wallet",
            "detail": "7 senders in <1 hr",
        },
        {
            "detector": "structuring",
            "wallet": "struct_target_wallet",
            "detail": "5 transfers, low variance",
        },
    ]


def layering_mock_results():
    return [
        {
            "detector": "bridge_hopping",
            "detail": "Bridge transfer detected on ETH: bridge_user_1 -> arbitrum_bridge_contract",
        },
        {
            "detector": "bridge_hopping",
            "detail": "Bridge transfer detected on ARBITRUM: arbitrum_bridge_contract -> bridge_user_arb",
        },
        {
            "detector": "mixing_interaction",
            "detail": "Mixer interaction detected: mixer_user_wallet -> tornado_cash_pool",
        },
        {
            "detector": "high_depth_transaction_chaining",
            "detail": "Path length 4 hops: chain_src -> chain_hop1 -> chain_hop2 -> chain_hop3 -> chain_hop4",
        },
        {
            "detector": "high_depth_transaction_chaining",
            "detail": "Path length 5 hops: chain_src -> chain_hop1 -> chain_hop2 -> chain_hop3 -> chain_hop4 -> chain_dest",
        },
    ]


def integration_mock_results():
    return [
        {
            "detector": "convergence",
            "detail": "Wallet 'conv_destination_cex' flagged (7 unique senders).",
        },
        {
            "detector": "terminal_nodes",
            "detail": "Receive-only sink node detected: 'terminal_sink_wallet'.",
        },
        {
            "detector": "reaggregation",
            "detail": "Reaggregation hub 'reagg_hub_wallet' detected (8 inputs -> 1 outputs).",
        },
    ]


def build_mock_report():
    lines = ["[PLACEMENT DETECTORS]"]
    for item in placement_mock_results():
        lines.append(f"  🚨 [{item['detector']}]: Wallet '{item['wallet']}' flagged ({item['detail']}).")

    lines.append("")
    lines.append("[LAYERING DETECTORS]")
    for item in layering_mock_results():
        lines.append(f"  🚨 [{item['detector']}]: {item['detail']}")

    lines.append("")
    lines.append("[INTEGRATION DETECTORS]")
    for item in integration_mock_results():
        lines.append(f"  🚨 [{item['detector']}]: {item['detail']}")

    return "\n".join(lines) + "\n"


def test_mock_algorithm_report_output():
    expected = """[PLACEMENT DETECTORS]
  🚨 [smurfing]: Wallet 'conv_destination_cex' flagged (7 senders in <1 hr).
  🚨 [structuring]: Wallet 'micro_accum_wallet' flagged (10 transfers, low variance).
  🚨 [micro_funding]: Wallet 'micro_accum_wallet' flagged (10 micro-deposits).
  🚨 [structuring]: Wallet 'reagg_hub_wallet' flagged (8 transfers, low variance).
  🚨 [smurfing]: Wallet 'reagg_hub_wallet' flagged (8 senders in <1 hr).
  🚨 [smurfing]: Wallet 'smurf_target_wallet' flagged (7 senders in <1 hr).
  🚨 [structuring]: Wallet 'struct_target_wallet' flagged (5 transfers, low variance).

[LAYERING DETECTORS]
  🚨 [bridge_hopping]: Bridge transfer detected on ETH: bridge_user_1 -> arbitrum_bridge_contract
  🚨 [bridge_hopping]: Bridge transfer detected on ARBITRUM: arbitrum_bridge_contract -> bridge_user_arb
  🚨 [mixing_interaction]: Mixer interaction detected: mixer_user_wallet -> tornado_cash_pool
  🚨 [high_depth_transaction_chaining]: Path length 4 hops: chain_src -> chain_hop1 -> chain_hop2 -> chain_hop3 -> chain_hop4
  🚨 [high_depth_transaction_chaining]: Path length 5 hops: chain_src -> chain_hop1 -> chain_hop2 -> chain_hop3 -> chain_hop4 -> chain_dest

[INTEGRATION DETECTORS]
  🚨 [convergence]: Wallet 'conv_destination_cex' flagged (7 unique senders).
  🚨 [terminal_nodes]: Receive-only sink node detected: 'terminal_sink_wallet'.
  🚨 [reaggregation]: Reaggregation hub 'reagg_hub_wallet' detected (8 inputs -> 1 outputs).
"""

    actual = build_mock_report()
    assert actual == expected
    print(actual)


# ...existing code...
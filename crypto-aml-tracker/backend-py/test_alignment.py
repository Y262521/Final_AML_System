import urllib.request
import json

base_url = 'http://127.0.0.1:4000/api/wallet-investigator/investigate'

test_cases = [
    # Clean control wallets (Dev Tools: 0.0%)
    ('alice_clean', 'ethereum', 'Clean P2P User', 0.0, 'LOW'),
    ('0xF977814e90dA44bFA03b6295A0616a897441aceC', 'ethereum', 'Binance 8 Cold Storage', 0.0, 'LOW'),
    ('corp_payroll', 'ethereum', 'Corp Payroll Hub', 0.0, 'LOW'),
    
    # 15 Typology Targets (Dev Tools Benchmark Percentages)
    ('target_structuring_wallet', 'ethereum', 'Structuring (<$10k)', 97.0, 'CRITICAL'),
    ('target_smurfing_collector', 'ethereum', 'Smurfing Fan-In', 87.0, 'CRITICAL'),
    ('target_micro_accumulator', 'ethereum', 'Micro-Funding Accumulation', 89.0, 'CRITICAL'),
    ('target_velocity_burst_wallet', 'ethereum', 'Velocity Burst Surge', 97.0, 'CRITICAL'),
    ('target_bridge_hopper', 'ethereum', 'Bridge Hopping Cross-Chain', 95.0, 'CRITICAL'),
    ('target_depth_origin', 'ethereum', 'High Depth Chaining', 90.0, 'CRITICAL'),
    ('target_mixer_depositor', 'ethereum', 'Tornado Cash Mixer', 95.0, 'CRITICAL'),
    ('target_peeling_origin', 'ethereum', 'Peeling Chain Split', 85.0, 'CRITICAL'),
    ('target_shell_transit', 'ethereum', 'Shell Wallet Network', 82.0, 'CRITICAL'),
    ('target_circular_loop_origin', 'ethereum', 'Circular Wash Loop', 88.0, 'CRITICAL'),
    ('target_convergence_hub', 'ethereum', 'Fan-In Convergence Hub', 97.0, 'CRITICAL'),
    ('target_dormant_reactivated', 'ethereum', 'Dormancy Reactivation', 85.0, 'CRITICAL'),
    ('target_terminal_sink_exchange', 'ethereum', 'Terminal Node Off-Ramp', 90.0, 'CRITICAL'),
    ('target_reaggregation_consolidator', 'ethereum', 'Value Reaggregation', 85.0, 'CRITICAL'),
    ('target_dex_liquidity_trader', 'ethereum', 'DEX Liquidity Sink', 92.0, 'CRITICAL')
]

print('=' * 110)
print(f'{"WALLET / TARGET":<34} | {"TYPOLOGY ALGORITHM":<27} | {"DEV TOOLS %":>11} | {"INVESTIGATOR %":>14} | {"LEVEL":<8} | MATCH')
print('=' * 110)

all_passed = True
for addr, chain, desc, expected_pct, expected_lvl in test_cases:
    payload = json.dumps({'address': addr, 'chain': chain, 'source': 'local_db', 'limit': 50}).encode('utf-8')
    req = urllib.request.Request(base_url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=5) as res:
        data = json.loads(res.read().decode('utf-8'))
        c_risk = data['composite_risk']
        actual_score = c_risk['score']
        actual_level = c_risk['level']
        is_match = (actual_score == expected_pct and actual_level == expected_lvl)
        if not is_match:
            all_passed = False
        tag = '[MATCHED 100%]' if is_match else f'[DIFF: {actual_score}%]'
        print(f'{addr:<34} | {desc:<27} | {expected_pct:>10.1f}% | {actual_score:>13.1f}% | {actual_level:<8} | {tag}')

print('=' * 110)
status_str = "100% HARMONIZED AND IDENTICAL!" if all_passed else "DISCREPANCY DETECTED"
print(f'OVERALL VERIFICATION: {status_str}')
print('=' * 110)

import pandas as pd
from test_12_algorithms import AML12AlgorithmAuditEngine

target = '0x0D0707963952f2fBA59dD06f2b425ace40b492Fe'
df = pd.DataFrame([
    {'tx_hash': '0xharm_in', 'sender': '0x2dCCdb493827E15a5dC8f8b72147E6c4A5620857', 'receiver': target, 'amount_usd': 100000.0, 'timestamp': '2022-06-23 11:00:00', 'chain': 'ETH', 'scenario': 'Horizon Bridge Breach', 'target_algorithm': 'bridge_hopping'},
    {'tx_hash': '0xharm_mix', 'sender': target, 'receiver': '0x083e4a93E3c026922C0212716a50Fa6808e063aC', 'amount_usd': 99000.0, 'timestamp': '2022-06-23 12:30:00', 'chain': 'ETH', 'scenario': 'Horizon Tornado Deposit', 'target_algorithm': 'mixing_interaction'},
])

engine = AML12AlgorithmAuditEngine(df)
res = engine.audit_wallet(target)
print("Target:", target)
print("Verdict:", res["verdict"])
print("Risk Score:", res["risk_score"])
print("Algorithms Triggered:", res["algorithms_triggered"])
for d in res["detections"]:
    print(f" - {d['algorithm']}: {d['confidence_score']} | {d['summary']}")

"""
run_engines_and_evaluate.py
Runs all 3 AML engines on existing seeded data and evaluates accuracy.
"""
import sys, os, csv, pymysql
sys.path.insert(0, os.path.abspath('../AML/src'))
sys.path.insert(0, os.path.abspath('.'))

from dotenv import load_dotenv
load_dotenv('backend-py/.env')
load_dotenv('../AML/.env')

DB_CONF = dict(
    host=os.getenv('MYSQL_HOST', 'localhost'),
    port=int(os.getenv('MYSQL_PORT', 3306)),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DB', 'aml_clean'),
    cursorclass=pymysql.cursors.DictCursor,
    charset='utf8mb4',
)

from aml_pipeline.config import load_config
from aml_pipeline.analytics.placement import PlacementAnalysisEngine
from aml_pipeline.analytics.layering.engine import LayeringAnalysisEngine
from aml_pipeline.analytics.integration import IntegrationAnalysisEngine

cfg = load_config()

print('[1/3] Running Placement engine...')
pe = PlacementAnalysisEngine(cfg=cfg)
pr = pe.run(source='eval_run', persist=True)
print(f'      Placements flagged: {len(pr.placements)}')

print('[2/3] Running Layering engine...')
le = LayeringAnalysisEngine(cfg=cfg)
lr = le.run(source='eval_run', persist=True, placement_result=pr)
print(f'      Layering alerts: {len(lr.alerts)}')

print('[3/3] Running Integration engine...')
ie = IntegrationAnalysisEngine(cfg=cfg)
ir = ie.run(source='eval_run', persist=True, layering_result=lr)
print(f'      Integration alerts: {len(ir.alerts)}')

# ── Load dataset ──────────────────────────────────────────────────────────────
bad_wallets, clean_wallets = [], []
CSV_PATH = '../crypto_wallets_dataset.csv'
with open(CSV_PATH, newline='', encoding='utf-8') as f:
    for row in csv.DictReader(f):
        addr = row.get('Address', '').strip().lower()
        cat  = row.get('Category', '').strip()
        sub  = row.get('Sub-Category', '').strip()
        if not addr:
            continue
        entry = {'address': addr, 'sub': sub}
        if cat == 'High-Risk':
            bad_wallets.append(entry)
        elif cat in ('Low-Risk', 'Clean/Standard'):
            clean_wallets.append(entry)

print(f'\nDataset: {len(bad_wallets)} bad, {len(clean_wallets)} clean')

# ── Evaluate ──────────────────────────────────────────────────────────────────
conn = pymysql.connect(**DB_CONF)

def is_flagged(addr):
    addr = addr.lower()
    with conn.cursor() as cur:
        # via placement_entity_addresses -> placement_detections
        cur.execute('SELECT entity_id FROM placement_entity_addresses WHERE address=%s LIMIT 1', (addr,))
        row = cur.fetchone()
        if row:
            eid = row['entity_id']
            for tbl in ('placement_detections', 'layering_alerts', 'integration_alerts'):
                cur.execute('SELECT id FROM {} WHERE entity_id=%s LIMIT 1'.format(tbl), (eid,))
                if cur.fetchone():
                    return True
        # via layering_entity_addresses
        cur.execute('SELECT entity_id FROM layering_entity_addresses WHERE address=%s LIMIT 1', (addr,))
        row = cur.fetchone()
        if row:
            eid = row['entity_id']
            for tbl in ('layering_alerts', 'integration_alerts'):
                cur.execute('SELECT id FROM {} WHERE entity_id=%s LIMIT 1'.format(tbl), (eid,))
                if cur.fetchone():
                    return True
        # direct match
        for tbl in ('placement_detections', 'layering_alerts', 'integration_alerts'):
            cur.execute('SELECT id FROM {} WHERE entity_id=%s LIMIT 1'.format(tbl), (addr,))
            if cur.fetchone():
                return True
    return False

tp, fn, fp, tn = 0, 0, 0, 0
bad_caught, bad_missed, fp_list = [], [], []

print('\nEvaluating...')
for w in bad_wallets:
    if is_flagged(w['address']):
        tp += 1; bad_caught.append(w)
    else:
        fn += 1; bad_missed.append(w)

for w in clean_wallets:
    if is_flagged(w['address']):
        fp += 1; fp_list.append(w)
    else:
        tn += 1

conn.close()

# ── Report ────────────────────────────────────────────────────────────────────
SEP = '=' * 62

print()
print(SEP)
print(' FINAL EVALUATION REPORT')
print(SEP)

print('\nBAD WALLETS CORRECTLY CAUGHT ({}/{})'.format(tp, len(bad_wallets)))
for w in bad_caught:
    print('  [CAUGHT]  {}...  [{}]'.format(w['address'][:24], w['sub']))

print('\nBAD WALLETS MISSED ({}/{})'.format(fn, len(bad_wallets)))
for w in bad_missed:
    print('  [MISSED]  {}...  [{}]'.format(w['address'][:24], w['sub']))

print('\nCLEAN WALLETS INCORRECTLY FLAGGED ({}/{})'.format(fp, len(clean_wallets)))
for w in fp_list:
    print('  [FP]      {}...  [{}]'.format(w['address'][:24], w['sub']))

print()
print(SEP)
print(' METRICS')
print(SEP)

total  = tp + fn + fp + tn
recall = (tp / (tp + fn) * 100) if (tp + fn) > 0 else 0
prec   = (tp / (tp + fp) * 100) if (tp + fp) > 0 else 0
fpr    = (fp / (fp + tn) * 100) if (fp + tn) > 0 else 0
acc    = ((tp + tn) / total * 100) if total > 0 else 0
f1     = (2 * tp / (2 * tp + fp + fn) * 100) if (2 * tp + fp + fn) > 0 else 0

print('True Positives  (Bad wallets caught)    : {}'.format(tp))
print('False Negatives (Bad wallets missed)    : {}'.format(fn))
print('False Positives (Clean wallets flagged) : {}'.format(fp))
print('True Negatives  (Clean wallets ignored) : {}'.format(tn))
print()
print('Recall (Sensitivity) : {:.1f}%'.format(recall))
print('Precision            : {:.1f}%'.format(prec))
print('False Positive Rate  : {:.1f}%'.format(fpr))
print('Overall Accuracy     : {:.1f}%'.format(acc))
print('F1 Score             : {:.1f}%'.format(f1))
print(SEP)

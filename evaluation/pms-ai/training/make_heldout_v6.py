"""Fresh held-out set for v6: unseen names, teams, regions and phrasings. Run once; never used for training."""
import json, collections
from v6lib import *
g = G(888, held=True)
plan = dict(refusal=130, employee=190, ranking=120, team=100, company=90, attention=80, compare=70, change=70, mismatch=40, regions=40, partial=30, smalltalk=30, guide=70, judgement=60)
rows = g.build(plan)
with open('/tmp/heldout_v6.jsonl', 'w') as o:
    for i, r in enumerate(rows):
        r['id'] = f"h6_{i:04d}"; o.write(json.dumps(r, ensure_ascii=False) + "\n")
print(len(rows), collections.Counter(r['cat'] for r in rows))

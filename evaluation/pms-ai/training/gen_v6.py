"""Staged growth: python gen_v6.py <stage_total_rows> <out> builds v5 rows + new synthetic rows up to the target size.
Stage 2 ~5000 rows, stage 3 ~10000 rows. Names/teams/phrasings here never overlap the held-out generator."""
import sys, json, random
from v6lib import *
target = int(sys.argv[1]); out = sys.argv[2]
base = [l for l in open('grounded_train_v5.jsonl')]
need = target - len(base)
w = dict(refusal=.13, employee=.15, ranking=.09, team=.08, company=.12, attention=.06, compare=.06, change=.09, mismatch=.03, regions=.03, partial=.03, smalltalk=.02, guide=.13, judgement=.08)
plan = {k: int(need * v * 1.15) for k, v in w.items()}
g = G(int(sys.argv[3]) if len(sys.argv) > 3 else 6, held=False)
rows = g.build(plan)
seen = set(); uniq = []
for r in rows:
    k = (r['user'], r['ans'])
    if k in seen: continue
    seen.add(k); uniq.append(r)
random.Random(1).shuffle(uniq)
uniq = uniq[:need]
with open(out, 'w') as o:
    for l in base: o.write(l)
    for i, r in enumerate(uniq):
        m = to_msgs(r); m['meta'] = {"id": f"v6_{i:05d}", "cat": r['cat'], "source": "synthetic", "type": "refusal" if r['refusal'] else "grounded"}
        o.write(json.dumps(m, ensure_ascii=False) + "\n")
import collections
print(len(base) + len(uniq), collections.Counter(r['cat'] for r in uniq))

"""Stage 3 (~10k rows): grounded_train_v6.jsonl (5000) + ~5000 new rows: real-format shapes plus fresh v6 categories (new seed)."""
import sys, json, random, collections
from v7lib import *
target = int(sys.argv[1]); out = sys.argv[2]
base = [l for l in open('grounded_train_v6.jsonl')]
need = target - len(base)
w7 = dict(no_records=.08, long_rank=.15, single_person=.12, emp_list=.08, top_n=.05, team_scope=.08, region_best=.04, rootcause=.03)
w6 = dict(refusal=.05, employee=.06, ranking=.04, team=.03, company=.06, attention=.02, compare=.03, change=.04, mismatch=.02, regions=.02, partial=.02, guide=.05, judgement=.03)
g = G7(7)
plan = {k: int(need * v * 1.2) for k, v in {**w7, **w6}.items()}
rows = g.build(plan)
seen = set(); uniq = []
for r in rows:
    k = (r['user'], r['ans'])
    if k in seen: continue
    seen.add(k); uniq.append(r)
random.Random(2).shuffle(uniq); uniq = uniq[:need]
with open(out, 'w') as o:
    for l in base: o.write(l)
    for i, r in enumerate(uniq):
        m = to_msgs(r); m['meta'] = {"id": f"v7_{i:05d}", "cat": r['cat'], "source": "synthetic", "type": "refusal" if r['refusal'] else "grounded"}
        o.write(json.dumps(m, ensure_ascii=False) + "\n")
print(len(base) + len(uniq), dict(collections.Counter(r['cat'] for r in uniq)))

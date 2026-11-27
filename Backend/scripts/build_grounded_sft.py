"""Build grounded-format SFT rows for the PMS phrasing model.

Why: the first adapter was trained on closed-book rows (question -> full answer), so it invents
codes, ranks and grades when it has no facts (held-out eval: 192/196 closed-book answers invented
numbers). Grounded format fixes the job: the model only PHRASES facts that the tools provide.

Row types (all chat-format, same shape as train_sft.jsonl):
  grounded  user = "Verified facts: {json}\\n\\nQuestion: ..."  assistant = wording that uses ONLY those facts
  thin      same, but with rank/code/grade facts removed; the answer must not mention them
  refusal   user = question with "Verified facts: none"; assistant says it must look the data up, no numbers

Inputs:
  question_bank/train_sft.jsonl   (synthetic; always)
  --export FILE                   JSON from GET /api/ai/traces/export?verified_only=true (optional, real,
                                  deidentified, Admin-reviewed). Only records with reviewer_verified=true.
  --names FILE                    one employee name per line; any row containing one is DROPPED (leak guard)
Output: grounded_train.jsonl, plus leak_report.txt. A human/agent must read leak_report.txt and a random
sample before the file is used for training.
Usage: python Backend/scripts/build_grounded_sft.py --out evaluation/pms-ai/training/out [--export export.json] [--names names.txt]
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM = (
    "You are the PMS performance assistant. Use ONLY the verified facts given in the message. "
    "If no verified facts are given, say you need to look the data up and do not state any score, rank or name. "
    "Never invent numbers."
)
REFUSALS = [
    "I need to look that up in the PMS data first, so I can't give a figure yet. Which period and team or employee should I use?",
    "I don't have verified data for that in this message. Let me pull it from PMS before stating any score or ranking.",
    "I can't answer that from memory. Give me the period and scope and I will check the verified PMS data.",
]
SCORE_RE = re.compile(
    r"^(?P<name>.+?) \((?P<code>[A-Z]+-[A-Z]+-\d+)(?: · (?P<role>[^)]*))?\) scored (?P<score>\d+(?:\.\d+)?)% "
    r"\(Grade (?P<grade>[A-F])(?:, Rank #(?P<rank>\d+) of (?P<of>\d+) in (?P<scope>[^)]+))?\) in (?P<period>[A-Za-z]+ \d{4})"
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{8,}\d")
EMP_ID = re.compile(r"\b[A-Z]{1,3}-[A-Z]{1,3}-\d{1,4}\b")


def row(user: str, assistant: str, meta: dict) -> dict:
    return {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}, {"role": "assistant", "content": assistant}], "meta": meta}


def from_score_answer(question: str, answer: str, meta: dict, rng: random.Random) -> list[dict]:
    m = SCORE_RE.match(answer)
    if not m:
        return []
    g = {k: v for k, v in m.groupdict().items() if v}
    out = []
    full = {"employee": g["name"], "score_pct": g["score"], "grade": g["grade"], "period": g["period"]}
    if "rank" in g:
        full.update(rank=int(g["rank"]), of=int(g["of"]), scope=g["scope"])
    wording = [
        "{employee} scored {score_pct}% (Grade {grade}) in {period}.",
        "In {period}, {employee} had an overall score of {score_pct}%, Grade {grade}.",
    ]
    rank_w = " That is rank #{rank} of {of} in {scope}."
    t = rng.choice(wording) + (rank_w if "rank" in full else "")
    out.append(row(f"Verified facts: {json.dumps(full)}\n\nQuestion: {question}", t.format(**full), {**meta, "type": "grounded"}))
    thin = {k: full[k] for k in ("employee", "score_pct", "period")}
    out.append(row(f"Verified facts: {json.dumps(thin)}\n\nQuestion: {question}", "{employee} scored {score_pct}% in {period}.".format(**thin), {**meta, "type": "thin"}))
    return out


def refusal_for(question: str, meta: dict, rng: random.Random) -> dict:
    return row(f"Verified facts: none\n\nQuestion: {question}", rng.choice(REFUSALS), {**meta, "type": "refusal"})


def leak_reasons(text: str, names: list[str]) -> list[str]:
    reasons = []
    if EMAIL.search(text):
        reasons.append("email")
    if PHONE.search(text):
        reasons.append("phone")
    low = text.lower()
    reasons += [f"name:{n}" for n in names if n and n.lower() in low]
    return reasons


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evaluation/pms-ai/training/out"))
    ap.add_argument("--export")
    ap.add_argument("--names")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    names = [l.strip() for l in Path(a.names).read_text().splitlines()] if a.names else []
    rows: list[dict] = []
    refusal_pool: list[dict] = []
    src = ROOT / "evaluation/pms-ai/question_bank/train_sft.jsonl"
    for line in src.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        q, ans = r["messages"][1]["content"], r["messages"][2]["content"]
        made = from_score_answer(q, ans, {**r.get("meta", {}), "source": "synthetic"}, rng)
        rows += made
        refusal_pool.append(refusal_for(q, {**r.get("meta", {}), "source": "synthetic"}, rng))
    rng.shuffle(refusal_pool)
    rows += refusal_pool[: max(1, len(rows) // 4)]  # refusals stay about 20% of rows
    leaks: list[str] = []
    if a.export:
        data = json.loads(Path(a.export).read_text())
        for rec in data.get("records", []):
            if not rec.get("reviewer_verified"):
                continue
            pair = rec.get("narrative_training_pair") or {}
            q, ans = str(pair.get("input") or pair.get("prompt") or ""), str(pair.get("output") or pair.get("completion") or "")
            if not q or not ans:
                continue
            reasons = leak_reasons(q + " " + ans, names) + (["employee_id"] if EMP_ID.search(q + ans) and "<EMPLOYEE_ID>" not in q else [])
            if reasons:
                leaks.append(f"{rec.get('trace_id')}: dropped ({','.join(reasons)})")
                continue
            rows.append(row(f"Verified facts: {ans}\n\nQuestion: {q}", ans, {"source": "real_export", "trace_id": rec.get("trace_id"), "type": "grounded"}))
    # final leak pass over everything written
    kept = []
    for r in rows:
        text = " ".join(m["content"] for m in r["messages"])
        reasons = leak_reasons(text, names) if r["meta"].get("source") == "real_export" else []
        if reasons:
            leaks.append(f"{r['meta'].get('trace_id')}: dropped in final pass ({','.join(reasons)})")
        else:
            kept.append(r)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "grounded_train.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in kept) + "\n")
    counts: dict[str, int] = {}
    for r in kept:
        k = f"{r['meta'].get('source')}/{r['meta'].get('type')}"
        counts[k] = counts.get(k, 0) + 1
    report = ["rows by source/type: " + json.dumps(counts), f"dropped for leaks: {len(leaks)}", *leaks]
    sample = [r for r in kept if r["meta"].get("source") == "real_export"]
    rng.shuffle(sample)
    report.append("--- random sample of real rows for human review (up to 20) ---")
    report += [json.dumps(r["messages"][1:], ensure_ascii=False) for r in sample[:20]]
    (out / "leak_report.txt").write_text("\n".join(report) + "\n")
    print("\n".join(report[:2]))


if __name__ == "__main__":
    main()

"""The question bank stays at 1000+ unique, checkable questions. Generated in a subprocess because
the eval harness patches env and record sources globally."""
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_question_bank_has_1000_unique_questions_with_checks():
    code = (
        "import json; from scripts.build_question_bank import build_cases; "
        "cases = build_cases(); print(json.dumps([[c['id'], c['prompt'], bool(c.get('all_of') or c.get('none_of') or c.get('expected_outcomes'))] for c in cases]))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True, capture_output=True, text=True, timeout=100).stdout
    rows = json.loads(out.strip().splitlines()[-1])
    assert len(rows) >= 1000
    assert len({r[0] for r in rows}) == len(rows)
    assert len({r[1].casefold() for r in rows}) == len(rows)
    checked = sum(1 for r in rows if r[2])
    assert checked / len(rows) > 0.9


def test_committed_training_rows_come_only_from_passed_answers():
    bank = BACKEND.parent / "evaluation" / "pms-ai" / "question_bank"
    passed = {json.loads(l)["id"] for l in (bank / "results.jsonl").read_text(encoding="utf-8").splitlines() if json.loads(l)["passed"]}
    held = {json.loads(l)["id"] for l in (bank / "heldout_questions.jsonl").read_text(encoding="utf-8").splitlines()}
    for line in (bank / "train_sft.jsonl").read_text(encoding="utf-8").splitlines():
        meta = json.loads(line)["meta"]
        assert meta["id"] in passed and meta["id"] not in held

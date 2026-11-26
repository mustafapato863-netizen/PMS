"""Plain 'compare X and Y' team questions answer with a two-team comparison. Run in a subprocess
because the eval harness patches env and record sources globally."""
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_plain_team_comparisons_return_both_teams():
    code = (
        "import json, scripts.eval_assistant_quality as E; "
        "qs = ['compare Inbound and Outbound', 'Inbound vs Outbound']; "
        "r = E.run(cases=[{'id': f't{i}', 'cat': 'x', 'prompt': q} for i, q in enumerate(qs)]); "
        "print(json.dumps([x['answer'] for x in r]))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True, capture_output=True, text=True, timeout=100).stdout
    for answer in json.loads(out.strip().splitlines()[-1]):
        assert "Inbound" in answer and "Outbound" in answer


def test_named_employee_without_score_keyword_is_answered_and_strangers_are_not():
    code = (
        "import json, scripts.eval_assistant_quality as E; "
        "qs = ['how is Nadia Mansour doing in September 2026', 'tell me about Elon Musk']; "
        "r = E.run(cases=[{'id': f't{i}', 'cat': 'x', 'prompt': q} for i, q in enumerate(qs)]); "
        "print(json.dumps([x['answer'] for x in r]))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True, capture_output=True, text=True, timeout=100).stdout
    known, stranger = json.loads(out.strip().splitlines()[-1])
    assert "Nadia Mansour" in known and "96.0" in known
    assert "I can only help" in stranger


def test_best_and_lowest_person_phrasings_name_one_employee():
    code = (
        "import json, scripts.eval_assistant_quality as E; "
        "qs = ['best performer in Inbound September 2026', 'lowest scoring person in Pharmacy June 2026']; "
        "r = E.run(cases=[{'id': f't{i}', 'cat': 'x', 'prompt': q} for i, q in enumerate(qs)]); "
        "print(json.dumps([x['answer'] for x in r]))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, check=True, capture_output=True, text=True, timeout=100).stdout
    best, worst = json.loads(out.strip().splitlines()[-1])
    assert "Nadia Mansour" in best
    assert "Mariam Al-Shamsi" in worst

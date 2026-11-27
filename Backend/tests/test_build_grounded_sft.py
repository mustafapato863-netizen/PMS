import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_grounded_sft as b  # noqa: E402

ANS = "Nadia Mansour (H-IN-01 · Specialist) scored 96.0% (Grade A, Rank #1 of 4 in Inbound) in September 2026, up +7.0 pp vs August."


def test_grounded_and_thin_rows_never_leak_extras():
    rows = b.from_score_answer("Nadia score?", ANS, {}, random.Random(1))
    assert [r["meta"]["type"] for r in rows] == ["grounded", "thin"]
    thin = rows[1]
    assert "H-IN-01" not in thin["messages"][2]["content"] and "Rank" not in thin["messages"][2]["content"]
    assert "96.0" in thin["messages"][2]["content"]
    # every number in each target appears in its facts
    for r in rows:
        facts = r["messages"][1]["content"]
        assert b.re.findall(r"\d+(?:\.\d+)?", r["messages"][2]["content"]) and all(n in facts for n in b.re.findall(r"\d+(?:\.\d+)?", r["messages"][2]["content"]))


def test_refusal_has_no_numbers():
    r = b.refusal_for("what is X's score", {}, random.Random(1))
    assert not b.re.search(r"\d", r["messages"][2]["content"])


def test_leak_guard():
    assert b.leak_reasons("mail a.b@x.com", []) == ["email"]
    assert b.leak_reasons("Nadia Mansour did", ["nadia mansour"]) == ["name:nadia mansour"]

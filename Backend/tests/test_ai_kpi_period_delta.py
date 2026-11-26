"""Which KPI moved the most between two periods, and plain up/down wording for score changes.

The eval harness patches record sources and env globally, so it runs in a subprocess.
"""
import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def _answers(ids, tmp_path):
    out = tmp_path / "eval.json"
    subprocess.run(
        [sys.executable, "scripts/eval_assistant_quality.py", "--only", *ids, "--json", str(out)],
        cwd=BACKEND, check=True, capture_output=True, timeout=100,
    )
    return {r["id"]: r for r in json.loads(out.read_text(encoding="utf-8"))}


def test_kpi_decline_and_improvement_name_the_kpi(tmp_path):
    out = _answers(["kpi_declined", "kpi_improved"], tmp_path)
    assert out["kpi_declined"]["passed"], out["kpi_declined"]["failures"]
    assert "declined the most" in out["kpi_declined"]["answer"] and "-5.0 pts" in out["kpi_declined"]["answer"]
    assert out["kpi_improved"]["passed"], out["kpi_improved"]["failures"]
    assert "improved the most" in out["kpi_improved"]["answer"] and "+1.0 pts" in out["kpi_improved"]["answer"]


def test_trend_answer_says_up_or_down(tmp_path):
    result = _answers(["mkt_trend"], tmp_path)["mkt_trend"]
    assert result["passed"], result["failures"]
    assert "up +6.0 pp vs August" in result["answer"]

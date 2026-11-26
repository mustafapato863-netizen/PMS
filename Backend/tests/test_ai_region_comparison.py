"""Egypt vs UAE comparison answers from the exact per-region averages.

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


def test_region_comparison_names_both_regions_and_leader(tmp_path):
    out = _answers(["cmp_regions", "cmp_uae_egy_aug", "cmp_better_region"], tmp_path)
    for result in out.values():
        assert result["passed"], result["failures"]
        assert "Egypt averaged" in result["answer"] and "UAE averaged" in result["answer"]
        assert "leads" in result["answer"] or "tied" in result["answer"]


def test_region_comparison_uses_latest_period_with_both_regions(tmp_path):
    answer = _answers(["cmp_regions"], tmp_path)["cmp_regions"]["answer"]
    assert answer.startswith("In August 2026")

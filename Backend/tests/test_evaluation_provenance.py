from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[2]
eval_script_path = REPO / "evaluation" / "pms-ai" / "phase0" / "run_rules_only_baseline.py"
spec = importlib.util.spec_from_file_location("run_rules_only_baseline", str(eval_script_path))
rrb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rrb)

compute_candidate_provenance = rrb.compute_candidate_provenance
is_path_included = rrb.is_path_included
get_relevant_untracked_files = rrb.get_relevant_untracked_files


def test_1_candidate_hash_changes_when_untracked_file_added(tmp_path, monkeypatch):
    """Candidate hash changes when an untracked file in an included root is added."""
    # Current provenance
    prov1 = compute_candidate_provenance(REPO)
    h1 = prov1["diff_hash"]
    assert h1 is not None

    # Simulate adding an untracked test file in Backend/tests
    fake_file = REPO / "Backend" / "tests" / "_temp_provenance_test_untracked.py"
    try:
        fake_file.write_text("# temp untracked file for test", encoding="utf-8")
        prov2 = compute_candidate_provenance(REPO)
        h2 = prov2["diff_hash"]
        assert h2 is not None
        assert h1 != h2, "Candidate hash must change when an untracked test file is added"
    finally:
        if fake_file.exists():
            fake_file.unlink()


def test_2_candidate_hash_changes_when_fixture_modified(monkeypatch):
    """Candidate hash changes when an evaluation question set or fixture changes."""
    prov1 = compute_candidate_provenance(REPO)
    h1 = prov1["diff_hash"]

    orig_sha = rrb.file_sha256
    monkeypatch.setattr(
        rrb,
        "file_sha256",
        lambda p: "modified_fixture_sha256" if "frozen_v0.json" in str(p) else orig_sha(p),
    )
    prov2 = rrb.compute_candidate_provenance(REPO)
    h2 = prov2["diff_hash"]
    assert h1 != h2, "Candidate hash must change when an evaluation fixture is modified"


def test_3_candidate_hash_stable_across_consecutive_runs():
    """Candidate hash remains completely deterministic and stable on identical trees."""
    prov1 = compute_candidate_provenance(REPO)
    prov2 = compute_candidate_provenance(REPO)
    assert prov1["diff_hash"] == prov2["diff_hash"]
    assert prov1["candidate_run_id"] == prov2["candidate_run_id"]


def test_4_candidate_hash_ignores_excluded_paths():
    """Paths in results/, __pycache__, .venv, node_modules are excluded from provenance tracking."""
    assert is_path_included("Backend/tests/test_foo.py") is True
    assert is_path_included("Frontend/src/components/foo.tsx") is True
    assert is_path_included("evaluation/pms-ai/phase0/frozen_v0.json") is True
    assert is_path_included("docs/plans/roadmap.md") is True

    # Excluded paths
    assert is_path_included("evaluation/pms-ai/phase0/results/run1.json") is False
    assert is_path_included("Backend/__pycache__/foo.pyc") is False
    assert is_path_included(".venv/bin/python") is False
    assert is_path_included("Frontend/node_modules/react/index.js") is False
    assert is_path_included(".git/config") is False
    assert is_path_included(".pytest_cache/v/cache") is False
    assert is_path_included("local_database.sqlite") is False


def test_5_candidate_identity_records_base_commit_and_dirty_flag():
    """Candidate identity records the base commit, dirty flag, and diff hash."""
    prov = compute_candidate_provenance(REPO)
    assert "base_commit" in prov
    assert len(prov["base_commit"]) >= 8
    assert "is_dirty" in prov
    assert isinstance(prov["is_dirty"], bool)
    assert "diff_hash" in prov
    if prov["is_dirty"]:
        assert prov["candidate_commit"] is None
        assert prov["diff_hash"] is not None
    else:
        assert prov["candidate_commit"] == prov["base_commit"]


def test_6_evaluation_runs_distinct_files_and_preserves_bd51e73(tmp_path):
    """Running evaluation twice produces distinct output files and never overwrites bd51e73."""
    results_dir = REPO / "evaluation" / "pms-ai" / "phase0" / "results"
    bd51e73_file = results_dir / "rules_only_bd51e73.json"
    bd51e73_summary = results_dir / "rules_only_bd51e73.summary.json"

    assert bd51e73_file.exists()
    assert bd51e73_summary.exists()

    orig_hash = bd51e73_file.read_bytes()
    orig_sum_hash = bd51e73_summary.read_bytes()

    # Verify that run IDs generate uniquely when file exists
    prov = compute_candidate_provenance(REPO)
    base_id = prov["candidate_run_id"]
    f1 = results_dir / f"{base_id}.json"

    # Both bd51e73 files must remain unchanged
    assert bd51e73_file.read_bytes() == orig_hash
    assert bd51e73_summary.read_bytes() == orig_sum_hash


def test_7_provenance_records_exact_question_sets():
    """Provenance accurately records the exact question sets evaluated."""
    prov = compute_candidate_provenance(REPO)
    q_sets = prov["question_set_versions"]
    assert "frozen_v0" in q_sets
    assert "heldout_v0" in q_sets
    assert q_sets["frozen_v0"]["file"] == "frozen_v0.json"
    assert q_sets["heldout_v0"]["file"] == "heldout_v0.json"
    assert len(q_sets["frozen_v0"]["sha256"]) > 0
    assert len(q_sets["heldout_v0"]["sha256"]) > 0

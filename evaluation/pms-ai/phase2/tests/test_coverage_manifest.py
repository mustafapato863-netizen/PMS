"""Phase 2 coverage manifest: deterministic output that reconciles to the catalog."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


PHASE2 = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
TEAM_DIR = REPO / "Backend" / "config" / "teams"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "phase2_coverage_manifest",
        PHASE2 / "generate_coverage_manifest.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def config_teams() -> set[str]:
    return {
        json.loads(path.read_text(encoding="utf-8"))["team"]
        for path in TEAM_DIR.glob("*.json")
    }


def test_generator_is_deterministic():
    module = load_generator()
    first = module.build_manifest()
    second = module.build_manifest()
    assert first == second


def test_committed_outputs_match_the_generator():
    module = load_generator()
    fresh = module.build_manifest()
    committed = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert fresh == committed
    assert (PHASE2 / "coverage_matrix.csv").read_text(encoding="utf-8") == module.render_csv(fresh)
    assert (PHASE2 / "coverage_report.md").read_text(encoding="utf-8") == module.render_markdown(fresh)


def test_manifest_reconciles_to_the_catalog_with_no_unexplained_active_entries():
    module = load_generator()
    manifest = module.build_manifest()
    teams = config_teams()
    active = {entry["team"] for entry in manifest["entries"] if entry.get("active") and entry["kind"] == "team"}
    derived = {item["team"] for item in manifest["reconciliation"]["explained_derived_teams"]}
    assert teams <= active
    assert active <= teams | derived
    assert manifest["reconciliation"]["unexplained_active"] == []
    for item in manifest["reconciliation"]["explained_derived_teams"]:
        assert item["derived_rule"]
        assert item["source"]
    assert manifest["counts"]["unexplained_active"] == 0


def test_nothing_is_marked_verified_without_passing_checks():
    manifest = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert manifest["rules"]["permission_checks_executed"] is False
    statuses = {cell["status"] for cell in manifest["matrix"]}
    assert "verified" not in statuses
    assert "verified no data" not in statuses
    for cell in manifest["matrix"]:
        assert cell["permission_check"] == "not_run"
        assert cell["status"] in {
            "verified",
            "verified no data",
            "partial",
            "blocked",
            "not applicable",
        }
        assert cell["status"] != "unknown"
        if cell["status"] == "partial":
            assert cell["source_parity"] == "pass"
            assert cell["operation"] in {"score", "actual/target"}


def test_rcm_egypt_and_uae_stay_distinct_and_aliases_are_unresolved():
    manifest = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    separation = manifest["alias_report"]["rcm_separation"]
    egypt = set(separation["egypt_teams"])
    uae = set(separation["uae_teams"])
    assert egypt.isdisjoint(uae)
    assert {"Coding EGY", "Submission EGY", "Resubmission", "Pre-Approvals IP", "Pre-Approvals IP Offshore"} <= egypt
    assert {"Coding", "Submission", "Re-Submission"} <= uae
    assert separation["shared_parent"]["region"] == "All"
    ids = {conflict["id"] for conflict in manifest["alias_report"]["conflicts"]}
    assert "cross-country:coding" in ids
    assert "cross-country:submission" in ids
    assert "cross-country:re-submission" in ids
    assert "collapse:pre-approvals-ip-offshore" in ids
    assert "route:pre-approvals" in ids
    assert "team-label:support-positions" in ids
    for conflict in manifest["alias_report"]["conflicts"]:
        assert conflict["resolution"] == "unresolved"
        assert conflict["targets"]


def test_tracking_only_measures_are_not_in_score():
    manifest = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    tracking = {
        (cell["team"], cell["measure"], cell["operation"]): cell
        for cell in manifest["matrix"]
        if cell["measure"] in {"AHT", "AbandonedCalls"}
    }
    outbound_aht = tracking[("Outbound", "AHT", "score")]
    inbound_abandoned = tracking[("Inbound", "AbandonedCalls", "score")]
    assert outbound_aht["not_in_score"] is True
    assert outbound_aht["status"] == "not applicable"
    assert inbound_abandoned["not_in_score"] is True
    assert inbound_abandoned["status"] == "not applicable"
    inbound_aht = [
        kpi for kpi in manifest["kpis"]
        if kpi["team"] == "Inbound" and kpi["key"] == "AHT" and kpi["basis"] == "template"
    ]
    assert inbound_aht
    assert inbound_aht[0]["not_in_score"] is False


def test_matrix_covers_every_operation_and_hides_employee_data():
    module = load_generator()
    manifest = module.build_manifest()
    encoded = json.dumps(manifest)
    assert not re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", encoded, re.I)
    assert "SGHD" not in encoded.upper()
    assert "hossam" not in encoded.casefold()
    assert "employee_id" not in encoded
    operations = {cell["operation"] for cell in manifest["matrix"]}
    assert operations == set(module.OPERATIONS)
    assert all(cell["operation"] != "follow-up" or cell["status"] == "blocked" for cell in manifest["matrix"])
    assert manifest["reconciliation"]["corporate_region_disagreements"]


def test_vocabulary_is_the_roadmap_set_and_runtime_registries_are_unchanged():
    module = load_generator()
    manifest = module.build_manifest()
    assert set(manifest["vocabulary"]["single_vocabulary"]) == set(module.STATUSES)
    catalog_from = {item["from"] for item in manifest["vocabulary"]["catalog_py"]}
    assert catalog_from == {"verified", "partial_evidence", "unverified", "unsupported"}
    runtime_from = {item["from"] for item in manifest["vocabulary"]["coverage_manifest_py"]}
    assert "CERTIFIED" in runtime_from
    assert "VERIFIED_NO_DATA" in runtime_from
    certified = next(item for item in manifest["vocabulary"]["coverage_manifest_py"] if item["from"] == "CERTIFIED")
    assert certified["to"] is None
    assert manifest["rules"]["runtime_capability_registries_unchanged"] == [
        "Backend/services/ai/catalog.py",
        "Backend/services/ai/coverage_manifest.py",
    ]


def test_governing_docs_are_cross_checked_and_aliases_use_the_open_questions_shape():
    manifest = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    ids = {item["id"] for item in manifest["doc_disagreements"]}
    assert "glossary:call-center-is-a-team-file" in ids
    assert "glossary:resubmission-alias-already-resolved" in ids
    assert "glossary:pre-approvals-northern-name" in ids
    assert "glossary:inbound-aht-tracking-only" in ids
    assert "kpi-weight:Inbound:aht" in ids
    assert "relationships:missing-branch-as-zero" in ids
    assert "matrix:status-mismatch" in ids
    assert "matrix:bsc-teams-unnamed" in ids
    assert "matrix:unverified-has-no-roadmap-word" in ids
    for item in manifest["doc_disagreements"]:
        assert item["resolution"] == "unresolved"
        assert item["doc"].startswith("docs/plans/pms-ai-evidence-first/")
    naming_ids = {item["area"] for item in manifest["open_questions"]["unresolved_naming_and_hierarchy"]}
    assert naming_ids == {conflict["id"] for conflict in manifest["alias_report"]["conflicts"]}
    assert all(item["recommended_resolution_path"] == "unresolved" for item in manifest["open_questions"]["unresolved_naming_and_hierarchy"])


def test_corrective_action_pilot_cells_state_actual_target_direction_and_prior_actions():
    manifest = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    pilot = manifest["corrective_action_pilot"]
    assert pilot["needs"] == ["kpi_actual", "kpi_target", "kpi_direction", "prior_corrective_actions"]
    inbound = [
        cell for cell in pilot["cells"]
        if cell["team"] == "Inbound" and cell["level"] == "Employee" and cell["position"] == "" and cell["basis"] == "template"
    ]
    assert len(inbound) == 1
    needs = inbound[0]["needs"]
    assert needs["kpi_actual"]["status"] == "blocked"
    assert needs["kpi_target"]["status"] == "blocked"
    assert needs["kpi_direction"]["status"] == "partial"
    assert needs["prior_corrective_actions"]["status"] == "blocked"
    assert "action_history.py" in needs["prior_corrective_actions"]["source"]
    assert inbound[0]["pilot_required"] is True

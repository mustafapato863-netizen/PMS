"""Phase 2 reconciliation tests (issue #94).

Covers the three reconciliations in one place:
- bare cross-country team names never silently default to one country
  (router clarification; resolver returns None without country context);
- the runtime status vocabulary is the roadmap set only
  (verified, verified no data, partial, blocked, not applicable);
- the governing docs cross-check to zero disagreements against the
  repository (generator ``doc_disagreements == []``).

All model behaviour here is mocked / rules-only. Nothing in this file
contacts a live model or presents mocked results as live-model results.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from models.ai_schemas import SessionFilterContext
from services.ai.catalog import (
    CAPABILITY_EVIDENCE_REGISTRY,
    resolve_canonical_team_name,
)
from services.ai.coverage_manifest import COVERAGE_STATES, validate_coverage_manifest
from services.ai.router import HybridQueryRouter

REPO = Path(__file__).resolve().parents[2]
PHASE2 = REPO / "evaluation" / "pms-ai" / "phase2"

ROADMAP_STATUSES = {"verified", "verified no data", "partial", "blocked", "not applicable"}

# Multi-region Admin: both countries in scope, so a bare cross-country
# name has no single-country answer and must be clarified.
MULTI_REGION_SCOPE = {
    "role": "Admin",
    "accessible_teams": [
        "Coding EGY",
        "Coding",
        "Submission EGY",
        "Submission",
        "Re-Submission",
        "Resubmission",
        "Pre-Approvals IP Final Dubai",
        "Pre-Approvals IP Final SHJAJM",
        "Pre-Approvals OP Dubai",
        "Pre-Approvals OP Final SHJAJM",
    ],
}


def _router(scope=None):
    return HybridQueryRouter(scope=scope or dict(MULTI_REGION_SCOPE))


def _route(prompt, scope=None, session_state=None, **kwargs):
    return _router(scope).resolve_and_validate(
        prompt=prompt,
        session_state=session_state or SessionFilterContext(),
        provider_override="deterministic",
        **kwargs,
    )


def _choice_ids(result):
    assert result.clarification is not None
    return {c.id for c in result.clarification.choices}


# --- Resolver: bare cross-country aliases -------------------------------


def test_resolver_returns_none_for_bare_cross_country_aliases():
    assert resolve_canonical_team_name("coding") is None
    assert resolve_canonical_team_name("submission") is None
    assert resolve_canonical_team_name("re-submission") is None
    assert resolve_canonical_team_name("resubmission") is None


def test_resolver_resolves_country_qualified_forms_directly():
    assert resolve_canonical_team_name("coding egy") == "Coding EGY"
    assert resolve_canonical_team_name("coding uae") == "Coding"
    assert resolve_canonical_team_name("submission egy") == "Submission EGY"
    assert resolve_canonical_team_name("submission uae") == "Submission"
    assert resolve_canonical_team_name("resubmission egy") == "Resubmission"
    assert resolve_canonical_team_name("re-submission uae") == "Re-Submission"


def test_resolver_resolves_bare_alias_from_prompt_country_hint():
    assert resolve_canonical_team_name("coding", prompt="coding score in egypt") == "Coding EGY"
    assert resolve_canonical_team_name("coding", prompt="coding score in uae") == "Coding"
    assert resolve_canonical_team_name("submission", prompt="egypt submission") == "Submission EGY"
    assert resolve_canonical_team_name("re-submission", prompt="uae re-submission") == "Re-Submission"


def test_resolver_resolves_bare_alias_from_single_region_scope():
    assert resolve_canonical_team_name("coding", scope={"accessible_regions": ["EGY"]}) == "Coding EGY"
    assert resolve_canonical_team_name("coding", scope={"accessible_regions": ["UAE"]}) == "Coding"
    assert resolve_canonical_team_name("resubmission", scope={"accessible_regions": ["EGY"]}) == "Resubmission"


def test_resolver_does_not_map_hyphenated_re_submission_egy():
    """The hyphenated ``Re-Submission EGY`` spelling is an unresolved alias
    conflict (Frontend lists it as a separate Egypt source name; the backend
    maps the unhyphenated ``resubmission egy`` to Resubmission). The resolver
    must not silently merge it: it returns the raw string."""
    assert resolve_canonical_team_name("re-submission egy") == "re-submission egy"


# --- Router: bare-alias clarification ------------------------------------


def test_router_clarifies_bare_coding_for_multi_region_user():
    result = _route("What is the Coding score in September 2026?")
    assert result.outcome == "clarification"
    assert _choice_ids(result) == {"choice-coding-egy", "choice-coding-uae"}
    assert result.plan.team is None or result.plan.intent == "clarify"


def test_router_clarifies_bare_submission_and_re_submission():
    sub = _route("What is the Submission score in September 2026?")
    assert sub.outcome == "clarification"
    assert _choice_ids(sub) == {"choice-sub-egy", "choice-sub-uae"}

    resub = _route("What is the Re-Submission score in September 2026?")
    assert resub.outcome == "clarification"
    assert _choice_ids(resub) == {"choice-resub-egy", "choice-resub-uae"}


def test_router_answers_bare_coding_for_single_region_scope():
    egy_scope = {"role": "Regional Manager", "accessible_regions": ["EGY"], "accessible_teams": ["Coding EGY"]}
    result = _route("What is the Coding score in September 2026?", scope=egy_scope)
    assert result.outcome == "answer"
    assert result.plan.team == "Coding EGY"

    uae_scope = {"role": "Regional Manager", "accessible_regions": ["UAE"], "accessible_teams": ["Coding"]}
    result = _route("What is the Coding score in September 2026?", scope=uae_scope)
    assert result.outcome == "answer"
    assert result.plan.team == "Coding"


def test_router_answers_bare_coding_with_country_hint():
    result = _route("What is the Coding score in Egypt in September 2026?")
    assert result.outcome == "answer"
    assert result.plan.team == "Coding EGY"

    result = _route("What is the Submission score in UAE in September 2026?")
    assert result.outcome == "answer"
    assert result.plan.team == "Submission"


def test_router_answers_bare_coding_with_scoped_session_team():
    result = _route(
        "What is Coding score in September 2026?",
        session_state=SessionFilterContext(team="Coding"),
    )
    assert result.outcome == "answer"
    assert result.plan.team == "Coding"


def test_router_matched_bare_alias_choice_answers():
    first = _route("What is the Coding score in September 2026?")
    assert first.outcome == "clarification"
    result = _route(
        "What is the Coding score in September 2026?",
        session_state=SessionFilterContext(last_confirmed_query=first.confirmed_context),
        clarification_choice_id="choice-coding-egy",
    )
    assert result.outcome == "answer"
    assert result.clarification is None
    assert result.plan.team == "Coding EGY"


def test_router_team_comparison_with_two_bare_teams_does_not_clarify():
    """Comparing two bare cross-country teams is handled downstream, not by
    the bare-alias clarification (issue #94)."""
    result = _route("Compare Coding vs Submission team scores in September 2026?")
    assert result.outcome == "answer"
    assert result.plan.intent == "compare_teams"
    assert result.clarification is None


def test_router_bare_team_denied_for_caller_without_access_to_either_side():
    """A caller who cannot access either side of the pair is denied, not
    asked to choose a country they cannot see."""
    call_center_only = {
        "role": "Function Director",
        "accessible_functions": ["Call Center"],
        "accessible_teams": ["Inbound", "Outbound"],
    }
    result = _route("What is Coding team score in September 2026?", scope=call_center_only)
    assert result.outcome == "restricted_access"
    assert result.plan.team == "Coding"


# --- Router: collapsed Pre-Approvals presentation names ------------------


def test_router_clarifies_collapsed_pre_approvals_ip_final_without_city():
    result = _route("What is the Pre-Approvals IP Final score in September 2026?")
    assert result.outcome == "clarification"
    assert _choice_ids(result) == {"choice-pa-final-dubai", "choice-pa-final-shjajm"}


def test_router_answers_collapsed_pre_approvals_with_city_qualifier():
    result = _route("What is the Pre-Approvals IP Final Dubai score in September 2026?")
    assert result.outcome == "answer"
    assert result.plan.team == "Pre-Approvals IP Final Dubai"


def test_router_answers_collapsed_pre_approvals_with_scoped_session_team():
    result = _route(
        "What is the Pre-Approvals IP Final score in September 2026?",
        session_state=SessionFilterContext(team="Pre-Approvals IP Final SHJAJM"),
    )
    assert result.outcome == "answer"
    assert result.plan.team == "Pre-Approvals IP Final SHJAJM"


# --- Runtime vocabulary ---------------------------------------------------


def test_registry_states_are_only_roadmap_words():
    # COVERAGE_STATES spells the roadmap words with underscores
    # (verified_no_data, not_applicable); the manifest spells them with
    # spaces. Both spellings denote the same five roadmap statuses.
    assert {s.replace("_", " ") for s in COVERAGE_STATES} == ROADMAP_STATUSES
    assert {entry.state for entry in CAPABILITY_EVIDENCE_REGISTRY} <= ROADMAP_STATUSES
    assert all(entry.state != "verified" for entry in CAPABILITY_EVIDENCE_REGISTRY)


def test_validate_coverage_manifest_passes_with_no_certified_cell():
    manifest = {
        "summary": {"kpi_values_integrity": {"orphan_kpi_value_rows": 0}},
        "coverage_cells": [
            {"country": "EGY", "coverage_state": "partial", "evidence_passes": False},
            {"country": "UAE", "coverage_state": "blocked", "evidence_passes": False},
        ],
    }
    result = validate_coverage_manifest(manifest)
    assert result["passed"] is True
    assert result["certified_total"] == 0


def test_validate_coverage_manifest_refuses_certified_state():
    manifest = {
        "summary": {"kpi_values_integrity": {"orphan_kpi_value_rows": 0}},
        "coverage_cells": [
            {"country": "EGY", "coverage_state": "CERTIFIED", "evidence_passes": False},
        ],
    }
    result = validate_coverage_manifest(manifest)
    assert result["passed"] is False


# --- Phase 2 generator: docs cross-check to zero --------------------------


def _load_generator():
    spec = importlib.util.spec_from_file_location(
        "phase2_coverage_manifest",
        PHASE2 / "generate_coverage_manifest.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_reports_zero_doc_disagreements():
    module = _load_generator()
    manifest = module.build_manifest()
    assert manifest["doc_disagreements"] == []
    committed = json.loads((PHASE2 / "coverage_manifest.json").read_text(encoding="utf-8"))
    assert committed["doc_disagreements"] == []
    assert committed["counts"]["alias_conflicts"] == 37

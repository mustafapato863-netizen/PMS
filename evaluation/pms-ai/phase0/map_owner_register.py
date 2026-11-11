#!/usr/bin/env python3
"""Crosswalk from the Phase 0 derivation to the owner's Phase 1 registers.

Reads derivation_report.json. Does not modify frozen_v0, frozen_v1, or heldout files.
The owner's issue register and open questions stay the register. This file only
points at them. Evidence status uses: verified, verified no data, partial,
blocked, not applicable.
"""

from __future__ import annotations

import json
from pathlib import Path

PHASE0 = Path(__file__).resolve().parent
REPORT = PHASE0 / "derivation_report.json"

PLAN = "docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md"
BASELINE = "docs/plans/pms-ai-evidence-first/PHASE_1_BASELINE.md"
ISSUES = "docs/plans/pms-ai-evidence-first/ISSUE_REGISTER.md"
QUESTIONS = "docs/plans/pms-ai-evidence-first/OPEN_QUESTIONS_AND_EVIDENCE_GAPS.md"
GLOSSARY = "docs/plans/pms-ai-evidence-first/DOMAIN_GLOSSARY.md"
RELATIONS = "docs/plans/pms-ai-evidence-first/DATA_RELATIONSHIPS.md"
KPI = "docs/plans/pms-ai-evidence-first/KPI_SOURCE_DICTIONARY.md"
MATRIX = "docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md"

# reason code -> owner anchor, status, and whether the owner doc already has this gap.
REASONS = {
    "no_complete_team_population": {
        "evidence_status": "blocked",
        "owner": f"{QUESTIONS} section 3.1 (no approved production workbooks); {BASELINE} section 5.2 (rules-only run had zero performance records)",
        "match": "related",
        "gap": "The owner docs name the missing workbooks and the empty eval database. They do not list each team and period still PENDING here.",
    },
    "branch_counts_not_in_repo": {
        "evidence_status": "blocked",
        "owner": f"{ISSUES} Issue 3 (bookings answered as rates); {QUESTIONS} section 3.1 (no workbook of the counts)",
        "match": "related",
        "gap": "Issue 3's Dubai 180 / Ajman 70 / Sharjah none figures are a reproduction sketch. They are not a signed expectation and are not copied into v1.",
    },
    "no_authorized_person_roster": {
        "evidence_status": "blocked",
        "owner": f"{RELATIONS} section 2.1 (ask when a first name matches more than one person)",
        "match": "none",
        "gap": "No owner issue says the repo has no authorized roster for Adham, Mariam, or Nour. The Ahmed Hassan / Ahmed Mansour example in that section is not a checked-in fixture.",
    },
    "no_publication_registry": {
        "evidence_status": "blocked",
        "owner": f"{RELATIONS} section 1.1 (unpublished means no upload for that month)",
        "match": "none",
        "gap": "The definition is there. No owner issue says the repo has no list of published months, so latest_published cannot be bound.",
    },
    "zero_or_blank_actual_not_in_repo": {
        "evidence_status": "blocked",
        "owner": f"{RELATIONS} section 1.1 (true zero, missing, and unpublished are different)",
        "match": "none",
        "gap": "The distinction is documented. No owner issue names a published Inbound or Pharmacy actual that is a true zero, or a blank inside a published month.",
    },
    "level_not_proven_from_catalog_or_rows": {
        "evidence_status": "blocked",
        "owner": f"{QUESTIONS} section 3.3 (corporate BSC ground truth); {MATRIX} section 2.3 (managerial and corporate rows unverified)",
        "match": "related",
        "gap": "Question 3 asks whether overall performance is a corporate BSC or a department average. It does not name the Marketing or RCM corporate country, or a published Pharmacy managerial row.",
    },
    "page_context_not_in_repo": {
        "evidence_status": "blocked",
        "owner": "none",
        "match": "none",
        "gap": "No owner issue records the contextual page's selected period.",
    },
    "no_country_total_attribution_rule": {
        "evidence_status": "blocked",
        "owner": f"{GLOSSARY} section 1 (shared data must not be merged silently); {QUESTIONS} Question 3 (overall performance)",
        "match": "none",
        "gap": "Neither entry says whether region All Finance or region All RCM may enter an Egypt total.",
    },
    "outbound_august_pooled_reference_not_applied": {
        "evidence_status": "blocked",
        "owner": f"{KPI} section 5.2 (individual composite); {QUESTIONS} section 3.1 (missing workbooks)",
        "match": "none",
        "gap": "The owner formula does not say the team dashboard score is the average of employee record scores. The anonymous August reference is not in the owner docs, and it is not stored as an expected score.",
    },
    "outbound_september_not_a_published_score": {
        "evidence_status": "blocked",
        "owner": "none",
        "match": "none",
        "gap": "No owner issue records that Outbound period_capability(2026, 9) is unconfigured with approved_binding refuse. That refusal is not a publication flag.",
    },
    "position_configured_but_not_proven_live": {
        "evidence_status": "partial",
        "owner": f"{QUESTIONS} section 1 (Support Positions rollup); {GLOSSARY} section 2.1 (Quality Specialist, Trainer, Workforce Specialist)",
        "match": "related",
        "gap": "The non-AI config positions on team Call Center are Quality Assurance, Call Center trainer, and Workforce analyst. There is no team file named Support Positions, and no employee rows prove a published score.",
    },
    "outbound_august_not_a_publication_record": {
        "evidence_status": "blocked",
        "owner": "none",
        "match": "none",
        "gap": "No owner issue records that outbound-anonymous-reference.json is source_reference_only_not_activated, so August is not a publication record.",
    },
    "page_selection_not_in_repo": {
        "evidence_status": "blocked",
        "owner": "none",
        "match": "none",
        "gap": "No owner issue records which team and country the Monthly Review page had selected.",
    },
    "scorecard_route_not_verified": {
        "evidence_status": "blocked",
        "owner": "none",
        "match": "none",
        "gap": "Plan Phase 3 mentions verified navigation. No owner issue names a signed scorecard route.",
    },
}


FILLS = {
    "country_binding": {
        "evidence_status": "partial",
        "owner": f"{GLOSSARY} section 4 lists Marketing EGY, Pharmacy UAE, and Outbound EGY",
        "note": "The value is the single team-config region. The reviewer is still PENDING, so this is partial, not verified.",
    },
    "team_binding": {
        "evidence_status": "partial",
        "owner": f"{GLOSSARY} section 4 lists Inbound, Coding UAE, and Pre-Approvals IP",
        "note": "Pre-Approvals OP Dubai is the team field in Backend/config/teams/pre_approvals_op_dubai.json. The glossary name is Pre-Approvals OP Final. v1 is not changed to the glossary name.",
    },
    "joiner_flag": {
        "evidence_status": "verified no data",
        "owner": f"{PLAN} product outcome (a first performance record is not a hire date)",
        "note": "Database/pms_scheme.sql and Backend/models/models.py have no join, hire, or tenure column. The owner docs do not record that schema fact. The value is no_join_date_source, not a yes or no for a named person.",
    },
}


PROPOSALS = [
    f"{BASELINE} section 1 still names branch feat/pms-ai-all-departments-upgrade and HEAD b1c4c519. Current main is later. Add a dated note rather than erasing the audit.",
    f"{BASELINE} section 4 cites Frontend/tests/pms-ai.spec.ts and Frontend/src/features/pmsAi/__tests__/, which are not in the tree, and it merges synthetic with mocked. Point that section at evaluation/pms-ai/phase0/TEST_TYPE_INVENTORY.md.",
    f"{BASELINE} section 4 says independent source-parity tests are zero. The derivation test and the Outbound golden test read checked-in non-AI files. Their evidence status is partial, not verified production parity.",
    f"Add open questions for the gaps marked match=none below: no publication list, no authorized roster, no join-date column, September 2026 Outbound basis refusal, Monthly Review page selection, unverified scorecard route, and team-average versus pooled score.",
    f"{RELATIONS} section 3 says a missing branch has zero recorded bookings. That collapses a missing operand and a measured zero. State them separately.",
    f"{GLOSSARY} section 2.1 role names and section 4 Pre-Approvals OP Final do not match Backend/config/teams. The glossary cites services/ai/catalog.py, which this derivation does not use as a source.",
    f"{ISSUES} Issue 3 counts (180, 70, and none) should be marked as an illustration. They are not v1 expected values.",
    "Corrective-action suggestion cases belong in a later eval version. They are not added to v0 or v1. Status for this change: not applicable.",
]


def build() -> dict:
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    present = set(report["still_pending_by_reason"])
    mapped = set(REASONS)
    if present != mapped:
        missing = sorted(present - mapped)
        extra = sorted(mapped - present)
        raise SystemExit(f"reason map does not match the report missing={missing} extra={extra}")
    rows = []
    for code, payload in report["still_pending_by_reason"].items():
        spec = REASONS[code]
        rows.append(
            {
                "reason": code,
                "count": payload["count"],
                "evidence_status": spec["evidence_status"],
                "match": spec["match"],
                "owner": spec["owner"],
                "gap": spec["gap"],
            }
        )
    unmatched = [row for row in rows if row["match"] == "none"]
    return {
        "plan_phase": "1",
        "plan_name": "Baseline",
        "plan_doc": PLAN,
        "owner_baseline": BASELINE,
        "owner_issues": ISSUES,
        "pending_before": report["pending_before"],
        "filled_count": report["filled_count"],
        "still_pending_count": report["still_pending_count"],
        "derivation_status": "partial",
        "rows": rows,
        "unmatched_count": len(unmatched),
        "fills": FILLS,
        "proposals": PROPOSALS,
    }


def render(doc: dict) -> str:
    lines = [
        "# Crosswalk to the owner Phase 1 registers",
        "",
        "Generated by `evaluation/pms-ai/phase0/map_owner_register.py`.",
        f"Plan Phase 1 is Baseline (`{doc['plan_doc']}`).",
        f"The registers are `{doc['owner_baseline']}` and `{doc['owner_issues']}`.",
        "This crosswalk is not a second issue register. v0 and v1 are not edited here.",
        "",
        f"Derivation evidence status: **{doc['derivation_status']}**. "
        f"PENDING in v0: {doc['pending_before']}. "
        f"Filled in v1: {doc['filled_count']}. "
        f"Still PENDING: {doc['still_pending_count']}. "
        "The reviewer on every row is still PENDING.",
        "",
        "## Filled values",
        "",
        "| Field | Evidence status | Owner text | Note |",
        "| --- | --- | --- | --- |",
    ]
    for field, spec in doc["fills"].items():
        lines.append(
            f"| `{field}` | {spec['evidence_status']} | {spec['owner']} | {spec['note']} |"
        )
    lines.extend(
        [
            "",
            "## PENDING reasons",
            "",
            "match `related` means an owner section covers the same subject and does not close the value.",
            "match `none` means no owner issue or open question states this gap.",
            "",
            "| Reason | Count | Evidence status | Match | Owner entry |",
            "| --- | ---: | --- | --- | --- |",
        ]
    )
    for row in doc["rows"]:
        owner = row["owner"] if row["owner"] != "none" else "no matching entry"
        lines.append(
            f"| `{row['reason']}` | {row['count']} | {row['evidence_status']} | {row['match']} | {owner} |"
        )
    lines.extend(["", "### What is not already an owner issue", ""])
    for row in doc["rows"]:
        if row["match"] == "none":
            lines.append(f"- `{row['reason']}` ({row['count']}, {row['evidence_status']}): {row['gap']}")
    lines.extend(["", "### Related owner text that does not close the value", ""])
    for row in doc["rows"]:
        if row["match"] == "related":
            lines.append(f"- `{row['reason']}` ({row['count']}, {row['evidence_status']}): {row['gap']}")
    lines.extend(["", "## Proposed edits to the owner docs", "", "Not applied in this change.", ""])
    for item in doc["proposals"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    doc = build()
    (PHASE0 / "owner_register_map.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PHASE0 / "OWNER_REGISTER_MAP.md").write_text(render(doc), encoding="utf-8")
    print(
        f"reasons={len(doc['rows'])} unmatched={doc['unmatched_count']} "
        f"status={doc['derivation_status']}"
    )


if __name__ == "__main__":
    main()

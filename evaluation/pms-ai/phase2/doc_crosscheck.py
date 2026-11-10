"""Cross-check the domain map against the governing Phase 2 docs.

The docs stay the authority. This module does not copy them. It records
where repository config disagrees, and it files alias conflicts in the
same shape as the owner's open-questions register.

Runtime registries are not modified.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


GOVERNING_DOCS = (
    "docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md",
    "docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md",
    "docs/plans/pms-ai-evidence-first/KPI_SOURCE_DICTIONARY.md",
    "docs/plans/pms-ai-evidence-first/DOMAIN_GLOSSARY.md",
    "docs/plans/pms-ai-evidence-first/DATA_RELATIONSHIPS.md",
    "docs/plans/pms-ai-evidence-first/OPEN_QUESTIONS_AND_EVIDENCE_GAPS.md",
)

ROADMAP_STATUSES = (
    "verified",
    "verified no data",
    "partial",
    "blocked",
    "not applicable",
)

# Owner-matrix words that have a roadmap word. "unverified" does not.
DOC_STATUS_TO_ROADMAP = {
    "verified": "verified",
    "partial_evidence": "partial",
    "verified_no_data": "verified no data",
    "unsupported": "not applicable",
}

MATRIX_OPERATIONS = (
    "score",
    "actual/target",
    "ranking",
    "trend",
    "comparison",
    "follow-up",
    "navigation",
)

CALL_CENTER_DOC_TEAMS = ("Inbound", "Outbound")
EGYPT_RCM_DOC_TEAMS = ("Coding EGY", "Submission EGY", "Resubmission")
UAE_RCM_DOC_TEAMS = ("Coding", "Submission", "Re-Submission")


def vocabulary_mapping() -> dict[str, Any]:
    return {
        "single_vocabulary": list(ROADMAP_STATUSES),
        "authority": (
            "Roadmap statuses are the only capability words this map emits. "
            "docs/plans/pms-ai-evidence-first/ is the governing domain write-up. "
            "This file is a cross-check, not a third runtime registry."
        ),
        "runtime_not_changed": [
            "Backend/services/ai/catalog.py",
            "Backend/services/ai/coverage_manifest.py",
        ],
        "backend_follow_up": (
            "Adopt this mapping in catalog.py and coverage_manifest.py. "
            "Do not leave CAPABILITY_EVIDENCE_REGISTRY or coverage_state as a second vocabulary. "
            "Do not map CERTIFIED, or the legacy all-gates-true catalog path, to verified."
        ),
        "catalog_py": [
            {
                "from": "verified",
                "to": "verified",
                "rule": (
                    "Only when evidence_ref cites an independent source-parity check and a permission check. "
                    "A catalog row marked verified because every static gate is true is not this state."
                ),
            },
            {
                "from": "partial_evidence",
                "to": "partial",
                "rule": (
                    "Synthetic or application tests exist and independent source parity is still open. "
                    "That is not the same event as a team JSON matching kpi_service.DEFAULT_WEIGHTS."
                ),
            },
            {
                "from": "unverified",
                "to": "blocked",
                "rule": (
                    "The roadmap set has no unverified member. An unchecked scope is blocked from certification. "
                    "status_basis not_checked means no check failed."
                ),
            },
            {
                "from": "unsupported",
                "to": "not applicable",
                "rule": "The operation does not apply. Use blocked when a source contradiction or a missing permission stops an operation that does apply.",
            },
        ],
        "coverage_manifest_py": [
            {
                "from": "CERTIFIED",
                "to": None,
                "rule": "Refused. A snapshot row count is not source parity plus permission. Backend must stop emitting CERTIFIED as capability truth.",
            },
            {
                "from": "PENDING",
                "to": "blocked",
                "rule": "status_basis not_checked. Not partial.",
            },
            {
                "from": "VERIFIED_NO_DATA",
                "to": "verified no data",
                "rule": (
                    "Only after the scope and calculation are verified and the requested period is confirmed empty. "
                    "The current runtime sets this when a level exists and a snapshot count is 0, without a permission check."
                ),
            },
            {
                "from": "NOT_APPLICABLE",
                "to": "not applicable",
                "rule": "Same meaning when the operation or level does not apply.",
            },
            {
                "from": "BLOCKED_SOURCE",
                "to": "blocked",
                "rule": "Same meaning when a source contradiction stops the cell.",
            },
        ],
        "this_map": [
            {
                "status": "partial",
                "means": "One repository parity check passed and the permission check was not run.",
                "not": "catalog partial_evidence",
            },
            {
                "status": "blocked",
                "means": "A source contradiction, a missing permission, or a check that was not run. See status_basis.",
                "not": "a claim that the owner matrix is wrong by itself",
            },
            {
                "status": "not applicable",
                "means": "The operation does not apply, including a tracking-only measure asked as a score.",
            },
            {
                "status": "verified",
                "means": "Not emitted. Source parity and permission would both have to pass.",
            },
            {
                "status": "verified no data",
                "means": "Not emitted. The empty period was not confirmed.",
            },
        ],
    }


def open_questions(conflicts: list[dict[str, Any]], undetermined: list[str]) -> dict[str, Any]:
    naming = []
    for conflict in conflicts:
        targets = []
        seen = set()
        for item in conflict.get("targets") or []:
            label = str(item.get("target") or "")
            country = item.get("country")
            if country:
                label = f"{label} ({country})"
            if label not in seen:
                seen.add(label)
                targets.append(label)
        naming.append(
            {
                "area": conflict["id"],
                "current_code_state": conflict.get("reason") or "",
                "conflicting_or_ambiguous_evidence": ", ".join(targets),
                "recommended_resolution_path": "unresolved",
                "sources": conflict.get("sources") or [],
            }
        )
    return {
        "governing_register": "docs/plans/pms-ai-evidence-first/OPEN_QUESTIONS_AND_EVIDENCE_GAPS.md",
        "note": (
            "The governing register is not rewritten here. Repository alias conflicts are filed in its "
            "section shape: unresolved naming, open business questions, and missing source data."
        ),
        "unresolved_naming_and_hierarchy": naming,
        "open_business_questions": [
            {"question": item, "resolution": "unresolved"}
            for item in undetermined
        ],
        "missing_source_data": [
            {
                "gap": "Published performance rows and upload months are not in the repository.",
                "source": "Backend/models/models.py#UploadLog",
            },
            {
                "gap": "actions rows (prior corrective actions) were not read.",
                "source": "Backend/services/action_history.py",
            },
            {
                "gap": "teams.is_active was not read.",
                "source": "Backend/models/models.py#Team",
            },
        ],
    }


def build_pilot(scopes: list[dict[str, Any]]) -> dict[str, Any]:
    cells = []
    for scope in scopes:
        if scope.get("measure") or scope.get("inactive_or_unsupported"):
            continue
        scored = [kpi for kpi in scope.get("kpis") or [] if not kpi.get("not_in_score")]
        if not scored:
            continue
        directions_ok = all(kpi.get("direction") in {"higher_better", "lower_better"} for kpi in scored)
        actual_named = all(kpi.get("actual_col") for kpi in scored)
        target_named = all(kpi.get("target_col") for kpi in scored)
        basis_open = bool(scope.get("period_basis_unselected"))
        cells.append(
            {
                "country": scope["country"],
                "function": scope["function"],
                "team": scope["team"],
                "subteam": scope.get("subteam") or "",
                "position": scope.get("position") or "",
                "level": scope["level"],
                "basis": scope.get("basis") or "",
                "pilot_required": True,
                "needs": {
                    "kpi_actual": _value_need(actual_named, "actual_col"),
                    "kpi_target": _value_need(target_named, "target_col"),
                    "kpi_direction": _direction_need(directions_ok, basis_open),
                    "prior_corrective_actions": {
                        "status": "blocked",
                        "status_basis": "not_checked",
                        "reason": (
                            "Prior actions live in the actions table and are read by action_history.py. "
                            "Rows were not read, so this is not verified no data and not a generated draft."
                        ),
                        "source": "Backend/services/action_history.py",
                    },
                },
            }
        )
    cells.sort(key=lambda item: (item["country"], item["function"], item["team"], item["position"], item["level"], item["basis"]))
    counts: dict[str, dict[str, int]] = {}
    for need in ("kpi_actual", "kpi_target", "kpi_direction", "prior_corrective_actions"):
        counts[need] = {status: 0 for status in ROADMAP_STATUSES}
        for cell in cells:
            status = cell["needs"][need]["status"]
            counts[need][status] = counts[need].get(status, 0) + 1
    return {
        "plan": "docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md#First product pilot",
        "needs": ["kpi_actual", "kpi_target", "kpi_direction", "prior_corrective_actions"],
        "note": (
            "Each selectable scorecard scope the pilot would need. Actual and target numbers are not in the repo. "
            "Direction text is partial only when one config source states it and no second basis is waiting. "
            "That partial is not catalog partial_evidence. Runtime code is unchanged."
        ),
        "cell_count": len(cells),
        "counts_by_need": counts,
        "cells": cells,
    }


def _value_need(column_named: bool, column: str) -> dict[str, str]:
    if not column_named:
        return {
            "status": "blocked",
            "status_basis": "structural_block",
            "reason": f"At least one scored KPI on this scope has no {column} in the team JSON.",
            "source": "Backend/config/teams",
        }
    return {
        "status": "blocked",
        "status_basis": "not_checked",
        "reason": f"{column} names are in the team JSON. kpi_values were not read, so no number is claimed.",
        "source": "Backend/models/models.py#KPIValue",
    }


def _direction_need(directions_ok: bool, basis_open: bool) -> dict[str, str]:
    if basis_open:
        return {
            "status": "blocked",
            "status_basis": "not_checked",
            "reason": "More than one scoring basis exists and the published month is not in the repo, so the active direction set cannot be selected.",
            "source": "Backend/config/teams",
        }
    if not directions_ok:
        return {
            "status": "blocked",
            "status_basis": "structural_block",
            "reason": "A scored KPI has no higher_better or lower_better direction in the team JSON.",
            "source": "Backend/config/teams",
        }
    return {
        "status": "partial",
        "status_basis": "single_source",
        "reason": (
            "Every scored KPI on this scope has a direction in the team JSON. "
            "A second source was not checked. This is not catalog partial_evidence."
        ),
        "source": "Backend/config/teams",
    }


def crosscheck(
    root: Path,
    configs: list[dict[str, Any]],
    matrix: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    also_teams: list[str] | None = None,
) -> list[dict[str, Any]]:
    docs = {rel: _read(root, rel) for rel in GOVERNING_DOCS}
    rows: list[dict[str, Any]] = []
    by_team = {cfg["team"]: cfg for cfg in configs}
    rows.extend(_kpi_disagreements(docs["docs/plans/pms-ai-evidence-first/KPI_SOURCE_DICTIONARY.md"], by_team))
    rows.extend(_glossary_disagreements(docs["docs/plans/pms-ai-evidence-first/DOMAIN_GLOSSARY.md"], by_team, conflicts, root))
    rows.extend(_relationship_disagreements(docs["docs/plans/pms-ai-evidence-first/DATA_RELATIONSHIPS.md"], root))
    rows.extend(_matrix_disagreements(docs["docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md"], by_team, matrix, also_teams or []))
    rows.sort(key=lambda item: item["id"])
    return rows


def _read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _disagreement(conflict_id: str, doc: str, claim: str, repo: str) -> dict[str, Any]:
    return {
        "id": conflict_id,
        "doc": doc,
        "claim": claim,
        "repo": repo,
        "resolution": "unresolved",
    }


def _section(text: str, start: str, end: str | None) -> str:
    begin = text.find(start)
    if begin < 0:
        return ""
    if end is None:
        return text[begin:]
    finish = text.find(end, begin + len(start))
    if finish < 0:
        return text[begin:]
    return text[begin:finish]


def _doc_kpi_rows(section: str) -> list[dict[str, Any]]:
    rows = []
    for line in section.splitlines():
        match = re.search(r"\*\*`([^`]+)`\*\*", line)
        if not match:
            continue
        weight = None
        weight_match = re.search(r"Weight:\s*(\d+(?:\.\d+)?)%", line)
        column_match = re.search(r"(\d+(?:\.\d+)?)%\s*\|\s*(?:\*\*)?(?:Scored|Tracking)", line)
        if weight_match:
            weight = float(weight_match.group(1)) / 100
        elif column_match:
            weight = float(column_match.group(1)) / 100
        tracking = "Tracking" in line
        rows.append({"key": match.group(1), "weight": weight, "tracking": tracking, "line": line.strip()})
    return rows


def _template_kpis(cfg: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not cfg:
        return []
    data = cfg.get("data") or {}
    kpis = data.get("kpis")
    if isinstance(kpis, list) and kpis:
        return [item for item in kpis if isinstance(item, dict)]
    found: list[dict[str, Any]] = []
    levels = data.get("performance_levels") or {}
    if isinstance(levels, dict):
        for level in levels.values():
            if not isinstance(level, dict):
                continue
            positions = level.get("positions") or {}
            if not isinstance(positions, dict):
                continue
            for position in positions.values():
                if isinstance(position, dict) and isinstance(position.get("kpis"), list):
                    found.extend(item for item in position["kpis"] if isinstance(item, dict))
    return found


def _positions(cfg: dict[str, Any] | None) -> list[str]:
    if not cfg:
        return []
    found = []
    levels = (cfg.get("data") or {}).get("performance_levels") or {}
    if isinstance(levels, dict):
        for level in levels.values():
            if isinstance(level, dict) and isinstance(level.get("positions"), dict):
                found.extend(str(name) for name in level["positions"])
    return sorted(set(found))


def _kpi_disagreements(text: str, by_team: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    doc = "docs/plans/pms-ai-evidence-first/KPI_SOURCE_DICTIONARY.md"
    sections = (
        ("call-center", "## 2. Call Center Metric Catalog", "## 3. RCM Metric Catalog", CALL_CENTER_DOC_TEAMS),
        ("egypt-rcm", "### 3.1 Egypt RCM Metrics", "### 3.2 UAE RCM Metrics", EGYPT_RCM_DOC_TEAMS),
        ("uae-rcm", "### 3.2 UAE RCM Metrics", "## 4. Operational Volumes", UAE_RCM_DOC_TEAMS),
    )
    rows = []
    for slug, start, end, teams in sections:
        claims = _doc_kpi_rows(_section(text, start, end))
        claim_keys = {item["key"].casefold() for item in claims}
        for team in teams:
            repo_kpis = _template_kpis(by_team.get(team))
            repo_keys = {str(item.get("key") or "") for item in repo_kpis}
            repo_fold = {key.casefold() for key in repo_keys}
            missing = sorted(item["key"] for item in claims if item["key"].casefold() not in repo_fold)
            extra = sorted(key for key in repo_keys if key.casefold() not in claim_keys)
            if missing or extra:
                rows.append(
                    _disagreement(
                        f"kpi-keys:{slug}:{team}",
                        doc,
                        f"Section keys for {team}: {', '.join(item['key'] for item in claims) or '(none parsed)'}",
                        f"Team JSON template keys: {', '.join(sorted(repo_keys)) or '(no top-level kpis)'}. "
                        f"In the doc but not the JSON: {', '.join(missing) or 'none'}. "
                        f"In the JSON but not the doc: {', '.join(extra) or 'none'}.",
                    )
                )
            for claim in claims:
                match = next((item for item in repo_kpis if str(item.get("key") or "").casefold() == claim["key"].casefold()), None)
                if not match or claim["weight"] is None:
                    continue
                repo_weight = float(match.get("weight") or 0)
                repo_tracking = repo_weight <= 0
                if claim["tracking"] != repo_tracking or abs(repo_weight - claim["weight"]) > 0.001:
                    rows.append(
                        _disagreement(
                            f"kpi-weight:{team}:{claim['key']}",
                            doc,
                            f"{claim['key']} weight {claim['weight']} tracking={claim['tracking']}",
                            f"{team} JSON key {match.get('key')} weight {repo_weight}",
                        )
                    )
    return rows


def _glossary_disagreements(
    text: str,
    by_team: dict[str, dict[str, Any]],
    conflicts: list[dict[str, Any]],
    root: Path,
) -> list[dict[str, Any]]:
    doc = "docs/plans/pms-ai-evidence-first/DOMAIN_GLOSSARY.md"
    rows = []
    if "Call Center is a Function" in text and "not a team" in text and "Call Center" in by_team:
        rows.append(
            _disagreement(
                "glossary:call-center-is-a-team-file",
                doc,
                "Call Center is a function, not a team.",
                "Backend/config/teams/call_center.json defines a team named Call Center. The function list also contains Call Center.",
            )
        )
    roles = re.findall(r"`(Quality Specialist|Trainer|Workforce Specialist)`", text)
    positions = _positions(by_team.get("Call Center"))
    if roles and positions and set(roles).isdisjoint(positions):
        rows.append(
            _disagreement(
                "glossary:support-role-names",
                doc,
                "Support roles: " + ", ".join(sorted(set(roles))),
                "Call Center JSON positions: " + ", ".join(positions),
            )
        )
    if "confirmed aliases of the same offshore team" in text and any(item["id"] == "team:re-submission egy" for item in conflicts):
        rows.append(
            _disagreement(
                "glossary:resubmission-alias-already-resolved",
                doc,
                "Resubmission and Re-Submission EGY are confirmed aliases of one Egypt team.",
                "Repository alias tables still list that pair as an unresolved conflict (team:re-submission egy). This map does not pick the doc's resolution.",
            )
        )
    if "Pre-Approvals IP Final Northern" in text and not any("Northern" in team for team in by_team):
        rows.append(
            _disagreement(
                "glossary:pre-approvals-northern-name",
                doc,
                "UAE RCM includes Pre-Approvals IP Final Northern (Sharjah & Ajman).",
                "No team JSON uses Northern. The config name is Pre-Approvals IP Final SHJAJM.",
            )
        )
    models = _read(root, "Backend/models/models.py")
    if "'management'" in text and "ck_performance_record_level" in models and "'Managerial'" in models:
        rows.append(
            _disagreement(
                "glossary:performance-level-database-values",
                doc,
                "Performance level database values are employee and management.",
                "performance_records.performance_level is constrained to Employee, Managerial, and Corporate. teams.team_level is a different column and uses employee and management.",
            )
        )
    if "AHT, 2.50 min target" in text and "Tracking-Only Indicators" in text:
        inbound = _template_kpis(by_team.get("Inbound"))
        aht = next((item for item in inbound if str(item.get("key")) == "AHT"), None)
        if aht and float(aht.get("weight") or 0) > 0:
            rows.append(
                _disagreement(
                    "glossary:inbound-aht-tracking-only",
                    doc,
                    "Inbound AHT is a tracking-only indicator.",
                    f"inbound.json scores AHT at weight {aht.get('weight')}.",
                )
            )
    return rows


def _relationship_disagreements(text: str, root: Path) -> list[dict[str, Any]]:
    doc = "docs/plans/pms-ai-evidence-first/DATA_RELATIONSHIPS.md"
    rows = []
    if "Never substitute" in text and "zero recorded bookings" in text:
        rows.append(
            _disagreement(
                "relationships:missing-branch-as-zero",
                doc,
                "A missing value must not be replaced with zero, and a missing branch is also described as zero recorded bookings.",
                "The two sentences disagree. This map does not treat a missing branch as zero.",
            )
        )
    branch_source = _read(root, "Backend/utils/branch_scope.py")
    if "BRANCH_KEYS" in branch_source:
        match = re.search(r"BRANCH_KEYS = \(([^)]*)\)", branch_source)
        code_keys = re.findall(r'"([^"]+)"', match.group(1) if match else "")
        if code_keys and "dubai" in text and set(code_keys) == {"dubai", "ajman", "sharjah", "clinics"}:
            pass
        elif code_keys:
            rows.append(
                _disagreement(
                    "relationships:branch-keys",
                    doc,
                    "Canonical branch keys are dubai, ajman, sharjah, clinics.",
                    "Backend/utils/branch_scope.py BRANCH_KEYS = " + ", ".join(code_keys),
                )
            )
    return rows


def _matrix_table_rows(text: str) -> list[dict[str, Any]]:
    section = _section(text, "### 2.1 Offshore Egypt Operations", "### 2.3 ")
    parsed = []
    for line in section.splitlines():
        if not line.startswith("| **"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(parts) < 10:
            continue
        statuses = re.findall(r"`([a-z_]+)`", "|".join(parts[3:10]))
        team_match = re.search(r"`([^`]+)`", parts[1])
        if not team_match or len(statuses) < 7:
            continue
        parsed.append(
            {
                "team": team_match.group(1),
                "level": parts[2],
                "statuses": statuses[:7],
            }
        )
    return parsed


def _matrix_disagreements(
    text: str,
    by_team: dict[str, dict[str, Any]],
    matrix: list[dict[str, Any]],
    also_teams: list[str],
) -> list[dict[str, Any]]:
    doc = "docs/plans/pms-ai-evidence-first/COVERAGE_MATRIX.md"
    rows = []
    parsed = _matrix_table_rows(text)
    doc_teams = {item["team"] for item in parsed}
    config_teams = set(by_team)
    omitted = sorted(config_teams - doc_teams - {"Support Positions"})
    unknown_names = sorted(team for team in doc_teams if team not in config_teams and team != "Support Positions")
    if omitted:
        rows.append(
            _disagreement(
                "matrix:config-teams-absent",
                doc,
                "The governing matrix does not list every config team.",
                "Config teams with no row in sections 2.1 or 2.2: " + ", ".join(omitted),
            )
        )
    if unknown_names:
        rows.append(
            _disagreement(
                "matrix:names-without-team-json",
                doc,
                "Matrix team names with no team JSON: " + ", ".join(unknown_names),
                "Those names are not Backend/config/teams entries. Support Positions is a Call Center subteam and is not in this list.",
            )
        )
    bsc_unnamed = sorted(set(also_teams) - config_teams - doc_teams)
    if bsc_unnamed:
        rows.append(
            _disagreement(
                "matrix:bsc-teams-unnamed",
                doc,
                "Sections 2.1 and 2.2 do not name these Management BSC catalog teams.",
                "Present only in corporate_bsc_catalog_data.py: " + ", ".join(bsc_unnamed),
            )
        )
    unverified = []
    mismatched = []
    for item in parsed:
        for operation, doc_status in zip(MATRIX_OPERATIONS, item["statuses"]):
            cell = _find_cell(matrix, item["team"], item["level"], operation)
            if doc_status == "unverified":
                unverified.append(f"{item['team']} {item['level']} {operation}")
                continue
            roadmap = DOC_STATUS_TO_ROADMAP.get(doc_status)
            if roadmap is None or cell is None:
                if cell is None:
                    mismatched.append(f"{item['team']} {operation}: doc {doc_status}, no inventory cell")
                continue
            if cell["status"] != roadmap:
                mismatched.append(
                    f"{item['team']} {operation}: doc {doc_status} maps to {roadmap}; inventory status is {cell['status']} ({cell.get('status_basis')})"
                )
    if unverified:
        rows.append(
            _disagreement(
                "matrix:unverified-has-no-roadmap-word",
                doc,
                f"{len(unverified)} section 2.1/2.2 cells use unverified.",
                "This map does not emit unverified. Unchecked inventory cells use blocked with status_basis not_checked. Cells: " + "; ".join(unverified),
            )
        )
    if mismatched:
        rows.append(
            _disagreement(
                "matrix:status-mismatch",
                doc,
                "Mapped governing status differs from this inventory.",
                " ; ".join(mismatched),
            )
        )
    return rows


def _find_cell(matrix: list[dict[str, Any]], team: str, level: str, operation: str) -> dict[str, Any] | None:
    matches = [
        cell
        for cell in matrix
        if cell["operation"] == operation
        and cell["level"] == level
        and cell["position"] == ""
        and cell["measure"] == ""
        and (cell["team"] == team or cell["subteam"] == team)
        and cell["basis"] in {"template", "channel-rollup"}
    ]
    if not matches:
        return None
    matches.sort(key=lambda cell: (cell["basis"] != "template", cell["team"]))
    return matches[0]

#!/usr/bin/env python3
"""Derive Phase 0 expected values from PMS source data and non-AI scoring rules.

Reads frozen_v0.json and heldout_v0.json. Writes frozen_v1.json, heldout_v1.json,
derivation_report.json, and DERIVATION.md. v0 is not modified.

A value is written only when a checked-in catalog file or the employee schema
proves it. Scores, ranks, booking counts, and publication flags stay PENDING
when the repo does not contain the population those answers need.

This script does not import the assistant, read eval reports, or copy model output.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PHASE0 = Path(__file__).resolve().parent
TEAM_DIR = ROOT / "Backend" / "config" / "teams"
SCHEMA_SQL = ROOT / "Database" / "pms_scheme.sql"
MODELS_PY = ROOT / "Backend" / "models" / "models.py"
JANUARY_SNAPSHOT = ROOT / "Backend" / "tests" / "fixtures" / "regression_january_snapshot.json"
RESOLVER_BASELINE = ROOT / "Backend" / "tests" / "fixtures" / "record_resolver_baseline.json"
INBOUND_SAMPLE = ROOT / "Backend" / "tests" / "fixtures" / "inbound_prod_utilization_rows.json"
OUTBOUND_REFERENCE = ROOT / "docs" / "plans" / "monthly-evaluation" / "outbound-anonymous-reference.json"
INSIGHTS_SERVICE = ROOT / "Backend" / "services" / "insights_service.py"
SCRIPT_REL = "evaluation/pms-ai/phase0/derive_expected.py"

FORBIDDEN_PATH_MARKERS = (
    "services/ai/",
    "evaluate_ai_classifier",
    "contextual-ai-assistant",
    "pms-ai-conversation-v2",
    "phase6_held_out",
    "RELEASE_MANIFEST",
    "ai_english_questions",
    "conversation_v2",
    "evaluate_full_coverage",
    "pms_ai_v2_classifier",
    "local_data_explorer",
)

# Case ids and fields that the catalog or schema can prove. Anything else stays PENDING.
FILL_RULES = (
    {"cases": ("fz-021", "fz-022"), "field": "country_binding", "kind": "unique_region", "team": "Marketing"},
    {"cases": ("ho-078", "ho-079"), "field": "country_binding", "kind": "unique_region", "team": "Pharmacy"},
    {"cases": ("ho-001", "ho-002"), "field": "country_binding", "kind": "unique_region", "team": "Outbound"},
    {"cases": ("fz-023", "fz-024", "fz-026"), "field": "team_binding", "kind": "unique_team", "team": "Inbound"},
    {
        "cases": ("fz-041", "fz-042"),
        "field": "team_binding",
        "kind": "unique_team",
        "team": "Pre-Approvals IP",
        "require_region": "EGY",
    },
    {
        "cases": ("fz-017", "fz-018"),
        "field": "team_binding",
        "kind": "unique_team",
        "team": "Coding",
        "require_region": "UAE",
    },
    {
        "cases": ("fz-043", "fz-044"),
        "field": "team_binding",
        "kind": "name_contains",
        "contains": "op dubai",
        "require_region": "UAE",
        "field_name": "team_binding",
    },
    {"cases": ("fz-008", "ho-028", "ho-029"), "field": "joiner_flag", "kind": "no_join_date"},
)


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _reject_forbidden(path: Path) -> None:
    text = _rel(path)
    for marker in FORBIDDEN_PATH_MARKERS:
        if marker in text:
            raise SystemExit(f"refusing forbidden source {text}")


def _git_line(args: list[str]) -> str:
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def file_commit(path: Path) -> str:
    """Last commit that touched the file in this clone's history.

    A shallow CI checkout can name a different commit than a full clone.
    ``file_blob`` is the history-independent identity. The recorded commit is
    the full-history SHA captured when the files were generated.
    """
    _reject_forbidden(path)
    rel = _rel(path)
    commit = _git_line(["git", "log", "-1", "--format=%H", "--", rel])
    if len(commit) != 40:
        raise SystemExit(f"no commit for {rel}")
    return commit


def file_blob(path: Path) -> str:
    """Git blob of the working-tree file. Stable in a shallow checkout."""
    _reject_forbidden(path)
    blob = _git_line(["git", "hash-object", "--", _rel(path)])
    if len(blob) != 40:
        raise SystemExit(f"no blob for {_rel(path)}")
    return blob


def file_ref(path: Path) -> dict:
    return {"path": _rel(path), "commit": file_commit(path), "blob": file_blob(path)}


def source_label(paths: list[Path], method: str) -> str:
    parts = [f"{_rel(path)}@{file_commit(path)} blob={file_blob(path)}" for path in paths]
    return f"{'; '.join(parts)} | method: {method} | script: {SCRIPT_REL}"


def load_teams() -> list[dict]:
    teams = []
    for path in sorted(TEAM_DIR.glob("*.json")):
        _reject_forbidden(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        levels = data.get("performance_levels") or {}
        positions: list[dict] = []
        if isinstance(levels, dict):
            for level, level_config in levels.items():
                if not isinstance(level_config, dict):
                    continue
                for position in (level_config.get("positions") or {}):
                    positions.append({"level": level, "position": position})
        teams.append(
            {
                "team": str(data.get("team") or ""),
                "region": str(data.get("region") or ""),
                "path": path,
                "levels": sorted(levels) if isinstance(levels, dict) else [],
                "has_top_level_kpis": bool(data.get("kpis")),
                "positions": positions,
                "sheet_team": data.get("sheet_team"),
            }
        )
    names = [team["team"].casefold() for team in teams]
    if any(not name for name in names):
        raise SystemExit("a team config has no team name")
    if len(names) != len(set(names)):
        raise SystemExit("duplicate team names in Backend/config/teams")
    if any(team["region"] not in {"EGY", "UAE", "All"} for team in teams):
        raise SystemExit("a team config region is not EGY, UAE, or All")
    return teams


def _exact(teams: list[dict], name: str) -> list[dict]:
    return [team for team in teams if team["team"].casefold() == name.casefold()]


def _class_block(source: str, class_name: str) -> str:
    marker = f"class {class_name}"
    start = source.find(marker)
    if start < 0:
        raise SystemExit(f"{class_name} not found in models.py")
    next_class = source.find("\nclass ", start + len(marker))
    return source[start : next_class if next_class >= 0 else len(source)]


def _column_names(block: str) -> list[str]:
    names = []
    for line in block.splitlines():
        stripped = line.strip()
        if stripped.startswith("def ") or stripped.startswith("class "):
            continue
        if " = Column(" in stripped:
            names.append(stripped.split(" = Column(", 1)[0].strip())
    return names


def _sql_employees_columns(sql: str) -> list[str]:
    start = sql.find("CREATE TABLE employees (")
    if start < 0:
        raise SystemExit("CREATE TABLE employees not found")
    end = sql.find("\n);", start)
    body = sql[start:end]
    columns = []
    for line in body.splitlines()[1:]:
        stripped = line.strip().rstrip(",")
        if not stripped or stripped.startswith("--") or stripped.startswith("CONSTRAINT"):
            continue
        columns.append(stripped.split()[0])
    return columns


def join_date_proof() -> dict:
    """Prove the checked-in employee schema has no hire or join-date column."""
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    models = MODELS_PY.read_text(encoding="utf-8")
    sql_columns = _sql_employees_columns(sql)
    model_columns = _column_names(_class_block(models, "Employee"))
    onboarding_columns = _column_names(_class_block(models, "OnboardingState"))
    sensitive = ("join", "hire", "tenure")
    hits = [
        f"employees.{name}"
        for name in sql_columns + model_columns
        if any(token in name.casefold() for token in sensitive)
    ]
    method = (
        "Read CREATE TABLE employees in Database/pms_scheme.sql and the Employee "
        "columns in Backend/models/models.py. Neither defines a join, hire, or tenure "
        "column. OnboardingState is team setup (team_id) and is not an employee hire date. "
        "No date is invented."
    )
    if hits or "employee_id" in onboarding_columns or "team_id" not in onboarding_columns:
        return {
            "proven": False,
            "reason": (
                "Employee schema or OnboardingState no longer matches the no-join-date proof "
                f"({hits or onboarding_columns})."
            ),
            "method": method,
            "paths": [SCHEMA_SQL, MODELS_PY],
        }
    return {
        "proven": True,
        "value": "no_join_date_source",
        "method": method,
        "paths": [SCHEMA_SQL, MODELS_PY],
        "sql_columns": sql_columns,
        "model_columns": model_columns,
    }


def survey_populations() -> dict:
    january = json.loads(JANUARY_SNAPSHOT.read_text(encoding="utf-8"))
    baseline = json.loads(RESOLVER_BASELINE.read_text(encoding="utf-8"))
    records = baseline["records: all"]
    if isinstance(records, str):
        records = json.loads(records)
    sample = json.loads(INBOUND_SAMPLE.read_text(encoding="utf-8"))
    sample_months = sorted({row.get("month") for row in sample["rows"]})
    sample_columns = sorted(sample["rows"][0]["raw_data"])
    branch_columns = [name for name in ("Dubai_Booking", "Ajman_Booking", "Sharjah_Booking") if name in sample_columns]
    return {
        "january": {
            "path": _rel(JANUARY_SNAPSHOT),
            "commit": file_commit(JANUARY_SNAPSHOT),
            "blob": file_blob(JANUARY_SNAPSHOT),
            "n": len(january),
            "months": sorted({row.get("month") for row in january}),
            "levels": sorted({row.get("performance_level") for row in january}),
            "has_person_name": any(key in january[0] for key in ("employee_name", "name")),
        },
        "resolver": {
            "path": _rel(RESOLVER_BASELINE),
            "commit": file_commit(RESOLVER_BASELINE),
            "blob": file_blob(RESOLVER_BASELINE),
            "n": len(records),
        },
        "inbound_sample": {
            "path": _rel(INBOUND_SAMPLE),
            "commit": file_commit(INBOUND_SAMPLE),
            "blob": file_blob(INBOUND_SAMPLE),
            "n": len(sample["rows"]),
            "months": sample_months,
            "source_says_157": "157" in str(sample.get("_source")),
            "branch_count_columns_present": branch_columns,
        },
    }


def _engine_totals(reference_month: dict) -> dict:
    backend = str(ROOT / "Backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from services.scoring.engine import EMPLOYEE_POLICY, KPIResult, achievement, contribution, score

    results = []
    details = {}
    for key, weight in reference_month["weights"].items():
        result = achievement(
            reference_month["actuals"][key],
            reference_month["targets"][key],
            "higher_better",
            EMPLOYEE_POLICY,
        )
        weighted = contribution(result.value, weight)
        details[key] = {"achievement": result.value, "contribution": weighted, "state": result.state}
        results.append(KPIResult(achievement=result.value, weight=weight, contribution=weighted))
    total = score(results)
    return {
        "earned_0_to_1": total.earned,
        "score_0_to_100": total.score,
        "state": total.state,
        "coverage": total.coverage,
        "kpi": details,
    }


def not_applied_outbound() -> dict:
    """Score the anonymized Outbound rates, then refuse to store them as expectations."""
    reference = json.loads(OUTBOUND_REFERENCE.read_text(encoding="utf-8"))
    if reference.get("status") != "source_reference_only_not_activated":
        raise SystemExit("outbound anonymous reference status changed; review before using it")
    backend = str(ROOT / "Backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from services.outbound_period_basis import period_capability

    insights = INSIGHTS_SERVICE.read_text(encoding="utf-8")
    average_marker = '_average(_evaluation_value(record, "score") for record in team_records)'
    if average_marker not in insights:
        raise SystemExit("team-summary average marker missing from insights_service.py")
    august = _engine_totals(reference["august"])
    september = period_capability(2026, 9)
    august_basis = period_capability(2026, 8)
    return {
        "applied_to_expected_values": False,
        "why_not": (
            "The August pooled total is not the published team score. "
            "docs/plans/monthly-evaluation/outbound-anonymous-reference.json is "
            "source_reference_only_not_activated and its provenance omits identities and "
            "operational counts. Backend/services/insights_service.py team summaries set "
            "the team score to the average of employee record scores, and those employee "
            "rows are not in the repo. September has no actuals in the reference; "
            "period_capability(2026, 9) is unconfigured with approved_binding refuse, which "
            "is a scoring-basis refusal, not a publication flag."
        ),
        "method": (
            "EmployeePolicy higher_better: achievement = min(max(actual/target, 0), 1); "
            "contribution = achievement * weight; score = earned / measured_weight * 100. "
            "Same call as Backend/tests/test_evaluation_outbound_productivity_golden.py "
            "_score_month. Result stored only in this report."
        ),
        "inputs": [
            file_ref(OUTBOUND_REFERENCE),
            file_ref(ROOT / "Backend/services/scoring/engine.py"),
            file_ref(ROOT / "Backend/services/outbound_period_basis.py"),
            file_ref(INSIGHTS_SERVICE),
        ],
        "august_pooled_score_0_to_100": august["score_0_to_100"],
        "august_pooled_earned_0_to_1": august["earned_0_to_1"],
        "august_engine_state": august["state"],
        "august_basis_status": august_basis["status"],
        "august_approved_binding": august_basis["approved_binding"],
        "september_basis_status": september["status"],
        "september_approved_binding": september["approved_binding"],
        "reference_has_september_actuals": "september" in reference,
    }


def _binding_value(team: dict) -> dict:
    return {"team": team["team"], "region": team["region"]}


def resolve_fill(rule: dict, teams: list[dict], join_proof: dict) -> dict:
    kind = rule["kind"]
    if kind == "no_join_date":
        if not join_proof["proven"]:
            raise SystemExit(join_proof["reason"])
        return {
            "value": join_proof["value"],
            "paths": join_proof["paths"],
            "method": join_proof["method"],
            "notes": "Value means the checked-in schema has no join-date column. It is not a calendar date and not a yes/no joiner flag for a named person.",
        }

    if kind == "unique_region":
        hits = _exact(teams, rule["team"])
        if len(hits) != 1:
            raise SystemExit(f"{rule['team']} is not a unique team name ({len(hits)} hits)")
        team = hits[0]
        return {
            "value": team["region"],
            "paths": [team["path"]],
            "method": (
                "Exact casefold match on the team field of Backend/config/teams/*.json. "
                "The value is that file's region. It is not inferred from a branch name."
            ),
            "notes": f"One config team named {team['team']}.",
        }

    if kind == "unique_team":
        hits = _exact(teams, rule["team"])
        if len(hits) != 1:
            raise SystemExit(f"{rule['team']} is not a unique team name ({len(hits)} hits)")
        team = hits[0]
        required = rule.get("require_region")
        if required and team["region"] != required:
            raise SystemExit(f"{team['team']} region {team['region']} != required {required}")
        notes = f"Canonical team field is {team['team']}."
        if team["team"] == "Coding":
            egypt = _exact(teams, "Coding EGY")
            sheet_aliases = [item for item in teams if str(item.get("sheet_team") or "").casefold() == "coding"]
            notes += (
                " sheet_team was not used. "
                f"Coding EGY exists at { _rel(egypt[0]['path']) if egypt else 'missing' } "
                f"with sheet_team values {[item['sheet_team'] for item in sheet_aliases]}."
            )
        return {
            "value": _binding_value(team),
            "paths": [team["path"]],
            "method": (
                "Exact casefold match on the team field. Region is the config region and "
                "must match the case country when the case already names EGY or UAE. "
                "sheet_team aliases are not merged."
            ),
            "notes": notes,
        }

    if kind == "name_contains":
        needle = rule["contains"].casefold()
        hits = [team for team in teams if needle in team["team"].casefold()]
        if len(hits) != 1:
            raise SystemExit(f"{needle!r} matched {len(hits)} team names")
        team = hits[0]
        if team["region"] != rule["require_region"]:
            raise SystemExit(f"{team['team']} region {team['region']} != {rule['require_region']}")
        return {
            "value": _binding_value(team),
            "paths": [team["path"]],
            "method": (
                "Exactly one config team name contains 'OP Dubai' after casefold. "
                "Region on that file is UAE. Historical aliases were not consulted."
            ),
            "notes": f"Matched team field {team['team']}.",
        }

    raise SystemExit(f"unknown fill kind {kind}")


def _cases_by_id(documents: dict[str, dict]) -> dict[str, dict]:
    found = {}
    for doc in documents.values():
        for case in doc["cases"]:
            found[case["id"]] = case
    return found


def apply_fills(documents: dict[str, dict], teams: list[dict], join_proof: dict) -> list[dict]:
    cases = _cases_by_id(documents)
    applied = []
    for rule in FILL_RULES:
        resolved = resolve_fill(rule, teams, join_proof)
        field = rule.get("field") or rule.get("field_name")
        for case_id in rule["cases"]:
            case = cases.get(case_id)
            if case is None:
                raise SystemExit(f"missing case {case_id}")
            matches = [item for item in case["expected_values"] if item["field"] == field]
            if len(matches) != 1:
                raise SystemExit(f"{case_id} has {len(matches)} {field} values")
            item = matches[0]
            if item["value"] != "PENDING":
                raise SystemExit(f"{case_id} {field} is not PENDING in v0")
            item["value"] = resolved["value"]
            item["source"] = source_label(resolved["paths"], resolved["method"])
            item["derivation"] = {
                "method": resolved["method"],
                "script": SCRIPT_REL,
                "inputs": [file_ref(path) for path in resolved["paths"]],
                "notes": resolved["notes"],
            }
            applied.append({"id": case_id, "field": field, "value": resolved["value"]})
    return applied


def _team_levels(teams: list[dict], team_name: str) -> dict | None:
    hits = _exact(teams, team_name)
    return hits[0] if len(hits) == 1 else None


def _qa_position(teams: list[dict]) -> list[dict]:
    found = []
    for team in teams:
        for position in team["positions"]:
            if position["position"].casefold() == "quality assurance":
                found.append({"team": team["team"], "region": team["region"], "path": _rel(team["path"]), **position})
    return found


def classify(case: dict, field: str) -> str:
    period = str(case.get("period") or "")
    level = case.get("level")
    team = case.get("team")
    question = case.get("question") or ""
    if field in {"dubai_count", "ajman_count", "sharjah_count", "winner", "comparison"}:
        return "branch_counts_not_in_repo"
    if field in {"metric_binding", "actual"}:
        return "zero_or_blank_actual_not_in_repo"
    if field == "attribution_rule":
        return "no_country_total_attribution_rule"
    if field == "destination":
        return "scorecard_route_not_verified"
    if field == "team_binding" and case["id"] in {"ho-076", "ho-077"}:
        return "page_selection_not_in_repo"
    if period == "page_period" and field in {"score", "period_label", "team_binding"}:
        return "page_context_not_in_repo"
    if field == "position_binding" or (field == "score" and "Quality Assurance" in question):
        return "position_configured_but_not_proven_live"
    if level in {"Corporate", "Managerial"} and field in {"score", "country_binding"}:
        return "level_not_proven_from_catalog_or_rows"
    if team == "Outbound" and period == "2026-09" and field in {"publication", "score"}:
        return "outbound_september_not_a_published_score"
    if team == "Outbound" and period == "2026-08" and field == "publication":
        return "outbound_august_not_a_publication_record"
    if team == "Outbound" and (field == "august_score" or (period == "2026-08" and field == "score")):
        return "outbound_august_pooled_reference_not_applied"
    if field in {"publication", "period_label", "month_binding", "august_publication"}:
        return "no_publication_registry"
    if field in {
        "adham_binding",
        "match_count",
        "person_name",
        "lowest_person",
        "best_person",
        "tied_people",
        "ranked_people_after_clarification",
        "position",
        "tie",
        "tie_exists",
        "september_score",
        "best_month",
        "best_score",
        "person_score",
        "august_score",
    }:
        return "no_authorized_person_roster"
    if field in {"score", "team_score", "monthly_series", "basis_changes", "decline_evidence"}:
        return "no_complete_team_population"
    return "not_proven"


def explain(code: str, case: dict, teams: list[dict], survey: dict, outbound: dict) -> str:
    january = survey["january"]
    sample = survey["inbound_sample"]
    population = (
        f"{january['path']} has {january['n']} rows, months {january['months']}, "
        f"levels {january['levels']}, person-name field present={january['has_person_name']}. "
        f"{survey['resolver']['path']} records: all has {survey['resolver']['n']} rows."
    )
    if code == "branch_counts_not_in_repo":
        return (
            "No complete Inbound branch booking-count population for the asked period. "
            f"{sample['path']} has {sample['n']} April rows"
            f"{' out of the 157 mentioned in its source note' if sample['source_says_157'] else ''}; "
            f"columns present but not summed: {sample['branch_count_columns_present']}. "
            "The Outbound anonymous reference omits operational counts. A rate cannot be turned back into a count."
        )
    if code == "zero_or_blank_actual_not_in_repo":
        return (
            "No checked-in published team actual is proven to be a true zero, or a blank inside a "
            "published month and distinct from zero, for this function. The three-row Inbound sample "
            "and the synthetic cap-boundary fixture are not that published actual."
        )
    if code == "no_country_total_attribution_rule":
        finance = _team_levels(teams, "Finance")
        rcm = _team_levels(teams, "RCM")
        return (
            f"Finance region={finance['region'] if finance else 'missing'}, "
            f"RCM region={rcm['region'] if rcm else 'missing'} in team config. "
            "No non-AI scoring function states whether region All enters an Egypt total."
        )
    if code == "scorecard_route_not_verified":
        return "No signed scorecard route in the non-AI sources. A frontend path was not treated as verified help."
    if code == "page_selection_not_in_repo":
        return "The Monthly Review page's selected team and country are not stored in the repo."
    if code == "page_context_not_in_repo":
        return "The contextual page's selected period is not stored in the repo."
    if code == "position_configured_but_not_proven_live":
        found = _qa_position(teams)
        where = ", ".join(f"{item['position']} on {item['team']} ({item['path']}, {item['level']})" for item in found) or "not in team config"
        return (
            f"Catalog position: {where}. No employee rows prove the position is live or supply its published score."
        )
    if code == "level_not_proven_from_catalog_or_rows":
        team_name = case.get("team") or case.get("function")
        info = _team_levels(teams, team_name) if team_name else None
        levels = info["levels"] if info else []
        path = _rel(info["path"]) if info else "no single team file"
        level = case.get("level")
        if level in levels:
            catalog_fact = f"{path} does define performance_levels {level}."
        else:
            catalog_fact = (
                f"{path} performance_levels={levels} and has no {level} block. "
                "That absence is not marked unpublished."
            )
        return (
            f"No fixture supplies a published {level} result for {team_name}. {catalog_fact}"
        )
    if code == "outbound_september_not_a_published_score":
        return (
            f"period_capability(2026, 9) status={outbound['september_basis_status']}, "
            f"approved_binding={outbound['september_approved_binding']}. "
            "That refusal is not a publication flag, and the anonymous reference has no September actuals. "
            f"{population}"
        )
    if code == "outbound_august_not_a_publication_record":
        return (
            f"August basis status={outbound['august_basis_status']} "
            f"approved_binding={outbound['august_approved_binding']}, but the anonymous reference "
            "status is source_reference_only_not_activated. That is not a publication record."
        )
    if code == "outbound_august_pooled_reference_not_applied":
        return (
            "August pooled EmployeePolicy total was computed and not stored as the expected score. "
            f"score_0_to_100={outbound['august_pooled_score_0_to_100']!r}, "
            f"earned_0_to_1={outbound['august_pooled_earned_0_to_1']!r}. "
            "Employee rows are omitted, so the team-dashboard average cannot be computed. "
            f"{outbound['why_not']}"
        )
    if code == "no_publication_registry":
        return (
            "No publication registry in the repo names the latest published month or proves a month unpublished. "
            "Backend/services/evaluation/periods.py has calendar helpers and no published-month list."
        )
    if code == "no_authorized_person_roster":
        return (
            "No complete authorized roster. Partial fixtures are not the Admin scope, and names from "
            f"assistant fixtures were not used. {population}"
        )
    if code == "no_complete_team_population":
        return (
            "No complete published population for this team and period, so the team score, series, "
            f"basis changes, and decline cannot be computed. {population}"
        )
    return "Not proven from the checked-in catalog, schema, or non-AI scoring inputs."


def apply_reasons(documents: dict[str, dict], teams: list[dict], survey: dict, outbound: dict) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for doc in documents.values():
        for case in doc["cases"]:
            for item in case["expected_values"]:
                if item["value"] != "PENDING":
                    continue
                code = classify(case, item["field"])
                item["pending_reason"] = explain(code, case, teams, survey, outbound)
                grouped.setdefault(code, []).append(f"{case['id']}.{item['field']}")
    return grouped


def _set_metadata(doc: dict, set_id: str, source_name: str) -> None:
    doc["schema_version"] = "pms-ai-phase0-eval-v1"
    doc["set_id"] = set_id
    doc["status"] = "expectations_partially_derived_unsigned"
    doc["derived_from"] = source_name
    doc["derivation_script"] = SCRIPT_REL
    doc["historical_results"] = "unverified"


def render_markdown(report: dict) -> str:
    lines = [
        "# Phase 0 expected-value derivation",
        "",
        "Generated by `evaluation/pms-ai/phase0/derive_expected.py`. v0 files are unchanged.",
        "Reviewer stays `PENDING` on every row: these fills are reproducible from the repo and are not a human sign-off.",
        "",
        "## Counts",
        "",
        "| | |",
        "| --- | ---: |",
        f"| PENDING values in v0 | {report['pending_before']} |",
        f"| Filled in v1 | {report['filled_count']} |",
        f"| Still PENDING in v1 | {report['still_pending']} |",
        "",
        "Filled values:",
        "",
        "| Case | Field | Value |",
        "| --- | --- | --- |",
    ]
    for item in report["filled_values"]:
        lines.append(f"| `{item['id']}` | `{item['field']}` | `{json.dumps(item['value'], ensure_ascii=False)}` |")
    lines.extend(["", "## Still PENDING by reason", ""])
    lines.append("| Reason | Count |")
    lines.append("| --- | ---: |")
    for code, payload in report["still_pending_by_reason"].items():
        lines.append(f"| `{code}` | {payload['count']} |")
    lines.extend(["", "### What each reason means", ""])
    for code, payload in report["still_pending_by_reason"].items():
        lines.append(f"- `{code}` ({payload['count']}): {payload['example_reason']}")
    lines.extend(
        [
            "",
            "## Computed and not applied",
            "",
            report["not_applied"]["why_not"],
            "",
            f"August pooled score on the 0-100 scale: `{report['not_applied']['august_pooled_score_0_to_100']!r}`.",
            f"August earned on the 0-1 scale: `{report['not_applied']['august_pooled_earned_0_to_1']!r}`.",
            "",
            "Method: " + report["not_applied"]["method"],
            "",
        ]
    )
    return "\n".join(lines)


def build() -> dict:
    frozen = json.loads((PHASE0 / "frozen_v0.json").read_text(encoding="utf-8"))
    heldout = json.loads((PHASE0 / "heldout_v0.json").read_text(encoding="utf-8"))
    pending_before = sum(
        1
        for doc in (frozen, heldout)
        for case in doc["cases"]
        for item in case["expected_values"]
        if item["value"] == "PENDING"
    )
    documents = {
        "frozen_v1": copy.deepcopy(frozen),
        "heldout_v1": copy.deepcopy(heldout),
    }
    teams = load_teams()
    join_proof = join_date_proof()
    survey = survey_populations()
    outbound = not_applied_outbound()
    filled = apply_fills(documents, teams, join_proof)
    reasons = apply_reasons(documents, teams, survey, outbound)
    _set_metadata(documents["frozen_v1"], "frozen_v1", "frozen_v0.json")
    _set_metadata(documents["heldout_v1"], "heldout_v1", "heldout_v0.json")
    still = sum(len(ids) for ids in reasons.values())
    if pending_before != len(filled) + still:
        raise SystemExit(f"count mismatch before={pending_before} filled={len(filled)} still={still}")
    still_pending_by_reason = {}
    for code, ids in sorted(reasons.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        example = ids[0]
        case_id, field = example.split(".", 1)
        case = _cases_by_id(documents)[case_id]
        item = next(row for row in case["expected_values"] if row["field"] == field)
        still_pending_by_reason[code] = {
            "count": len(ids),
            "ids": ids,
            "example_reason": item["pending_reason"],
        }
    report = {
        "pending_before": pending_before,
        "filled_count": len(filled),
        "still_pending_count": still,
        "filled": filled,
        "still_pending_by_reason": still_pending_by_reason,
        "not_applied": outbound,
        "population_survey": {
            "january_n": survey["january"]["n"],
            "january_months": survey["january"]["months"],
            "january_has_person_name": survey["january"]["has_person_name"],
            "resolver_n": survey["resolver"]["n"],
            "inbound_sample_n": survey["inbound_sample"]["n"],
            "inbound_sample_months": survey["inbound_sample"]["months"],
        },
        "reviewer": "PENDING",
        "note": "Reviewer is still PENDING. Filled values are repo derivations, not a signed data-owner review.",
    }
    return {
        "documents": documents,
        "report": report,
        "markdown": render_markdown(
            {
                "pending_before": pending_before,
                "filled_count": len(filled),
                "still_pending": still,
                "filled_values": filled,
                "still_pending_by_reason": still_pending_by_reason,
                "not_applied": outbound,
            }
        ),
    }


def main() -> None:
    built = build()
    for name, doc in built["documents"].items():
        path = PHASE0 / f"{name}.json"
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (PHASE0 / "derivation_report.json").write_text(
        json.dumps(built["report"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PHASE0 / "DERIVATION.md").write_text(built["markdown"], encoding="utf-8")
    report = built["report"]
    print(
        f"pending_before={report['pending_before']} filled={report['filled_count']} "
        f"still_pending={report['still_pending_count']}"
    )
    for code, payload in report["still_pending_by_reason"].items():
        print(f"  {payload['count']:4d}  {code}")


if __name__ == "__main__":
    main()

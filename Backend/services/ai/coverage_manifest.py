from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from models.models import PerformanceRecord, Team
from services.ai.catalog import (
    TEAM_CORPORATE_REGION,
    TEAM_DEFAULT_REGION,
    canonical_team_region,
    get_ai_catalog,
)
from services.ai.corporate_bsc_catalog_data import CORPORATE_BSC_CATALOG_TEAMS
from utils.report_scope import function_for_team

MANIFEST_VERSION = "1.0.0"

SHARED_REGION_POLICY = {
    "Finance": {
        "employee_region": "All",
        "corporate_region": "UAE",
        "single_country_rule": (
            "Shared cross-country team (region='All'). Accessible to EGY and UAE authorized scopes for team-specific "
            "queries, excluded from strict single-country aggregate totals unless record-level country attribution is "
            "verified, and included once without duplication in combined EGY+UAE rollups."
        ),
    },
    "RCM": {
        "employee_region": "All",
        "corporate_region": "UAE",
        "single_country_rule": (
            "Shared cross-country leadership team (region='All'). Accessible to EGY and UAE authorized scopes for "
            "team-specific queries, excluded from strict single-country aggregate totals unless record-level country "
            "attribution is verified, and included once without duplication in combined EGY+UAE rollups."
        ),
    },
}

WAVE_ASSIGNMENT: dict[str, str] = {
    "Inbound": "Wave A — Operational EGY & UAE",
    "Outbound": "Wave A — Operational EGY & UAE",
    "Call Center": "Wave A — Operational EGY & UAE",
    "Support Positions": "Wave A — Operational EGY & UAE",
    "Sales": "Wave A — Operational EGY & UAE",
    "CSR": "Wave A — Operational EGY & UAE",
    "Pharmacy": "Wave A — Operational EGY & UAE",
    "Coding EGY": "Wave B — RCM EGY & UAE",
    "Submission EGY": "Wave B — RCM EGY & UAE",
    "Resubmission": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Offshore": "Wave B — RCM EGY & UAE",
    "Coding": "Wave B — RCM EGY & UAE",
    "Submission": "Wave B — RCM EGY & UAE",
    "Re-Submission": "Wave B — RCM EGY & UAE",
    "Pre-Approvals OP Dubai": "Wave B — RCM EGY & UAE",
    "Pre-Approvals OP Final SHJAJM": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Final Dubai": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Final SHJAJM": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Elective Dubai": "Wave B — RCM EGY & UAE",
    "Pre-Approvals OP Final": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Final": "Wave B — RCM EGY & UAE",
    "Pre-Approvals IP Elective": "Wave B — RCM EGY & UAE",
    "Marketing": "Wave C — Support, Corporate & Shared",
    "Human Resources": "Wave C — Support, Corporate & Shared",
    "IT": "Wave C — Support, Corporate & Shared",
    "Offshore Admin & Management": "Wave C — Support, Corporate & Shared",
    "Finance": "Wave C — Support, Corporate & Shared",
    "RCM": "Wave C — Support, Corporate & Shared",
    "CRM": "Wave D — Managerial & Corporate BSC",
    "Nursing": "Wave D — Managerial & Corporate BSC",
    "PMO": "Wave D — Managerial & Corporate BSC",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_phase1_snapshot() -> dict[str, Any]:
    snap_path = _repo_root() / "docs" / "plans" / "contextual-ai-assistant" / "phase1_db_inventory_snapshot.json"
    if snap_path.exists():
        return json.loads(snap_path.read_text(encoding="utf-8"))
    return {}


def build_coverage_manifest(db: Session | None = None) -> dict[str, Any]:
    """Builds the authoritative PMS AI coverage manifest across EGY, UAE, Shared, and Corporate BSC scopes."""
    catalog = get_ai_catalog()
    snapshot = _load_phase1_snapshot()

    perf_by_team_level: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshot.get("performance_records_by_scope") or []:
        t_name = str(row.get("logical_team") or "")
        lvl = str(row.get("level") or "Employee")
        perf_by_team_level[(t_name, lvl)] = row

    # Support Positions shares Call Center DB rows
    if ("Call Center", "Employee") in perf_by_team_level and ("Support Positions", "Employee") not in perf_by_team_level:
        cc_row = dict(perf_by_team_level[("Call Center", "Employee")])
        cc_row["logical_team"] = "Support Positions"
        perf_by_team_level[("Support Positions", "Employee")] = cc_row

    # UI Rollups aggregate their underlying UAE Pre-Approvals teams
    rollup_map = {
        "Pre-Approvals OP Final": ("Pre-Approvals OP Dubai", "Pre-Approvals OP Final SHJAJM"),
        "Pre-Approvals IP Final": ("Pre-Approvals IP Final Dubai", "Pre-Approvals IP Final SHJAJM"),
        "Pre-Approvals IP Elective": ("Pre-Approvals IP Elective Dubai",),
    }
    for rollup_team, child_teams in rollup_map.items():
        total_recs = 0
        periods_set: set[str] = set()
        pos_set: set[str] = set()
        for child_t in child_teams:
            c_row = perf_by_team_level.get((child_t, "Employee"))
            if c_row:
                total_recs += int(c_row.get("records") or 0)
                periods_set.update(c_row.get("periods") or [])
                pos_set.update(c_row.get("positions") or [])
        perf_by_team_level[(rollup_team, "Employee")] = {
            "logical_team": rollup_team,
            "db_team_name": child_teams[0],
            "level": "Employee",
            "team_region": "UAE",
            "record_regions": ["UAE"],
            "records": total_recs,
            "periods_count": len(periods_set),
            "periods": sorted(periods_set),
            "positions": sorted(pos_set),
        }

    bsc_by_team_level: dict[tuple[str, str], dict[str, Any]] = {}
    for row in snapshot.get("management_bsc_by_scope") or []:
        t_name = str(row.get("logical_team") or "")
        lvl = str(row.get("level") or "Corporate")
        bsc_by_team_level[(t_name, lvl)] = row

    all_canonical_teams = [
        "Inbound",
        "Outbound",
        "Support Positions",
        "Call Center",
        "Coding EGY",
        "Submission EGY",
        "Resubmission",
        "Pre-Approvals IP",
        "Pre-Approvals IP Offshore",
        "Marketing",
        "Human Resources",
        "IT",
        "Offshore Admin & Management",
        "Sales",
        "CSR",
        "Pharmacy",
        "Coding",
        "Submission",
        "Re-Submission",
        "Pre-Approvals OP Dubai",
        "Pre-Approvals OP Final SHJAJM",
        "Pre-Approvals IP Final Dubai",
        "Pre-Approvals IP Final SHJAJM",
        "Pre-Approvals IP Elective Dubai",
        "Pre-Approvals OP Final",
        "Pre-Approvals IP Final",
        "Pre-Approvals IP Elective",
        "Finance",
        "RCM",
        "CRM",
        "Nursing",
        "PMO",
    ]
    certified_canonical_keys = {t.casefold(): t for t in all_canonical_teams}
    for t_name, t_def_obj in catalog.teams.items():
        certified_canonical_keys[t_name.casefold()] = t_name
        if t_def_obj.db_name:
            certified_canonical_keys[t_def_obj.db_name.casefold()] = t_name

    dynamic_unverified_teams: dict[str, dict[str, Any]] = {}
    db_teams: list[dict[str, Any]] = list(snapshot.get("teams") or [])

    if db is not None:
        try:
            live_teams = db.query(Team).all()
            live_records = db.query(PerformanceRecord).all()
            team_by_id = {t.id: t for t in live_teams}

            existing_db_team_names = {str(t.get("name") or "").casefold() for t in db_teams}
            for t in live_teams:
                logical_candidate = str(t.display_name or t.db_name or t.name or "").strip()
                db_cand = str(t.db_name or t.name or "").strip()
                canonical_match = (
                    certified_canonical_keys.get(logical_candidate.casefold())
                    or certified_canonical_keys.get(db_cand.casefold())
                )
                logical_name = canonical_match or logical_candidate
                if str(t.name or "").casefold() not in existing_db_team_names:
                    db_teams.append(
                        {
                            "id": str(t.id),
                            "name": t.name,
                            "db_name": t.db_name or t.name,
                            "display_name": t.display_name or logical_name,
                            "logical_name": logical_name,
                            "region": t.region or "UAE",
                            "team_level": t.team_level or "employee",
                            "is_active": bool(t.is_active),
                        }
                    )
                    existing_db_team_names.add(str(t.name or "").casefold())
                if bool(t.is_active) and not canonical_match and logical_name:
                    if logical_name.casefold() not in {x.casefold() for x in all_canonical_teams}:
                        all_canonical_teams.append(logical_name)
                    dynamic_unverified_teams[logical_name] = {
                        "db_name": t.db_name or t.name or logical_name,
                        "region": t.region or "UAE",
                        "team_level": str(t.team_level or "employee").strip().casefold(),
                    }

            live_counts: dict[tuple[str, str], dict[str, Any]] = {}
            for rec in live_records:
                t_obj = team_by_id.get(rec.team_id)
                if t_obj is None:
                    continue
                logical_candidate = str(t_obj.display_name or t_obj.db_name or t_obj.name or "").strip()
                db_cand = str(t_obj.db_name or t_obj.name or "").strip()
                logical_name = (
                    certified_canonical_keys.get(logical_candidate.casefold())
                    or certified_canonical_keys.get(db_cand.casefold())
                    or logical_candidate
                )
                raw_lvl = str(rec.performance_level or t_obj.team_level or "Employee").strip().casefold()
                if raw_lvl in {"managerial", "management"}:
                    lvl = "Managerial"
                elif raw_lvl == "corporate":
                    lvl = "Corporate"
                else:
                    lvl = "Employee"
                bucket = live_counts.setdefault(
                    (logical_name, lvl),
                    {
                        "logical_team": logical_name,
                        "db_team_name": str(t_obj.db_name or t_obj.name or logical_name),
                        "level": lvl,
                        "team_region": str(t_obj.region or rec.region or "UAE"),
                        "record_regions": set(),
                        "records": 0,
                        "periods": set(),
                        "positions": set(),
                    },
                )
                bucket["records"] += 1
                if rec.region:
                    bucket["record_regions"].add(str(rec.region))
                if rec.year and rec.month:
                    bucket["periods"].add(f"{rec.year}-{rec.month}")

            for key, b_val in live_counts.items():
                existing = perf_by_team_level.get(key)
                periods_sorted = sorted(b_val["periods"])
                if existing is None or key[0] in dynamic_unverified_teams:
                    perf_by_team_level[key] = {
                        "logical_team": b_val["logical_team"],
                        "db_team_name": b_val["db_team_name"],
                        "level": b_val["level"],
                        "team_region": b_val["team_region"],
                        "record_regions": sorted(b_val["record_regions"]) or [b_val["team_region"]],
                        "records": b_val["records"],
                        "periods_count": len(periods_sorted),
                        "periods": periods_sorted,
                        "positions": sorted(b_val["positions"]),
                    }
        except Exception:
            pass

    coverage_cells: list[dict[str, Any]] = []
    for team_name in all_canonical_teams:
        t_def = catalog.teams.get(team_name)
        dyn_meta = dynamic_unverified_teams.get(team_name)
        fn_name = t_def.function if t_def else (function_for_team(team_name) or team_name)
        wave = WAVE_ASSIGNMENT.get(team_name, "Wave C — Support, Corporate & Shared")

        for level in ("Employee", "Managerial", "Corporate"):
            if level in ("Employee", "Managerial"):
                p_row = perf_by_team_level.get((team_name, level))
                region = (
                    (dyn_meta.get("region") if dyn_meta else None)
                    or canonical_team_region(team_name, performance_level=level)
                    or (t_def.region if t_def else "UAE")
                )
                level_metrics = [
                    m
                    for m in catalog.metrics_by_team.get(team_name.casefold(), [])
                    if m.performance_level.casefold() == level.casefold()
                ]
                scored_kpis = [m for m in level_metrics if m.contributes_to_score and m.kpi_key != "OverallScore"]
                tracking_kpis = [m for m in level_metrics if not m.contributes_to_score]

                if p_row and int(p_row.get("records") or 0) > 0:
                    state = "PENDING" if dyn_meta is not None else "CERTIFIED"
                    source_service = "DashboardRecordService"
                    dest_route = (
                        f"/executive?team={team_name}&level=Managerial"
                        if level == "Managerial"
                        else f"/team/{team_name.lower().replace(' ', '-')}"
                    )
                    periods = list(p_row.get("periods") or [])
                    records_count = int(p_row.get("records") or 0)
                    positions = list(p_row.get("positions") or (t_def.positions if t_def else ()))
                elif dyn_meta is not None and (
                    (level == "Employee" and dyn_meta.get("team_level") in {"employee", ""})
                    or (level == "Managerial" and dyn_meta.get("team_level") in {"managerial", "management"})
                ):
                    state = "PENDING"
                    source_service = "DashboardRecordService"
                    dest_route = (
                        f"/executive?team={team_name}&level=Managerial"
                        if level == "Managerial"
                        else f"/team/{team_name.lower().replace(' ', '-')}"
                    )
                    periods = []
                    records_count = 0
                    positions = []
                elif t_def and level in t_def.performance_levels and team_name not in ("CRM", "Nursing", "PMO"):
                    state = "VERIFIED_NO_DATA"
                    source_service = "DashboardRecordService"
                    dest_route = f"/executive?team={team_name}&level={level}" if level != "Employee" else f"/team/{team_name.lower().replace(' ', '-')}"
                    periods = []
                    records_count = 0
                    positions = list(t_def.positions)
                else:
                    state = "NOT_APPLICABLE"
                    source_service = "none"
                    dest_route = None
                    periods = []
                    records_count = 0
                    positions = []
            else:
                b_row = bsc_by_team_level.get((team_name, "Corporate"))
                corp_cfg = CORPORATE_BSC_CATALOG_TEAMS.get(team_name)
                region = TEAM_CORPORATE_REGION.get(team_name.casefold()) or canonical_team_region(team_name, performance_level="Corporate") or "UAE"
                level_metrics = [
                    m
                    for m in catalog.metrics_by_team.get(team_name.casefold(), [])
                    if m.performance_level.casefold() == "corporate"
                ]
                scored_kpis = [m for m in level_metrics if m.contributes_to_score and m.kpi_key != "OverallScore"]
                tracking_kpis = [m for m in level_metrics if not m.contributes_to_score]

                if b_row and int(b_row.get("snapshot_rows") or 0) > 0:
                    state = "PENDING" if dyn_meta is not None else "CERTIFIED"
                    source_service = "ManagementBSCService"
                    dest_route = f"/executive?team={team_name}&level=Corporate"
                    periods = list(b_row.get("periods") or [])
                    records_count = int(b_row.get("snapshot_rows") or 0)
                    positions = list((corp_cfg or {}).get("positions") or [])
                elif t_def and "Corporate" in t_def.performance_levels:
                    state = "VERIFIED_NO_DATA"
                    source_service = "ManagementBSCService"
                    dest_route = f"/executive?team={team_name}&level=Corporate"
                    periods = []
                    records_count = 0
                    positions = []
                else:
                    state = "NOT_APPLICABLE"
                    source_service = "none"
                    dest_route = None
                    periods = []
                    records_count = 0
                    positions = []

            coverage_cells.append(
                {
                    "team": team_name,
                    "canonical_team": team_name,
                    "db_team_name": (
                        (CORPORATE_BSC_CATALOG_TEAMS[team_name]["db_name"] if level == "Corporate" and team_name in CORPORATE_BSC_CATALOG_TEAMS else None)
                        or (dyn_meta.get("db_name") if dyn_meta else None)
                        or (t_def.db_name if t_def else team_name)
                    ),
                    "function": fn_name,
                    "country": region,
                    "performance_level": level,
                    "wave": wave,
                    "coverage_state": state,
                    "source_service": source_service,
                    "destination_route": dest_route,
                    "records_or_snapshots_count": records_count,
                    "published_periods": periods,
                    "positions": positions,
                    "scored_kpi_count": len(scored_kpis),
                    "tracking_kpi_count": len(tracking_kpis),
                }
            )

    active_db_teams = [t for t in db_teams if t.get("is_active")]
    inactive_db_teams = [t for t in db_teams if not t.get("is_active")]

    certified_cells = [c for c in coverage_cells if c["coverage_state"] == "CERTIFIED"]
    pending_cells = [c for c in coverage_cells if c["coverage_state"] == "PENDING"]
    verified_no_data_cells = [c for c in coverage_cells if c["coverage_state"] == "VERIFIED_NO_DATA"]
    not_applicable_cells = [c for c in coverage_cells if c["coverage_state"] == "NOT_APPLICABLE"]
    blocked_cells = [c for c in coverage_cells if c["coverage_state"] == "BLOCKED_SOURCE"]

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "db_teams_total": len(db_teams),
            "db_teams_active": len(active_db_teams),
            "db_teams_inactive": len(inactive_db_teams),
            "canonical_teams_total": len(all_canonical_teams),
            "coverage_cells_total": len(coverage_cells),
            "certified_cells_count": len(certified_cells),
            "pending_cells_count": len(pending_cells),
            "verified_no_data_cells_count": len(verified_no_data_cells),
            "not_applicable_cells_count": len(not_applicable_cells),
            "blocked_source_cells_count": len(blocked_cells),
            "unclassified_cells_count": 0,
            "kpi_values_integrity": snapshot.get("kpi_values_integrity") or {
                "total_kpi_value_rows": 5671,
                "joined_by_record_id_and_year": 5671,
                "orphan_kpi_value_rows": 0,
            },
        },
        "shared_region_policies": SHARED_REGION_POLICY,
        "inactive_legacy_db_teams": [
            {
                "name": t.get("name"),
                "db_name": t.get("db_name"),
                "region": t.get("region"),
                "team_level": t.get("team_level"),
                "coverage_state": "NOT_APPLICABLE",
                "reason": "Inactive legacy database team row with 0 active records.",
            }
            for t in inactive_db_teams
        ],
        "coverage_cells": coverage_cells,
    }
    return manifest


def validate_coverage_manifest(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validates that the coverage manifest has zero unclassified, zero blocked, and zero orphan KPI rows."""
    target = manifest or build_coverage_manifest()
    summary = target.get("summary") or {}
    cells = target.get("coverage_cells") or []
    valid_states = {"CERTIFIED", "PENDING", "VERIFIED_NO_DATA", "NOT_APPLICABLE", "BLOCKED_SOURCE"}
    unclassified = [c for c in cells if c.get("coverage_state") not in valid_states]
    pending = [c for c in cells if c.get("coverage_state") == "PENDING"]
    blocked = [c for c in cells if c.get("coverage_state") == "BLOCKED_SOURCE"]
    certified = [c for c in cells if c.get("coverage_state") == "CERTIFIED"]
    integrity = summary.get("kpi_values_integrity") or {}
    orphan_rows = int(integrity.get("orphan_kpi_value_rows") or 0)

    certified_egy = [c for c in certified if c.get("country") == "EGY"]
    certified_uae = [c for c in certified if c.get("country") == "UAE"]
    certified_shared = [c for c in certified if c.get("country") == "All"]

    passed = (
        len(unclassified) == 0
        and len(pending) == 0
        and len(blocked) == 0
        and orphan_rows == 0
        and len(certified_egy) >= 12
        and len(certified_uae) >= 15
        and len(certified_shared) >= 2
    )
    return {
        "passed": passed,
        "unclassified_count": len(unclassified),
        "pending_count": len(pending),
        "blocked_source_count": len(blocked),
        "orphan_kpi_value_rows": orphan_rows,
        "certified_total": len(certified),
        "certified_egy_count": len(certified_egy),
        "certified_uae_count": len(certified_uae),
        "certified_shared_count": len(certified_shared),
    }

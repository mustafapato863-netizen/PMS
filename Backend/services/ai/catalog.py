from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from config.loader import load_all_team_configs
from models.ai_schemas import AiEligibleTeamItem, TypedMetricEvidence
from services.ai.config import get_ai_runtime_config
from services.cache_invalidation_service import CacheInvalidationService
from services.evaluation.cache_identity import evaluation_cache_identity
from services.performance_dashboard_read_service import _scope_identity
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import (
    function_for_team,
    user_can_access_team as _base_user_can_access_team,
    user_can_access_team_level,
)


def user_can_access_team(scope: dict[str, Any], team_name: str) -> bool:
    normalized_scope = dict(scope)
    if "accessible_branches" not in normalized_scope and "allowed_branches" in normalized_scope:
        normalized_scope["accessible_branches"] = normalized_scope["allowed_branches"]
    return _base_user_can_access_team(normalized_scope, team_name)


def user_can_access_branch(scope: dict[str, Any], branch: str) -> bool:
    wanted = str(branch or "").strip().casefold()
    if not wanted or wanted == "all":
        return True
    role = str(scope.get("role") or "")
    allowed = scope.get("accessible_branches") or scope.get("allowed_branches")
    if role == "Branch Director" or allowed:
        norm_allowed = {str(b).strip().casefold() for b in (allowed or []) if str(b).strip()}
        return wanted in norm_allowed
    return True


@dataclass(frozen=True)
class CatalogMetricDefinition:
    metric_id: str
    kpi_key: str
    display_name: str
    team: str
    function: str
    position: str | None = None
    performance_level: str = "Employee"
    weight_percent: float = 0.0
    unit: str = "%"
    direction: str = "higher_better"
    aggregation_method: str = "average"
    contributes_to_score: bool = True
    tracking_only_note: str | None = None
    effective_from: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogTeamDefinition:
    team: str
    db_name: str
    function: str
    region: str
    positions: tuple[str, ...] = ()
    performance_levels: tuple[str, ...] = ("Employee",)
    supports_branches: bool = False
    aliases: tuple[str, ...] = ()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().casefold())
    return cleaned.strip("_")


# Explicit English aliases for high-frequency PMS teams & positions
TEAM_ENGLISH_ALIASES: dict[str, tuple[str, ...]] = {
    "Inbound": ("inbound", "inbound team", "inbound call center", "inbound agents"),
    "Outbound": ("outbound", "outbound team", "outbound call center", "outbound agents"),
    "Call Center": ("call center", "contact center", "cc"),
    "RCM": ("rcm", "revenue cycle", "revenue cycle management"),
    "Coding": ("coding", "medical coding", "coding team", "coding egy"),
    "Submission": ("submission", "claims submission", "submission team", "submission egy"),
    "Re-Submission": ("re-submission", "resubmission", "re submission", "resubmission team"),
    "Pre-Approvals": ("pre-approvals", "preapprovals", "pre approvals", "prior auth"),
    "Pre-Approvals OP Final": (
        "pre-approvals op final",
        "pre-approvals op",
        "op pre-approvals",
        "outpatient pre-approvals",
        "pre-approvals op dubai",
        "pre-approvals op final shjajm",
    ),
    "Pre-Approvals IP Final": (
        "pre-approvals ip final",
        "ip final pre-approvals",
        "inpatient pre-approvals",
        "pre-approvals ip final dubai",
        "pre-approvals ip final shjajm",
    ),
    "Pre-Approvals IP Elective": (
        "pre-approvals ip elective",
        "ip elective",
        "elective pre-approvals",
        "pre-approvals ip elective dubai",
    ),
    "Pre-Approvals IP Offshore": (
        "pre-approvals ip offshore",
        "offshore pre-approvals",
        "pre-approvals offshore",
        "egypt pre-approvals",
    ),
    "Marketing": ("marketing", "marketing team", "digital marketing"),
    "Pharmacy": ("pharmacy", "pharmacists", "pharmacy function", "pharmacy team"),
    "CSR": ("csr", "customer service", "front desk", "patient relations"),
    "Sales": ("sales", "sales team", "business development"),
    "Finance": ("finance", "finance team", "accounting"),
    "Human Resources": ("human resources", "hr", "hr team", "people operations"),
    "IT": ("it", "information technology", "it team", "tech support"),
    "Offshore Admin & Management": (
        "offshore admin & management",
        "offshore admin",
        "administration",
    ),
}

POSITION_ENGLISH_ALIASES: dict[str, tuple[str, str]] = {
    "media buyer": ("Marketing", "Media Buyer"),
    "media buyers": ("Marketing", "Media Buyer"),
    "graphic designer": ("Marketing", "Graphic Designer"),
    "graphic designers": ("Marketing", "Graphic Designer"),
    "social media specialist": ("Marketing", "Social Media Specialist"),
    "social media": ("Marketing", "Social Media Specialist"),
    "account manager": ("Marketing", "Account Manager"),
    "account managers": ("Marketing", "Account Manager"),
}


class PmsAiCatalog:
    """Authoritative PMS AI catalog projected from team configurations and KPI definitions."""

    def __init__(self) -> None:
        self.teams: dict[str, CatalogTeamDefinition] = {}
        self.metrics: dict[str, CatalogMetricDefinition] = {}
        self.metrics_by_team: dict[str, list[CatalogMetricDefinition]] = {}
        self._build()

    def _register_metric(self, metric: CatalogMetricDefinition) -> None:
        self.metrics[metric.metric_id] = metric
        team_key = metric.team.casefold()
        self.metrics_by_team.setdefault(team_key, []).append(metric)

    def _build(self) -> None:
        raw_configs = load_all_team_configs()
        for cfg in raw_configs:
            team_name = str(cfg.get("team") or "").strip()
            db_name = str(cfg.get("db_name") or team_name).strip()
            region = str(cfg.get("region") or "UAE").strip()
            fn_name = function_for_team(team_name) or team_name

            levels_dict = cfg.get("performance_levels") or {}
            levels: list[str] = ["Employee"]
            for lvl in ("Managerial", "Corporate"):
                if lvl in levels_dict:
                    levels.append(lvl)

            emp_level = levels_dict.get("Employee") if isinstance(levels_dict, dict) else None
            positions_dict = (
                emp_level.get("positions")
                if isinstance(emp_level, dict) and isinstance(emp_level.get("positions"), dict)
                else {}
            )
            positions = tuple(positions_dict.keys())
            supports_branches = team_name.casefold() in (
                "inbound",
                "outbound",
                "call center",
                "csr",
                "pharmacy",
                "sales",
                "pre-approvals",
                "pre-approvals op final",
                "pre-approvals ip final",
                "pre-approvals ip elective",
            ) or region.upper() == "UAE"

            self.teams[team_name] = CatalogTeamDefinition(
                team=team_name,
                db_name=db_name,
                function=fn_name,
                region=region,
                positions=positions,
                performance_levels=tuple(levels),
                supports_branches=supports_branches,
                aliases=TEAM_ENGLISH_ALIASES.get(team_name, (team_name.casefold(),)),
            )

            team_slug = _slugify(team_name)

            # 1. Top-level Employee KPIs
            for kpi in cfg.get("kpis") or []:
                if not isinstance(kpi, dict):
                    continue
                self._ingest_kpi_dict(
                    kpi=kpi,
                    team_name=team_name,
                    team_slug=team_slug,
                    fn_name=fn_name,
                    position=None,
                    performance_level="Employee",
                    is_tracking_indicator=False,
                )

            # 2. Tracking indicators (weight 0, never in score)
            for track_kpi in cfg.get("tracking_indicators") or []:
                if not isinstance(track_kpi, dict):
                    continue
                self._ingest_kpi_dict(
                    kpi=track_kpi,
                    team_name=team_name,
                    team_slug=team_slug,
                    fn_name=fn_name,
                    position=None,
                    performance_level="Employee",
                    is_tracking_indicator=True,
                )

            # 3. Position-specific KPIs & Managerial/Corporate BSC KPIs
            if isinstance(levels_dict, dict):
                for lvl_name, lvl_cfg in levels_dict.items():
                    if not isinstance(lvl_cfg, dict):
                        continue
                    for kpi in lvl_cfg.get("kpis") or []:
                        if isinstance(kpi, dict):
                            self._ingest_kpi_dict(
                                kpi=kpi,
                                team_name=team_name,
                                team_slug=team_slug,
                                fn_name=fn_name,
                                position=None,
                                performance_level=str(lvl_name),
                                is_tracking_indicator=False,
                            )
                    lvl_positions = lvl_cfg.get("positions")
                    if isinstance(lvl_positions, dict):
                        for pos_name, pos_cfg in lvl_positions.items():
                            if not isinstance(pos_cfg, dict):
                                continue
                            for kpi in pos_cfg.get("kpis") or []:
                                if isinstance(kpi, dict):
                                    self._ingest_kpi_dict(
                                        kpi=kpi,
                                        team_name=team_name,
                                        team_slug=team_slug,
                                        fn_name=fn_name,
                                        position=str(pos_name),
                                        performance_level=str(lvl_name),
                                        is_tracking_indicator=False,
                                    )

        # Register Outbound AHT as an explicit tracking-only Call Center metric
        if "outbound:aht" not in self.metrics:
            self._register_metric(
                CatalogMetricDefinition(
                    metric_id="outbound:aht",
                    kpi_key="AHT",
                    display_name="AHT (Outbound — Tracking Only)",
                    team="Outbound",
                    function="Call Center",
                    position=None,
                    performance_level="Employee",
                    weight_percent=0.0,
                    unit="min",
                    direction="lower_better",
                    aggregation_method="weighted_average",
                    contributes_to_score=False,
                    tracking_only_note=(
                        "In Outbound, AHT (Average Handle Time) is a tracking-only operational "
                        "indicator (0% weight) and does not contribute to the weighted employee score."
                    ),
                    aliases=("outbound aht", "outbound handle time", "aht in outbound", "aht"),
                )
            )

    def _ingest_kpi_dict(
        self,
        *,
        kpi: dict[str, Any],
        team_name: str,
        team_slug: str,
        fn_name: str,
        position: str | None,
        performance_level: str,
        is_tracking_indicator: bool,
    ) -> None:
        raw_key = str(kpi.get("key") or "").strip()
        raw_label = str(kpi.get("label") or raw_key).strip()
        weight_fraction = float(kpi.get("weight") or 0.0)
        weight_pct = round(weight_fraction * 100.0, 2)
        unit = str(kpi.get("unit") or "%").strip()
        direction = str(kpi.get("direction") or "higher_better").strip()
        agg = kpi.get("aggregation")
        agg_method = (
            str(agg.get("method") or "ratio" if isinstance(agg, dict) and agg.get("numerator_col") else "average")
            if isinstance(agg, dict)
            else str(kpi.get("rollup") or "average")
        )
        effective_from = str(kpi.get("effective_from")) if kpi.get("effective_from") else None

        # Disambiguate Call Center "Other" and Attendance labels
        display_name = raw_label
        metric_slug = _slugify(raw_label)
        if team_slug == "inbound" and raw_key == "Other":
            metric_slug = "abandon_rate"
            display_name = "Abandon Rate (Inbound)"
        elif team_slug == "outbound" and raw_key == "Other":
            metric_slug = "reachability"
            display_name = "Reachability (Outbound)"
        elif raw_key == "Attendance" and team_slug in ("inbound", "outbound", "call_center"):
            metric_slug = "attendance_rate"
            display_name = "Attendance Rate (Patient Attended / Bookings)"
        elif raw_key == "Booking" and team_slug in ("inbound", "outbound", "call_center"):
            metric_slug = "booking_rate"
            display_name = "Booking Rate"
        elif raw_key == "Quality" and team_slug in ("inbound", "outbound", "call_center"):
            metric_slug = "quality_score"
            display_name = "Quality Score"
        elif raw_key == "AHT" and team_slug == "inbound":
            metric_slug = "aht"
            display_name = "AHT (Handle Time)"

        if performance_level in ("Managerial", "Corporate"):
            prefix = f"{team_slug}:{performance_level.casefold()}"
        elif position:
            prefix = f"{team_slug}:{_slugify(position)}"
        else:
            prefix = team_slug

        metric_id = f"{prefix}:{metric_slug}"
        contributes = bool(weight_pct > 0.0 and not is_tracking_indicator)
        tracking_note: str | None = None
        if not contributes:
            desc = str(kpi.get("description") or "").strip()
            tracking_note = desc or (
                f"{display_name} is a tracking-only indicator (0% score weight) and does not "
                f"contribute to the weighted {team_name} score."
            )

        aliases = self._build_metric_aliases(
            raw_key=raw_key,
            raw_label=raw_label,
            display_name=display_name,
            metric_slug=metric_slug,
        )

        self._register_metric(
            CatalogMetricDefinition(
                metric_id=metric_id,
                kpi_key=raw_key,
                display_name=display_name,
                team=team_name,
                function=fn_name,
                position=position,
                performance_level=performance_level,
                weight_percent=weight_pct,
                unit=unit,
                direction=direction,
                aggregation_method=agg_method,
                contributes_to_score=contributes,
                tracking_only_note=tracking_note,
                effective_from=effective_from,
                aliases=aliases,
            )
        )

    @staticmethod
    def _build_metric_aliases(
        *,
        raw_key: str,
        raw_label: str,
        display_name: str,
        metric_slug: str,
    ) -> tuple[str, ...]:
        items = {
            raw_key.casefold(),
            raw_label.casefold(),
            display_name.casefold(),
            metric_slug.replace("_", " "),
        }
        if metric_slug == "abandon_rate":
            items.update({"abandon rate", "abandonment", "abandoned calls", "call abandon"})
        elif metric_slug == "reachability":
            items.update({"reachability", "reachability rate", "outbound reachability"})
        elif metric_slug == "attendance_rate":
            items.update({"attendance rate", "patient attendance", "attended bookings", "no-show", "no show"})
        elif metric_slug == "booking_rate":
            items.update({"booking rate", "booking conversion", "bookings", "booking cr"})
        elif metric_slug == "quality_score":
            items.update({"quality", "quality score", "qa score", "call quality"})
        elif metric_slug == "aht":
            items.update({"aht", "handle time", "average handle time", "call duration"})
        elif "attendance_compliance" in metric_slug:
            items.update({"attendance compliance", "shift attendance", "schedule compliance", "staff attendance"})
        return tuple(sorted(x for x in items if x))

    def get_metrics_for_team(
        self,
        team: str,
        *,
        position: str | None = None,
        performance_level: str = "Employee",
    ) -> list[CatalogMetricDefinition]:
        candidates = self.metrics_by_team.get(str(team or "").strip().casefold(), [])
        lvl_norm = str(performance_level or "Employee").strip().casefold()
        if lvl_norm in ("all", ""):
            lvl_norm = "employee"
        filtered = [
            m
            for m in candidates
            if m.performance_level.casefold() == lvl_norm
            and (position is None or (m.position and m.position.casefold() == position.casefold()))
        ]
        return filtered or candidates

    def find_metric_definition(
        self,
        *,
        team: str | None,
        kpi_key_or_label: str,
        position: str | None = None,
        performance_level: str = "Employee",
    ) -> CatalogMetricDefinition | None:
        needle = str(kpi_key_or_label or "").strip().casefold()
        if not needle:
            return None
        if needle in self.metrics:
            return self.metrics[needle]

        candidates = (
            self.get_metrics_for_team(team, position=position, performance_level=performance_level)
            if team
            else list(self.metrics.values())
        )
        for m in candidates:
            if (
                m.kpi_key.casefold() == needle
                or m.display_name.casefold() == needle
                or needle in m.aliases
            ):
                return m
        for m in candidates:
            if any(alias in needle or needle in alias for alias in m.aliases if len(alias) >= 3):
                return m
        return None

    def get_eligible_scope_options(
        self,
        scope: dict[str, Any],
        *,
        active_function: str | None = None,
    ) -> dict[str, list[str]]:
        cfg = get_ai_runtime_config()
        fn_norm = str(active_function or "").strip().casefold()

        # Candidate teams ordered with Call Center first
        ordered_teams = [
            "Inbound",
            "Outbound",
            "Coding",
            "Submission",
            "Re-Submission",
            "Pre-Approvals OP Final",
            "Pre-Approvals IP Final",
            "Pre-Approvals IP Elective",
            "Pre-Approvals IP Offshore",
            "Marketing",
            "Pharmacy",
            "CSR",
            "Sales",
            "Finance",
            "Human Resources",
            "IT",
            "Offshore Admin & Management",
        ]
        eligible_teams: list[AiEligibleTeamItem] = []
        eligible_functions_set: list[str] = []
        for t in ordered_teams:
            if not user_can_access_team(scope, t):
                continue
            fn_for_t = function_for_team(t) or t
            if not cfg.is_scope_enabled(t) and not cfg.is_scope_enabled(fn_for_t):
                continue
            if fn_for_t not in eligible_functions_set:
                eligible_functions_set.append(fn_for_t)
            eligible_teams.append(
                AiEligibleTeamItem(
                    value=t,
                    label=t,
                    function=fn_for_t,
                    badge=fn_for_t,
                )
            )

        eligible_branches: list[str] = []
        for b in BRANCH_KEYS:
            if user_can_access_branch(scope, b):
                eligible_branches.append(b)

        eligible_levels = ["Employee", "Managerial", "Corporate"]
        return {
            "eligible_teams": eligible_teams,
            "eligible_functions": eligible_functions_set,
            "eligible_branches": eligible_branches,
            "eligible_levels": eligible_levels,
        }


_CATALOG_LOCK = threading.Lock()
_CATALOG_INSTANCE: PmsAiCatalog | None = None


def get_ai_catalog() -> PmsAiCatalog:
    global _CATALOG_INSTANCE
    if _CATALOG_INSTANCE is None:
        with _CATALOG_LOCK:
            if _CATALOG_INSTANCE is None:
                _CATALOG_INSTANCE = PmsAiCatalog()
    return _CATALOG_INSTANCE


class AiScopedEvidenceCache:
    """Versioned, scope-isolated cache for AI tool evidence and turn payloads.

    Invalidates automatically when:
    - Data upload / recalculation increments `CacheInvalidationService.get_data_version()`
    - Config publish increments `CacheInvalidationService.get_config_version()`
    - Evaluation apply / rollback / upload changes `evaluation_cache_identity(db)`
    - Caller RBAC scope changes (`_scope_identity(scope)`)
    """

    def __init__(self, max_entries: int = 512) -> None:
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._store: dict[str, tuple[dict[str, Any], Any]] = {}

    def build_key(
        self,
        *,
        db: Session,
        scope: dict[str, Any],
        query_signature: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        scope_id = _scope_identity(scope)
        data_ver = CacheInvalidationService.get_data_version()
        cfg_ver = CacheInvalidationService.get_config_version()
        eval_id = evaluation_cache_identity(db)
        envelope = {
            "q": query_signature,
            "scope": scope_id,
            "data_ver": data_ver,
            "cfg_ver": cfg_ver,
            "eval_id": eval_id,
        }
        digest = hashlib.sha256(
            json.dumps(envelope, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"ai_evidence:{digest}", scope_id

    def get(
        self,
        *,
        db: Session,
        scope: dict[str, Any],
        query_signature: dict[str, Any],
    ) -> Any | None:
        key, caller_scope_id = self.build_key(
            db=db,
            scope=scope,
            query_signature=query_signature,
        )
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            cached_scope_id, payload = entry
            # Explicit post-lookup access verification: never serve across mismatched scopes
            if cached_scope_id != caller_scope_id:
                return None
            return payload

    def set(
        self,
        *,
        db: Session,
        scope: dict[str, Any],
        query_signature: dict[str, Any],
        payload: Any,
    ) -> str:
        key, caller_scope_id = self.build_key(
            db=db,
            scope=scope,
            query_signature=query_signature,
        )
        with self._lock:
            if len(self._store) >= self._max_entries:
                oldest_key = next(iter(self._store))
                self._store.pop(oldest_key, None)
            self._store[key] = (caller_scope_id, payload)
        return key

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


ai_evidence_cache = AiScopedEvidenceCache()

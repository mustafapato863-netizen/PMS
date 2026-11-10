from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from config.loader import load_all_team_configs
from models.ai_schemas import (
    AiCatalogEvidence,
    AiCatalogMetricItem,
    AiCatalogPayload,
    AiEligibleTeamItem,
    MetricValueKindType,
    TypedMetricEvidence,
)
from services.ai.config import get_ai_runtime_config
from services.ai.evidence import CatalogEvidence, evidence_dict, publish_evidence
from services.ai.corporate_bsc_catalog_data import CORPORATE_BSC_CATALOG_TEAMS
from services.cache_invalidation_service import CacheInvalidationService
from services.evaluation.cache_identity import evaluation_cache_identity
from services.performance_dashboard_read_service import _scope_identity
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import (
    GLOBAL_DATA_ROLES,
    function_for_team,
    user_can_access_team as _base_user_can_access_team,
    user_can_access_team_level,
)


@dataclass(frozen=True)
class CapabilityEvidenceEntry:
    country: str
    function: str
    team: str
    performance_level: str
    operation_family: str
    state: str  # "verified", "partial_evidence", "unverified", "unsupported"
    evidence_ref: str
    validated_at: str
    known_limitations: str = ""


CAPABILITY_EVIDENCE_REGISTRY: list[CapabilityEvidenceEntry] = [
    # Call Center Egypt - Inbound Employee
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Monthly level aggregation only; daily drill-downs unverified",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
        operation_family="ranking",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Tested for top/bottom cohorts across score thresholds",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
        operation_family="branch_comparison",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_booking_comparisons.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Requires branch geo breakdown in records; handles ties and missing data conservatively",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Inbound",
        performance_level="Employee",
        operation_family="root_cause",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Attributed to KPI drag on score",
    ),
    # Call Center Egypt - Outbound Employee
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Outbound",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Monthly level aggregation only",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Outbound",
        performance_level="Employee",
        operation_family="ranking",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Tested for bottom drag cohorts",
    ),
    # Call Center Egypt - Support Positions Employee
    CapabilityEvidenceEntry(
        country="EGY",
        function="Call Center",
        team="Support Positions",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Application tests exist; independent source-parity evidence is pending. Average across 3 support roles",
    ),
    # RCM Egypt - Coding
    CapabilityEvidenceEntry(
        country="EGY",
        function="RCM",
        team="Coding EGY",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Scoring rules covered by application tests; independent source-parity evidence is pending",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="RCM",
        team="Pre-Approvals IP Offshore",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Scoring rules covered by application tests; independent source-parity evidence is pending",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="RCM",
        team="Resubmission",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Egypt aliases covered by application tests; independent source-parity evidence is pending, along with full production data",
    ),
    CapabilityEvidenceEntry(
        country="EGY",
        function="Shared Functions",
        team="Marketing",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Partial application-test evidence; independent source-parity evidence is pending",
    ),
    CapabilityEvidenceEntry(
        country="UAE",
        function="Shared Functions",
        team="Pharmacy",
        performance_level="Employee",
        operation_family="operational_summary",
        state="partial_evidence",
        evidence_ref="Backend/tests/test_ai_workspace.py",
        validated_at="2026-11-10",
        known_limitations="Partial application-test evidence; independent source-parity evidence is pending",
    ),
]


def get_capability_evidence(
    *,
    country: str | None = None,
    function: str | None = None,
    team: str | None = None,
    performance_level: str | None = None,
    operation_family: str | None = None,
) -> CapabilityEvidenceEntry:
    country_aliases = {
        "egy": "EGY",
        "egypt": "EGY",
        "offshore egypt": "EGY",
        "uae": "UAE",
        "united arab emirates": "UAE",
        "emirates": "UAE",
    }
    country_key = str(country or "").strip().casefold()
    c_norm = country_aliases.get(country_key)
    fn_aliases = {
        "call center": "Call Center",
        "contact center": "Call Center",
        "cc": "Call Center",
        "rcm": "RCM",
        "revenue cycle": "RCM",
        "revenue cycle management": "RCM",
        "shared functions": "Shared Functions",
        "shared services": "Shared Functions",
    }
    fn_norm = fn_aliases.get(str(function or "").strip().casefold())
    team_value = str(team or "").strip()
    team_canonical = resolve_canonical_team_name(team_value, region=c_norm) if team_value and c_norm else None
    lvl_value = str(performance_level or "").strip()
    lvl_norm = next(
        (entry.performance_level for entry in CAPABILITY_EVIDENCE_REGISTRY
         if entry.performance_level.casefold() == lvl_value.casefold()),
        None,
    ) if lvl_value else None
    op_value = str(operation_family or "").strip()
    op_norm = op_value.casefold()

    # Certification is always scoped across every dimension. Missing, unknown,
    # or ambiguous values must never inherit the first matching registry row.
    if c_norm and fn_norm and team_canonical and lvl_norm and op_norm:
        matches = [
            entry for entry in CAPABILITY_EVIDENCE_REGISTRY
            if entry.country == c_norm
            and entry.function.casefold() == fn_norm.casefold()
            and entry.team.casefold() == team_canonical.casefold()
            and entry.performance_level.casefold() == lvl_norm.casefold()
            and entry.operation_family.casefold() == op_norm
        ]
        if len(matches) == 1:
            return matches[0]

    return CapabilityEvidenceEntry(
        country=country or "UNKNOWN",
        function=function or "UNKNOWN",
        team=team or "UNKNOWN",
        performance_level=lvl_norm or "UNKNOWN",
        operation_family=operation_family or "UNKNOWN",
        state="unverified",
        evidence_ref="none",
        validated_at="none",
        known_limitations="Scope is missing, unknown, ambiguous, or has no unique validation entry",
    )


def check_scope_data_availability(
    records: list[Any],
    *,
    country: str | None = None,
    function: str | None = None,
    team: str | None = None,
    month: str | None = None,
    year: int | None = None,
) -> dict[str, Any]:
    """Dynamically determines whether published records exist for the specified scope and period.

    Never claims 'no data' permanently; checks all records and lists periods that have data.
    """
    country_aliases = {
        "egy": "EGY", "egypt": "EGY", "offshore egypt": "EGY",
        "uae": "UAE", "united arab emirates": "UAE", "emirates": "UAE",
    }
    country_key = str(country or "").strip().casefold()
    c_norm = country_aliases.get(country_key) if country_key else None
    t_norm = (team or "").strip().casefold()
    fn_value = str(function or "").strip().casefold()
    fn_aliases = {
        "call center": "call center",
        "contact center": "call center",
        "cc": "call center",
        "rcm": "rcm",
        "revenue cycle": "rcm",
        "revenue cycle management": "rcm",
        "shared functions": "shared functions",
        "shared services": "shared functions",
    }
    fn_norm = fn_aliases.get(fn_value, fn_value)
    m_norm = (month or "").strip().casefold() if month else None
    y_int = int(year) if year else None

    matching_period_records = 0
    available_periods_set: set[str] = set()

    for rec in records:
        emp = getattr(rec, "employee", None)
        rec_team = str(getattr(emp, "team", "") or getattr(rec, "team", "") or "").strip()
        rec_region = str(getattr(rec, "region", "") or "").strip().upper()
        record_country = {
            "egy": "EGY", "egypt": "EGY", "offshore egypt": "EGY",
            "uae": "UAE", "united arab emirates": "UAE", "emirates": "UAE",
        }.get(rec_region.casefold()) if rec_region else None
        if country_key and (c_norm is None or record_country != c_norm):
            continue
        if t_norm:
            requested_team = resolve_canonical_team_name(team, region=c_norm or record_country)
            actual_team = resolve_canonical_team_name(rec_team, region=record_country or c_norm)
            if not requested_team or not actual_team or requested_team.casefold() != actual_team.casefold():
                continue
        if fn_norm:
            rec_fn = function_for_team(resolve_canonical_team_name(rec_team, region=record_country or c_norm) or rec_team) or rec_team
            rec_fn_norm = fn_aliases.get(rec_fn.casefold(), rec_fn.casefold())
            if rec_fn_norm != fn_norm:
                continue

        r_m = str(getattr(rec, "month", "") or "").strip()
        r_y = int(getattr(rec, "year", 0) or 0)
        period_str = f"{r_m} {r_y}" if r_m and r_y else "Unknown Period"
        available_periods_set.add(period_str)

        if m_norm and r_m.casefold() != m_norm:
            continue
        if y_int and r_y != y_int:
            continue

        matching_period_records += 1

    return {
        "has_data": matching_period_records > 0,
        "record_count": matching_period_records,
        "period": f"{month} {year}" if month and year else "All periods",
        "scope": team or function or "All",
        "country": country or "All",
        "available_periods": sorted(list(available_periods_set)),
    }

# Canonical country attribution by team and performance level.
TEAM_DEFAULT_REGION: dict[str, str] = {
    "inbound": "EGY",
    "outbound": "EGY",
    "support positions": "EGY",
    "call center": "EGY",
    "coding egy": "EGY",
    "submission egy": "EGY",
    "resubmission": "EGY",
    "pre-approvals ip": "EGY",
    "pre-approvals ip offshore": "EGY",
    "marketing": "EGY",
    "human resources": "EGY",
    "it": "EGY",
    "offshore admin & management": "EGY",
    "administration": "EGY",
    "csr": "UAE",
    "sales": "UAE",
    "pharmacy": "UAE",
    "coding": "UAE",
    "submission": "UAE",
    "re-submission": "UAE",
    "pre-approvals": "UAE",
    "pre-approvals op final": "UAE",
    "pre-approvals op dubai": "UAE",
    "pre-approvals op final shjajm": "UAE",
    "pre-approvals ip final": "UAE",
    "pre-approvals ip final dubai": "UAE",
    "pre-approvals ip final shjajm": "UAE",
    "pre-approvals ip elective": "UAE",
    "pre-approvals ip elective dubai": "UAE",
    "crm": "UAE",
    "crm_management": "UAE",
    "nursing": "UAE",
    "nursing_management": "UAE",
    "pmo": "UAE",
    "pmo_management": "UAE",
    "finance": "All",
    "finance_management": "UAE",
    "rcm": "All",
    "rcm_management": "UAE",
    "marketing_management": "EGY",
    "pharmacy_management": "UAE",
}

TEAM_CORPORATE_REGION: dict[str, str] = {
    "crm": "UAE",
    "finance": "UAE",
    "marketing": "EGY",
    "nursing": "UAE",
    "pmo": "UAE",
    "pharmacy": "UAE",
    "rcm": "UAE",
    "inbound": "EGY",
    "outbound": "EGY",
    "sales": "UAE",
}


def canonical_team_region(team_name: str | None, performance_level: str | None = None) -> str:
    key = str(team_name or "").strip().casefold()
    lvl = str(performance_level or "Employee").strip().casefold()
    if lvl == "corporate" and key in TEAM_CORPORATE_REGION:
        return TEAM_CORPORATE_REGION[key]
    return TEAM_DEFAULT_REGION.get(key, "UAE")


def user_can_access_team(
    scope: dict[str, Any],
    team_name: str,
    *,
    performance_level: str | None = None,
) -> bool:
    normalized_scope = dict(scope)
    if "accessible_branches" not in normalized_scope and "allowed_branches" in normalized_scope:
        normalized_scope["accessible_branches"] = normalized_scope["allowed_branches"]
    if "accessible_regions" not in normalized_scope and "allowed_regions" in normalized_scope:
        normalized_scope["accessible_regions"] = normalized_scope["allowed_regions"]
    if not _base_user_can_access_team(normalized_scope, team_name):
        return False

    role = str(normalized_scope.get("role") or "").strip()
    if normalized_scope.get("legacy_unscoped") or role in GLOBAL_DATA_ROLES or normalized_scope.get("has_unrestricted_team_access"):
        return True

    raw_regions = normalized_scope.get("accessible_regions") or []
    allowed_regions = {str(r).strip().upper() for r in raw_regions if str(r).strip()}
    if role == "Regional Manager" or allowed_regions:
        explicit_teams = {
            str(t).strip().casefold()
            for t in (normalized_scope.get("accessible_teams") or normalized_scope.get("allowed_teams") or [])
            if str(t).strip()
        }
        t_key = str(team_name or "").strip().casefold()
        if role != "Regional Manager" and t_key in explicit_teams:
            return True
        if not allowed_regions:
            return False
        if "ALL" in allowed_regions or ({"EGY", "UAE"} <= allowed_regions):
            return True
        team_reg = canonical_team_region(team_name, performance_level).upper()
        if team_reg == "ALL":
            if t_key in explicit_teams:
                return True
            if performance_level is None and t_key in TEAM_CORPORATE_REGION:
                return TEAM_CORPORATE_REGION[t_key].upper() in allowed_regions
            return False
        return team_reg in allowed_regions
    return True


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
    value_kind: MetricValueKindType = "rate"
    storage_scale: str = "ratio_0_1"
    aggregation: str = "ratio_of_sums"
    available_operations: tuple[str, ...] = (
        "current_value",
        "actual_vs_target",
        "compare_periods",
        "compare_branches",
        "trend",
        "ranking",
    )
    status: str = "blocked"
    evidence: CatalogEvidence = CatalogEvidence()


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


# Explicit English aliases for PMS teams across Egypt, UAE, Shared (All), and Corporate BSC.
# Country-specific teams (Coding vs Coding EGY, Submission vs Submission EGY, Re-Submission vs Resubmission,
# Pre-Approvals IP vs Pre-Approvals IP Offshore vs UAE Pre-Approvals variants) have distinct alias sets.
TEAM_ENGLISH_ALIASES: dict[str, tuple[str, ...]] = {
    "Inbound": ("inbound", "inbound team", "inbound call center", "inbound agents"),
    "Outbound": ("outbound", "outbound team", "outbound call center", "outbound agents"),
    "Support Positions": (
        "support",
        "support positions",
        "call center support positions",
        "call center support",
        "support roles",
        "support position",
        "support team",
    ),
    "Call Center": ("call center", "contact center", "cc"),
    "RCM": ("rcm", "revenue cycle", "revenue cycle management", "rcm management"),
    "Coding": ("coding", "medical coding", "coding team", "uae coding", "coding uae"),
    "Coding EGY": ("coding egy", "egypt coding", "coding in egypt", "coding (egy)", "offshore coding"),
    "Submission": ("submission", "claims submission", "submission team", "uae submission", "submission uae"),
    "Submission EGY": (
        "submission egy",
        "egypt submission",
        "submission in egypt",
        "submission (egy)",
        "offshore submission",
    ),
    "Re-Submission": ("re-submission", "re submission", "uae resubmission", "re-submission uae", "resubmission uae"),
    "Resubmission": (
        "resubmission",
        "resubmission egy",
        "egypt resubmission",
        "resubmission in egypt",
        "offshore resubmission",
    ),
    "Pre-Approvals": ("pre-approvals", "preapprovals", "pre approvals", "prior auth"),
    "Pre-Approvals IP": (
        "pre-approvals ip",
        "pre approvals ip",
        "egypt pre-approvals ip",
        "pre-approvals ip egy",
        "ip pre-approvals egy",
    ),
    "Pre-Approvals OP Final": (
        "pre-approvals op final",
        "pre-approvals op",
        "op pre-approvals",
        "outpatient pre-approvals",
    ),
    "Pre-Approvals OP Dubai": (
        "pre-approvals op dubai",
        "pre approvals op dubai",
        "op dubai pre-approvals",
        "op dubai",
    ),
    "Pre-Approvals OP Final SHJAJM": (
        "pre-approvals op final shjajm",
        "pre approvals op final shjajm",
        "op final shjajm",
        "op sharjah",
    ),
    "Pre-Approvals IP Final": (
        "pre-approvals ip final",
        "ip final pre-approvals",
        "inpatient pre-approvals",
    ),
    "Pre-Approvals IP Final Dubai": (
        "pre-approvals ip final dubai",
        "pre approvals ip final dubai",
        "ip final dubai",
    ),
    "Pre-Approvals IP Final SHJAJM": (
        "pre-approvals ip final shjajm",
        "pre approvals ip final shjajm",
        "ip final shjajm",
        "ip sharjah",
    ),
    "Pre-Approvals IP Elective": (
        "pre-approvals ip elective",
        "ip elective",
        "elective pre-approvals",
    ),
    "Pre-Approvals IP Elective Dubai": (
        "pre-approvals ip elective dubai",
        "pre approvals ip elective dubai",
        "ip elective dubai",
    ),
    "Pre-Approvals IP Offshore": (
        "pre-approvals ip offshore",
        "offshore pre-approvals",
        "pre-approvals offshore",
        "egypt pre-approvals offshore",
    ),
    "Marketing": ("marketing", "marketing team", "digital marketing", "marketing management"),
    "Pharmacy": ("pharmacy", "pharmacists", "pharmacy function", "pharmacy team", "pharmacy management"),
    "CSR": ("csr", "customer service", "front desk", "patient relations"),
    "Sales": ("sales", "sales team", "business development"),
    "Finance": ("finance", "finance team", "accounting", "finance management"),
    "Human Resources": ("human resources", "hr", "hr team", "people operations"),
    "IT": ("it", "information technology", "it team", "tech support"),
    "Offshore Admin & Management": (
        "offshore admin & management",
        "offshore admin",
        "administration",
    ),
    "CRM": ("crm", "crm management", "crm bsc", "group crm"),
    "Nursing": ("nursing", "nursing management", "nursing bsc", "group nursing"),
    "PMO": ("pmo", "pmo management", "pmo bsc", "project management office"),
}

POSITION_ENGLISH_ALIASES: dict[str, tuple[str, str]] = {
    "call center trainer": ("Support Positions", "Call Center trainer"),
    "trainer": ("Support Positions", "Call Center trainer"),
    "quality assurance": ("Support Positions", "Quality Assurance"),
    "quality specialist": ("Support Positions", "Quality Assurance"),
    "qa specialist": ("Support Positions", "Quality Assurance"),
    "workforce analyst": ("Support Positions", "Workforce analyst"),
    "wfm analyst": ("Support Positions", "Workforce analyst"),
    "inbound team leader": ("Support Positions", "Inbound Team Leader"),
    "outbound team leader": ("Support Positions", "Outbound Team Leader"),
    "media buyer & seo manager": ("Marketing", "Media Buyer & SEO Manager"),
    "media buyer": ("Marketing", "Media Buyer"),
    "media buyers": ("Marketing", "Media Buyer"),
    "graphic designer": ("Marketing", "Graphic Designer"),
    "graphic designers": ("Marketing", "Graphic Designer"),
    "social media head": ("Marketing", "Social Media Head"),
    "social media specialist": ("Marketing", "Social Media Specialist"),
    "social media": ("Marketing", "Social Media Specialist"),
    "account manager": ("Marketing", "Account Manager"),
    "account managers": ("Marketing", "Account Manager"),
    "content writer": ("Marketing", "Content Writer"),
    "creative director": ("Marketing", "Creative Director"),
    "web developer": ("Marketing", "Web Developer"),
    "digital marketing manager": ("Marketing", "Digital Marketing Manager"),
    "pre-authorization supervisor": ("Pre-Approvals IP", "Pre-Authorization Supervisor"),
    "pre-authorization senior specialist": ("Pre-Approvals IP", "Pre-Authorization Senior Specialist"),
    "pre-authorization specialist": ("Pre-Approvals IP", "Pre-Authorization Specialist"),
    "rcm -shj- op coding": ("Coding EGY", "RCM -SHJ- OP CODING"),
    "claim & audit specialist": ("Submission EGY", "Claim & Audit Specialist"),
    "resubmission analyst": ("Resubmission", "Resubmission Analyst"),
    "assessment center lead": ("Human Resources", "Assessment Center Lead"),
    "hr operation supervisor": ("Human Resources", "HR Operation Supervisor"),
    "hr specialist": ("Human Resources", "HR Specialist"),
    "it technical support": ("IT", "IT Technical Support"),
    "admin supervisor": ("Offshore Admin & Management", "Admin Supervisor"),
    "offshore pmo": ("Offshore Admin & Management", "Offshore PMO"),
    "ajm pharmacy manager": ("Pharmacy", "AJM Pharmacy Manager"),
    "dubai pharmacy manager": ("Pharmacy", "Dubai Pharmacy Manager"),
    "shj pharmacy manager": ("Pharmacy", "SHJ Pharmacy Manager"),
    "fp&a manager": ("Finance", "FP&A Manager"),
    "finance controller": ("Finance", "Finance Controller"),
    "general accountant": ("Finance", "General Accountant"),
    "head of accounts payable": ("Finance", "Head of Accounts Payable"),
    "head of accounts receivable": ("Finance", "Head of Accounts Receivable"),
    "head of taxation": ("Finance", "Head of Taxation"),
    "head of treasury": ("Finance", "Head of Treasury"),
    "cfo": ("Finance", "CFO"),
    "group claims operations manager": ("RCM", "Group Claims Operations Manager"),
    "group clinical revenue manager": ("RCM", "Group Clinical Revenue Manager"),
    "rcm manager shj, ajm": ("RCM", "RCM Manager SHJ, AJM"),
    "group rcm director": ("RCM", "Group RCM Director"),
    "group crm director": ("CRM", "Group CRM Director"),
    "sgh uae group nursing director": ("Nursing", "SGH UAE Group Nursing Director"),
    "enterprise project management office manager": ("PMO", "Enterprise Project Management Office Manager"),
    "sgh uae group pharmacy director": ("Pharmacy", "SGH UAE Group Pharmacy Director"),
}


def resolve_canonical_team_name(
    raw_team: str | None,
    *,
    prompt: str = "",
    scope: dict[str, Any] | None = None,
    region: str | None = None,
) -> str | None:
    """Resolve a team name or alias to its canonical PMS team without merging country-specific scopes."""
    cand = str(raw_team or "").strip()
    if not cand:
        return None
    cand_lower = cand.casefold()
    prompt_lower = str(prompt or "").casefold()

    eff_region = str(region or "").strip().upper()
    if not eff_region and scope:
        raw_regs = scope.get("accessible_regions") or scope.get("allowed_regions") or []
        regs = [str(r).strip().upper() for r in raw_regs if str(r).strip()]
        if len(regs) == 1 and regs[0] in ("EGY", "UAE"):
            eff_region = regs[0]
    if not eff_region:
        if re.search(r"\b(egypt|egy)\b", prompt_lower):
            eff_region = "EGY"
        elif re.search(r"\b(uae|dubai|sharjah|ajman)\b", prompt_lower):
            eff_region = "UAE"

    # Country-disambiguated pairs first
    if cand_lower in ("coding egy", "egypt coding", "coding in egypt"):
        return "Coding EGY"
    if cand_lower == "coding":
        return "Coding EGY" if eff_region == "EGY" else "Coding"

    if cand_lower in ("submission egy", "egypt submission", "submission in egypt"):
        return "Submission EGY"
    if cand_lower == "submission":
        return "Submission EGY" if eff_region == "EGY" else "Submission"

    if cand_lower in ("resubmission egy", "egypt resubmission", "resubmission in egypt"):
        return "Resubmission"
    if cand_lower == "resubmission":
        return "Re-Submission" if eff_region == "UAE" else "Resubmission"
    if cand_lower in ("re-submission", "re submission"):
        return "Resubmission" if eff_region == "EGY" else "Re-Submission"

    if cand_lower in ("pre-approvals ip offshore", "offshore pre-approvals", "pre-approvals offshore"):
        return "Pre-Approvals IP Offshore"
    if cand_lower in ("pre-approvals ip", "pre approvals ip", "egypt pre-approvals ip", "pre-approvals ip egy"):
        return "Pre-Approvals IP"

    for canonical, aliases in TEAM_ENGLISH_ALIASES.items():
        if cand_lower == canonical.casefold() or cand_lower in aliases:
            return canonical
    return cand


# Incomplete on purpose: a pending reviewer cannot pass. Tests and fixture
# versions below are files that exist in this repo. No review date is recorded
# because nobody has signed these scopes.
_CALL_CENTER_EVIDENCE = CatalogEvidence(
    state="partial",
    tests=("Backend/tests/test_ai_workspace.py",),
    fixture_or_source_version="pms-ai-english-eval-v1",
    reviewed_on="",
    reviewer="pending",
)
_DEFINITION_EVIDENCE = CatalogEvidence(
    state="partial",
    tests=("Backend/tests/test_ai_workspace.py",),
    fixture_or_source_version="",
    reviewed_on="",
    reviewer="pending",
)
_BSC_REGISTRATION_EVIDENCE = CatalogEvidence(
    state="partial",
    tests=("Backend/tests/test_ai_full_coverage_egy_uae.py",),
    fixture_or_source_version="",
    reviewed_on="",
    reviewer="pending",
)
_BLOCKED_EVIDENCE = CatalogEvidence(state="blocked", reviewer="pending")

_TEAM_EVIDENCE: dict[str, CatalogEvidence] = {
    "Inbound": _CALL_CENTER_EVIDENCE,
    "Outbound": _CALL_CENTER_EVIDENCE,
    "Support Positions": _CALL_CENTER_EVIDENCE,
    "Call Center": _CALL_CENTER_EVIDENCE,
    "Pre-Approvals IP Offshore": _DEFINITION_EVIDENCE,
    "Marketing": _DEFINITION_EVIDENCE,
    "Pharmacy": _DEFINITION_EVIDENCE,
    "Finance": _BSC_REGISTRATION_EVIDENCE,
    "RCM": _BSC_REGISTRATION_EVIDENCE,
    "CRM": _BSC_REGISTRATION_EVIDENCE,
    "Nursing": _BSC_REGISTRATION_EVIDENCE,
    "PMO": _BSC_REGISTRATION_EVIDENCE,
}


def evidence_for_team(team_name: str) -> CatalogEvidence:
    """Evidence on file for a team. Unknown teams stay blocked."""
    return _TEAM_EVIDENCE.get(str(team_name or "").strip(), _BLOCKED_EVIDENCE)


def evidence_for_level(team_name: str, level: str, defined_levels: list[str] | tuple[str, ...]) -> CatalogEvidence:
    if str(level or "").strip() not in {str(item) for item in defined_levels}:
        return CatalogEvidence(state="not_applicable", tests=(), fixture_or_source_version="", reviewed_on="", reviewer="")
    return evidence_for_team(team_name)


class PmsAiCatalog:
    """Authoritative PMS AI catalog projected from team configurations and KPI definitions."""

    def __init__(self) -> None:
        self.teams: dict[str, CatalogTeamDefinition] = {}
        self.metrics: dict[str, CatalogMetricDefinition] = {}
        self.metrics_by_team: dict[str, list[CatalogMetricDefinition]] = {}
        self._build()

    def _register_metric(self, metric: CatalogMetricDefinition) -> None:
        evidence = evidence_for_team(metric.team)
        state, _passes = publish_evidence(evidence)
        metric = replace(metric, status=state, evidence=evidence)
        self.metrics[metric.metric_id] = metric
        team_key = metric.team.casefold()
        self.metrics_by_team.setdefault(team_key, []).append(metric)
        if team_key == "call center" and metric.position:
            self.metrics_by_team.setdefault("support positions", []).append(metric)

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
            positions_list: list[str] = []
            if isinstance(emp_level, dict) and isinstance(emp_level.get("positions"), dict):
                positions_list.extend(str(p) for p in emp_level["positions"].keys())
            if isinstance(levels_dict, dict):
                for lvl_cfg in levels_dict.values():
                    if isinstance(lvl_cfg, dict) and isinstance(lvl_cfg.get("positions"), dict):
                        for p in lvl_cfg["positions"].keys():
                            if str(p) not in positions_list:
                                positions_list.append(str(p))
            positions = tuple(positions_list)
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
                "pre-approvals op dubai",
                "pre-approvals op final shjajm",
                "pre-approvals ip final dubai",
                "pre-approvals ip final shjajm",
                "pre-approvals ip elective dubai",
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
            if team_name == "Call Center":
                self.teams["Support Positions"] = CatalogTeamDefinition(
                    team="Support Positions",
                    db_name="Call Center",
                    function="Call Center",
                    region=region,
                    positions=positions,
                    performance_levels=("Employee",),
                    supports_branches=supports_branches,
                    aliases=TEAM_ENGLISH_ALIASES["Support Positions"],
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

        # Register UAE Pre-Approvals UI rollup teams so both rollup names and exact DB names resolve
        rollup_team_sources = {
            "Pre-Approvals OP Final": ("Pre-Approvals OP Dubai", "Pre-Approvals OP Final SHJAJM"),
            "Pre-Approvals IP Final": ("Pre-Approvals IP Final Dubai", "Pre-Approvals IP Final SHJAJM"),
            "Pre-Approvals IP Elective": ("Pre-Approvals IP Elective Dubai",),
        }
        for rollup_name, source_teams in rollup_team_sources.items():
            rollup_positions: list[str] = []
            for src_t in source_teams:
                src_def = self.teams.get(src_t)
                if src_def:
                    for p in src_def.positions:
                        if p not in rollup_positions:
                            rollup_positions.append(p)
            self.teams[rollup_name] = CatalogTeamDefinition(
                team=rollup_name,
                db_name=source_teams[0],
                function="RCM",
                region="UAE",
                positions=tuple(rollup_positions),
                performance_levels=("Employee",),
                supports_branches=True,
                aliases=TEAM_ENGLISH_ALIASES.get(rollup_name, (rollup_name.casefold(),)),
            )
            for src_t in source_teams:
                for m in list(self.metrics_by_team.get(src_t.casefold(), [])):
                    self.metrics_by_team.setdefault(rollup_name.casefold(), []).append(m)

        # Register Corporate BSC teams & KPIs from ManagementKPIConfig
        for corp_team, corp_info in CORPORATE_BSC_CATALOG_TEAMS.items():
            corp_db_name = str(corp_info.get("db_name") or corp_team)
            corp_region = str(corp_info.get("region") or "UAE")
            corp_positions = [str(p) for p in (corp_info.get("positions") or []) if p]
            fn_name = function_for_team(corp_team) or corp_team
            existing_def = self.teams.get(corp_team)
            if existing_def is not None:
                merged_levels = list(existing_def.performance_levels)
                if "Corporate" not in merged_levels:
                    merged_levels.append("Corporate")
                merged_positions = list(existing_def.positions)
                for p in corp_positions:
                    if p not in merged_positions:
                        merged_positions.append(p)
                self.teams[corp_team] = CatalogTeamDefinition(
                    team=existing_def.team,
                    db_name=existing_def.db_name,
                    function=existing_def.function,
                    region=existing_def.region,
                    positions=tuple(merged_positions),
                    performance_levels=tuple(merged_levels),
                    supports_branches=existing_def.supports_branches,
                    aliases=existing_def.aliases,
                )
            else:
                self.teams[corp_team] = CatalogTeamDefinition(
                    team=corp_team,
                    db_name=corp_db_name,
                    function=fn_name,
                    region=corp_region,
                    positions=tuple(corp_positions),
                    performance_levels=("Corporate",),
                    supports_branches=corp_region.upper() == "UAE",
                    aliases=TEAM_ENGLISH_ALIASES.get(corp_team, (corp_team.casefold(),)),
                )
            corp_slug = _slugify(corp_team)
            for kpi_row in corp_info.get("kpis") or []:
                if not isinstance(kpi_row, dict):
                    continue
                raw_w = float(kpi_row.get("weight") or 0.0)
                is_track = raw_w <= 0.0005
                self._ingest_kpi_dict(
                    kpi={
                        "key": kpi_row.get("key"),
                        "label": kpi_row.get("label"),
                        "weight": 0.0 if is_track else raw_w,
                        "unit": kpi_row.get("unit") or "%",
                        "direction": kpi_row.get("direction") or "higher_better",
                        "perspective": kpi_row.get("perspective"),
                    },
                    team_name=corp_team,
                    team_slug=corp_slug,
                    fn_name=fn_name,
                    position=corp_positions[0] if len(corp_positions) == 1 else None,
                    performance_level="Corporate",
                    is_tracking_indicator=is_track,
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
                    value_kind="diagnostic_indicator",
                    storage_scale="raw",
                    aggregation="weighted_average",
                    available_operations=("current_value", "compare_periods", "compare_branches", "trend"),
                )
            )

        # Register explicit Call Center count / volume metrics and overall score metrics (Section 5.2)
        for cc_team in ("Inbound", "Outbound"):
            t_slug = cc_team.casefold()
            self._register_metric(
                CatalogMetricDefinition(
                    metric_id=f"{t_slug}:bookings_count",
                    kpi_key="TotalBookings",
                    display_name="Bookings (Count)",
                    team=cc_team,
                    function="Call Center",
                    position=None,
                    performance_level="Employee",
                    weight_percent=0.0,
                    unit="count",
                    direction="higher_better",
                    aggregation_method="sum",
                    contributes_to_score=False,
                    tracking_only_note=(
                        "Bookings (Count) measures total bookings by destination branch or agent "
                        "and is distinct from Booking Rate (Bookings / Handled Calls)."
                    ),
                    aliases=(
                        # NOTE (Task 2): bare "bookings" and singular "booking
                        # count" belong to the counter, not the Booking Rate.
                        # Without them a bare booking-count question had no
                        # exact alias and fell through to the rate metric.
                        "bookings",
                        "bookings count",
                        "booking count",
                        "total bookings",
                        "number of bookings",
                        "booking volume",
                        "more bookings",
                        "most bookings",
                    ),
                    value_kind="count",
                    storage_scale="raw",
                    aggregation="sum",
                    available_operations=("current_value", "compare_periods", "compare_branches", "trend", "ranking"),
                )
            )
            self._register_metric(
                CatalogMetricDefinition(
                    metric_id=f"{t_slug}:attended_count",
                    kpi_key="AttendedPatients",
                    display_name="Attended Bookings (Count)",
                    team=cc_team,
                    function="Call Center",
                    position=None,
                    performance_level="Employee",
                    weight_percent=0.0,
                    unit="count",
                    direction="higher_better",
                    aggregation_method="sum",
                    contributes_to_score=False,
                    tracking_only_note="Attended Bookings (Count) measures total attended patient appointments.",
                    aliases=(
                        "attended count",
                        # NOTE (Task 2): "attended bookings" is also the count
                        # of attended appointments. It stays an alias of the
                        # Attendance Rate too; find_metric_definition prefers
                        # the count metric when the question carries a count
                        # cue ("how many attended bookings?").
                        "attended bookings",
                        "attended bookings count",
                        "total attended",
                        "attended patients",
                    ),
                    value_kind="count",
                    storage_scale="raw",
                    aggregation="sum",
                    available_operations=("current_value", "compare_periods", "compare_branches", "trend", "ranking"),
                )
            )
            self._register_metric(
                CatalogMetricDefinition(
                    metric_id=f"{t_slug}:handled_calls_count",
                    kpi_key="HandledCalls",
                    display_name="Handled Calls (Count)",
                    team=cc_team,
                    function="Call Center",
                    position=None,
                    performance_level="Employee",
                    weight_percent=0.0,
                    unit="count",
                    direction="higher_better",
                    aggregation_method="sum",
                    contributes_to_score=False,
                    tracking_only_note="Handled Calls (Count) measures total call volume.",
                    aliases=("handled calls", "handled calls count", "call volume", "total calls"),
                    value_kind="count",
                    storage_scale="raw",
                    aggregation="sum",
                    available_operations=("current_value", "compare_periods", "compare_branches", "trend", "ranking"),
                )
            )

        self._register_metric(
            CatalogMetricDefinition(
                metric_id="inbound:abandoned_calls_count",
                kpi_key="AbandonedCalls",
                display_name="Abandoned Calls (Count)",
                team="Inbound",
                function="Call Center",
                position=None,
                performance_level="Employee",
                weight_percent=0.0,
                unit="count",
                direction="lower_better",
                aggregation_method="sum",
                contributes_to_score=False,
                tracking_only_note=(
                    "Abandoned Calls (Count) is raw abandoned call volume and is distinct from "
                    "Abandon Rate (Abandoned Calls / Offered Calls)."
                ),
                aliases=("abandoned calls count", "number of abandoned calls", "total abandoned calls"),
                value_kind="count",
                storage_scale="raw",
                aggregation="sum",
                available_operations=("current_value", "compare_periods", "trend", "ranking"),
            )
        )

        for t_def in list(self.teams.values()):
            t_slug_score = _slugify(t_def.team)
            for lvl in t_def.performance_levels:
                m_id = (
                    f"{t_slug_score}:overall_score"
                    if lvl == "Employee"
                    else f"{t_slug_score}:{lvl.casefold()}:overall_score"
                )
                if m_id in self.metrics:
                    continue
                self._register_metric(
                    CatalogMetricDefinition(
                        metric_id=m_id,
                        kpi_key="OverallScore",
                        display_name="Overall Weighted PMS Score",
                        team=t_def.team,
                        function=t_def.function,
                        position=None,
                        performance_level=lvl,
                        weight_percent=100.0,
                        unit="%",
                        direction="higher_better",
                        aggregation_method="average",
                        contributes_to_score=True,
                        aliases=("overall score", "weighted score", "pms score", "total score", "scorecard score"),
                        value_kind="score",
                        storage_scale="percent_0_100",
                        aggregation="simple_average",
                        available_operations=(
                            "current_value",
                            "compare_periods",
                            "compare_branches",
                            "compare_teams",
                            "trend",
                            "ranking",
                            "person_summary",
                            "person_best_period",
                            "person_worst_period",
                        ),
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

        unit_lower = unit.casefold()
        if not contributes:
            val_kind: MetricValueKindType = "diagnostic_indicator"
            scale = "raw" if unit != "%" else "ratio_0_1"
            agg_sem = "simple_average"
        elif unit_lower in ("min", "minutes", "sec", "seconds", "hrs", "hours"):
            val_kind = "duration"
            scale = "raw"
            agg_sem = "weighted_average"
        elif unit_lower in ("aed", "usd", "egp", "sar"):
            val_kind = "currency"
            scale = "raw"
            agg_sem = "simple_average"
        elif unit_lower in ("count", "leads", "bookings", "calls", "claims"):
            val_kind = "count"
            scale = "raw"
            agg_sem = "sum"
        elif agg_method == "ratio":
            val_kind = "rate"
            scale = "ratio_0_1"
            agg_sem = "ratio_of_sums"
        else:
            val_kind = "rate"
            scale = "ratio_0_1"
            agg_sem = "simple_average"

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
                value_kind=val_kind,
                storage_scale=scale,
                aggregation=agg_sem,
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
            # NOTE (Task 2): the bare noun "bookings" is deliberately NOT a
            # Booking Rate alias. A bare "bookings" denotes a count, so it
            # lives on the Bookings (Count) metric; otherwise every booking
            # count question ("How many Clinics bookings?") resolved to the
            # Booking Rate percentage instead of the authorised counter.
            items.update({"booking rate", "booking conversion", "booking cr"})
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

        shorthand_map = {
            "marketing:mb_cpl": "marketing:media_buyer:cpl",
            "mb_cpl": "marketing:media_buyer:cpl",
            "marketing:mb_leads": "marketing:media_buyer:leads",
            "mb_leads": "marketing:media_buyer:leads",
            "marketing:gd_rework": "marketing:graphic_designer:rework_percentage",
            "gd_rework": "marketing:graphic_designer:rework_percentage",
            "marketing:sms_response_time": "marketing:social_media_specialist:response_time",
            "sms_response_time": "marketing:social_media_specialist:response_time",
            "pharmacy:ajm_pharmacy_man_iv_cost_saving": "pharmacy:ajm_pharmacy_manager:iv_cost_saving",
            "ajm_pharmacy_man_iv_cost_saving": "pharmacy:ajm_pharmacy_manager:iv_cost_saving",
            "pharmacy:waitingtime": "pharmacy:waiting_time",
            "waitingtime": "pharmacy:waiting_time",
            "pharmacy:tendercompliance": "pharmacy:tender_compliance",
            "tendercompliance": "pharmacy:tender_compliance",
            "pharmacy:atv": "pharmacy:average_transaction_value",
            "atv": "pharmacy:average_transaction_value",
            "pre_approvals_ip_offshore:policyrejection": "pre_approvals_ip_offshore:policy_rejection_rate",
            "policyrejection": "pre_approvals_ip_offshore:policy_rejection_rate",
            "pre_approvals_ip_offshore:rejection": "pre_approvals_ip_offshore:rejection_rate",
            "rejection": "pre_approvals_ip_offshore:rejection_rate",
            "inbound:team_sla": "inbound:managerial:team_sla",
            "outbound:team_sla": "outbound:managerial:team_sla",
            "coding:team_sla": "coding:managerial:team_sla",
            "inbound:attendance_compliance": "inbound:managerial:attendance_compliance",
            "outbound:attendance_compliance": "outbound:managerial:attendance_compliance",
        }
        mapped_id = shorthand_map.get(needle)
        if mapped_id and mapped_id in self.metrics:
            return self.metrics[mapped_id]

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
        # Substring fallback: pick the best match, not the first metric in
        # team order. A short alias of an early metric ("booking" on Booking
        # Rate) used to win over the longer, more specific alias of the metric
        # the user actually asked about ("bookings" on Bookings (Count)), so
        # every booking-count question resolved to a rate. Prefer, in order:
        #   1. a count metric when the question carries a count cue
        #      ("how many", "count", "number of", "total", "volume", ...),
        #      or a non-count metric when it carries only a rate cue;
        #   2. the longest matching alias;
        #   3. the earliest metric in team order (stable tie-break).
        count_cue = bool(
            re.search(
                r"\b(?:how many|count|counts|number of|total|volume|most|fewest|fewer|least|many)\b",
                needle,
            )
        )
        rate_cue = bool(
            re.search(r"\b(?:rate|ratio|conversion|percentage|percent|achievement)\b|%", needle)
        )
        best: tuple[int, int, int, CatalogMetricDefinition] | None = None
        for order, m in enumerate(candidates):
            longest = 0
            for alias in m.aliases:
                if len(alias) >= 3 and (alias in needle or needle in alias):
                    longest = max(longest, len(alias))
            if not longest:
                continue
            kind_rank = 0
            if count_cue and m.value_kind == "count":
                kind_rank = 1
            elif rate_cue and not count_cue and m.value_kind != "count":
                kind_rank = 1
            key = (kind_rank, longest, -order)
            if best is None or key > best[:3]:
                best = (*key, m)
        return best[3] if best is not None else None

    def _scope_row(self, t_name: str) -> dict[str, Any]:
        """One scope row. ``certified`` is true only when published evidence passes."""
        t_def = self.teams.get(t_name) or self.teams.get(t_name.casefold())
        fn_name = t_def.function if t_def else (function_for_team(t_name) or t_name)
        t_metrics = self.metrics_by_team.get(t_name.casefold(), [])
        scored_metrics = [m for m in t_metrics if m.contributes_to_score]
        tracking_metrics = [m for m in t_metrics if not m.contributes_to_score]
        perf_levels = list(t_def.performance_levels) if t_def else ["Employee"]
        cfg = get_ai_runtime_config()
        is_enabled = bool(cfg.is_scope_enabled(t_name) or cfg.is_scope_enabled(fn_name))
        region_name = t_def.region if t_def else (canonical_team_region(t_name) or "UAE")
        # Shared All-region Finance/RCM rows have no reviewed country attribution.
        if str(region_name).strip().casefold() == "all" or canonical_team_region(t_name) == "All":
            evidence = CatalogEvidence(state="blocked", reviewer="pending")
        else:
            looked_up = get_capability_evidence(
                country=canonical_team_region(t_name) or region_name,
                function=fn_name,
                team=t_name,
                performance_level="Employee",
                operation_family="operational_summary",
            )
            mapped = {
                "verified": "verified",
                "verified_no_data": "verified_no_data",
                "partial_evidence": "partial",
                "partial": "partial",
                "unverified": "blocked",
                "unsupported": "not_applicable",
            }.get(looked_up.state, "blocked")
            tests = (looked_up.evidence_ref,) if str(looked_up.evidence_ref).startswith("Backend/tests/") else ()
            # validated_at is not a reviewer sign-off. Pending review cannot pass.
            evidence = CatalogEvidence(
                state=mapped,
                tests=tests,
                fixture_or_source_version="",
                reviewed_on="",
                reviewer="pending",
            )
        state, passes = publish_evidence(evidence)
        level_rows: list[dict[str, Any]] = []
        for lvl in perf_levels:
            if lvl == "Employee":
                lvl_evidence = evidence
            elif lvl not in perf_levels:
                lvl_evidence = CatalogEvidence(state="not_applicable", reviewer="")
            else:
                lvl_evidence = CatalogEvidence(state="blocked", reviewer="pending")
            lvl_state, lvl_passes = publish_evidence(lvl_evidence)
            level_rows.append(
                {
                    "level": lvl,
                    "evidence_state": lvl_state,
                    "passes": lvl_passes,
                    "certified": lvl_passes,
                    "evidence": evidence_dict(lvl_evidence),
                }
            )
        verified_levels = [row["level"] for row in level_rows if row["passes"]]
        unverified_levels = [lvl for lvl in perf_levels if lvl not in verified_levels]
        gates = {
            "source_mappings": passes,
            "metric_semantics": passes,
            "calculations": passes,
            "permissions": passes,
            "periods": passes,
            "destination_links": passes,
        }
        return {
            "team": t_name,
            "db_name": t_def.db_name if t_def else t_name,
            "function": fn_name,
            "region": t_def.region if t_def else (canonical_team_region(t_name) or "UAE"),
            "corporate_region": canonical_team_region(t_name, performance_level="Corporate") if "Corporate" in perf_levels else None,
            "positions": list(t_def.positions) if t_def else [],
            "performance_levels": perf_levels,
            "verified_levels": verified_levels,
            "unverified_levels": unverified_levels,
            "supports_branches": bool(t_def.supports_branches) if t_def else False,
            "scored_kpi_count": len(scored_metrics),
            "tracking_only_kpi_count": len(tracking_metrics),
            "enabled": is_enabled,
            "certified": passes,
            "passes": passes,
            "certification_status": state,
            "status": state,
            "evidence_state": state,
            "evidence": evidence_dict(evidence),
            "level_evidence": level_rows,
            "verification_gates": gates,
        }

    def get_scope_certification_registry(self) -> list[dict[str, Any]]:
        """Scope matrix. ``certified`` follows published evidence and is not a default."""
        ordered_teams = [
            "Inbound",
            "Outbound",
            "Support Positions",
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
        return [self._scope_row(t_name) for t_name in ordered_teams]

    def get_full_coverage_scope_registry(self) -> list[dict[str, Any]]:
        """Full EGY, UAE, shared, and Corporate BSC registry. Same evidence rule as the scope matrix."""
        ordered_full_teams = [
            "Inbound",
            "Outbound",
            "Support Positions",
            "Call Center",
            "Coding",
            "Coding EGY",
            "Submission",
            "Submission EGY",
            "Re-Submission",
            "Resubmission",
            "Pre-Approvals IP",
            "Pre-Approvals IP Offshore",
            "Pre-Approvals OP Dubai",
            "Pre-Approvals OP Final SHJAJM",
            "Pre-Approvals IP Final Dubai",
            "Pre-Approvals IP Final SHJAJM",
            "Pre-Approvals IP Elective Dubai",
            "Pre-Approvals OP Final",
            "Pre-Approvals IP Final",
            "Pre-Approvals IP Elective",
            "Marketing",
            "Pharmacy",
            "CSR",
            "Sales",
            "Finance",
            "RCM",
            "Human Resources",
            "IT",
            "Offshore Admin & Management",
            "CRM",
            "Nursing",
            "PMO",
        ]
        return [self._scope_row(t_name) for t_name in ordered_full_teams]

    def get_eligible_scope_options(
        self,
        scope: dict[str, Any],
        *,
        active_function: str | None = None,
    ) -> dict[str, list[str]]:
        cfg = get_ai_runtime_config()
        fn_norm = str(active_function or "").strip().casefold()

        # Candidate teams ordered with Call Center first, covering EGY, UAE, Shared, and Corporate BSC
        ordered_teams = [
            "Inbound",
            "Outbound",
            "Support Positions",
            "Coding",
            "Coding EGY",
            "Submission",
            "Submission EGY",
            "Re-Submission",
            "Resubmission",
            "Pre-Approvals IP",
            "Pre-Approvals OP Final",
            "Pre-Approvals IP Final",
            "Pre-Approvals IP Elective",
            "Pre-Approvals IP Offshore",
            "Pre-Approvals OP Dubai",
            "Pre-Approvals OP Final SHJAJM",
            "Pre-Approvals IP Final Dubai",
            "Pre-Approvals IP Final SHJAJM",
            "Pre-Approvals IP Elective Dubai",
            "Marketing",
            "Pharmacy",
            "CSR",
            "Sales",
            "Finance",
            "RCM",
            "Human Resources",
            "IT",
            "Offshore Admin & Management",
            "CRM",
            "Nursing",
            "PMO",
        ]
        corporate_only_teams = {"CRM", "Nursing", "PMO"}
        eligible_teams: list[AiEligibleTeamItem] = []
        eligible_functions_set: list[str] = []
        for t in ordered_teams:
            lvl_check = "Corporate" if t in corporate_only_teams else None
            if not user_can_access_team(scope, t, performance_level=lvl_check):
                continue
            fn_for_t = function_for_team(t) or t
            if not cfg.is_scope_enabled(t) and not cfg.is_scope_enabled(fn_for_t):
                continue
            if fn_for_t not in eligible_functions_set:
                eligible_functions_set.append(fn_for_t)
            if fn_norm and fn_norm not in ("all", "") and fn_for_t.casefold() != fn_norm and t.casefold() != fn_norm:
                continue
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

        role = str(scope.get("role") or "")
        if role == "Branch Director":
            eligible_levels = ["Employee"]
        else:
            candidate_team_names = [t.value for t in eligible_teams] or ["Inbound"]
            eligible_levels = [
                lvl
                for lvl in ("Employee", "Managerial", "Corporate")
                if any(user_can_access_team_level(scope, t_name, lvl) for t_name in candidate_team_names)
            ] or ["Employee"]
        return {
            "eligible_teams": eligible_teams,
            "eligible_functions": eligible_functions_set,
            "eligible_branches": eligible_branches,
            "eligible_levels": eligible_levels,
        }

    def get_authorized_catalog_payload(self, scope: dict[str, Any]) -> AiCatalogPayload:
        eligible = self.get_eligible_scope_options(scope)
        eligible_team_names = {t.value.casefold() for t in eligible["eligible_teams"]}
        eligible_levels_set = {lvl.casefold() for lvl in eligible["eligible_levels"]}
        metrics_out: list[AiCatalogMetricItem] = []
        for m in self.metrics.values():
            t_norm = m.team.casefold()
            if t_norm not in eligible_team_names and not (t_norm == "call center" and "support positions" in eligible_team_names):
                continue
            if m.performance_level.casefold() not in eligible_levels_set:
                continue
            state, passes = publish_evidence(m.evidence)
            metrics_out.append(
                AiCatalogMetricItem(
                    metric_id=m.metric_id,
                    kpi_key=m.kpi_key,
                    display_name=m.display_name,
                    team="Support Positions" if (t_norm == "call center" and m.position) else m.team,
                    function=m.function,
                    position=m.position,
                    performance_level=m.performance_level,
                    value_kind=m.value_kind,
                    unit=m.unit,
                    storage_scale=m.storage_scale,
                    direction=m.direction,
                    aggregation=m.aggregation,
                    weight_percent=m.weight_percent,
                    contributes_to_score=m.contributes_to_score,
                    available_operations=list(m.available_operations),
                    status=state,  # type: ignore[arg-type]
                    evidence=AiCatalogEvidence(**evidence_dict(m.evidence)),
                    evidence_passes=passes,
                )
            )
        capabilities = [
            row
            for row in self.get_scope_certification_registry()
            if row["team"].casefold() in eligible_team_names
        ]
        return AiCatalogPayload(
            eligible_teams=eligible["eligible_teams"],
            eligible_functions=eligible["eligible_functions"],
            eligible_branches=eligible["eligible_branches"],
            eligible_levels=eligible["eligible_levels"],
            metrics=metrics_out,
            capabilities=capabilities,
        )


_CATALOG_LOCK = threading.Lock()
_CATALOG_INSTANCE: PmsAiCatalog | None = None
_CATALOG_CONFIG_VERSION: int | None = None


def get_ai_catalog() -> PmsAiCatalog:
    global _CATALOG_INSTANCE, _CATALOG_CONFIG_VERSION
    current_cfg_ver = CacheInvalidationService.get_config_version()
    if _CATALOG_INSTANCE is None or _CATALOG_CONFIG_VERSION != current_cfg_ver:
        with _CATALOG_LOCK:
            if _CATALOG_INSTANCE is None or _CATALOG_CONFIG_VERSION != current_cfg_ver:
                _CATALOG_INSTANCE = PmsAiCatalog()
                _CATALOG_CONFIG_VERSION = current_cfg_ver
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
        eval_id: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        scope_id = _scope_identity(scope)
        data_ver = CacheInvalidationService.get_data_version()
        cfg_ver = CacheInvalidationService.get_config_version()
        resolved_eval_id = eval_id if eval_id is not None else evaluation_cache_identity(db)
        envelope = {
            "q": query_signature,
            "scope": scope_id,
            "data_ver": data_ver,
            "cfg_ver": cfg_ver,
            "eval_id": resolved_eval_id,
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
        eval_id: str | None = None,
    ) -> Any | None:
        key, caller_scope_id = self.build_key(
            db=db,
            scope=scope,
            query_signature=query_signature,
            eval_id=eval_id,
        )
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            cached_scope_id, payload = entry
            # Explicit post-lookup access verification: never serve across mismatched scopes
            if cached_scope_id != caller_scope_id:
                return None
            return copy.deepcopy(payload)

    def set(
        self,
        *,
        db: Session,
        scope: dict[str, Any],
        query_signature: dict[str, Any],
        payload: Any,
        eval_id: str | None = None,
    ) -> str:
        key, caller_scope_id = self.build_key(
            db=db,
            scope=scope,
            query_signature=query_signature,
            eval_id=eval_id,
        )
        with self._lock:
            if len(self._store) >= self._max_entries:
                oldest_key = next(iter(self._store))
                self._store.pop(oldest_key, None)
            self._store[key] = (caller_scope_id, copy.deepcopy(payload))
        return key

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


ai_evidence_cache = AiScopedEvidenceCache()

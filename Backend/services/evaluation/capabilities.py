"""Server-owned calculation capability for monthly evaluation edits.

A registered importer or a higher-is-better / lower-is-better direction is not
proof that the scoring engine's capped target ratio is the team's formula.
Weight-only editing is also server-owned: a client ``weight_only`` flag cannot
grant it. Weight-only would require trustworthy stored achievement provenance
plus an unchanged policy and cap. ``KPIValue`` stores a numeric achievement
only. It does not store the formula, policy version, or cap that produced that
number, and a workbook achievement column is not that provenance. Until that
store exists, weight-only stays off for every scope.

Enabled employee-ratio scopes, and why:

- Coding / Employee / no position. ``process_coding`` calls
  ``calculate_achievement`` for QualityErrors, Rejection, and TAT, each inverse
  and capped at 100%. ``coding.json`` matches those keys, uses ``lower_better``,
  sets ``capped_at_100``, and declares no ``score_formula`` or achievement column.
- Submission / Employee / no position. ``process_submission`` calls
  ``calculate_achievement`` for both KPIs, capped at 100%. ``submission.json``
  matches the importer inverse flags (``initial_rejection_rate`` lower-is-better,
  ``submission_within_due_date`` higher-is-better) and the same cap, with no
  ``score_formula`` or achievement column. Its ratio aggregation measures the
  rejection rate; it is not a second achievement formula.

Not enabled by this audit (the list is the boundary, not a claim that every
other team was given a formula):

- Pre-Approvals IP Final Dubai and Pre-Approvals IP Final SHJAJM use
  ``baseline_80``, not the target ratio.
- CSR ``Queries`` is inverse in ``process_csr`` and ``higher_better`` in
  ``csr.json``, so the two sources are not one ratio contract.
- Pharmacy reads a precomputed achievement for part of the workbook.
- Outbound, Inbound, Inbound UAE, Re-Submission, Sales, Offshore, OP, and
  IP Elective were not admitted. Several depend on workbook achievement
  columns. Outbound August productivity is a later slice.
- Marketing has no CleanerFactory ratio importer in this gate.
- Outbound Employee with an empty position is not in the map above. It is
  admitted only for July 2026 and August 2026, and only when ``year`` and
  ``month`` are passed through to :func:`decide`. The admission is the
  period-owned decision from ``services.outbound_period_basis.period_capability``
  (capped target ratio, source targets, no August inference). A call with no
  period stays blocked, so the global catalog does not claim every Outbound
  month. ``Backend/config/teams/outbound.json`` stays the technical four-KPI
  file and is not rewritten. Workbook achievement columns on that file are
  not the formula and cannot turn on weight-only edits.

Any scope absent from the audited map stays blocked. A client flag is not an
input and cannot grant a formula.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.evaluation.scoring import SUPPORTED_DIRECTIONS


@dataclass(frozen=True)
class CapabilityDecision:
    edit_mode: str
    reason: str
    weight_only_allowed: bool = False

    @property
    def allows_ratio_edit(self) -> bool:
        return self.edit_mode == "full"


# Baseline directions proven against the importer's inverse flags.
# Admission is this map plus a live config that still matches it.
_AUDITED_RATIO: dict[tuple[str, str, str], dict] = {
    ("coding", "Employee", ""): {
        "directions": {
            "QualityErrors": "lower_better",
            "Rejection": "lower_better",
            "TAT": "lower_better",
        },
        "reason": (
            "Coding Employee is an audited capped target-ratio path: "
            "process_coding uses calculate_achievement for QualityErrors, Rejection, and TAT, "
            "and coding.json matches those inverse directions with capped_at_100 and no alternate formula."
        ),
    },
    ("submission", "Employee", ""): {
        "directions": {
            "initial_rejection_rate": "lower_better",
            "submission_within_due_date": "higher_better",
        },
        "reason": (
            "Submission Employee is an audited capped target-ratio path: "
            "process_submission uses calculate_achievement for both KPIs, "
            "and submission.json matches those directions with capped_at_100 and no alternate formula."
        ),
    },
}


def weight_only_allowed(_kpis: list[dict] | None = None) -> bool:
    """Stored achievement provenance is not available. The client cannot turn this on."""
    return False


# Exact months ``period_capability`` marks as catalog templates. The helper
# remains the gate: a month is admitted only when that decision says so.
OUTBOUND_PERIOD_CANDIDATES = ((2026, 7), (2026, 8))
_OUTBOUND_FILE_KEYS = ("Attendance", "Booking", "Quality", "Other")


def is_outbound_employee_scope(team_name: str, level: str, position: str | None) -> bool:
    """True for the only Outbound scope this gate can admit."""
    return _norm(team_name) == "outbound" and str(level or "") == "Employee" and (position or "") == ""


def admitted_outbound_periods() -> tuple[dict, ...]:
    """July 2026 and August 2026 when the period helper still admits them.

    The global catalog lists these periods. It does not mark the scope supported
    for every other month.
    """
    from services.outbound_period_basis import period_capability

    found = []
    for year, month in OUTBOUND_PERIOD_CANDIDATES:
        decision = period_capability(year, month)
        if decision.get("catalog_template_supported") and decision.get("approved_binding") == "apply":
            found.append({"year": year, "month": month, "status": decision.get("status")})
    return tuple(found)


def _norm(value: str) -> str:
    return str(value or "").casefold().replace(" ", "_").replace("-", "_").replace("preapprovals", "pre_approvals")


def _blocked(reason: str) -> CapabilityDecision:
    return CapabilityDecision(edit_mode="blocked", reason=reason, weight_only_allowed=False)


def _unsupported_formula_reason(kpis: list[dict]) -> str | None:
    found = []
    for kpi in kpis:
        formula = str(kpi.get("score_formula") or "").strip()
        if formula and formula != "target_ratio":
            found.append(f"{kpi.get('key') or 'kpi'}={formula}")
    if not found:
        return None
    listed = ", ".join(found)
    return (
        "Unsupported calculation "
        + listed
        + ". Target and direction edits are blocked. "
        "Weight-only edits stay blocked until stored achievement provenance exists, "
        "and a client weight_only flag cannot grant them."
    )


def _outbound_file_mismatch(kpis: list[dict]) -> str | None:
    """Checked-in Outbound file must still be the capped higher-is-better baseline.

    Productivity is period-owned and is allowed to be absent from the file.
    A workbook achievement column is ignored here: the period basis scores
    actual against target with the employee cap. That column is not permission
    for weight-only edits.
    """
    if not kpis:
        return "No technical baseline is checked in for Outbound Employee."
    seen = set()
    for kpi in kpis:
        key = str(kpi.get("key") or "")
        seen.add(key)
        if str(kpi.get("direction") or "") != "higher_better":
            return (
                "Checked-in Outbound directions do not match the audited capped target ratio. "
                "The scope stays blocked rather than assuming the engine formula."
            )
        capping = str(kpi.get("capping") or "capped_at_100")
        if capping != "capped_at_100":
            return f"Cap {capping} is not the audited 100% cap."
        if kpi.get("cap_achievement") is False:
            return "The audited 100% cap is turned off in the checked-in contract."
    if not set(_OUTBOUND_FILE_KEYS) <= seen:
        return "Checked-in Outbound keys do not cover the audited period contract."
    return None


def _outbound_period_decision(kpis: list[dict], importer_registered: bool, year, month) -> CapabilityDecision:
    """Admit Outbound Employee only for the helper's exact catalog months."""
    if year is None or month is None:
        return _blocked(
            "Outbound Employee is period-dependent. "
            "July 2026 and August 2026 are the only admitted exact months. "
            "This catalog entry does not enable every month, and a client flag cannot grant the formula."
        )
    from services.outbound_period_basis import period_capability

    try:
        decision = period_capability(int(year), month)
    except (TypeError, ValueError):
        return _blocked(
            "Outbound Employee is period-dependent. The requested period is not an exact admitted month."
        )
    period_label = decision.get("period") or "the requested period"
    if (
        not decision.get("catalog_template_supported")
        or decision.get("approved_binding") != "apply"
        or decision.get("infer_from_august")
        or decision.get("silent_fallback")
    ):
        return _blocked(
            f"Outbound Employee is not admitted for {period_label}. "
            "Only July 2026 and August 2026 are admitted. "
            "Later months stay blocked and are not inferred from August or Productivity."
        )
    mismatch = _outbound_file_mismatch(kpis)
    if mismatch:
        return _blocked(mismatch)
    if not importer_registered:
        return _blocked("The audited ratio importer is not registered for this scope.")
    status = decision.get("status")
    return CapabilityDecision(
        edit_mode="full",
        reason=(
            f"Outbound Employee {status} is an audited capped target-ratio path. "
            "period_capability supplies the exact-month lines and source targets. "
            "Workbook achievement columns are not the formula. "
            "Weight-only edits stay blocked, and a client flag cannot grant them."
        ),
        weight_only_allowed=False,
    )


def decide(
    *,
    team_name: str,
    level: str,
    position: str,
    kpis: list[dict],
    importer_registered: bool,
    year: int | None = None,
    month: int | str | None = None,
) -> CapabilityDecision:
    """Return the server edit mode. Caller flags are not an input.

    ``year`` and ``month`` are optional. Omit both and Outbound stays blocked.
    Pass both and only July 2026 or August 2026 Outbound Employee (empty
    position) can be admitted, using ``period_capability``. Coding and
    Submission ignore the period and keep the audited map.
    """
    formula = _unsupported_formula_reason(kpis)
    if formula:
        return _blocked(formula)
    if is_outbound_employee_scope(team_name, level, position):
        return _outbound_period_decision(kpis, importer_registered, year, month)
    key = (_norm(team_name), str(level or ""), position or "")
    audited = _AUDITED_RATIO.get(key)
    if audited is None:
        return _blocked(
            "This scope has no audited employee-ratio proof. "
            "A supported direction or a registered importer is not proof of the ratio formula. "
            "Weight-only edits stay blocked until stored achievement provenance exists."
        )
    if not importer_registered:
        return _blocked("The audited ratio importer is not registered for this scope.")
    directions = {str(kpi.get("key") or ""): str(kpi.get("direction") or "") for kpi in kpis}
    if directions != audited["directions"]:
        return _blocked(
            "Checked-in KPI directions do not match the audited importer ratio contract. "
            "The scope stays blocked rather than assuming the engine formula."
        )
    for kpi in kpis:
        if kpi.get("achievement_col"):
            return _blocked(
                "A workbook achievement column is not stored formula provenance. "
                "Weight-only edits stay blocked."
            )
        if str(kpi.get("direction") or "") not in SUPPORTED_DIRECTIONS:
            return _blocked("The audited contract includes a direction the ratio engine does not score.")
        capping = str(kpi.get("capping") or "capped_at_100")
        if capping != "capped_at_100":
            return _blocked(f"Cap {capping} is not the audited 100% cap.")
        if kpi.get("cap_achievement") is False:
            return _blocked("The audited 100% cap is turned off in the checked-in contract.")
    if weight_only_allowed(kpis):
        return CapabilityDecision(edit_mode="weight_only", reason=audited["reason"], weight_only_allowed=True)
    return CapabilityDecision(edit_mode="full", reason=audited["reason"], weight_only_allowed=False)

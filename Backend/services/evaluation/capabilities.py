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

Any scope absent from the audited map stays blocked.
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


def decide(
    *,
    team_name: str,
    level: str,
    position: str,
    kpis: list[dict],
    importer_registered: bool,
) -> CapabilityDecision:
    """Return the server edit mode. Caller flags are not an input."""
    formula = _unsupported_formula_reason(kpis)
    if formula:
        return _blocked(formula)
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

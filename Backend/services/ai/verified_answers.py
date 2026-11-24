"""Build direct answers from the same scoped scores and rankings PMS displays."""

from __future__ import annotations

import re
from math import isfinite

from models.ai_schemas import StructuredQueryPlan, TypedMetricEvidence
from services.ai.entity_resolver import format_period_label
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext, ToolExecutionResult


def answer_kpi_question(
    kind: str,
    metric: str | None,
    evidence: list[TypedMetricEvidence],
    digests: list[dict],
    show_contributors: bool,
) -> tuple[str, list[str], TypedMetricEvidence | None]:
    def key(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", value.casefold().rsplit(":", 1)[-1])

    metric_key = key(metric or "")
    candidates = [item for item in evidence if not item.employee_id and item.kpi_key != "overall_score"]
    candidate = next((
        item for item in candidates if metric_key and metric_key in {
            key(item.metric_id), key(item.kpi_key), key(item.display_name),
        }
    ), None)
    if kind == "weight":
        if candidate is None:
            return "Which KPI's weight would you like to see?", [], None
        suffix = " Its score contribution is unavailable for this period." if (
            candidate.weight_percent and candidate.achievement_percent is None
        ) else ""
        return (
            f"{candidate.display_name} has a {candidate.weight_percent:g}% configured scorecard weight "
            f"in {candidate.period}.{suffix}", [], candidate,
        )
    measured = [
        item for item in candidates
        if item.contributes_to_score and item.weight_percent > 0 and item.achievement_percent is not None
    ]
    if kind == "gap" or (kind == "impact" and not metric_key):
        if not measured:
            return "No scored KPI with a published actual and target was available for this comparison.", [], None
        if kind == "gap":
            candidate = min(measured, key=lambda item: item.achievement_percent)
        else:
            candidate = max(measured, key=lambda item: item.weight_percent * max(0, 1 - item.achievement_percent / 100))
    if candidate is None:
        return "I couldn't verify the requested KPI in the selected scope and month.", [], None
    if candidate.achievement_percent is None or not candidate.contributes_to_score:
        availability = "I can't verify its score impact" if kind == "impact" else "Its target gap is unavailable"
        if show_contributors:
            availability += " or attribute the gap to employees"
        observation = (
            f"{candidate.display_name} was listed as tracking-only in {candidate.period}."
            if candidate.actual_display.casefold() in {"tracking only", "tracking-only"} else
            f"{candidate.display_name} was {candidate.actual_display} in {candidate.period}."
            if candidate.actual_display else f"{candidate.display_name} had no published actual in {candidate.period}."
        )
        return (
            f"{observation} {availability} from the published evidence.",
            [], candidate,
        )
    gap = max(0, 100 - candidate.achievement_percent)
    if kind == "gap" and not gap:
        return f"All {len(measured)} scored KPIs with comparable targets met their targets in {candidate.period}.", [], None
    headline = (
        f"{candidate.display_name} had the largest measured gap in {candidate.period} at "
        f"{candidate.actual_display} vs {candidate.target_display} target ({candidate.achievement_percent:.1f}% attainment)."
        if kind == "gap" else
        f"{candidate.display_name} was {candidate.actual_display} vs {candidate.target_display} target "
        f"in {candidate.period} ({candidate.achievement_percent:.1f}% attainment, {candidate.weight_percent:g}% weight)."
    )
    notes = []
    if kind == "gap":
        missing = [item.display_name for item in candidates if item.weight_percent and item.achievement_percent is None]
        if missing:
            notes.append(f"Target attainment was unavailable for {', '.join(missing)}.")
    if show_contributors:
        top_rows = next((
            digest.get("top_contributors") or [] for digest in digests
            if key(str(digest.get("kpi_analyzed") or "")) in {key(candidate.display_name), key(candidate.kpi_key)}
        ), [])
        notes.extend(
            f"{row['employee_name']} · {row['achievement_percent']:.1f}% KPI attainment"
            for row in top_rows[:3]
            if row.get("weighted_impact") is not None and row["weighted_impact"] < 0
            and row.get("achievement_percent") is not None
        )
        if not notes:
            notes.append("No employee-level contribution could be verified for this KPI.")
    return headline, notes, candidate


def read_score_comparison(
    registry: DeterministicToolRegistry, plan: StructuredQueryPlan,
) -> ToolExecutionResult:
    by_team = plan.verified_comparison == "team_scores"
    employee_id = plan.employee_id if plan.verified_comparison == "employee_scores" else None
    subjects = (
        [(team, None, plan.periods[0]) for team in plan.comparison_teams]
        if by_team else [(plan.team, plan.function, period) for period in sorted(plan.periods)]
    )
    combined = ToolExecutionResult(
        tool_name="read_verified_score_comparison",
        arguments={"teams": plan.comparison_teams, "periods": plan.periods, "employee_id": employee_id},
    )
    state = registry.ctx.session_state
    if by_team:
        # Neither side should inherit an old team, function, or job-position filter.
        registry = DeterministicToolRegistry(ToolExecutionContext(
            db=registry.ctx.db,
            scope=registry.ctx.scope,
            session_state=state.model_copy(update={"team": None, "function": None, "position": None}),
        ))

    missing = []
    for team, function, period in subjects:
        label = format_period_label(period)
        if not label:
            missing.append("requested month")
            continue
        month, year = label.split()
        filters = dict(
            team=team,
            function=function,
            position=None if by_team else plan.position,
            branch=plan.branch,
            performance_level=plan.performance_level,
            month=month,
            year=int(year),
            kpi="overall_score",
        )
        if employee_id:
            result = registry.execute_agent_spotlight_and_trend(
                **filters, employee_query=employee_id, months_window=1,
            )
        else:
            result = registry.execute_kpi_diagnosis_and_trends(
                **filters, score_measure=getattr(plan, "score_measure", None) or "official",
            )
        combined.resolved_month, combined.resolved_year = month, int(year)
        accepted_teams = {team or function}
        if not by_team and plan.position:
            accepted_teams.add(f"{team or function} · {plan.position}")
        evidence = next((
            entry for entry in result.typed_evidence
            if entry.kpi_key == "overall_score" and entry.period == label
            and (
                (employee_id and entry.employee_id == employee_id)
                or (not employee_id and entry.team in accepted_teams and entry.sample_size)
            )
            and entry.actual is not None and isfinite(entry.actual)
        ), None)
        if evidence is None:
            missing.append(f"{plan.employee_name or team or function or 'the selected employee'} in {label}")
            continue
        combined.typed_evidence.append(evidence)
        combined.records_evaluated += evidence.sample_size or 1
        combined.citations.extend(result.citations)
        combined.deep_links.extend(result.deep_links)
        combined.basis_warning = combined.basis_warning or result.basis_warning

    if missing or len(combined.typed_evidence) != 2:
        combined.digest["missing_periods"] = list(missing)
        partial_note = ""
        if len(combined.typed_evidence) == 1:
            only_ev = combined.typed_evidence[0]
            subj_lbl = only_ev.employee_name or only_ev.team or "the selected scope"
            partial_note = f" Published score for {subj_lbl} in {only_ev.period}: {only_ev.actual:.1f}%."
        combined.digest["comparison_headline"] = (
            f"No published overall score for {', '.join(missing)}. The comparison is unavailable.{partial_note}"
        )
        return combined

    first, second = combined.typed_evidence
    difference = round(second.actual - first.actual, 1)
    points = abs(difference)
    point_label = "percentage point" if points == 1 else "percentage points"
    measure_tag = (
        "average employee score"
        if getattr(plan, "score_measure", "official") == "employee_average" and not employee_id
        else ("Monthly Review score" if not employee_id else "individual score")
    )
    if by_team:
        if difference:
            winner = second.team if difference > 0 else first.team
            conclusion = f"{winner} leads by {points:.1f} {point_label}."
        else:
            conclusion = "The teams tied, with a 0.0 percentage-point difference."
        combined.digest["comparison_headline"] = (
            f"In {first.period}, {first.team} scored {first.actual:.1f}% and "
            f"{second.team} scored {second.actual:.1f}% ({measure_tag}). {conclusion}"
        )
    else:
        movement = (
            f"rose by {points:.1f} {point_label}" if difference > 0
            else f"fell by {points:.1f} {point_label}" if difference < 0
            else "held steady"
        )
        subject = (
            first.employee_name
            or (
                f"{plan.position} ({first.team})"
                if plan.position and first.team and plan.position.casefold() not in first.team.casefold()
                else (plan.position or first.team)
            )
        )
        position = (
            f" Position: {second.position}."
            if plan.include_employee_position and second.position else
            " No position was recorded for the later month." if plan.include_employee_position else ""
        )
        basis_suffix = f" ({measure_tag})" if not employee_id else ""
        combined.digest["comparison_headline"] = (
            f"{subject}'s overall score{basis_suffix} {movement}, from {first.actual:.1f}% "
            f"in {first.period} to {second.actual:.1f}% in {second.period}."
            + position
        )
    combined.digest["verified_answer_family"] = "team_scores" if by_team else "period_scores"
    return combined


def ranked_positions_answer(
    prompt: str,
    digests: list[dict],
    evidence: list[TypedMetricEvidence],
) -> tuple[str, list[str]] | None:
    """Build one concise answer from the authorized ranking and its position evidence."""
    if not re.search(r"\b(?:positions?|titles?|job roles?)\b", prompt, re.IGNORECASE):
        return None
    ranking = next((
        item for digest in digests if (item := digest.get("query_rankings"))
        and item.get("entity") == "employee" and not item.get("groups") and item.get("rows")
    ), None)
    if not ranking:
        return None
    people = {
        (entry.employee_id, entry.period): entry for entry in evidence
        if entry.employee_id and entry.employee_name and entry.actual_display
    }
    rows = []
    for ranked in ranking["rows"]:
        entry = people.get((str(ranked.get("id")), ranking.get("period")))
        if entry is None or not entry.position:
            return None
        rows.append(entry)
    direction = "Top" if ranking["sort_order"] == "desc" else "Lowest"
    scope = f"{ranking['scope']} for {ranking['period']}"
    if len(rows) == 1:
        row = rows[0]
        return (
            f"{direction} employee in {scope} is {row.employee_name} ({row.position}) at {row.actual_display}.",
            [],
        )
    heading = (
        f"{len(rows)} employees tied for {'first' if direction == 'Top' else 'the lowest score'} in {scope}."
        if ranking["limit"] == 1 and all(row.actual == rows[0].actual for row in rows)
        else f"{direction} {len(rows)} employees in {scope}."
    )
    return (
        heading,
        [f"{row.employee_name} · {row.actual_display} · {row.position}" for row in rows],
    )

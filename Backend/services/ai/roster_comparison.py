"""Compare who or what appears in two PMS evaluation periods."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from models.ai_schemas import (
    AiChatResponsePayload,
    AiClarificationPrompt,
    AiEntityListItem,
    AiToolCallRecord,
    ConfirmedQueryContext,
    EvidenceItemV2,
    QueryOperationV2,
    QueryScopeV2,
    SessionFilterContext,
    SourceCitationPill,
    StructuredQueryPlan,
    StructuredVisualCard,
    ValidatedQueryPlanV2,
)
from services.ai.contextual_assistant import is_self_only
from services.ai.conversation_service import AiConversationService
from services.ai.domain_policies import MONTH_ALIASES
from services.ai.read_only_guard import ReadOnlySessionGuard
from services.ai.router import _detect_branches_in_prompt, _detect_teams_in_prompt
from services.dashboard_record_service import DashboardRecordService
from services.planning_service import MONTH_ORDER
from utils.report_scope import filter_records_by_scope, function_team_keys, selection_team_keys

_MONTH_PATTERN = "|".join(map(re.escape, sorted(MONTH_ALIASES, key=len, reverse=True)))
_YEAR_PATTERN = r"(?:20\d{2}|2100)"
_MONTH_BY_NUMBER = {number: month for month, number in MONTH_ORDER.items()}
_PERIOD = re.compile(
    rf"(?<!\w)(?:(?P<iso_year>{_YEAR_PATTERN})-(?P<number>0[1-9]|1[0-2])"
    rf"|(?P<month>{_MONTH_PATTERN})(?:\s+(?P<year>{_YEAR_PATTERN}))?)(?!\w)"
)
ROSTER_TOOL_NAME = "compare_evaluation_rosters"
_ROSTER_PERIOD_KEY = re.compile(rf"({_YEAR_PATTERN})-(0[1-9]|1[0-2])")
ROSTER_TOOL_SCHEMA = {
    "description": (
        "Compare presence in PMS evaluation records. Return employees or teams present in the baseline "
        "period and absent in the target period. Use for roster changes, missing evaluations and people "
        "or teams that stopped appearing. Requires two periods from the question or verified context."
    ),
    "properties": {
        "entity": {"type": "string", "enum": ["employee", "team"]},
        "baseline_period": {"type": "string", "description": "YYYY-MM period in which the entities appeared"},
        "target_period": {"type": "string", "description": "YYYY-MM period from which the entities are missing"},
    },
    "required": ["entity", "baseline_period", "target_period"],
}
_ENTITY = re.compile(r"\b(?:who|employees?|agents?|staff|people|teams?)\b")
_ABSENCE = (
    r"\b(?:missing|absent|dropped\s+off|no\s+longer(?:\s+(?:appear(?:ed)?|show(?:ed)?|evaluated))?|"
    r"(?:didn['’]t|did\s+not)\s+(?:appear|show\s+up)|"
    r"but\s+not|not\s+(?:in|present|listed|evaluated|recorded)|no\s+evaluation(?:s)?)\b"
)
_TARGET_PERIOD = re.compile(
    rf"{_ABSENCE}(?:\s+\w+){{0,5}}\s+(?:in|for|during|from)\s*$|{_ABSENCE}\s*$"
)
_METRIC_OR_WRITE = re.compile(r"\b(?:kpis?|scores?|targets?|corrective\s+actions?|delete|remove|update|add)\b")
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RosterComparison:
    entity: Literal["employee", "team"]
    periods: tuple[tuple[int | None, str], ...]
    target_index: int | None
    region: str | None
    team: str | None
    function: str | None
    branch: str | None


def detect_roster_comparison(
    prompt: str, state: SessionFilterContext, explicit_region: str | None
) -> RosterComparison | None:
    text = prompt.casefold()
    entity_match = _ENTITY.search(text)
    if not entity_match or not re.search(_ABSENCE, text) or _METRIC_OR_WRITE.search(text):
        return None

    entity = "team" if entity_match.group().startswith("team") else "employee"
    query = _parse_roster_scope(text, state, explicit_region, entity)
    return query if query and query.periods else None


def _parse_roster_scope(
    text: str,
    state: SessionFilterContext,
    explicit_region: str | None,
    entity: Literal["employee", "team"],
) -> RosterComparison | None:
    matches = [
        match for match in _PERIOD.finditer(text)
        if not (match["month"] == "may" and re.match(r"\s+(?:be|have|need)\b", text[match.end():]))
    ]

    # An explicit country-wide request supersedes incidental team and branch filters.
    teams = _detect_teams_in_prompt(text)
    team = teams[0] if teams else (None if explicit_region else state.team)
    branches = _detect_branches_in_prompt(text, team)
    branch = branches[0] if branches else (None if explicit_region else state.branch)
    function = None if explicit_region or teams else state.function
    if re.search(r"\bcall\s+cent(?:er|re)\b", text):
        function = "Call Center"
    elif re.search(r"\brcm\b", text):
        function = "RCM"
    if len(teams) > 1 or len(branches) > 1:
        return None

    years = {int(year) for year in re.findall(rf"\b{_YEAR_PATTERN}\b", text)}
    default_year = next(iter(years)) if len(years) == 1 else state.year if not years else None
    periods: list[tuple[int | None, str]] = []
    target_index = None
    previous_end = 0
    for match in matches:
        month = (
            _MONTH_BY_NUMBER[int(match["number"])]
            if match["number"]
            else MONTH_ALIASES[match["month"]]
        )
        year = match["iso_year"] or match["year"]
        period = (int(year) if year else default_year, month)
        if period not in periods:
            if _TARGET_PERIOD.search(text[previous_end:match.start()]):
                target_index = len(periods)
            periods.append(period)
        previous_end = match.end()
    if len(matches) == len(periods) == 2 and re.search(
        r"\bfrom\s*$", text[:matches[0].start()]
    ) and re.fullmatch(r"\s+to\s+", text[matches[0].end():matches[1].start()]):
        target_index = 1
    return RosterComparison(
        entity=entity,
        periods=tuple(periods),
        target_index=target_index,
        region=explicit_region or (
            state.region if state.region and state.region.strip().casefold() not in ("all", "") else None
        ),
        team=team if team and team.strip().casefold() not in ("all", "") else None,
        function=function if function and function.strip().casefold() not in ("all", "") else None,
        branch=branch if branch and branch.strip().casefold() not in ("all", "") else None,
    )


def resolve_planned_roster_comparison(
    prompt: str,
    state: SessionFilterContext,
    explicit_region: str | None,
    arguments: dict,
) -> RosterComparison | None:
    """Use model-selected intent and direction with server-resolved dates and filters."""
    entity = arguments.get("entity")
    if entity not in ("employee", "team"):
        return None
    query = _parse_roster_scope(prompt.casefold(), state, explicit_region, entity)
    if query is None:
        return None

    ordered_periods = []
    for key in ("baseline_period", "target_period"):
        match = _ROSTER_PERIOD_KEY.fullmatch(str(arguments.get(key) or ""))
        if match is None:
            break
        ordered_periods.append((int(match[1]), _MONTH_BY_NUMBER[int(match[2])]))
    valid_order = len(ordered_periods) == 2 and ordered_periods[0] != ordered_periods[1]

    # Resolve the dates from the question. The planner can choose their order
    # when the question leaves it implicit and both proposed dates match.
    if len(query.periods) == 2:
        if query.target_index is not None or not valid_order:
            return query
        indexes = [
            [index for index, (year, month) in enumerate(query.periods)
             if month == planned_month and year in (None, planned_year)]
            for planned_year, planned_month in ordered_periods
        ]
        if all(len(matches) == 1 for matches in indexes) and indexes[0] != indexes[1]:
            return replace(query, target_index=indexes[1][0])
        return query

    prior = state.last_confirmed_query
    if valid_order and not query.periods and prior and prior.last_operation_kind == "roster_comparison":
        planned_keys = {arguments["baseline_period"], arguments["target_period"]}
        if planned_keys == set(prior.periods):
            return replace(
                query,
                periods=tuple(ordered_periods),
                target_index=1,
                region=explicit_region or query.region or prior.region,
                team=query.team or (None if explicit_region else prior.team),
                function=query.function or (None if explicit_region else prior.function),
                branch=query.branch or (None if explicit_region else prior.branch),
            )
    return replace(query, periods=())


def build_roster_comparison_response(
    query: RosterComparison,
    state: SessionFilterContext,
    auth: AiConversationService,
    scope: dict,
) -> tuple[AiChatResponsePayload, ValidatedQueryPlanV2]:
    noun = "team" if query.entity == "team" else "employee"
    region_label = {"EGY": "Egypt", "KSA": "Saudi Arabia"}.get(query.region, query.region)
    subject_scope = " · ".join(
        label for label in (region_label, query.branch and query.branch.title(), query.team or query.function) if label
    ) or "your authorized scope"
    op = QueryOperationV2(
        operation_id="roster_comparison",
        kind="roster_comparison",
        dimension=query.entity,
        args={"region": query.region},
    )
    plan = ValidatedQueryPlanV2(
        turn_kind="analytical",
        scope=QueryScopeV2(
            function=query.function,
            team=query.team,
            branches=[query.branch] if query.branch else [],
        ),
        operations=[op],
        resolution_source="local_rules",
    )
    response = AiChatResponsePayload(
        trace_id="",
        outcome="answer",
        headline="",
        scope_banner=subject_scope,
        effective_context_label=subject_scope,
        resolved_session_state=state,
        validated_plan_v2=plan,
        answer_detail="brief",
        capability_mode="performance_query",
        provider_used="deterministic",
        model_used="pms-roster-comparison",
        answer_source="deterministic",
    )

    if (
        is_self_only(scope)
        or not auth._is_region_authorized(query.region, scope)
        or not auth._is_function_authorized(query.function, scope)
        or not auth._is_team_and_level_authorized(query.team, "Employee", scope, region=query.region)
        or not auth._is_branch_authorized(query.branch, scope)
    ):
        response.outcome = "restricted_access"
        response.headline = f"Your PMS permissions do not allow an evaluation roster comparison for {subject_scope}."
        plan.clarification_code = "RESTRICTED_SCOPE_SUGGESTION"
        return response, plan

    if len(query.periods) != 2 or (
        any(year is None for year, _ in query.periods) and any(year is not None for year, _ in query.periods)
    ):
        response.outcome = "clarification"
        response.headline = f"Which two months and years should I compare for missing {noun}s in {subject_scope}?"
        plan.turn_kind = "clarification"
        plan.clarification_code = "MISSING_COMPARISON_PERIOD"
        response.clarification = AiClarificationPrompt(
            code=plan.clarification_code,
            question=response.headline,
            choices=[],
        )
        return response, plan

    source = DashboardRecordService(auth.db)
    team_keys = selection_team_keys(query.team) if query.team else None
    function_keys = function_team_keys(query.function) if query.function else None

    def matches_scope(row):
        team_name = row.team.casefold()
        return (team_keys is None or team_name in team_keys) and (function_keys is None or team_name in function_keys)

    try:
        with ReadOnlySessionGuard(auth.db):
            inferred_year = None
            if query.periods[0][0] is None:
                index = source.list_record_index(
                    months=[month for _, month in query.periods], region=query.region, scope=scope,
                )
                scoped_index = filter_records_by_scope(index or [], scope)
                inferred_year = max(
                    (
                        row.year for row in scoped_index
                        if row.performance_level.casefold() == "employee"
                        and matches_scope(row)
                        and (not query.branch or row.branch_key in (None, query.branch))
                    ),
                    default=None,
                )
                if inferred_year is None:
                    months = " or ".join(month for _, month in query.periods)
                    response.outcome = "unavailable_data"
                    response.headline = f"No authorized PMS evaluation records were found for {months} in {subject_scope}."
                    return response, plan

            periods = [(year or inferred_year, month) for year, month in query.periods]
            if query.target_index == 0:
                periods.reverse()
            elif query.target_index is None:
                periods.sort(key=lambda period: (period[0], MONTH_ORDER[period[1]]))
            period_labels = [f"{month} {year}" for year, month in periods]
            baseline_label, target_label = period_labels
            period_keys = [f"{year:04d}-{MONTH_ORDER[month]:02d}" for year, month in periods]
            plan.scope.periods = period_keys
            plan.scope.period_window = "explicit"
            response.scope_banner = f"{subject_scope} · {baseline_label} → {target_label}"
            response.effective_context_label = response.scope_banner
            response.citations = [
                SourceCitationPill(label=label, category="period") for label in period_labels
            ] + [SourceCitationPill(label="PMS employee evaluation records", category="basis")]

            records = filter_records_by_scope(
                source.list_records(
                    periods=periods,
                    performance_level="Employee",
                    region=query.region,
                    branch=query.branch,
                    scope=scope,
                ),
                scope,
            )
    except SQLAlchemyError:
        logger.exception("Unable to read evaluation rosters")
        response.outcome = "unavailable_data"
        response.headline = f"PMS could not read the evaluation records for {subject_scope}."
        return response, plan

    baseline_rows, target_rows = (
        [row for row in records if (row.year, row.month) == period] for period in periods
    )
    response.tool_calls = [AiToolCallRecord(
        tool_name=ROSTER_TOOL_NAME,
        arguments={
            "region": query.region,
            "team": query.team,
            "function": query.function,
            "branch": query.branch,
            "periods": period_keys,
            "entity": query.entity,
        },
        records_evaluated=len(records),
    )]
    missing_periods = [label for label, rows in zip(period_labels, (baseline_rows, target_rows)) if not rows]
    if missing_periods:
        response.outcome = "unavailable_data"
        response.headline = f"No authorized PMS evaluation records were found for {' or '.join(missing_periods)} in {subject_scope}."
        response.narrative_bullets = ["The comparison requires evaluation records for both periods."]
        return response, plan

    def roster(rows):
        members: dict[str, tuple[str, set[str]]] = {}
        for row in rows:
            if not matches_scope(row):
                continue
            team = row.team.strip()
            key = team.casefold() if query.entity == "team" else str(row.employee_id).strip()
            name = team if query.entity == "team" else row.employee_name or key
            if key:
                members.setdefault(key, (name, set()))[1].add(team)
        return members

    baseline = roster(baseline_rows)
    target = roster(target_rows)
    missing = sorted(baseline.keys() - target.keys(), key=lambda key: (baseline[key][0].casefold(), key))
    count = len(missing)
    if not baseline:
        response.outcome = "unavailable_data"
        response.headline = f"No authorized {noun} evaluation records were found for {subject_scope} in {baseline_label}."
        return response, plan

    response.narrative_bullets = [
        f"Distinct {noun}s with evaluations: {len(baseline)} in {baseline_label} and {len(target)} in {target_label}."
    ]
    if count:
        label = noun if count == 1 else f"{noun}s"
        verb = "has" if count == 1 else "have"
        response.headline = (
            f"{count} {label} with {baseline_label} evaluations {verb} no {target_label} evaluation in {subject_scope}."
        )
        items = [
            AiEntityListItem(
                id=key,
                title=baseline[key][0],
                subtitle=", ".join(sorted(baseline[key][1])) if query.entity == "employee" else f"Evaluated in {baseline_label}",
                severity="info",
            )
            for key in missing
        ]
        response.visual_cards = [StructuredVisualCard(
            card_type="entity_list", title=f"Missing from {target_label}", items=items,
        )]
    else:
        response.headline = (
            f"Every {noun} evaluated in {baseline_label} also appears in {target_label} in {subject_scope}."
        )

    response.evidence_envelope_v2 = [EvidenceItemV2(
        operation_id=op.operation_id,
        scope=plan.scope,
        headline_value=count,
        record_count=len(records),
        missing_count=count,
    )]
    response.structured_query = StructuredQueryPlan(
        intent="compare_periods", operation_kind_v2="roster_comparison", requested_parts=["roster_comparison"],
        team=query.team, function=query.function, branch=query.branch, periods=period_keys,
    )
    confirmed = ConfirmedQueryContext(
        intent="compare_periods",
        last_operation_kind="roster_comparison",
        comparison_type="period",
        periods=period_keys,
        region=query.region,
        team=query.team,
        function=query.function,
        branch=query.branch,
        performance_level="Employee",
    )
    response.resolved_session_state = state.model_copy(update={"last_confirmed_query": confirmed})
    return response, plan

from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy.orm import Session

from config.database import release_read_transaction
from models.ai_schemas import (
    AiChatRequest,
    AiChatResponsePayload,
    AiProviderUsageMetrics,
    AiToolCallRecord,
    AiTurnTimingBreakdown,
    AiWatchingAlertItem,
    AiWatchingPayload,
    DeepLinkCta,
    EvidenceItemV2,
    QueryOperationV2,
    QueryScopeV2,
    SessionFilterContext,
    SourceCitationPill,
    StructuredVisualCard,
    TypedMetricEvidence,
    ValidatedQueryPlanV2,
)
from models.report_schemas import MONTHS
from services.ai.catalog import ai_evidence_cache, evaluation_cache_identity, get_ai_catalog
from services.ai.config import get_ai_runtime_config
from services.ai.conversation_service import AiConversationService
from services.ai.domain_policies import (
    build_call_center_guardrails,
    build_call_center_starter_prompts,
    extract_prompt_signals,
    sanitize_untrusted_text,
)
from services.ai.entity_resolver import (
    EmployeeHistoryCandidate,
    build_employee_candidates_from_records,
)
from services.ai.providers import DeterministicLocalProviderAdapter
from services.ai.router import HybridQueryRouter, RouterValidationResult
from services.ai.tool_registry import (
    DeterministicToolRegistry,
    ToolExecutionContext,
    ToolExecutionResult,
    build_verified_deep_link,
)
from services.ai.trace_logger import TrainingTraceLogger
from services.corrective_action_service import CorrectiveActionService
from services.database_record_source import DatabaseRecordSource
from utils.report_scope import filter_records_by_scope

REVERSE_MONTHS: dict[int, str] = {v: k for k, v in MONTHS.items()}


def _period_key_to_month_year(period_key: str) -> tuple[str | None, int | None]:
    try:
        yr_s, mo_s = period_key.split("-", 1)
        return REVERSE_MONTHS.get(int(mo_s)), int(yr_s)
    except Exception:
        return None, None


class PmsAiOrchestrator:
    """Coordinates zero-token 'AI is watching' alerts and multi-tool analytical chat turns."""

    def __init__(self, db: Session, scope: dict[str, Any]) -> None:
        self.db = db
        self.scope = scope

    def _get_published_periods_and_candidates(self) -> tuple[set[str], list[EmployeeHistoryCandidate]]:
        try:
            records = filter_records_by_scope(DatabaseRecordSource(self.db).get_all(), self.scope)
            periods: set[str] = set()
            for r in records:
                yr = getattr(r, "year", None)
                mo = getattr(r, "month", None)
                if not yr or not mo:
                    continue
                m_num = MONTHS.get(str(mo).strip())
                if m_num:
                    periods.add(f"{int(yr):04d}-{int(m_num):02d}")
            candidates = build_employee_candidates_from_records(records)
            return periods, candidates
        except Exception:
            return set(), []

    def _get_published_periods(self) -> set[str]:
        periods, _ = self._get_published_periods_and_candidates()
        return periods

    @staticmethod
    def _build_validated_plan_v2(
        routed: RouterValidationResult,
        *,
        turn_kind: str = "analytical",
    ) -> ValidatedQueryPlanV2:
        p = routed.plan
        op_kind_override = routed.confirmed_context.last_operation_kind
        branches_list = list(p.branches)
        if not branches_list:
            for b in (p.branch, p.compare_branch):
                if b and b not in branches_list:
                    branches_list.append(b)
        perf_lvl = p.performance_level if p.performance_level in ("Employee", "Managerial", "Corporate") else "Employee"
        scope_v2 = QueryScopeV2(
            function=p.function or "Call Center",
            team=p.team,
            position_group="Support Positions" if p.team == "Support Positions" else None,
            position=p.position,
            performance_level=perf_lvl,  # type: ignore[arg-type]
            branches=branches_list,
            periods=list(p.periods),
            period_window="all_published" if op_kind_override == "employee_best_period" else ("explicit" if p.periods else "latest_published"),
            employee_id=p.employee_id,
            employee_placeholder="<EMP_1>" if p.employee_id else None,
        )
        ops: list[QueryOperationV2] = []
        if p.requested_parts == ["trend", "ranking"] or (
            "trend" in p.requested_parts and "ranking" in p.requested_parts
        ):
            ops.append(
                QueryOperationV2(
                    operation_id="op_1",
                    kind="trend",
                    metric_id=p.metric,
                    dimension="period",
                )
            )
            ops.append(
                QueryOperationV2(
                    operation_id="op_2",
                    kind="ranking",
                    metric_id=p.metric,
                    dimension="employee",
                    direction=p.ranking_direction,
                    limit=1 if p.single_person else 3,
                )
            )
        else:
            kind_map = {
                "employee_best_period": "person_best_period",
                "joiner_check": "person_tenure_check",
                "unsupported": "current_value",
            }
            raw_kind = op_kind_override or p.intent
            effective_kind = kind_map.get(str(raw_kind), str(raw_kind))
            valid_kinds = {
                "greeting",
                "thanks",
                "current_value",
                "actual_vs_target",
                "compare_periods",
                "compare_branches",
                "compare_teams",
                "trend",
                "ranking",
                "person_summary",
                "person_best_period",
                "person_tenure_check",
                "score_drivers",
                "scorecard_structure",
                "corrective_actions",
            }
            if effective_kind not in valid_kinds:
                effective_kind = "actual_vs_target"
            ops.append(
                QueryOperationV2(
                    operation_id="op_1",
                    kind=effective_kind,  # type: ignore[arg-type]
                    metric_id=p.metric,
                    direction=p.ranking_direction if effective_kind == "ranking" else None,
                    limit=1 if p.single_person else 3,
                )
            )
        res_src = "gemini_router" if routed.route_used == "gemini_router" else "local_rules"
        return ValidatedQueryPlanV2(
            turn_kind=turn_kind if turn_kind in ("social", "analytical", "clarification", "correction", "unsupported") else "analytical",  # type: ignore[arg-type]
            scope=scope_v2,
            operations=ops,
            clarification_code=routed.clarification.code if routed.clarification else "NONE",
            resolution_source=res_src,  # type: ignore[arg-type]
            confidence=1.0,
        )

    @staticmethod
    def _build_evidence_envelope_v2(
        typed_evidence: list[TypedMetricEvidence],
        tool_digests: list[dict[str, Any]],
    ) -> list[EvidenceItemV2]:
        catalog = get_ai_catalog()
        envelope: list[EvidenceItemV2] = []
        for idx, ev in enumerate(typed_evidence, start=1):
            cat_def = catalog.find_metric_definition(
                team=ev.team,
                kpi_key_or_label=ev.metric_id,
                performance_level=ev.performance_level,
            )
            val_kind = getattr(cat_def, "value_kind", None) or ("rate" if ev.unit == "%" else "score")
            perf_lvl = ev.performance_level if ev.performance_level in ("Employee", "Managerial", "Corporate") else "Employee"
            envelope.append(
                EvidenceItemV2(
                    operation_id=f"op_{idx}",
                    outcome="ok",
                    scope=QueryScopeV2(
                        function=getattr(cat_def, "function", "Call Center") if cat_def else "Call Center",
                        team=ev.team,
                        position=ev.position,
                        performance_level=perf_lvl,  # type: ignore[arg-type]
                        branches=[ev.branch] if ev.branch and ev.branch != "all" else [],
                        periods=[ev.period],
                    ),
                    metric_id=ev.metric_id,
                    metric_display_name=ev.display_name,
                    value_kind=str(val_kind),
                    unit=ev.unit,
                    headline_value=ev.actual,
                    headline_display=ev.actual_display,
                    target_value=ev.target,
                    target_display=ev.target_display,
                    achievement_percent=ev.achievement_percent,
                    weight_percent=ev.weight_percent,
                    contributes_to_score=ev.contributes_to_score,
                    record_count=ev.sample_size,
                    source_link=DeepLinkCta(label=f"Open {ev.team} Source →", route=ev.source_link, icon_key="team") if ev.source_link else None,
                )
            )
        for d in tool_digests:
            sp = d.get("spotlight") or d.get("agent_spotlight")
            if isinstance(sp, dict) and sp.get("entity_id"):
                emp_team = str(sp.get("team") or "Call Center")
                src_route = str(sp.get("source_route") or "")
                envelope.append(
                    EvidenceItemV2(
                        operation_id="op_spotlight",
                        outcome="ok",
                        scope=QueryScopeV2(
                            function="Call Center",
                            team=emp_team,
                            position=sp.get("position"),
                            periods=[str(sp.get("period") or d.get("period") or "Latest Period")],
                            employee_id=str(sp.get("entity_id")),
                        ),
                        metric_id=f"{emp_team.casefold().replace(' ', '_')}:overall_score",
                        metric_display_name=str(sp.get("ranking_metric_label") or "Overall PMS Score"),
                        value_kind="score",
                        unit="%",
                        headline_value=float(sp.get("score") or 0.0),
                        headline_display=f"{float(sp.get('score') or 0.0):.1f}%",
                        target_value=100.0,
                        target_display="100.0%",
                        rows=list(sp.get("all_history") or []),
                        ties=[str(t) for t in (sp.get("ties") or [])],
                        record_count=int(sp.get("total_in_team") or 1),
                        source_link=DeepLinkCta(label=f"Open {sp.get('entity_name')} Profile →", route=src_route, icon_key="employee") if src_route else None,
                    )
                )
        return envelope

    def build_watching_workspace(self, session_state: SessionFilterContext) -> AiWatchingPayload:
        ctx = ToolExecutionContext(db=self.db, scope=self.scope, session_state=session_state)
        resolved = ctx.resolve_filters()

        ws = ctx.insights_service.generate_workspace(
            self.scope,
            sections="summary,executive_story,priority_insights,risks,team_summaries,comparison",
            month=resolved["month"],
            year=resolved["year"],
            region=resolved["region"],
            team=resolved["team"],
            function=resolved["function"],
            performance_level=resolved["performance_level"],
            branch=resolved["branch"],
        )

        res_month = ws.comparison.current.month if ws.comparison and ws.comparison.current else resolved["month"]
        res_year = ws.comparison.current.year if ws.comparison and ws.comparison.current else resolved["year"]
        total_employees = sum(int(t.total_employees or 0) for t in (ws.team_summaries or []))

        overdue_count = 0
        try:
            ca_res = CorrectiveActionService(self.db).list_follow_up(
                self.scope,
                state="overdue",
                team=resolved["team"],
                month=res_month,
            )
            overdue_actions = list(ca_res.get("actions") or [])
            if not resolved["team"] and (resolved["function"] or "").casefold() == "call center":
                overdue_actions = [
                    a for a in overdue_actions if str(a.get("team") or "").casefold() in ("inbound", "outbound", "call center")
                ]
            overdue_count = len(overdue_actions)
        except Exception:
            overdue_count = 0

        release_read_transaction(self.db)

        alerts: list[AiWatchingAlertItem] = []

        # 1. Priority Insights / Team Drop Alert
        for ins in (ws.priority_insights or [])[:2]:
            sev_val = "critical" if str(ins.severity).casefold() == "critical" else "warning"
            focus_txt = ins.explanation or (ins.detail.recommended_focus if ins.detail else "")
            alerts.append(
                AiWatchingAlertItem(
                    id=f"watch-{ins.id}",
                    title=ins.title,
                    subtitle=sanitize_untrusted_text(focus_txt, 110),
                    severity=sev_val,  # type: ignore[arg-type]
                    badge_text=ins.team or (resolved["function"] or "Call Center"),
                    prompt_to_ask=f"Diagnose why {ins.team or 'Call Center'} triggered '{ins.title}' and show the top employees causing it.",
                    deep_link=build_verified_deep_link(
                        "/insights",
                        month=res_month,
                        year=res_year,
                        function=resolved["function"],
                        team=ins.team or resolved["team"],
                        branch=resolved["branch"],
                    ),
                )
            )

        # 2. SIP / Risk Candidates Alert
        if ws.risks:
            non_zero_risks = [r for r in ws.risks if int(r.count or 0) > 0]
            if non_zero_risks:
                top_r = non_zero_risks[0]
                alerts.append(
                    AiWatchingAlertItem(
                        id=f"watch-risk-{top_r.key}",
                        title=f"{top_r.count} employees in {top_r.label}",
                        subtitle=sanitize_untrusted_text(top_r.explanation, 110),
                        severity="warning",
                        badge_text=f"{top_r.count} flagged",
                        prompt_to_ask=f"Who are the employees in {top_r.label} for {resolved['team'] or 'Call Center'}?",
                        deep_link=build_verified_deep_link("/planning", month=res_month, year=res_year, team=resolved["team"]),
                    )
                )

        # 3. Overdue Corrective Actions Alert
        if overdue_count > 0:
            alerts.append(
                AiWatchingAlertItem(
                    id="watch-overdue-actions",
                    title=f"{overdue_count} corrective actions overdue",
                    subtitle="Follow-up deadline passed without completion sign-off",
                    severity="critical",
                    badge_text=f"{overdue_count} exceptions",
                    prompt_to_ask="Show overdue corrective actions and their owners.",
                    deep_link=build_verified_deep_link("/corrective-actions", team=resolved["team"], month=res_month),
                )
            )

        # Ensure at least 3 watching cards when team summaries exist
        if len(alerts) < 3 and ws.team_summaries:
            lowest_t = min(ws.team_summaries, key=lambda t: (t.current_score if t.current_score is not None else 999.0))
            alerts.append(
                AiWatchingAlertItem(
                    id=f"watch-team-{lowest_t.team}",
                    title=f"{lowest_t.team} score at {(lowest_t.current_score or 0.0):.1f}%",
                    subtitle=f"{lowest_t.impacted_employees} of {lowest_t.total_employees} agents below target",
                    severity="warning" if (lowest_t.current_score or 0.0) < 88 else "info",
                    badge_text=lowest_t.team,
                    prompt_to_ask=f"Analyze {lowest_t.team} KPI gaps and who caused the drop in {res_month or 'the latest month'}.",
                    deep_link=build_verified_deep_link(
                        f"/team/{lowest_t.team.lower()}",
                        month=res_month,
                        year=res_year,
                        branch=resolved["branch"],
                    ),
                )
            )

        resolved_state = SessionFilterContext(
            function=resolved["function"],
            team=resolved["team"],
            branch=resolved["branch"],
            region=resolved["region"],
            performance_level=resolved["performance_level"],
            month=res_month,
            year=res_year,
            employee_id=session_state.employee_id,
        )

        eligible = get_ai_catalog().get_eligible_scope_options(
            self.scope,
            active_function=resolved["function"],
        )

        return AiWatchingPayload(
            resolved_session_state=resolved_state,
            alerts=alerts[:4],
            guardrails=build_call_center_guardrails(),
            starter_prompts=build_call_center_starter_prompts(resolved_state),
            summary_score=ws.executive_story.current_score if ws.executive_story else None,
            summary_score_change=ws.executive_story.score_change if ws.executive_story else None,
            measured_records=total_employees,
            eligible_teams=eligible["eligible_teams"],
            eligible_functions=eligible["eligible_functions"],
            eligible_branches=eligible["eligible_branches"],
            eligible_levels=eligible["eligible_levels"],
        )

    def run_chat_turn(self, req: AiChatRequest) -> AiChatResponsePayload:
        t0 = time.perf_counter()
        cfg = get_ai_runtime_config()
        role = str(self.scope.get("role") or "Manager")
        requested_detail = req.answer_detail or "auto"
        lower_prompt = (req.prompt or "").casefold()

        conv_service = AiConversationService(self.db) if req.conversation_id else None
        claimed_turn = None
        active_context_version: int = int(req.context_version or 0)
        if conv_service and req.conversation_id:
            conv_ctx = conv_service.get_context(
                conversation_id=req.conversation_id,
                scope=self.scope,
            )
            if req.session_state.last_confirmed_query is None and conv_ctx.confirmed_context is not None:
                req.session_state.last_confirmed_query = conv_ctx.confirmed_context
            claimed_turn, replayed_payload = conv_service.claim_or_replay_turn(
                conversation_id=req.conversation_id,
                scope=self.scope,
                prompt=req.prompt,
                client_request_id=req.client_request_id,
                expected_context_version=req.context_version,
            )
            if replayed_payload is not None:
                return AiChatResponsePayload.model_validate(replayed_payload)
            active_context_version = conv_ctx.context_version

        is_greeting = bool(
            re.fullmatch(
                r"(?:hi|hello|hey|good morning|good afternoon|good evening)(?:\s+there)?[\s!.,?]*",
                lower_prompt.strip(),
            )
        )
        is_social_thanks = bool(
            re.fullmatch(
                r"(?:thanks|thank you|thx|ty|many thanks|thanks a lot|thank you so much|got it,?\s*thanks|ok\s*thanks|okay\s*thanks|appreciate it|great,?\s*thanks)[\s!.,?]*",
                lower_prompt.strip(),
            )
        )
        if is_greeting or is_social_thanks:
            social_headline = (
                "Hi! What would you like to know about performance?"
                if is_greeting
                else "You're welcome! Let me know if you need anything else."
            )
            social_plan_v2 = ValidatedQueryPlanV2(
                turn_kind="social",
                scope=QueryScopeV2(
                    function=req.session_state.function or "Call Center",
                    team=req.session_state.team,
                ),
                operations=[
                    QueryOperationV2(
                        operation_id="op_1",
                        kind="greeting" if is_greeting else "thanks",
                    )
                ],
            )
            social_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=req.conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                answer_detail="brief",
                headline=social_headline,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                validated_plan_v2=social_plan_v2,
                evidence_envelope_v2=[],
            )
            if conv_service and req.conversation_id and claimed_turn:
                new_ver = conv_service.complete_turn(
                    conversation_id=req.conversation_id,
                    turn_id=str(claimed_turn.id),
                    scope=self.scope,
                    outcome="answer",
                    turn_kind="social",
                    route_used="local_rules",
                    validated_plan=social_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=social_resp.model_dump(),
                    session_state=req.session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=0,
                    total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
                social_resp.context_version = new_ver
            return social_resp
        asks_explicit_breakdown = any(
            phrase in lower_prompt
            for phrase in (
                "show details",
                "in detail",
                "detailed breakdown",
                "full breakdown",
                "full table",
                "kpi table",
                "all kpis",
            )
        )
        if requested_detail in ("brief", "details"):
            effective_detail = requested_detail
        elif asks_explicit_breakdown:
            effective_detail = "details"
        elif cfg.brief_default_enabled:
            effective_detail = "brief"
        else:
            effective_detail = "details"

        # Derive authorized published periods + employee candidates and release the read transaction before routing
        published_periods, employee_candidates = self._get_published_periods_and_candidates()
        release_read_transaction(self.db)
        t_res_start = time.perf_counter()
        routed = HybridQueryRouter(
            scope=self.scope,
            published_periods=published_periods,
            employee_candidates=employee_candidates,
        ).resolve_and_validate(
            prompt=req.prompt,
            session_state=req.session_state,
            provider_override=req.provider_override,
            clarification_choice_id=req.clarification_choice_id,
        )
        signals = extract_prompt_signals(req.prompt, req.session_state)

        # Synchronize signals with validated StructuredQueryPlan (including inherited follow-up context)
        if routed.plan.team:
            signals.detected_team = routed.plan.team
        if routed.plan.branch:
            signals.detected_branch = routed.plan.branch
        if routed.plan.compare_branch:
            signals.detected_compare_branch = routed.plan.compare_branch
        if routed.plan.branches:
            signals.detected_branches = list(routed.plan.branches)
        if routed.plan.intent == "compare_branches":
            signals.asks_branch_comparison = True
        if routed.plan.performance_level:
            signals.detected_level = routed.plan.performance_level
        if routed.plan.metric:
            signals.detected_kpi = routed.plan.metric.split(":")[-1]
            if routed.plan.metric.endswith(":bookings_count"):
                signals.asks_booking_count = True
        if routed.plan.employee_id:
            signals.detected_employee_query = routed.plan.employee_id
        if routed.confirmed_context.last_operation_kind in ("employee_best_period", "person_best_period"):
            signals.asks_best_month_history = True
        if routed.plan.periods:
            p_month, p_year = _period_key_to_month_year(routed.plan.periods[-1])
            if p_month:
                signals.detected_month = p_month
            if p_year:
                signals.detected_year = p_year
        signals.asks_worst_agent = routed.plan.ranking_direction == "worst"

        if routed.plan.requested_parts == ["trend", "ranking"] or (
            "trend" in routed.plan.requested_parts and "ranking" in routed.plan.requested_parts
        ):
            signals.primary_intents = ["team_trend_spotlight", "agent_spotlight_trend"]
            signals.asks_single_person = True
        elif routed.plan.intent == "ranking" and (routed.plan.single_person or routed.plan.employee_id):
            signals.primary_intents = ["agent_spotlight_trend"]
            signals.asks_single_person = True
        elif routed.plan.intent == "trend":
            signals.primary_intents = ["team_trend_spotlight"]
        elif routed.route_used == "gemini_router" or routed.inherited_filters or routed.plan.metric or routed.plan.position or routed.plan.intent in ("compare_periods", "compare_branches"):
            if routed.plan.intent in ("actual_vs_target", "score_drivers", "compare_periods", "compare_branches") and "kpi_diagnosis" not in signals.primary_intents:
                if signals.primary_intents == ["executive_summary"]:
                    signals.primary_intents = ["kpi_diagnosis"]
                else:
                    signals.primary_intents.insert(0, "kpi_diagnosis")
            elif routed.plan.intent == "ranking" and "people_contribution" not in signals.primary_intents and "agent_spotlight_trend" not in signals.primary_intents:
                target_tool = "agent_spotlight_trend" if routed.plan.single_person else "people_contribution"
                if signals.primary_intents == ["executive_summary"]:
                    signals.primary_intents = [target_tool]
                else:
                    signals.primary_intents.insert(0, target_tool)
            elif routed.plan.intent == "scorecard_structure" and "management_bsc" not in signals.primary_intents:
                signals.primary_intents.insert(0, "management_bsc")
            elif routed.plan.intent == "corrective_actions" and "corrective_actions" not in signals.primary_intents:
                signals.primary_intents.insert(0, "corrective_actions")

        resolution_ms = round((time.perf_counter() - t_res_start) * 1000.0, 2)
        validated_plan_v2 = self._build_validated_plan_v2(
            routed,
            turn_kind="analytical" if routed.outcome == "answer" else "clarification",
        )

        # Pre-read validation short-circuit for clarification, restricted_access, unavailable_data, unsupported_request
        if routed.outcome != "answer":
            p_month, p_year = (
                _period_key_to_month_year(routed.plan.periods[-1])
                if routed.plan.periods
                else (req.session_state.month, req.session_state.year)
            )
            resolved_state = SessionFilterContext(
                function=routed.plan.function or req.session_state.function or "Call Center",
                team=routed.plan.team or req.session_state.team,
                position=routed.plan.position or req.session_state.position,
                branch=routed.plan.branch or req.session_state.branch,
                region=req.session_state.region,
                performance_level=routed.plan.performance_level or req.session_state.performance_level,
                month=p_month or req.session_state.month,
                year=p_year or req.session_state.year,
                employee_id=routed.plan.employee_id or req.session_state.employee_id,
                last_confirmed_query=routed.confirmed_context,
            )
            scope_team_or_fn = resolved_state.team or resolved_state.function or "Call Center"
            if resolved_state.position:
                scope_team_or_fn = f"{scope_team_or_fn} ({resolved_state.position})"
            scope_branch = (
                resolved_state.branch.capitalize()
                if resolved_state.branch and resolved_state.branch.casefold() != "all"
                else "All Branches"
            )
            scope_level = resolved_state.performance_level or "Employee"
            scope_period = (
                f"{resolved_state.month} {resolved_state.year}"
                if resolved_state.month and resolved_state.year
                else (resolved_state.month or "Latest Period")
            )
            scope_banner = f"{scope_branch} · {scope_team_or_fn} · {scope_level} · {scope_period}"

            t_trace_start = time.perf_counter()
            pre_trace_ms = int((t_trace_start - t0) * 1000)
            trace_id = TrainingTraceLogger(self.db).record_turn(
                user_id=str(self.scope.get("user_id") or ""),
                role=role,
                prompt=req.prompt,
                session_state=resolved_state,
                tool_calls=[],
                tool_digest={"outcome": routed.outcome, "plan": routed.plan.model_dump()},
                structured_response={
                    "headline": routed.headline or "",
                    "narrative_bullets": routed.narrative_bullets,
                    "outcome": routed.outcome,
                },
                provider_name="gemini" if routed.route_used == "gemini_router" else "local",
                model_name=cfg.gemini_model if routed.route_used == "gemini_router" else "deterministic-router-v2",
                latency_ms=pre_trace_ms,
                non_empty_evidence=False,
                guardrail_triggered=routed.outcome in ("restricted_access", "unsupported_request"),
                turn_id=str(claimed_turn.id) if claimed_turn else None,
            )
            trace_ms = round((time.perf_counter() - t_trace_start) * 1000.0, 2)
            total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            timings = AiTurnTimingBreakdown(
                resolution_ms=resolution_ms,
                provider_ms=round(routed.provider_metrics.provider_ms, 2),
                database_ms=0.0,
                render_ms=0.0,
                trace_ms=trace_ms,
                total_ms=total_ms,
            )
            provider_usage = AiProviderUsageMetrics(
                router_mode=cfg.router_mode,
                route_used=routed.route_used,  # type: ignore[arg-type]
                provider_calls=routed.provider_metrics.provider_calls,
                input_tokens=routed.provider_metrics.input_tokens,
                output_tokens=routed.provider_metrics.output_tokens,
                estimated_cost_usd=routed.provider_metrics.estimated_cost_usd,
                fallback_outcome=routed.provider_metrics.fallback_outcome,
            )
            short_resp = AiChatResponsePayload(
                trace_id=trace_id,
                conversation_id=req.conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome=routed.outcome,
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline=routed.headline or "",
                narrative_bullets=routed.narrative_bullets,
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=routed.suggested_followups,
                resolved_session_state=resolved_state,
                scope_banner=scope_banner,
                clarification=routed.clarification,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                inherited_filters=routed.inherited_filters,
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="gemini" if routed.route_used == "gemini_router" else "local",
                model_used=cfg.gemini_model if routed.route_used == "gemini_router" else "deterministic-router-v2",
                latency_ms=max(0, int(round(total_ms))),
                timings=timings,
                provider_usage=provider_usage,
                basis_warning=None,
                cache_hit=False,
            )
            if conv_service and req.conversation_id and claimed_turn:
                new_ver = conv_service.complete_turn(
                    conversation_id=req.conversation_id,
                    turn_id=str(claimed_turn.id),
                    scope=self.scope,
                    outcome=routed.outcome,
                    turn_kind="clarification",
                    route_used=routed.route_used,
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=short_resp.model_dump(),
                    session_state=resolved_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=routed.provider_metrics.provider_calls,
                    total_ms=total_ms,
                )
                short_resp.context_version = new_ver
            return short_resp

        t_db_start = time.perf_counter()
        ctx = ToolExecutionContext(db=self.db, scope=self.scope, session_state=req.session_state)
        registry = DeterministicToolRegistry(ctx)

        tool_results: list[ToolExecutionResult] = []
        guardrail_notes: list[str] = []

        if signals.asks_revenue_in_call_center:
            guardrail_notes.append(
                "Call Center (Inbound & Outbound) measures operational patient volume (Bookings, Attended Visits, and Handled Calls) rather than financial revenue. Financial revenue is tracked under Marketing and RCM."
            )

        cache_sig = {
            "intents": list(signals.primary_intents[:2]),
            "team": signals.detected_team or req.session_state.team,
            "function": routed.plan.function or req.session_state.function,
            "position": routed.plan.position,
            "branch": signals.detected_branch or req.session_state.branch,
            "compare_branch": signals.detected_compare_branch,
            "branches": list(signals.detected_branches),
            "asks_branch_comparison": signals.asks_branch_comparison,
            "level": signals.detected_level or req.session_state.performance_level,
            "kpi": signals.detected_kpi,
            "month": signals.detected_month or req.session_state.month,
            "year": signals.detected_year or req.session_state.year,
            "periods": list(routed.plan.periods),
            "employee_query": signals.detected_employee_query,
            "worst_agent": signals.asks_worst_agent,
            "single_person": signals.asks_single_person,
            "asks_best_month_history": signals.asks_best_month_history,
            "asks_revenue_in_call_center": signals.asks_revenue_in_call_center,
        }
        eval_id = evaluation_cache_identity(self.db)
        cached_results = ai_evidence_cache.get(
            db=self.db,
            scope=self.scope,
            query_signature=cache_sig,
            eval_id=eval_id,
        )
        cache_hit = False
        if cached_results is not None:
            tool_results = cached_results
            cache_hit = True
        else:
            for intent in signals.primary_intents[:2]:
                if intent == "agent_spotlight_trend":
                    tool_results.append(
                        registry.execute_agent_spotlight_and_trend(
                            team=signals.detected_team,
                            position=routed.plan.position,
                            function=routed.plan.function,
                            branch=signals.detected_branch,
                            month=signals.detected_month,
                            year=signals.detected_year,
                            kpi=signals.detected_kpi,
                            employee_query=signals.detected_employee_query,
                            ranking_direction="worst" if signals.asks_worst_agent else "best",
                            single_person=signals.asks_single_person,
                        )
                    )
                elif intent == "team_trend_spotlight":
                    tool_results.append(
                        registry.execute_team_trend_spotlight(
                            team=signals.detected_team,
                            position=routed.plan.position,
                            function=routed.plan.function,
                            branch=signals.detected_branch,
                            month=signals.detected_month,
                            year=signals.detected_year,
                            kpi=signals.detected_kpi,
                        )
                    )
                elif intent == "management_bsc":
                    tool_results.append(
                        registry.execute_management_balanced_scorecard(
                            team=signals.detected_team,
                            performance_level=signals.detected_level or "Managerial",
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
                elif intent == "corrective_actions":
                    tool_results.append(
                        registry.execute_corrective_actions_status(
                            team=signals.detected_team,
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
                elif intent == "governance_plans":
                    tool_results.append(
                        registry.execute_governance_candidates_and_plans(
                            team=signals.detected_team,
                            branch=signals.detected_branch,
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
                elif intent == "employee_history" and signals.detected_employee_query:
                    tool_results.append(
                        registry.execute_employee_multi_month_history(
                            employee_query=signals.detected_employee_query,
                            branch=signals.detected_branch,
                        )
                    )
                elif intent == "people_contribution":
                    tool_results.append(
                        registry.execute_people_contribution_and_rankings(
                            team=signals.detected_team,
                            position=routed.plan.position,
                            function=routed.plan.function,
                            branch=signals.detected_branch,
                            performance_level=signals.detected_level,
                            kpi=signals.detected_kpi,
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
                elif intent == "kpi_diagnosis":
                    tool_results.append(
                        registry.execute_kpi_diagnosis_and_trends(
                            team=signals.detected_team,
                            position=routed.plan.position,
                            function=routed.plan.function,
                            branch=signals.detected_branch,
                            compare_branch=signals.detected_compare_branch,
                            branches=signals.detected_branches,
                            asks_branch_comparison=signals.asks_branch_comparison,
                            asks_period_comparison=routed.plan.intent == "compare_periods",
                            performance_level=signals.detected_level,
                            kpi=signals.detected_kpi,
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
                else:
                    tool_results.append(
                        registry.execute_executive_and_priority_insights(
                            team=signals.detected_team,
                            position=routed.plan.position,
                            function=routed.plan.function,
                            branch=signals.detected_branch,
                            performance_level=signals.detected_level,
                            month=signals.detected_month,
                            year=signals.detected_year,
                        )
                    )
            ai_evidence_cache.set(
                db=self.db,
                scope=self.scope,
                query_signature=cache_sig,
                payload=tool_results,
                eval_id=eval_id,
            )

        # CRITICAL BLOCKER-2: Release the DB read transaction BEFORE calling any LLM network provider!
        release_read_transaction(self.db)
        database_ms = round((time.perf_counter() - t_db_start) * 1000.0, 2)

        t_render_start = time.perf_counter()
        visual_cards: list[StructuredVisualCard] = []
        citations: list[SourceCitationPill] = []
        deep_links: list[DeepLinkCta] = []
        typed_evidence: list[TypedMetricEvidence] = []
        tool_call_records: list[AiToolCallRecord] = []
        tool_digests: list[dict[str, Any]] = []
        seen_citations: set[str] = set()
        seen_links: set[str] = set()
        res_month = req.session_state.month
        res_year = req.session_state.year
        basis_warning: str | None = None
        any_guardrail = bool(signals.asks_revenue_in_call_center)
        total_records_eval = 0

        if signals.asks_revenue_in_call_center:
            visual_cards.append(
                StructuredVisualCard(
                    card_type="guardrail_notice",
                    title="Call Center Production Metric Notice",
                    subtitle="Domain Schema Guardrail",
                    notice_text=guardrail_notes[0],
                )
            )

        for tr in tool_results:
            total_records_eval += tr.records_evaluated
            any_guardrail = any_guardrail or tr.guardrail_triggered
            if tr.resolved_month:
                res_month = tr.resolved_month
            if tr.resolved_year:
                res_year = tr.resolved_year
            if tr.basis_warning and not basis_warning:
                basis_warning = tr.basis_warning

            tool_call_records.append(
                AiToolCallRecord(
                    tool_name=tr.tool_name,
                    arguments=tr.arguments,
                    records_evaluated=tr.records_evaluated,
                )
            )
            tool_digests.append(tr.digest)
            visual_cards.extend(tr.visual_cards)
            typed_evidence.extend(tr.typed_evidence)

            for c in tr.citations:
                if c.label not in seen_citations:
                    seen_citations.add(c.label)
                    citations.append(c)

            for dl in tr.deep_links:
                if dl.route not in seen_links:
                    seen_links.add(dl.route)
                    deep_links.append(dl)

        # Separate data cards from decision_playbook cards and merge decisions into one cohesive playbook card
        data_cards: list[StructuredVisualCard] = []
        merged_decisions = []
        seen_dec_ids: set[str] = set()
        playbook_title = "Recommended Executive Decisions & What-If Playbook"
        playbook_subtitle = "Data-driven managerial actions prioritized by score recovery and patient conversion ROI"

        for vc in visual_cards:
            if vc.card_type == "decision_playbook":
                if vc.title:
                    playbook_title = vc.title
                if vc.subtitle:
                    playbook_subtitle = vc.subtitle
                for d in vc.decisions:
                    if d.id not in seen_dec_ids:
                        seen_dec_ids.add(d.id)
                        merged_decisions.append(d)
            else:
                data_cards.append(vc)

        final_cards = data_cards[:3]
        if merged_decisions:
            final_cards.append(
                StructuredVisualCard(
                    card_type="decision_playbook",
                    title=playbook_title,
                    subtitle=playbook_subtitle,
                    decisions=merged_decisions[:4],
                )
            )
        render_ms = round((time.perf_counter() - t_render_start) * 1000.0, 2)

        t_prov_start = time.perf_counter()
        adapter = DeterministicLocalProviderAdapter()
        synthesis = adapter.synthesize(
            prompt=req.prompt,
            signals=signals,
            tool_digests=tool_digests,
            guardrail_notes=guardrail_notes,
        )
        provider_ms = round(synthesis.metrics.provider_ms or ((time.perf_counter() - t_prov_start) * 1000.0 if synthesis.metrics.provider_calls > 0 else 0.0), 2)

        resolved_state = SessionFilterContext(
            function=routed.plan.function or req.session_state.function or "Call Center",
            team=signals.detected_team or req.session_state.team,
            position=routed.plan.position or req.session_state.position,
            branch=signals.detected_branch or req.session_state.branch,
            region=req.session_state.region,
            performance_level=signals.detected_level or req.session_state.performance_level,
            month=res_month,
            year=res_year,
            employee_id=routed.plan.employee_id or req.session_state.employee_id,
            last_confirmed_query=routed.confirmed_context,
        )

        scope_team_or_fn = resolved_state.team or resolved_state.function or "Call Center"
        if resolved_state.position:
            scope_team_or_fn = f"{scope_team_or_fn} ({resolved_state.position})"
        scope_branch = (
            resolved_state.branch.capitalize()
            if resolved_state.branch and resolved_state.branch.casefold() != "all"
            else "All Branches"
        )
        scope_level = resolved_state.performance_level or "Employee"
        scope_period = (
            f"{res_month} {res_year}"
            if res_month and res_year
            else (res_month or "Latest Period")
        )
        scope_banner = f"{scope_branch} · {scope_team_or_fn} · {scope_level} · {scope_period}"

        # Prefer a direct team/employee/BSC scorecard link as primary_source_link when available
        primary_link = None
        for dl in deep_links:
            if dl.icon_key in ("team", "employee", "bsc"):
                primary_link = dl
                break
        if primary_link is None and deep_links:
            primary_link = deep_links[0]

        response_dict = {
            "headline": synthesis.headline,
            "narrative_bullets": synthesis.narrative_bullets,
            "citations": [c.model_dump() for c in citations],
        }

        t_trace_start = time.perf_counter()
        pre_trace_ms = int((t_trace_start - t0) * 1000)
        trace_id = TrainingTraceLogger(self.db).record_turn(
            user_id=str(self.scope.get("user_id") or ""),
            role=role,
            prompt=req.prompt,
            session_state=resolved_state,
            tool_calls=[tc.model_dump() for tc in tool_call_records],
            tool_digest={"digests": tool_digests},
            structured_response=response_dict,
            provider_name=synthesis.provider_used,
            model_name=synthesis.model_used,
            latency_ms=pre_trace_ms,
            non_empty_evidence=total_records_eval > 0,
            guardrail_triggered=any_guardrail,
            turn_id=str(claimed_turn.id) if claimed_turn else None,
        )
        trace_ms = round((time.perf_counter() - t_trace_start) * 1000.0, 2)
        total_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        latency_ms = max(0, int(round(total_ms)))

        timings = AiTurnTimingBreakdown(
            resolution_ms=resolution_ms,
            provider_ms=provider_ms,
            database_ms=database_ms,
            render_ms=render_ms,
            trace_ms=trace_ms,
            total_ms=total_ms,
        )
        total_provider_calls = routed.provider_metrics.provider_calls + synthesis.metrics.provider_calls
        provider_usage = AiProviderUsageMetrics(
            router_mode=cfg.router_mode,
            route_used="gemini_router" if total_provider_calls > 0 else "local_rules",
            provider_calls=total_provider_calls,
            input_tokens=routed.provider_metrics.input_tokens + synthesis.metrics.input_tokens,
            output_tokens=routed.provider_metrics.output_tokens + synthesis.metrics.output_tokens,
            estimated_cost_usd=round(routed.provider_metrics.estimated_cost_usd + synthesis.metrics.estimated_cost_usd, 6),
            fallback_outcome=synthesis.metrics.fallback_outcome if synthesis.metrics.fallback_outcome != "none" else routed.provider_metrics.fallback_outcome,
        )
        evidence_envelope_v2 = self._build_evidence_envelope_v2(typed_evidence, tool_digests)

        final_resp = AiChatResponsePayload(
            trace_id=trace_id,
            conversation_id=req.conversation_id,
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            context_version=active_context_version,
            outcome=routed.outcome,
            answer_detail=effective_detail,  # type: ignore[arg-type]
            headline=synthesis.headline,
            narrative_bullets=synthesis.narrative_bullets,
            visual_cards=final_cards,
            citations=citations,
            deep_links=deep_links[:3],
            primary_source_link=primary_link,
            suggested_followups=synthesis.suggested_followups,
            resolved_session_state=resolved_state,
            scope_banner=scope_banner,
            clarification=routed.clarification,
            structured_query=routed.plan,
            validated_plan_v2=validated_plan_v2,
            evidence_envelope_v2=evidence_envelope_v2,
            inherited_filters=routed.inherited_filters,
            typed_evidence=typed_evidence,
            domain_guardrail_notes=guardrail_notes,
            tool_calls=tool_call_records,
            provider_used=synthesis.provider_used,
            model_used=synthesis.model_used,
            latency_ms=latency_ms,
            timings=timings,
            provider_usage=provider_usage,
            basis_warning=basis_warning,
            cache_hit=cache_hit,
        )
        if conv_service and req.conversation_id and claimed_turn:
            new_ver = conv_service.complete_turn(
                conversation_id=req.conversation_id,
                turn_id=str(claimed_turn.id),
                scope=self.scope,
                outcome=routed.outcome,
                turn_kind="analytical",
                route_used="gemini_router" if total_provider_calls > 0 else "local_rules",
                validated_plan=validated_plan_v2.model_dump(),
                evidence_envelope=[ev.model_dump() for ev in evidence_envelope_v2],
                response_payload=final_resp.model_dump(),
                session_state=resolved_state,
                confirmed_context=routed.confirmed_context,
                provider_calls=total_provider_calls,
                total_ms=total_ms,
            )
            final_resp.context_version = new_ver
        return final_resp

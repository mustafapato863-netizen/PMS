from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sqlalchemy.orm import Session

from config.database import release_read_transaction
from models.ai_schemas import (
    AiChatRequest,
    AiChatResponsePayload,
    AiClarificationPrompt,
    AiProviderUsageMetrics,
    AiSpotlightMetricTile,
    AiToolCallRecord,
    AiTurnTimingBreakdown,
    AiWatchingAlertItem,
    AiWatchingPayload,
    ClarificationChoice,
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
from services.ai.catalog import (
    ai_evidence_cache,
    check_scope_data_availability,
    evaluation_cache_identity,
    function_for_team,
    get_ai_catalog,
)
from services.ai.claim_validator import ClaimFact, build_claim_ledger, validate_claims
from services.ai.config import get_ai_runtime_config
from services.ai.contextual_assistant import (
    apply_page_context_to_request,
    build_capabilities_help_payload,
    build_clarification_gate_payload,
    build_corrective_action_proposal_from_evidence,
    build_effective_context_label,
    build_explain_previous_payload,
    build_navigation_payload,
    build_off_topic_gate_payload,
    build_page_help_payload,
    detect_contextual_capability,
    is_self_only,
    validate_page_context_scope,
)
from services.ai.conversation_service import AiConversationService
from services.ai.domain_policies import (
    build_call_center_guardrails,
    build_call_center_starter_prompts,
    extract_prompt_signals,
    has_pms_performance_signal,
    is_greeting_or_thanks_prompt,
    sanitize_untrusted_text,
)
from services.ai.entity_resolver import (
    EmployeeHistoryCandidate,
    build_employee_candidates_from_records,
    format_period_label,
    resolve_employee_from_candidates,
    REVERSE_MONTHS_BY_NUM,
)
from services.ai.provider_engine import (
    ProviderMessage,
    ProviderRequest,
    ProviderTimeoutError,
    get_unified_provider_engine,
)
from services.ai.local_evidence_synthesis import (
    extract_branch_booking_facts,
    extract_overall_score_facts,
    local_synthesis_enabled,
    synthesize_branch_bookings,
    synthesize_overall_score,
    synthesize_validated_executive_variation,
)
from services.ai.llm_client import active_provider_name, configured_model_name, local_exploration_enabled
from services.ai.local_model_router import BoundedIntentContext
from services.ai.prompt_versions import ACTIVE_PROMPT_VERSIONS, MODEL_LED_SYNTHESIS_PROMPT_VERSION
from services.ai.providers import (
    DeterministicLocalProviderAdapter,
    ProviderCallMetrics,
    ProviderUnavailableError,
    combine_cost_statuses,
    metrics_from_provider_response,
    resolve_variation_index,
)
from services.ai.router import (
    AiProviderUnavailableError,
    HybridQueryRouter,
    RouterValidationResult,
    parse_score_threshold_query,
)
from services.ai.tool_registry import (
    DeterministicToolRegistry,
    ToolExecutionContext,
    ToolExecutionResult,
    build_verified_deep_link,
)
from services.ai.trace_logger import (
    TrainingTraceLogger,
    sanitize_prompt_for_router_training,
)
from services.corrective_action_service import CorrectiveActionService
from services.database_record_source import DatabaseRecordSource
from utils.branch_scope import BRANCH_KEYS
from utils.report_scope import filter_records_by_scope
from utils.regions import ksa_region_hint_from_prompt

logger = logging.getLogger(__name__)

REVERSE_MONTHS: dict[int, str] = {v: k for k, v in MONTHS.items()}


def _build_aggregated_usage(
    *,
    router_mode: str,
    route_used: str,
    router_metrics: ProviderCallMetrics,
    synth_metrics: ProviderCallMetrics | None = None,
    fallback_outcome_override: str | None = None,
) -> AiProviderUsageMetrics:
    """Aggregate router and synthesis token, neuron, cost, and cost_status metrics safely."""
    s_calls = int(synth_metrics.provider_calls or 0) if synth_metrics else 0
    s_in = int(synth_metrics.input_tokens or 0) if synth_metrics else 0
    s_out = int(synth_metrics.output_tokens or 0) if synth_metrics else 0
    s_neu = int(synth_metrics.neurons or 0) if synth_metrics else 0
    s_cost = float(synth_metrics.estimated_cost_usd or 0.0) if synth_metrics else 0.0
    r_cost = float(router_metrics.estimated_cost_usd or 0.0)
    total_in = int(router_metrics.input_tokens or 0) + s_in
    total_out = int(router_metrics.output_tokens or 0) + s_out
    total_neu = int(router_metrics.neurons or 0) + s_neu
    total_cost = round(r_cost + s_cost, 8)
    statuses = [router_metrics.cost_status]
    if synth_metrics is not None:
        statuses.append(synth_metrics.cost_status)
    cost_status = combine_cost_statuses(
        statuses,
        input_tokens=total_in,
        output_tokens=total_out,
        neurons=total_neu,
        estimated_cost_usd=total_cost,
    )
    fallback_outcome = (
        fallback_outcome_override
        if fallback_outcome_override is not None
        else (
            synth_metrics.fallback_outcome
            if synth_metrics and synth_metrics.fallback_outcome not in ("none", "", None)
            else router_metrics.fallback_outcome
        )
    )
    return AiProviderUsageMetrics(
        router_mode=router_mode,  # type: ignore[arg-type]
        route_used=route_used,
        provider_calls=int(router_metrics.provider_calls or 0) + s_calls,
        input_tokens=total_in,
        output_tokens=total_out,
        neurons=total_neu,
        estimated_cost_usd=total_cost,
        cost_status=cost_status,
        fallback_outcome=fallback_outcome,
    )


def _score_tone(score_val: float) -> str:
    if score_val >= 85.0:
        return "good"
    if score_val >= 75.0:
        return "warning"
    return "critical"


def build_response_summary_tiles(
    *,
    merged: dict[str, Any] | None,
    visual_cards: list[StructuredVisualCard] | None = None,
    typed_evidence: list[TypedMetricEvidence] | None = None,
) -> list[AiSpotlightMetricTile]:
    """Derive 2-4 concise, zero-hallucination KPI summary tiles from verified tool output."""
    cards = visual_cards or []
    if any(c.card_type == "trend_spotlight" for c in cards):
        return []

    data = merged if isinstance(merged, dict) else {}
    evidence_rows = typed_evidence or []
    tiles: list[AiSpotlightMetricTile] = []

    avg_score = data.get("average_score")
    score_change = data.get("score_change")
    tot_rec = int(data.get("total_records") or 0)
    below_cnt = int(data.get("employees_below_target") or 0)
    teams_list = data.get("teams") or []
    total_teams = int(data.get("total_teams") or len(teams_list))
    worst_team = data.get("worst_team") if isinstance(data.get("worst_team"), dict) else None
    best_team = data.get("best_team") if isinstance(data.get("best_team"), dict) else None
    requested_kpi = data.get("requested_kpi") if isinstance(data.get("requested_kpi"), dict) else None

    # 1. Multi-team executive pulse
    if isinstance(avg_score, (int, float)) and (total_teams > 1 or (worst_team and tot_rec > int(worst_team.get("total_employees") or 0) > 0)):
        delta_part = f"{float(score_change):+.1f} pts vs prior" if isinstance(score_change, (int, float)) else None
        eval_part = f"{tot_rec} evaluated" if tot_rec > 0 else "Active scope"
        sub = f"{delta_part} · {eval_part}" if delta_part else eval_part
        tiles.append(
            AiSpotlightMetricTile(
                label="Overall Score",
                value=f"{float(avg_score):.1f}%",
                sublabel=sub,
                tone=_score_tone(float(avg_score)),  # type: ignore[arg-type]
            )
        )

        on_track_raw = data.get("teams_on_track")
        if on_track_raw is None and teams_list:
            on_track_raw = sum(1 for t in teams_list if float(t.get("score") or 0.0) >= 85.0)
        if isinstance(on_track_raw, int) and total_teams > 0:
            ratio_ok = on_track_raw == total_teams
            tone = "good" if ratio_ok else ("warning" if on_track_raw >= max(1, total_teams // 2) else "critical")
            tiles.append(
                AiSpotlightMetricTile(
                    label="Teams On Track",
                    value=f"{on_track_raw} of {total_teams}",
                    sublabel="≥ 85% benchmark",
                    tone=tone,  # type: ignore[arg-type]
                )
            )

        if worst_team and worst_team.get("team"):
            w_score = float(worst_team.get("current_score") or 0.0)
            w_chg = worst_team.get("score_change")
            w_sub = str(worst_team["team"])
            if isinstance(w_chg, (int, float)):
                w_sub = f"{w_sub} ({float(w_chg):+.1f} pts)"
            tiles.append(
                AiSpotlightMetricTile(
                    label="Needs Attention",
                    value=f"{w_score:.1f}%",
                    sublabel=w_sub,
                    tone="critical" if w_score < 75.0 else "warning",
                )
            )

        if not best_team and len(teams_list) > 1:
            top_row = max(teams_list, key=lambda r: float(r.get("score") or 0.0))
            best_team = {"team": top_row.get("team"), "current_score": top_row.get("score")}
        if best_team and best_team.get("team") and (not worst_team or best_team.get("team") != worst_team.get("team")):
            b_score = float(best_team.get("current_score") or 0.0)
            tiles.append(
                AiSpotlightMetricTile(
                    label="Top Performing",
                    value=f"{b_score:.1f}%",
                    sublabel=f"{best_team['team']} · Highest score",
                    tone="good",
                )
            )
        return tiles[:4]

    # 2. Focused KPI diagnosis
    if requested_kpi and requested_kpi.get("actual_display"):
        ach = requested_kpi.get("achievement_percent")
        ach_tone = _score_tone(float(ach)) if isinstance(ach, (int, float)) else "neutral"
        tiles.append(
            AiSpotlightMetricTile(
                label="Actual",
                value=str(requested_kpi["actual_display"]),
                sublabel=str(requested_kpi.get("kpi_label") or "Selected KPI"),
                tone=ach_tone,  # type: ignore[arg-type]
            )
        )
        tgt_disp = str(requested_kpi.get("target_display") or "").strip()
        if tgt_disp and tgt_disp not in ("—", "N/A", "-"):
            wt = float(requested_kpi.get("weight_percent") or 0.0)
            tiles.append(
                AiSpotlightMetricTile(
                    label="Target",
                    value=tgt_disp,
                    sublabel=f"Weight {wt:.0f}%" if requested_kpi.get("contributes_to_score") is not False and wt > 0 else "Tracking indicator",
                    tone="neutral",
                )
            )
        if isinstance(ach, (int, float)):
            tiles.append(
                AiSpotlightMetricTile(
                    label="Achievement",
                    value=f"{float(ach):.1f}%",
                    sublabel="vs KPI target",
                    tone=ach_tone,  # type: ignore[arg-type]
                )
            )
        kpi_below = requested_kpi.get("people_below_target")
        if isinstance(kpi_below, int) and tot_rec > 0:
            on_tgt = max(0, tot_rec - kpi_below)
            tiles.append(
                AiSpotlightMetricTile(
                    label="Agents On Target",
                    value=f"{on_tgt} of {tot_rec}",
                    sublabel=f"{kpi_below} need coaching" if kpi_below > 0 else "All meeting target",
                    tone="warning" if kpi_below > 0 else "good",
                )
            )
        return tiles[:4]

    # 3. Single-team overview
    if isinstance(avg_score, (int, float)):
        delta_sub = f"{float(score_change):+.1f} pts vs prior" if isinstance(score_change, (int, float)) else str(data.get("period") or "Selected period")
        tiles.append(
            AiSpotlightMetricTile(
                label="Team Score",
                value=f"{float(avg_score):.1f}%",
                sublabel=delta_sub,
                tone=_score_tone(float(avg_score)),  # type: ignore[arg-type]
            )
        )
        if tot_rec > 0:
            on_tgt = max(0, tot_rec - below_cnt)
            tiles.append(
                AiSpotlightMetricTile(
                    label="Evaluated Staff",
                    value=f"{tot_rec}",
                    sublabel=f"{below_cnt} below target" if below_cnt > 0 else f"All {on_tgt} on target",
                    tone="warning" if below_cnt > 0 else "good",
                )
            )
        lowest_kpi = data.get("lowest_kpi") if isinstance(data.get("lowest_kpi"), dict) else None
        if lowest_kpi and lowest_kpi.get("kpi_label"):
            l_ach = lowest_kpi.get("achievement_percent")
            tiles.append(
                AiSpotlightMetricTile(
                    label="Primary KPI Focus",
                    value=f"{float(l_ach):.1f}%" if isinstance(l_ach, (int, float)) else str(lowest_kpi.get("actual_display") or "—"),
                    sublabel=str(lowest_kpi["kpi_label"]),
                    tone="warning" if (float(l_ach or 0.0) < 90.0) else "neutral",
                )
            )
        return tiles[:4]

    # 4. Typed evidence fallback (model-led single metric / comparison)
    if 1 <= len(evidence_rows) <= 3 and not cards:
        ev = evidence_rows[0]
        if ev.actual_display:
            ev_tone = _score_tone(float(ev.achievement_percent)) if ev.achievement_percent is not None else "neutral"
            tiles.append(
                AiSpotlightMetricTile(
                    label=ev.display_name,
                    value=ev.actual_display,
                    sublabel=f"{ev.team} · {ev.period}",
                    tone=ev_tone,  # type: ignore[arg-type]
                )
            )
            if ev.target_display and ev.target_display not in ("—", "N/A", "-"):
                tiles.append(
                    AiSpotlightMetricTile(
                        label="Target",
                        value=ev.target_display,
                        sublabel=f"Weight {ev.weight_percent:.0f}%" if ev.contributes_to_score and ev.weight_percent > 0 else "Reference target",
                        tone="neutral",
                    )
                )
            if ev.achievement_percent is not None:
                tiles.append(
                    AiSpotlightMetricTile(
                        label="Achievement",
                        value=f"{ev.achievement_percent:.1f}%",
                        sublabel="Score attainment",
                        tone=ev_tone,  # type: ignore[arg-type]
                    )
                )
        return tiles[:4]

    return []


def _build_bounded_intent_context(session_state: SessionFilterContext) -> BoundedIntentContext:
    """Build classifier context from validated scope fields, never client history or employee lists."""
    confirmed = session_state.last_confirmed_query
    return BoundedIntentContext(
        confirmed_function=(confirmed.function if confirmed and confirmed.function else session_state.function),
        confirmed_team=(confirmed.team if confirmed and confirmed.team else session_state.team),
        confirmed_region=(confirmed.region if confirmed and confirmed.region else session_state.region),
        confirmed_branch=(confirmed.branch if confirmed and confirmed.branch else session_state.branch),
        confirmed_level=(
            confirmed.performance_level
            if confirmed and confirmed.performance_level
            else session_state.performance_level
        ),
        confirmed_metric=(confirmed.metric_display_name if confirmed else None),
        confirmed_periods=tuple(str(period) for period in (confirmed.periods[:3] if confirmed else []) if period),
        previous_operation=(
            (confirmed.last_operation_kind or confirmed.intent)
            if confirmed and confirmed.intent not in (None, "clarify", "unsupported")
            else None
        ),
        has_confirmed_employee=bool(
            (confirmed and (confirmed.last_subject_employee_id or confirmed.last_subject_employee_name))
            or session_state.employee_id
        ),
        pending_clarification_code=(confirmed.pending_clarification_code if confirmed else None),
    )


def _resolved_capability_mode(
    capability_mode: str,
    *,
    outcome: str,
    plan_intent: str,
    prompt: str,
) -> str:
    if (
        outcome == "clarification"
        and plan_intent == "clarify"
        and capability_mode == "performance_query"
        and not has_pms_performance_signal(prompt)
    ):
        return "clarification"
    return capability_mode


def _ranking_candidates_from_digests(
    digests: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    """Return named ranking candidates, retaining ties for a follow-up choice."""
    for digest in digests or []:
        if not isinstance(digest, dict):
            continue
        spotlight = digest.get("agent_spotlight") or digest.get("spotlight")
        if not isinstance(spotlight, dict):
            continue

        candidates: list[dict[str, str]] = []
        tied_agents = spotlight.get("tied_agents") or []
        if spotlight.get("ties") and isinstance(tied_agents, list):
            selected_id = spotlight.get("entity_id") or digest.get("employee_id")
            selected_name = spotlight.get("entity_name") or digest.get("employee_name")
            if selected_id and selected_name:
                candidates.append(
                    {
                        "employee_id": str(selected_id),
                        "employee_name": str(selected_name),
                        "team": str(spotlight.get("team") or digest.get("team") or ""),
                        "position": str(spotlight.get("position") or ""),
                    }
                )
            for candidate in tied_agents:
                if not isinstance(candidate, dict):
                    continue
                employee_id = candidate.get("employee_id")
                employee_name = candidate.get("employee_name")
                if employee_id and employee_name:
                    candidates.append(
                        {
                            "employee_id": str(employee_id),
                            "employee_name": str(employee_name),
                            "team": str(candidate.get("team") or spotlight.get("team") or ""),
                            "position": str(candidate.get("position") or ""),
                        }
                    )

        if len(candidates) < 2:
            top_agents = spotlight.get("top_agents") or []
            if isinstance(top_agents, list):
                candidates = [
                    {
                        "employee_id": str(candidate["employee_id"]),
                        "employee_name": str(candidate["employee_name"]),
                        "team": str(candidate.get("team") or spotlight.get("team") or ""),
                        "position": str(candidate.get("position") or ""),
                    }
                    for candidate in top_agents
                    if isinstance(candidate, dict)
                    and candidate.get("employee_id")
                    and candidate.get("employee_name")
                ]

        unique: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for candidate in candidates:
            if candidate["employee_id"] in seen_ids:
                continue
            seen_ids.add(candidate["employee_id"])
            unique.append(candidate)
        if len(unique) > 1:
            return unique
    return []


def _format_country_scope_text(text: str, team: str | None, region: str | None) -> str:
    """Render shared-country teams with an explicit country in user-facing text."""
    team_value = (team or "").strip()
    region_value = (region or "").strip().upper()
    team_bases = {
        "coding": "Coding",
        "coding egy": "Coding",
        "submission": "Submission",
        "submission egy": "Submission",
        "re-submission": "Re-Submission",
        "resubmission": "Re-Submission",
    }
    team_base = team_bases.get(team_value.casefold())
    if not team_base:
        return text
    if not region_value and team_value.casefold().endswith(" egy"):
        region_value = "EGY"
    country = {"EGY": "Egypt", "UAE": "UAE", "KSA": "Saudi Arabia"}.get(region_value)
    if not country:
        return text
    display_label = f"{team_base} · {country}"
    return re.sub(re.escape(team_value), lambda _: display_label, text, flags=re.IGNORECASE)


def _prompt_region_hint(prompt: str) -> str | None:
    ksa_region = ksa_region_hint_from_prompt(prompt)
    if ksa_region:
        return ksa_region
    lower = (prompt or "").casefold()
    if re.search(r"\b(?:egy|egypt)\b", lower):
        return "EGY"
    if re.search(r"\b(?:uae|emirates)\b", lower):
        return "UAE"
    return None


def _watching_scope_label(resolved: dict[str, Any]) -> str:
    """Name the alert from the active scope, not a Call Center default.

    An insight with no team used to badge and prompt "Call Center" even when
    the workspace was another function, or had no function selected.
    """
    team = str(resolved.get("team") or "").strip()
    function = str(resolved.get("function") or "").strip()
    if team and team.casefold() not in {"all"}:
        return team
    if function and function.casefold() not in {"all"}:
        return function
    return "this scope"


def _period_key_to_month_year(period_key: str) -> tuple[str | None, int | None]:
    try:
        yr_s, mo_s = period_key.split("-", 1)
        return REVERSE_MONTHS.get(int(mo_s)), int(yr_s)
    except Exception:
        return None, None


def _extract_evidence_teams_and_functions(
    *,
    typed_evidence: list[TypedMetricEvidence] | None = None,
    tool_digests: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Collect distinct teams and functions actually present in executed evidence."""
    teams: list[str] = []
    functions: list[str] = []

    def _add_team(raw_t: Any) -> None:
        if not raw_t:
            return
        t = str(raw_t).strip()
        if not t or t.casefold() in {"all", "all teams", "all authorized departments"}:
            return
        if t not in teams:
            teams.append(t)
        fn = function_for_team(t)
        if fn and fn not in functions:
            functions.append(fn)

    def _add_fn(raw_f: Any) -> None:
        if not raw_f:
            return
        f = str(raw_f).strip()
        if not f or f.casefold() in {"all", "all functions", "all authorized departments"}:
            return
        if f not in functions:
            functions.append(f)

    for ev in typed_evidence or []:
        _add_team(getattr(ev, "team", None))

    for td in tool_digests or []:
        if not isinstance(td, dict):
            continue
        _add_team(td.get("team"))
        _add_fn(td.get("function"))
        for t_item in td.get("teams") or []:
            if isinstance(t_item, dict):
                _add_team(t_item.get("team"))
        sp = td.get("spotlight") or td.get("agent_spotlight")
        if isinstance(sp, dict):
            _add_team(sp.get("team"))
        for list_key in ("ranked_employees", "top_agents", "bottom_agents"):
            for emp in td.get(list_key) or []:
                if isinstance(emp, dict):
                    _add_team(emp.get("team"))

    return teams, functions


class PmsAiOrchestrator:
    """Coordinates zero-token 'AI is watching' alerts and multi-tool analytical chat turns."""

    def __init__(self, db: Session, scope: dict[str, Any]) -> None:
        self.db = db
        self.scope = scope
        from services.ai.user_rules_spec import build_user_rules_spec
        self.user_rules_spec = build_user_rules_spec(scope)
        self.scope["user_rules_spec"] = self.user_rules_spec
        self.scope["user_rules_spec_text"] = self.user_rules_spec.get("summary_text", "")

    def _resolve_scope_banner_and_function(
        self,
        *,
        session_state: SessionFilterContext,
        typed_evidence: list[TypedMetricEvidence] | None = None,
        tool_digests: list[dict[str, Any]] | None = None,
        region: str | None = None,
        branch_override: str | None = None,
        month: str | None = None,
        year: int | None = None,
    ) -> tuple[str, str | None]:
        """Compute accurate scope_banner and resolved function from live scope and evidence."""
        ev_teams, ev_functions = _extract_evidence_teams_and_functions(
            typed_evidence=typed_evidence,
            tool_digests=tool_digests,
        )
        eff_team = (
            session_state.team.strip()
            if session_state.team and session_state.team.strip().casefold() not in {"all", ""}
            else None
        )
        eff_fn = (
            session_state.function.strip()
            if session_state.function and session_state.function.strip().casefold() not in {"all", ""}
            else None
        )
        if eff_team and not eff_fn:
            eff_fn = function_for_team(eff_team)
        elif not eff_fn and len(ev_functions) == 1:
            eff_fn = ev_functions[0]

        if eff_team:
            scope_team_or_fn = eff_team
        elif len(ev_teams) == 1:
            scope_team_or_fn = ev_teams[0]
        elif eff_fn:
            scope_team_or_fn = eff_fn
        elif len(ev_functions) == 1:
            scope_team_or_fn = ev_functions[0]
        elif is_self_only(self.scope):
            scope_team_or_fn = "My Scope"
        else:
            role = str(self.scope.get("role") or "").strip()
            is_unrestricted = bool(self.scope.get("has_unrestricted_team_access")) or role in {
                "Admin",
                "General Manager",
                "Performance Team",
                "Viewer",
            }
            acc_teams = [str(t).strip() for t in (self.scope.get("accessible_teams") or []) if str(t).strip()]
            acc_fns = [str(f).strip() for f in (self.scope.get("accessible_functions") or []) if str(f).strip()]
            if not is_unrestricted and len(acc_teams) == 1:
                scope_team_or_fn = acc_teams[0]
                if not eff_fn:
                    eff_fn = function_for_team(acc_teams[0])
            elif not is_unrestricted and len(acc_fns) == 1:
                scope_team_or_fn = acc_fns[0]
                if not eff_fn:
                    eff_fn = acc_fns[0]
            else:
                scope_team_or_fn = "All Authorized Departments"

        if session_state.position and session_state.position.strip().casefold() not in {"all", ""}:
            scope_team_or_fn = f"{scope_team_or_fn} ({session_state.position.strip()})"

        if branch_override:
            scope_branch = branch_override
        else:
            scope_branch = (
                session_state.branch.capitalize()
                if session_state.branch and session_state.branch.casefold() != "all"
                else "All Branches"
            )
            eff_region = region or session_state.region
            if eff_region and eff_region.strip().casefold() not in {"all", ""} and scope_branch == "All Branches":
                scope_branch = f"All Branches ({eff_region.strip().upper()})"

        scope_level = session_state.performance_level or "Employee"
        eff_month = month if month is not None else session_state.month
        eff_year = year if year is not None else session_state.year
        scope_period = (
            f"{eff_month} {eff_year}"
            if eff_month and eff_year
            else (eff_month or "Latest Period")
        )
        return f"{scope_branch} · {scope_team_or_fn} · {scope_level} · {scope_period}", eff_fn

    def _get_published_periods_and_candidates(self) -> tuple[set[str], list[EmployeeHistoryCandidate]]:
        try:
            records = filter_records_by_scope(
                DatabaseRecordSource(self.db, scope=self.scope).get_all(scope=self.scope),
                self.scope,
            )
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
        prompt: str = "",
    ) -> ValidatedQueryPlanV2:
        p = routed.plan
        prompt_lower = prompt.casefold()
        month_mentions = set(
            re.findall(
                r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b",
                prompt_lower,
            )
        )
        asks_team_trend_and_rank = bool(
            (len(p.periods) >= 2 or len(month_mentions) >= 2)
            and re.search(r"\b(?:who|which\s+(?:employee|agent|person)|top\s+performer)\b", prompt_lower)
            and re.search(r"\b(?:top|highest|most|best|rank|leader)\b", prompt_lower)
        )
        has_explicit_employee_in_prompt = bool(
            (p.employee_id and p.employee_id.casefold() in prompt_lower)
            or (p.employee_name and p.employee_name.casefold() in prompt_lower)
        )
        team_level_compound = asks_team_trend_and_rank and not has_explicit_employee_in_prompt
        op_kind_override = routed.confirmed_context.last_operation_kind
        branches_list = list(p.branches)
        if not branches_list:
            for b in (p.branch, p.compare_branch):
                if b and b not in branches_list:
                    branches_list.append(b)
        perf_lvl = p.performance_level if p.performance_level in ("Employee", "Managerial", "Corporate") else "Employee"
        scope_v2 = QueryScopeV2(
            function=p.function,
            team=p.team,
            position_group="Support Positions" if p.team == "Support Positions" else None,
            position=p.position,
            performance_level=perf_lvl,  # type: ignore[arg-type]
            branches=branches_list,
            periods=list(p.periods),
            period_window=(
                "all_published"
                if op_kind_override in ("employee_best_period", "person_best_period", "employee_worst_period", "person_worst_period")
                else ("explicit" if p.periods else "latest_published")
            ),
            employee_id=None if team_level_compound else p.employee_id,
            employee_placeholder="<EMP_1>" if p.employee_id and not team_level_compound else None,
        )
        ops: list[QueryOperationV2] = []
        if team_level_compound or p.requested_parts == ["trend", "ranking"] or (
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
                    limit=1 if (team_level_compound or p.single_person) else 3,
                )
            )
        else:
            kind_map = {
                "employee_best_period": "person_best_period",
                "employee_worst_period": "person_worst_period",
                "joiner_check": "person_tenure_check",
                "unsupported": "current_value",
            }
            raw_kind = p.operation_kind_v2 or op_kind_override or p.intent
            effective_kind = kind_map.get(str(raw_kind), str(raw_kind))
            if p.employee_id and effective_kind == "current_value":
                effective_kind = "person_summary"
            if "score_drivers" in p.requested_parts:
                effective_kind = "score_drivers"
            asks_person_trend = bool(
                len(p.periods) >= 2
                and (p.single_person or p.employee_id or p.employee_name)
                and re.search(r"\b(?:change|changed|trend|over\s+time|across\s+months?)\b", prompt_lower)
            )
            if asks_person_trend:
                effective_kind = "trend"
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
                "person_worst_period",
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
        res_src = routed.route_used if routed.route_used in {"gemini_router", "local_model_router", "local_classifier", "clarification_choice"} else "local_rules"
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
                        function=getattr(cat_def, "function", None) if cat_def else function_for_team(ev.team),
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
                emp_team = str(sp.get("team") or "")
                src_route = str(sp.get("source_route") or "")
                envelope.append(
                    EvidenceItemV2(
                        operation_id="op_spotlight",
                        outcome="ok",
                        scope=QueryScopeV2(
                            function=function_for_team(emp_team) if emp_team else None,
                            team=emp_team or None,
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
        scope_label = _watching_scope_label(resolved)

        # 1. Priority Insights / Team Drop Alert
        for ins in (ws.priority_insights or [])[:2]:
            sev_val = "critical" if str(ins.severity).casefold() == "critical" else "warning"
            focus_txt = ins.explanation or (ins.detail.recommended_focus if ins.detail else "")
            insight_scope = ins.team or scope_label
            alerts.append(
                AiWatchingAlertItem(
                    id=f"watch-{ins.id}",
                    title=ins.title,
                    subtitle=sanitize_untrusted_text(focus_txt, 110),
                    severity=sev_val,  # type: ignore[arg-type]
                    badge_text=insight_scope,
                    prompt_to_ask=f"Diagnose why {insight_scope} triggered '{ins.title}' and show the top employees causing it.",
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
                        prompt_to_ask=f"Who are the employees in {top_r.label} for {scope_label}?",
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

    def _handle_model_led_turn(
        self,
        *,
        req: AiChatRequest,
        routed: RouterValidationResult,
        registry: DeterministicToolRegistry,
        employee_candidates: list[EmployeeHistoryCandidate],
        published_periods: set[str] | None,
        live_auth_service: Any,
        active_conversation_id: str | None,
        claimed_turn: Any,
        claimed_token: str | None,
        claimed_context_version: int | None,
        active_context_version: int | None,
        conv_service: Any,
        t0: float,
        role: str,
        effective_detail: str,
        t_res_start: float,
        validated_plan_v2: ValidatedQueryPlanV2,
    ) -> AiChatResponsePayload:
        cfg = get_ai_runtime_config()
        t_tool_start = time.perf_counter()
        tool_call = routed.plan.model_led_tool_call or {}
        tool_name = str(tool_call.get("tool_name") or "").strip()
        if tool_name in ("get_employee_metric", "read_metric"):
            tool_name = "read_employee_metric"
        elif tool_name in ("read_employee_history", "get_history"):
            tool_name = "get_employee_history"
        tool_args = tool_call.get("tool_arguments") or {}
        if not isinstance(tool_args, dict):
            tool_args = {}

        prior = req.session_state.last_confirmed_query
        prompt_lower = req.prompt.casefold()
        prompt_mentions_employee = any(
            (candidate.employee_name and candidate.employee_name.casefold() in prompt_lower)
            or (candidate.employee_id and candidate.employee_id.casefold() in prompt_lower)
            for candidate in employee_candidates
        ) or bool(
            (routed.plan.employee_name and routed.plan.employee_name.casefold() in prompt_lower)
            or (routed.plan.employee_id and routed.plan.employee_id.casefold() in prompt_lower)
            or re.search(r"\b(?:sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", prompt_lower)
        )
        requested_team = routed.plan.team or validated_plan_v2.scope.team
        team_level_compound = (
            [str(operation.kind) for operation in validated_plan_v2.operations[:2]] == ["trend", "ranking"]
            and not prompt_mentions_employee
        )
        explicit_prompt_region = _prompt_region_hint(req.prompt)
        team_level_query = team_level_compound or bool(
            requested_team
            and validated_plan_v2.scope.employee_id is None
            and not prompt_mentions_employee
            and not re.search(r"\b(?:his|her|their|him|he|she|they|them)\b", prompt_lower)
        )
        requested_function = (
            routed.plan.function
            or validated_plan_v2.scope.function
            or routed.confirmed_context.function
        )
        current_region = explicit_prompt_region or registry.ctx.session_state.region
        scope_changed = bool(
            prior
            and (
                (requested_function and prior.function and requested_function.casefold() != prior.function.casefold())
                or
                (requested_team and prior.team and requested_team.casefold() != prior.team.casefold())
                or (current_region and prior.region and current_region.casefold() != prior.region.casefold())
                or (
                    routed.plan.branch
                    and prior.branch
                    and routed.plan.branch.casefold() != prior.branch.casefold()
                )
                or (
                    routed.plan.position
                    and prior.position
                    and routed.plan.position.casefold() != prior.position.casefold()
                )
            )
        )

        # Validate tool name against registry.AUTHORIZED_MODEL_LED_TOOLS
        if tool_name not in registry.AUTHORIZED_MODEL_LED_TOOLS and tool_name not in ("read_employee_history", "agent_spotlight_trend"):
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="clarification",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline=f"The requested tool '{tool_name}' is not supported.",
                narrative_bullets=[f"Tool '{tool_name}' is not an authorized data tool."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    provider_calls=routed.provider_metrics.provider_calls,
                    fallback_outcome="unknown_tool",
                ),
            )

        # Validate required arguments before data access
        if "metric_id" not in tool_args:
            m_val = tool_args.get("metric") or tool_args.get("metric_type") or tool_args.get("kpi") or tool_args.get("kpi_key")
            if m_val:
                tool_args["metric_id"] = m_val
        if str(tool_args.get("metric_id") or "").strip().casefold() in ("performance", "score", "overall score", "pms score", "overall"):
            tool_args["metric_id"] = "overall_score"

        metric_arg_raw = tool_args.get("metric_id") or (prior.metric_id if prior else None)
        if tool_name in ("read_employee_metric", "get_employee_history", "read_employee_history") and not metric_arg_raw:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="clarification",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Could not complete query due to missing required metric argument.",
                narrative_bullets=["Please specify the metric or KPI you would like to view."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    provider_calls=routed.provider_metrics.provider_calls,
                    fallback_outcome="invalid_tool_arguments",
                ),
            )

        # A model tool argument is not an employee identity grant. Bind an employee
        # only when the local validated plan or the user's prompt resolves one.
        # This prevents a team-level question from becoming a person read because
        # the model supplied an employee name or ID in its tool arguments.
        prompt_employee_id_match = re.search(
            r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", req.prompt, re.IGNORECASE
        )
        prompt_employee_id = prompt_employee_id_match.group(1).upper() if prompt_employee_id_match else None
        prompt_employee_matches = [
            candidate
            for candidate in employee_candidates
            if candidate.employee_name and candidate.employee_name.casefold() in prompt_lower
        ]
        unique_prompt_employee_ids = {candidate.employee_id for candidate in prompt_employee_matches}
        prompt_cand = (
            prompt_employee_matches[0]
            if prompt_employee_matches and len(unique_prompt_employee_ids) == 1
            else None
        )
        validated_employee_id = validated_plan_v2.scope.employee_id
        trusted_employee_id = validated_employee_id or (prompt_cand.employee_id if prompt_cand else None) or prompt_employee_id
        trusted_employee = next(
            (candidate for candidate in employee_candidates if candidate.employee_id == trusted_employee_id),
            None,
        )
        if trusted_employee_id:
            tool_args["employee_id"] = trusted_employee_id
            if trusted_employee:
                tool_args["employee_name"] = trusted_employee.employee_name
        else:
            tool_args.pop("employee_id", None)
            tool_args.pop("employee_name", None)

        # Resolve an employee only from a user-supplied reference or the
        # validated plan. Never add the model's untrusted name to the search text.
        resolved_emp = None
        cand_prompt = req.prompt if prompt_mentions_employee and not trusted_employee_id else ""
        raw_id = str(tool_args.get("employee_id") or "").strip()
        explicit_id = None
        if req.clarification_choice_id:
            for prefix in ("choice-person-", "choice-emp-"):
                if prefix in req.clarification_choice_id:
                    explicit_id = req.clarification_choice_id.replace(prefix, "").strip()
                    break
        if prompt_cand:
            explicit_id = prompt_cand.employee_id
            if prompt_cand.team:
                tool_args["team"] = prompt_cand.team
        elif not explicit_id:
            if raw_id and not any(c in raw_id for c in " \t\n") and not raw_id.startswith("EMP"):
                explicit_id = raw_id
            elif (raw_id.startswith("EMP") or raw_id.startswith("emp")) and not (
                scope_changed and not prompt_mentions_employee
            ):
                explicit_id = raw_id
            elif prior and prior.last_subject_employee_id and not scope_changed:
                explicit_id = prior.last_subject_employee_id
            elif req.session_state.employee_id and not scope_changed:
                explicit_id = req.session_state.employee_id

        resolution = resolve_employee_from_candidates(
            prompt=cand_prompt,
            candidates=employee_candidates,
            explicit_employee_id=explicit_id,
        )

        # Ambiguous employee resolution -> ask focused clarification
        if resolution.status == "ambiguous" and len(resolution.candidates) > 1:
            choices = [
                ClarificationChoice(
                    id=f"choice-emp-{c.employee_id}",
                    label=f"{c.employee_name} ({c.team} · {c.branch})",
                    prompt_to_send=req.prompt,
                    employee_id=c.employee_id,
                    employee_name=c.employee_name,
                )
                for c in resolution.candidates[:5]
            ]
            routed.confirmed_context.pending_clarification_code = "AMBIGUOUS_PERSON"
            routed.confirmed_context.pending_clarification_choices = choices
            clar_prompt = AiClarificationPrompt(
                prompt="Multiple employees match your request. Please select one:",
                choices=[c.label for c in choices],
                code="AMBIGUOUS_PERSON",
            )
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            clar_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="clarification",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Multiple employees match your request. Please select one:",
                narrative_bullets=[f"{c.employee_name}: {c.team} · {c.branch}" for c in resolution.candidates[:5]],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[c.label for c in choices[:2]],
                resolved_session_state=req.session_state.model_copy(update={"last_confirmed_query": routed.confirmed_context}),
                scope_banner="All Authorized Departments",
                clarification=clar_prompt,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used=routed.provider_metrics.provider_used or "cloudflare",
                model_used=routed.provider_metrics.model_used or "granite-4.0-h-micro",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(
                    resolution_ms=round((time.perf_counter() - t_res_start) * 1000.0, 2),
                    provider_ms=routed.provider_metrics.provider_ms,
                    database_ms=0.0,
                    trace_ms=0.0,
                    total_ms=tot_ms,
                ),
                provider_usage=_build_aggregated_usage(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    router_metrics=routed.provider_metrics,
                    fallback_outcome_override="none",
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = clar_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="clarification",
                    turn_kind="clarification",
                    route_used="model_led_pilot",
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=clar_resp.resolved_session_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=routed.provider_metrics.provider_calls,
                    total_ms=tot_ms,
                )
                clar_resp.context_version = new_ver
            return clar_resp

        if resolution.status == "unique" and resolution.matched_employee:
            resolved_emp = resolution.matched_employee
            emp_id = resolved_emp.employee_id
            emp_name = resolved_emp.employee_name
            emp_pos = getattr(resolved_emp, "position", None) or getattr(routed.plan, "position", None)
            team = resolved_emp.team
            branch = resolved_emp.branch
        else:
            safe_raw_id = raw_id if not scope_changed or prompt_mentions_employee else None
            emp_id = explicit_id or safe_raw_id or (prior.last_subject_employee_id if prior and not scope_changed else None)
            emp_name = str(
                (tool_args.get("employee_name") if not scope_changed or prompt_mentions_employee else None)
                or (prior.last_subject_employee_name if prior and not scope_changed else None)
                or ""
            )
            emp_pos = (getattr(prior, "position", None) if prior and not scope_changed else None) or getattr(routed.plan, "position", None)
            model_team = tool_args.get("team") if not scope_changed or requested_team else None
            team = requested_team or model_team or (None if scope_changed else req.session_state.team or (prior.team if prior else None)) or "Inbound"
            branch = routed.plan.branch or registry.ctx.session_state.branch

        if team_level_query:
            emp_id = None
            emp_name = ""
            emp_pos = None
            team = requested_team or req.session_state.team or "Inbound"
            branch = routed.plan.branch or registry.ctx.session_state.branch

        branch = str(branch or "").casefold().strip() or None
        if branch not in BRANCH_KEYS:
            branch = None

        # 2. Check authorization
        is_auth = live_auth_service.is_plan_and_context_authorized(
            scope=self.scope,
            team=team,
            function=requested_function or req.session_state.function or (prior.function if prior else None),
            branch=branch,
            employee_id=emp_id,
        )
        if not is_auth:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="restricted_access",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Access restricted: your permissions do not allow viewing this employee or scope.",
                narrative_bullets=["You do not have permission to view the requested evaluation records."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=["Show performance summary for my authorized scope"],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome="restricted_access",
                ),
            )

        # 3. Parse period and metric
        period_arg = str(tool_args.get("period") or tool_args.get("time_period") or "").strip()
        month_str = None
        year_int = None
        # Explicit user instructions override inherited context
        prompt_month = None
        for m in MONTHS:
            if re.search(rf"\b{m}\b", req.prompt, re.IGNORECASE):
                prompt_month = m
                break
        if prompt_month:
            month_str = prompt_month
            year_match = re.search(r"20\d{2}", req.prompt)
            year_int = int(year_match.group(0)) if year_match else (req.session_state.year or 2026)
        elif re.match(r"^20\d{2}-(0[1-9]|1[0-2])$", period_arg):
            year_int = int(period_arg.split("-")[0])
            month_num = int(period_arg.split("-")[1])
            month_str = REVERSE_MONTHS_BY_NUM.get(month_num, "September")
        elif period_arg.capitalize() in MONTHS:
            month_str = period_arg.capitalize()
            year_int = req.session_state.year or 2026
        elif any(m in period_arg.capitalize() for m in MONTHS):
            for m in MONTHS:
                if m.casefold() in period_arg.casefold():
                    month_str = m
                    break
            year_match = re.search(r"20\d{2}", period_arg)
            year_int = int(year_match.group(0)) if year_match else (req.session_state.year or 2026)
        elif req.session_state.month and req.session_state.year:
            month_str = req.session_state.month
            year_int = req.session_state.year
        else:
            month_str = "September"
            year_int = 2026

        if team_level_compound and validated_plan_v2.scope.periods:
            latest_period = str(validated_plan_v2.scope.periods[-1])
            latest_period_match = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", latest_period)
            if latest_period_match:
                year_int = int(latest_period_match.group(1))
                month_str = REVERSE_MONTHS_BY_NUM.get(int(latest_period_match.group(2)), month_str)

        planned_metric_id = (
            validated_plan_v2.operations[0].metric_id
            if len(validated_plan_v2.operations) == 1
            else None
        )
        metric_arg = str(
            (planned_metric_id if team_level_query else None)
            or tool_args.get("metric_id")
            or planned_metric_id
            or routed.plan.metric
            or (prior.metric_id if prior else None)
            or "waitingtime"
        ).strip().casefold()
        catalog = get_ai_catalog()
        metric_definition = catalog.find_metric_definition(
            team=team,
            kpi_key_or_label=metric_arg,
            position=emp_pos,
            performance_level=validated_plan_v2.scope.performance_level or "Employee",
        )
        metric_scope_rebased = False
        original_metric_id = metric_definition.metric_id if metric_definition else None
        if metric_definition and metric_definition.team.casefold() != team.casefold():
            requested_label = metric_definition.display_name
            team_metric_definition = catalog.find_metric_definition(
                team=team,
                kpi_key_or_label=requested_label,
                position=emp_pos,
                performance_level=validated_plan_v2.scope.performance_level or "Employee",
            )
            if team_metric_definition is None:
                metric_leaf = metric_arg.rsplit(":", 1)[-1].replace("_", " ")
                team_metric_definition = catalog.find_metric_definition(
                    team=team,
                    kpi_key_or_label=metric_leaf,
                    position=emp_pos,
                    performance_level=validated_plan_v2.scope.performance_level or "Employee",
                )
            if team_metric_definition is not None:
                metric_definition = team_metric_definition
                metric_scope_rebased = True
        canonical_metric_id = metric_definition.metric_id if metric_definition else None
        if canonical_metric_id:
            kpi_key = canonical_metric_id.rsplit(":", 1)[-1]
            kpi_display = metric_definition.display_name
            if metric_scope_rebased:
                routed.plan.metric = canonical_metric_id
                routed.confirmed_context.metric_id = canonical_metric_id
                for operation in validated_plan_v2.operations:
                    if operation.metric_id and operation.metric_id.casefold() == str(original_metric_id).casefold():
                        operation.metric_id = canonical_metric_id
        elif "wait" in metric_arg:
            kpi_key = "waitingtime"
            kpi_display = "Waiting Time"
        elif "book" in metric_arg:
            kpi_key = "bookings_count"
            kpi_display = "Bookings Count"
        elif "attend" in metric_arg:
            kpi_key = "attendance"
            kpi_display = "Attendance"
        elif "score" in metric_arg or "pms" in metric_arg or "perform" in metric_arg:
            kpi_key = "overall_score"
            kpi_display = "Overall Score"
        else:
            kpi_key = metric_arg.split(":")[-1]
            kpi_display = kpi_key.replace("_", " ").title()

        single_operation = validated_plan_v2.operations[0] if len(validated_plan_v2.operations) == 1 else None
        single_operation_kind = str(single_operation.kind) if single_operation else ""
        if single_operation_kind in ("compare_branches", "branch_comparison"):
            routed.plan.intent = "compare_branches"
            routed.plan.operation_kind_v2 = "compare_branches"
        elif single_operation_kind in ("score_drivers", "diagnosis"):
            routed.plan.intent = "score_drivers"
            routed.plan.operation_kind_v2 = "score_drivers"
        canonical_tool_for_operation = {
            "trend": "get_employee_history" if emp_id else "get_score_trend",
            "compare_periods": "get_employee_history" if emp_id else "get_score_trend",
            "ranking": "rank_employees",
            "compare_branches": "compare_branches",
            "branch_comparison": "compare_branches",
            "score_drivers": "get_kpi_diagnosis",
            "diagnosis": "get_kpi_diagnosis",
        }.get(single_operation_kind)
        if emp_id and single_operation_kind in (
            "current_value",
            "actual_vs_target",
            "person_summary",
        ):
            canonical_tool_for_operation = "read_employee_metric"
        elif (
            not emp_id
            and (branch or routed.plan.branch)
            and single_operation_kind in ("current_value", "actual_vs_target")
            and metric_definition is not None
            and metric_definition.value_kind == "count"
        ):
            canonical_tool_for_operation = "compare_branches"
        elif (
            not emp_id and single_operation_kind in ("current_value", "actual_vs_target")
            and (
                tool_name == "compare_branches"
                or (tool_name == "read_employee_metric" and (team_level_query or tool_args.get("branch") != branch))
            )
        ):
            canonical_tool_for_operation = "get_kpi_diagnosis"
        threshold_spec = parse_score_threshold_query(req.prompt)
        if threshold_spec is not None:
            canonical_tool_for_operation = "rank_employees"
        if canonical_tool_for_operation:
            tool_name = canonical_tool_for_operation

        # Check if trend / multi-month
        is_history = (
            single_operation_kind in ("trend", "compare_periods")
            or tool_name in ("get_employee_history", "read_employee_history")
            or any(kw in req.prompt.casefold() for kw in ("change", "trend", "across", "months", "history", "evolv"))
        )
        if is_history and (
            single_operation_kind in ("trend", "compare_periods")
            or re.search(r"\bhow\s+did\b.*\bchange\b", req.prompt.casefold())
        ):
            routed.plan.operation_kind_v2 = "trend"
            if routed.plan.intent in ("current_value", "person_summary"):
                routed.plan.intent = "trend"
        months_window = 6 if is_history else 1

        # Prepare tool arguments
        effective_tool_args = dict(tool_args)
        if threshold_spec is not None:
            effective_tool_args["threshold_operator"] = threshold_spec[0]
            effective_tool_args["score_threshold"] = threshold_spec[1]
        if scope_changed:
            if requested_team:
                effective_tool_args["team"] = requested_team
            else:
                effective_tool_args.pop("team", None)
            if not prompt_mentions_employee:
                effective_tool_args.pop("employee_id", None)
                effective_tool_args.pop("employee_name", None)
            if not routed.plan.branch:
                effective_tool_args.pop("branch", None)
        if "team" not in effective_tool_args or not effective_tool_args["team"]:
            effective_tool_args["team"] = team
        effective_tool_args["branch"] = branch
        effective_tool_args["metric_id"] = canonical_metric_id or kpi_key
        effective_tool_args["metric"] = canonical_metric_id or kpi_key
        if emp_id and "employee_id" not in effective_tool_args:
            effective_tool_args["employee_id"] = emp_id
        if emp_name and "employee_name" not in effective_tool_args:
            effective_tool_args["employee_name"] = emp_name
        if "period" not in effective_tool_args or not effective_tool_args["period"]:
            effective_tool_args["period"] = f"{year_int:04d}-{MONTHS.get(month_str, 9):02d}"

        # 4. Execute the model-selected call, completing a validated two-operation plan when needed.
        call_specs: list[tuple[str, dict[str, Any]]] = [(tool_name, effective_tool_args)]
        if single_operation and canonical_tool_for_operation:
            operation_periods = list(validated_plan_v2.scope.periods)
            plan_period = operation_periods[-1] if operation_periods else effective_tool_args.get("period")
            canonical_metric = canonical_metric_id or str(single_operation.metric_id or kpi_key)
            canonical_args = dict(effective_tool_args)
            canonical_args.update(
                {
                    "team": requested_team or team,
                    "metric_id": canonical_metric,
                    "metric": canonical_metric,
                    "period": plan_period,
                }
            )
            if validated_plan_v2.scope.performance_level:
                canonical_args["performance_level"] = validated_plan_v2.scope.performance_level
            if branch and not scope_changed:
                canonical_args["branch"] = branch
            if single_operation_kind in ("trend", "compare_periods") and operation_periods:
                canonical_args["periods"] = operation_periods
            if single_operation_kind == "ranking":
                canonical_args["limit"] = int(single_operation.limit or 1)
                canonical_args["include_ties"] = bool(single_operation.include_ties)
                canonical_args["direction"] = single_operation.direction or routed.plan.ranking_direction
            if threshold_spec is not None:
                canonical_args["threshold_operator"] = threshold_spec[0]
                canonical_args["score_threshold"] = threshold_spec[1]
            if emp_id and single_operation_kind in ("trend", "compare_periods", "person_summary", "current_value", "actual_vs_target"):
                canonical_args["employee_id"] = emp_id
                if emp_name:
                    canonical_args["employee_name"] = emp_name
            if emp_id and single_operation_kind in ("score_drivers", "diagnosis"):
                canonical_args["employee_id"] = emp_id
                if emp_name:
                    canonical_args["employee_name"] = emp_name
            if canonical_tool_for_operation == "compare_branches":
                requested_branches = [
                    str(value).strip().casefold()
                    for value in (routed.plan.branches or [])
                    if str(value).strip()
                ]
                if not requested_branches:
                    requested_branches = [
                        str(value).strip().casefold()
                        for value in (branch, routed.plan.compare_branch)
                        if value and str(value).strip()
                    ]
                canonical_args = {
                    "team": requested_team or team,
                    "branches": requested_branches,
                    "metric": canonical_metric,
                    "period": plan_period,
                }
            elif canonical_tool_for_operation == "get_kpi_diagnosis":
                canonical_args.pop("metric", None)
                if not routed.plan.compare_branch:
                    canonical_args.pop("compare_branch", None)
                canonical_args["branch"] = branch
            call_specs = [(canonical_tool_for_operation, canonical_args)]
            tool_args_with_kpi = dict(canonical_args)
            if metric_definition is not None:
                tool_args_with_kpi["kpi_key"] = metric_definition.kpi_key
            routed.plan.model_led_tool_call = {
                "tool_name": canonical_tool_for_operation,
                "tool_arguments": tool_args_with_kpi,
            }
            routed.plan.model_led_tool_calls = [
                {"tool_name": canonical_tool_for_operation, "tool_arguments": dict(tool_args_with_kpi)}
            ]
        elif metric_definition is not None and isinstance(routed.plan.model_led_tool_call, dict):
            ta = dict(routed.plan.model_led_tool_call.get("tool_arguments") or {})
            ta.setdefault("kpi_key", metric_definition.kpi_key)
            routed.plan.model_led_tool_call = {
                **routed.plan.model_led_tool_call,
                "tool_arguments": ta,
            }
        if len(validated_plan_v2.operations) > 1:
            model_calls = routed.plan.model_led_tool_calls or [
                {"tool_name": tool_name, "tool_arguments": tool_args}
            ]
            planned_specs: list[tuple[str, dict[str, Any]]] = []
            scope_team = requested_team or team
            plan_period = (
                validated_plan_v2.scope.periods[-1]
                if validated_plan_v2.scope.periods
                else effective_tool_args.get("period")
            )
            for operation in validated_plan_v2.operations[:2]:
                metric_id = canonical_metric_id or str(operation.metric_id or metric_arg_raw or kpi_key).split(":")[-1]
                operation_kind = str(operation.kind)
                if operation_kind == "trend":
                    derived_name = "get_employee_history" if emp_id and not team_level_compound else "get_score_trend"
                    accepted_names = {"get_score_trend"} if team_level_compound else {"get_employee_history", "get_score_trend"}
                elif operation_kind == "ranking":
                    derived_name = "rank_employees"
                    accepted_names = {"rank_employees"}
                elif operation_kind in ("compare_branches", "branch_comparison"):
                    derived_name = "compare_branches"
                    accepted_names = {"compare_branches"}
                elif operation_kind in ("score_drivers", "actual_vs_target", "diagnosis"):
                    derived_name = "get_kpi_diagnosis"
                    accepted_names = {"get_kpi_diagnosis", "read_employee_metric"}
                else:
                    derived_name = "read_employee_metric"
                    accepted_names = {"read_employee_metric"}

                derived_args: dict[str, Any] = {
                    "team": scope_team,
                    "metric_id": metric_id,
                    "period": plan_period,
                    "branch": branch,
                }
                if operation_kind == "trend" and validated_plan_v2.scope.periods:
                    derived_args["periods"] = list(validated_plan_v2.scope.periods)
                if operation_kind in ("compare_branches", "branch_comparison"):
                    derived_args["metric"] = metric_id
                    if routed.plan.branches:
                        derived_args["branches"] = list(routed.plan.branches)
                if operation_kind == "ranking":
                    derived_args["limit"] = int(operation.limit or 1)
                    derived_args["include_ties"] = bool(operation.include_ties)
                    derived_args["direction"] = operation.direction or routed.plan.ranking_direction
                if validated_plan_v2.scope.performance_level:
                    derived_args["performance_level"] = validated_plan_v2.scope.performance_level
                if emp_id and operation_kind == "trend":
                    derived_args["employee_id"] = emp_id
                    if emp_name:
                        derived_args["employee_name"] = emp_name

                model_match: tuple[str, dict[str, Any]] | None = None
                for candidate in model_calls:
                    if not isinstance(candidate, dict):
                        continue
                    candidate_name = str(candidate.get("tool_name") or "").strip()
                    if candidate_name not in accepted_names:
                        continue
                    candidate_args = candidate.get("tool_arguments")
                    candidate_args = dict(candidate_args) if isinstance(candidate_args, dict) else {}
                    if scope_changed:
                        if not requested_team:
                            candidate_args.pop("team", None)
                        if not routed.plan.branch:
                            candidate_args.pop("branch", None)
                        if not prompt_mentions_employee:
                            candidate_args.pop("employee_id", None)
                            candidate_args.pop("employee_name", None)
                    if team_level_compound:
                        candidate_args.pop("employee_id", None)
                        candidate_args.pop("employee_name", None)
                    merged_args = {**candidate_args, **derived_args}
                    requested_metric_id = str(candidate_args.get("metric_id") or "").strip()
                    if requested_metric_id and canonical_metric_id:
                        normalize_metric_ref = lambda value: re.sub(
                            r"[^a-z0-9]", "", str(value or "").casefold().rsplit(":", 1)[-1]
                        )
                        allowed_metric_refs = {
                            normalize_metric_ref(canonical_metric_id),
                            normalize_metric_ref(getattr(metric_definition, "kpi_key", "")),
                            normalize_metric_ref(getattr(metric_definition, "display_name", "")),
                            *(
                                normalize_metric_ref(alias)
                                for alias in (getattr(metric_definition, "aliases", ()) or ())
                            ),
                        }
                        if normalize_metric_ref(requested_metric_id) in allowed_metric_refs:
                            merged_args["requested_metric_id"] = requested_metric_id.rsplit(":", 1)[-1]
                    model_match = (candidate_name, merged_args)
                    break
                planned_specs.append(model_match or (derived_name, derived_args))
            if planned_specs:
                call_specs = planned_specs[:2]

        try:
            tool_results: list[ToolExecutionResult] = []
            tool_records: list[AiToolCallRecord] = []
            tool_exec_ms_total = 0.0
            for call_name, call_args in call_specs:
                call_start = time.perf_counter()
                if call_name in registry.AUTHORIZED_MODEL_LED_TOOLS:
                    call_result = registry.execute_model_led_tool(
                        tool_name=call_name,
                        tool_arguments=call_args,
                    )
                elif call_name == "agent_spotlight_trend":
                    call_result = registry.execute_agent_spotlight_and_trend(
                        team=call_args.get("team") or team,
                        branch=call_args.get("branch") or branch,
                        month=month_str,
                        year=year_int,
                        kpi=call_args.get("metric_id") or kpi_key,
                        employee_query=call_args.get("employee_name") or call_args.get("employee_id") or emp_name or emp_id,
                        single_person=True,
                        months_window=months_window,
                    )
                else:
                    raise ValueError(f"Tool '{call_name}' is not an authorized model-led tool")
                call_ms = round((time.perf_counter() - call_start) * 1000.0, 2)
                tool_exec_ms_total += call_ms
                tool_results.append(call_result)
                tool_records.append(
                    AiToolCallRecord(
                        tool_name=call_name,
                        arguments=call_args,
                        records_evaluated=call_result.records_evaluated,
                    )
                )
            tool_name, tool_args = call_specs[0]
            executed_period = str(tool_args.get("period") or "").strip()
            executed_period_match = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", executed_period)
            if executed_period_match:
                year_int = int(executed_period_match.group(1))
                month_str = REVERSE_MONTHS_BY_NUM.get(int(executed_period_match.group(2)), month_str)
            tool_result = tool_results[0]
            for extra_result in tool_results[1:]:
                tool_result.records_evaluated += extra_result.records_evaluated
                tool_result.visual_cards.extend(extra_result.visual_cards)
                tool_result.citations.extend(extra_result.citations)
                tool_result.deep_links.extend(extra_result.deep_links)
                tool_result.typed_evidence.extend(extra_result.typed_evidence)
                tool_result.guardrail_triggered = tool_result.guardrail_triggered or extra_result.guardrail_triggered
                if not tool_result.basis_warning:
                    tool_result.basis_warning = extra_result.basis_warning
            all_tool_digests = [result.digest for result in tool_results]
            t_tool_ms = round(tool_exec_ms_total, 2)
        except PermissionError as p_exc:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="restricted_access",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Access restricted: your permissions do not allow viewing this employee or scope.",
                narrative_bullets=[str(p_exc)],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome="restricted_access",
                ),
            )
        except Exception as exc:
            # Handle malformed arguments gracefully
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="clarification",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Could not complete query with the provided arguments.",
                narrative_bullets=[str(exc)],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-fallback",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome="invalid_tool_arguments",
                ),
            )

        # 5. Check returned evidence authorization
        ev_auth = live_auth_service.is_returned_evidence_authorized(
            scope=self.scope,
            typed_evidence=tool_result.typed_evidence,
            tool_digests=all_tool_digests,
        )
        if not ev_auth:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="restricted_access",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Access restricted: live permission revalidation detected unauthorized records.",
                narrative_bullets=["Your role does not allow viewing the returned evaluation evidence."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=tool_records,
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome="restricted_access",
                ),
            )

        # 6. Check missing data
        if tool_result.records_evaluated == 0 or not tool_result.typed_evidence:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            missing_team = requested_team or (None if scope_changed else team)
            missing_period = f"{year_int:04d}-{MONTHS.get(month_str, 9):02d}"
            missing_context = routed.confirmed_context.model_copy(
                update={
                    "intent": routed.plan.intent,
                    "team": missing_team,
                    "function": requested_function or routed.confirmed_context.function,
                    "position": routed.plan.position or (None if scope_changed else emp_pos),
                    "branch": branch,
                    "region": current_region,
                    "performance_level": routed.plan.performance_level or (
                        None if scope_changed else req.session_state.performance_level
                    ),
                    "metric_id": canonical_metric_id or metric_arg,
                    "metric_display_name": kpi_display,
                    "periods": [missing_period],
                    "last_subject_employee_id": None if scope_changed else emp_id,
                    "last_subject_employee_name": None if scope_changed else (emp_name or None),
                    "candidate_employees": [] if scope_changed else routed.confirmed_context.candidate_employees,
                }
            )
            missing_state = req.session_state.model_copy(
                update={
                    "function": missing_context.function,
                    "team": missing_context.team,
                    "position": missing_context.position,
                    "branch": missing_context.branch,
                    "region": missing_context.region,
                    "performance_level": missing_context.performance_level,
                    "employee_id": missing_context.last_subject_employee_id,
                    "month": month_str,
                    "year": year_int,
                    "last_confirmed_query": missing_context,
                }
            )
            missing_scope_name = _format_country_scope_text(
                missing_context.team or missing_context.function or "the requested subject",
                missing_context.team,
                missing_context.region,
            )
            missing_scope_banner, _ = self._resolve_scope_banner_and_function(
                session_state=missing_state,
                region=missing_context.region,
            )
            ucm = (
                tool_result.digest.get("unavailable_count_metric")
                if isinstance(tool_result.digest, dict)
                else None
            )
            missing_outcome: Any = "unavailable_data"
            if ucm and not tool_result.typed_evidence:
                ucm_team_lbl = str(ucm.get("team") or missing_scope_name)
                ucm_branch = ucm.get("branch") or branch
                ucm_branch_title = str(ucm_branch).capitalize() if ucm_branch else ""
                missing_headline = (
                    f"No published {ucm['display_name']} records exist for {ucm_team_lbl} in {ucm_branch_title} ({month_str} {year_int})."
                    if ucm_branch_title
                    else f"No published {ucm['display_name']} records exist for {ucm_team_lbl} ({month_str} {year_int})."
                )
            elif (
                tool_name == "get_kpi_diagnosis"
                and not emp_id
                and branch
                and current_region != "KSA"
                and not ksa_region_hint_from_prompt(req.prompt)
                and (not metric_definition or getattr(metric_definition, "value_kind", None) != "count")
                and (not published_periods or missing_period in published_periods)
            ):
                missing_outcome = "answer"
                missing_headline = (
                    f"No performance records matched the selected filters ({missing_scope_name} · {month_str} {year_int} · {str(branch).capitalize()})."
                )
            else:
                branch_clause = f" in {str(branch).capitalize()}" if branch and str(branch).casefold() != "all" else ""
                missing_headline = f"No published PMS evaluation records exist for {emp_name or missing_scope_name}{branch_clause} in {month_str} {year_int}."
            missing_response = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome=missing_outcome,
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline=missing_headline,
                narrative_bullets=[] if missing_outcome == "answer" else [f"No performance data was found for {missing_scope_name} in {month_str} {year_int}."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=missing_state,
                scope_banner=missing_scope_banner,
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=tool_records,
                provider_used="deterministic",
                model_used="deterministic-fallback",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome=missing_outcome,
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = missing_response.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="unavailable_data",
                    turn_kind="clarification",
                    route_used="model_led_pilot",
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=missing_state,
                    confirmed_context=missing_context,
                    provider_calls=routed.provider_metrics.provider_calls,
                    total_ms=tot_ms,
                )
                missing_response.context_version = new_ver
            return missing_response

        # 7. Grounded Model Synthesis Pass
        def _norm_k(k: str | None) -> str:
            return re.sub(r"[^a-z0-9]", "", str(k or "").casefold())
        def _metric_tokens(value: str | None) -> set[str]:
            raw = str(value or "").strip()
            values = {raw}
            if ":" in raw:
                values.add(raw.rsplit(":", 1)[-1])
            return {token for item in values if (token := _norm_k(item))}

        requested_metric_tokens = set().union(
            _metric_tokens(kpi_key),
            _metric_tokens(canonical_metric_id),
            _metric_tokens(metric_arg),
            _metric_tokens(kpi_display),
        )
        if metric_definition:
            requested_metric_tokens.update(_metric_tokens(metric_definition.kpi_key))
            requested_metric_tokens.update(
                token
                for alias in metric_definition.aliases
                for token in _metric_tokens(alias)
            )
        ev_items = [
            ev for ev in tool_result.typed_evidence
            if (
                _metric_tokens(ev.kpi_key)
                | _metric_tokens(ev.metric_id)
                | _metric_tokens(ev.display_name)
            )
            & requested_metric_tokens
        ]

        def _period_id(raw_period: str | None) -> str | None:
            text = str(raw_period or "").strip()
            iso_match = re.match(r"^(20\d{2})-(0[1-9]|1[0-2])$", text)
            if iso_match:
                return f"{int(iso_match.group(1)):04d}-{int(iso_match.group(2)):02d}"
            human_match = re.search(r"\b([A-Za-z]+)\s+(20\d{2})\b", text)
            if human_match:
                month_number = MONTHS.get(human_match.group(1).capitalize())
                if month_number:
                    return f"{int(human_match.group(2)):04d}-{month_number:02d}"
            return None

        requested_period_ids = {
            period_id
            for raw_period in validated_plan_v2.scope.periods
            if (period_id := _period_id(raw_period))
        }
        if not is_history:
            requested_period_ids = {f"{year_int:04d}-{MONTHS.get(month_str, 9):02d}"}
        if requested_period_ids and (not is_history or len(requested_period_ids) >= 2):
            ev_items = [ev for ev in ev_items if _period_id(ev.period) in requested_period_ids]

        is_position_query = any(kw in req.prompt.casefold() for kw in ("job title", "position", "role"))
        if not ev_items and is_position_query:
            ev_items = [
                ev for ev in tool_result.typed_evidence
                if (emp_id and ev.employee_id == emp_id)
                or (emp_name and ev.employee_name and ev.employee_name.casefold() == emp_name.casefold())
            ]

        if not ev_items:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            return AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="unavailable_data",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline=f"No published {kpi_display} evidence was found for {emp_name or team} in the requested period.",
                narrative_bullets=["No answer was produced because the requested metric evidence was unavailable."],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=tool_records,
                provider_used="deterministic",
                model_used="deterministic-fallback",
                answer_source="fallback",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(total_ms=tot_ms),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    fallback_outcome="unavailable_data",
                ),
            )

        if is_history and len(validated_plan_v2.scope.periods) >= 2:
            req_p_labels = {format_period_label(p).casefold() for p in validated_plan_v2.scope.periods}
            matched_ev_items = [ev for ev in ev_items if str(ev.period or "").strip().casefold() in req_p_labels]
            if len(matched_ev_items) >= 2:
                ev_items = matched_ev_items
        if not is_history and month_str:
            latest_ev = ev_items[-1]
        else:
            latest_ev = ev_items[-1]

        def _safe_period_label(p: str) -> str:
            if not p:
                return f"{month_str} {year_int}"
            if "-" in p:
                return format_period_label(p)
            return p

        if latest_ev.display_name and latest_ev.display_name.casefold() not in ("overall pms score", "score", "overall score"):
            kpi_display = latest_ev.display_name
        unit = latest_ev.unit or ("min" if "wait" in kpi_key else ("%" if "score" in kpi_key or "attend" in kpi_key else ""))
        curr_val = latest_ev.actual
        curr_period = latest_ev.period or f"{year_int:04d}-{MONTHS.get(month_str, 9):02d}"
        curr_period_label = _safe_period_label(curr_period)

        display_subject = getattr(latest_ev, "employee_name", None) or emp_name or latest_ev.team or team
        compound_required_groups: list[list[str]] = []
        compound_trend_result = (
            tool_results[0]
            if len(validated_plan_v2.operations) > 1
            and validated_plan_v2.operations[0].kind == "trend"
            and tool_results
            else next(
                (result for result in tool_results if result.tool_name in ("get_employee_history", "get_score_trend")),
                None,
            )
        )
        compound_rank_result = (
            tool_results[1]
            if len(validated_plan_v2.operations) > 1
            and validated_plan_v2.operations[1].kind == "ranking"
            and len(tool_results) > 1
            else next(
                (result for result in tool_results if result.tool_name == "rank_employees"),
                None,
            )
        )
        compound_trend_evidence: list[TypedMetricEvidence] = []
        compound_rank_evidence: list[TypedMetricEvidence] = []
        if compound_trend_result and compound_rank_result and len(validated_plan_v2.operations) > 1:
            requested_metric = _norm_k(
                str(validated_plan_v2.operations[0].metric_id or kpi_key).rsplit(":", 1)[-1]
            )
            compound_trend_evidence = [
                ev for ev in compound_trend_result.typed_evidence
                if ev.actual is not None
                and (not team_level_compound or (not ev.employee_id and not ev.employee_name))
                and (
                    _norm_k(ev.kpi_key) == requested_metric
                    or _norm_k(ev.metric_id).endswith(requested_metric)
                    or requested_metric in _norm_k(ev.display_name)
                )
            ]
            compound_rank_evidence = [
                ev for ev in compound_rank_result.typed_evidence
                if ev.employee_name
                and ev.actual is not None
                and (
                    _norm_k(ev.kpi_key) == requested_metric
                    or _norm_k(ev.metric_id).endswith(requested_metric)
                    or requested_metric in _norm_k(ev.display_name)
                )
            ]

        compound_trend_ready = len({ev.period for ev in compound_trend_evidence}) >= 2
        compound_rank_ready = bool(compound_rank_evidence)

        if compound_trend_ready and compound_rank_ready:
            month_index = {name.casefold(): index for index, name in enumerate(MONTHS, start=1)}

            def _compound_period_key(ev: TypedMetricEvidence) -> tuple[int, int, str]:
                match = re.search(r"([A-Za-z]+)\s+(20\d{2})", ev.period or "")
                if match:
                    return (int(match.group(2)), month_index.get(match.group(1).casefold(), 0), ev.period)
                iso_match = re.match(r"(20\d{2})-(\d{2})", ev.period or "")
                if iso_match:
                    return (int(iso_match.group(1)), int(iso_match.group(2)), ev.period)
                return (0, 0, ev.period or "")

            compound_trend_evidence.sort(key=_compound_period_key)
            trend_first, trend_last = compound_trend_evidence[0], compound_trend_evidence[-1]
            top_performer = compound_rank_evidence[0]
            compound_metric_display = trend_last.display_name or kpi_display
            compound_unit = trend_last.unit or unit
            trend_subject = (
                f"{trend_last.employee_name}'s"
                if trend_last.employee_name
                else f"{team} team's"
            )
            trend_first_period = _safe_period_label(trend_first.period)
            trend_last_period = _safe_period_label(trend_last.period)
            rank_period = _safe_period_label(top_performer.period)
            first_display = trend_first.actual_display or f"{trend_first.actual} {compound_unit}".strip()
            last_display = trend_last.actual_display or f"{trend_last.actual} {compound_unit}".strip()
            rank_display = top_performer.actual_display or f"{top_performer.actual} {top_performer.unit}".strip()
            fallback_headline = (
                f"{top_performer.employee_name} was the top performer in {team} for {compound_metric_display} "
                f"in {rank_period} with {rank_display}. {trend_subject} {compound_metric_display} changed "
                f"from {first_display} in {trend_first_period} to {last_display} in {trend_last_period}."
            )
            fallback_bullets = [
                f"{trend_first_period}: {first_display}",
                f"{trend_last_period}: {last_display}",
                f"Top performer in {rank_period}: {top_performer.employee_name} ({rank_display})",
            ]
            facts_payload = {
                "team": team,
                "metric": compound_metric_display,
                "trend": [
                    {"period": trend_first_period, "value": trend_first.actual, "display": first_display, "unit": compound_unit},
                    {"period": trend_last_period, "value": trend_last.actual, "display": last_display, "unit": compound_unit},
                ],
                "top_performer": {
                    "employee": top_performer.employee_name,
                    "period": rank_period,
                    "value": top_performer.actual,
                    "display": rank_display,
                    "unit": top_performer.unit,
                },
            }
            instruction = (
                "Answer both parts of the question in the same response: report the verified trend values for both periods, "
                "then name the first employee in the verified ranking and give that employee's value. Use only the supplied facts. "
                "Do not omit a requested period, employee, metric, value, or unit; do not invent numbers. "
                'Return JSON with {"headline": "...", "narrative_bullets": [...]}.'
            )
            compound_required_groups = [
                [str(top_performer.employee_name or "").casefold()],
                [compound_metric_display.casefold()],
                [trend_first_period.casefold()],
                [trend_last_period.casefold()],
                list(dict.fromkeys(
                    [str(trend_first.actual), f"{trend_first.actual:.1f}"]
                    + ([str(int(float(trend_first.actual)))] if float(trend_first.actual).is_integer() else [])
                )),
                list(dict.fromkeys(
                    [str(trend_last.actual), f"{trend_last.actual:.1f}"]
                    + ([str(int(float(trend_last.actual)))] if float(trend_last.actual).is_integer() else [])
                )),
                ["top", "highest", "most"],
            ]
        elif tool_name == "compare_branches":
            branch_ev = [ev for ev in tool_result.typed_evidence if ev.branch and ev.branch != "all" and ev.actual is not None]
            period_lbl = f"{month_str} {year_int}"
            fallback_headline = f"UAE branch comparison for {team} in {period_lbl}: " + ", ".join(
                f"{ev.branch.capitalize()}: {ev.actual_display}" for ev in branch_ev
            ) + "."
            fallback_bullets = [f"{ev.branch.capitalize()}: {ev.actual_display}" for ev in branch_ev]
            facts_payload = {
                "team": team,
                "metric": kpi_display,
                "period": period_lbl,
                "branches": [
                    {"branch": ev.branch.capitalize(), "value": ev.actual, "unit": ev.unit}
                    for ev in branch_ev
                ],
            }
            instruction = (
                "You are the PMS AI Assistant. State the verified branch comparison answer directly and concisely in 1-2 sentences. "
                "Use ONLY the exact branch names, metric name, period, values, and unit in `verified_facts`. "
                "Do NOT use causal words like 'because' or 'due to'. Do NOT invent numbers. "
                'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
            )
        elif tool_name == "rank_employees":
            tcs = (tool_result.digest or {}).get("threshold_count_summary") if isinstance(tool_result.digest, dict) else None
            if tcs:
                cnt = int(tcs.get("count") or 0)
                tot = int(tcs.get("total_evaluated") or 0)
                op_lbl = str(tcs.get("operator_label") or "above")
                thr = tcs.get("threshold")
                thr_txt = f"{thr:g}%" if thr is not None else ""
                t_team = str(tcs.get("team") or team)
                t_period = str(tcs.get("period") or f"{month_str} {year_int}")
                q_emps = tcs.get("qualifying_employees") or []
                emp_word = "employee" if cnt == 1 else "employees"
                if tot == 0:
                    fallback_headline = f"No published PMS evaluation records matched {t_team} in {t_period}."
                elif q_emps:
                    names_txt = ", ".join(f"{e['employee_name']} ({e['score']:.1f}%)" for e in q_emps[:10])
                    fallback_headline = f"In {t_team} ({t_period}), {cnt} of {tot} evaluated {emp_word} scored {op_lbl} {thr_txt}: {names_txt}."
                else:
                    fallback_headline = f"In {t_team} ({t_period}), 0 of {tot} evaluated employees scored {op_lbl} {thr_txt}."
                fallback_bullets = [f"{e['employee_name']} ({e['employee_id']}): {e['score']:.1f}%." for e in q_emps[:5]]
                facts_payload = {"threshold_count_summary": tcs}
                instruction = (
                    "You are the PMS AI Assistant. State the exact qualifying employee count and qualifying employee names/scores "
                    "from `verified_facts.threshold_count_summary` directly and concisely in 1-2 sentences. Do NOT invent numbers. "
                    'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
                )
            else:
                rank_ev = [ev for ev in ev_items if ev.employee_name and ev.actual is not None]
                period_lbl = f"{month_str} {year_int}"
                fallback_headline = f"Employee performance rankings for {team} in {period_lbl}: " + ", ".join(
                    f"{ev.employee_name}: {ev.actual_display}" for ev in rank_ev[:5]
                ) + "."
                fallback_bullets = [f"{ev.employee_name}: {ev.actual_display}" for ev in rank_ev[:5]]
                facts_payload = {
                    "team": team,
                    "metric": kpi_display,
                    "period": period_lbl,
                    "rankings": [
                        {"rank": i + 1, "employee": ev.employee_name, "value": ev.actual, "unit": ev.unit}
                        for i, ev in enumerate(rank_ev[:5])
                    ],
                }
                instruction = (
                    "You are the PMS AI Assistant. State the verified employee rankings directly and concisely in 1-2 sentences. "
                    "Use ONLY the exact employee names, metric name, period, values, and unit in `verified_facts`. "
                    "Disclose any ties clearly. Do NOT invent numbers. "
                    'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
                )
        elif is_history and len(ev_items) >= 2:
            prev_ev = ev_items[-2]
            prev_val = prev_ev.actual
            prev_period = prev_ev.period
            prev_period_label = _safe_period_label(prev_period)
            delta = round(curr_val - prev_val, 2)
            is_better = (delta < 0) if latest_ev.direction == "lower_better" else (delta > 0)
            if delta == 0:
                diff_word = "unchanged"
                change = f"0.0 {unit} (unchanged)"
                direction_instruction = "State that the value was unchanged."
            else:
                diff_word = "improvement" if is_better else "worsening"
                change = f"{abs(delta):.1f} {unit} ({diff_word})"
                direction_instruction = f"Describe the change of {abs(delta):.1f} {unit} as {diff_word}."
            fallback_headline = (
                f"{display_subject}'s {kpi_display} went from {prev_val} {unit} in {prev_period_label} "
                f"to {curr_val} {unit} in {curr_period_label}. Change: {change}."
            )
            fallback_bullets = [
                f"{prev_period_label}: {prev_val} {unit}",
                f"{curr_period_label}: {curr_val} {unit}",
                f"Change: {change}",
            ]
            facts_payload = {
                "employee": display_subject,
                "metric": kpi_display,
                "unit": unit,
                "history": [
                    {"period": prev_period_label, "value": prev_val, "unit": unit},
                    {"period": curr_period_label, "value": curr_val, "unit": unit},
                ],
                "delta": delta,
                "evaluation": diff_word,
            }
            instruction = (
                "You are the PMS AI Assistant. State the verified performance trend answer directly and concisely in 1-2 sentences. "
                "Use ONLY the exact employee name, metric name, periods, values, and unit in `verified_facts`. "
                f"State both the {prev_period_label} value and the {curr_period_label} value. {direction_instruction} "
                "Do NOT use causal words like 'because' or 'due to'. Do NOT invent numbers. "
                'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
            )
        else:
            eff_dir = latest_ev.direction or "higher_better"
            tgt_clause = ""
            tgt_note = ""
            if latest_ev.target is not None:
                tgt_val = float(latest_ev.target)
                c_val = float(curr_val)
                diff = round(abs(c_val - tgt_val), 2)
                if eff_dir == "lower_better":
                    if c_val <= tgt_val:
                        tgt_clause = f"meeting the target of {tgt_val} {unit}"
                        tgt_note = f"The headline must state that {display_subject}'s {kpi_display} was {c_val} {unit} in {curr_period_label}, meeting the target of {tgt_val} {unit} (for {kpi_display}, lower is better)."
                    else:
                        tgt_clause = f"exceeding the target limit of {tgt_val} {unit} by {diff:.1f} {unit}"
                        tgt_note = (
                            f"The headline must state that {display_subject}'s {kpi_display} was {c_val} {unit} in {curr_period_label}, exceeding the target limit of {tgt_val} {unit} by {diff:.1f} {unit} (did not meet target). "
                            "Do NOT state that it met the target."
                        )
                else:
                    if c_val >= tgt_val:
                        tgt_clause = f"meeting the target of {tgt_val} {unit}"
                        tgt_note = f"The headline must state that {display_subject}'s {kpi_display} was {c_val} {unit} in {curr_period_label}, meeting the target of {tgt_val} {unit}."
                    else:
                        tgt_clause = f"falling short of the target of {tgt_val} {unit} by {diff:.1f} {unit}"
                        tgt_note = (
                            f"The headline must state that {display_subject}'s {kpi_display} was {c_val} {unit} in {curr_period_label}, falling short of the target of {tgt_val} {unit} by {diff:.1f} {unit}. "
                            "Do NOT state that it met the target."
                        )

            is_pos_query = is_position_query
            if is_pos_query:
                pos_val = str(getattr(latest_ev, "position", None) or emp_pos or "Call Center Agent").strip()
                fallback_headline = f"{display_subject}'s job title is {pos_val} ({team})."
                fallback_bullets = [f"Position: {pos_val}", f"Team: {team}"]
                facts_payload = {
                    "employee": display_subject,
                    "team": team,
                    "position": pos_val,
                    "metric": "Job Title",
                    "period": curr_period_label,
                    "value": pos_val,
                    "unit": "",
                }
                instruction = (
                    "You are the PMS AI Assistant. State the verified employee position/job title answer directly and concisely in 1 sentence. "
                    "Use ONLY the exact employee name, position, and team from `verified_facts`. "
                    f"State that {display_subject}'s position is {pos_val} in {team}. "
                    'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
                )
            else:
                fallback_headline = (
                    f"{display_subject}'s {kpi_display} was {curr_val} {unit} in {curr_period_label}"
                    + (f", {tgt_clause}." if tgt_clause else ".")
                )
                fallback_bullets = [f"Target: {latest_ev.target} {unit}"] if latest_ev.target is not None else []
                facts_payload = {
                    "employee": display_subject,
                    "team": team,
                    "position": getattr(latest_ev, "position", None) or emp_pos,
                    "metric": kpi_display,
                    "period": curr_period_label,
                    "value": curr_val,
                    "unit": unit,
                    "target": latest_ev.target,
                    "target_status": tgt_clause,
                }
                instruction = (
                    f"[User Context]\n{self.user_rules_spec.get('summary_text', '')}\n\n"
                    "You are the PMS AI Assistant. State the verified performance answer directly and concisely in 1-2 sentences. "
                    "Use ONLY the exact employee name, metric name, period, value, and unit in `verified_facts`. "
                    "For single-period questions, report only the requested period's value and target (if present). "
                    + (f"{tgt_note} " if tgt_note else "")
                    + "Do NOT use temporal change words like 'increased', 'decreased', or 'improved' across time because there is no prior period comparison. "
                    "Do NOT use causal words like 'because' or 'due to'. Do NOT invent numbers. "
                    'Return JSON with {"headline": "...", "narrative_bullets": [...]}'
                )

        claim_ev = ev_items if is_history else [latest_ev]
        claim_ledger = build_claim_ledger(typed_evidence=claim_ev)

        # Call configured model for Pass 2 synthesis
        engine = get_unified_provider_engine()
        req_synth = ProviderRequest(
            messages=[
                ProviderMessage(
                    role="system",
                    content=f"[PromptVersion: {MODEL_LED_SYNTHESIS_PROMPT_VERSION}]\n{instruction}",
                ),
                ProviderMessage(role="user", content=f"Question: {req.prompt}\nVerified Facts: {json.dumps(facts_payload)}"),
            ],
            response_format="json",
            json_schema={
                "type": "object",
                "properties": {
                    "headline": {"type": "string"},
                    "narrative_bullets": {"type": ["array", "null"], "items": {"type": "string"}},
                },
                "required": ["headline"],
            },
            temperature=0.0,
            max_tokens=None,
            timeout_seconds=cfg.provider_timeout_seconds,
            purpose="model_led_synthesis",
            user_id=str(self.scope.get("user_id") or "") or None,
            user_role=role or None,
        )

        synth_metrics = ProviderCallMetrics(provider_used="deterministic", model_used="deterministic-fallback")
        final_headline = fallback_headline
        final_bullets = fallback_bullets
        final_provider = "deterministic"
        final_model = "deterministic-fallback"
        final_fallback_outcome = "none"
        final_answer_source = "fallback"

        try:
            resp_synth = engine.generate(req_synth)
            attempts = getattr(resp_synth, "attempts", None) or []
            synth_calls = (
                1
                if (resp_synth.is_success or any(a.status not in ("missing_key", "disabled") for a in attempts))
                else 0
            )
            synth_metrics = metrics_from_provider_response(resp_synth, provider_calls=synth_calls)
            if resp_synth.is_success and resp_synth.content:
                synth_metrics.provider_calls = 1
                parsed = json.loads(resp_synth.content)
                cand_h = str(parsed.get("headline") or "").strip()
                cand_b = [str(b).strip() for b in (parsed.get("narrative_bullets") or []) if str(b).strip()]
                # If model put value into bullets rather than headline, integrate it into headline
                has_val_in_h = str(curr_val) in cand_h or f"{curr_val:.1f}" in cand_h
                has_val_in_b = any(str(curr_val) in b or f"{curr_val:.1f}" in b for b in cand_b)
                if not has_val_in_h and has_val_in_b:
                    if f"{curr_val}" not in cand_h:
                        cand_h = f"{display_subject}'s {kpi_display} was {curr_val} {unit} in {curr_period_label} ({cand_h})."

                # Verify claims with claim validator
                check = validate_claims(headline=cand_h, bullets=cand_b, ledger=claim_ledger)
                candidate_text = (cand_h + " " + " ".join(cand_b)).casefold()
                has_compound_facts = all(
                    any(str(term).casefold() in candidate_text for term in alternatives)
                    for alternatives in compound_required_groups
                )
                # Verify exact value and unit are present
                if tool_name in ("compare_branches", "rank_employees"):
                    has_val = True
                    has_unit = True
                elif any(kw in req.prompt.casefold() for kw in ("job title", "position", "role")):
                    pos_val = str(getattr(latest_ev, "position", None) or emp_pos or "")
                    has_val = pos_val.casefold() in cand_h.casefold() or len(cand_h) > 10
                    has_unit = True
                else:
                    has_val = str(curr_val) in cand_h or f"{curr_val:.1f}" in cand_h
                    has_unit = (
                        unit.casefold() in cand_h.casefold()
                        or (unit.casefold() == "min" and "minute" in cand_h.casefold())
                        if unit else True
                    )
                if check.valid and has_val and has_unit and has_compound_facts:
                    final_headline = cand_h
                    final_bullets = cand_b if cand_b else fallback_bullets
                    if is_history and len(ev_items) >= 2 and not compound_trend_ready and not any(f"{abs(delta):.1f}" in b for b in final_bullets) and not (f"{abs(delta):.1f}" in final_headline):
                        final_bullets.append(f"Change: {abs(delta):.1f} {unit} ({diff_word})")
                    final_provider = resp_synth.provider
                    final_model = resp_synth.model
                    final_fallback_outcome = "none"
                    final_answer_source = "model_synthesis"
                else:
                    reason = check.reason_code if not check.valid else (
                        "missing_compound_component" if not has_compound_facts else ("missing_value" if not has_val else "missing_unit")
                    )
                    logger.debug(
                        "Pass 2 model synthesis rejected: cand_h=%s cand_b=%s check.valid=%s check.reason=%s check.errors=%s has_val=%s has_unit=%s",
                        cand_h, cand_b, check.valid, check.reason_code, check.errors, has_val, has_unit
                    )
                    final_fallback_outcome = f"claim_validation_failed:{reason}"
                    final_answer_source = "fallback"
            else:
                final_fallback_outcome = resp_synth.outcome or "timeout"
                final_answer_source = "fallback"
        except (ProviderTimeoutError, TimeoutError):
            final_fallback_outcome = "timeout"
            final_answer_source = "fallback"
        except Exception:
            final_fallback_outcome = "synthesis_exception"
            final_answer_source = "fallback"

        synth_metrics.fallback_outcome = final_fallback_outcome

        # Post-synthesis live RBAC re-verification before logging traces or returning evidence
        try:
            self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
        except Exception:
            if conv_service and claimed_turn and claimed_token:
                conv_service.repo.release_turn_claim(turn_id=str(claimed_turn.id), claim_token=claimed_token)
            raise

        post_exec_authorized = live_auth_service.is_plan_and_context_authorized(
            scope=self.scope,
            team=requested_team or team,
            function=requested_function or routed.confirmed_context.function,
            branch=branch,
            branches=list(routed.plan.branches or []),
            performance_level=routed.plan.performance_level or req.session_state.performance_level,
            region=current_region,
            employee_id=emp_id,
            employee_name=emp_name or None,
        )
        if post_exec_authorized:
            post_exec_authorized = live_auth_service.is_returned_evidence_authorized(
                scope=self.scope,
                typed_evidence=tool_result.typed_evidence,
                tool_digests=all_tool_digests,
                fallback_branch=branch,
                fallback_level=routed.plan.performance_level,
            )

        provider_usage = _build_aggregated_usage(
            router_mode=cfg.router_mode,
            route_used="model_led_pilot",
            router_metrics=routed.provider_metrics,
            synth_metrics=synth_metrics,
        )
        total_provider_calls = provider_usage.provider_calls
        total_provider_ms = round(float(routed.provider_metrics.provider_ms or 0.0) + float(synth_metrics.provider_ms or 0.0), 2)

        if not post_exec_authorized:
            routed.confirmed_context.team = None
            routed.confirmed_context.branch = None
            routed.confirmed_context.branches = []
            routed.confirmed_context.performance_level = None
            routed.confirmed_context.last_subject_employee_id = None
            routed.confirmed_context.last_subject_employee_name = None
            routed.confirmed_context.candidate_employees = []
            routed.confirmed_context.single_person = False
            restricted_state = req.session_state.model_copy(
                update={
                    "team": None,
                    "branch": None,
                    "performance_level": None,
                    "employee_id": None,
                    "last_confirmed_query": routed.confirmed_context,
                }
            )
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            restricted_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="restricted_access",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline="Access restricted: your permissions changed during execution and no longer allow viewing this scope.",
                narrative_bullets=[
                    "Live permission revalidation detected that access to the requested team, level, branch, function, or employee was revoked."
                ],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=["Show performance summary for my authorized scope"],
                resolved_session_state=restricted_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used="deterministic",
                model_used="deterministic-access-gate",
                answer_source="deterministic",
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(
                    resolution_ms=round((time.perf_counter() - t_res_start) * 1000.0, 2),
                    provider_ms=total_provider_ms,
                    database_ms=t_tool_ms,
                    trace_ms=0.0,
                    total_ms=tot_ms,
                ),
                provider_usage=provider_usage,
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = restricted_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="restricted_access",
                    turn_kind="clarification",
                    route_used="model_led_pilot",
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=restricted_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=total_provider_calls,
                    total_ms=tot_ms,
                )
                restricted_resp.context_version = new_ver
            return restricted_resp

        # Update confirmed context
        final_headline = _format_country_scope_text(
            final_headline,
            requested_team or team,
            current_region,
        )
        model_led_ranking = bool(
            routed.plan.intent == "ranking"
            or any(operation.kind == "ranking" for operation in validated_plan_v2.operations)
        )
        ranking_candidates = (
            _ranking_candidates_from_digests(all_tool_digests)
            if model_led_ranking and not routed.plan.employee_id
            else []
        )
        evidence_subject_ids = {
            str(evidence.employee_id).strip()
            for evidence in tool_result.typed_evidence
            if evidence.employee_id and str(evidence.employee_id).strip()
        }
        evidence_subject_id = (
            next(iter(evidence_subject_ids))
            if len(evidence_subject_ids) == 1
            and tool_name in ("read_employee_metric", "get_kpi_diagnosis")
            and not team_level_query
            and (not scope_changed or prompt_mentions_employee)
            else None
        )
        evidence_subject_name = next(
            (
                evidence.employee_name
                for evidence in tool_result.typed_evidence
                if evidence_subject_id
                and str(evidence.employee_id).strip() == evidence_subject_id
                and evidence.employee_name
            ),
            None,
        )
        confirmed_subject_id = emp_id or evidence_subject_id
        confirmed_subject_name = (emp_name or evidence_subject_name) if confirmed_subject_id else None
        if ranking_candidates:
            routed.confirmed_context.last_subject_employee_id = None
            routed.confirmed_context.last_subject_employee_name = None
            routed.confirmed_context.candidate_employees = ranking_candidates
        else:
            routed.confirmed_context.last_subject_employee_id = confirmed_subject_id
            routed.confirmed_context.last_subject_employee_name = confirmed_subject_name
            routed.confirmed_context.candidate_employees = []
        routed.confirmed_context.intent = routed.plan.intent
        routed.confirmed_context.metric_id = canonical_metric_id or f"{team.lower()}:{kpi_key}"
        routed.confirmed_context.periods = [_period_id(curr_period) or f"{year_int:04d}-{MONTHS[month_str]:02d}"]
        routed.confirmed_context.team = requested_team or (None if scope_changed else team)
        routed.confirmed_context.function = requested_function or routed.confirmed_context.function
        routed.confirmed_context.region = current_region
        routed.confirmed_context.branch = branch

        resolved_session_state = req.session_state.model_copy(
            update={
                "employee_id": None if ranking_candidates else confirmed_subject_id,
                "team": requested_team or (None if scope_changed else team),
                "function": requested_function or req.session_state.function,
                "position": emp_pos if not scope_changed else routed.plan.position,
                "branch": branch,
                "region": current_region,
                "performance_level": routed.plan.performance_level or (None if scope_changed else req.session_state.performance_level),
                "month": month_str,
                "year": year_int,
                "last_confirmed_query": routed.confirmed_context,
            }
        )

        scope_banner, _ = self._resolve_scope_banner_and_function(
            session_state=resolved_session_state,
            typed_evidence=tool_result.typed_evidence,
            tool_digests=all_tool_digests,
        )

        t_trace_start = time.perf_counter()
        pre_trace_ms = int((t_trace_start - t0) * 1000)
        known_emp_names = [c.employee_name for c in employee_candidates if c.employee_name]
        if emp_name and emp_name not in known_emp_names:
            known_emp_names.append(emp_name)
        trace_id = TrainingTraceLogger(self.db).record_turn(
            user_id=str(self.scope.get("user_id") or ""),
            role=role,
            prompt=req.prompt,
            session_state=resolved_session_state,
            tool_calls=[tc.model_dump() for tc in tool_records],
            tool_digest={"digests": all_tool_digests},
            structured_response={
                "headline": final_headline,
                "narrative_bullets": final_bullets,
                "citations": [c.model_dump() for c in tool_result.citations],
                "typed_evidence": [ev.model_dump() for ev in tool_result.typed_evidence],
                "structured_query": routed.plan.model_dump(),
                "resolved_session_state": resolved_session_state.model_dump(),
                "provider_usage": provider_usage.model_dump(),
                "answer_source": final_answer_source,
                "prompt_version": MODEL_LED_SYNTHESIS_PROMPT_VERSION,
            },
            provider_name=final_provider,
            model_name=final_model,
            latency_ms=pre_trace_ms,
            non_empty_evidence=tool_result.records_evaluated > 0,
            guardrail_triggered=bool(tool_result.guardrail_triggered),
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            known_employee_names=known_emp_names,
        )
        trace_ms = round((time.perf_counter() - t_trace_start) * 1000.0, 2)
        tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        primary_link = tool_result.deep_links[0] if tool_result.deep_links else None

        model_led_tiles = build_response_summary_tiles(
            merged=tool_result.digest if isinstance(tool_result.digest, dict) else {},
            visual_cards=tool_result.visual_cards,
            typed_evidence=tool_result.typed_evidence,
        )
        resp_payload = AiChatResponsePayload(
            trace_id=trace_id,
            conversation_id=active_conversation_id,
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            context_version=active_context_version,
            outcome="answer",
            answer_detail=effective_detail,  # type: ignore[arg-type]
            headline=final_headline,
            narrative_bullets=final_bullets,
            summary_tiles=model_led_tiles,
            visual_cards=tool_result.visual_cards,
            citations=tool_result.citations,
            deep_links=tool_result.deep_links,
            primary_source_link=primary_link,
            suggested_followups=[],
            resolved_session_state=resolved_session_state,
            scope_banner=scope_banner,
            clarification=None,
            structured_query=routed.plan,
            validated_plan_v2=validated_plan_v2,
            evidence_envelope_v2=[],
            typed_evidence=tool_result.typed_evidence,
            domain_guardrail_notes=[],
            tool_calls=tool_records,
            provider_used=final_provider,
            model_used=final_model,
            answer_source=final_answer_source,
            latency_ms=max(0, int(round(tot_ms))),
            timings=AiTurnTimingBreakdown(
                resolution_ms=round((time.perf_counter() - t_res_start) * 1000.0, 2),
                provider_ms=total_provider_ms,
                database_ms=t_tool_ms,
                trace_ms=trace_ms,
                total_ms=tot_ms,
            ),
            provider_usage=provider_usage,
        )

        if conv_service and active_conversation_id and claimed_turn:
            payload_for_store = resp_payload.model_dump()
            if claimed_context_version is not None:
                payload_for_store["context_version"] = claimed_context_version + 1
            new_ver = conv_service.complete_turn(
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id),
                expected_context_version=claimed_context_version,
                claim_token=claimed_token,
                scope=self.scope,
                outcome="answer",
                turn_kind="analytical",
                route_used="model_led_pilot",
                validated_plan=validated_plan_v2.model_dump(),
                evidence_envelope=[],
                response_payload=payload_for_store,
                session_state=resolved_session_state,
                confirmed_context=routed.confirmed_context,
                provider_calls=total_provider_calls,
                total_ms=tot_ms,
            )
            resp_payload.context_version = new_ver

        return resp_payload

    def run_chat_turn(self, req: AiChatRequest) -> AiChatResponsePayload:
        claim_state: dict[str, Any] = {}
        try:
            return self._execute_chat_turn(req, _claim_state=claim_state)
        except (ProviderUnavailableError, AiProviderUnavailableError) as exc:
            conv_service = claim_state.get("conv_service")
            claimed_turn = claim_state.get("claimed_turn")
            if conv_service is not None and claimed_turn is not None:
                try:
                    conv_service.fail_turn(
                        conversation_id=claim_state.get("active_conversation_id"),
                        turn_id=str(claimed_turn.id),
                        claim_token=claim_state.get("claimed_token"),
                        prompt=req.prompt,
                        error_message=str(exc) or "AI provider unavailable",
                    )
                except Exception:
                    pass
            raise

    def _execute_chat_turn(
        self,
        req: AiChatRequest,
        _claim_state: dict[str, Any] | None = None,
    ) -> AiChatResponsePayload:
        t0 = time.perf_counter()
        cfg = get_ai_runtime_config()
        role = str(self.scope.get("role") or "Manager")
        requested_detail = req.answer_detail or "auto"
        lower_prompt = (req.prompt or "").casefold()

        conv_service = AiConversationService(self.db, self.scope) if cfg.conversation_state_enabled else None
        if conv_service is not None:
            self.scope = conv_service.validate_live_account_and_scope(self.scope)
        live_auth_service = conv_service or AiConversationService(self.db, self.scope)
        self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
        role = str(self.scope.get("role") or "Manager")
        from services.ai.user_rules_spec import build_user_rules_spec
        self.user_rules_spec = build_user_rules_spec(self.scope)
        self.scope["user_rules_spec"] = self.user_rules_spec
        self.scope["user_rules_spec_text"] = self.user_rules_spec.get("summary_text", "")
        page_ctx_ok, page_restr_h, page_restr_b = validate_page_context_scope(req, self.scope, live_auth_service)
        req, selected_metric_display = apply_page_context_to_request(req)
        prompt_region = _prompt_region_hint(req.prompt)
        if prompt_region:
            req.session_state = req.session_state.model_copy(update={"region": prompt_region})
        if req.session_state.last_confirmed_query is not None:
            lcq = req.session_state.last_confirmed_query
            if not live_auth_service._is_function_authorized(lcq.function, self.scope):
                lcq.function = None
            if (lcq.team or lcq.performance_level) and not live_auth_service._is_team_and_level_authorized(
                lcq.team, lcq.performance_level, self.scope, region=lcq.region
            ):
                if lcq.team and not live_auth_service._is_team_and_level_authorized(
                    lcq.team, "Employee", self.scope, region=lcq.region
                ):
                    lcq.team = None
                    lcq.position = None
                    lcq.metric_id = None
                lcq.performance_level = None
            if lcq.branch and not live_auth_service._is_branch_authorized(lcq.branch, self.scope):
                lcq.branch = None
            if lcq.branches:
                lcq.branches = [b for b in lcq.branches if live_auth_service._is_branch_authorized(b, self.scope)]
            if (lcq.last_subject_employee_id or lcq.last_subject_employee_name) and not live_auth_service._is_employee_authorized_for_scope(
                lcq.last_subject_employee_id, lcq.last_subject_employee_name, self.scope
            ):
                lcq.last_subject_employee_id = None
                lcq.last_subject_employee_name = None
                lcq.single_person = False
                if lcq.last_operation_kind in ("person_best_period", "person_worst_period", "new_joiner_check", "person_tenure_check"):
                    lcq.last_operation_kind = None
        claimed_turn = None
        claimed_token: str | None = None
        claimed_context_version: int | None = None
        active_conversation_id: str | None = req.conversation_id
        active_context_version: int = int(req.context_version or 0)
        if conv_service and (conv_service.is_schema_ready() or req.conversation_id):
            conv_ctx = conv_service.get_context(
                conversation_id=req.conversation_id,
                scope=self.scope,
                initial_state=req.session_state,
                origin=req.origin or "workspace",
            )
            active_conversation_id = conv_ctx.conversation_id
            claimed_context_version = int(conv_ctx.context_version)
            if req.session_state.last_confirmed_query is None and conv_ctx.confirmed_context is not None:
                req.session_state.last_confirmed_query = conv_ctx.confirmed_context
            elif req.session_state.last_confirmed_query is not None:
                client_context = req.session_state.last_confirmed_query
                saved_context = conv_ctx.confirmed_context
                client_context.candidate_employees = (
                    saved_context.candidate_employees
                    if client_context.intent and all(
                        getattr(client_context, field) == getattr(saved_context, field)
                        for field in ("function", "team", "position", "region", "branch", "performance_level")
                    )
                    else []
                )
            release_read_transaction(self.db)
            bounded_intent_context = _build_bounded_intent_context(req.session_state)
            capability_mode, cap_source, cap_provider_ms = detect_contextual_capability(
                req,
                intent_context=bounded_intent_context,
                scope=self.scope,
            )
            is_gate_non_perf = capability_mode in (
                "greeting",
                "capabilities_help",
                "page_help",
                "navigation",
                "clarification",
                "off_topic",
                "explain_previous",
            )
            claimed_turn, replayed_payload = conv_service.claim_or_replay_turn(
                conversation_id=active_conversation_id,
                scope=self.scope,
                prompt=req.prompt,
                client_request_id=req.client_request_id,
                expected_context_version=req.context_version,
                clarification_choice_id=req.clarification_choice_id,
                answer_detail=req.answer_detail,
                session_state=req.session_state,
                variation_seed=req.variation_seed,
                origin=req.origin or "workspace",
                skip_record_lookup=is_gate_non_perf,
            )
            if replayed_payload is not None:
                return AiChatResponsePayload.model_validate(replayed_payload)
            claimed_token = str(claimed_turn.claim_token)
            active_context_version = claimed_context_version
            if _claim_state is not None:
                _claim_state["conv_service"] = conv_service
                _claim_state["claimed_turn"] = claimed_turn
                _claim_state["claimed_token"] = claimed_token
                _claim_state["active_conversation_id"] = active_conversation_id
        else:
            bounded_intent_context = _build_bounded_intent_context(req.session_state)
            capability_mode, cap_source, cap_provider_ms = detect_contextual_capability(
                req,
                intent_context=bounded_intent_context,
                scope=self.scope,
            )

        social_kind = is_greeting_or_thanks_prompt(req.prompt)
        if social_kind is not None or capability_mode == "greeting":
            is_greeting = social_kind != "thanks"
            social_variant = resolve_variation_index(req.prompt, req.history, req.variation_seed)
            if is_greeting:
                social_headline = (
                    "Hi! What would you like to know about performance?",
                    "Hello! Which team, KPI, or branch metric would you like to review?",
                    "Hi there! Ask about team trends, KPI targets, branch comparisons, or corrective actions.",
                )[social_variant]
            else:
                social_headline = (
                    "You're welcome! Let me know if you need anything else.",
                    "You're very welcome! Feel free to ask if you'd like to drill into another KPI or team.",
                    "You're welcome! Happy to help whenever you want to review another metric or branch.",
                )[social_variant]
            social_scope_banner, social_fn = self._resolve_scope_banner_and_function(
                session_state=req.session_state,
            )
            social_session_state = (
                req.session_state.model_copy(update={"function": social_fn})
                if social_fn != req.session_state.function
                else req.session_state
            )
            social_plan_v2 = ValidatedQueryPlanV2(
                turn_kind="social",
                scope=QueryScopeV2(
                    function=social_fn,
                    team=social_session_state.team,
                ),
                operations=[
                    QueryOperationV2(
                        operation_id="op_1",
                        kind="greeting" if is_greeting else "thanks",
                    )
                ],
                resolution_source="local_model_router" if cap_source == "local_model_router" else "local_rules",
            )
            social_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="answer",
                answer_detail="brief",
                headline=social_headline,
                suggested_followups=[],
                resolved_session_state=social_session_state,
                scope_banner=social_scope_banner,
                validated_plan_v2=social_plan_v2,
                evidence_envelope_v2=[],
                tool_calls=[],
                capability_mode="greeting",
                provider_used=active_provider_name() if cap_source == "local_model_router" else "deterministic",
                model_used=configured_model_name() if cap_source == "local_model_router" else "pms-deterministic-v1",
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used=cap_source if cap_source == "local_model_router" else "local_rules",
                    provider_calls=1 if cap_source == "local_model_router" else 0,
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = social_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="answer",
                    turn_kind="social",
                    route_used=cap_source if cap_source == "local_model_router" else "local_rules",
                    validated_plan=social_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=social_session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=1 if cap_source == "local_model_router" else 0,
                    total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
                social_resp.context_version = new_ver
            return social_resp
        eff_ctx_label_initial = build_effective_context_label(
            page_context=req.page_context,
            session_state=req.session_state,
            selected_metric_display=selected_metric_display,
        )
        initial_scope_banner, initial_fn = self._resolve_scope_banner_and_function(
            session_state=req.session_state,
        )
        if not page_ctx_ok:
            restr_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="restricted_access",
                answer_detail="brief",
                headline=page_restr_h or "Access restricted for this page scope.",
                narrative_bullets=[page_restr_b] if page_restr_b else [],
                suggested_followups=["Show performance summary for my authorized scope"],
                resolved_session_state=req.session_state,
                scope_banner=initial_scope_banner,
                effective_context_label=eff_ctx_label_initial,
                capability_mode="performance_query",
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = restr_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="restricted_access",
                    turn_kind="clarification",
                    route_used="local_rules",
                    validated_plan={},
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=req.session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=0,
                    total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
                restr_resp.context_version = new_ver
            return restr_resp

        if capability_mode in ("capabilities_help", "clarification", "off_topic", "explain_previous"):
            explicit_help_function = "RCM" if re.search(r"\brcm\b", lower_prompt) else None
            gate_function = explicit_help_function or initial_fn
            gate_updates: dict[str, Any] = {}
            if gate_function != req.session_state.function:
                gate_updates["function"] = gate_function
            if explicit_help_function:
                gate_updates.update(
                    team=None,
                    position=None,
                    branch=None,
                    employee_id=None,
                )
            gate_session_state = req.session_state.model_copy(update=gate_updates) if gate_updates else req.session_state
            gate_scope_banner, _ = self._resolve_scope_banner_and_function(session_state=gate_session_state)
            g_detail_bullets: list[str] = []
            explain_meta: dict[str, Any] = {}
            if capability_mode == "capabilities_help":
                g_head, g_bullets, g_followups = build_capabilities_help_payload(
                    scope=self.scope,
                    session_state=gate_session_state,
                )
                g_outcome = "answer"
                g_turn_kind = "social"
                g_clar = None
            elif capability_mode == "clarification":
                g_head, g_bullets, g_followups = build_clarification_gate_payload(
                    scope=self.scope,
                    session_state=gate_session_state,
                )
                g_outcome = "clarification"
                g_turn_kind = "clarification"
                g_clar = AiClarificationPrompt(
                    code="AMBIGUOUS_TEAM_SCOPE",
                    question=g_head,
                    choices=[],
                )
            elif capability_mode == "explain_previous":
                previous_summary = (
                    conv_service.get_last_completed_turn_summary(active_conversation_id, scope=self.scope)
                    if conv_service is not None and active_conversation_id
                    else None
                )
                (
                    g_head,
                    g_bullets,
                    g_detail_bullets,
                    g_followups,
                    g_outcome,
                    explain_meta,
                ) = build_explain_previous_payload(
                    last_turn_summary=previous_summary,
                    scope=self.scope,
                    session_state=gate_session_state,
                    prompt=req.prompt,
                    provider_override=req.provider_override or "auto",
                )
                g_turn_kind = "social" if g_outcome == "answer" else "clarification"
                g_clar = (
                    AiClarificationPrompt(code="AMBIGUOUS_KPI_SCOPE", question=g_head, choices=[])
                    if g_outcome == "clarification"
                    else None
                )
            else:
                g_head, g_bullets, g_followups = build_off_topic_gate_payload(
                    scope=self.scope,
                    session_state=gate_session_state,
                )
                g_outcome = "unsupported_request"
                g_turn_kind = "unsupported"
                g_clar = None

            gate_plan_v2 = ValidatedQueryPlanV2(
                turn_kind=g_turn_kind,  # type: ignore[arg-type]
                scope=QueryScopeV2(
                    function=gate_session_state.function,
                    team=gate_session_state.team,
                ),
                operations=[],
                clarification_code="AMBIGUOUS_TEAM_SCOPE" if capability_mode == "clarification" else "NONE",
                resolution_source="local_model_router" if cap_source == "local_model_router" else "local_rules",
            )
            trace_id_gate = TrainingTraceLogger(self.db).record_turn(
                user_id=str(self.scope.get("user_id") or ""),
                role=role,
                prompt=req.prompt,
                session_state=gate_session_state,
                tool_calls=[],
                tool_digest={"capability_mode": capability_mode, "outcome": g_outcome},
                structured_response={"headline": g_head, "narrative_bullets": g_bullets, "outcome": g_outcome},
                provider_name=active_provider_name() if cap_source == "local_model_router" else "local",
                model_name=configured_model_name() if cap_source == "local_model_router" else "intent-gate-v1",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                non_empty_evidence=False,
                guardrail_triggered=capability_mode == "off_topic",
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                skip_record_lookup=True,
            )
            tot_gate_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            gate_resp = AiChatResponsePayload(
                trace_id=trace_id_gate,
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome=g_outcome,  # type: ignore[arg-type]
                answer_detail="brief",
                headline=g_head,
                narrative_bullets=g_bullets,
                suggested_followups=g_followups[:3],
                resolved_session_state=gate_session_state,
                scope_banner=gate_scope_banner,
                effective_context_label=eff_ctx_label_initial,
                clarification=g_clar,
                detail_bullets=g_detail_bullets,
                validated_plan_v2=gate_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                tool_calls=[],
                capability_mode=capability_mode,
                provider_used=(
                    str(explain_meta.get("provider_used") or "deterministic")
                    if capability_mode == "explain_previous"
                    else (active_provider_name() if cap_source == "local_model_router" else "deterministic")
                ),
                model_used=(
                    str(explain_meta.get("model_used") or "intent-gate-v1")
                    if capability_mode == "explain_previous"
                    else (configured_model_name() if cap_source == "local_model_router" else "intent-gate-v1")
                ),
                latency_ms=max(0, int(round(tot_gate_ms))),
                timings=AiTurnTimingBreakdown(
                    resolution_ms=round(cap_provider_ms, 2),
                    provider_ms=round(cap_provider_ms, 2),
                    total_ms=tot_gate_ms,
                ),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used=cap_source,  # type: ignore[arg-type]
                    provider_calls=(
                        int(explain_meta.get("provider_calls") or 0)
                        if capability_mode == "explain_previous"
                        else (1 if cap_source == "local_model_router" else 0)
                    ),
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = gate_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome=g_outcome,
                    turn_kind=g_turn_kind,
                    route_used=cap_source,
                    validated_plan=gate_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=gate_session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=1 if cap_source == "local_model_router" else 0,
                    total_ms=tot_gate_ms,
                )
                gate_resp.context_version = new_ver
            return gate_resp

        if capability_mode in ("page_help", "navigation"):
            if capability_mode == "page_help":
                h_head, h_bullets, help_sec, nav_targets, h_followups, fb_warn = build_page_help_payload(
                    req=req,
                    scope=self.scope,
                    session_state=req.session_state,
                    selected_metric_display=selected_metric_display,
                )
            else:
                h_head, h_bullets, nav_targets, h_followups = build_navigation_payload(
                    req=req,
                    scope=self.scope,
                    session_state=req.session_state,
                )
                help_sec = None
                fb_warn = (
                    "This page is currently displaying sample/fallback preview data."
                    if (req.page_context and req.page_context.is_fallback_data)
                    else None
                )
            nav_links = [
                DeepLinkCta(
                    label=t.label,
                    route=t.route,
                    icon_key="insights" if t.icon_key == "presentation" else t.icon_key,  # type: ignore[arg-type]
                )
                for t in nav_targets[:3]
            ]
            trace_id_help = TrainingTraceLogger(self.db).record_turn(
                user_id=str(self.scope.get("user_id") or ""),
                role=role,
                prompt=req.prompt,
                session_state=req.session_state,
                tool_calls=[],
                tool_digest={"capability_mode": capability_mode, "outcome": "answer"},
                structured_response={"headline": h_head, "narrative_bullets": h_bullets, "outcome": "answer"},
                provider_name=active_provider_name() if cap_source == "local_model_router" else "local",
                model_name=configured_model_name() if cap_source == "local_model_router" else "contextual-catalog-v1",
                latency_ms=int((time.perf_counter() - t0) * 1000),
                non_empty_evidence=True,
                guardrail_triggered=False,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                skip_record_lookup=True,
            )
            tot_help_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            help_resp = AiChatResponsePayload(
                trace_id=trace_id_help,
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="answer",
                answer_detail="brief",
                headline=h_head,
                narrative_bullets=h_bullets,
                deep_links=nav_links,
                primary_source_link=nav_links[0] if nav_links else None,
                suggested_followups=h_followups,
                resolved_session_state=req.session_state,
                scope_banner=initial_scope_banner,
                effective_context_label=eff_ctx_label_initial,
                capability_mode=capability_mode,
                page_help=help_sec,
                navigation_targets=nav_targets,
                basis_warning=fb_warn,
                provider_used=active_provider_name() if cap_source == "local_model_router" else "deterministic",
                model_used=configured_model_name() if cap_source == "local_model_router" else "contextual-catalog-v1",
                latency_ms=max(0, int(round(tot_help_ms))),
                timings=AiTurnTimingBreakdown(
                    resolution_ms=round(cap_provider_ms, 2),
                    provider_ms=round(cap_provider_ms, 2),
                    total_ms=tot_help_ms,
                ),
                provider_usage=AiProviderUsageMetrics(
                    router_mode=cfg.router_mode,
                    route_used=cap_source,
                    provider_calls=1 if cap_source == "local_model_router" else 0,
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = help_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="answer",
                    turn_kind="analytical",
                    route_used=cap_source,
                    validated_plan={"capability_mode": capability_mode},
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=req.session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=1 if cap_source == "local_model_router" else 0,
                    total_ms=tot_help_ms,
                )
                help_resp.context_version = new_ver
            return help_resp

        if req.page_context and req.page_context.is_fallback_data:
            fb_msg = (
                "This view is currently showing sample fallback data rather than verified PMS records, "
                "so I cannot report factual performance metrics or propose a corrective action from it."
            )
            fb_warn = (
                "Page is currently displaying sample/fallback preview data. "
                "Analytical figures and corrective actions require verified backend PMS records."
            )
            fb_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="unavailable_data",
                answer_detail="brief",
                headline=fb_msg,
                narrative_bullets=[
                    "Switch to a published period with verified backend PMS records before running analytical queries or creating corrective actions."
                ],
                suggested_followups=["What does this page show?"],
                resolved_session_state=req.session_state,
                scope_banner=eff_ctx_label_initial,
                effective_context_label=eff_ctx_label_initial,
                capability_mode=capability_mode,
                basis_warning=fb_warn,
                action_proposal=None,
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = fb_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="unavailable_data",
                    turn_kind="clarification",
                    route_used="local_rules",
                    validated_plan={"capability_mode": capability_mode, "is_fallback_data": True},
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=req.session_state,
                    confirmed_context=req.session_state.last_confirmed_query,
                    provider_calls=0,
                    total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
                )
                fb_resp.context_version = new_ver
            return fb_resp

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
            db=self.db,
        ).resolve_and_validate(
            prompt=req.prompt,
            session_state=req.session_state,
            provider_override=req.provider_override,
            clarification_choice_id=req.clarification_choice_id,
            bounded_context=bounded_intent_context,
            history=req.history,
        )
        effective_region = prompt_region or routed.confirmed_context.region or req.session_state.region
        prior_scope_context = req.session_state.last_confirmed_query
        current_scope_values = {
            "function": routed.plan.function or routed.confirmed_context.function,
            "team": routed.plan.team,
            "position": routed.plan.position,
            "branch": routed.plan.branch,
            "region": effective_region,
            "performance_level": routed.plan.performance_level,
        }
        previous_employee_id = req.session_state.employee_id or (
            prior_scope_context.last_subject_employee_id if prior_scope_context else None
        )
        changed_employee = bool(
            routed.plan.employee_id and previous_employee_id
            and routed.plan.employee_id.casefold() != previous_employee_id.casefold()
        )
        resolved_scope_changed = changed_employee or bool(
            prior_scope_context
            and any(
                current_value
                and prior_value
                and str(current_value).casefold() != str(prior_value).casefold()
                for field, current_value in current_scope_values.items()
                for prior_value in [getattr(prior_scope_context, field, None)]
            )
        )
        if effective_region:
            routed.confirmed_context.region = effective_region
        if routed.plan.team:
            routed.confirmed_context.team = routed.plan.team
        signals = extract_prompt_signals(req.prompt, req.session_state)

        # Synchronize signals with validated StructuredQueryPlan (including inherited follow-up context)
        if routed.plan.team or resolved_scope_changed:
            signals.detected_team = routed.plan.team
        signals.detected_branch = routed.plan.branch
        signals.detected_compare_branch = (
            routed.plan.compare_branch if routed.plan.intent == "compare_branches" else None
        )
        signals.detected_branches = (
            list(routed.plan.branches)
            if routed.plan.intent == "compare_branches"
            else ([routed.plan.branch] if routed.plan.branch else [])
        )
        signals.asks_branch_comparison = routed.plan.intent == "compare_branches"
        if routed.plan.performance_level or resolved_scope_changed:
            signals.detected_level = routed.plan.performance_level
        if routed.plan.metric:
            signals.detected_kpi = routed.plan.metric.split(":")[-1]
            if routed.plan.metric.endswith(":bookings_count"):
                signals.asks_booking_count = True
        if routed.plan.employee_id:
            signals.detected_employee_query = routed.plan.employee_id
        elif routed.plan.intent == "ranking":
            signals.detected_employee_query = None
        if routed.plan.intent in ("trend", "compare_periods") or routed.plan.operation_kind_v2 == "trend":
            signals.asks_trend = True
        signals.asks_single_person = bool(routed.plan.single_person)
        if routed.confirmed_context.last_operation_kind in ("employee_worst_period", "person_worst_period"):
            signals.asks_worst_month_history = True
            signals.asks_best_month_history = False
        elif routed.confirmed_context.last_operation_kind in ("employee_best_period", "person_best_period"):
            signals.asks_best_month_history = True
            signals.asks_worst_month_history = False
        else:
            signals.asks_best_month_history = False
            signals.asks_worst_month_history = False
        is_open_ended_extremum_q = bool(
            re.match(
                r"^\s*(?:what\s+(?:was|is|were)|which\s+month|what\s+month|and\s+(?:his|her|their)\s+(?:best|worst|highest|lowest)|what\s+about\s+(?:his|her|their)\s+(?:best|worst|highest|lowest))",
                lower_prompt,
            )
        )
        if is_open_ended_extremum_q:
            signals.asks_specific_month_in_prompt = False
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
        elif routed.plan.requested_parts == ["current_value", "ranking"] or (
            "current_value" in routed.plan.requested_parts and "ranking" in routed.plan.requested_parts
        ):
            signals.primary_intents = ["executive_insights", "agent_spotlight_trend"]
            signals.asks_single_person = True
        elif routed.plan.employee_id or (routed.plan.intent == "ranking" and routed.plan.single_person):
            signals.primary_intents = ["agent_spotlight_trend"]
            signals.asks_single_person = True
        elif routed.plan.intent == "trend":
            signals.primary_intents = ["team_trend_spotlight"]
        else:
            asks_why_root_cause = bool(
                re.search(
                    r"\b(?:why|how\s+come|what\s+caused|what\s+drove|diagnose|dragging|pulling)\b",
                    lower_prompt,
                )
                or (
                    routed.plan.metric
                    and re.search(
                        r"\b(?:down|low|drop|dropped|dropping|below|weak|bad|decline|declined|fell|fall|behind|miss|missed|gap|bottleneck)\b",
                        lower_prompt,
                    )
                )
            )
            if routed.plan.intent in ("actual_vs_target", "score_drivers", "compare_periods", "compare_branches") or (
                routed.plan.intent == "current_value" and routed.plan.team
                and routed.plan.metric and routed.plan.metric != "overall_score"
            ):
                signals.primary_intents = [
                    t for t in signals.primary_intents if t not in ("executive_insights", "executive_summary")
                ]
                if "kpi_diagnosis" not in signals.primary_intents:
                    signals.primary_intents.insert(0, "kpi_diagnosis")
                if (
                    (asks_why_root_cause or routed.plan.intent == "score_drivers")
                    and routed.plan.intent != "compare_branches"
                    and "people_contribution" not in signals.primary_intents
                ):
                    signals.primary_intents.append("people_contribution")
            elif routed.plan.intent == "ranking" and "people_contribution" not in signals.primary_intents and "agent_spotlight_trend" not in signals.primary_intents:
                target_tool = "agent_spotlight_trend" if routed.plan.single_person else "people_contribution"
                signals.primary_intents = [
                    t for t in signals.primary_intents if t not in ("executive_insights", "executive_summary")
                ]
                signals.primary_intents.insert(0, target_tool)
            elif routed.plan.intent == "scorecard_structure" and "management_bsc" not in signals.primary_intents:
                signals.primary_intents = [
                    t for t in signals.primary_intents if t not in ("executive_insights", "executive_summary")
                ]
                signals.primary_intents.insert(0, "management_bsc")
            elif routed.plan.intent == "corrective_actions" and "corrective_actions" not in signals.primary_intents:
                signals.primary_intents = [
                    t for t in signals.primary_intents if t not in ("executive_insights", "executive_summary")
                ]
                signals.primary_intents.insert(0, "corrective_actions")

        resolution_ms = round((time.perf_counter() - t_res_start) * 1000.0, 2)
        validated_plan_v2 = self._build_validated_plan_v2(
            routed,
            turn_kind="analytical" if routed.outcome == "answer" else "clarification",
            prompt=req.prompt,
        )
        known_emp_names = [c.employee_name for c in employee_candidates if c.employee_name]

        # Phase 2 Model-Led Pilot direct conversational response
        if routed.route_used == "model_led_pilot" and routed.plan.model_led_direct_response and not routed.plan.model_led_tool_call:
            tot_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            direct_resp = AiChatResponsePayload(
                trace_id="",
                conversation_id=active_conversation_id,
                turn_id=str(claimed_turn.id) if claimed_turn else None,
                context_version=active_context_version,
                outcome="answer",
                answer_detail=effective_detail,  # type: ignore[arg-type]
                headline=routed.plan.model_led_direct_response,
                narrative_bullets=[],
                visual_cards=[],
                citations=[],
                deep_links=[],
                primary_source_link=None,
                suggested_followups=[],
                resolved_session_state=req.session_state,
                scope_banner="All Authorized Departments",
                clarification=None,
                structured_query=routed.plan,
                validated_plan_v2=validated_plan_v2,
                evidence_envelope_v2=[],
                typed_evidence=[],
                domain_guardrail_notes=[],
                tool_calls=[],
                provider_used=routed.provider_metrics.provider_used or "cloudflare",
                model_used=routed.provider_metrics.model_used or "granite-4.0-h-micro",
                answer_source=(
                    "model_synthesis"
                    if routed.provider_metrics.provider_used in ("cloudflare", "gemini")
                    else "deterministic"
                ),
                latency_ms=max(0, int(round(tot_ms))),
                timings=AiTurnTimingBreakdown(
                    resolution_ms=resolution_ms,
                    provider_ms=routed.provider_metrics.provider_ms,
                    database_ms=0.0,
                    trace_ms=0.0,
                    total_ms=tot_ms,
                ),
                provider_usage=_build_aggregated_usage(
                    router_mode=cfg.router_mode,
                    route_used="model_led_pilot",
                    router_metrics=routed.provider_metrics,
                    fallback_outcome_override="none",
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = direct_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome="answer",
                    turn_kind="conversational",
                    route_used="model_led_pilot",
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=req.session_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=routed.provider_metrics.provider_calls,
                    total_ms=tot_ms,
                )
                direct_resp.context_version = new_ver
            return direct_resp

        # Pre-read validation short-circuit for clarification, restricted_access, unavailable_data, unsupported_request
        if routed.outcome != "answer":
            p_month, p_year = (
                _period_key_to_month_year(routed.plan.periods[-1])
                if routed.plan.periods
                else (req.session_state.month, req.session_state.year)
            )
            resolved_state = SessionFilterContext(
                function=routed.plan.function or routed.confirmed_context.function or req.session_state.function,
                team=routed.plan.team or (None if resolved_scope_changed else req.session_state.team),
                position=routed.plan.position or (None if resolved_scope_changed else req.session_state.position),
                branch=routed.plan.branch or (None if resolved_scope_changed else req.session_state.branch),
                region=effective_region,
                performance_level=routed.plan.performance_level or (None if resolved_scope_changed else req.session_state.performance_level),
                month=p_month or req.session_state.month,
                year=p_year or req.session_state.year,
                employee_id=routed.plan.employee_id,
                last_confirmed_query=routed.confirmed_context,
            )
            scope_banner, short_fn = self._resolve_scope_banner_and_function(
                session_state=resolved_state,
                region=effective_region,
            )
            if short_fn != resolved_state.function:
                resolved_state.function = short_fn

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
                known_employee_names=known_emp_names,
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
            provider_usage = _build_aggregated_usage(
                router_mode=cfg.router_mode,
                route_used=routed.route_used,
                router_metrics=routed.provider_metrics,
            )
            short_resp = AiChatResponsePayload(
                trace_id=trace_id,
                conversation_id=active_conversation_id,
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
                suggested_followups=list(routed.suggested_followups[:1]),
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
                answer_source="deterministic",
                latency_ms=max(0, int(round(total_ms))),
                timings=timings,
                provider_usage=provider_usage,
                basis_warning=None,
                cache_hit=False,
                capability_mode=_resolved_capability_mode(
                    capability_mode,
                    outcome=routed.outcome,
                    plan_intent=routed.plan.intent,
                    prompt=req.prompt,
                ),
            )
            if conv_service and active_conversation_id and claimed_turn:
                payload_for_store = short_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome=routed.outcome,
                    turn_kind="clarification",
                    route_used=routed.route_used,
                    validated_plan=validated_plan_v2.model_dump(),
                    evidence_envelope=[],
                    response_payload=payload_for_store,
                    session_state=resolved_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=routed.provider_metrics.provider_calls,
                    total_ms=total_ms,
                )
                short_resp.context_version = new_ver
            return short_resp

        t_db_start = time.perf_counter()
        self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
        tool_session_state = req.session_state.model_copy(
            update={
                "function": routed.plan.function or routed.confirmed_context.function or (
                    None if resolved_scope_changed else req.session_state.function
                ),
                "team": routed.plan.team or (None if resolved_scope_changed else req.session_state.team),
                "position": routed.plan.position or (None if resolved_scope_changed else req.session_state.position),
                "branch": routed.plan.branch or (None if resolved_scope_changed else req.session_state.branch),
                "region": effective_region,
                "performance_level": routed.plan.performance_level or (
                    None if resolved_scope_changed else req.session_state.performance_level
                ),
                "employee_id": routed.plan.employee_id,
            }
        )
        ctx = ToolExecutionContext(db=self.db, scope=self.scope, session_state=tool_session_state)
        registry = DeterministicToolRegistry(ctx)

        # Phase 2 Model-Led Pilot execution path
        if routed.route_used == "model_led_pilot" and routed.plan.model_led_tool_call:
            return self._handle_model_led_turn(
                req=req,
                routed=routed,
                registry=registry,
                employee_candidates=employee_candidates,
                published_periods=published_periods,
                live_auth_service=live_auth_service,
                active_conversation_id=active_conversation_id,
                claimed_turn=claimed_turn,
                claimed_token=claimed_token,
                claimed_context_version=claimed_context_version,
                active_context_version=active_context_version,
                conv_service=conv_service,
                t0=t0,
                role=role,
                effective_detail=effective_detail,
                t_res_start=t_res_start,
                validated_plan_v2=validated_plan_v2,
            )

        tool_results: list[ToolExecutionResult] = []
        guardrail_notes: list[str] = []
        booking_team = routed.plan.team
        booking_metric = routed.plan.metric
        period_operations = [op.kind for op in validated_plan_v2.operations]
        bookings_trend = bool(
            booking_team and booking_metric and booking_metric.endswith(":bookings_count")
            and not validated_plan_v2.scope.employee_id
            and not signals.asks_branch_comparison
            and len(validated_plan_v2.scope.periods) >= 2
            and any(kind in ("trend", "compare_periods") for kind in period_operations)
        )

        if signals.asks_revenue_in_call_center:
            guardrail_notes.append(
                "Call Center (Inbound & Outbound) measures operational patient volume (Bookings, Attended Visits, and Handled Calls) rather than financial revenue. Financial revenue is tracked under Marketing and RCM."
            )

        # Shared All-region scorecard choice (PR #84): the router already
        # authorised the choice; the scorecard must be computed by the
        # exact-team + region='All' tool, never by the domain rollup tools
        # (team=RCM would otherwise expand to every RCM sub-team).
        shared_choice_team = {"choice-shared-rcm": "RCM", "choice-shared-finance": "Finance"}.get(
            str(req.clarification_choice_id or "")
        )

        cache_sig = {
            "intents": list(signals.primary_intents[:2]),
            "region": effective_region,
            "team": signals.detected_team or req.session_state.team,
            "function": routed.plan.function or req.session_state.function,
            "position": routed.plan.position,
            "branch": signals.detected_branch or req.session_state.branch,
            "compare_branch": signals.detected_compare_branch,
            "branches": list(signals.detected_branches),
            "asks_branch_comparison": signals.asks_branch_comparison,
            "level": signals.detected_level or req.session_state.performance_level,
            "kpi": routed.plan.metric or signals.detected_kpi,
            "month": signals.detected_month or req.session_state.month,
            "year": signals.detected_year or req.session_state.year,
            "periods": list(routed.plan.periods),
            "employee_query": signals.detected_employee_query,
            "worst_agent": signals.asks_worst_agent,
            "single_person": signals.asks_single_person,
            "asks_best_month_history": signals.asks_best_month_history,
            "asks_worst_month_history": signals.asks_worst_month_history,
            "asks_specific_month_in_prompt": signals.asks_specific_month_in_prompt,
            "asks_revenue_in_call_center": signals.asks_revenue_in_call_center,
            # The shared scorecard and the plain team scorecard share every
            # other signature field; without this they would share a cache
            # entry and return each other's numbers.
            "shared_region_team": shared_choice_team,
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
        elif shared_choice_team:
            tool_results.append(
                registry.execute_shared_region_scorecard(
                    team=shared_choice_team,
                    month=signals.detected_month or req.session_state.month,
                    year=signals.detected_year or req.session_state.year,
                )
            )
        elif bookings_trend and booking_team:
            periods = validated_plan_v2.scope.periods
            tool_results.append(registry.execute_team_metric_trend(
                team=booking_team, branch=routed.plan.branch,
                performance_level=routed.plan.performance_level, kpi=booking_metric,
                period=periods[-1], periods=periods,
            ))
            if "ranking" in period_operations:
                rank_month, rank_year = _period_key_to_month_year(periods[-1])
                tool_results.append(registry.execute_agent_spotlight_and_trend(
                    team=booking_team, branch=routed.plan.branch,
                    performance_level=routed.plan.performance_level, kpi=booking_metric,
                    ranking_direction=routed.plan.ranking_direction,
                    single_person=True, month=rank_month, year=rank_year, months_window=1,
                ))
        else:
            for intent in signals.primary_intents[:2]:
                if intent == "agent_spotlight_trend":
                    spotlight_res = registry.execute_agent_spotlight_and_trend(
                        team=signals.detected_team,
                        position=routed.plan.position,
                        function=routed.plan.function,
                        branch=signals.detected_branch,
                        month=signals.detected_month,
                        year=signals.detected_year,
                        kpi=routed.plan.metric or signals.detected_kpi,
                        employee_query=signals.detected_employee_query,
                        ranking_direction="worst" if signals.asks_worst_agent else "best",
                        single_person=signals.asks_single_person,
                    )
                    if routed.plan.intent == "score_drivers" and routed.plan.employee_id:
                        spotlight_res.tool_name = "get_kpi_diagnosis"
                    tool_results.append(spotlight_res)
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
                    threshold_spec_det = parse_score_threshold_query(req.prompt)
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
                            direct_rank_fallback=threshold_spec_det is not None,
                            score_threshold=threshold_spec_det[1] if threshold_spec_det is not None else None,
                            threshold_operator=threshold_spec_det[0] if threshold_spec_det is not None else None,
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
                            kpi=routed.plan.metric or signals.detected_kpi,
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
        if len(routed.plan.periods) >= 2:
            req_period_labels = [format_period_label(p) for p in routed.plan.periods if format_period_label(p)]
            for td in tool_digests:
                if isinstance(td, dict):
                    for sp_key in ("spotlight", "agent_spotlight"):
                        sp_obj = td.get(sp_key)
                        if isinstance(sp_obj, dict):
                            sp_obj["requested_period_labels"] = req_period_labels
        adapter = DeterministicLocalProviderAdapter()
        booking_comparison_facts = None
        synthesis = adapter.synthesize(
            prompt=req.prompt,
            signals=signals,
            tool_digests=tool_digests,
            guardrail_notes=guardrail_notes,
            history=req.history,
            variation_seed=req.variation_seed,
            session_state=req.session_state,
        )
        if len(routed.plan.requested_parts) >= 2 and len(tool_digests) >= 2:
            part_headlines: list[str] = []
            for p_kind, td in zip(routed.plan.requested_parts[:2], tool_digests[:2]):
                p_sig = extract_prompt_signals(req.prompt, req.session_state)
                p_sig.detected_team = signals.detected_team
                p_sig.detected_branch = signals.detected_branch
                p_sig.detected_kpi = signals.detected_kpi
                p_sig.detected_month = signals.detected_month
                p_sig.detected_year = signals.detected_year
                p_sig.asks_worst_agent = signals.asks_worst_agent
                if p_kind == "current_value":
                    p_sig.asks_agent_ranking = False
                    p_sig.asks_single_person = False
                    p_sig.asks_team_trend = False
                    p_sig.asks_trend = False
                elif p_kind == "trend":
                    p_sig.asks_team_trend = True
                    p_sig.asks_trend = True
                    p_sig.asks_agent_ranking = False
                    p_sig.asks_single_person = False
                elif p_kind == "ranking":
                    p_sig.asks_agent_ranking = True
                    p_sig.asks_single_person = True
                    p_sig.asks_team_trend = False
                p_syn = adapter.synthesize(
                    prompt=req.prompt,
                    signals=p_sig,
                    tool_digests=[td],
                    guardrail_notes=[],
                    history=req.history,
                    variation_seed=req.variation_seed,
                    session_state=req.session_state,
                )
                if p_syn.headline and p_syn.headline not in part_headlines:
                    part_headlines.append(p_syn.headline)
            if len(part_headlines) >= 2:
                synthesis.headline = f"{part_headlines[0]} {part_headlines[1]}"
        # Local model access is optional and receives only authorized scoped
        # evidence. Recheck current permissions before passing data to it.
        accepted_local = False
        if routed.plan.intent in ("compare_branches", "current_value") and local_synthesis_enabled():
            self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
            if (
                live_auth_service.is_plan_and_context_authorized(
                    scope=self.scope,
                    team=routed.plan.team,
                    function=routed.plan.function,
                    branch=routed.plan.branch,
                    branches=list(routed.plan.branches or []),
                    performance_level=routed.plan.performance_level,
                    region=effective_region,
                )
                and live_auth_service.is_returned_evidence_authorized(
                    scope=self.scope,
                    typed_evidence=typed_evidence,
                    tool_digests=tool_digests,
                    fallback_branch=routed.plan.branch,
                    fallback_level=routed.plan.performance_level,
                )
            ):
                release_read_transaction(self.db)
                local_synthesis = (
                    synthesize_branch_bookings(
                        req.prompt,
                        tool_digests,
                        user_id=str(self.scope.get("user_id") or "") or None,
                        user_role=role or None,
                    )
                    if routed.plan.intent == "compare_branches"
                    else synthesize_overall_score(
                        req.prompt,
                        tool_digests,
                        user_id=str(self.scope.get("user_id") or "") or None,
                        user_role=role or None,
                    )
                )
                self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
                if local_synthesis is not None:
                    accepted_local = True
                    booking_facts_cand = (
                        extract_branch_booking_facts(req.prompt, tool_digests)
                        if routed.plan.intent == "compare_branches"
                        else None
                    )
                    score_facts_cand = (
                        extract_overall_score_facts(req.prompt, tool_digests)
                        if booking_facts_cand is None
                        else None
                    )
                    if local_synthesis.provider_used in ("cloudflare", "gemini"):
                        if booking_facts_cand is not None:
                            claim_ledger = [
                                ClaimFact(
                                    fact_id=f"F{idx}",
                                    part="compare_branches",
                                    subject=name,
                                    team=booking_facts_cand.scope,
                                    branch=name,
                                    period=booking_facts_cand.period,
                                    value=count,
                                    display=str(count),
                                    unit="count",
                                    direction="higher_better",
                                )
                                for idx, (name, count) in enumerate(booking_facts_cand.counts, start=1)
                            ]
                        elif score_facts_cand is not None:
                            claim_ledger = [
                                ClaimFact(
                                    fact_id="F1",
                                    part="score",
                                    subject=score_facts_cand.scope,
                                    branch=(
                                        None
                                        if score_facts_cand.branch.casefold() in ("all branches", "all")
                                        else score_facts_cand.branch
                                    ),
                                    period=score_facts_cand.period,
                                    value=score_facts_cand.score,
                                    display=f"{score_facts_cand.score:.1f}%",
                                    unit="%",
                                    direction="higher_better",
                                )
                            ]
                        else:
                            claim_ledger = build_claim_ledger(typed_evidence=typed_evidence)
                        claim_check = validate_claims(
                            headline=local_synthesis.headline,
                            bullets=local_synthesis.narrative_bullets,
                            ledger=claim_ledger,
                        )
                        if not claim_check.valid:
                            accepted_local = False
                            synthesis.metrics.fallback_outcome = "invalid_or_unverified_response"
                    if accepted_local:
                        synthesis = local_synthesis
                        final_cards = []
                        if booking_facts_cand is not None:
                            booking_comparison_facts = booking_facts_cand
                            citations = [
                                SourceCitationPill(label=f"Period · {booking_comparison_facts.period}", category="period"),
                                SourceCitationPill(label=f"Scope · {booking_comparison_facts.scope}", category="scope"),
                                SourceCitationPill(label="Branches · " + ", ".join(name for name, _ in booking_comparison_facts.counts), category="branch"),
                            ]
                            # The answer compares booking counts within one period,
                            # not month-over-month score changes.
                            basis_warning = None
                        elif score_facts_cand is not None:
                            citations = [
                                SourceCitationPill(label=f"Period · {score_facts_cand.period}", category="period"),
                                SourceCitationPill(label=f"Scope · {score_facts_cand.scope}", category="scope"),
                                SourceCitationPill(label=f"Branch · {score_facts_cand.branch}", category="branch"),
                            ]
                            basis_warning = None
        if (
            not accepted_local
            and (req.provider_override or "auto") == "auto"
            and capability_mode != "proposal"
            and local_synthesis_enabled()
            and ((req.variation_seed or 0) >= 1 or len(req.history) >= 2)
            and get_ai_runtime_config().is_scope_allowed_for_cloud(
                routed.plan.team or routed.plan.function or req.session_state.team or req.session_state.function
            )
        ):
            has_employee_pii = bool(
                routed.plan.single_person
                or routed.plan.employee_id
                or routed.plan.employee_name
                or routed.plan.employee_placeholder
                or req.session_state.employee_id
                or signals.detected_employee_query
                or signals.asks_single_person
                or signals.asks_best_agent
                or signals.asks_worst_agent
                or routed.plan.intent in ("ranking", "corrective_actions")
                or routed.plan.operation_kind_v2
                in (
                    "ranking",
                    "person_summary",
                    "person_best_period",
                    "person_worst_period",
                    "person_tenure_check",
                    "corrective_actions",
                )
                or any(
                    isinstance(td, dict)
                    and any(
                        td.get(k)
                        for k in (
                            "employee_id",
                            "employee_name",
                            "top_performers",
                            "bottom_performers",
                            "top_contributors",
                            "actions",
                            "employees",
                            "individual_actions",
                            "spotlight",
                            "agent_spotlight",
                            "ranking",
                        )
                    )
                    for td in tool_digests
                )
                or any(
                    getattr(ev, "subject_type", None) in ("person", "employee", "agent")
                    or getattr(ev, "employee_id", None)
                    or getattr(ev, "employee_name", None)
                    for ev in typed_evidence
                )
                or sanitize_prompt_for_router_training(req.prompt, db=self.db) != req.prompt
            )
            if not has_employee_pii:
                self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
                if (
                    live_auth_service.is_plan_and_context_authorized(
                        scope=self.scope,
                        team=routed.plan.team,
                        function=routed.plan.function,
                        branch=routed.plan.branch,
                        branches=list(routed.plan.branches or []),
                        performance_level=routed.plan.performance_level,
                        region=effective_region,
                    )
                    and live_auth_service.is_returned_evidence_authorized(
                        scope=self.scope,
                        typed_evidence=typed_evidence,
                        tool_digests=tool_digests,
                        fallback_branch=routed.plan.branch,
                        fallback_level=routed.plan.performance_level,
                    )
                ):
                    release_read_transaction(self.db)
                    var_syn = synthesize_validated_executive_variation(
                        question=req.prompt,
                        digests=tool_digests,
                        typed_evidence=typed_evidence,
                        variant_idx=resolve_variation_index(
                            req.prompt,
                            req.history,
                            req.variation_seed,
                        ),
                        user_id=str(self.scope.get("user_id") or "") or None,
                        user_role=role or None,
                    )
                    self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
                    if var_syn is not None:
                        synthesis.headline = var_syn.headline
                        if var_syn.narrative_bullets:
                            synthesis.narrative_bullets = var_syn.narrative_bullets
                        synthesis.provider_used = var_syn.provider_used
                        synthesis.model_used = var_syn.model_used
                        synthesis.metrics = var_syn.metrics
        provider_ms = round(synthesis.metrics.provider_ms or ((time.perf_counter() - t_prov_start) * 1000.0 if synthesis.metrics.provider_calls > 0 else 0.0), 2)

        resolved_state = SessionFilterContext(
            function=routed.plan.function or routed.confirmed_context.function or req.session_state.function,
            team=signals.detected_team or (None if resolved_scope_changed else req.session_state.team),
            position=routed.plan.position or (None if resolved_scope_changed else req.session_state.position),
            branch=None if signals.asks_branch_comparison else (signals.detected_branch or (None if resolved_scope_changed else req.session_state.branch)),
            region=effective_region,
            performance_level=signals.detected_level or (None if resolved_scope_changed else req.session_state.performance_level),
            month=res_month,
            year=res_year,
            employee_id=routed.plan.employee_id,
            last_confirmed_query=routed.confirmed_context,
        )

        branch_override = (
            " vs ".join(name for name, _ in booking_comparison_facts.counts)
            if booking_comparison_facts is not None
            else None
        )
        scope_banner, resolved_fn = self._resolve_scope_banner_and_function(
            session_state=resolved_state,
            typed_evidence=typed_evidence,
            tool_digests=tool_digests,
            region=effective_region,
            branch_override=branch_override,
            month=res_month,
            year=res_year,
        )
        if resolved_fn != resolved_state.function:
            resolved_state.function = resolved_fn

        # Prefer a direct team/employee/BSC scorecard link as primary_source_link when available
        primary_link = None
        for dl in deep_links:
            if dl.icon_key in ("team", "employee", "bsc"):
                primary_link = dl
                break
        if primary_link is None and deep_links:
            primary_link = deep_links[0]

        evidence_envelope_v2 = self._build_evidence_envelope_v2(typed_evidence, tool_digests)

        # Revalidate live permissions after slow operations and BEFORE tracing, committing, or returning an answer
        try:
            self.scope = live_auth_service.validate_live_account_and_scope(self.scope)
        except Exception:
            if conv_service and claimed_turn and claimed_token:
                conv_service.repo.release_turn_claim(turn_id=str(claimed_turn.id), claim_token=claimed_token)
            raise

        detected_emp_id = routed.plan.employee_id or resolved_state.employee_id
        detected_emp_name = routed.plan.employee_name
        for td in tool_digests:
            if isinstance(td, dict):
                if not detected_emp_id and td.get("employee_id"):
                    detected_emp_id = str(td.get("employee_id"))
                if not detected_emp_name and td.get("employee_name"):
                    detected_emp_name = str(td.get("employee_name"))

        post_exec_authorized = live_auth_service.is_plan_and_context_authorized(
            scope=self.scope,
            team=resolved_state.team or routed.plan.team,
            function=resolved_state.function or routed.plan.function,
            branch=resolved_state.branch or routed.plan.branch,
            branches=list(routed.plan.branches or []),
            performance_level=resolved_state.performance_level or routed.plan.performance_level,
            region=effective_region,
            employee_id=detected_emp_id,
            employee_name=detected_emp_name,
        )
        if post_exec_authorized:
            post_exec_authorized = live_auth_service.is_returned_evidence_authorized(
                scope=self.scope,
                typed_evidence=typed_evidence,
                tool_digests=tool_digests,
                fallback_branch=resolved_state.branch,
                fallback_level=resolved_state.performance_level,
            )

        # Preserve the person actually returned by a single-person query so a
        # later "his/her" question cannot silently select a different employee,
        # and store ranked candidates on plural rankings so pronoun follow-ups clarify.
        if post_exec_authorized:
            is_ranking_result = bool(
                routed.plan.intent == "ranking"
                or "ranking" in routed.plan.requested_parts
                or any(operation.kind == "ranking" for operation in validated_plan_v2.operations)
            )
            ranking_candidates = (
                _ranking_candidates_from_digests(tool_digests)
                if is_ranking_result and not routed.plan.employee_id
                else []
            )
            if len(ranking_candidates) > 1:
                routed.confirmed_context.candidate_employees = ranking_candidates
                routed.confirmed_context.last_subject_employee_id = None
                routed.confirmed_context.last_subject_employee_name = None
                resolved_state.employee_id = None
                resolved_state.last_confirmed_query = routed.confirmed_context

            person_results = [
                tr.digest for tr in tool_results
                if tr.tool_name == "get_agent_spotlight_and_trend"
                and isinstance(tr.digest, dict)
                and tr.digest.get("employee_id")
            ]
            if len(ranking_candidates) > 1:
                pass
            elif routed.plan.single_person and len(person_results) == 1:
                person = person_results[0]
                spotlight = person.get("agent_spotlight") or {}
                if routed.plan.employee_id or not spotlight.get("ties"):
                    routed.confirmed_context.last_subject_employee_id = str(person["employee_id"])
                    routed.confirmed_context.last_subject_employee_name = str(person.get("employee_name") or "") or None
                    routed.confirmed_context.candidate_employees = []
                    resolved_state.last_confirmed_query = routed.confirmed_context
            elif not routed.plan.single_person and person_results:
                top_cands = _ranking_candidates_from_digests([person_results[0]])
                if len(top_cands) > 1:
                    routed.confirmed_context.candidate_employees = top_cands
                    routed.confirmed_context.last_subject_employee_id = None
                    routed.confirmed_context.last_subject_employee_name = None
                    resolved_state.last_confirmed_query = routed.confirmed_context

        if post_exec_authorized and routed.outcome == "answer" and len(typed_evidence) == 0:
            ucm_det = next(
                (
                    tr.digest.get("unavailable_count_metric")
                    for tr in tool_results
                    if isinstance(tr.digest, dict) and tr.digest.get("unavailable_count_metric")
                ),
                None,
            )
            if ucm_det:
                routed.outcome = "unavailable_data"
                typed_evidence = []
                evidence_envelope_v2 = []
                ucm_team_lbl = str(ucm_det.get("team") or routed.plan.team or "the requested team")
                ucm_branch = ucm_det.get("branch") or routed.plan.branch
                ucm_branch_title = str(ucm_branch).capitalize() if ucm_branch else ""
                m_lbl = signals.detected_month or res_month or "September"
                y_lbl = signals.detected_year or res_year or 2026
                synthesis.headline = (
                    f"No published {ucm_det['display_name']} records exist for {ucm_team_lbl} in {ucm_branch_title} ({m_lbl} {y_lbl})."
                    if ucm_branch_title
                    else f"No published {ucm_det['display_name']} records exist for {ucm_team_lbl} ({m_lbl} {y_lbl})."
                )
                synthesis.narrative_bullets = []
                synthesis.suggested_followups = []

        if (
            post_exec_authorized
            and routed.outcome == "answer"
            and routed.plan.employee_id
            and signals.detected_month
            and signals.detected_year
            and not signals.asks_trend
        ):
            emp_spotlight_missing = False
            for tr in tool_results:
                if tr.tool_name in ("get_agent_spotlight_and_trend", "get_kpi_diagnosis") and isinstance(tr.digest, dict):
                    sp_obj = tr.digest.get("agent_spotlight") or tr.digest.get("spotlight")
                    if sp_obj is None and tr.records_evaluated == 0:
                        emp_spotlight_missing = True
                        break
            if emp_spotlight_missing:
                routed.outcome = "unavailable_data"
                typed_evidence = []
                evidence_envelope_v2 = []
                synthesis.headline = (
                    f"No published PMS evaluation records exist for {routed.plan.employee_name or routed.plan.employee_id} "
                    f"in {signals.detected_month} {signals.detected_year}."
                )
                synthesis.narrative_bullets = []
                synthesis.suggested_followups = []

        if (
            post_exec_authorized
            and routed.outcome == "answer"
            and total_records_eval == 0
            and signals.detected_month
            and signals.detected_year
            and not routed.plan.employee_id
            and (
                routed.plan.team not in ("Support Positions", "Call Center", "RCM", "Finance", None)
                or ksa_region_hint_from_prompt(req.prompt)
                or routed.confirmed_context.region == "KSA"
            )
            and routed.confirmed_context.region != "All"
        ):
            avail = check_scope_data_availability(
                ctx.get_scoped_records(),
                country=routed.confirmed_context.region,
                function=routed.plan.function,
                team=routed.plan.team,
                month=signals.detected_month,
                year=signals.detected_year,
            )
            available_periods = avail["available_periods"]
            if not avail["has_data"] and (available_periods or ksa_region_hint_from_prompt(req.prompt)):
                routed.outcome = "unavailable_data"
                reg_note = f" ({routed.confirmed_context.region})" if routed.confirmed_context.region else ""
                synthesis.headline = (
                    f"No published PMS evaluation records exist for {routed.plan.team}{reg_note} in {signals.detected_month} {signals.detected_year}."
                )
                synthesis.narrative_bullets = []
                synthesis.suggested_followups = []
                if not available_periods:
                    typed_evidence = []
                    evidence_envelope_v2 = []
                if available_periods:
                    latest_avail = available_periods[-1]
                    synthesis.narrative_bullets = [f"The latest verified period for this scope is {latest_avail}."]
                    synthesis.suggested_followups = [f"What is {routed.plan.team} score in {latest_avail}?"]

        if not post_exec_authorized:
            routed.outcome = "restricted_access"
            synthesis.headline = (
                "Access restricted: your permissions changed during execution and no longer allow viewing this scope."
            )
            synthesis.narrative_bullets = [
                "Live permission revalidation detected that access to the requested team, level, branch, function, or employee was revoked."
            ]
            synthesis.suggested_followups = ["Show performance summary for my authorized scope"]
            final_cards = []
            citations = []
            deep_links = []
            primary_link = None
            typed_evidence = []
            evidence_envelope_v2 = []
            tool_call_records = []
            tool_digests = []
            total_records_eval = 0
            any_guardrail = True
            routed.confirmed_context.team = None
            routed.confirmed_context.branch = None
            routed.confirmed_context.branches = []
            routed.confirmed_context.performance_level = None
            routed.confirmed_context.last_subject_employee_id = None
            routed.confirmed_context.last_subject_employee_name = None
            routed.confirmed_context.single_person = False
            resolved_state.last_confirmed_query = routed.confirmed_context

        elif routed.outcome == "answer":
            synthesis.headline = _format_country_scope_text(
                synthesis.headline,
                routed.plan.team or resolved_state.team,
                routed.confirmed_context.region or resolved_state.region,
            )

        response_dict = {
            "headline": synthesis.headline,
            "narrative_bullets": synthesis.narrative_bullets,
            "citations": [c.model_dump() for c in citations],
            "prompt_version": MODEL_LED_SYNTHESIS_PROMPT_VERSION
            if routed.route_used == "model_led_pilot"
            else ACTIVE_PROMPT_VERSIONS["narrow_evidence_synthesis"],
        }

        t_trace_start = time.perf_counter()
        pre_trace_ms = int((t_trace_start - t0) * 1000)
        if post_exec_authorized and routed.outcome != "restricted_access":
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
                known_employee_names=known_emp_names,
            )
        else:
            trace_id = ""
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
        provider_usage = _build_aggregated_usage(
            router_mode=cfg.router_mode,
            route_used=routed.route_used,
            router_metrics=routed.provider_metrics,
            synth_metrics=synthesis.metrics,
        )
        total_provider_calls = provider_usage.provider_calls

        eff_ctx_label_final = build_effective_context_label(
            page_context=req.page_context,
            session_state=resolved_state,
            selected_metric_display=selected_metric_display,
        )
        action_proposal = None
        final_capability_mode = _resolved_capability_mode(
            capability_mode,
            outcome=routed.outcome,
            plan_intent=routed.plan.intent,
            prompt=req.prompt,
        )
        if (
            post_exec_authorized
            and routed.outcome == "answer"
            and capability_mode == "proposal"
        ):
            raw_sel_metric = (
                (req.page_context.selected_metric_id if req.page_context else None)
                or routed.plan.metric
            )
            action_proposal = build_corrective_action_proposal_from_evidence(
                db=self.db,
                scope=self.scope,
                session_state=resolved_state,
                typed_evidence=typed_evidence,
                records=ctx.get_scoped_records(),
                selected_metric_id=raw_sel_metric,
                primary_source_link=primary_link,
            )
            if action_proposal is not None:
                save_note = (
                    "Review and confirm below to save as an Open corrective action."
                    if action_proposal.can_user_create_action
                    else f"Your role ({role}) has read-only access and cannot save corrective actions."
                )
                synthesis.headline = (
                    f"Proposed {action_proposal.action_type} action for {action_proposal.team} on "
                    f"{action_proposal.metric_display_name} ({action_proposal.actual_display} vs. "
                    f"{action_proposal.target_display} target in {action_proposal.month} {action_proposal.year}). "
                    f"{save_note}"
                )
                synthesis.narrative_bullets = [
                    *action_proposal.observed_facts,
                    *([action_proposal.hypothesis] if action_proposal.hypothesis else []),
                ]

        if (
            routed.outcome == "answer"
            and routed.plan.metric is None
            and routed.plan.model_led_tool_call is None
            and any(ev.kpi_key == "overall_score" and ev.source_link for ev in typed_evidence)
        ):
            routed.plan.model_led_tool_call = {
                "tool_name": "read_employee_metric" if routed.plan.employee_id else "rank_employees",
                "tool_arguments": {"metric_id": "overall_score"},
            }

        final_answer_source = (
            "model_synthesis"
            if routed.outcome == "answer" and synthesis.provider_used in ("cloudflare", "gemini")
            else (
                "fallback"
                if routed.outcome == "answer"
                and provider_usage.fallback_outcome not in ("none", "", "not_called")
                else "deterministic"
            )
        )
        combined_digest: dict[str, Any] = {}
        for td in tool_digests:
            if isinstance(td, dict):
                combined_digest.update(td)
        summary_tiles = (
            build_response_summary_tiles(
                merged=combined_digest,
                visual_cards=final_cards,
                typed_evidence=typed_evidence,
            )
            if routed.outcome == "answer"
            else []
        )
        final_resp = AiChatResponsePayload(
            trace_id=trace_id,
            conversation_id=active_conversation_id,
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            context_version=active_context_version,
            outcome=routed.outcome,
            answer_detail=effective_detail,  # type: ignore[arg-type]
            headline=synthesis.headline,
            narrative_bullets=synthesis.narrative_bullets,
            summary_tiles=summary_tiles,
            visual_cards=final_cards,
            citations=citations,
            deep_links=deep_links[:3],
            primary_source_link=primary_link,
            suggested_followups=synthesis.suggested_followups[:1],
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
            answer_source=final_answer_source,
            latency_ms=latency_ms,
            timings=timings,
            provider_usage=provider_usage,
            basis_warning=basis_warning,
            cache_hit=cache_hit,
            capability_mode=final_capability_mode,
            effective_context_label=eff_ctx_label_final,
            action_proposal=action_proposal,
        )
        if conv_service and active_conversation_id and claimed_turn:
            try:
                payload_for_store = final_resp.model_dump()
                if claimed_context_version is not None:
                    payload_for_store["context_version"] = claimed_context_version + 1
                new_ver = conv_service.complete_turn(
                    conversation_id=active_conversation_id,
                    turn_id=str(claimed_turn.id),
                    expected_context_version=claimed_context_version,
                    claim_token=claimed_token,
                    scope=self.scope,
                    outcome=routed.outcome,
                    turn_kind="analytical" if post_exec_authorized else "clarification",
                    route_used=routed.route_used,
                    validated_plan=validated_plan_v2.model_dump() if post_exec_authorized else {},
                    evidence_envelope=[ev.model_dump() for ev in evidence_envelope_v2] if post_exec_authorized else [],
                    response_payload=payload_for_store,
                    session_state=resolved_state,
                    confirmed_context=routed.confirmed_context,
                    provider_calls=total_provider_calls,
                    total_ms=total_ms,
                )
                final_resp.context_version = new_ver
            except Exception:
                if not post_exec_authorized and claimed_token:
                    conv_service.repo.release_turn_claim(
                        turn_id=str(claimed_turn.id), claim_token=claimed_token
                    )
                else:
                    raise
        return final_resp

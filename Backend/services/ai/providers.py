from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from typing import Any, Literal

CostStatusType = Literal["measured_usd", "measured_neurons", "unknown", "not_applicable"]

from models.ai_schemas import StructuredQueryPlan
from services.ai.config import get_ai_runtime_config
from services.ai.domain_policies import ParsedPromptSignals
from services.ai.trace_logger import sanitize_prompt_for_router_training
from services.ai.compound_parts_planner import (
    compound_parts_enabled,
    plan_compound_parts,
    render_compound_parts_answer,
)

logger = logging.getLogger(__name__)

_UNSAFE_TABULAR_RE = re.compile(r"(?:\t[^\t]+\t[^\t]+|\n[^\n]+\|[^\n]+\|)")


class ProviderUnavailableError(RuntimeError):
    """Raised when an external provider fails and no safe local fallback or clarification is available."""


def ranking_value(row: dict, precision: int = 1) -> str:
    if row.get("actual_display"):
        return str(row["actual_display"])
    score = row.get("score")
    return f"{score:.{precision}f}%" if isinstance(score, (float, int)) else "unavailable"


@dataclass
class ProviderCallMetrics:
    provider_used: str = "deterministic"
    model_used: str = "pms-local-router-v1"
    provider_calls: int = 0
    provider_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    neurons: int = 0
    estimated_cost_usd: float = 0.0
    cost_status: CostStatusType = "not_applicable"
    fallback_outcome: str = "none"
    outbound_payload: dict[str, Any] | None = None


def resolve_cost_status(
    *,
    provider_calls: int,
    input_tokens: int,
    output_tokens: int,
    neurons: int,
    raw_estimated_cost_usd: float | None,
) -> CostStatusType:
    """Compute truthful cost attribution status without fabricating zero-dollar claims."""
    if neurons > 0:
        return "measured_neurons"
    if raw_estimated_cost_usd is not None:
        return "measured_usd"
    if input_tokens > 0 or output_tokens > 0:
        return "unknown"
    if provider_calls > 0:
        return "not_applicable"
    return "not_applicable"


def combine_cost_statuses(
    statuses: list[str],
    *,
    input_tokens: int,
    output_tokens: int,
    neurons: int,
    estimated_cost_usd: float,
) -> CostStatusType:
    """Aggregate cost_status across multiple provider calls (e.g. router + synthesis)."""
    if input_tokens == 0 and output_tokens == 0 and neurons == 0 and estimated_cost_usd == 0.0:
        return "not_applicable"
    if "unknown" in statuses:
        return "unknown"
    if neurons > 0 or "measured_neurons" in statuses:
        return "measured_neurons"
    if "measured_usd" in statuses:
        return "measured_usd"
    return "not_applicable"


def metrics_from_provider_response(
    resp: Any,
    *,
    provider_calls: int | None = None,
    fallback_outcome: str = "none",
    outbound_payload: dict[str, Any] | None = None,
) -> ProviderCallMetrics:
    """Build null-safe ProviderCallMetrics from a ProviderResponse."""
    usage = getattr(resp, "usage", None)
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    raw_neurons = getattr(resp, "neurons", None)
    if raw_neurons is None and usage is not None:
        raw_neurons = getattr(usage, "neurons", None)
    neurons_int = int(round(float(raw_neurons or 0)))
    raw_cost = getattr(resp, "estimated_cost_usd", None)
    cost_usd = round(float(raw_cost or 0.0), 8)
    calls = (
        int(provider_calls)
        if provider_calls is not None
        else (1 if (in_tok + out_tok > 0 or getattr(resp, "is_success", False)) else 0)
    )
    return ProviderCallMetrics(
        provider_used=str(getattr(resp, "provider", None) or "deterministic"),
        model_used=str(getattr(resp, "model", None) or ""),
        provider_calls=calls,
        provider_ms=float(getattr(resp, "latency_ms", 0.0) or 0.0),
        input_tokens=in_tok,
        output_tokens=out_tok,
        neurons=neurons_int,
        estimated_cost_usd=cost_usd,
        cost_status=resolve_cost_status(
            provider_calls=calls,
            input_tokens=in_tok,
            output_tokens=out_tok,
            neurons=neurons_int,
            raw_estimated_cost_usd=raw_cost,
        ),
        fallback_outcome=fallback_outcome,
        outbound_payload=outbound_payload,
    )


@dataclass
class StructuredRoutingProviderResult:
    plan: StructuredQueryPlan | None
    metrics: ProviderCallMetrics = field(default_factory=ProviderCallMetrics)
    error_detail: str | None = None


@dataclass
class NarrativeSynthesisResult:
    headline: str
    narrative_bullets: list[str]
    suggested_followups: list[str]
    provider_used: str
    model_used: str
    metrics: ProviderCallMetrics = field(default_factory=ProviderCallMetrics)
    detail_bullets: list[str] = field(default_factory=list)


def is_prompt_safe_for_external_projection(prompt: str) -> bool:
    """Reject prompts that look like raw workbook dumps, multi-row tables, or unprojectable payloads."""
    if not prompt or len(prompt.strip()) > 600:
        return False
    if _UNSAFE_TABULAR_RE.search(prompt):
        return False
    if prompt.count("\n") > 6:
        return False
    return True


def build_minimized_routing_payload(
    *,
    prompt: str,
    current_view: dict[str, Any],
    candidate_teams: list[str],
    candidate_metrics: list[str],
    candidate_branches: list[str],
    known_employee_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build a strictly minimized, PII-free payload for external structured intent routing.
    Never includes workbook contents, employee records, private KPI values, or conversation transcripts.
    """
    sanitized_question = sanitize_prompt_for_router_training(
        prompt, known_employee_names=known_employee_names
    )
    compact_view = {
        "function": current_view.get("function"),
        "team": current_view.get("team"),
        "branch": current_view.get("branch"),
        "performance_level": current_view.get("performance_level") or "Employee",
        "period": current_view.get("period"),
        "last_intent": current_view.get("last_intent"),
        "last_metric": current_view.get("last_metric"),
    }
    return {
        "question": sanitized_question[:400],
        "current_view": compact_view,
        "eligible_teams": candidate_teams[:25],
        "eligible_metrics": candidate_metrics[:40],
        "eligible_branches": candidate_branches[:10],
    }


class NvidiaStructuredRouterAdapter:
    """Routes legacy shadow and hybrid requests through the unified provider engine."""

    def propose_query_plan(
        self,
        *,
        prompt: str,
        current_view: dict[str, Any],
        candidate_teams: list[str],
        candidate_metrics: list[str],
        candidate_branches: list[str],
        known_employee_names: list[str] | None = None,
        timeout: float | None = None,
    ) -> StructuredRoutingProviderResult:
        cfg = get_ai_runtime_config()
        scope_key = current_view.get("team") or current_view.get("function")
        if not cfg.nvidia_routing_enabled:
            return StructuredRoutingProviderResult(
                plan=None, metrics=ProviderCallMetrics(fallback_outcome="cloud_disabled")
            )
        if not cfg.is_scope_allowed_for_cloud(scope_key):
            return StructuredRoutingProviderResult(
                plan=None, metrics=ProviderCallMetrics(fallback_outcome="scope_not_allowed")
            )
        if not is_prompt_safe_for_external_projection(prompt):
            return StructuredRoutingProviderResult(
                plan=None, metrics=ProviderCallMetrics(fallback_outcome="unsafe_prompt")
            )

        minimized_input = build_minimized_routing_payload(
            prompt=prompt,
            current_view=current_view,
            candidate_teams=candidate_teams,
            candidate_metrics=candidate_metrics,
            candidate_branches=candidate_branches,
            known_employee_names=known_employee_names,
        )
        config = replace(load_unified_provider_config(), primary_provider="nvidia", fallback_enabled=False)
        response = UnifiedProviderEngine(config).generate(
            ProviderRequest(
                system_instruction=(
                    "Convert the manager's question and view into a PMS query plan. Return only "
                    "a JSON object with intent and any relevant scope fields. Allowed intents: current_value, "
                    "actual_vs_target, compare_periods, compare_branches, trend, ranking, score_drivers, "
                    "scorecard_structure, corrective_actions, clarify, unsupported. Use eligible teams and metrics. "
                    "Use YYYY-MM periods and best/worst ranking_direction. Use query_rankings_args for aggregate rankings."
                ),
                messages=[ProviderMessage(role="user", content=json.dumps(minimized_input, ensure_ascii=False))],
                response_format="json",
                json_schema={"type": "object", "properties": {"intent": {"type": "string"}}, "required": ["intent"]},
                timeout_seconds=min(cfg.provider_timeout_seconds, timeout) if timeout is not None else cfg.provider_timeout_seconds,
                purpose="structured_routing",
                task_role="routine",
            )
        )
        executed_attempts = [attempt for attempt in response.attempts if attempt.status not in ("disabled", "missing_key", "skipped")]
        fallback_outcome = "none" if response.is_success else response.outcome
        if fallback_outcome == "provider_unavailable" and executed_attempts:
            fallback_outcome = executed_attempts[-1].status
        metrics = metrics_from_provider_response(
            response,
            provider_calls=len(executed_attempts),
            fallback_outcome=fallback_outcome,
            outbound_payload=minimized_input,
        )
        if not response.is_success:
            return StructuredRoutingProviderResult(plan=None, metrics=metrics)
        try:
            plan = StructuredQueryPlan.model_validate_json(response.content)
        except ValueError:
            metrics.fallback_outcome = "schema_validation_failed"
            return StructuredRoutingProviderResult(plan=None, metrics=metrics)
        return StructuredRoutingProviderResult(plan=plan, metrics=metrics)


_VARIATION_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "is", "are", "was", "were",
    "what", "which", "who", "how", "why", "where", "when", "show", "me", "give", "tell", "about",
    "this", "that", "month", "latest", "period", "score", "performance", "kpi", "kpis", "vs", "with",
})


def _meaningful_tokens(text: str) -> set[str]:
    return {
        tok
        for tok in re.findall(r"[a-z0-9\u0600-\u06ff]+", (text or "").casefold())
        if len(tok) >= 2 and tok not in _VARIATION_STOPWORDS
    }


def resolve_variation_index(
    prompt: str,
    history: list[Any] | None = None,
    variation_seed: int | None = None,
) -> int:
    """Resolve deterministic phrasing variant index in {0, 1, 2}.

    - variation_seed >= 1 -> int(variation_seed) % 3 (so seed=1 -> 1, seed=2 -> 2, seed=3 -> 0)
    - variation_seed in (None, 0) -> 0 on fresh/non-overlapping turns; shifts to
      (overlap_count % 2) + 1 when prior assistant turns in history cover an overlapping subject/scope.
    """
    if variation_seed is not None and int(variation_seed) >= 1:
        return int(variation_seed) % 3

    if not history:
        return 0

    curr_tokens = _meaningful_tokens(prompt)
    if not curr_tokens:
        return 0

    overlap_count = 0
    for msg in history:
        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
        if role != "assistant" or not content:
            continue
        hist_tokens = _meaningful_tokens(str(content))
        if curr_tokens & hist_tokens:
            overlap_count += 1

    if overlap_count >= 1:
        return (overlap_count % 2) + 1
    return 0


def _build_dynamic_followups(
    *,
    prompt: str,
    history: list[Any] | None,
    scope: str,
    branch: str,
    period: str,
    merged: dict[str, Any],
    variant_idx: int,
    session_state: Any | None = None,
) -> list[str]:
    """Generate context-aware follow-up chips excluding already-asked prompts and inapplicable scopes."""
    scope_cf = (scope or "").strip().casefold()
    branch_cf = (branch or "").strip().casefold()
    prompt_cf = (prompt or "").casefold()
    sess_region = (getattr(session_state, "region", None) or "").strip().casefold()
    sess_fn = (getattr(session_state, "function", None) or "").strip().casefold()
    sess_team = (getattr(session_state, "team", None) or "").strip().casefold()
    history_cf = " ".join(
        str(getattr(m, "content", None) if not isinstance(m, dict) else m.get("content") or "")
        for m in (history or [])
    ).casefold()
    non_uae_branch_teams = {
        "support positions",
        "coding egy",
        "submission egy",
        "resubmission egy",
        "re-submission",
        "pre-approvals ip offshore",
    }
    has_egy_context = (
        sess_region in ("egy", "egypt")
        or any(
            marker in text
            for marker in ("egy", "egypt", "offshore")
            for text in (prompt_cf, history_cf, scope_cf, sess_team)
        )
    )
    is_uae_cc = (
        scope_cf in ("call center", "inbound", "outbound")
        and (not sess_fn or sess_fn == "call center")
        and sess_team not in non_uae_branch_teams
        and branch_cf in ("all branches", "all", "")
        and sess_region in ("", "uae")
        and not has_egy_context
    )

    candidates: list[str] = []
    if merged.get("branch_comparison"):
        candidates.extend([
            f"Show verified KPI score drivers for {scope} in {period}",
            f"Which team had the lowest score in {period}?",
            f"What is {scope} 6-month trend?",
            f"Summarize open corrective actions in {scope}",
        ])
    elif merged.get("lowest_kpi") or merged.get("requested_kpi"):
        kpi_obj = merged.get("requested_kpi") or merged.get("lowest_kpi") or {}
        kpi_lbl = str(kpi_obj.get("kpi_label") or "KPI gaps")
        candidates.extend([
            f"Who are the top negative contributors on {kpi_lbl} in {scope}?",
            f"What is {scope} 6-month trend?",
            f"Summarize open corrective actions in {scope}",
        ])
        if is_uae_cc:
            candidates.append(f"Compare Dubai vs Sharjah branch performance for {scope}")
    elif merged.get("worst_team"):
        w_team = str(merged["worst_team"].get("team") or scope)
        candidates.extend([
            f"What is driving {w_team}'s score in {period}?",
            f"Who are the lowest-scoring performers in {w_team}?",
            f"Summarize open corrective actions in {w_team}",
            f"What is {w_team} 6-month trend?",
        ])
    elif merged.get("spotlight") or merged.get("agent_spotlight"):
        sp = merged.get("spotlight") or merged.get("agent_spotlight") or {}
        e_team = str(sp.get("team") or scope)
        r_dir = sp.get("ranking_direction")
        candidates.extend([
            f"Show verified KPI score drivers for {e_team} in {period}",
            (
                f"Who is the #1 top performer in {e_team}?"
                if r_dir == "worst"
                else f"Who is the lowest-scoring performer in {e_team}?"
            ),
            f"What is {e_team} 6-month trend?",
            f"Summarize open corrective actions in {e_team}",
        ])
    elif merged.get("top_contributors"):
        candidates.extend([
            f"Show verified KPI score drivers for {scope} in {period}",
            f"What is {scope} 6-month trend?",
            f"Summarize open corrective actions in {scope}",
            f"Who is the top performer in {scope}?",
        ])
    elif "total_actions" in merged:
        candidates.extend([
            f"What are the largest KPI gaps in {scope} for {period}?",
            f"Who are the top negative contributors in {scope}?",
            f"What is {scope} 6-month trend?",
        ])
    elif merged.get("bsc_kpis"):
        t_name = str(merged.get("team") or scope)
        candidates.extend([
            f"What are the largest KPI gaps in {t_name} for {period}?",
            f"What is {t_name} 6-month trend?",
            f"Summarize open corrective actions in {t_name}",
        ])
    else:
        if is_uae_cc:
            candidates.append(f"Compare Dubai vs Sharjah branch performance for {scope}")
        candidates.extend([
            f"Show verified KPI score drivers for {scope} in {period}",
            f"Who is the top performer in {scope}?",
            f"Who is the lowest-scoring performer in {scope}?",
            f"What is {scope} 6-month trend?",
        ])

    asked_texts = [prompt or ""]
    for msg in history or []:
        role = getattr(msg, "role", None) if not isinstance(msg, dict) else msg.get("role")
        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
        if role == "user" and content:
            asked_texts.append(str(content))

    def _norm_q(q: str) -> str:
        return " ".join(re.findall(r"[a-z0-9\u0600-\u06ff]+", q.casefold()))

    asked_norms = [_norm_q(a) for a in asked_texts if a]
    asked_token_sets = [_meaningful_tokens(a) for a in asked_texts if a]

    filtered: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        c_norm = _norm_q(cand)
        if not c_norm or c_norm in seen:
            continue
        if any(c_norm == an or (len(c_norm) >= 12 and (c_norm in an or an in c_norm)) for an in asked_norms):
            continue
        c_tokens = _meaningful_tokens(cand)
        if c_tokens and any(
            len(c_tokens & ats) >= max(3, int(round(0.8 * len(c_tokens))))
            for ats in asked_token_sets
            if ats
        ):
            continue
        seen.add(c_norm)
        filtered.append(cand)

    if not filtered:
        return []
    offset = variant_idx % len(filtered)
    rotated = filtered[offset:] + filtered[:offset]
    return rotated[:1]


class DeterministicLocalProviderAdapter:
    """Zero-dependency English analytical synthesizer & local composer over verified PMS evidence."""

    provider_name = "deterministic"
    model_name = "pms-local-router-v1"

    def synthesize(
        self,
        *,
        prompt: str,
        signals: ParsedPromptSignals,
        tool_digests: list[dict[str, Any]],
        guardrail_notes: list[str],
        history: list[Any] | None = None,
        variation_seed: int | None = None,
        session_state: Any | None = None,
    ) -> NarrativeSynthesisResult:
        bullets: list[str] = []
        detail_bullets: list[str] = []
        headline = ""
        variant_idx = resolve_variation_index(
            prompt=prompt,
            history=history,
            variation_seed=variation_seed,
        )

        # Combine digests across executed tools
        merged: dict[str, Any] = {}
        for d in tool_digests:
            merged.update(d)

        period = merged.get("period") or "Latest Period"
        scope = merged.get("scope") or "your authorized scope"
        branch = merged.get("branch") or "All Branches"

        # Composable rankings: a direction-aware headline from the single engine.
        # This branch is isolated so existing worst-first fallbacks stay intact.
        if qr := merged.get("query_rankings"):
            qr_rows = list(qr.get("rows") or [])
            raw_entity = str(qr.get("entity") or "department").replace("_", " ")
            entity_label = "role" if raw_entity == "position" else raw_entity
            order = qr.get("sort_order") or "desc"
            groups = qr.get("groups") or {}
            if qr_rows:
                first_row = qr_rows[0]
                name = first_row.get("name") or "the top group"
                score = first_row.get("score")
                precision = 2 if entity_label == "employee" else 1
                score_txt = ranking_value(first_row, precision)
                total = int(qr.get("total") or len(qr_rows))
                requested = qr.get("limit", 1)
                first_count = first_row.get("total")
                count_note = (
                    f" ({int(first_count)} evaluated employee)"
                    if entity_label == "role" and first_count == 1
                    else (f" ({int(first_count)} evaluated)" if entity_label == "role" and first_count else "")
                )
                # Detect ties at rank #1
                tied_top = [
                    str(r.get("name") or "")
                    for r in qr_rows
                    if isinstance(score, (int, float))
                    and isinstance(r.get("score"), (int, float))
                    and round(float(r["score"]), 4) == round(float(score), 4)
                ]
                if requested == 1:
                    label = "Best" if order == "desc" else "Lowest"
                    if len(tied_top) > 1:
                        headline = f"{label} {entity_label} in {scope} for {period}: tied between {', '.join(tied_top[:3])} at {score_txt}."
                    else:
                        headline = f"{label} {entity_label} in {scope} for {period} is {name} at {score_txt}{count_note}."
                elif entity_label == "employee" and not groups:
                    label = "Top" if order == "desc" else "Bottom"
                    emp_noun = "employee" if total == 1 else "employees"
                    headline = f"{label} {total} {emp_noun} in {scope} for {period}."
                else:
                    label = "Best" if order == "desc" else "Lowest"
                    if len(tied_top) > 1:
                        headline = f"{label} {entity_label} in {scope} for {period}: tied between {', '.join(tied_top[:3])} at {score_txt}."
                    else:
                        headline = f"{label} {entity_label} in {scope} for {period} is {name} at {score_txt}{count_note}."
                if qr.get("score_basis") == "average employee score":
                    headline = headline.rstrip(".") + " by average employee score."
                for row in qr_rows[:5] if requested != 1 and not groups else []:
                    value = ranking_value(row, precision)
                    row_cnt = row.get("total")
                    row_note = f" ({int(row_cnt)} evaluated)" if entity_label == "role" and row_cnt is not None else ""
                    bullets.append(f"{row.get('name') or 'Unknown'} — {value}{row_note}.")
                for gname, grows in list(groups.items())[:8]:
                    top = grows[0] if grows else {}
                    top_txt = ranking_value(top)
                    bullets.append(
                        f"{gname}: {len(grows)} ranked, led by {top.get('name') or 'Unknown'} at {top_txt}."
                    )
                excluded = list(qr.get("excluded_unverified") or [])
                if excluded:
                    excl_names = ", ".join(str(item.get("name") or "") for item in excluded[:5] if item.get("name"))
                    if excl_names:
                        bullets.append(
                            f"Coverage: {len(qr_rows)} verified ranked; excluded without verified official score: {excl_names}."
                        )
            else:
                headline = f"No scored {entity_label} records matched {scope} in {period}."

        # 0. Multi-part Team/Metric Trend + Top/Lowest Performer OR Single Spotlight
        elif team_metric_history := merged.get("team_metric_history"):
            metric = team_metric_history[0]["display_name"]
            first, last = team_metric_history[0], team_metric_history[-1]
            if len(team_metric_history) == 1:
                headline = f"{metric} for {scope} was {last['actual_display']} in {last['period']}."
            elif first["actual"] == last["actual"]:
                headline = (
                    f"{metric} for {scope} was unchanged from {first['period']} to {last['period']} "
                    f"at {last['actual_display']}."
                )
            else:
                movement = "rose" if last["actual"] > first["actual"] else "fell"
                headline = (
                    f"{metric} for {scope} {movement} from {first['actual_display']} in {first['period']} "
                    f"to {last['actual_display']} in {last['period']}."
                )
            if len(team_metric_history) > 2:
                detail_bullets.append(", ".join(
                    f"{point['period']}: {point['actual_display']}" for point in team_metric_history
                ))
            if spotlight := merged.get("agent_spotlight"):
                name = spotlight.get("entity_name")
                actual = spotlight.get("ranking_metric_actual_display")
                if name and actual:
                    rank = "lowest" if spotlight.get("ranking_direction") == "worst" else "highest"
                    bullets.append(f"{name} ranked {rank} in {spotlight.get('period') or period} with {actual}.")
                    if ties := spotlight.get("ties"):
                        bullets.append(f"Tied with {', '.join(ties)}.")
        elif merged.get("team_trend_spotlight") and merged.get("agent_spotlight"):
            tt = merged["team_trend_spotlight"]
            ap = merged["agent_spotlight"]
            t_scope = tt.get("team") or scope
            t_metric = tt.get("metric_label") or "Overall Score"
            t_sc = float(tt.get("score") or 0.0)
            t_first_sc = float(tt.get("first_score") or t_sc)
            t_first_lbl = tt.get("first_month_label") or ""
            t_six_d = tt.get("six_month_delta")
            t_delta_txt = f" ({t_six_d:+.1f} pp)" if t_six_d is not None else ""

            e_name = ap.get("entity_name") or "Agent"
            e_id = ap.get("entity_id")
            e_pos = str(ap.get("position") or "").strip()
            asks_pos = bool(re.search(r"\b(?:position|role|title)\b", (prompt or "").casefold()))
            pos_inline = f" · {e_pos}" if e_pos and asks_pos else ""
            e_team = ap.get("team") or scope
            r_dir = ap.get("ranking_direction")
            rank_num = ap.get("rank")
            tot_team = ap.get("total_in_team")
            rank_metric_lbl = ap.get("ranking_metric_label") or "Overall PMS Score"
            rank_metric_disp = ap.get("ranking_metric_display") or f"{float(ap.get('score') or 0.0):.1f}%"
            src_route = ap.get("source_route") or f"/employee/{e_id}"
            role_lbl = "lowest-scoring performer" if r_dir == "worst" else "#1 top performer"

            if variant_idx == 1:
                headline = (
                    f"Across {t_first_lbl} to {period}, {t_scope} {t_metric} shifted from {t_first_sc:.1f}% to {t_sc:.1f}%{t_delta_txt}, "
                    f"while {e_name} ({e_id}{pos_inline}) holds Rank #{rank_num} of {tot_team} ({role_lbl}) on {rank_metric_lbl} at {rank_metric_disp}."
                )
            elif variant_idx == 2:
                headline = (
                    f"Benchmark spotlight for {e_team} ({branch}) in {period}: {t_scope} {t_metric} reached {t_sc:.1f}%{t_delta_txt} from {t_first_lbl} ({t_first_sc:.1f}%), "
                    f"with {e_name} ({e_id}{pos_inline}) ranked #{rank_num}/{tot_team} as {role_lbl} ({rank_metric_disp} on {rank_metric_lbl})."
                )
            else:
                headline = (
                    f"{t_scope} {t_metric} moved from {t_first_lbl} ({t_first_sc:.1f}%) to {period} ({t_sc:.1f}%{t_delta_txt}), "
                    f"and {e_name} ({e_id}{pos_inline}) is the {role_lbl} in {e_team} ({branch}) for {period} by {rank_metric_lbl} at {rank_metric_disp} (Rank #{rank_num} of {tot_team})."
                )
            if asks_pos and e_pos:
                bullets.append(f"Role / Position: {e_pos} in {e_team} ({period}).")
            bullets.append(
                f"Ranking metric: {rank_metric_lbl} ({rank_metric_disp}) · Source: {src_route}."
            )
            detail_bullets.append(
                f"Verified performer evidence: {e_name} ({e_id}) · Ranking metric: {rank_metric_lbl} ({rank_metric_disp}) · Period: {period} · Scope: {e_team} ({branch}) · Source: {src_route}."
            )
        elif merged.get("spotlight"):
            sp = merged["spotlight"]
            e_name = sp.get("entity_name") or "Agent"
            e_id = sp.get("entity_id")
            e_pos = str(sp.get("position") or "").strip()
            asks_role_or_pos = bool(re.search(r"\b(?:position|role|title)\b", (prompt or "").casefold()))
            pos_txt = (
                f" · {e_pos}"
                if e_pos and (asks_role_or_pos or e_pos.casefold() not in ("agent", "call center agent"))
                else ""
            )
            e_team = sp.get("team") or scope
            has_period_score = bool(sp.get("selected_period_has_score", sp.get("score") is not None))
            sc = float(sp.get("score") or 0.0)
            gr = sp.get("grade") or "B"
            chg = sp.get("change_vs_prev") if has_period_score else None
            prev_lbl = sp.get("previous_month_label") or "prior month"
            six_d = sp.get("six_month_delta") if has_period_score else None
            first_lbl = sp.get("first_month_label") or ""
            r_dir = sp.get("ranking_direction")
            rank_num = sp.get("rank")
            tot_team = sp.get("total_in_team")
            metric_lbl = sp.get("metric_label") or "Overall Score"
            rank_metric_lbl = sp.get("ranking_metric_label") or "Overall PMS Score"

            def _fmt_pct(v: float) -> str:
                if abs(round(v, 2) - round(v, 1)) >= 1e-6:
                    return f"{v:.2f}%"
                return f"{v:.1f}%"

            sc_disp = _fmt_pct(sc)
            rank_disp = (
                str(sp.get("ranking_metric_display"))
                if rank_metric_lbl != "Overall PMS Score" and sp.get("ranking_metric_display")
                else f"{sc_disp} (Grade {gr})"
            )
            if chg is None:
                chg_txt = ""
            elif round(chg, 1) == 0:
                chg_txt = f", unchanged vs {prev_lbl}"
            else:
                chg_txt = f", {'up' if chg > 0 else 'down'} {chg:+.1f} pp vs {prev_lbl}"
            same_comparison = bool(
                chg is not None and six_d is not None
                and prev_lbl == first_lbl and round(chg, 1) == round(six_d, 1)
            )
            six_txt = f" ({six_d:+.1f} pp since {first_lbl})" if six_d is not None and first_lbl and not same_comparison else ""
            ties = list(sp.get("ties") or [])
            tie_txt = f", tied with {', '.join(ties[:2])}" if ties else ""
            missing_months = list(sp.get("missing_months") or [])
            missing_headline_note = (
                f" (Note: {', '.join(missing_months)} had no evaluated score and was excluded.)"
                if missing_months
                else ""
            )
            missing_headline_note_inline = (
                f" (Note: {', '.join(missing_months)} had no evaluated score and was excluded)"
                if missing_months
                else ""
            )
            def _human_kpi_name(mid: str) -> str:
                leaf = mid.rsplit(":", 1)[-1].casefold()
                labels = {
                    "waitingtime": "Waiting Time",
                    "bookings_count": "Bookings Count",
                    "attended_count": "Attended Count",
                    "handled_calls_count": "Handled Calls",
                    "abandoned_calls_count": "Abandoned Calls",
                    "booking_rate": "Booking Rate",
                    "attendance_rate": "Attendance Rate",
                    "attendance_compliance": "Attendance Compliance",
                    "team_sla": "Team SLA",
                    "abandon_rate": "Abandon Rate",
                    "reachability": "Reachability",
                    "aht": "AHT",
                    "quality_errors": "Quality Errors",
                    "quality_score": "Quality Score",
                    "ajm_pharmacy_man_iv_cost_saving": "IV Cost Saving",
                    "leakage": "Leakage",
                    "tendercompliance": "Tender Compliance",
                    "atv": "Average Transaction Value (ATV)",
                    "mb_cpl": "CPL",
                    "mb_leads": "Leads",
                    "gd_rework": "Rework",
                    "sms_response_time": "Response Time",
                    "rejection": "Controllable Rejection Rate",
                    "policyrejection": "Policy Rejection Rate",
                }
                return labels.get(leaf, leaf.replace("_", " ").title())

            def _match_snap_for_metric(mid: str, snaps: list[dict[str, Any]]) -> dict[str, Any] | None:
                leaf = mid.rsplit(":", 1)[-1].casefold().replace("_", "")
                alias_map = {
                    "waitingtime": "waitingtime",
                    "bookingscount": "bookings",
                    "attendedcount": "attended",
                    "handledcallscount": "handled",
                    "abandonedcallscount": "abandoned",
                    "bookingrate": "bookingrate",
                    "attendancerate": "attendancerate",
                    "abandonrate": "abandonrate",
                    "reachability": "reachability",
                    "qualityerrors": "qualityerrors",
                    "qualityscore": "qualityscore",
                    "ajmpharmacymanivcostsaving": "ivcostsaving",
                    "mbcpl": "cpl",
                    "mbleads": "leads",
                    "gdrework": "rework",
                    "smsresponsetime": "responsetime",
                    "rejection": "rejection",
                    "policyrejection": "policyrejection",
                }
                probe = alias_map.get(leaf, leaf)
                for s_item in snaps:
                    s_key = re.sub(r"[^a-z0-9]", "", str(s_item.get("kpi_key") or "").casefold())
                    s_lbl = re.sub(r"[^a-z0-9]", "", str(s_item.get("kpi_label") or "").casefold())
                    if probe == s_key or probe == s_lbl or probe in s_lbl or probe in s_key:
                        return {
                            "display_name": s_item.get("kpi_label") or s_item.get("kpi_key"),
                            "actual": s_item.get("numeric_value"),
                            "target": s_item.get("target_numeric"),
                            "unit": s_item.get("unit") or "",
                            "direction": s_item.get("direction") or "higher_better",
                        }
                return None

            from models.report_schemas import MONTHS as _M_MAP
            _explicit_sp_periods: list[str] = []
            for _rlbl in (sp.get("requested_period_labels") or []):
                _parts_p = str(_rlbl or "").strip().split()
                if len(_parts_p) == 2 and _parts_p[0] in _M_MAP and _parts_p[1].isdigit():
                    _pk = f"{int(_parts_p[1]):04d}-{_M_MAP[_parts_p[0]]:02d}"
                    if _pk not in _explicit_sp_periods:
                        _explicit_sp_periods.append(_pk)

            c_plan = (
                plan_compound_parts(
                    prompt or "",
                    team=e_team,
                    explicit_periods=_explicit_sp_periods or None,
                    prior_metric_id=signals.detected_kpi,
                )
                if compound_parts_enabled()
                else None
            )
            all_hist_sp = list(sp.get("all_history") or [])
            covered_all_periods = {str(pt.get("period") or "").strip().casefold() for pt in all_hist_sp}
            import calendar as _cal_p
            req_lbls_p = [
                str(lbl).strip()
                for lbl in (
                    sp.get("requested_period_labels")
                    or (
                        [
                            f"{_cal_p.month_name[int(ep[5:7])]} {int(ep[:4])}"
                            for ep in (c_plan.explicit_periods or [])
                            if re.match(r"^\d{4}-\d{2}$", ep)
                        ]
                        if c_plan
                        else []
                    )
                )
                if str(lbl).strip()
            ]
            has_missing_req_period = bool(
                covered_all_periods
                and any(lbl.casefold() not in covered_all_periods for lbl in req_lbls_p)
            )
            all_snaps_pre = list(sp.get("all_kpi_snapshots") or [])
            if sp.get("ranking_metric_actual") is not None and not any(
                str(s.get("kpi_label") or "").casefold() == str(rank_metric_lbl or "").casefold()
                for s in all_snaps_pre
            ):
                all_snaps_pre.insert(0, {
                    "kpi_key": rank_metric_lbl,
                    "kpi_label": rank_metric_lbl,
                    "numeric_value": sp.get("ranking_metric_actual"),
                    "target_numeric": sp.get("ranking_metric_target"),
                    "unit": sp.get("ranking_metric_unit") or "",
                    "direction": sp.get("ranking_metric_direction") or "higher_better",
                })
            missing_req_kpis: list[str] = []
            if c_plan and all_snaps_pre:
                for rm in (c_plan.requested_metrics or []):
                    if rm == "overall_score":
                        continue
                    if _match_snap_for_metric(rm, all_snaps_pre) is None:
                        hk = _human_kpi_name(rm)
                        if hk not in missing_req_kpis:
                            missing_req_kpis.append(hk)

            compound_override_needed = bool(
                compound_parts_enabled()
                and c_plan is not None
                and (sp.get("ranking_metric_actual") is not None or has_period_score or bool(all_snaps_pre))
                and (
                    c_plan.asks_target_gap
                    or c_plan.asks_unsupported_action
                    or c_plan.asks_causal_hypothesis
                    or c_plan.asks_corrective_plan
                    or len([m for m in c_plan.requested_metrics if m != "overall_score"]) >= 2
                    or (len([m for m in c_plan.requested_metrics if m != "overall_score"]) >= 1 and (c_plan.asks_overall_score or asks_role_or_pos))
                    or bool(missing_req_kpis and has_period_score)
                    or (c_plan.asks_period_comparison and has_missing_req_period)
                )
            )
            if compound_override_needed and sp.get("single_person") is False and r_dir not in ("best", "worst"):
                compound_override_needed = False

            def _render_employee_compound() -> tuple[str, list[str]]:
                assert c_plan is not None
                requested_specific = [m for m in (c_plan.requested_metrics or []) if m != "overall_score"]
                matched_dicts: list[dict[str, Any]] = []
                seen_matched_lbls: set[str] = set()
                if sp.get("ranking_metric_actual") is not None:
                    prim_dict = {
                        "display_name": rank_metric_lbl,
                        "actual": sp.get("ranking_metric_actual"),
                        "target": sp.get("ranking_metric_target"),
                        "unit": sp.get("ranking_metric_unit") or "",
                        "direction": sp.get("ranking_metric_direction") or "higher_better",
                    }
                    matched_dicts.append(prim_dict)
                    seen_matched_lbls.add(str(prim_dict["display_name"] or "").casefold())
                for r_mid in requested_specific:
                    m_snap = _match_snap_for_metric(r_mid, all_snaps_pre)
                    if m_snap and str(m_snap.get("display_name") or "").casefold() not in seen_matched_lbls:
                        matched_dicts.append(m_snap)
                        seen_matched_lbls.add(str(m_snap.get("display_name") or "").casefold())

                kpi_ev_dict = matched_dicts[0] if matched_dicts else None
                extra_kpi_evs = matched_dicts[1:] if len(matched_dicts) > 1 else None

                kpi_hist_sp = list(sp.get("kpi_history") or [])
                if not kpi_hist_sp and kpi_ev_dict is None:
                    kpi_hist_sp = [
                        {"period": pt.get("period"), "value": pt.get("score")}
                        for pt in all_hist_sp
                        if pt.get("score") is not None
                    ]
                prev_requested_lbl = next(
                    (lbl for lbl in req_lbls_p if lbl.casefold() != str(period).casefold()),
                    None,
                )
                prev_ev_dict = None
                if prev_requested_lbl and kpi_hist_sp:
                    matched_prev_pt = next(
                        (pt for pt in kpi_hist_sp if str(pt.get("period") or "").strip().casefold() == prev_requested_lbl.casefold()),
                        None,
                    )
                    if matched_prev_pt and matched_prev_pt.get("value") is not None:
                        prev_ev_dict = {"period": matched_prev_pt.get("period"), "actual": matched_prev_pt.get("value")}
                if prev_ev_dict is None and len(kpi_hist_sp) >= 2:
                    prev_pt = kpi_hist_sp[-2]
                    prev_ev_dict = {
                        "period": prev_pt.get("period"),
                        "actual": prev_pt.get("value"),
                    }
                elif prev_ev_dict is None and has_period_score and kpi_ev_dict is None and chg is not None:
                    prev_ev_dict = {
                        "period": prev_lbl,
                        "actual": round(sc - float(chg), 2),
                    }

                prev_ov_dict = None
                if prev_requested_lbl and all_hist_sp:
                    ov_pt = next(
                        (pt for pt in all_hist_sp if str(pt.get("period") or "").strip().casefold() == prev_requested_lbl.casefold()),
                        None,
                    )
                    if ov_pt and ov_pt.get("score") is not None:
                        prev_ov_dict = {"period": ov_pt.get("period"), "actual": ov_pt.get("score")}
                elif len(all_hist_sp) >= 2:
                    ov_pt = all_hist_sp[-2]
                    if ov_pt.get("score") is not None:
                        prev_ov_dict = {"period": ov_pt.get("period"), "actual": ov_pt.get("score")}

                missing_p: list[str] = [
                    str(m) for m in (sp.get("missing_months") or [])
                    if str(m).split()[0].casefold() in (prompt or "").casefold()
                ]
                if kpi_ev_dict is not None and c_plan.asks_period_comparison and not missing_req_kpis:
                    for m in (sp.get("kpi_missing_months") or []):
                        if str(m).split()[0].casefold() in (prompt or "").casefold() and str(m) not in missing_p:
                            missing_p.append(str(m))
                for lbl in req_lbls_p:
                    if covered_all_periods and lbl.casefold() not in covered_all_periods and lbl not in missing_p:
                        missing_p.append(lbl)
                _ov_snap = _match_snap_for_metric("overall_score", all_snaps_pre)
                _ov_tgt_val = float(_ov_snap["target"]) if (_ov_snap and _ov_snap.get("target") is not None) else 100.0
                c_head_out, c_bul_out, _ = render_compound_parts_answer(
                    plan=c_plan,
                    subject_name=e_name,
                    team_name=e_team,
                    period_label=period,
                    kpi_evidence=kpi_ev_dict,
                    overall_score_val=sc if has_period_score else None,
                    previous_kpi_evidence=prev_ev_dict,
                    missing_periods=missing_p or None,
                    extra_kpi_evidences=extra_kpi_evs,
                    previous_overall_score=prev_ov_dict,
                    missing_kpis=missing_req_kpis or None,
                    overall_score_target=_ov_tgt_val,
                )
                return c_head_out, c_bul_out

            if (signals.asks_best_month_history or signals.asks_worst_month_history) and sp.get("all_history"):
                is_worst_q = bool(signals.asks_worst_month_history)
                target_label = "worst" if is_worst_q else "best"
                extremum_sc = float(
                    (sp.get("worst_score") if is_worst_q else sp.get("best_score"))
                    if (sp.get("worst_score") if is_worst_q else sp.get("best_score")) is not None
                    else sc
                )
                extremum_disp = _fmt_pct(extremum_sc)
                extremum_months = list(
                    (sp.get("worst_months") if is_worst_q else sp.get("best_months")) or [period]
                )
                searched_win = str(sp.get("searched_window") or period)
                is_match = bool(
                    sp.get("is_asked_period_worst") if is_worst_q else sp.get("is_asked_period_best")
                )
                win_months_str = (
                    " and ".join(extremum_months)
                    if len(extremum_months) <= 2
                    else ", ".join(extremum_months)
                )
                if signals.asks_specific_month_in_prompt:
                    if not has_period_score:
                        if variant_idx == 1:
                            headline = (
                                f"No—{e_name} ({e_id}{pos_txt}) had no published score in {period}, and across {searched_win} their {target_label} month by {rank_metric_lbl} was {win_months_str} ({extremum_disp}){missing_headline_note_inline}."
                            )
                        elif variant_idx == 2:
                            headline = (
                                f"No; {period} has no published evaluation for {e_name} ({e_id}{pos_txt}), whereas their {target_label} {searched_win} benchmark by {rank_metric_lbl} stood at {extremum_disp} in {win_months_str}{missing_headline_note_inline}."
                            )
                        else:
                            headline = (
                                f"No. {e_name} ({e_id}{pos_txt}) had no published evaluation score in {period}, while their {target_label} month across "
                                f"{searched_win} by {rank_metric_lbl} was {win_months_str} at {extremum_disp}.{missing_headline_note}"
                            )
                    elif is_match:
                        others = [m for m in extremum_months if m.casefold() != str(period).casefold()]
                        tie_str = f" (tied with {', '.join(others)})" if others else ""
                        if variant_idx == 1:
                            headline = (
                                f"Yes—{period} marked {e_name}'s ({e_id}{pos_txt}) {target_label} result across {searched_win} in {e_team} at {sc_disp} on {rank_metric_lbl}{tie_str}{missing_headline_note_inline}."
                            )
                        elif variant_idx == 2:
                            headline = (
                                f"Yes; across {searched_win} in {e_team}, {e_name} ({e_id}{pos_txt}) posted their {target_label} {rank_metric_lbl} result in {period} at {sc_disp}{tie_str}{missing_headline_note_inline}."
                            )
                        else:
                            headline = (
                                f"Yes. {period} was {e_name}'s ({e_id}{pos_txt}) {target_label} month across {searched_win} "
                                f"in {e_team} by {rank_metric_lbl} at {sc_disp}{tie_str}.{missing_headline_note}"
                            )
                    else:
                        if variant_idx == 1:
                            headline = (
                                f"No—{e_name} ({e_id}{pos_txt}) recorded {sc_disp} in {period}, whereas {win_months_str} was their {target_label} month across {searched_win} on {rank_metric_lbl} at {extremum_disp}{missing_headline_note_inline}."
                            )
                        elif variant_idx == 2:
                            headline = (
                                f"No; {e_name} ({e_id}{pos_txt}) stood at {sc_disp} in {period}, while their {searched_win} {target_label} benchmark by {rank_metric_lbl} occurred in {win_months_str} ({extremum_disp}){missing_headline_note_inline}."
                            )
                        else:
                            headline = (
                                f"No. {e_name} ({e_id}{pos_txt}) scored {sc_disp} in {period}, while their {target_label} month across "
                                f"{searched_win} by {rank_metric_lbl} was {win_months_str} at {extremum_disp}.{missing_headline_note}"
                            )
                else:
                    tie_note = " (tied)" if len(extremum_months) > 1 else ""
                    if variant_idx == 1:
                        headline = (
                            f"Across {searched_win} in {e_team}, {e_name}'s ({e_id}{pos_txt}) {target_label} {rank_metric_lbl} period was {win_months_str}{tie_note} at {extremum_disp}{missing_headline_note_inline}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Historical {rank_metric_lbl} benchmark for {e_name} ({e_id}{pos_txt}) in {e_team}: {win_months_str}{tie_note} stands as the {target_label} month across {searched_win} at {extremum_disp}{missing_headline_note_inline}."
                        )
                    else:
                        headline = (
                            f"{e_name}'s ({e_id}{pos_txt}) {target_label} month across {searched_win} in {e_team} "
                            f"by {rank_metric_lbl} was {win_months_str}{tie_note} at {extremum_disp}.{missing_headline_note}"
                        )
                if missing_months:
                    bullets.append(
                        f"Note: {', '.join(missing_months)} had no evaluated score and was excluded rather than treated as 0%."
                    )
                hist_pts = [
                    f"{pt['period']}: {_fmt_pct(float(pt.get('raw_score', pt['score'])))}"
                    for pt in (sp.get("all_history") or [])
                ]
                if hist_pts:
                    detail_bullets.append(
                        f"Full history ({searched_win} · {rank_metric_lbl}): " + " · ".join(hist_pts) + "."
                    )
            elif r_dir == "team_trend":
                if metric_lbl and metric_lbl != "Overall Score":
                    if variant_idx == 1:
                        headline = f"{e_team} {metric_lbl} landed at {sc_disp} in {period}{chg_txt}{six_txt}."
                    elif variant_idx == 2:
                        headline = f"Trajectory view for {e_team} {metric_lbl}: {sc_disp} in {period}{chg_txt}{six_txt}."
                    else:
                        headline = f"{e_team} {metric_lbl} reached {sc_disp} in {period}{chg_txt}{six_txt}."
                else:
                    if variant_idx == 1:
                        headline = f"{e_team} stood at {sc_disp} (Grade {gr}) in {period}{chg_txt}{six_txt}."
                    elif variant_idx == 2:
                        headline = f"Team benchmark for {e_team} in {period}: {sc_disp} (Grade {gr}){chg_txt}{six_txt}."
                    else:
                        headline = f"{e_team} scored {sc_disp} (Grade {gr}) in {period}{chg_txt}{six_txt}."
                if compound_override_needed:
                    c_headline, c_bullets = _render_employee_compound()
                    if c_headline:
                        headline = c_headline
                        bullets.extend(b for b in c_bullets if b not in bullets)
            elif not has_period_score:
                searched_win = str(sp.get("searched_window") or "")
                avail_pts = list(sp.get("all_history") or [])
                avail_note = (
                    f" Published scores are available across {searched_win}."
                    if searched_win and avail_pts
                    else ""
                )
                if variant_idx == 1:
                    headline = (
                        f"No published evaluation score exists for {e_name} ({e_id}{pos_txt}) in {period} ({e_team}); prior-period substitution is disabled.{avail_note}"
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Evaluation data for {e_name} ({e_id}{pos_txt}) is unpublished for {period} in {e_team}.{avail_note}"
                    )
                else:
                    headline = (
                        f"No published evaluation score is available for {e_name} ({e_id}{pos_txt}) in {period} ({e_team}).{avail_note}"
                    )
                bullets.append(
                    f"Note: {period} has no published evaluation score for {e_name} ({e_id}); PMS AI does not substitute another month's score."
                )
            elif sp.get("single_person") is False and sp.get("top_agents") and not signals.detected_employee_query:
                top_list = list(sp.get("top_agents") or [])[:3]
                dir_lbl = "lowest" if r_dir == "worst" else "top"
                summary_items = ", ".join(
                    f"#{item['rank']} {item['employee_name']} ({float(item['score']):.1f}%)"
                    for item in top_list
                )
                headline = f"The {dir_lbl} {len(top_list)} agents in {e_team} ({branch}) for {period} by {rank_metric_lbl}: {summary_items}."
                bullets.append(
                    "Ranked breakdown: "
                    + " · ".join(
                        f"#{item['rank']} {item['employee_name']} ({item['employee_id']}"
                        + (f" · {item['position']}" if item.get("position") else "")
                        + f"): {float(item['score']):.1f}% (Grade {item['grade']})"
                        for item in top_list
                    )
                    + "."
                )
            elif r_dir == "worst" and not signals.detected_employee_query:
                is_kpi_rank = str(rank_metric_lbl or "").strip().casefold() not in ("overall score", "overall pms score", "")
                if variant_idx == 1:
                    headline = (
                        f"Coaching priority in {e_team} ({branch}) for {period}: {e_name} ({e_id}{pos_txt}) recorded the lowest {rank_metric_lbl} at {rank_disp} (Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Bottom-ranked benchmark in {e_team} ({branch}) for {period}: {e_name} ({e_id}{pos_txt}) sits at Rank #{rank_num} of {tot_team} by {rank_metric_lbl} with {rank_disp}{tie_txt}{chg_txt}{six_txt}."
                    )
                elif is_kpi_rank:
                    headline = (
                        f"{e_name} ({e_id}{pos_txt}) has the lowest {rank_metric_lbl} in {e_team} ({branch}) for {period} at "
                        f"{rank_disp} (Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                    )
                else:
                    headline = (
                        f"{e_name} ({e_id}{pos_txt}) is the lowest-scoring agent in {e_team} ({branch}) for {period} by {rank_metric_lbl} at "
                        f"{rank_disp} (Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                    )
                if compound_override_needed:
                    c_headline, c_bullets = _render_employee_compound()
                    if c_headline:
                        headline = f"{headline} {c_headline}"
                        bullets.extend(b for b in c_bullets if b not in bullets)
                if not is_kpi_rank and sp.get("all_kpi_snapshots"):
                    drag_snaps = [
                        snap
                        for snap in (sp.get("all_kpi_snapshots") or [])
                        if isinstance(snap, dict)
                        and str(snap.get("kpi_key") or "").casefold() not in ("overall_score", "bookings_count", "attended_count")
                        and snap.get("achievement_percent") is not None
                        and float(snap["achievement_percent"]) < 95.0
                    ]
                    drag_snaps.sort(key=lambda s: float(s["achievement_percent"]))
                    if drag_snaps:
                        drag_parts = []
                        for s in drag_snaps[:2]:
                            s_lbl = str(s.get("kpi_label") or s.get("kpi_key") or "KPI")
                            s_act = str(s.get("actual_display") or "")
                            s_ach = float(s["achievement_percent"])
                            s_tgt = s.get("target_numeric")
                            s_unit = str(s.get("unit") or "")
                            if s_tgt is not None:
                                tgt_txt = f"{float(s_tgt):.1f}%" if s_unit == "%" else f"{float(s_tgt):g} {s_unit}".strip()
                                drag_parts.append(f"{s_lbl} at {s_act} vs {tgt_txt} target ({s_ach:.1f}% ach)")
                            else:
                                drag_parts.append(f"{s_lbl} at {s_act} ({s_ach:.1f}% ach)")
                        bullets.append("Key KPI drags: " + " · ".join(drag_parts) + ".")
            elif not signals.detected_employee_query:
                is_kpi_rank = str(rank_metric_lbl or "").strip().casefold() not in ("overall score", "overall pms score", "")
                if variant_idx == 1:
                    headline = (
                        f"Leading {e_team} ({branch}) in {period}, {e_name} ({e_id}{pos_txt}) ranks #1 of {tot_team} by {rank_metric_lbl} at {rank_disp}{tie_txt}{chg_txt}{six_txt}."
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Top benchmark in {e_team} ({branch}) for {period}: {e_name} ({e_id}{pos_txt}) holds #1 of {tot_team} on {rank_metric_lbl} with {rank_disp}{tie_txt}{chg_txt}{six_txt}."
                    )
                elif is_kpi_rank:
                    headline = (
                        f"{e_name} ({e_id}{pos_txt}) is the #1 top performer in {e_team} ({branch}) for {period} on {rank_metric_lbl} at "
                        f"{rank_disp} (Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                    )
                else:
                    headline = (
                        f"{e_name} ({e_id}{pos_txt}) is the #1 top performer in {e_team} ({branch}) for {period} by {rank_metric_lbl} at "
                        f"{rank_disp} (Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                    )
                if compound_override_needed:
                    c_headline, c_bullets = _render_employee_compound()
                    if c_headline:
                        headline = f"{headline} {c_headline}"
                        bullets.extend(b for b in c_bullets if b not in bullets)
            elif compound_override_needed:
                c_headline, c_bullets = _render_employee_compound()
                if c_headline:
                    headline = c_headline
                    bullets.extend(b for b in c_bullets if b not in bullets)
                else:
                    headline = f"{e_name} ({e_id}{pos_txt}) scored {sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}) in {period}{chg_txt}{six_txt}."
            elif asks_role_or_pos and e_pos and not signals.asks_trend and not signals.asks_worst_agent and not signals.asks_best_agent:
                headline = (
                    f"{e_name} ({e_id}) holds the position of {e_pos} in {e_team} "
                    f"({period} score: {sc_disp}, Grade {gr}, Rank #{rank_num} of {tot_team}{chg_txt})."
                )
            elif signals.asks_trend:
                kpi_hist = list(sp.get("kpi_history") or [])
                kpi_missing = list(sp.get("kpi_missing_months") or [])
                avail_pts = list(sp.get("all_history") or [])
                req_period_labels = {
                    str(p).strip().casefold()
                    for p in (sp.get("requested_period_labels") or [])
                    if str(p).strip()
                }
                if len(req_period_labels) >= 2:
                    matched_kpi = [
                        pt for pt in kpi_hist if str(pt.get("period") or "").strip().casefold() in req_period_labels
                    ]
                    if len(matched_kpi) >= 2:
                        kpi_hist = matched_kpi
                        kpi_missing = [m for m in kpi_missing if str(m).strip().casefold() in req_period_labels]
                    matched_pts = [
                        pt for pt in avail_pts if str(pt.get("period") or "").strip().casefold() in req_period_labels
                    ]
                    if len(matched_pts) >= 2:
                        avail_pts = matched_pts
                        missing_months = [m for m in missing_months if str(m).strip().casefold() in req_period_labels]
                        missing_headline_note = (
                            f" ({len(missing_months)} month(s) had no published score and were excluded)."
                            if missing_months
                            else ""
                        )
                asks_specific_kpi_trend = bool(
                    signals.detected_kpi and rank_metric_lbl != "Overall PMS Score"
                )
                if asks_specific_kpi_trend:
                    if len(kpi_hist) >= 2:
                        first_k = kpi_hist[0]
                        last_k = kpi_hist[-1]
                        delta_val = float(last_k["value"]) - float(first_k["value"])
                        unit = str(last_k.get("unit") or "")
                        if unit == "%":
                            delta_str = "flat, 0.0 pp" if abs(delta_val) < 0.05 else f"{delta_val:+.1f} pp"
                        elif unit in ("bookings", "attended"):
                            delta_int = int(round(delta_val))
                            delta_str = "no change (0)" if delta_int == 0 else f"{delta_int:+,d} {unit}"
                        elif unit:
                            delta_str = "flat" if abs(delta_val) < 0.05 else f"{delta_val:+.1f} {unit}"
                        else:
                            delta_str = "flat" if abs(delta_val) < 0.05 else f"{delta_val:+.1f}"
                        headline = (
                            f"Across {first_k['period']} to {last_k['period']} ({len(kpi_hist)} months), "
                            f"{e_name} ({e_id}{pos_txt}) recorded {last_k['actual_display']} on {rank_metric_lbl} "
                            f"in {last_k['period']} (from {first_k['actual_display']} in {first_k['period']}, {delta_str}) in {e_team}."
                        )
                        bullets.append(
                            f"Monthly {rank_metric_lbl} history: "
                            + ", ".join(f"{pt['period']}: {pt['actual_display']}" for pt in kpi_hist)
                            + "."
                        )
                        if kpi_missing:
                            bullets.append(
                                f"Periods without {rank_metric_lbl} data excluded: {', '.join(kpi_missing)}."
                            )
                    elif len(kpi_hist) == 1:
                        only_k = kpi_hist[0]
                        headline = (
                            f"Insufficient multi-month history for a {rank_metric_lbl} trend in {e_team}: "
                            f"{e_name} ({e_id}{pos_txt}) has verified data for only 1 period ({only_k['period']}: {only_k['actual_display']})."
                        )
                        bullets.append(
                            f"Only 1 period ({only_k['period']}) has verified {rank_metric_lbl} data for {e_name} ({e_id}), "
                            "so a multi-month trend cannot be established yet."
                        )
                    else:
                        headline = (
                            f"Insufficient historical data for a {rank_metric_lbl} trend for "
                            f"{e_name} ({e_id}{pos_txt}) in {e_team}."
                        )
                        bullets.append(
                            f"No multi-month {rank_metric_lbl} history is available in scope for {e_name} ({e_id})."
                        )
                else:
                    if len(avail_pts) >= 2:
                        first_p = avail_pts[0]
                        last_p = avail_pts[-1]
                        net_pp = round(float(last_p["score"]) - float(first_p["score"]), 1)
                        net_str = "flat, 0.0 pp" if abs(net_pp) < 0.05 else f"{net_pp:+.1f} pp net"
                        step_str = f", {chg:+.1f} pp vs {prev_lbl}" if chg is not None and len(avail_pts) >= 3 else ""
                        headline = (
                            f"Across {first_p['period']} to {last_p['period']} ({len(avail_pts)} months), "
                            f"{e_name} ({e_id}{pos_txt}) moved from {float(first_p['score']):.1f}% to "
                            f"{float(last_p['score']):.1f}% Overall PMS Score ({net_str}{step_str}; "
                            f"{period} Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}).{missing_headline_note}"
                        )
                        bullets.append(
                            "Monthly Overall PMS Score history: "
                            + ", ".join(f"{pt['period']}: {float(pt['score']):.1f}%" for pt in avail_pts)
                            + "."
                        )
                        if missing_months:
                            bullets.append(
                                f"Excluded missing evaluation periods: {', '.join(missing_months)}."
                            )
                    elif len(avail_pts) == 1:
                        only_p = avail_pts[0]
                        headline = (
                            f"Insufficient multi-month history for an overall score trend in {e_team}: "
                            f"{e_name} ({e_id}{pos_txt}) has only 1 evaluated month ({only_p['period']}: {float(only_p['score']):.1f}%, Grade {gr})."
                        )
                        bullets.append(
                            f"Only 1 evaluated month ({only_p['period']}) exists for {e_name} ({e_id}), "
                            "so a multi-month score trend cannot be established yet."
                        )
                    else:
                        headline = (
                            f"Insufficient historical evaluation data to determine a score trend for "
                            f"{e_name} ({e_id}{pos_txt}) in {e_team}."
                        )
                        bullets.append(
                            f"No multi-month score history is available in scope for {e_name} ({e_id})."
                        )
            elif signals.asks_booking_count and sp.get("ranking_metric_actual_display") and not asks_role_or_pos:
                headline = (
                    f"{e_name} recorded {sp['ranking_metric_actual_display']} in {period}."
                )
            elif signals.detected_kpi and sp.get("ranking_metric_actual_display") and not asks_role_or_pos:
                if sp.get("ranking_metric_target_display") and re.search(
                    r"\b(?:target|why|miss|missed|meet|met|benchmark|gap)\b",
                    (prompt or "").casefold(),
                ):
                    act_num = sp.get("ranking_metric_actual")
                    tgt_num = sp.get("ranking_metric_target")
                    kpi_dir = str(sp.get("ranking_metric_direction") or "higher_better")
                    tgt_disp = sp["ranking_metric_target_display"]
                    if act_num is not None and tgt_num is not None:
                        met_target = (
                            float(act_num) <= float(tgt_num)
                            if kpi_dir == "lower_better"
                            else float(act_num) >= float(tgt_num)
                        )
                        status_txt = "met the target of" if met_target else "missed the target of"
                        headline = f"{e_name}'s {rank_metric_lbl} was {sp['ranking_metric_actual_display']} in {period}, which {status_txt} {tgt_disp}."
                    else:
                        headline = f"{e_name}'s {rank_metric_lbl} was {sp['ranking_metric_actual_display']} in {period} (target {tgt_disp})."
                else:
                    headline = f"{e_name}'s {rank_metric_lbl} was {sp['ranking_metric_actual_display']} in {period}."
            else:
                if variant_idx == 1:
                    headline = (
                        f"In {period}, {e_name} ({e_id}{pos_txt}) posted {sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}){chg_txt}{six_txt}.{missing_headline_note if signals.asks_trend else ''}"
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Performance posture for {e_name} ({e_id}{pos_txt}) in {e_team} ({period}): {sc_disp} (Grade {gr}, #{rank_num} of {tot_team}){chg_txt}{six_txt}.{missing_headline_note if signals.asks_trend else ''}"
                    )
                else:
                    headline = (
                        f"{e_name} ({e_id}{pos_txt}) scored {sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}) "
                        f"in {period}{chg_txt}{six_txt}.{missing_headline_note if signals.asks_trend else ''}"
                    )

            if asks_role_or_pos and e_pos:
                bullets.append(f"Role / Position: {e_pos} in {e_team} ({period}).")
            if variant_idx in (1, 2) and has_period_score:
                detail_bullets.append(
                    f"Peer position: {e_name} ({e_id}) sits at Rank #{rank_num} of {tot_team} in {e_team} ({period}) with {sc_disp} (Grade {gr})."
                )

        # 1. Revenue guardrail note
        elif signals.asks_revenue_in_call_center:
            vols = merged.get("operational_volumes") or {}
            b_cnt = vols.get("total_bookings")
            a_cnt = vols.get("total_attended")
            c_cnt = vols.get("total_calls_handled")
            b_text = f"{int(b_cnt):,}" if b_cnt is not None and not vols.get("has_partial_evidence") else "unavailable"
            a_text = f"{int(a_cnt):,}" if a_cnt is not None else "unavailable"
            if variant_idx == 1:
                headline = (
                    f"Revenue is outside {scope} KPIs; verified operational volume in {period} ({branch}) stands at {b_text} Bookings and {a_text} Attended visits."
                )
            elif variant_idx == 2:
                headline = (
                    f"Governance guardrail: {scope} measures patient throughput ({b_text} Bookings, {a_text} Attended in {period} · {branch}) rather than financial revenue."
                )
            else:
                headline = (
                    f"{scope} tracks operational patient volume rather than financial revenue: "
                    f"{b_text} Bookings and {a_text} Attended visits in {period} ({branch})."
                )
            bullets.append(f"Total calls handled in scope: {int(c_cnt):,} calls." if c_cnt is not None else "Calls handled data is unavailable.")
            bullets.append("Financial revenue metrics are tracked under Marketing and RCM.")

        # 2. Branch comparison
        elif merged.get("branch_comparison"):
            bc = list(merged.get("branch_comparison") or [])
            req_branches = list(merged.get("requested_branches") or [])
            if len(req_branches) >= 2:
                req_set = {rb.casefold(): rb for rb in req_branches}
                bc_by_name = {str(b.get("branch") or "").casefold(): b for b in bc}
                target_bc = []
                for rb_cf, rb_orig in req_set.items():
                    if rb_cf in bc_by_name:
                        target_bc.append(bc_by_name[rb_cf])
                    else:
                        target_bc.append({
                            "branch": rb_orig.capitalize(),
                            "bookings": None,
                            "data_present": False,
                            "period_published": True,
                        })
            else:
                target_bc = list(bc[:2]) if len(bc) >= 2 else list(bc)

            asks_least = any(w in (prompt or "").casefold() for w in ("fewer", "fewest", "least", "lowest", "bottom"))
            prompt_lower_bc = (prompt or "").casefold()
            asks_bc_bookings = bool(
                signals.asks_booking_count
                or signals.detected_kpi in ("bookings_count", "TotalBookings", "Booking", "booking_rate")
                or (
                    re.search(r"\bbookings?\b", prompt_lower_bc)
                    and "attendance" not in prompt_lower_bc
                )
            )
            if asks_bc_bookings:
                valid_bc = [
                    b for b in target_bc
                    if b.get("data_present") is not False
                    and b.get("bookings") is not None
                    and b.get("status") not in ("missing", "unpublished", "no_data")
                    and b.get("period_published") is not False
                    and not b.get("has_partial_evidence")
                ]
                partial_bc = [b for b in target_bc if b.get("has_partial_evidence")]
                missing_bc = [b for b in target_bc if b not in valid_bc and b not in partial_bc]

                # 1. All missing or period unpublished
                if not valid_bc and not partial_bc:
                    branch_names = ", ".join(str(b.get("branch") or "") for b in target_bc)
                    headline = f"Booking data is missing or unpublished for {branch_names} in {period}."
                    bullets.append("No booking records were found for the requested branches in this period.")

                # 2. Partially available branch comparison (missing branches or partial evidence in some branches)
                elif missing_bc or partial_bc:
                    missing_names = ", ".join(str(b.get("branch") or "") for b in (missing_bc + partial_bc))
                    valid_details = ", ".join(
                        f"{b['branch']} recorded {int(b['bookings']):,} bookings"
                        for b in valid_bc
                    )
                    if not valid_details and partial_bc:
                        valid_details = ", ".join(
                            f"{b['branch']} recorded {int(b['bookings']):,} bookings (partial)"
                            for b in partial_bc
                        )
                    headline = (
                        f"Booking data is only partially available for {scope} in {period}: "
                        f"{valid_details}, while {missing_names} booking data is missing or unpublished. "
                        f"A complete branch winner cannot be determined without all requested branch records."
                    )
                    bullets.append(
                        "A complete branch comparison cannot be made because data is missing or incomplete for one or more requested branches."
                    )
                    bullets.append(
                        "Branch booking breakdown: "
                        + " · ".join(
                            (
                                f"{b['branch']}: {int(b['bookings']):,} bookings"
                                + (
                                    f" ({int(b['attended']):,} attended, {float(b['attendance_rate_pct']):.1f}%)"
                                    if b.get("attended") is not None and b.get("attendance_rate_pct") is not None
                                    else " (attendance unrecorded)"
                                )
                                + (" [partial data]" if b.get("has_partial_evidence") else "")
                            )
                            if b.get("bookings") is not None
                            else f"{b['branch']}: data missing or unpublished"
                            for b in target_bc
                        )
                        + "."
                    )

                # 3. All requested branches have valid recorded data
                else:
                    counts = [int(b.get("bookings") or 0) for b in valid_bc]
                    max_count = max(counts)
                    min_count = min(counts)
                    top_branches = [b for b in valid_bc if int(b.get("bookings") or 0) == max_count]
                    bottom_branches = [b for b in valid_bc if int(b.get("bookings") or 0) == min_count]
                    ranked_b = sorted(
                        valid_bc,
                        key=lambda b: int(b.get("bookings") or 0),
                        reverse=not asks_least,
                    )

                    def _join_names(names: list[str]) -> str:
                        if not names:
                            return ""
                        if len(names) == 1:
                            return names[0]
                        if len(names) == 2:
                            return f"{names[0]} and {names[1]}"
                        return ", ".join(names[:-1]) + f", and {names[-1]}"

                    def _format_others_txt(others_list: list[dict[str, Any]]) -> str:
                        if not others_list:
                            return ""
                        parts = [f"{o['branch']} with {int(o.get('bookings') or 0):,}" for o in others_list]
                        if len(parts) == 1:
                            return parts[0]
                        if len(parts) == 2:
                            return f"{parts[0]} and {parts[1]}"
                        return ", ".join(parts[:-1]) + f", and {parts[-1]}"

                    # Subcase 3.1: All branches tied with same count (including all zero!)
                    if len(top_branches) == len(valid_bc):
                        val = max_count
                        branch_names = _join_names([b["branch"] for b in valid_bc])
                        headline = f"In {period}, {branch_names} tied with {val:,} bookings each for {scope}."

                    # Subcase 3.2: Highest / Most / General comparison (not asks_least)
                    elif not asks_least:
                        # Tie for first place
                        if len(top_branches) > 1:
                            top_names = _join_names([b["branch"] for b in top_branches])
                            others = [b for b in ranked_b if b not in top_branches]
                            others_txt = _format_others_txt(others)
                            headline = (
                                f"In {period}, {top_names} tied for the most {scope} bookings with "
                                f"{max_count:,} each, followed by {others_txt}."
                            )
                        else:
                            winner = top_branches[0]
                            others = [b for b in ranked_b if b != winner]
                            # Check if remaining branches are tied for lowest
                            if len(others) >= 2 and all(int(o.get("bookings") or 0) == min_count for o in others):
                                bottom_names = _join_names([b["branch"] for b in others])
                                headline = (
                                    f"{winner['branch']} led {period} {scope} bookings with "
                                    f"{int(winner.get('bookings') or 0):,}, followed by a tie between "
                                    f"{bottom_names} with {min_count:,} each."
                                )
                            else:
                                others_txt = _format_others_txt(others)
                                if variant_idx == 1:
                                    headline = (
                                        f"Booking volume concentration in {period} ({scope}): {winner['branch']} recorded the highest volume at {int(winner.get('bookings') or 0):,}, ahead of {others_txt}."
                                    )
                                elif variant_idx == 2:
                                    headline = (
                                        f"Branch volume ranking for {scope} in {period}: {winner['branch']} tops the comparison with {int(winner.get('bookings') or 0):,} bookings, followed by {others_txt}."
                                    )
                                else:
                                    headline = (
                                        f"{winner['branch']} led {period} {scope} bookings with "
                                        f"{int(winner.get('bookings') or 0):,}, followed by {others_txt}."
                                    )

                    # Subcase 3.3: Fewest / Lowest comparison (asks_least is True)
                    else:
                        # Tie for lowest place
                        if len(bottom_branches) > 1:
                            bottom_names = _join_names([b["branch"] for b in bottom_branches])
                            others = [b for b in ranked_b if b not in bottom_branches]
                            others_txt = _format_others_txt(others)
                            headline = (
                                f"In {period}, {bottom_names} tied for the fewest {scope} bookings with "
                                f"{min_count:,} each, while {others_txt}."
                            )
                        else:
                            least_branch = bottom_branches[0]
                            others = [b for b in ranked_b if b != least_branch]
                            if len(others) >= 2 and all(int(o.get("bookings") or 0) == max_count for o in others):
                                top_names = _join_names([b["branch"] for b in others])
                                headline = (
                                    f"{least_branch['branch']} had the fewest {period} {scope} bookings with "
                                    f"{int(least_branch.get('bookings') or 0):,}, while {top_names} tied with {max_count:,} each."
                                )
                            else:
                                others_txt = _format_others_txt(others)
                                if variant_idx == 1:
                                    headline = (
                                        f"Lowest {scope} booking intake in {period} occurred in {least_branch['branch']} ({int(least_branch.get('bookings') or 0):,}), trailing {others_txt}."
                                    )
                                elif variant_idx == 2:
                                    headline = (
                                        f"Across {period} {scope} branches, {least_branch['branch']} posted the smallest booking count at {int(least_branch.get('bookings') or 0):,}, compared with {others_txt}."
                                    )
                                else:
                                    headline = (
                                        f"{least_branch['branch']} had the fewest {period} {scope} bookings with "
                                        f"{int(least_branch.get('bookings') or 0):,}, followed by {others_txt}."
                                    )

                    bullets.append(
                        "Branch booking breakdown: "
                        + " · ".join(
                            (
                                f"{b['branch']}: {int(b.get('bookings') or 0):,} bookings"
                                + (
                                    f" ({int(b.get('attended') or 0):,} attended, {float(b.get('attendance_rate_pct') or 0.0):.1f}%)"
                                    if b.get("attended") is not None and b.get("attendance_rate_pct") is not None
                                    else " (attendance unrecorded)"
                                )
                            )
                            for b in ranked_b
                        )
                        + "."
                    )
            elif len(target_bc) >= 3:
                valid_scores = [b for b in target_bc if b.get("score") is not None]
                missing_scores = [b for b in target_bc if b.get("score") is None]
                if not valid_scores:
                    branch_names = ", ".join(b["branch"] for b in target_bc)
                    headline = f"Performance score data is missing or unpublished for {branch_names} in {period}."
                elif missing_scores:
                    missing_names = ", ".join(b["branch"] for b in missing_scores)
                    valid_txt = ", ".join(f"{b['branch']} at {b['score']:.1f}%" for b in valid_scores)
                    headline = f"In {period}, score data is only partially available for {scope}: {valid_txt}, while score data for {missing_names} is unavailable or unpublished."
                else:
                    ranked_b = sorted(
                        valid_scores,
                        key=lambda b: float(b["score"]),
                        reverse=not asks_least,
                    )
                    winner = ranked_b[0]
                    others_txt = ", ".join(f"{o['branch']} at {float(o['score']):.1f}%" for o in ranked_b[1:])
                    if variant_idx == 1:
                        headline = (
                            f"Branch gap alert for {scope} in {period}: {winner['branch']} stands at {float(winner['score']):.1f}%, while {others_txt}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Multi-branch benchmark in {period} ({scope}): {winner['branch']} ranks first at {float(winner['score']):.1f}% ahead of {others_txt}."
                        )
                    else:
                        headline = (
                            f"In {period}, {winner['branch']} leads {scope} at {float(winner['score']):.1f}%, "
                            f"followed by {others_txt}."
                        )
            elif len(target_bc) < 2:
                headline = f"A branch comparison requires at least two accessible branches for {scope} in {period}."
            else:
                b1, b2 = target_bc[0], target_bc[1]
                s1, s2 = b1.get("score"), b2.get("score")
                if s1 is None and s2 is None:
                    headline = f"Performance score data is missing or unpublished for {b1['branch']} and {b2['branch']} in {period}."
                elif s1 is None or s2 is None:
                    avail_b = b1 if s1 is not None else b2
                    unavail_b = b2 if s1 is not None else b1
                    headline = f"In {period}, {avail_b['branch']} recorded {avail_b['score']:.1f}%, while score data for {unavail_b['branch']} is unavailable or unpublished."
                else:
                    diff = round(float(s1) - float(s2), 1)
                    leader = b1 if diff >= 0 else b2
                    lagger = b2 if diff >= 0 else b1
                    with_vol = [b for b in target_bc if int(b.get("bookings") or 0) > 0 and b.get("no_shows") is not None and b.get("attendance_rate_pct") is not None and not b.get("has_partial_evidence")]
                    most_noshows = max(with_vol, key=lambda b: int(b.get("no_shows") or 0)) if with_vol else None
                    if variant_idx == 1:
                        headline = (
                            f"{scope} branch scores in {period}: {lagger['branch']} trails {leader['branch']} by {abs(diff):.1f} pts ({lagger['score']:.1f}% vs {leader['score']:.1f}%)."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"{scope} branch scores in {period}: {leader['branch']} holds {leader['score']:.1f}% against {lagger['branch']} at {lagger['score']:.1f}%—a {abs(diff):.1f}-pt spread."
                        )
                    else:
                        headline = (
                            f"For {scope} in {period}, {leader['branch']} leads at {leader['score']:.1f}% vs. "
                            f"{lagger['branch']} at {lagger['score']:.1f}% ({abs(diff):.1f} pts gap)."
                        )
                    if most_noshows:
                        bullets.append(
                            f"{most_noshows['branch']} holds the largest No-Show volume ({most_noshows['no_shows']:,} missed visits out of "
                            f"{most_noshows['bookings']:,} bookings · {most_noshows['attendance_rate_pct']:.1f}% Attended)."
                        )

        # 2b. Threshold Employee Count Summary
        elif merged.get("threshold_count_summary"):
            tcs = merged["threshold_count_summary"]
            cnt = int(tcs.get("count") or 0)
            tot = int(tcs.get("total_evaluated") or 0)
            op_lbl = str(tcs.get("operator_label") or "above")
            thr = tcs.get("threshold")
            thr_txt = f"{thr:g}%" if thr is not None else ""
            t_team = str(tcs.get("team") or scope)
            t_period = str(tcs.get("period") or period)
            q_emps = tcs.get("qualifying_employees") or []
            emp_word = "employee" if cnt == 1 else "employees"
            if tot == 0:
                headline = f"No published PMS evaluation records matched {t_team} in {t_period}."
            elif q_emps:
                names_txt = ", ".join(f"{e['employee_name']} ({e['score']:.1f}%)" for e in q_emps[:10])
                headline = f"In {t_team} ({t_period}), {cnt} of {tot} evaluated {emp_word} scored {op_lbl} {thr_txt}: {names_txt}."
            else:
                headline = f"In {t_team} ({t_period}), 0 of {tot} evaluated employees scored {op_lbl} {thr_txt}."
            for e in q_emps[:5]:
                bullets.append(f"{e['employee_name']} ({e['employee_id']}): {e['score']:.1f}%.")

        # 3. Root-cause employees (People Contribution — when user explicitly asks who/employees or no KPI diagnosis is active)
        elif merged.get("top_contributors") and (
            any(
                w in (prompt or "").casefold()
                for w in ("who", "employee", "employees", "agent", "agents", "person", "people", "contributors")
            )
            or (not merged.get("requested_kpi") and not merged.get("lowest_kpi"))
        ):
            top_list = merged["top_contributors"]
            first = top_list[0]
            neg_cnt = merged.get("negative_contributors", len(top_list))
            tot_cnt = merged.get("total_employees", len(top_list))
            kpi_name = merged.get("kpi_analyzed") or "Overall Performance"
            pareto = merged.get("pareto_summary") or {}
            p_share = float(pareto.get("top3_pareto_share_pct") or 0.0)
            p_top3_pts = float(pareto.get("top3_negative_impact_pts") or 0.0)
            p_tot_pts = float(pareto.get("total_negative_impact_pts") or 0.0)
            if variant_idx == 1:
                headline = (
                    f"Risk concentration on {kpi_name} ({period} · {branch}): {neg_cnt} of {tot_cnt} employees missed target, led by {first['employee_name']} ({first.get('weighted_impact') or 0:+.2f} pts)."
                )
            elif variant_idx == 2:
                headline = (
                    f"Coaching focus for {kpi_name} in {period} ({branch}): lifting {first['employee_name']} ({first.get('weighted_impact') or 0:+.2f} pts) addresses the steepest gap across {neg_cnt} of {tot_cnt} below-target records."
                )
            else:
                headline = (
                    f"{neg_cnt} of {tot_cnt} employees are below target on {kpi_name} in {period} ({branch}). "
                    f"{first['employee_name']} drives the largest negative impact ({first.get('weighted_impact') or 0:+.2f} pts)."
                )
            if p_tot_pts > 0 and signals.asks_decisions_or_what_if:
                bullets.append(
                    f"Pareto Concentration: The top 3 below-target agents account for {p_share:.0f}% of the total weighted loss "
                    f"(-{p_top3_pts:.2f} pts of -{p_tot_pts:.2f} pts), and coaching them to target recovers +{p_top3_pts:.2f} pts."
                )

        # 4. Employee Multi-Month History
        elif merged.get("history") is not None:
            hist = merged.get("history") or []
            emp_name = merged.get("employee_name") or "Employee"
            if hist:
                latest = hist[-1]
                earliest = hist[0]
                delta = round(float(latest["score"]) - float(earliest["score"]), 1)
                if variant_idx == 1:
                    headline = (
                        f"Over {len(hist)} evaluated months, {emp_name} moved {delta:+.1f} pp from {earliest['period']} to finish at {latest['score']:.1f}% in {latest['period']}."
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Longitudinal posture for {emp_name}: {latest['score']:.1f}% in {latest['period']} ({delta:+.1f} pp since {earliest['period']} across {len(hist)} months)."
                    )
                else:
                    headline = (
                        f"{emp_name} scored {latest['score']:.1f}% in {latest['period']} across {len(hist)} tracked months "
                        f"({delta:+.1f} pp vs. {earliest['period']})."
                    )
            else:
                headline = f"No evaluation records matched '{emp_name}' within your authorized scope."

        # 5. Corrective Actions
        elif "total_actions" in merged:
            tot_act = merged.get("total_actions", 0)
            acts = merged.get("actions") or []
            emp_filter = merged.get("employee_filter")
            emp_ctx = merged.get("employee_context") or {}
            other_acts = merged.get("other_period_actions") or []
            period_clause = f" for {period}" if period and period != "the active period" else ""

            if emp_filter:
                if tot_act == 0:
                    headline = f"No saved corrective action has been recorded for {emp_filter}{period_clause} yet."
                    if other_acts:
                        prev_list = "; ".join(
                            f"{a.get('month') or ''} {a.get('year') or ''} ({a.get('status') or 'Open'}: {a.get('action_text') or a.get('action_type') or 'Action'})".strip()
                            for a in other_acts[:2]
                        )
                        bullets.append(f"Prior saved actions found in other periods: {prev_list}.")
                    else:
                        bullets.append(
                            "Any action shown as 'Suggested — not saved' on the review page is a recommendation only and has not been saved to PMS."
                        )
                    if emp_ctx.get("score") is not None:
                        gr_txt = f" ({emp_ctx['grade']})" if emp_ctx.get("grade") else ""
                        drags = emp_ctx.get("top_drags") or []
                        drag_txt = (
                            " · Primary KPI drag: "
                            + ", ".join(
                                f"{d['label']} at {d['actual']}" + (f" vs {d['target']} target" if d.get("target") else "")
                                for d in drags[:2]
                            )
                            if drags
                            else ""
                        )
                        bullets.append(
                            f"Current scorecard context ({emp_ctx.get('period') or period}): {float(emp_ctx['score']):.1f}%{gr_txt}{drag_txt}."
                        )
                else:
                    noun = "saved corrective action" if tot_act == 1 else "saved corrective actions"
                    headline = f"{tot_act} {noun} recorded for {emp_filter}{period_clause}."
                    for a in acts[:3]:
                        due_part = f" · Due {a['due_date']}" if a.get("due_date") else ""
                        owner_part = f" · Owner: {a['owner']}" if a.get("owner") else ""
                        txt_part = f" — {a['action_text']}" if a.get("action_text") else ""
                        bullets.append(
                            f"{a.get('action_type') or 'Action'} ({a.get('status') or 'Open'}{due_part}{owner_part}){txt_part}"
                        )
            else:
                if merged.get("open_actions_only"):
                    headline = f"{tot_act} open corrective {'action' if tot_act == 1 else 'actions'} for {scope} in {period}."
                elif variant_idx == 1:
                    headline = f"Governance queue for {scope}: {tot_act} corrective actions require tracking across active follow-up states."
                elif variant_idx == 2:
                    headline = f"Action posture in {scope}: {tot_act} tracked corrective actions are currently logged for manager follow-up."
                else:
                    headline = f"{tot_act} corrective actions are currently tracked for {scope}."
                for a in acts[:3]:
                    bullets.append(
                        f"{a.get('employee_name')} ({a.get('team')}): {a.get('action_type')} — {a.get('status')} ({a.get('follow_up_state')})."
                    )

        # 6. Managerial / Corporate BSC
        elif merged.get("bsc_kpis") or merged.get("guardrail"):
            if merged.get("guardrail"):
                headline = merged["guardrail"]
            else:
                lvl = merged.get("level", "Managerial")
                t_name = merged.get("team", "Inbound")
                avg_bsc = merged.get("average_score")
                if isinstance(avg_bsc, (int, float)):
                    if variant_idx == 1:
                        headline = f"{t_name} {lvl} Balanced Scorecard stands at {float(avg_bsc):.1f}% in {period} across 4 weighted perspectives."
                    elif variant_idx == 2:
                        headline = f"Strategic benchmark for {t_name} ({lvl} BSC) in {period}: {float(avg_bsc):.1f}% across 4 perspectives."
                    else:
                        headline = f"{t_name} {lvl} Balanced Scorecard scored {float(avg_bsc):.1f}% in {period} across 4 strategic perspectives."
                else:
                    headline = f"{t_name} {lvl} Balanced Scorecard is structured across 4 strategic perspectives."
                bsc_rows = merged.get("bsc_kpis") or []
                scored_bsc = [r for r in bsc_rows if float(r.get("weight_percent") or 0.0) > 0]
                if scored_bsc:
                    top_labels = ", ".join(
                        f"{r.get('label')} ({r.get('weight_percent'):.0f}%)"
                        + (f" — {r.get('actual_display')} vs {r.get('target_display')}" if r.get("actual_display") else "")
                        for r in scored_bsc[:3]
                    )
                    bullets.append(f"Key {lvl} BSC KPIs: {top_labels}.")

        # 7. Team / KPI Diagnosis Summary
        else:
            worst = merged.get("worst_team")
            lowest_kpi = merged.get("lowest_kpi")
            requested_kpi = merged.get("requested_kpi")
            period_comp = merged.get("period_comparison")
            avg_score = merged.get("average_score")
            score_change = merged.get("score_change")
            below_cnt = merged.get("employees_below_target", 0)
            tot_rec = merged.get("total_records", 0)

            if period_comp:
                p_from = period_comp.get("from_period", "Prior Period")
                p_to = period_comp.get("to_period", period)
                s_from = period_comp.get("from_score")
                s_to = period_comp.get("to_score", avg_score)
                delta = period_comp.get("delta", score_change)
                delta_txt = f" ({delta:+.1f} pp change)" if delta is not None else ""
                if s_from is not None and s_to is not None:
                    if variant_idx == 1:
                        headline = (
                            f"Period-over-period shift for {scope} ({branch}): {s_to:.1f}% in {p_to} vs {s_from:.1f}% in {p_from}{delta_txt}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Comparing {p_from} to {p_to}, {scope} ({branch}) transitioned from {s_from:.1f}% to {s_to:.1f}%{delta_txt}."
                        )
                    else:
                        headline = (
                            f"{scope} ({branch}) moved from {s_from:.1f}% in {p_from} to {s_to:.1f}% in {p_to}{delta_txt}."
                        )
                else:
                    headline = (
                        f"Comparing {scope} ({branch}) across {p_from} and {p_to}: latest score is {(s_to or 0.0):.1f}%{delta_txt}."
                    )
            elif requested_kpi:
                if requested_kpi.get("single_published_sample"):
                    headline = (
                        f"{requested_kpi['kpi_label']} for {scope} in {period} was "
                        f"{requested_kpi['actual_display']} from one published record."
                    )
                elif requested_kpi.get("kpi_key") in (
                    "bookings_count",
                    "TotalBookings",
                    "attended_count",
                    "AttendedPatients",
                    "handled_calls_count",
                    "HandledCalls",
                    "abandoned_calls_count",
                    "AbandonedCalls",
                ):
                    if variant_idx == 1:
                        headline = (
                            f"Operational count for {scope} ({period} · {branch}): {requested_kpi['kpi_label']} totaled {requested_kpi['actual_display']}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Volume benchmark in {scope} ({period} · {branch}): {requested_kpi['actual_display']} recorded for {requested_kpi['kpi_label']}."
                        )
                    else:
                        headline = (
                            f"In {scope} ({period} · {branch}), {requested_kpi['kpi_label']} reached "
                            f"{requested_kpi['actual_display']}."
                        )
                    if requested_kpi.get("tracking_only_note"):
                        bullets.append(str(requested_kpi["tracking_only_note"]))
                elif requested_kpi.get("contributes_to_score") is False:
                    if variant_idx == 1:
                        headline = (
                            f"{requested_kpi['kpi_label']} in {scope} ({period} · {branch}) carries 0% score weight and serves as a diagnostic volume indicator."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Diagnostic indicator check for {scope} ({period} · {branch}): {requested_kpi['kpi_label']} is tracking-only (0% weight) and excluded from the weighted PMS score."
                        )
                    else:
                        headline = (
                            f"In {scope} ({period} · {branch}), {requested_kpi['kpi_label']} is a tracking-only indicator "
                            f"(0% score weight) and does not affect the weighted PMS score."
                        )
                    if requested_kpi.get("tracking_only_note"):
                        bullets.append(str(requested_kpi["tracking_only_note"]))
                else:
                    ach_val = requested_kpi.get("achievement_percent")
                    ach_txt = f"{ach_val:.1f}% achievement" if ach_val is not None else "tracked"
                    below_kpi_cnt = int(requested_kpi.get("people_below_target") or 0)
                    below_kpi_note = (
                        f", with {below_kpi_cnt} agents below target"
                        if below_kpi_cnt > 0
                        else ""
                    )
                    if variant_idx == 1:
                        headline = (
                            f"Driver check for {requested_kpi['kpi_label']} in {scope} ({period} · {branch}): actual {requested_kpi['actual_display']} vs target {requested_kpi['target_display']} delivers {ach_txt} ({requested_kpi.get('weight_percent') or 0:.0f}% weight){below_kpi_note}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Target posture on {requested_kpi['kpi_label']} ({scope} · {period} · {branch}): {ach_txt} at {requested_kpi['actual_display']} against {requested_kpi['target_display']} ({requested_kpi.get('weight_percent') or 0:.0f}% weight){below_kpi_note}."
                        )
                    else:
                        headline = (
                            f"In {scope} ({period} · {branch}), {requested_kpi['kpi_label']} is at {requested_kpi['actual_display']} "
                            f"vs target {requested_kpi['target_display']} ({ach_txt}, {requested_kpi.get('weight_percent') or 0:.0f}% weight){below_kpi_note}."
                        )
                    if merged.get("top_contributors"):
                        top_c = merged["top_contributors"]
                        neg_c = merged.get("negative_contributors", len(top_c))
                        tot_c = merged.get("total_employees", len(top_c))
                        top_names = ", ".join(
                            f"{c['employee_name']} ({c.get('weighted_impact') or 0:+.2f} pts)"
                            for c in top_c[:3]
                        )
                        bullets.append(
                            f"Contributing factors on {requested_kpi['kpi_label']}: {neg_c} of {tot_c} employees are below target, led by {top_names}."
                        )
            elif signals.asks_average_overall_score:
                if avg_score is not None:
                    employee_label = "employee" if tot_rec == 1 else "employees"
                    coverage = f" across {tot_rec} evaluated {employee_label}" if tot_rec else ""
                    headline = f"{scope} averaged {avg_score:.1f}% in {period}{coverage}."
                else:
                    headline = f"Overall PMS score is not available for {scope} in {period} ({branch})."
            elif worst and avg_score is not None:
                w_score = worst.get("current_score") or 0.0
                w_change = worst.get("score_change")
                change_txt_en = f" ({w_change:+.1f} pts vs prior month)" if w_change is not None else ""
                w_impacted = int(worst.get("impacted_employees", below_cnt) or 0)
                w_total = int(worst.get("total_employees", tot_rec) or 0)
                teams_list = merged.get("teams") or []
                is_multi_team = int(merged.get("total_teams") or len(teams_list)) > 1 or (
                    tot_rec > w_total and w_total > 0
                )
                if w_impacted > 0 and w_total > 0:
                    agent_impact_clause = f", with {w_impacted} of {w_total} agents below target"
                elif w_total > 0:
                    agent_unit = "agent" if w_total == 1 else "agents"
                    agent_impact_clause = f" ({w_total} evaluated {agent_unit})"
                else:
                    agent_impact_clause = ""

                if is_multi_team:
                    overall_delta = (
                        f" ({score_change:+.1f} pts vs prior month)"
                        if score_change is not None
                        else ""
                    )
                    emp_unit = "employee" if tot_rec == 1 else "employees"
                    if variant_idx == 1:
                        headline = (
                            f"Overall performance in {period} ({branch}) stands at {avg_score:.1f}%{overall_delta} across {tot_rec} evaluated {emp_unit}; "
                            f"primary attention area is {worst['team']} trailing at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Executive pulse for {period} ({branch}): {avg_score:.1f}%{overall_delta} average across {tot_rec} {emp_unit}, "
                            f"while {worst['team']} has the lowest score at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                    else:
                        headline = (
                            f"Overall performance in {period} ({branch}) averages {avg_score:.1f}%{overall_delta} across {tot_rec} evaluated {emp_unit}; "
                            f"{worst['team']} has the lowest score at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                else:
                    raw_scope_label = str(merged.get("scope") or "").strip()
                    if " · " in raw_scope_label:
                        headline = (
                            f"In {period} ({branch}), {raw_scope_label} scored {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                    elif variant_idx == 1:
                        headline = (
                            f"Primary risk area in {period} ({branch}): {worst['team']} trails at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                    elif variant_idx == 2:
                        headline = (
                            f"Coaching attention in {period} ({branch}) centers on {worst['team']} at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                    else:
                        headline = (
                            f"In {period} ({branch}), {worst['team']} has the lowest score at {w_score:.1f}%{change_txt_en}{agent_impact_clause}."
                        )
                if is_multi_team and merged.get("best_team"):
                    best_team_data = merged["best_team"]
                    b_score = best_team_data.get("current_score") or 0.0
                    b_change = best_team_data.get("score_change")
                    b_change_txt = f" ({b_change:+.1f} pts vs prior month)" if b_change is not None else ""
                    bullets.append(f"Top performing department: {best_team_data['team']} leads at {b_score:.1f}%{b_change_txt}.")
                if worst.get("main_cause"):
                    bullets.append(f"Primary score driver in {worst['team']}: {worst['main_cause']}.")
            elif lowest_kpi:
                below_low_cnt = int(lowest_kpi.get("people_below_target") or 0)
                below_low_note = f", {below_low_cnt} agents below target" if below_low_cnt > 0 else ""
                if variant_idx == 1:
                    headline = (
                        f"Biggest score drag in {scope} ({period} · {branch}): {lowest_kpi['kpi_label']} achieved {lowest_kpi.get('achievement_percent') or 0:.1f}% ({lowest_kpi['actual_display']} vs target {lowest_kpi['target_display']}{below_low_note})."
                    )
                elif variant_idx == 2:
                    headline = (
                        f"Priority KPI recovery target for {scope} ({period} · {branch}): closing {lowest_kpi['kpi_label']} from {lowest_kpi['actual_display']} toward {lowest_kpi['target_display']} ({lowest_kpi.get('achievement_percent') or 0:.1f}% achievement{below_low_note})."
                    )
                else:
                    headline = (
                        f"The primary KPI bottleneck in {scope} ({period} · {branch}) is {lowest_kpi['kpi_label']} "
                        f"at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['actual_display']} vs target {lowest_kpi['target_display']}{below_low_note})."
                    )
                if merged.get("top_contributors"):
                    top_c = merged["top_contributors"]
                    neg_c = merged.get("negative_contributors", len(top_c))
                    tot_c = merged.get("total_employees", len(top_c))
                    top_names = ", ".join(
                        f"{c['employee_name']} ({c.get('weighted_impact') or 0:+.2f} pts)"
                        for c in top_c[:3]
                    )
                    bullets.append(
                        f"Contributing factors on {lowest_kpi['kpi_label']}: {neg_c} of {tot_c} employees are below target, led by {top_names}."
                    )
            elif avg_score is not None:
                delta_str = f" ({score_change:+.1f} pp)" if score_change is not None else ""
                if variant_idx == 1:
                    headline = f"Across {tot_rec} evaluated records in {period} ({branch}), {scope} stands at {avg_score:.1f}%{delta_str}."
                elif variant_idx == 2:
                    headline = f"Overall benchmark for {scope} in {period} ({branch}): {avg_score:.1f}%{delta_str} over {tot_rec} evaluated records."
                else:
                    headline = f"{scope} average performance in {period} ({branch}) is {avg_score:.1f}%{delta_str} across {tot_rec} evaluated records."
            else:
                reg_note = f" · {merged['region']}" if merged.get("region") else ""
                branch_note = f" · {branch}" if branch and branch not in ("All Branches", "all", "All") else ""
                headline = f"No performance records matched the selected filters ({scope}{reg_note} · {period}{branch_note})."

            if lowest_kpi and (
                worst
                or (
                    requested_kpi
                    and str(requested_kpi.get("kpi_key") or "").casefold()
                    != str(lowest_kpi.get("kpi_key") or "").casefold()
                )
            ):
                bullets.append(
                    f"Lowest KPI: {lowest_kpi['kpi_label']} (Weight {lowest_kpi['weight_percent']:.0f}%) at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['people_below_target']} agents below target)."
                )

        followups = _build_dynamic_followups(
            prompt=prompt,
            history=history,
            scope=str(scope),
            branch=str(branch),
            period=str(period),
            merged=merged,
            variant_idx=variant_idx,
            session_state=session_state,
        )

        return NarrativeSynthesisResult(
            headline=headline,
            narrative_bullets=bullets[:5] if merged.get("query_rankings") else bullets[:4],
            suggested_followups=followups,
            provider_used=self.provider_name,
            model_used=self.model_name,
            metrics=ProviderCallMetrics(
                provider_used=self.provider_name,
                model_used=self.model_name,
                provider_calls=0,
            ),
            detail_bullets=detail_bullets[:4],
        )


# ---------------------------------------------------------------------------
# Unified provider engine exports
# ---------------------------------------------------------------------------
from services.ai.provider_engine import (  # noqa: E402
    CloudflareAIProviderAdapter,
    NvidiaProviderAdapter,
    ProviderAttempt,
    ProviderError,
    ProviderMessage,
    ProviderNonRetryableError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderResponse,
    ProviderTimeoutError,
    ProviderTransientError,
    TokenUsage,
    UnifiedProviderConfig,
    UnifiedProviderEngine,
    estimate_cost_usd,
    get_unified_provider_engine,
    load_unified_provider_config,
)

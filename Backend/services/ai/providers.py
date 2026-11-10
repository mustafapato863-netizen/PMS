from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from models.ai_schemas import StructuredQueryPlan
from services.ai.config import get_ai_runtime_config, redact_secrets
from services.ai.domain_policies import ParsedPromptSignals
from services.ai.trace_logger import sanitize_prompt_for_router_training

logger = logging.getLogger(__name__)

# Gemini 2.5 Flash reference pricing per token ($0.15 / 1M input, $0.60 / 1M output)
GEMINI_FLASH_INPUT_USD_PER_TOKEN = 0.15 / 1_000_000.0
GEMINI_FLASH_OUTPUT_USD_PER_TOKEN = 0.60 / 1_000_000.0

_UNSAFE_TABULAR_RE = re.compile(r"(?:\t[^\t]+\t[^\t]+|\n[^\n]+\|[^\n]+\|)")


class ProviderUnavailableError(RuntimeError):
    """Raised when an external provider fails and no safe local fallback or clarification is available."""


@dataclass
class ProviderCallMetrics:
    provider_used: str = "deterministic"
    model_used: str = "pms-local-router-v1"
    provider_calls: int = 0
    provider_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    fallback_outcome: str = "none"
    outbound_payload: dict[str, Any] | None = None


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
    """Build a strictly minimized, PII-free payload for Gemini structured intent routing.
    Never includes workbook contents, employee records, private KPI values, or conversation transcripts.
    """
    sanitized_question = sanitize_prompt_for_router_training(
        prompt, known_employee_names=known_employee_names
    )
    compact_view = {
        "function": current_view.get("function") or "Call Center",
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


def _estimate_tokens(text: str) -> int:
    return max(1, int(round(len(text or "") / 4.0)))


class GeminiStructuredRouterAdapter:
    """Calls Gemini structured output API with x-goog-api-key header and minimized metadata."""

    def propose_query_plan(
        self,
        *,
        prompt: str,
        current_view: dict[str, Any],
        candidate_teams: list[str],
        candidate_metrics: list[str],
        candidate_branches: list[str],
        known_employee_names: list[str] | None = None,
    ) -> StructuredRoutingProviderResult:
        cfg = get_ai_runtime_config()
        scope_key = str(current_view.get("team") or current_view.get("function") or "call center")

        if not cfg.gemini_routing_enabled:
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(fallback_outcome="cloud_disabled"),
            )
        if not cfg.is_scope_allowed_for_cloud(scope_key):
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(fallback_outcome="scope_not_allowed"),
            )
        if not is_prompt_safe_for_external_projection(prompt):
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(fallback_outcome="unsafe_prompt"),
            )
        if not cfg.gemini_api_key:
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(fallback_outcome="missing_api_key"),
            )

        minimized_input = build_minimized_routing_payload(
            prompt=prompt,
            current_view=current_view,
            candidate_teams=candidate_teams,
            candidate_metrics=candidate_metrics,
            candidate_branches=candidate_branches,
            known_employee_names=known_employee_names,
        )

        system_instruction = (
            "You are the PMS AI query router. Convert the manager's English question and current view "
            "into a JSON object matching StructuredQueryPlan. "
            "Allowed intents: current_value, actual_vs_target, compare_periods, compare_branches, "
            "compare_teams, trend, ranking, score_drivers, scorecard_structure, corrective_actions, "
            "clarify, unsupported. "
            "Allowed clarification_code values: NONE, AMBIGUOUS_ABANDON_METRIC, "
            "AMBIGUOUS_ATTENDANCE_DEFINITION, AMBIGUOUS_TEAM_SCOPE, AMBIGUOUS_KPI_SCOPE, "
            "MISSING_COMPARISON_PERIOD, RESTRICTED_SCOPE_SUGGESTION, UNAVAILABLE_PERIOD_SUGGESTION. "
            "Return ONLY valid JSON."
        )

        candidate_models = [m.strip() for m in cfg.gemini_model.split(",") if m.strip()] or ["gemini-2.5-flash"]
        user_text = json.dumps(minimized_input, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "intent": {"type": "STRING"},
                        "requested_parts": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "team": {"type": "STRING", "nullable": True},
                        "function": {"type": "STRING", "nullable": True},
                        "position": {"type": "STRING", "nullable": True},
                        "branch": {"type": "STRING", "nullable": True},
                        "compare_branch": {"type": "STRING", "nullable": True},
                        "performance_level": {"type": "STRING"},
                        "metric": {"type": "STRING", "nullable": True},
                        "periods": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "ranking_direction": {"type": "STRING", "enum": ["best", "worst"]},
                        "single_person": {"type": "BOOLEAN"},
                        "clarification_code": {"type": "STRING"},
                    },
                    "required": ["intent", "performance_level", "clarification_code"],
                },
            },
        }
        encoded_payload = json.dumps(payload).encode("utf-8")

        last_result: StructuredRoutingProviderResult | None = None
        calls_made = 0
        t_start = time.perf_counter()

        for model_name in candidate_models:
            calls_made += 1
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            req = urllib.request.Request(
                url,
                data=encoded_payload,
                headers={
                    "Content-Type": "application/json",
                    "x-goog-api-key": cfg.gemini_api_key,
                },
                method="POST",
            )

            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=cfg.provider_timeout_seconds) as resp:
                    raw_body = resp.read().decode("utf-8")
                elapsed_ms = round((time.perf_counter() - t_start) * 1000.0, 2)
                body = json.loads(raw_body)
                usage = body.get("usageMetadata") or {}
                in_tok = int(usage.get("promptTokenCount") or _estimate_tokens(system_instruction + user_text))
                out_tok = int(usage.get("candidatesTokenCount") or _estimate_tokens(raw_body))
                cost_usd = round(
                    in_tok * GEMINI_FLASH_INPUT_USD_PER_TOKEN + out_tok * GEMINI_FLASH_OUTPUT_USD_PER_TOKEN,
                    8,
                )
                text_out = body["candidates"][0]["content"]["parts"][0]["text"]
                parsed_dict = json.loads(text_out)
                if isinstance(parsed_dict, dict):
                    if str(parsed_dict.get("ranking_direction") or "").strip().casefold() not in ("best", "worst"):
                        parsed_dict["ranking_direction"] = "best"
                    else:
                        parsed_dict["ranking_direction"] = str(parsed_dict["ranking_direction"]).strip().casefold()
                    if not parsed_dict.get("clarification_code"):
                        parsed_dict["clarification_code"] = "NONE"
                plan = StructuredQueryPlan.model_validate(parsed_dict)
                return StructuredRoutingProviderResult(
                    plan=plan,
                    metrics=ProviderCallMetrics(
                        provider_used="gemini",
                        model_used=model_name,
                        provider_calls=calls_made,
                        provider_ms=elapsed_ms,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        estimated_cost_usd=cost_usd,
                        fallback_outcome="none",
                        outbound_payload=minimized_input,
                    ),
                )
            except TimeoutError as exc:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                logger.warning("Gemini router (%s) timed out after %.1f ms", model_name, elapsed_ms)
                return StructuredRoutingProviderResult(
                    plan=None,
                    metrics=ProviderCallMetrics(
                        provider_used="gemini",
                        model_used=model_name,
                        provider_calls=calls_made,
                        provider_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
                        fallback_outcome="timeout",
                        outbound_payload=minimized_input,
                    ),
                    error_detail=redact_secrets(str(exc)),
                )
            except (json.JSONDecodeError, KeyError, ValueError) as exc:
                logger.warning("Gemini router (%s) returned invalid structured output: %s", model_name, redact_secrets(str(exc)))
                return StructuredRoutingProviderResult(
                    plan=None,
                    metrics=ProviderCallMetrics(
                        provider_used="gemini",
                        model_used=model_name,
                        provider_calls=calls_made,
                        provider_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
                        fallback_outcome="invalid_json",
                        outbound_payload=minimized_input,
                    ),
                    error_detail=redact_secrets(str(exc)),
                )
            except Exception as exc:
                outcome = "timeout" if "timed out" in str(exc).casefold() else "http_error"
                logger.warning("Gemini router (%s) request failed (%s): %s", model_name, outcome, redact_secrets(str(exc)))
                last_result = StructuredRoutingProviderResult(
                    plan=None,
                    metrics=ProviderCallMetrics(
                        provider_used="gemini",
                        model_used=model_name,
                        provider_calls=calls_made,
                        provider_ms=round((time.perf_counter() - t_start) * 1000.0, 2),
                        fallback_outcome=outcome,
                        outbound_payload=minimized_input,
                    ),
                    error_detail=redact_secrets(str(exc)),
                )
                http_code = getattr(exc, "code", None)
                if http_code not in (429, 500, 502, 503, 504):
                    return last_result

        return last_result or StructuredRoutingProviderResult(plan=None)


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
    ) -> NarrativeSynthesisResult:
        bullets: list[str] = []
        headline = ""

        # Combine digests across executed tools
        merged: dict[str, Any] = {}
        for d in tool_digests:
            merged.update(d)

        period = merged.get("period") or "Latest Period"
        scope = merged.get("scope") or "Call Center"
        branch = merged.get("branch") or "All Branches"

        # 0. Multi-part Team/Metric Trend + Top/Lowest Performer OR Single Spotlight
        if merged.get("team_trend_spotlight") and merged.get("agent_spotlight"):
            tt = merged["team_trend_spotlight"]
            ap = merged["agent_spotlight"]
            t_scope = tt.get("team") or scope
            t_metric = tt.get("metric_label") or "Overall Score"
            t_sc = float(tt.get("score") or 0.0)
            t_first_sc = float(tt.get("first_score") or t_sc)
            t_first_lbl = tt.get("first_month_label") or ""
            t_six_d = tt.get("six_month_delta")
            t_delta_txt = f" ({t_six_d:+.1f}%)" if t_six_d is not None else ""

            e_name = ap.get("entity_name") or "Agent"
            e_id = ap.get("entity_id")
            e_team = ap.get("team") or scope
            r_dir = ap.get("ranking_direction")
            rank_num = ap.get("rank")
            tot_team = ap.get("total_in_team")
            rank_metric_lbl = ap.get("ranking_metric_label") or "Overall PMS Score"
            rank_metric_disp = ap.get("ranking_metric_display") or f"{float(ap.get('score') or 0.0):.1f}%"
            src_route = ap.get("source_route") or f"/employee/{e_id}"
            role_lbl = "lowest-scoring performer" if r_dir == "worst" else "#1 top performer"

            headline = (
                f"{t_scope} {t_metric} moved from {t_first_lbl} ({t_first_sc:.1f}%) to {period} ({t_sc:.1f}%{t_delta_txt}), "
                f"and {e_name} ({e_id}) is the {role_lbl} in {e_team} ({branch}) for {period} by {rank_metric_lbl} at {rank_metric_disp} (Rank #{rank_num} of {tot_team})."
            )
            bullets.append(
                f"Verified performer evidence: {e_name} ({e_id}) · Ranking metric: {rank_metric_lbl} ({rank_metric_disp}) · Period: {period} · Scope: {e_team} ({branch}) · Source: {src_route}."
            )
        elif merged.get("spotlight"):
            sp = merged["spotlight"]
            e_name = sp.get("entity_name") or "Agent"
            e_id = sp.get("entity_id")
            e_pos = str(sp.get("position") or "").strip()
            pos_txt = f" · {e_pos}" if e_pos and e_pos.casefold() not in ("agent", "call center agent") else ""
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
            chg_txt = f", moving {chg:+.1f}% vs {prev_lbl}" if chg is not None else ""
            six_txt = f" ({six_d:+.1f}% since {first_lbl})" if six_d is not None and first_lbl else ""
            ties = list(sp.get("ties") or [])
            tie_txt = f", tied with {', '.join(ties[:2])}" if ties else ""
            missing_months = list(sp.get("missing_months") or [])
            missing_headline_note = (
                f" (Note: {', '.join(missing_months)} had no evaluated score and was excluded.)"
                if missing_months
                else ""
            )
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
                        headline = (
                            f"No. {e_name} ({e_id}{pos_txt}) had no published evaluation score in {period}, while their {target_label} month across "
                            f"{searched_win} by {rank_metric_lbl} was {win_months_str} at {extremum_disp}.{missing_headline_note}"
                        )
                    elif is_match:
                        others = [m for m in extremum_months if m.casefold() != str(period).casefold()]
                        tie_str = f" (tied with {', '.join(others)})" if others else ""
                        headline = (
                            f"Yes. {period} was {e_name}'s ({e_id}{pos_txt}) {target_label} month across {searched_win} "
                            f"in {e_team} by {rank_metric_lbl} at {sc_disp}{tie_str}.{missing_headline_note}"
                        )
                    else:
                        headline = (
                            f"No. {e_name} ({e_id}{pos_txt}) scored {sc_disp} in {period}, while their {target_label} month across "
                            f"{searched_win} by {rank_metric_lbl} was {win_months_str} at {extremum_disp}.{missing_headline_note}"
                        )
                else:
                    tie_note = " (tied)" if len(extremum_months) > 1 else ""
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
                    bullets.append(
                        f"Full history ({searched_win} · {rank_metric_lbl}): " + " · ".join(hist_pts) + "."
                    )
            elif r_dir == "team_trend":
                if metric_lbl and metric_lbl != "Overall Score":
                    headline = f"{e_team} {metric_lbl} reached {sc_disp} in {period}{chg_txt}{six_txt}."
                else:
                    headline = f"{e_team} scored {sc_disp} (Grade {gr}) in {period}{chg_txt}{six_txt}."
            elif not has_period_score:
                searched_win = str(sp.get("searched_window") or "")
                avail_pts = list(sp.get("all_history") or [])
                avail_note = (
                    f" Published scores are available across {searched_win}."
                    if searched_win and avail_pts
                    else ""
                )
                headline = (
                    f"No published evaluation score is available for {e_name} ({e_id}{pos_txt}) in {period} ({e_team}).{avail_note}"
                )
                bullets.append(
                    f"Note: {period} has no published evaluation score for {e_name} ({e_id}); PMS AI does not substitute another month's score."
                )
            elif r_dir == "worst" and not signals.detected_employee_query:
                headline = (
                    f"{e_name} ({e_id}{pos_txt}) is the lowest-scoring agent in {e_team} ({branch}) for {period} by {rank_metric_lbl} at "
                    f"{sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                )
            elif not signals.detected_employee_query:
                headline = (
                    f"{e_name} ({e_id}{pos_txt}) is the #1 top performer in {e_team} ({branch}) for {period} by {rank_metric_lbl} at "
                    f"{sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team}{tie_txt}){chg_txt}{six_txt}."
                )
            else:
                headline = (
                    f"{e_name} ({e_id}{pos_txt}) scored {sc_disp} (Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}) "
                    f"in {period}{chg_txt}{six_txt}.{missing_headline_note if signals.asks_trend else ''}"
                )

        # 1. Revenue guardrail note
        elif signals.asks_revenue_in_call_center:
            vols = merged.get("operational_volumes") or {}
            b_cnt = int(vols.get("total_bookings") or 0)
            a_cnt = int(vols.get("total_attended") or 0)
            c_cnt = int(vols.get("total_calls_handled") or 0)
            headline = (
                f"{scope} tracks operational patient volume rather than financial revenue: "
                f"{b_cnt:,} Bookings and {a_cnt:,} Attended visits in {period} ({branch})."
            )
            bullets.append(f"Total calls handled in scope: {c_cnt:,} calls.")
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
                    headline = (
                        f"In {period}, {leader['branch']} leads at {leader['score']:.1f}% vs. "
                        f"{lagger['branch']} at {lagger['score']:.1f}% ({abs(diff):.1f} pts gap)."
                    )
                    if most_noshows:
                        bullets.append(
                            f"{most_noshows['branch']} holds the largest No-Show volume ({most_noshows['no_shows']:,} missed visits out of "
                            f"{most_noshows['bookings']:,} bookings · {most_noshows['attendance_rate_pct']:.1f}% Attended)."
                        )

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
                headline = (
                    f"{emp_name} scored {latest['score']:.1f}% in {latest['period']} across {len(hist)} tracked months "
                    f"({delta:+.1f}% vs. {earliest['period']})."
                )
            else:
                headline = f"No evaluation records matched '{emp_name}' within your authorized scope."

        # 5. Corrective Actions
        elif "total_actions" in merged:
            tot_act = merged.get("total_actions", 0)
            acts = merged.get("actions") or []
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
                delta_txt = f" ({delta:+.1f}% change)" if delta is not None else ""
                if s_from is not None and s_to is not None:
                    headline = (
                        f"{scope} ({branch}) moved from {s_from:.1f}% in {p_from} to {s_to:.1f}% in {p_to}{delta_txt}."
                    )
                else:
                    headline = (
                        f"Comparing {scope} ({branch}) across {p_from} and {p_to}: latest score is {(s_to or 0.0):.1f}%{delta_txt}."
                    )
            elif requested_kpi:
                if requested_kpi.get("kpi_key") in (
                    "bookings_count",
                    "TotalBookings",
                    "attended_count",
                    "AttendedPatients",
                    "handled_calls_count",
                    "HandledCalls",
                    "abandoned_calls_count",
                    "AbandonedCalls",
                ):
                    headline = (
                        f"In {scope} ({period} · {branch}), {requested_kpi['kpi_label']} reached "
                        f"{requested_kpi['actual_display']}."
                    )
                    if requested_kpi.get("tracking_only_note"):
                        bullets.append(str(requested_kpi["tracking_only_note"]))
                elif requested_kpi.get("contributes_to_score") is False:
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
                    headline = (
                        f"In {scope} ({period} · {branch}), {requested_kpi['kpi_label']} is at {requested_kpi['actual_display']} "
                        f"vs target {requested_kpi['target_display']} ({ach_txt}, {requested_kpi.get('weight_percent') or 0:.0f}% weight){below_kpi_note}."
                    )
                    if merged.get("top_contributors"):
                        top_c = merged["top_contributors"]
                        first_c = top_c[0]
                        neg_c = merged.get("negative_contributors", len(top_c))
                        tot_c = merged.get("total_employees", len(top_c))
                        top_names = ", ".join(
                            f"{c['employee_name']} ({c.get('weighted_impact') or 0:+.2f} pts)"
                            for c in top_c[:3]
                        )
                        bullets.append(
                            f"Root-cause drivers on {requested_kpi['kpi_label']}: {neg_c} of {tot_c} employees are below target, led by {top_names}."
                        )
            elif worst and avg_score is not None:
                w_score = worst.get("current_score") or 0.0
                w_change = worst.get("score_change")
                change_txt_en = f" ({w_change:+.1f}% vs prior month)" if w_change is not None else ""
                headline = (
                    f"In {period} ({branch}), {worst['team']} has the lowest score at {w_score:.1f}%{change_txt_en}, "
                    f"with {worst.get('impacted_employees', below_cnt)} of {worst.get('total_employees', tot_rec)} agents below target."
                )
                if worst.get("main_cause"):
                    bullets.append(f"Primary driver: {worst['main_cause']}.")
            elif lowest_kpi:
                below_low_cnt = int(lowest_kpi.get("people_below_target") or 0)
                below_low_note = f", {below_low_cnt} agents below target" if below_low_cnt > 0 else ""
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
                        f"Root-cause drivers on {lowest_kpi['kpi_label']}: {neg_c} of {tot_c} employees are below target, led by {top_names}."
                    )
            elif avg_score is not None:
                delta_str = f" ({score_change:+.1f}%)" if score_change is not None else ""
                headline = f"{scope} average performance in {period} ({branch}) is {avg_score:.1f}%{delta_str} across {tot_rec} evaluated records."
            else:
                headline = f"No performance records matched the selected filters ({scope} · {period})."

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

        if str(branch).casefold() in ("all branches", "all", "") and not merged.get("branch_comparison"):
            primary_drilldown = f"Compare Dubai vs Sharjah branch performance for {scope}"
        elif not merged.get("top_contributors"):
            primary_drilldown = f"Show verified KPI score drivers for {scope} in {period}"
        else:
            primary_drilldown = f"What is {scope} 6-month trend?"

        followups = [
            primary_drilldown,
            f"Who is the best agent in {scope} and his trend?",
            f"Who is the lowest agent in {scope} and his trend?",
            f"What is {scope} 6-month trend?",
        ]

        return NarrativeSynthesisResult(
            headline=headline,
            narrative_bullets=bullets[:4],
            suggested_followups=followups,
            provider_used=self.provider_name,
            model_used=self.model_name,
            metrics=ProviderCallMetrics(
                provider_used=self.provider_name,
                model_used=self.model_name,
                provider_calls=0,
            ),
        )

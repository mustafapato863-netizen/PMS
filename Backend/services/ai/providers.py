from __future__ import annotations

import json
import logging
import os
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

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.gemini_model}:generateContent"
        user_text = json.dumps(minimized_input, ensure_ascii=False, separators=(",", ":"))
        payload = {
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json",
            },
        }
        encoded_payload = json.dumps(payload).encode("utf-8")
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
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
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
            plan = StructuredQueryPlan.model_validate(parsed_dict)
            return StructuredRoutingProviderResult(
                plan=plan,
                metrics=ProviderCallMetrics(
                    provider_used="gemini",
                    model_used=cfg.gemini_model,
                    provider_calls=1,
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
            logger.warning("Gemini router timed out after %.1f ms", elapsed_ms)
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(
                    provider_used="gemini",
                    model_used=cfg.gemini_model,
                    provider_calls=1,
                    provider_ms=elapsed_ms,
                    fallback_outcome="timeout",
                    outbound_payload=minimized_input,
                ),
                error_detail=redact_secrets(str(exc)),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            logger.warning("Gemini router returned invalid structured output: %s", redact_secrets(str(exc)))
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(
                    provider_used="gemini",
                    model_used=cfg.gemini_model,
                    provider_calls=1,
                    provider_ms=elapsed_ms,
                    fallback_outcome="invalid_json",
                    outbound_payload=minimized_input,
                ),
                error_detail=redact_secrets(str(exc)),
            )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            outcome = "timeout" if "timed out" in str(exc).casefold() else "http_error"
            logger.warning("Gemini router request failed (%s): %s", outcome, redact_secrets(str(exc)))
            return StructuredRoutingProviderResult(
                plan=None,
                metrics=ProviderCallMetrics(
                    provider_used="gemini",
                    model_used=cfg.gemini_model,
                    provider_calls=1,
                    provider_ms=elapsed_ms,
                    fallback_outcome=outcome,
                    outbound_payload=minimized_input,
                ),
                error_detail=redact_secrets(str(exc)),
            )


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

        # 0. Focused Agent or Team Spotlight & 6-Month Trend (concise 1-sentence answer, zero bullet clutter)
        if merged.get("spotlight"):
            sp = merged["spotlight"]
            e_name = sp.get("entity_name") or "Agent"
            e_id = sp.get("entity_id")
            e_team = sp.get("team") or scope
            sc = float(sp.get("score") or 0.0)
            gr = sp.get("grade") or "B"
            chg = sp.get("change_vs_prev")
            prev_lbl = sp.get("previous_month_label") or "prior month"
            six_d = sp.get("six_month_delta")
            first_lbl = sp.get("first_month_label") or ""
            r_dir = sp.get("ranking_direction")
            rank_num = sp.get("rank")
            tot_team = sp.get("total_in_team")

            chg_txt = f", moving {chg:+.1f}% vs {prev_lbl}" if chg is not None else ""
            six_txt = f" ({six_d:+.1f}% since {first_lbl})" if six_d is not None and first_lbl else ""
            if r_dir == "team_trend":
                headline = f"{e_team} scored {sc:.1f}% (Grade {gr}) in {period}{chg_txt}{six_txt}."
            elif r_dir == "worst" and not signals.detected_employee_query:
                headline = (
                    f"{e_name} ({e_id}) is the lowest-scoring agent in {e_team} for {period} at "
                    f"{sc:.1f}% (Grade {gr}, Rank #{rank_num} of {tot_team}){chg_txt}{six_txt}."
                )
            elif not signals.detected_employee_query:
                headline = (
                    f"{e_name} ({e_id}) is the #1 top performer in {e_team} for {period} at "
                    f"{sc:.1f}% (Grade {gr}, Rank #{rank_num} of {tot_team}){chg_txt}{six_txt}."
                )
            else:
                headline = (
                    f"{e_name} ({e_id}) scored {sc:.1f}% (Grade {gr}, Rank #{rank_num} of {tot_team} in {e_team}) "
                    f"in {period}{chg_txt}{six_txt}."
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
            bc = merged["branch_comparison"]
            b1, b2 = bc[0], bc[1]
            diff = round(float(b1["score"] or 0.0) - float(b2["score"] or 0.0), 1)
            leader = b1 if diff >= 0 else b2
            lagger = b2 if diff >= 0 else b1
            with_vol = [b for b in bc if int(b.get("bookings") or 0) > 0]
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

        # 3. Root-cause employees (People Contribution)
        elif merged.get("top_contributors"):
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
                headline = f"{t_name} {lvl} Balanced Scorecard is structured across 4 strategic perspectives."

        # 7. Team / KPI Diagnosis Summary
        else:
            worst = merged.get("worst_team")
            lowest_kpi = merged.get("lowest_kpi")
            avg_score = merged.get("average_score")
            score_change = merged.get("score_change")
            below_cnt = merged.get("employees_below_target", 0)
            tot_rec = merged.get("total_records", 0)

            if worst and avg_score is not None:
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
                headline = (
                    f"The primary KPI bottleneck in {scope} ({period} · {branch}) is {lowest_kpi['kpi_label']} "
                    f"at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['actual_display']} vs target {lowest_kpi['target_display']})."
                )
            elif avg_score is not None:
                delta_str = f" ({score_change:+.1f}%)" if score_change is not None else ""
                headline = f"{scope} average performance in {period} ({branch}) is {avg_score:.1f}%{delta_str} across {tot_rec} evaluated records."
            else:
                headline = f"No performance records matched the selected filters ({scope} · {period})."

            if lowest_kpi and worst:
                bullets.append(
                    f"Lowest KPI: {lowest_kpi['kpi_label']} (Weight {lowest_kpi['weight_percent']:.0f}%) at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['people_below_target']} agents below target)."
                )

        followups = [
            f"Who is the best agent in {scope} and his trend?",
            f"Who is the lowest agent in {scope} and his trend?",
            f"What is {scope} 6-month trend?",
            f"Compare Dubai vs Sharjah branch performance for {scope}",
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


class CloudOrLocalHttpProviderAdapter:
    """Server-controlled synthesis adapter. Enforces server-owned cloud switches, header-based API keys,
    and outbound PII/evidence minimization, defaulting to deterministic local composition."""

    def __init__(self, provider_override: str | None = "auto") -> None:
        self.provider_override = provider_override or "auto"
        self.fallback = DeterministicLocalProviderAdapter()

    def synthesize(
        self,
        *,
        prompt: str,
        signals: ParsedPromptSignals,
        tool_digests: list[dict[str, Any]],
        guardrail_notes: list[str],
    ) -> NarrativeSynthesisResult:
        baseline = self.fallback.synthesize(
            prompt=prompt,
            signals=signals,
            tool_digests=tool_digests,
            guardrail_notes=guardrail_notes,
        )
        cfg = get_ai_runtime_config()

        # Server controls provider choice: unless PMS_AI_GEMINI_ROUTING_ENABLED is true and router_mode is legacy,
        # compose the answer locally from PMS evidence with zero external synthesis calls.
        if self.provider_override == "deterministic" or cfg.router_mode != "legacy":
            return baseline

        if not cfg.gemini_routing_enabled:
            baseline.metrics.fallback_outcome = "cloud_disabled"
            return baseline

        scope_candidate = signals.detected_team or "Call Center"
        if not cfg.is_scope_allowed_for_cloud(scope_candidate):
            baseline.metrics.fallback_outcome = "scope_not_allowed"
            return baseline

        if not is_prompt_safe_for_external_projection(prompt):
            baseline.metrics.fallback_outcome = "unsafe_prompt"
            return baseline

        local_url = os.environ.get("PMS_LOCAL_LLM_URL", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        gemini_key = cfg.gemini_api_key

        try:
            if (self.provider_override in ("local_ollama", "auto")) and local_url:
                return self._call_openai_compatible(
                    base_url=local_url,
                    api_key="ollama",
                    model=os.environ.get("PMS_LOCAL_LLM_MODEL", "qwen2.5:7b-instruct"),
                    provider_label="local_ollama",
                    prompt=prompt,
                    baseline=baseline,
                    timeout=cfg.provider_timeout_seconds,
                )
            if (self.provider_override in ("gemini", "auto")) and gemini_key:
                return self._call_gemini_rest(
                    api_key=gemini_key,
                    model=cfg.gemini_model,
                    prompt=prompt,
                    baseline=baseline,
                    timeout=cfg.provider_timeout_seconds,
                )
            if (self.provider_override in ("openai", "auto")) and openai_key:
                return self._call_openai_compatible(
                    base_url="https://api.openai.com/v1/chat/completions",
                    api_key=openai_key,
                    model=os.environ.get("PMS_OPENAI_MODEL", "gpt-4o-mini"),
                    provider_label="openai",
                    prompt=prompt,
                    baseline=baseline,
                    timeout=cfg.provider_timeout_seconds,
                )
        except Exception as exc:
            logger.warning(
                "External/Local LLM synthesis fell back to deterministic engine: %s",
                redact_secrets(str(exc)),
            )
            baseline.metrics.fallback_outcome = "http_error"

        return baseline

    def _build_system_instruction(self) -> str:
        return (
            "You are PMS AI, the executive performance analytics copilot for Saudi German Health. "
            "Respond strictly in English. "
            "Refine the provided verified summary headline into 1-2 clear sentences without changing any numbers. "
            'Return JSON: {"headline": "1-2 sentence executive answer", "bullets": ["up to 2 concise bullets"]}.'
        )

    def _call_gemini_rest(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        baseline: NarrativeSynthesisResult,
        timeout: float,
    ) -> NarrativeSynthesisResult:
        # Use header x-goog-api-key (never URL query parameter) and send only sanitized summary text
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        sanitized_prompt = sanitize_prompt_for_router_training(prompt)[:300]
        sanitized_headline = sanitize_prompt_for_router_training(baseline.headline)
        user_content = f"Question: {sanitized_prompt}\nVerified Summary: {sanitized_headline}"
        payload = {
            "systemInstruction": {"parts": [{"text": self._build_system_instruction()}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        body = json.loads(raw_body)
        usage = body.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount") or _estimate_tokens(user_content))
        out_tok = int(usage.get("candidatesTokenCount") or _estimate_tokens(raw_body))
        cost_usd = round(
            in_tok * GEMINI_FLASH_INPUT_USD_PER_TOKEN + out_tok * GEMINI_FLASH_OUTPUT_USD_PER_TOKEN,
            8,
        )
        text_out = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_out)
        return NarrativeSynthesisResult(
            headline=str(parsed.get("headline") or baseline.headline),
            narrative_bullets=[str(b) for b in (parsed.get("bullets") or baseline.narrative_bullets)[:4]],
            suggested_followups=baseline.suggested_followups,
            provider_used="gemini",
            model_used=model,
            metrics=ProviderCallMetrics(
                provider_used="gemini",
                model_used=model,
                provider_calls=1,
                provider_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                estimated_cost_usd=cost_usd,
                fallback_outcome="none",
            ),
        )

    def _call_openai_compatible(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_label: str,
        prompt: str,
        baseline: NarrativeSynthesisResult,
        timeout: float,
    ) -> NarrativeSynthesisResult:
        sanitized_prompt = sanitize_prompt_for_router_training(prompt)[:300]
        sanitized_headline = sanitize_prompt_for_router_training(baseline.headline)
        user_content = f"Question: {sanitized_prompt}\nVerified Summary: {sanitized_headline}"
        payload = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._build_system_instruction()},
                {"role": "user", "content": user_content},
            ],
        }
        req = urllib.request.Request(
            base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_body = resp.read().decode("utf-8")
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        body = json.loads(raw_body)
        text_out = body["choices"][0]["message"]["content"]
        parsed = json.loads(text_out)
        in_tok = _estimate_tokens(user_content)
        out_tok = _estimate_tokens(text_out)
        return NarrativeSynthesisResult(
            headline=str(parsed.get("headline") or baseline.headline),
            narrative_bullets=[str(b) for b in (parsed.get("bullets") or baseline.narrative_bullets)[:4]],
            suggested_followups=baseline.suggested_followups,
            provider_used=provider_label,
            model_used=model,
            metrics=ProviderCallMetrics(
                provider_used=provider_label,
                model_used=model,
                provider_calls=1,
                provider_ms=elapsed_ms,
                input_tokens=in_tok,
                output_tokens=out_tok,
                estimated_cost_usd=0.0,
                fallback_outcome="none",
            ),
        )

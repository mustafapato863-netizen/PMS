from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass
from typing import Any

from services.ai.domain_policies import ParsedPromptSignals

logger = logging.getLogger(__name__)


@dataclass
class NarrativeSynthesisResult:
    headline: str
    narrative_bullets: list[str]
    suggested_followups: list[str]
    provider_used: str
    model_used: str


class DeterministicLocalProviderAdapter:
    """Zero-dependency bilingual (Arabic/English) analytical synthesizer & fallback engine."""

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
        ar = False
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
            if ar:
                headline = (
                    f"فرق الكول سنتر ({scope}) تقيس الإنتاج بعدد الحجوزات والحضور الفعلي للمرضى وليس الإيرادات المالية: "
                    f"إجمالي الحجوزات {b_cnt:,} والحضور الفعلي {a_cnt:,} في {period}."
                )
                bullets.append(f"إجمالي المكالمات المتعامل معها: {c_cnt:,} مكالمة عبر ({branch}).")
                bullets.append("الإيرادات المالية المباشرة تُسجل في قطاعات التسويق (Marketing) وإدارة دورة الإيرادات (RCM).")
            else:
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
            if ar:
                headline = (
                    f"في {period}، يتفوق فرع {leader['branch']} بمتوسط أداء {leader['score']:.1f}% مقابل "
                    f"{lagger['score']:.1f}% لفرع {lagger['branch']} بفارق {abs(diff):.1f} نقطة."
                )
                if most_noshows:
                    bullets.append(
                        f"أكبر كتلة حجوزات لم تحضر (No-Shows) تتركز في فرع {most_noshows['branch']} بعدد "
                        f"{most_noshows['no_shows']:,} مريض من أصل {most_noshows['bookings']:,} حجز (نسبة حضور {most_noshows['attendance_rate_pct']:.1f}%)."
                    )
            else:
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
            if ar:
                headline = (
                    f"يوجد {neg_cnt} من أصل {tot_cnt} موظف تحت المستهدف في {kpi_name} ({period} · {branch})؛ "
                    f"أكبر تأثير سلبي جاء من {first['employee_name']} بتأثير ({first.get('weighted_impact') or 0:+.2f} نقطة)."
                )
                if p_tot_pts > 0:
                    bullets.append(
                        f"تركيز باريتو (Pareto 80/20): أعلى 3 موظفين متأثرين يمثلون {p_share:.0f}% من إجمالي الفقد المرجح "
                        f"(-{p_top3_pts:.2f} من أصل -{p_tot_pts:.2f} نقطة)."
                    )
                    bullets.append(
                        f"محاكاة الأثر (What-If ROI): رفع أداء أول 3 موظفين فقط إلى المستهدف يرفع متوسط الفريق بمقدار +{p_top3_pts:.2f} نقطة فوراً."
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
                if ar:
                    headline = (
                        f"سجل أداء {emp_name} عبر {len(hist)} شهور يظهر تقييم {latest['score']:.1f}% في {latest['period']} "
                        f"({delta:+.1f}% مقارنة بـ {earliest['period']})."
                    )
                else:
                    headline = (
                        f"{emp_name} scored {latest['score']:.1f}% in {latest['period']} across {len(hist)} tracked months "
                        f"({delta:+.1f}% vs. {earliest['period']})."
                    )
            else:
                headline = (
                    f"لا توجد سجلات تقييم مطابقة للموظف '{emp_name}' ضمن نطاق صلاحياتك."
                    if ar
                    else f"No evaluation records matched '{emp_name}' within your authorized scope."
                )

        # 5. Corrective Actions
        elif "total_actions" in merged:
            tot_act = merged.get("total_actions", 0)
            acts = merged.get("actions") or []
            if ar:
                headline = f"تم رصد {tot_act} قرار/خطة تصحيحية مسجلة في نطاق {scope} حتى الآن."
                for a in acts[:3]:
                    bullets.append(
                        f"{a.get('employee_name')} ({a.get('team')}): {a.get('action_type')} — الحالة: {a.get('status')} ({a.get('follow_up_state')})."
                    )
            else:
                headline = f"{tot_act} corrective actions are currently tracked for {scope}."
                for a in acts[:3]:
                    bullets.append(
                        f"{a.get('employee_name')} ({a.get('team')}): {a.get('action_type')} — {a.get('status')} ({a.get('follow_up_state')})."
                    )

        # 6. Managerial / Corporate BSC
        elif merged.get("bsc_kpis") or merged.get("guardrail"):
            if merged.get("guardrail"):
                headline = (
                    "بطاقة الأداء المتوازن (Managerial / Corporate BSC) تُقيّم على مستوى الفريق بالكامل ولا تُقسّم حسب الفروع."
                    if ar
                    else merged["guardrail"]
                )
            else:
                lvl = merged.get("level", "Managerial")
                t_name = merged.get("team", "Inbound")
                headline = (
                    f"هيكل بطاقة الأداء المتوازن ({lvl} BSC) لفريق {t_name} يوزع الأوزان على 4 محاور استراتيجية."
                    if ar
                    else f"{t_name} {lvl} Balanced Scorecard is structured across 4 strategic perspectives."
                )

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
                change_txt_ar = f" ({w_change:+.1f}% عن الشهر السابق)" if w_change is not None else ""
                change_txt_en = f" ({w_change:+.1f}% vs prior month)" if w_change is not None else ""
                if ar:
                    headline = (
                        f"في {period} ({branch})، فريق {worst['team']} هو الأكثر تراجعاً بمتوسط {w_score:.1f}%{change_txt_ar}، "
                        f"مع وجود {worst.get('impacted_employees', below_cnt)} من أصل {worst.get('total_employees', tot_rec)} موظف تحت المستهدف."
                    )
                    if worst.get("main_cause"):
                        bullets.append(f"السبب الرئيسي المسجل: {worst['main_cause']}.")
                else:
                    headline = (
                        f"In {period} ({branch}), {worst['team']} has the lowest score at {w_score:.1f}%{change_txt_en}, "
                        f"with {worst.get('impacted_employees', below_cnt)} of {worst.get('total_employees', tot_rec)} agents below target."
                    )
                    if worst.get("main_cause"):
                        bullets.append(f"Primary driver: {worst['main_cause']}.")
            elif lowest_kpi:
                if ar:
                    headline = (
                        f"أكثر مؤشر مسبب للفجوة في {scope} ({period} · {branch}) هو {lowest_kpi['kpi_label']} "
                        f"بنسبة تحقيق {lowest_kpi.get('achievement_percent') or 0:.1f}% (الفعلي {lowest_kpi['actual_display']} مقابل المستهدف {lowest_kpi['target_display']})."
                    )
                else:
                    headline = (
                        f"The primary KPI bottleneck in {scope} ({period} · {branch}) is {lowest_kpi['kpi_label']} "
                        f"at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['actual_display']} vs target {lowest_kpi['target_display']})."
                    )
            elif avg_score is not None:
                delta_str = f" ({score_change:+.1f}%)" if score_change is not None else ""
                if ar:
                    headline = f"متوسط أداء {scope} في {period} ({branch}) يبلغ {avg_score:.1f}%{delta_str} عبر {tot_rec} سجل مقيّم."
                else:
                    headline = f"{scope} average performance in {period} ({branch}) is {avg_score:.1f}%{delta_str} across {tot_rec} evaluated records."
            else:
                headline = (
                    f"لا توجد سجلات أداء متاحة للفلاتر المحددة ({scope} · {period})."
                    if ar
                    else f"No performance records matched the selected filters ({scope} · {period})."
                )

            if lowest_kpi and worst:
                if ar:
                    bullets.append(
                        f"أضعف مؤشر أداء: {lowest_kpi['kpi_label']} (وزن {lowest_kpi['weight_percent']:.0f}%) بنسبة تحقيق {lowest_kpi.get('achievement_percent') or 0:.1f}% وعدد {lowest_kpi['people_below_target']} موظف تحت التارجت."
                    )
                else:
                    bullets.append(
                        f"Lowest KPI: {lowest_kpi['kpi_label']} (Weight {lowest_kpi['weight_percent']:.0f}%) at {lowest_kpi.get('achievement_percent') or 0:.1f}% achievement ({lowest_kpi['people_below_target']} agents below target)."
                    )

        if ar:
            followups = [
                f"مين أكتر موظفين تسببوا في نزول تقييم {scope}؟",
                f"قارن أداء فرع دبي مقابل الشارقة في {scope}",
                f"إيه القرارات والخطط التصحيحية المفتوحة في {scope}؟",
                "اعرض تقييم المستوى الإداري (Managerial BSC)",
            ]
        else:
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
        )


class CloudOrLocalHttpProviderAdapter:
    """Calls Gemini, OpenAI, or Local Ollama/vLLM for narrative synthesis over deterministic tool digests,
    falling back immediately to DeterministicLocalProviderAdapter if unconfigured or unreachable."""

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
        if self.provider_override == "deterministic":
            return baseline

        # Check Local Ollama / vLLM endpoint if requested or configured
        local_url = os.environ.get("PMS_LOCAL_LLM_URL", "").strip()
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        gemini_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()

        try:
            if (self.provider_override in ("local_ollama", "auto")) and local_url:
                return self._call_openai_compatible(
                    base_url=local_url,
                    api_key="ollama",
                    model=os.environ.get("PMS_LOCAL_LLM_MODEL", "qwen2.5:7b-instruct"),
                    provider_label="local_ollama",
                    prompt=prompt,
                    signals=signals,
                    tool_digests=tool_digests,
                    baseline=baseline,
                )
            if (self.provider_override in ("gemini", "auto")) and gemini_key:
                return self._call_gemini_rest(
                    api_key=gemini_key,
                    model=os.environ.get("PMS_GEMINI_MODEL", "gemini-2.5-flash"),
                    prompt=prompt,
                    signals=signals,
                    tool_digests=tool_digests,
                    baseline=baseline,
                )
            if (self.provider_override in ("openai", "auto")) and openai_key:
                return self._call_openai_compatible(
                    base_url="https://api.openai.com/v1/chat/completions",
                    api_key=openai_key,
                    model=os.environ.get("PMS_OPENAI_MODEL", "gpt-4o-mini"),
                    provider_label="openai",
                    prompt=prompt,
                    signals=signals,
                    tool_digests=tool_digests,
                    baseline=baseline,
                )
        except Exception as exc:
            logger.warning("External/Local LLM synthesis fell back to deterministic engine: %s", exc)

        return baseline

    def _build_system_instruction(self, signals: ParsedPromptSignals) -> str:
        lang = "Arabic (Egyptian/Modern Standard professional)" if signals.is_arabic else "English"
        return (
            "You are PMS AI, the executive performance analytics copilot for Saudi German Health. "
            f"Respond strictly in {lang}. "
            "Use ONLY the exact numbers provided in the verified tool digest JSON. "
            "Never invent numbers, never equate Call Center Bookings/Attendance with financial revenue, "
            "and keep your response to a JSON object with keys: "
            '{"headline": "1-2 sentence executive answer", "bullets": ["up to 3 concise evidence bullets"]}.'
        )

    def _call_gemini_rest(
        self,
        *,
        api_key: str,
        model: str,
        prompt: str,
        signals: ParsedPromptSignals,
        tool_digests: list[dict[str, Any]],
        baseline: NarrativeSynthesisResult,
    ) -> NarrativeSynthesisResult:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "systemInstruction": {"parts": [{"text": self._build_system_instruction(signals)}]},
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"Manager Question: {prompt}\nVerified Tool Digest JSON:\n{json.dumps(tool_digests, ensure_ascii=False)}"
                        }
                    ],
                }
            ],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text_out = body["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text_out)
        return NarrativeSynthesisResult(
            headline=str(parsed.get("headline") or baseline.headline),
            narrative_bullets=[str(b) for b in (parsed.get("bullets") or baseline.narrative_bullets)[:4]],
            suggested_followups=baseline.suggested_followups,
            provider_used="gemini",
            model_used=model,
        )

    def _call_openai_compatible(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        provider_label: str,
        prompt: str,
        signals: ParsedPromptSignals,
        tool_digests: list[dict[str, Any]],
        baseline: NarrativeSynthesisResult,
    ) -> NarrativeSynthesisResult:
        payload = {
            "model": model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._build_system_instruction(signals)},
                {
                    "role": "user",
                    "content": f"Manager Question: {prompt}\nVerified Tool Digest JSON:\n{json.dumps(tool_digests, ensure_ascii=False)}",
                },
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
        with urllib.request.urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text_out = body["choices"][0]["message"]["content"]
        parsed = json.loads(text_out)
        return NarrativeSynthesisResult(
            headline=str(parsed.get("headline") or baseline.headline),
            narrative_bullets=[str(b) for b in (parsed.get("bullets") or baseline.narrative_bullets)[:4]],
            suggested_followups=baseline.suggested_followups,
            provider_used=provider_label,
            model_used=model,
        )

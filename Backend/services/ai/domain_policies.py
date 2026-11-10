from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from models.ai_schemas import AiGuardrailItem, AiStarterPrompt, SessionFilterContext


ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")

MONTH_ALIASES: dict[str, str] = {
    "january": "January", "jan": "January", "يناير": "January", "شهر 1": "January",
    "february": "February", "feb": "February", "فبراير": "February", "شهر 2": "February",
    "march": "March", "mar": "March", "مارس": "March", "شهر 3": "March",
    "april": "April", "apr": "April", "أبريل": "April", "ابريل": "April", "شهر 4": "April",
    "may": "May", "مايو": "May", "شهر 5": "May",
    "june": "June", "jun": "June", "يونيو": "June", "يونية": "June", "شهر 6": "June",
    "july": "July", "jul": "July", "يوليو": "July", "يولية": "July", "شهر 7": "July",
    "august": "August", "aug": "August", "أغسطس": "August", "اغسطس": "August", "شهر 8": "August",
    "september": "September", "sep": "September", "sept": "September", "سبتمبر": "September", "شهر 9": "September",
    "october": "October", "oct": "October", "أكتوبر": "October", "اكتوبر": "October", "شهر 10": "October",
    "november": "November", "nov": "November", "نوفمبر": "November", "شهر 11": "November",
    "december": "December", "dec": "December", "ديسمبر": "December", "شهر 12": "December",
}

BRANCH_ALIASES: dict[str, str] = {
    "dubai": "dubai", "dxb": "dubai", "دبي": "dubai", "دبى": "dubai",
    "sharjah": "sharjah", "shj": "sharjah", "الشارقة": "sharjah", "الشارقه": "sharjah", "شارقة": "sharjah",
    "ajman": "ajman", "ajm": "ajman", "عجمان": "ajman",
    "clinics": "clinics", "clinic": "clinics", "العيادات": "clinics", "عيادات": "clinics",
}

TEAM_ALIASES: dict[str, str] = {
    "inbound": "Inbound", "انباوند": "Inbound", "إنباوند": "Inbound", "الاستقبال": "Inbound",
    "outbound": "Outbound", "اوتباوند": "Outbound", "أوتباوند": "Outbound", "اوت باوند": "Outbound",
    "support positions": "Support Positions", "call center support": "Support Positions",
    "egypt support": "Support Positions", "support in egypt": "Support Positions",
    "support team": "Support Positions", "in support": "Support Positions",
    "lowest in support": "Support Positions", "best in support": "Support Positions",
    "top in support": "Support Positions", "worst in support": "Support Positions",
    "marketing": "Marketing", "ماركتنج": "Marketing", "الماركتنج": "Marketing", "التسويق": "Marketing",
    "sales": "Sales",
    "csr": "CSR",
    "pharmacy": "Pharmacy",
    "coding egy": "Coding EGY",
    "coding": "Coding", "كودينج": "Coding",
    "submission egy": "Submission EGY",
    "submission": "Submission", "سبمشن": "Submission",
    "re-submission": "Re-Submission",
    "resubmission": "Resubmission",
    "pre-approvals ip offshore": "Pre-Approvals IP Offshore",
    "pre-approvals ip elective dubai": "Pre-Approvals IP Elective Dubai",
    "ip elective dubai": "Pre-Approvals IP Elective Dubai",
    "pre-approvals ip final dubai": "Pre-Approvals IP Final Dubai",
    "ip final dubai": "Pre-Approvals IP Final Dubai",
    "pre-approvals ip final shjajm": "Pre-Approvals IP Final SHJAJM",
    "ip sharjah": "Pre-Approvals IP Final SHJAJM",
    "pre-approvals op dubai": "Pre-Approvals OP Dubai",
    "op dubai": "Pre-Approvals OP Dubai",
    "pre-approvals op final shjajm": "Pre-Approvals OP Final SHJAJM",
    "op sharjah": "Pre-Approvals OP Final SHJAJM",
    "pre-approvals ip": "Pre-Approvals IP",
    "pre-approvals": "Pre-Approvals", "preapprovals": "Pre-Approvals",
    "human resources": "Human Resources",
    "offshore admin & management": "Offshore Admin & Management",
    "finance": "Finance",
    "crm": "CRM",
    "nursing": "Nursing",
    "pmo": "PMO",
    "rcm": "RCM",
}

REVENUE_KEYWORDS: tuple[str, ...] = (
    "revenue", "revenues", "income", "financial return", "cash",
    "ايراد", "إيراد", "ايرادات", "إيرادات", "مبيعات", "عائد مالي", "فلوس", "دخل",
)


def is_arabic_text(text: str) -> bool:
    return bool(ARABIC_CHAR_RE.search(text or ""))


def sanitize_untrusted_text(value: Any, max_len: int = 200) -> str:
    """Truncate and strip control characters from untrusted Excel/DB free-text cells."""
    if value is None:
        return ""
    cleaned = re.sub(r"[\r\n\t]+", " ", str(value)).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1].rstrip() + "…"
    return cleaned


def disambiguate_call_center_kpi_label(team_name: str | None, kpi_key: str, raw_label: str | None = None) -> str:
    """Resolve Call Center KPI collisions (key='Other' and Patient Attendance vs Agent Shift Attendance)."""
    t_norm = str(team_name or "").strip().casefold()
    k_norm = str(kpi_key or "").strip().casefold()
    label = str(raw_label or kpi_key or "").strip()

    if k_norm == "other":
        if "inbound" in t_norm or "abandon" in label.casefold():
            return "Abandon Rate (Inbound)"
        if "outbound" in t_norm or "reach" in label.casefold():
            return "Reachability (Outbound)"
        return f"{label} ({team_name})" if team_name else label

    if k_norm == "attendance":
        return "Attendance Rate (Patient Attended / Bookings)"

    if k_norm == "attendancecompliance":
        return "Attendance Compliance (Managerial Shift Compliance)"

    return label


@dataclass
class ParsedPromptSignals:
    detected_team: str | None = None
    detected_branch: str | None = None
    detected_compare_branch: str | None = None
    detected_branches: list[str] = field(default_factory=list)
    asks_branch_comparison: bool = False
    asks_booking_count: bool = False
    asks_best_month_history: bool = False
    asks_worst_month_history: bool = False
    asks_specific_month_in_prompt: bool = False
    asks_decisions_or_what_if: bool = False
    asks_best_agent: bool = False
    asks_worst_agent: bool = False
    asks_trend: bool = False
    asks_single_person: bool = False
    detected_month: str | None = None
    detected_year: int | None = None
    detected_kpi: str | None = None
    detected_level: str | None = None
    detected_employee_query: str | None = None
    asks_revenue_in_call_center: bool = False
    is_arabic: bool = False
    primary_intents: list[str] = field(default_factory=list)


def extract_prompt_signals(prompt: str, session_state: SessionFilterContext) -> ParsedPromptSignals:
    """Deterministic bilingual (Arabic + English) signal extractor for hybrid local routing."""
    text = (prompt or "").strip()
    lower = text.casefold()
    signals = ParsedPromptSignals(is_arabic=is_arabic_text(text))

    # 1. Detect Team
    used_b_spans: list[tuple[int, int]] = []
    for alias, canonical in sorted(TEAM_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        m_team = re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower)
        if m_team:
            signals.detected_team = canonical
            used_b_spans.append(m_team.span())
            break

    # 2. Detect Branches (supports comparison of 2 or 3+ branches like Dubai, Ajman or Sharjah, or all UAE branches)
    branch_hits: list[tuple[int, str]] = []
    for alias, canonical in sorted(BRANCH_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        for m_b in re.finditer(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower):
            span = m_b.span()
            if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in used_b_spans):
                continue
            used_b_spans.append(span)
            branch_hits.append((span[0], canonical))
    branch_hits.sort(key=lambda x: x[0])
    found_branches: list[str] = []
    for _, canonical in branch_hits:
        if canonical not in found_branches:
            found_branches.append(canonical)
    if found_branches:
        signals.detected_branches = list(found_branches)
        signals.detected_branch = found_branches[0]
        if len(found_branches) > 1:
            signals.detected_compare_branch = found_branches[1]
            signals.asks_branch_comparison = True
    if any(
        k in lower
        for k in (
            "compare branch", "all branches", "across branches", "branches", "which branch", "what branch",
            "كل الفروع", "جميع الفروع", "مقارنة الفروع", "بين الفروع", "فروع الإمارات", "الفروع",
        )
    ):
        signals.asks_branch_comparison = True

    # NOTE (Task 2): keep in step with router._detect_metric_id — a bare
    # "bookings" noun and "how many <branch> bookings" are count questions,
    # not Booking Rate questions.
    if (
        any(
            k in lower
            for k in (
                "more bookings",
                "most bookings",
                "fewer bookings",
                "least bookings",
                "bookings count",
                "booking count",
                "total bookings",
                "number of bookings",
                "booking volume",
                "how many bookings",
            )
        )
        or re.search(r"how many\b.{0,50}\bbookings?\b", lower)
    ):
        signals.asks_booking_count = True

    if re.search(
        r"\b(?:worst|lowest|weakest|poorest|bottom)\s+month\b|\bwhich\s+month\b.*\b(?:worst|lowest|weakest|poorest|bottom)\b|\bwhat\s+month\b.*\b(?:worst|lowest|weakest|poorest|bottom)\b",
        lower,
    ):
        signals.asks_worst_month_history = True
    elif re.search(
        r"\b(?:best|highest|peak|strongest)\s+month\b|\bwhich\s+month\b.*\b(?:best|highest|peak|strongest)\b|\bwhat\s+month\b.*\b(?:best|highest|peak|strongest)\b",
        lower,
    ):
        signals.asks_best_month_history = True

    if any(
        k in lower
        for k in (
            "decision", "decisions", "recommend", "recommendations", "what if", "what-if", "playbook", "action plan",
            "قرار", "قرارات", "توصية", "توصيات", "اقترح", "اقتراح", "ماذا لو", "لو رفعنا", "سيناريو", "خطة عمل",
        )
    ):
        signals.asks_decisions_or_what_if = True

    # Detect Best / Worst / Trend / Single-Person intent
    if any(
        re.search(rf"\b{w}\b", lower)
        for w in ("better", "best", "top", "highest", "leader", "led", "leading", "star", "strongest", "number 1")
    ) or "#1" in lower:
        # Exclude "top negative contributors" from being treated as "best agent"
        if "negative" not in lower and "below target" not in lower and "loss" not in lower:
            signals.asks_best_agent = True

    if any(
        re.search(rf"\b{w}\b", lower)
        for w in ("worst", "lowest", "weakest", "bottom", "lagging", "poorest")
    ):
        signals.asks_worst_agent = True

    if any(
        re.search(rf"\b{w}\b", lower)
        for w in ("trend", "trends", "trajectory", "history", "monthly", "months", "progression")
    ) or "over time" in lower:
        signals.asks_trend = True

    asks_person_word = any(
        re.search(rf"\b{w}\b", lower)
        for w in ("who", "agent", "agents", "employee", "employees", "person", "people", "his", "her", "performer", "member", "members")
    )
    if any(
        phrase in lower
        for phrase in (
            "better agent",
            "best agent",
            "top agent",
            "top performer",
            "highest agent",
            "worst agent",
            "lowest agent",
            "weakest agent",
            "his trend",
            "her trend",
            "who is the",
            "who is better",
            "who is best",
            "who is worst",
        )
    ) or (asks_person_word and "agents" not in lower and "employees" not in lower and "contributors" not in lower):
        signals.asks_single_person = True

    # 3. Detect Month & Year
    for alias, canonical_month in MONTH_ALIASES.items():
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower):
            signals.detected_month = canonical_month
            signals.asks_specific_month_in_prompt = True
            break
    year_match = re.search(r"\b(202[4-9])\b", lower)
    if year_match:
        signals.detected_year = int(year_match.group(1))

    # 4. Detect KPI focus
    if any(k in lower for k in ("attendance", "attend", "حضور", "الحضور")):
        signals.detected_kpi = "Attendance"
    elif any(k in lower for k in ("booking", "bookings", "حجز", "حجوزات", "الحجوزات")):
        signals.detected_kpi = "Booking"
    elif any(k in lower for k in ("aht", "handle time", "وقت المكالمة", "زمن المكالمة")):
        signals.detected_kpi = "AHT"
    elif any(k in lower for k in ("abandon", "abandoned", "فقد", "المكالمات المفقودة")):
        signals.detected_kpi = "Other"
        if not signals.detected_team:
            signals.detected_team = "Inbound"
    elif any(k in lower for k in ("reachability", "reach", "الوصول")):
        signals.detected_kpi = "Other"
        if not signals.detected_team:
            signals.detected_team = "Outbound"
    elif any(k in lower for k in ("quality", "جودة", "الجودة")):
        signals.detected_kpi = "Quality"

    # 5. Detect Performance Level (Employee vs Managerial vs Corporate)
    if any(k in lower for k in ("corporate", "شركة", "قطاع", "كوربوريت")):
        signals.detected_level = "Corporate"
    elif any(k in lower for k in ("managerial", "balanced scorecard", "bsc", "team sla", "coaching", "مستوى الادارة", "مستوى الإدارة", "المديرين", "إداري")):
        signals.detected_level = "Managerial"

    # 6. Check Call Center Revenue Guardrail
    active_fn = (session_state.function or "").casefold()
    active_team = (signals.detected_team or session_state.team or "").casefold()
    is_cc_scope = active_team in ("inbound", "outbound", "support positions", "call center") or (
        not active_team and ("call center" in active_fn or not active_fn)
    )
    if is_cc_scope and any(rk in lower for rk in REVENUE_KEYWORDS):
        if signals.detected_team not in ("Marketing", "Sales", "Finance", "RCM", "Pharmacy", "CSR"):
            signals.asks_revenue_in_call_center = True

    # 7. Detect Employee Name / ID query (supports SGHD70xxx, EMP-xxx, or case-insensitive name phrases)
    emp_id_match = re.search(r"\b(sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", lower)
    if emp_id_match:
        signals.detected_employee_query = emp_id_match.group(1).upper()
    else:
        name_patterns = [
            r"\b([a-zA-Z]+(?:\s+[a-zA-Z]+)?)'s\b",
            r"\b(?:is|was|did)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+(?:a\s+new\s+joiner|new\s+in|join\b)",
            r"\bwhen\s+did\s+([a-zA-Z]+(?:\s+[a-zA-Z]+)?)\s+join\b",
            r"(?:employee|agent|for|about|trend of|trend for|score of|profile of)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
            r"(?:الموظف|موظف|ايجنت|أيجنت|عن)\s+([\u0600-\u06FFa-zA-Z]+(?:\s+[\u0600-\u06FFa-zA-Z]+)?)",
        ]
        stop_words = {
            "inbound", "outbound", "call", "center", "dubai", "sharjah", "ajman", "clinics",
            "all", "team", "teams", "branch", "branches", "the", "his", "her", "and", "in",
            "on", "at", "to", "from", "with", "who", "what", "which", "better", "best", "worst",
            "lowest", "top", "bottom", "trend", "month", "january", "february", "march", "april",
            "may", "june", "july", "august", "september", "october", "november", "december",
            "had", "has", "have", "was", "were", "is", "are", "led", "leads", "leading",
            "scored", "scores", "scoring", "performed", "performing", "performance", "score",
            "rate", "by", "for", "of", "support", "positions", "position", "employee", "employees",
            "agent", "agents", "performer", "performers", "highest",
        }
        for pat in name_patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                raw_tokens = [
                    tok for tok in m.group(1).strip().split()
                    if tok.casefold() not in stop_words
                ]
                if raw_tokens:
                    signals.detected_employee_query = " ".join(raw_tokens)
                    break

    # 8. Determine Primary Tool Intents
    intents: list[str] = []

    # High-priority specific spotlight & trend queries (returns 1 focused card without clutter)
    if signals.detected_employee_query or (
        asks_person_word and (signals.asks_best_agent or signals.asks_worst_agent or signals.asks_trend)
        and "negative contributors" not in lower
        and "caused" not in lower
    ):
        intents.append("agent_spotlight_trend")
    elif signals.asks_trend and not asks_person_word and not signals.asks_branch_comparison and not signals.asks_decisions_or_what_if:
        intents.append("team_trend_spotlight")

    if not intents:
        if signals.detected_level in ("Managerial", "Corporate") or any(
            k in lower for k in ("bsc", "scorecard", "managerial", "corporate", "sla", "مستوى الادارة", "مستوى الإدارة")
        ):
            intents.append("management_bsc")

        if any(
            k in lower
            for k in (
                "action", "actions", "corrective", "overdue",
                "خطة تصحيحية", "خطط تصحيحية", "اكشن", "أكشن", "متأخرة",
            )
        ):
            intents.append("corrective_actions")

        if any(
            k in lower
            for k in (
                "sip", "pip", "pi candidate", "attrition", "reward", "promotion", "training",
                "مرشح", "ترقية", "تدريب", "مخاطر ترك", "خطط الأداء",
            )
        ):
            intents.append("governance_plans")

        if any(
            k in lower
            for k in (
                "who", "agent", "agents", "employee", "employees", "person", "people", "caused", "contributors", "bottom", "lowest",
                "مين", "موظف", "موظفين", "شخص", "السبب", "المتسبب", "المتسببين", "أقل حد", "اكتر حد", "أكتر حد",
            )
        ):
            intents.append("people_contribution")

        if (
            any(
                k in lower
                for k in (
                    "kpi", "kpis", "metric", "attendance", "booking", "aht", "abandon", "reachability", "quality", "driver", "drivers", "trend",
                    "مؤشر", "مؤشرات", "تارجت", "الحضور", "الحجوزات", "الجودة", "بسبب ايه", "السبب في", "اكتر kpi",
                )
            )
            or signals.detected_kpi
            or signals.detected_compare_branch
            or signals.asks_branch_comparison
            or signals.asks_decisions_or_what_if
            or signals.asks_revenue_in_call_center
        ):
            intents.append("kpi_diagnosis")

        if signals.asks_decisions_or_what_if and "people_contribution" not in intents and not signals.asks_branch_comparison:
            intents.append("people_contribution")

        if any(
            k in lower
            for k in (
                "team", "teams", "which team", "dropped", "worst", "overview", "summary", "call center",
                "تيم", "فريق", "فرق", "أكتر تيم", "اكتر تيم", "واقع", "ملخص", "كول سنتر", "الكول سنتر",
            )
        ) or not intents:
            intents.insert(0, "executive_insights")

    # Deduplicate preserving order
    seen: set[str] = set()
    signals.primary_intents = [x for x in intents if not (x in seen or seen.add(x))]
    return signals


def build_call_center_guardrails() -> list[AiGuardrailItem]:
    """Static verifiable guardrails displayed in the Right Rail (modeled on ZainX Guardrails panel)."""
    return [
        AiGuardrailItem(
            label="Strict Read-Only Mode",
            description="Never creates, modifies, or approves evaluations or corrective actions on its own.",
            verified=True,
        ),
        AiGuardrailItem(
            label="Role & Scope Enforced (RBAC)",
            description="Only queries teams, branches, and performance levels granted to your role.",
            verified=True,
        ),
        AiGuardrailItem(
            label="Every Answer Cites Its Sources",
            description="Displays exact period, team, branch projection, and measured employee count.",
            verified=True,
        ),
        AiGuardrailItem(
            label="Official PMS Scoring Engine",
            description="Uses ratio aggregation, weighted AHT, 100% KPI cap, and Bookings/Attended volumes.",
            verified=True,
        ),
    ]


def build_call_center_starter_prompts(session_state: SessionFilterContext) -> list[AiStarterPrompt]:
    """Role- and filter-aware starter prompts for the empty state and scenario explorer."""
    is_cc = (
        (session_state.function or "").casefold() == "call center"
        or (session_state.team or "").casefold() in ("inbound", "outbound", "call center", "support positions")
    )
    team_label = (
        session_state.team
        if session_state.team and session_state.team != "All"
        else (session_state.function or ("Call Center" if is_cc else "All authorized departments"))
    )
    branch_label = session_state.branch.capitalize() if session_state.branch and session_state.branch != "all" else None
    scope_suffix = f" in {branch_label}" if branch_label else ""

    if not is_cc and team_label != "Call Center":
        return [
            AiStarterPrompt(
                id="team-drop",
                label=f"Which team in {team_label} dropped most?",
                subtitle="Identify the team with the largest performance drop and see key drivers.",
                badge="TEAM",
                prompt=f"Which team in {team_label} dropped the most this month{scope_suffix}, what is the main KPI driver, and what decisions do you recommend?",
                category="team",
                icon_key="users",
            ),
            AiStarterPrompt(
                id="people-root-cause",
                label=f"Top negative contributors in {team_label}",
                subtitle="Find the employees driving KPI gaps and coaching opportunities.",
                badge="PEOPLE",
                prompt=f"Who are the top negative contributors in {team_label}{scope_suffix} and what happens if we coach the bottom 3?",
                category="people",
                icon_key="users",
            ),
            AiStarterPrompt(
                id="branch-compare",
                label="Compare UAE Branches",
                subtitle="Compare performance and operational metrics across Dubai, Sharjah, Ajman, and Clinics.",
                badge="BRANCH",
                prompt=f"Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) performance for {team_label} and recommend branch decisions.",
                category="branch",
                icon_key="chart",
            ),
            AiStarterPrompt(
                id="governance-actions",
                label="Pending corrective actions",
                subtitle="Review open corrective actions and items with owners and due dates.",
                badge="GOVERNANCE",
                prompt=f"Summarize open or overdue corrective actions in {team_label} with recommended next steps.",
                category="governance",
                icon_key="shield",
            ),
            AiStarterPrompt(
                id="agent-spotlight-trend",
                label=f"Top performer in {team_label}",
                subtitle="Instant spotlight of top performer with score and trend.",
                badge="PEOPLE · TREND",
                prompt=f"Who is the top performer in {team_label} and what is their score trend?",
                category="people",
                icon_key="users",
            ),
        ]

    return [
        AiStarterPrompt(
            id="team-drop",
            label="Which Call Center team dropped most?",
            subtitle="Identify the team with the largest performance drop and see the key drivers (AHT, QA, Attendance, etc.).",
            badge="TEAM",
            prompt=f"Which Call Center team dropped the most this month{scope_suffix}, what is the main KPI driver, and what decisions do you recommend?",
            category="team",
            icon_key="users",
        ),
        AiStarterPrompt(
            id="people-root-cause",
            label="Who caused the Attendance gap?",
            subtitle="Find the employees driving the attendance gap, Pareto 80/20 concentration, and What-If coaching ROI.",
            badge="PEOPLE",
            prompt=f"Who are the top negative contributors to the Attendance Rate gap in {team_label}{scope_suffix} and what happens if we coach the bottom 3?",
            category="people",
            icon_key="users",
        ),
        AiStarterPrompt(
            id="branch-compare",
            label="Compare Dubai vs Sharjah & UAE Branches",
            subtitle="Compare performance, attendance, bookings, and no-shows across Dubai, Sharjah, Ajman, and Clinics.",
            badge="BRANCH",
            prompt=f"Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) Attendance and Booking conversion for {team_label} and recommend branch decisions.",
            category="branch",
            icon_key="chart",
        ),
        AiStarterPrompt(
            id="governance-actions",
            label="Pending corrective actions & SIP",
            subtitle="Review open corrective actions and SIP items, with owners, due dates, and current status.",
            badge="GOVERNANCE",
            prompt=f"Summarize open or overdue corrective actions and SIP/PI risk candidates in {team_label} with recommended next steps.",
            category="governance",
            icon_key="shield",
        ),
        AiStarterPrompt(
            id="agent-spotlight-trend",
            label="Best Agent & 6-Month Score Trend",
            subtitle="Instant spotlight of the #1 agent in Inbound or Outbound with grade, KPIs, and 6-month trend chart.",
            badge="PEOPLE · TREND",
            prompt=f"Who is the best agent in {team_label if team_label != 'Call Center' else 'Inbound'} and his trend?",
            category="people",
            icon_key="users",
        ),
        AiStarterPrompt(
            id="outbound-paradox",
            label="Diagnose Outbound Booking vs. No-Show",
            subtitle="Evaluate why Booking Rate is 100% while Patient Attendance is 56.6% and propose an executive decision playbook.",
            badge="KPI & DECISIONS",
            prompt="Diagnose Outbound KPIs (Attendance Rate, Reachability, Booking Rate) and propose an executive decision playbook to reduce patient no-shows.",
            category="kpi",
            icon_key="chart",
        ),
    ]

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

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
    "submission egy": "Submission EGY",
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

# Bare cross-country team names. These deliberately have NO entry in
# TEAM_ALIASES: without a country word, a single-region scope, or a scoped
# session team they are ambiguous, and signal extraction must not silently
# assign them to one country (previously UAE, or EGY for "resubmission").
# The router asks for clarification; see
# Backend/services/ai/catalog.py#BARE_CROSS_COUNTRY_TEAMS and
# Backend/services/ai/router.py#resolve_and_validate.
BARE_CROSS_COUNTRY_TEAM_ALIASES: dict[str, tuple[str, str]] = {
    "coding": ("Coding EGY", "Coding"),
    "submission": ("Submission EGY", "Submission"),
    "re-submission": ("Resubmission", "Re-Submission"),
    "resubmission": ("Resubmission", "Re-Submission"),
}


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
        or (
            re.search(r"how many\b.{0,50}\bbookings?\b", lower)
            and not re.search(r"\bbooking[\s-]+(?:rate|conversion)\b", lower)
        )
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
    ) or "over time" in lower or re.search(
        r"\b(?:score|monthly|trend)\s+pattern\b|\bacross\b.{0,25}\bmonths?\b",
        lower,
    ):
        signals.asks_trend = True

    asks_person_word = any(
        re.search(rf"\b{w}\b", lower)
        for w in ("who", "agent", "agents", "employee", "employees", "person", "people", "his", "her", "performer", "performers", "leader", "leaders", "member", "members")
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
    elif "policy rejection" in lower:
        signals.detected_kpi = "PolicyRejection"
    elif any(k in lower for k in ("rejection", "rejected", "مرفوض", "رفض")):
        signals.detected_kpi = "Rejection"
    elif "waiting time" in lower:
        signals.detected_kpi = "WaitingTime"
    elif re.search(r"\bcpl\b", lower):
        signals.detected_kpi = "mb_cpl"
    elif re.search(r"\bleads\b", lower):
        signals.detected_kpi = "mb_leads"
    elif "rework" in lower:
        signals.detected_kpi = "gd_rework"
    elif "response time" in lower:
        signals.detected_kpi = "sms_response_time"

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
            r"\b(?:how\s+did|what\s+did|how\s+is|how\s+was)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})\s+(?:score|perform|do|doing|rank)\b",
            r"(?:employee|agent|for|about|trend of|trend for|score of|profile of|show me|check|look at)\s+([a-zA-Z]+(?:\s+[a-zA-Z]+){0,2})",
            r"(?:الموظف|موظف|ايجنت|أيجنت|عن)\s+([\u0600-\u06FFa-zA-Z]+(?:\s+[\u0600-\u06FFa-zA-Z]+)?)",
        ]
        stop_words = {
            "inbound", "outbound", "call", "center", "dubai", "sharjah", "ajman", "clinics",
            "dxb", "shj", "ajm", "uae", "egy", "egypt", "emirates",
            "all", "team", "teams", "branch", "branches", "the", "his", "her", "him", "me", "their", "its", "this", "that", "and", "in", "instead",
            "on", "at", "to", "from", "with", "who", "what", "which", "better", "best", "worst",
            "lowest", "weakest", "strongest", "top", "bottom", "most", "fewest", "more", "less",
            "trend", "month", "months", "overall", "summary", "january", "february", "march", "april",
            "may", "june", "july", "august", "september", "october", "november", "december",
            "had", "has", "have", "was", "were", "is", "are", "led", "leads", "leading", "leader", "leaders",
            "generated", "achieved", "recorded", "delivered", "scored", "scores", "scoring",
            "performed", "performing", "performance", "score", "rate", "by", "for", "of",
            "support", "positions", "position", "role", "roles", "employee", "employees",
            "agent", "agents", "performer", "performers", "highest",
            "booking", "bookings", "attendance", "attended", "reachability", "abandon", "abandoned",
            "aht", "quality", "target", "targets", "gap", "gaps", "drop", "dropped", "dropping",
            "show", "tell", "give", "list", "find", "get", "display", "check", "within",
            "person", "people", "someone", "anyone", "everyone", "individual",
            "workforce", "analyst", "trainer", "assurance", "company", "everything", "things", "we", "they",
            "let", "lets", "she", "he", "there", "here", "where", "how", "when", "why",
            "pharmacy", "marketing", "coding", "submission", "resubmission", "rcm", "finance", "sales", "nursing", "pmo", "crm", "csr", "media", "buyer", "waiting", "time", "cpl",
        }
        import difflib
        person_search_text = re.sub(
            r"^\s*not\s+[a-zA-Z]+(?:\s+[a-zA-Z]+)?\s*(?:,|—|-)+\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )
        for index, pat in enumerate(name_patterns):
            m = re.search(pat, person_search_text, flags=re.IGNORECASE)
            if m:
                if index == 0 and re.match(
                    r"^(?:switch|go|see|check|look|review|be|been|got|have|is|are|was|were)\b",
                    person_search_text[m.end():].strip(),
                    flags=re.IGNORECASE,
                ):
                    continue
                raw_tokens = [
                    tok for tok in m.group(1).strip().split()
                    if tok.casefold() not in stop_words
                ]
                if raw_tokens:
                    if len(raw_tokens) == 1 and difflib.get_close_matches(
                        raw_tokens[0].casefold(),
                        ("inbound", "outbound", "marketing", "pharmacy", "finance", "nursing", "coding", "submission", "resubmission", "support", "collections"),
                        n=1,
                        cutoff=0.78,
                    ):
                        continue
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
                label="Compare branches",
                subtitle="Branch score comparison in your scope",
                badge="BRANCH",
                prompt=f"Compare branch performance for {team_label}{scope_suffix} and recommend branch decisions.",
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
            AiStarterPrompt(
                id="kpi-gaps",
                label=f"Largest KPI gaps ({team_label})",
                subtitle="Diagnose the lowest-achieving KPIs against target and focus areas.",
                badge="KPI & DECISIONS",
                prompt=f"What are the largest KPI gaps vs target in {team_label}{scope_suffix} and what decisions do you recommend?",
                category="kpi",
                icon_key="chart",
            ),
        ]

    team_cf = (session_state.team or "").strip().casefold()
    if team_cf == "inbound":
        cc_kpi_prompt = AiStarterPrompt(
            id="inbound-kpi-decisions",
            label="Inbound KPI Gaps & Queue Decisions",
            subtitle="Diagnose Abandon Rate, Booking Rate, and Attendance gaps with an executive decision playbook.",
            badge="KPI & DECISIONS",
            prompt=f"Diagnose Inbound KPIs (Abandon Rate, Booking Rate, Attendance Rate){scope_suffix} and propose an executive decision playbook.",
            category="kpi",
            icon_key="chart",
        )
    elif team_cf == "support positions":
        cc_kpi_prompt = AiStarterPrompt(
            id="support-kpi-decisions",
            label="Support Positions KPI Diagnosis",
            subtitle="Evaluate Support Positions KPI achievement vs target and role-level score drivers.",
            badge="KPI & DECISIONS",
            prompt=f"Diagnose Support Positions KPIs vs target{scope_suffix} and recommend targeted operational decisions.",
            category="kpi",
            icon_key="chart",
        )
    else:
        cc_kpi_prompt = AiStarterPrompt(
            id="outbound-paradox",
            label="Outbound Booking vs Attendance Gap",
            subtitle="Diagnose the gap between Outbound Booking Rate and Patient Attendance with an executive decision playbook.",
            badge="KPI & DECISIONS",
            prompt="Diagnose Outbound KPIs (Attendance Rate, Reachability, Booking Rate) and propose an executive decision playbook to reduce patient no-shows.",
            category="kpi",
            icon_key="chart",
        )

    region_cf = (session_state.region or "").strip().casefold()
    is_support_positions = team_cf == "support positions"
    is_egy_scope = region_cf in ("egy", "egypt") or "egy" in team_cf or "offshore" in team_cf
    is_uae_branch_cc = not is_support_positions and not is_egy_scope

    if is_support_positions:
        people_root_cause_prompt = AiStarterPrompt(
            id="people-root-cause",
            label="Top negative contributors in Support Positions",
            subtitle="Find the employees driving Support Positions KPI gaps and What-If coaching ROI.",
            badge="PEOPLE",
            prompt=f"Who are the top negative contributors to weighted KPI gaps in Support Positions{scope_suffix} and what happens if we coach the bottom 3?",
            category="people",
            icon_key="users",
        )
        branch_compare_prompt = AiStarterPrompt(
            id="branch-compare",
            label="Support Positions KPI drivers & trend",
            subtitle="Review role-level KPI achievement and month-over-month score drivers across Support Positions.",
            badge="BRANCH",
            prompt=f"Show verified KPI score drivers and 6-month trend for Support Positions{scope_suffix} and recommend operational decisions.",
            category="branch",
            icon_key="chart",
        )
        spotlight_prompt = AiStarterPrompt(
            id="agent-spotlight-trend",
            label="Top Performer & 6-Month Score Trend",
            subtitle="Instant spotlight of the #1 Support Positions performer with grade, KPIs, and 6-month trend chart.",
            badge="PEOPLE · TREND",
            prompt=f"Who is the best agent in Support Positions{scope_suffix} and his trend?",
            category="people",
            icon_key="users",
        )
    elif not is_uae_branch_cc:
        people_root_cause_prompt = AiStarterPrompt(
            id="people-root-cause",
            label=f"Top negative contributors in {team_label}",
            subtitle="Find the employees driving KPI gaps, Pareto concentration, and What-If coaching ROI.",
            badge="PEOPLE",
            prompt=f"Who are the top negative contributors in {team_label}{scope_suffix} and what happens if we coach the bottom 3?",
            category="people",
            icon_key="users",
        )
        branch_compare_prompt = AiStarterPrompt(
            id="branch-compare",
            label="Compare teams & scope KPIs",
            subtitle="Compare performance, SLA attainment, and score drivers across authorized teams in your scope.",
            badge="BRANCH",
            prompt=f"Compare team performance and KPI score drivers for {team_label}{scope_suffix} and recommend operational decisions.",
            category="branch",
            icon_key="chart",
        )
        spotlight_prompt = AiStarterPrompt(
            id="agent-spotlight-trend",
            label="Best Agent & 6-Month Score Trend",
            subtitle=f"Instant spotlight of the #1 performer in {team_label} with grade, KPIs, and 6-month trend chart.",
            badge="PEOPLE · TREND",
            prompt=f"Who is the best agent in {team_label}{scope_suffix} and his trend?",
            category="people",
            icon_key="users",
        )
    else:
        people_root_cause_prompt = AiStarterPrompt(
            id="people-root-cause",
            label="Who caused the Attendance gap?",
            subtitle="Find the employees driving the attendance gap, Pareto 80/20 concentration, and What-If coaching ROI.",
            badge="PEOPLE",
            prompt=f"Who are the top negative contributors to the Attendance Rate gap in {team_label}{scope_suffix} and what happens if we coach the bottom 3?",
            category="people",
            icon_key="users",
        )
        branch_compare_prompt = AiStarterPrompt(
            id="branch-compare",
            label="Compare Dubai vs Sharjah & UAE Branches",
            subtitle="Compare performance, attendance, bookings, and no-shows across Dubai, Sharjah, Ajman, and Clinics.",
            badge="BRANCH",
            prompt=f"Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) Attendance and Booking conversion for {team_label} and recommend branch decisions.",
            category="branch",
            icon_key="chart",
        )
        spotlight_prompt = AiStarterPrompt(
            id="agent-spotlight-trend",
            label="Best Agent & 6-Month Score Trend",
            subtitle="Instant spotlight of the #1 agent in Inbound or Outbound with grade, KPIs, and 6-month trend chart.",
            badge="PEOPLE · TREND",
            prompt=f"Who is the best agent in {team_label if team_label != 'Call Center' else 'Inbound'} and his trend?",
            category="people",
            icon_key="users",
        )

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
        people_root_cause_prompt,
        branch_compare_prompt,
        AiStarterPrompt(
            id="governance-actions",
            label="Pending corrective actions & SIP",
            subtitle="Review open corrective actions and SIP items, with owners, due dates, and current status.",
            badge="GOVERNANCE",
            prompt=f"Summarize open or overdue corrective actions and SIP/PI risk candidates in {team_label} with recommended next steps.",
            category="governance",
            icon_key="shield",
        ),
        spotlight_prompt,
        cc_kpi_prompt,
    ]


_GREETING_PROMPT_RE = re.compile(
    r"^\s*(?:hi|hello|hey|good morning|good afternoon|good evening)(?:\s+there)?[\s!.,?]*$",
    re.I,
)
_THANKS_PROMPT_RE = re.compile(
    r"^\s*(?:thanks|thank you|thx|ty|many thanks|thanks a lot|thank you so much|"
    r"got it,?\s*thanks|ok\s*thanks|okay\s*thanks|appreciate it|great,?\s*thanks|"
    r"thanks,?\s*(?:that was helpful|that helps)|thank you,?\s*(?:that was helpful|that helps))[\s!.,?]*$",
    re.I,
)

_CAPABILITIES_ANALYTICAL_EXCLUDE_RE = re.compile(
    r"\b(?:what\s+(?:is|are|was|were)|who\s+(?:is|are|was|were|performed|leads|had|has|scored)|"
    r"compare|versus|\bvs\b|trend|trajectory|dropped|drop|why\s+(?:did|is|are|was|were)|"
    r"lowest|worst|best|highest|top\s+\d+|diagnose|calculate|rank\s+|"
    r"how\s+many|overdue\s+corrective|most\s+bookings|best\s+month|worst\s+month|new\s+joiner)\b",
    re.I,
)

_CAPABILITIES_HELP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(?:hi[,!]?\s*)?help(?:\s+me)?(?:\s+please)?[\s?!.]*$", re.I),
    re.compile(
        r"^\s*(?:hi[,!]?\s*)?(?:how\s+(?:can|could|do)\s+(?:you|u|this\s+assistant|pms\s+ai)\s+"
        r"(?:help|assist|support)(?:\s+me)?)(?:\s+(?:with|for|on|in|about)\b.*)?[\s?!.]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:hi[,!]?\s*)?(?:what\s+(?:can|could)\s+(?:you|u|this\s+assistant|pms\s+ai)\s+"
        r"(?:do|help(?:\s+me)?(?:\s+with)?|assist(?:\s+me)?(?:\s+with)?|answer|support))(?:\s+(?:for|with|on|in|about|here)\b.*)?[\s?!.]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:hi[,!]?\s*)?(?:what\s+(?:questions|things|topics)\s+|what\s+all\s+|what\s+)can\s+i\s+ask(?:\s+you)?(?:\s+(?:about|for|here|on)\b.*)?[\s?!.]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:hi[,!]?\s*)?(?:what\s+(?:do\s+you\s+do|are\s+your\s+capabilities)|capabilities)(?:\s+(?:for|in|on)\b.*)?[\s?!.]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:hi[,!]?\s*)?(?:can|could)\s+(?:you|u)\s+help(?:\s+me)?(?:\s+(?:with|for|on)\s+(?:my\s+|the\s+|our\s+)?(?:team|teams|department|scope|work|pms|rcm|inbound|outbound|call\s+center|kpi|kpis|metrics?))?[\s?!.]*$",
        re.I,
    ),
)

_EXPLAIN_PREVIOUS_RE = re.compile(
    r"^\s*(?:"
    r"what\s+(?:do\s+you|did\s+you|do\s+u)\s+mean(?:\s+by\b.*)?|"
    r"what\s+does\s+(?:that|this|[\w.%+-]+(?:\s+[\w.%+-]+){0,3})\s+mean(?:\s+(?:here|in\s+(?:this|your)\s+(?:answer|reply|response)))?|"
    r"(?:please\s+|can\s+you\s+|could\s+you\s+)?(?:explain|clarify|elaborate\s+on|simplify|break\s+down)\s+"
    r"(?:that|this|it|your\s+(?:last\s+|previous\s+)?(?:answer|reply|response|point|conclusion|numbers?|figures?))"
    r"(?:\s+(?:more\s+)?(?:simply|in\s+(?:simple|plain|clear)\s+(?:words|terms|language)))?|"
    r"(?:can\s+you\s+|could\s+you\s+)?clarify(?:\s+that|\s+this|\s+please)?|"
    r"why\s+(?:do|did|are)\s+(?:you|u)\s+(?:say|call(?:ing)?)\s+(?:that|this|it)\b.*|"
    r"(?:which|what)\s+part\s+of\s+your\s+(?:last\s+|previous\s+)?(?:answer|reply|response|explanation)\s+(?:supports|shows|proves)\b.*|"
    r"what\s+(?:supports|backs\s+up)\s+(?:that|this|your)\s+(?:conclusion|claim|statement)\b.*|"
    r"i\s+(?:don'?t|do\s+not)\s+understand(?:\s+(?:that|this|it|what\s+you\s+mean))?"
    r")(?:\s+please)?\s*[?.!]*$",
    re.I,
)

_EXPLICIT_CORRECTION_RE = re.compile(
    r"(?:^\s*(?:"
    r"no\s*,?\s*(?:i\s+mean(?:t)?\b|not\b)|"
    r"sorry\s*,?\s*(?:i\s+mean(?:t)?\b|look\b|check\b|use\b|make\b)|"
    r"i\s+mean(?:t)?\b|"
    r"actually\s*(?:,|i\s+mean(?:t)?\b|check\b|look\b|show\b|use\b|try\b)|"
    r"not\s+[a-z][a-z\s]{1,30}(?:,|—|-)+\s*(?:show|check|use|give|look)\b|"
    r"make\s+(?:that|it)\b|"
    r"change\s+(?:that|it)\s+to\b|"
    r"switch\s+to\s+(?:the\s+)?(?:egypt|egy|uae|emirates|ksa|saudi\s+arabia)(?:\s+instead)?\s*[?.!]*$"
    r")|\binstead\s*[?.!]*$)",
    re.I,
)

_TOPIC_SWITCH_PREFIX_RE = re.compile(
    r"^\s*(?:now\s+(?:show|check|tell|give|compare|analyze|review|what|who|how|look)\b|"
    r"(?:let'?s\s+|alright\s*,?\s*)?switch(?:\s+gears)?\s+to\b|change\s+(?:topic|subject)\s+to\b|"
    r"moving\s+on\s+to\b|(?:different|new|separate|another)\s+question\b|on\s+another\s+note\b)",
    re.I,
)

_BARE_REFINEMENT_WORDS = frozenset(
    {
        "and", "what", "about", "how", "instead", "for", "in", "only", "the",
        "uae", "egy", "egypt", "emirates", "all",
        "dubai", "sharjah", "ajman", "clinics", "dxb", "shj", "ajm", "shjajm",
        "january", "jan", "february", "feb", "march", "mar", "april", "apr",
        "may", "june", "jun", "july", "jul", "august", "aug",
        "september", "sep", "sept", "october", "oct", "november", "nov", "december", "dec",
        "2024", "2025", "2026", "2027",
    }
)

_OFF_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:weather|forecast|temperature|rain(?:ing)?|sunny|poem|poetry|haiku|"
        r"football|soccer|basketball|tennis|cricket|world\s+cup|recipe|recipes|cook(?:ing)?|"
        r"pasta|pizza|joke|jokes|funny|horoscope|zodiac|movie|movies|film|netflix|"
        r"song|songs|music|lyrics|capital\s+of|president|prime\s+minister|bitcoin|crypto|"
        r"stock\s+price|celebrity|astronomy|planet|dinner|lunch|breakfast)\b",
        re.I,
    ),
    re.compile(
        r"^\s*(?:tell\s+me\s+(?:a\s+)?(?:joke|story|fun\s+fact)|"
        r"write\s+(?:a\s+)?(?:poem|story|song|code)|"
        r"who\s+won\s+the\s+(?:game|match|cup))\b",
        re.I,
    ),
)

_BROAD_OVERVIEW_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bhow\s+(?:are|is|were|did)\s+(?:we|the\s+company|things|everything|performance|it)\s+(?:doing|performing|going|looking)\b",
        re.I,
    ),
    re.compile(
        r"\bhow\s+(?:am\s+i|is\s+my\s+team|did\s+we)\s+(?:doing|performing|perform)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:overall|executive|company|organization)\s+(?:performance|score|summary|overview|standing|results?)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:give\s+me|show(?:\s+me)?)\s+(?:an?\s+)?(?:overall|executive|performance)\s+(?:overview|summary|score|report|status)\b",
        re.I,
    ),
    re.compile(
        r"\bwhat\s+is\s+(?:our|the|my)\s+(?:overall\s+)?(?:score|performance|standing)\b",
        re.I,
    ),
    re.compile(r"\b(?:all\s+authorized\s+departments?|authorized\s+scope)\b", re.I),
    re.compile(r"^\s*show\s+(?:my\s+)?performance\s+summary\b", re.I),
)

_VAGUE_DATALESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^\s*(?:check|look\s+at|show(?:\s+me)?|give\s+me|tell\s+me|analyze|review|inspect|see)\s+"
        r"(?:the\s+)?(?:numbers?|data|stats|figures|metrics|it|this|that|everything|something)\s*[?.!]*$",
        re.I,
    ),
    re.compile(
        r"^\s*(?:show\s+me|anything|anything\s+new|tell\s+me\s+more|more|details|info|status|update|updates|check)\s*[?.!]*$",
        re.I,
    ),
)

_SECURITY_OR_MUTATION_RE = re.compile(
    r"\b(?:delete|update|recalculate|approve|modify|drop)\b.*\b(?:evaluation|target|scores?|table)\b"
    r"|\b(?:ignore|disregard|forget)\b.*\b(?:instructions?|policy|policies|rules|guidelines|permissions?|access\s+rules|previous)\b"
    r"|\b(?:system\s+prompt|developer\s+mode|jailbreak|system\s+override|unrestricted|list\s+every\s+employee\s+score|salar(?:y|ies)|other\s+country)\b",
    re.I,
)

# Core PMS entities, KPIs, and analytical words (excludes bare branch cities and bare periods so "October" or "weather in Dubai" stays gated cleanly).
_PMS_ENTITY_OR_KPI_RE = re.compile(
    r"\b(?:score|scores|scored|scoring|kpi|kpis|metric|metrics|target|targets|booking|bookings|"
    r"attended|attendance|abandon|abandoned|reachability|aht|fcr|qa|quality|sla|compliance|"
    r"resubmission|re-submission|submission|coding|pre-approvals?|collections|denial|rejection|"
    r"revenue|sales|marketing|pharmacy|csr|finance|human\s+resources|crm|nursing|pmo|rcm|"
    r"inbound|outbound|call\s+center|support\s+positions?|support\s+team|scorecard|scorecards|bsc|balanced\s+scorecard|"
    r"corrective\s+actions?|action\s+plan|pip|sip|grade|grades|ranking|rank|ranks|"
    r"top\s+performers?|top\s+agents?|best\s+agents?|worst\s+agents?|lowest|highest|weakest|strongest|"
    r"bottom\s+agents?|leader|leaders|leading|leads|driver|drivers|gap|gaps|trend|trends|trajectory|"
    r"progression|over\s+time|6-month|compare|comparison|versus|vs|diagnose|root\s+cause|dragging|"
    r"pulling|below\s+target|dropped|drop|dropping|decline|declined|fell|fall|improve|improved|"
    r"improvement|underperform|overdue|joiner|joiners|joined|joining|hire\s+date|tenure|evaluation|"
    r"evaluations|managerial|corporate|sghd\d+|emp[-_ ]?\d+|e[-_]\d+|"
    r"employee|employees|agent|agents)\b",
    re.I,
)

_PMS_ANALYTICAL_INTENT_RE = re.compile(
    r"\b(?:score|scores|scored|scoring|kpi|kpis|metric|metrics|target|targets|booking|bookings|"
    r"attended|attendance|abandon|abandoned|reachability|aht|fcr|qa|quality|sla|compliance|"
    r"rejection|resubmission|re-submission|submission|coding|pre-approvals?|collections|denial|"
    r"operational|volume|volumes|revenue|revenues|perform|performs|performing|performed|focus|prioritize|priorities|"
    r"waiting\s+time|cpl|cpv|leads|rework|response\s+time|leakage|tender\s+compliance|atv|media\s+buyer|"
    r"scorecard|scorecards|bsc|balanced\s+scorecard|corrective\s+actions?|action\s+plan|"
    r"ranking|rank|ranks|top|best|worst|lowest|highest|weakest|strongest|bottom|leader|leaders|leading|leads|"
    r"driver|drivers|gap|gaps|trend|trends|trajectory|progression|over\s+time|6-month|"
    r"compare|comparison|versus|vs|diagnose|root\s+cause|dragging|pulling|below\s+target|"
    r"dropped|drop|dropping|decline|declined|fell|fall|overdue|joiner|joiners|joined|joining|"
    r"hire\s+date|tenure|position|role|title|performance|result|results)\b",
    re.I,
)

_PMS_BRANCH_OR_PERIOD_RE = re.compile(
    r"\b(?:dubai|sharjah|ajman|clinics|dxb|shj|ajm|shjajm|egy|egypt|uae|emirates|"
    r"january|jan|february|feb|march|mar|april|apr|may|june|jun|july|jul|"
    r"august|aug|september|sep|sept|october|oct|november|nov|december|dec|202\d)\b",
    re.I,
)

_ARABIC_PMS_KEYWORDS: tuple[str, ...] = (
    "أداء", "اداء", "نتيجة", "مؤشر", "مؤشرات", "تقييم", "حضور", "الحضور", "حجز", "حجوزات",
    "جودة", "انباوند", "إنباوند", "اوتباوند", "أوتباوند", "ماركتنج", "التسويق", "دبي",
    "الشارقة", "عجمان", "موظف", "الموظف", "كول سنتر", "ايراد", "إيراد",
    "خطة", "ملخص", "تارجت", "واقع", "السبب",
)


def is_greeting_or_thanks_prompt(prompt: str) -> Literal["greeting", "thanks"] | None:
    text = (prompt or "").strip()
    if _GREETING_PROMPT_RE.fullmatch(text):
        return "greeting"
    if _THANKS_PROMPT_RE.fullmatch(text):
        return "thanks"
    return None


def is_capabilities_help_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    if _CAPABILITIES_ANALYTICAL_EXCLUDE_RE.search(text):
        return False
    return any(pat.match(text) for pat in _CAPABILITIES_HELP_PATTERNS)


def is_explain_previous_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    return bool(_EXPLAIN_PREVIOUS_RE.match(text))


def is_explicit_correction_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    return bool(_EXPLICIT_CORRECTION_RE.match(text))


def is_topic_switch_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    m = _TOPIC_SWITCH_PREFIX_RE.match(text)
    if not m:
        return False
    remainder = text[m.end():].strip(" ,.?!:-")
    if remainder and is_bare_scope_or_period_refinement(remainder):
        return False
    return True


def is_bare_scope_or_period_refinement(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    tokens = re.findall(r"[A-Za-z0-9]+", text.casefold())
    if not tokens or len(tokens) > 4:
        return False
    has_scope_or_period = any(_PMS_BRANCH_OR_PERIOD_RE.fullmatch(tok) for tok in tokens)
    if not has_scope_or_period:
        return False
    return all(tok in _BARE_REFINEMENT_WORDS for tok in tokens)


def is_off_topic_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    if _PMS_ENTITY_OR_KPI_RE.search(text):
        return False
    return any(pat.search(text) for pat in _OFF_TOPIC_PATTERNS)


_SELF_SERVICE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:how\s+am\s+i|how\s+am\s+doing|my\s+(?:score|performance|numbers|kpi[s]?|results?))\b", re.I),
    re.compile(r"\b(?:what(?:'s| is)\s+my\s+(?:score|performance|numbers|kpi[s]?|results?))\b", re.I),
    re.compile(r"\b(?:show\s+me\s+my\s+(?:score|performance|numbers|kpi[s]?|results?|profile|scorecard))\b", re.I),
    re.compile(r"\b(?:my\s+(?:trend|history|corrective\s+actions?|coaching))\b", re.I),
    re.compile(r"\b(?:am\s+i\s+(?:doing|performing)\s+(?:well|ok|okay|good|bad))\b", re.I),
)


def is_self_service_prompt(prompt: str) -> bool:
    """Check if the prompt is asking about the user's own data."""
    text = (prompt or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _SELF_SERVICE_PATTERNS)


def is_broad_overview_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    return any(pat.search(text) for pat in _BROAD_OVERVIEW_PATTERNS)


def is_vague_dataless_prompt(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text:
        return False
    return any(pat.match(text) for pat in _VAGUE_DATALESS_PATTERNS)


def has_pms_performance_signal(prompt: str) -> bool:
    text = (prompt or "").strip()
    if not text or is_off_topic_prompt(text) or is_capabilities_help_prompt(text) or is_explain_previous_prompt(text):
        return False
    if is_bare_scope_or_period_refinement(text):
        return False
    if is_broad_overview_prompt(text) or _SECURITY_OR_MUTATION_RE.search(text):
        return True
    if re.search(r"\b(?:sghd\d+|emp[-_ ]?\d+|e[-_]\d+)\b", text, re.I):
        return True
    if _PMS_ANALYTICAL_INTENT_RE.search(text):
        return True
    lower = text.casefold()
    if any(
        re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower)
        for alias in (*TEAM_ALIASES.keys(), *BARE_CROSS_COUNTRY_TEAM_ALIASES.keys())
    ):
        return True
    if re.search(r"\bwho\s+(?:is|are|was|were)\s+[A-Z][a-z]+", text):
        return True
    if re.search(
        r"\b[A-Za-z]+(?:'s|’s)\s+(?:score|performance|position|role|trend|best|worst|highest|lowest)\b",
        text,
        re.I,
    ):
        return True
    if is_arabic_text(text) and any(kw in text for kw in _ARABIC_PMS_KEYWORDS):
        return True
    return False

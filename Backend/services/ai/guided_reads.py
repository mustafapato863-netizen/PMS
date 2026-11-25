"""Guided read-only workflows, searchable product guide, compound requests, and target assessment.

Activated behind ``AiRuntimeConfig.guided_reads_enabled`` (env
``PMS_AI_GUIDED_READS_ENABLED``). Turning the switch off restores the previous
orchestrator path without any database migration.
"""
from __future__ import annotations

import datetime as dt
import os
import re
import time
from dataclasses import dataclass
from typing import Any

from models.ai_schemas import (
    AiChatRequest,
    AiChatResponsePayload,
    AiNavigationTarget,
    AiProviderUsageMetrics,
    AiToolCallRecord,
    AiTurnTimingBreakdown,
    ConfirmedQueryContext,
    QueryOperationV2,
    QueryScopeV2,
    SessionFilterContext,
    StructuredQueryPlan,
    ValidatedQueryPlanV2,
)
from services.ai.contextual_assistant import (
    build_effective_context_label,
    is_self_only,
)
from services.ai.domain_policies import (
    BRANCH_ALIASES,
    TEAM_ALIASES,
    is_off_topic_prompt,
)
from services.ai.tool_registry import (
    DeterministicToolRegistry,
    ToolExecutionContext,
    ToolExecutionResult,
)
from utils.report_scope import function_for_team, user_can_access_team_level

_MONTH_NAME_MAP: dict[str, tuple[str, int]] = {
    "january": ("January", 1), "jan": ("January", 1),
    "february": ("February", 2), "feb": ("February", 2),
    "march": ("March", 3), "mar": ("March", 3),
    "april": ("April", 4), "apr": ("April", 4),
    "may": ("May", 5),
    "june": ("June", 6), "jun": ("June", 6),
    "july": ("July", 7), "jul": ("July", 7),
    "august": ("August", 8), "aug": ("August", 8),
    "september": ("September", 9), "sep": ("September", 9), "sept": ("September", 9),
    "october": ("October", 10), "oct": ("October", 10),
    "november": ("November", 11), "nov": ("November", 11),
    "december": ("December", 12), "dec": ("December", 12),
}

_MUTATION_OR_WRITE_RE = re.compile(
    r"\b(?:create|add|assign|draft|propose|update|edit|change|mark|close|complete|cancel|delete|remove|drop|approve|apply)\s+"
    r"(?:a\s+|an\s+|the\s+|all\s+)?(?:new\s+)?(?:corrective\s+)?(?:actions?|pip|coaching|plan|warning|records?|evaluation)\b",
    re.I,
)

_ACTION_NOUN_RE = re.compile(
    r"\b(?:corrective\s+actions?|correctiv\w*\s+act\w*|action\s+items?|follow[- ]?up\s+actions?)\b"
    r"|الإجراءات\s+التصحيحية|الاجراءات\s+التصحيحية",
    re.I,
)

_ACTION_READ_VERB_RE = re.compile(
    r"\b(?:show|list|get|display|fetch|pull|check|see|view|count|how\s+many|what\s+are|which|give\s+me)\b"
    r"|اعرض|أعرض|كم",
    re.I,
)

_GUIDE_CUE_RE = re.compile(
    r"\b(?:where\s+(?:can|do|should)\s+i|where\s+(?:is|are|to)|how\s+(?:can|do|should)\s+i|"
    r"tell\s+me\s+(?:where|how|a?\s*br[ie]{1,2}f)|give\s+me\s+(?:a\s+)?(?:br[ie]{1,2}f|overview|guide)|"
    r"explain\s+how\s+to|steps\s+to|walk\s+me\s+through|what\s+is\s+(?:this\s+system|pms)|"
    r"system\s+overview|product\s+overview|follow[- ]?up\s+(?:page|tab|screen|steps|instructions))\b"
    r"|وين|فين|كيف\s+(?:اشوف|أشوف|اتابع|أتابع)|نظرة\s+عامة|ملخص\s+النظام",
    re.I,
)

_GUIDE_COMPOUND_CUE_RE = re.compile(
    r"\b(?:and\s+(?:tell\s+me\s+)?(?:where|how)\b|plus\s+(?:where|how)\b|where\s+to\s+follow\s+up\b|"
    r"how\s+to\s+(?:follow\s+up|filter|find|open|view)\b)",
    re.I,
)

_MONTHLY_EVAL_GUIDE_RE = re.compile(
    r"\b(?:monthly\s+evaluation|evaluation\s+settings|save\s+preview\s+approve\s+apply|"
    r"approve\s+and\s+apply|revise\s+this\s+month|monthly\s+rules)\b"
    r"|التقييم\s+الشهري|اعدادات\s+التقييم",
    re.I,
)

_OVERVIEW_GUIDE_RE = re.compile(
    r"\b(?:tell\s+me\s+(?:a\s+)?br[ie]{1,2}f\s+(?:for|about|of)\s+(?:the\s+)?system|"
    r"(?:system|pms|product)\s+(?:overview|brief|breef|summary|guide)|"
    r"what\s+is\s+(?:this\s+system|pms))\b"
    r"|نظرة\s+عامة\s+على\s+النظام|ملخص\s+النظام",
    re.I,
)

_TEAM_GUIDE_RE = re.compile(
    r"\b(?:how\s+(?:can|do)\s+i\s+(?:check|view|find|open|see|select)\s+(?:a\s+)?(?:spec[if]{1,3}c\s+)?team|"
    r"where\s+(?:can|do)\s+i\s+(?:check|view|find|open|see)\s+(?:a\s+)?(?:spec[if]{1,3}c\s+)?team|"
    r"how\s+to\s+(?:check|view|open|select)\s+(?:a\s+)?(?:spec[if]{1,3}c\s+)?team)\b"
    r"|كيف\s+(?:اشوف|أشوف)\s+فريق",
    re.I,
)

_TARGET_ASSESSMENT_RE = re.compile(
    r"\b(?:should\s+we\s+(?:adjust|change|lower|raise|revise|update|keep)\s+(?:the\s+)?(?:outbound\s+)?(?:reachability\s+)?target|"
    r"(?:assess|evaluate|review)\s+(?:the\s+)?(?:outbound\s+)?reachability\s+target|"
    r"what\s+if\s+we\s+(?:adjust|change|lower|raise|set)\s+(?:the\s+)?(?:outbound\s+)?(?:reachability\s+)?target|"
    r"hypothetical\s+(?:reachability\s+)?target)\b",
    re.I,
)

_STATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("overdue", re.compile(r"\b(?:over\s*du\w*|past[- ]due|late)\b|المتأخر[ةه]?|متأخر[ةه]?", re.I)),
    ("due_soon", re.compile(r"\b(?:due\s+soon|due\s+this\s+week)\b", re.I)),
    ("upcoming", re.compile(r"\bupcoming\b", re.I)),
    ("no_due_date", re.compile(r"\bno\s+due\s+date\b", re.I)),
    ("completed", re.compile(r"\b(?:completed|closed|finished|done)\b|المكتمل[ةه]?", re.I)),
    ("cancelled", re.compile(r"\bcancell?ed\b", re.I)),
)


def get_reference_today() -> dt.date | None:
    """Optional frozen PMS reference date override via ``PMS_AI_REFERENCE_DATE`` (YYYY-MM-DD)."""
    raw = (os.environ.get("PMS_AI_REFERENCE_DATE") or "").strip()
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _detect_action_state(prompt: str) -> str | None:
    for canonical, pat in _STATE_PATTERNS:
        if pat.search(prompt):
            return canonical
    return None


def _detect_explicit_team(prompt: str) -> str | None:
    lower = (prompt or "").casefold()
    for alias, canonical in sorted(TEAM_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower):
            return canonical
    return None


def _detect_explicit_branches(prompt: str) -> list[str]:
    lower = (prompt or "").casefold()
    found: list[str] = []
    for alias, canonical in sorted(BRANCH_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower):
            if canonical not in found:
                found.append(canonical)
    return found


def _detect_explicit_period(prompt: str) -> tuple[str | None, int | None, str | None]:
    lower = (prompt or "").casefold()
    m_month: str | None = None
    m_num: int | None = None
    for token, (canonical, num) in sorted(_MONTH_NAME_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"\b{re.escape(token)}\b", lower):
            m_month, m_num = canonical, num
            break
    m_year_match = re.search(r"\b(202[4-9]|203\d)\b", lower)
    m_year = int(m_year_match.group(1)) if m_year_match else None
    if m_month and m_num:
        eff_year = m_year or (get_reference_today() or dt.date.today()).year
        return m_month, eff_year, f"{eff_year}-{m_num:02d}"
    return None, m_year, None


def _detect_hypothetical_target(prompt: str) -> float | None:
    m = re.search(r"\b(?:to|at)\s+(\d{1,3}(?:\.\d+)?)\s*%?", prompt, re.I)
    if m:
        val = float(m.group(1))
        if 0 < val <= 100:
            return val
    return None


def _check_requested_scope_access(
    scope: dict[str, Any],
    *,
    team: str | None,
    branches: list[str],
    performance_level: str = "Employee",
) -> str | None:
    """Return a refusal reason if the user lacks access to the requested team or branch."""
    if is_self_only(scope):
        if team:
            return f"Access restricted: your Employee role is scoped to your own scorecard and cannot query {team} team records."
    if team:
        if not user_can_access_team_level(scope, team, performance_level):
            return f"Access restricted: your current PMS permissions do not include {team}."
    allowed_branches = [str(b).strip().casefold() for b in (scope.get("accessible_branches") or scope.get("allowed_branches") or []) if str(b).strip()]
    if allowed_branches and branches:
        disallowed = [b for b in branches if b.casefold() not in allowed_branches]
        if disallowed:
            return f"Access restricted: your branch permissions do not include {', '.join(d.title() for d in disallowed)}."
    return None


@dataclass
class GuidedReadIntent:
    operations: list[QueryOperationV2]
    team: str | None = None
    function: str | None = None
    month: str | None = None
    year: int | None = None
    period_key: str | None = None
    branches: tuple[str, ...] = ()
    region: str | None = None
    action_state: str | None = None
    workflow_kind: str = "corrective_actions"
    apply_period_filter: bool = False
    inherited_filters: tuple[str, ...] = ()


def detect_guided_read_intent(
    prompt: str,
    session_state: SessionFilterContext,
) -> GuidedReadIntent | None:
    """Classify corrective-action reads, searchable product guide, compound requests, and Reachability target assessments."""
    text = (prompt or "").strip()
    if not text or is_off_topic_prompt(text):
        return None
    # Never intercept write/mutation/proposal requests ("create an action", "delete all actions")
    if _MUTATION_OR_WRITE_RE.search(text) and not _GUIDE_CUE_RE.search(text) and not _MONTHLY_EVAL_GUIDE_RE.search(text):
        return None

    prior = session_state.last_confirmed_query
    prior_is_ca = bool(prior and (prior.workflow_kind == "corrective_actions" or prior.intent == "corrective_actions"))
    prior_is_reachability = bool(
        prior
        and (
            prior.workflow_kind == "target_assessment"
            or (prior.metric_id and "reachability" in prior.metric_id.casefold())
            or (prior.team == "Outbound" and prior.metric_display_name and "reachability" in prior.metric_display_name.casefold())
        )
    )

    explicit_team = _detect_explicit_team(text)
    explicit_branches = _detect_explicit_branches(text)
    explicit_month, explicit_year, explicit_period_key = _detect_explicit_period(text)
    explicit_state = _detect_action_state(text)
    lower = text.casefold()

    # ------------------------------------------------------------------
    # 1. Outbound Reachability target assessment (Step 4.5)
    # ------------------------------------------------------------------
    mentions_reachability = bool(re.search(r"\breachability\b", lower))
    if _TARGET_ASSESSMENT_RE.search(text) and (
        mentions_reachability or explicit_team == "Outbound" or prior_is_reachability or session_state.team == "Outbound"
    ):
        hyp_target = _detect_hypothetical_target(text)
        args: dict[str, Any] = {"metric_id": "outbound:reachability", "team": "Outbound"}
        if hyp_target is not None:
            args["hypothetical_target"] = hyp_target
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="target_assessment",
                    metric_id="outbound:reachability",
                    args=args,
                )
            ],
            team="Outbound",
            function="Call Center",
            month=explicit_month,
            year=explicit_year,
            period_key=explicit_period_key,
            branches=tuple(explicit_branches),
            workflow_kind="target_assessment",
            apply_period_filter=bool(explicit_month or explicit_year),
        )

    # ------------------------------------------------------------------
    # 2. Compound or single Corrective Actions + Guide workflows (Steps 4.2 & 4.3)
    # ------------------------------------------------------------------
    has_action_noun = bool(_ACTION_NOUN_RE.search(text))
    has_read_verb = bool(_ACTION_READ_VERB_RE.search(text))
    has_guide_cue = bool(_GUIDE_CUE_RE.search(text))
    has_compound_guide = bool(_GUIDE_COMPOUND_CUE_RE.search(text))

    # Pure navigation/how-to question about corrective actions ("Where can I see corrective actions?")
    is_pure_ca_guide = bool(
        has_action_noun
        and has_guide_cue
        and not (
            explicit_state
            and re.search(r"\b(?:show|list|get|display|fetch|how\s+many|count|give\s+me)\b", lower)
        )
        and re.match(r"^\s*(?:where|how|can\s+you\s+tell\s+me\s+where|tell\s+me\s+where|وين|فين|كيف)\b", lower)
    )
    if is_pure_ca_guide:
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="guide_lookup",
                    args={"query": text, "page_id": "corrective_actions"},
                )
            ],
            team=explicit_team,
            function=function_for_team(explicit_team) if explicit_team else None,
            month=explicit_month,
            year=explicit_year,
            period_key=explicit_period_key,
            branches=tuple(explicit_branches),
            workflow_kind="guide_lookup",
        )

    # Compound: corrective actions read + follow-up guide ("Show overdue corrective actions and tell me where to follow up.")
    if has_action_noun and (has_read_verb or explicit_state) and (has_compound_guide or has_guide_cue):
        eff_team = explicit_team or (prior.team if prior_is_ca and prior else None)
        eff_fn = function_for_team(eff_team) if eff_team else (prior.function if prior_is_ca and prior else None)
        inherited: list[str] = []
        if not explicit_team and eff_team:
            inherited.append("team")
        eff_month, eff_year, eff_pkey = explicit_month, explicit_year, explicit_period_key
        apply_period = bool(explicit_month or explicit_year)
        if not apply_period and prior_is_ca and prior and prior.periods:
            eff_pkey = prior.periods[-1]
            y_s, m_s = eff_pkey.split("-")
            eff_year = int(y_s)
            eff_month = next((name for name, num in _MONTH_NAME_MAP.values() if num == int(m_s)), None)
            apply_period = bool(eff_month and eff_year)
            if apply_period:
                inherited.append("periods")

        ca_args: dict[str, Any] = {}
        if explicit_state:
            ca_args["state"] = explicit_state
        if eff_team:
            ca_args["team"] = eff_team
        if apply_period and eff_month:
            ca_args["month"] = eff_month
            ca_args["year"] = eff_year

        guide_q = "corrective action follow-up"
        if explicit_state == "overdue":
            guide_q = "corrective action follow-up overdue"
        elif explicit_state:
            guide_q = f"filter corrective actions {explicit_state}"

        return GuidedReadIntent(
            operations=[
                QueryOperationV2(operation_id="op_1", kind="corrective_actions", args=ca_args),
                QueryOperationV2(
                    operation_id="op_2",
                    kind="guide_lookup",
                    args={"query": guide_q, "page_id": "corrective_actions"},
                ),
            ],
            team=eff_team,
            function=eff_fn,
            month=eff_month if apply_period else None,
            year=eff_year if apply_period else None,
            period_key=eff_pkey if apply_period else None,
            branches=tuple(explicit_branches),
            action_state=explicit_state,
            workflow_kind="corrective_actions",
            apply_period_filter=apply_period,
            inherited_filters=tuple(inherited),
        )

    # Single-op corrective actions read ("Show overdue corrective actions.", "Show past due corrective actions.")
    if has_action_noun and (has_read_verb or explicit_state):
        eff_team = explicit_team or (prior.team if prior_is_ca and prior else None)
        eff_fn = function_for_team(eff_team) if eff_team else (prior.function if prior_is_ca and prior else None)
        inherited = []
        if not explicit_team and eff_team:
            inherited.append("team")
        eff_month, eff_year, eff_pkey = explicit_month, explicit_year, explicit_period_key
        apply_period = bool(explicit_month or explicit_year)
        if not apply_period and prior_is_ca and prior and prior.periods:
            eff_pkey = prior.periods[-1]
            y_s, m_s = eff_pkey.split("-")
            eff_year = int(y_s)
            eff_month = next((name for name, num in _MONTH_NAME_MAP.values() if num == int(m_s)), None)
            apply_period = bool(eff_month and eff_year)
            if apply_period:
                inherited.append("periods")

        ca_args = {}
        if explicit_state:
            ca_args["state"] = explicit_state
        if eff_team:
            ca_args["team"] = eff_team
        if apply_period and eff_month:
            ca_args["month"] = eff_month
            ca_args["year"] = eff_year

        return GuidedReadIntent(
            operations=[QueryOperationV2(operation_id="op_1", kind="corrective_actions", args=ca_args)],
            team=eff_team,
            function=eff_fn,
            month=eff_month if apply_period else None,
            year=eff_year if apply_period else None,
            period_key=eff_pkey if apply_period else None,
            branches=tuple(explicit_branches),
            action_state=explicit_state,
            workflow_kind="corrective_actions",
            apply_period_filter=apply_period,
            inherited_filters=tuple(inherited),
        )

    # Follow-up turns within an active corrective-actions workflow:
    # - "Show completed ones." / "What about overdue?" / "Now upcoming ones"
    # - "What about Outbound?" / "In Inbound?" / "And September 2026?"
    is_short_followup = len(text.split()) <= 8
    if prior_is_ca and prior is not None and is_short_followup:
        is_state_switch = bool(explicit_state and not re.search(r"\b(?:score|kpi|trend|ranking|waiting\s+time|booking)\b", lower))
        is_team_or_period_switch = bool(
            (explicit_team or explicit_month or explicit_branches)
            and re.match(r"^\s*(?:what\s+about|how\s+about|and\s+(?:in|for)?|in|for|only|show|now)\b", lower)
            and not re.search(r"\b(?:score|kpi|trend|ranking|waiting\s+time|booking|reachability)\b", lower)
        )
        if is_state_switch or is_team_or_period_switch:
            eff_state = explicit_state or prior.action_state
            eff_team = explicit_team if explicit_team is not None else prior.team
            eff_fn = function_for_team(eff_team) if eff_team else prior.function
            inherited = []
            if not explicit_state and eff_state:
                inherited.append("action_state")
            if explicit_team is None and eff_team:
                inherited.append("team")
            eff_month, eff_year, eff_pkey = explicit_month, explicit_year, explicit_period_key
            apply_period = bool(explicit_month or explicit_year)
            if not apply_period and prior.periods:
                eff_pkey = prior.periods[-1]
                y_s, m_s = eff_pkey.split("-")
                eff_year = int(y_s)
                eff_month = next((name for name, num in _MONTH_NAME_MAP.values() if num == int(m_s)), None)
                apply_period = bool(eff_month and eff_year)
                if apply_period:
                    inherited.append("periods")

            ca_args = {}
            if eff_state:
                ca_args["state"] = eff_state
            if eff_team:
                ca_args["team"] = eff_team
            if apply_period and eff_month:
                ca_args["month"] = eff_month
                ca_args["year"] = eff_year

            return GuidedReadIntent(
                operations=[QueryOperationV2(operation_id="op_1", kind="corrective_actions", args=ca_args)],
                team=eff_team,
                function=eff_fn,
                month=eff_month if apply_period else None,
                year=eff_year if apply_period else None,
                period_key=eff_pkey if apply_period else None,
                branches=tuple(explicit_branches),
                action_state=eff_state,
                workflow_kind="corrective_actions",
                apply_period_filter=apply_period,
                inherited_filters=tuple(inherited),
            )

    # ------------------------------------------------------------------
    # 3. Expanded Product Guide: PMS Overview, Team Navigation, Monthly Evaluation (Step 4.4)
    # ------------------------------------------------------------------
    if _OVERVIEW_GUIDE_RE.search(text):
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="guide_lookup",
                    args={"query": text, "page_id": "overview"},
                )
            ],
            workflow_kind="guide_lookup",
        )

    if _MONTHLY_EVAL_GUIDE_RE.search(text) and (
        has_guide_cue or re.search(r"\b(?:how|where|explain|steps|workflow|save|preview|approve|apply|revise)\b", lower)
    ):
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="guide_lookup",
                    args={"query": text, "page_id": "monthly_evaluation"},
                )
            ],
            workflow_kind="guide_lookup",
        )

    if _TEAM_GUIDE_RE.search(text) or (
        explicit_team
        and re.match(r"^\s*(?:where|how)\s+(?:can|do)\s+i\s+(?:check|view|find|open|see)\b", lower)
        and not re.search(r"\b(?:score|kpi|trend|ranking|waiting\s+time|booking|reachability)\b", lower)
    ):
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="guide_lookup",
                    args={"query": text, "page_id": "team_dashboard", **({"team": explicit_team} if explicit_team else {})},
                )
            ],
            team=explicit_team,
            function=function_for_team(explicit_team) if explicit_team else None,
            workflow_kind="guide_lookup",
        )

    from services.ai.product_guide import is_system_knowledge_question

    if is_system_knowledge_question(text):
        return GuidedReadIntent(
            operations=[
                QueryOperationV2(
                    operation_id="op_1",
                    kind="guide_lookup",
                    args={"query": text},
                )
            ],
            workflow_kind="guide_lookup",
        )

    return None


def _render_corrective_actions_section(ca_res: ToolExecutionResult, *, state_label: str) -> tuple[str, list[str], list[str]]:
    digest = ca_res.digest or {}
    if digest.get("status") == "unavailable":
        return (
            "Corrective-action records are temporarily unavailable because the follow-up service could not be read.",
            ["Retry in a moment or open Corrective Actions directly if you have access."],
            [],
        )
    total = int(digest.get("total_actions") or 0)
    actions = list(digest.get("actions") or [])
    scope_txt = str(digest.get("scope") or "your authorized scope")
    period_txt = f" for {digest['period']}" if digest.get("period") else ""
    state_phrase = f"{state_label} " if state_label else ""

    if total == 0:
        headline = f"0 {state_phrase}corrective actions matched {scope_txt}{period_txt}."
        return headline, [], []

    noun = "action" if total == 1 else "actions"
    headline = f"Found {total} {state_phrase}corrective {noun} in {scope_txt}{period_txt}."
    bullets: list[str] = []
    details: list[str] = []
    for act in actions[:5]:
        emp = act.get("employee_name") or "Team Action"
        team = act.get("team") or "Unassigned team"
        due = act.get("due_date")
        due_part = f" · due {due}" if due else ""
        status_part = act.get("status") or "Open"
        text_part = act.get("action_text") or act.get("action_type") or "Action"
        bullets.append(f"{emp} ({team}{due_part}) — {status_part}: {text_part}")
    if total > len(actions[:5]):
        details.append(f"Showing {len(actions[:5])} of {total} matching authorized records.")
    return headline, bullets, details


def _render_guide_section(
    guide_res: ToolExecutionResult,
    *,
    requested_page_id: str | None,
    role: str,
) -> tuple[str, list[str], list[AiNavigationTarget], list[str]]:
    digest = guide_res.digest or {}
    status = digest.get("status")
    sections = list(digest.get("sections") or [])
    nav_targets = [AiNavigationTarget.model_validate(n) for n in (digest.get("navigation_targets") or [])]

    if status == "unavailable":
        return (
            "The PMS product guide section is currently unavailable.",
            ["Guide instructions could not be loaded right now."],
            [],
            [],
        )

    if not sections:
        if requested_page_id == "monthly_evaluation" and role != "Admin":
            return (
                "Monthly evaluation settings are restricted to Admins in PMS.",
                ["Your role retains read access to authorized performance dashboards and reports, while monthly target/weight changes require an Admin account."],
                [],
                [],
            )
        return (
            "No authorized product guide section matched your request.",
            ["Specify the screen or workflow you want to find (for example, Corrective Actions, Team Dashboard, or System Overview)."],
            [],
            [],
        )

    primary = sections[0]
    sec_title = primary.get("title") or "PMS Guide"
    summary = str(primary.get("summary") or "").strip()
    steps = list(primary.get("steps") or [])
    route = primary.get("route")
    route_note = f" ({route})" if route and route not in summary else ""
    asked_grade = None
    if primary.get("id") == "pms-grade-scale":
        from services.ai.product_guide import GRADE_DEFINITIONS, extract_asked_grade_letter

        asked_grade = extract_asked_grade_letter(str((guide_res.arguments or {}).get("query") or ""))
        if asked_grade and asked_grade in GRADE_DEFINITIONS:
            g_label, g_range, g_desc = GRADE_DEFINITIONS[asked_grade]
            headline = f"Grade {asked_grade} means {g_label} ({g_range}): {g_desc}"
        else:
            headline = f"{summary}{route_note}" if summary else f"{sec_title}{route_note}."
    else:
        headline = f"{summary}{route_note}" if summary else f"{sec_title}{route_note}."
    bullets = [str(s) for s in steps[:5]]
    section_ids = [f"{s.get('id')}@v{s.get('version')}" for s in sections if s.get("id")]
    return headline, bullets, nav_targets, section_ids


def _render_reachability_assessment(res: ToolExecutionResult) -> tuple[str, list[str], list[str]]:
    d = res.digest or {}
    kpi_def = d.get("kpi_definition") or {}
    periods = list(d.get("periods") or [])
    valid = [p for p in periods if p.get("actual") is not None]
    pending = list(d.get("pending_approved_targets") or [])
    hyp = d.get("hypothetical_assessment")
    explanation = str(d.get("explanation_comparison") or "").strip()
    missing = list(d.get("missing_evidence") or [])

    if not valid:
        headline = "Insufficient Outbound Reachability evidence to assess a target change."
        bullets = [
            f"KPI definition: Outbound Reachability (key `Other`, weight {kpi_def.get('weight_percent', 10.0):g}%, higher is better, unit {kpi_def.get('unit', '%')}).",
            *(missing or ["No published Outbound records with Reachability actuals were found in your authorized scope."]),
        ]
        return headline, bullets, []

    latest = valid[-1]
    actual_txt = f"{latest['actual']:.1f}%"
    tgt_txt = f"{latest['applied_target']:.1f}%" if latest.get("applied_target") is not None else "unavailable"
    att_txt = f"{latest['measured_attainment']:.1f}%" if latest.get("measured_attainment") is not None else "unavailable"

    if hyp:
        headline = (
            f"Outbound Reachability actual in {hyp['period']} remains fixed at {hyp['actual_reachability_pct']:.1f}%; "
            f"a hypothetical target of {hyp['hypothetical_target_pct']:.1f}% would change measured attainment "
            f"from {hyp['current_measured_attainment_pct']:.1f}% to {hyp['hypothetical_measured_attainment_pct']:.1f}% "
            f"(capped at {hyp['cap_pct']:.0f}%)."
            if hyp.get("current_measured_attainment_pct") is not None
            else (
                f"Outbound Reachability actual in {hyp['period']} remains fixed at {hyp['actual_reachability_pct']:.1f}%; "
                f"at a hypothetical target of {hyp['hypothetical_target_pct']:.1f}%, measured attainment would be "
                f"{hyp['hypothetical_measured_attainment_pct']:.1f}% (capped at {hyp['cap_pct']:.0f}%)."
            )
        )
    else:
        headline = (
            f"Outbound Reachability assessment ({latest['period']}): actual Reachability is {actual_txt} "
            f"against applied target {tgt_txt} (measured attainment: {att_txt}; "
            f"coverage {latest['sample_size']}/{latest['total_records']} records, {latest['coverage_pct']:.0f}%)."
        )

    bullets: list[str] = [
        f"KPI definition: Outbound Reachability (`Other`), weight {kpi_def.get('weight_percent', 10.0):g}%, higher is better, average aggregation.",
    ]
    for row in valid[-3:]:
        r_tgt = f"{row['applied_target']:.1f}%" if row.get("applied_target") is not None else "n/a"
        r_att = f"{row['measured_attainment']:.1f}%" if row.get("measured_attainment") is not None else "n/a"
        bullets.append(
            f"{row['period']}: actual {row['actual']:.1f}%, applied target {r_tgt}, attainment {r_att}, "
            f"sample {row['sample_size']}/{row['total_records']} ({row['coverage_pct']:.0f}% coverage) · basis: {row['scoring_basis']}."
        )
    if pending:
        for p_item in pending[:2]:
            bullets.append(
                f"Pending approved target (not yet applied): {p_item['period']} v{p_item['version_number']} sets Reachability target to {p_item['approved_target_pct']:.1f}%."
            )
    if explanation:
        bullets.append(explanation)
    for m_note in missing:
        bullets.append(f"Additional evidence needed: {m_note}")

    details = [
        "Changing a target alters measured KPI attainment only; underlying actual Reachability remains unchanged.",
    ]
    return headline, bullets, details


def try_execute_guided_read_turn(
    *,
    orchestrator: Any,
    req: AiChatRequest,
    t0: float,
    active_conversation_id: str | None,
    claimed_turn: Any,
    claimed_context_version: int | None,
    claimed_token: str | None,
    active_context_version: int | None,
    conv_service: Any,
    eff_ctx_label_initial: str,
    initial_scope_banner: str,
    cfg: Any,
) -> AiChatResponsePayload | None:
    """Execute a guided read, searchable guide, compound, or Reachability assessment turn if matched."""
    intent = detect_guided_read_intent(req.prompt, req.session_state)
    if intent is None:
        return None

    scope = orchestrator.scope
    role = str(scope.get("role") or "Manager").strip()
    t_res_end = time.perf_counter()
    resolution_ms = round((t_res_end - t0) * 1000.0, 2)

    # Recheck authorization on EVERY turn (including follow-ups like "What about Outbound?")
    access_error = _check_requested_scope_access(
        scope,
        team=intent.team,
        branches=list(intent.branches),
        performance_level=req.session_state.performance_level or "Employee",
    )
    if access_error:
        plan_v2 = ValidatedQueryPlanV2(
            turn_kind="analytical",
            scope=QueryScopeV2(
                function=intent.function,
                team=intent.team,
                branches=list(intent.branches),
                periods=[intent.period_key] if intent.period_key else [],
                period_window="explicit" if intent.period_key else "all_published",
            ),
            operations=intent.operations[:2],
            clarification_code="RESTRICTED_SCOPE_SUGGESTION",
            resolution_source="local_rules",
        )
        restr = AiChatResponsePayload(
            trace_id="",
            conversation_id=active_conversation_id,
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            context_version=active_context_version,
            outcome="restricted_access",
            answer_detail="details" if req.answer_detail == "details" else "brief",
            headline=access_error,
            narrative_bullets=["Ask about a team or branch inside your authorized PMS scope."],
            resolved_session_state=req.session_state,
            scope_banner=initial_scope_banner,
            effective_context_label=eff_ctx_label_initial,
            validated_plan_v2=plan_v2,
            tool_calls=[],
            navigation_targets=[],
            deep_links=[],
            capability_mode="performance_query",
            provider_used="deterministic",
            model_used="pms-guided-reads-v1",
            answer_source="deterministic",
            timings=AiTurnTimingBreakdown(
                resolution_ms=resolution_ms,
                total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
            ),
            provider_usage=AiProviderUsageMetrics(router_mode=cfg.router_mode, route_used="local_rules", provider_calls=0),
        )
        return finalize_deterministic_turn(
            orchestrator=orchestrator,
            req=req,
            resp=restr,
            plan_v2=plan_v2,
            confirmed_ctx=req.session_state.last_confirmed_query,
            conv_service=conv_service,
            active_conversation_id=active_conversation_id,
            claimed_turn=claimed_turn,
            claimed_context_version=claimed_context_version,
            claimed_token=claimed_token,
            t0=t0,
        )

    # Execute authorized operations cleanly via DeterministicToolRegistry
    t_db_start = time.perf_counter()
    registry = DeterministicToolRegistry(
        ToolExecutionContext(
            db=orchestrator.db,
            scope=scope,
            session_state=req.session_state,
        )
    )
    today_override = get_reference_today()

    ca_result: ToolExecutionResult | None = None
    guide_result: ToolExecutionResult | None = None
    reach_result: ToolExecutionResult | None = None
    tool_results: list[ToolExecutionResult] = []

    for op in intent.operations[:2]:
        if op.kind == "corrective_actions":
            ca_result = registry.execute_corrective_actions_status(
                team=op.args.get("team", intent.team),
                function=intent.function,
                month=op.args.get("month", intent.month) if intent.apply_period_filter else None,
                year=op.args.get("year", intent.year) if intent.apply_period_filter else None,
                region=intent.region,
                state=op.args.get("state", intent.action_state),
                today=today_override,
                apply_period_filter=intent.apply_period_filter,
            )
            tool_results.append(ca_result)
        elif op.kind == "guide_lookup":
            guide_result = registry.execute_guide_lookup(
                query=str(op.args.get("query") or req.prompt),
                page_id=op.args.get("page_id"),
                team=op.args.get("team", intent.team),
                function=intent.function,
                month=intent.month,
                year=intent.year,
            )
            tool_results.append(guide_result)
        elif op.kind == "target_assessment":
            reach_result = registry.execute_reachability_target_assessment(
                team="Outbound",
                region=intent.region,
                branch=intent.branches[0] if intent.branches else None,
                month=intent.month,
                year=intent.year,
                hypothetical_target=op.args.get("hypothetical_target"),
            )
            tool_results.append(reach_result)

    database_ms = round((time.perf_counter() - t_db_start) * 1000.0, 2)

    # Compose grounded response retaining result and source of each operation
    t_render_start = time.perf_counter()
    outcome: Any = "answer"
    headline = ""
    narrative_bullets: list[str] = []
    detail_bullets: list[str] = []
    visual_cards = []
    citations = []
    deep_links = []
    nav_targets: list[AiNavigationTarget] = []
    capability_mode: Any = "performance_query"
    guide_section_ids: list[str] = []

    for tr in tool_results:
        visual_cards.extend(tr.visual_cards)
        citations.extend(tr.citations)
        for dl in tr.deep_links:
            if all(existing.route != dl.route for existing in deep_links):
                deep_links.append(dl)

    if ca_result is not None and guide_result is not None:
        # Compound workflow: authorized records first, then verified guide steps + link
        ca_h, ca_b, ca_d = _render_corrective_actions_section(ca_result, state_label=(intent.action_state or "").replace("_", " "))
        req_page = next((op.args.get("page_id") for op in intent.operations if op.kind == "guide_lookup"), None)
        g_h, g_b, g_nav, guide_section_ids = _render_guide_section(guide_result, requested_page_id=req_page, role=role)
        nav_targets.extend(g_nav)

        if (ca_result.digest or {}).get("status") == "unavailable":
            outcome = "unavailable_data"
            headline = f"{ca_h} {g_h}"
            narrative_bullets = [*ca_b, *g_b]
        else:
            headline = f"{ca_h} {g_h}"
            narrative_bullets = [*ca_b, *g_b]
            detail_bullets = list(ca_d)
    elif ca_result is not None:
        ca_h, ca_b, ca_d = _render_corrective_actions_section(ca_result, state_label=(intent.action_state or "").replace("_", " "))
        if (ca_result.digest or {}).get("status") == "unavailable":
            outcome = "unavailable_data"
        headline = ca_h
        narrative_bullets = ca_b
        detail_bullets = ca_d
    elif guide_result is not None:
        capability_mode = "navigation"
        req_page = next((op.args.get("page_id") for op in intent.operations if op.kind == "guide_lookup"), None)
        g_h, g_b, g_nav, guide_section_ids = _render_guide_section(guide_result, requested_page_id=req_page, role=role)
        nav_targets.extend(g_nav)
        headline = g_h
        narrative_bullets = g_b
        if (guide_result.digest or {}).get("status") == "unavailable":
            outcome = "unavailable_data"
    elif reach_result is not None:
        r_h, r_b, r_d = _render_reachability_assessment(reach_result)
        headline = r_h
        narrative_bullets = r_b
        detail_bullets = r_d

    # Build validated plan & confirmed conversational context for follow-ups
    plan_v2 = ValidatedQueryPlanV2(
        turn_kind="analytical",
        scope=QueryScopeV2(
            function=intent.function,
            team=intent.team,
            branches=list(intent.branches),
            periods=[intent.period_key] if intent.period_key else [],
            period_window="explicit" if intent.period_key else "all_published",
        ),
        operations=intent.operations[:2],
        clarification_code="NONE",
        resolution_source="local_rules",
    )
    structured_plan = StructuredQueryPlan(
        intent="corrective_actions" if ca_result is not None else "current_value",
        requested_parts=[op.kind for op in intent.operations[:2]],
        team=intent.team,
        function=intent.function,
        periods=[intent.period_key] if intent.period_key else [],
        operation_kind_v2=intent.operations[0].kind if intent.operations else None,
        action_state=intent.action_state,
        guide_query=next((op.args.get("query") for op in intent.operations if op.kind == "guide_lookup"), None),
        hypothetical_target=next((op.args.get("hypothetical_target") for op in intent.operations if op.kind == "target_assessment"), None),
    )

    confirmed_ctx = ConfirmedQueryContext(
        intent="corrective_actions" if ca_result is not None else "current_value",
        team=intent.team,
        function=intent.function,
        branch=intent.branches[0] if intent.branches else None,
        branches=list(intent.branches),
        region=intent.region,
        performance_level=req.session_state.performance_level or "Employee",
        metric_id="outbound:reachability" if reach_result is not None else None,
        metric_display_name="Reachability" if reach_result is not None else None,
        periods=[intent.period_key] if intent.period_key else [],
        last_operation_kind=intent.operations[0].kind if intent.operations else None,
        inherited_filters=list(intent.inherited_filters),
        action_state=intent.action_state,
        workflow_kind=intent.workflow_kind,
    )

    resolved_ss = req.session_state.model_copy(
        update={
            "team": intent.team if intent.team is not None else (None if ca_result is not None else req.session_state.team),
            "function": intent.function if intent.function is not None else (None if ca_result is not None else req.session_state.function),
            "month": intent.month if intent.apply_period_filter else req.session_state.month,
            "year": intent.year if intent.apply_period_filter else req.session_state.year,
            "last_confirmed_query": confirmed_ctx,
        }
    )

    tool_call_records = [
        AiToolCallRecord(
            tool_name=tr.tool_name,
            arguments={
                **(tr.arguments or {}),
                **({"guide_sections": guide_section_ids} if tr.tool_name == "guide_lookup" and guide_section_ids else {}),
                **({"record_ids": (tr.digest or {}).get("record_ids")} if tr.tool_name == "get_corrective_actions_status" else {}),
                "execution_status": (tr.digest or {}).get("status", "ok"),
            },
            records_evaluated=tr.records_evaluated,
        )
        for tr in tool_results
    ]

    scope_banner, _ = orchestrator._resolve_scope_banner_and_function(session_state=resolved_ss)
    eff_ctx_label = build_effective_context_label(
        page_context=req.page_context,
        session_state=resolved_ss,
        selected_metric_display="Reachability" if reach_result is not None else None,
    )
    render_ms = round((time.perf_counter() - t_render_start) * 1000.0, 2)
    total_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    resp = AiChatResponsePayload(
        trace_id="",
        conversation_id=active_conversation_id,
        turn_id=str(claimed_turn.id) if claimed_turn else None,
        context_version=active_context_version,
        outcome=outcome,
        answer_detail="details" if req.answer_detail == "details" else "brief",
        headline=headline,
        narrative_bullets=narrative_bullets,
        detail_bullets=detail_bullets,
        visual_cards=visual_cards,
        citations=citations,
        deep_links=deep_links,
        navigation_targets=nav_targets,
        primary_source_link=deep_links[0] if deep_links else None,
        resolved_session_state=resolved_ss,
        scope_banner=scope_banner,
        effective_context_label=eff_ctx_label,
        inherited_filters=list(intent.inherited_filters),
        structured_query=structured_plan,
        validated_plan_v2=plan_v2,
        tool_calls=tool_call_records,
        capability_mode=capability_mode,
        provider_used="deterministic",
        model_used="pms-guided-reads-v1",
        answer_source="deterministic",
        latency_ms=int(total_ms),
        timings=AiTurnTimingBreakdown(
            resolution_ms=resolution_ms,
            provider_ms=0.0,
            database_ms=database_ms,
            render_ms=render_ms,
            total_ms=total_ms,
        ),
        provider_usage=AiProviderUsageMetrics(
            router_mode=cfg.router_mode,
            route_used="local_rules",
            provider_calls=0,
        ),
    )

    return finalize_deterministic_turn(
        orchestrator=orchestrator,
        req=req,
        resp=resp,
        plan_v2=plan_v2,
        confirmed_ctx=confirmed_ctx,
        conv_service=conv_service,
        active_conversation_id=active_conversation_id,
        claimed_turn=claimed_turn,
        claimed_context_version=claimed_context_version,
        claimed_token=claimed_token,
        t0=t0,
    )


def finalize_deterministic_turn(
    *,
    orchestrator: Any,
    req: AiChatRequest,
    resp: AiChatResponsePayload,
    plan_v2: ValidatedQueryPlanV2,
    confirmed_ctx: ConfirmedQueryContext | None,
    conv_service: Any,
    active_conversation_id: str | None,
    claimed_turn: Any,
    claimed_context_version: int | None,
    claimed_token: str | None,
    t0: float,
) -> AiChatResponsePayload:
    from services.ai.trace_logger import TrainingTraceLogger

    try:
        trace_digest = {
            "validated_operations": [op.model_dump() for op in plan_v2.operations],
            "effective_filters": {
                "team": plan_v2.scope.team,
                "function": plan_v2.scope.function,
                "branches": plan_v2.scope.branches,
                "periods": plan_v2.scope.periods,
                "action_state": confirmed_ctx.action_state if confirmed_ctx else None,
            },
            "result_counts": {tc.tool_name: tc.records_evaluated for tc in resp.tool_calls},
            "guide_sections": [
                sec
                for tc in resp.tool_calls
                if tc.tool_name == "guide_lookup"
                for sec in (tc.arguments.get("guide_sections") or [])
            ],
            "execution_statuses": {
                tc.tool_name: tc.arguments.get("execution_status", "ok") for tc in resp.tool_calls
            },
        }
        trace_id = TrainingTraceLogger(orchestrator.db).record_turn(
            user_id=str(orchestrator.scope.get("user_id") or "") or None,
            role=str(orchestrator.scope.get("role") or "Manager"),
            prompt=req.prompt,
            session_state=resp.resolved_session_state,
            tool_calls=[tc.model_dump() for tc in resp.tool_calls],
            tool_digest=trace_digest,
            structured_response={
                "outcome": resp.outcome,
                "headline": resp.headline,
                "narrative_bullets": resp.narrative_bullets,
                "navigation_routes": [n.route for n in resp.navigation_targets],
            },
            provider_name=resp.provider_used,
            model_name=resp.model_used,
            latency_ms=int(resp.latency_ms or 0),
            non_empty_evidence=any(tc.records_evaluated > 0 for tc in resp.tool_calls),
            guardrail_triggered=resp.outcome in ("restricted_access", "unavailable_data"),
            turn_id=str(claimed_turn.id) if claimed_turn else None,
            skip_record_lookup=True,
        )
        if trace_id:
            resp.trace_id = str(trace_id)
    except Exception:
        pass

    if conv_service and active_conversation_id and claimed_turn:
        payload_for_store = resp.model_dump()
        if claimed_context_version is not None:
            payload_for_store["context_version"] = claimed_context_version + 1
        new_ver = conv_service.complete_turn(
            conversation_id=active_conversation_id,
            turn_id=str(claimed_turn.id),
            expected_context_version=claimed_context_version,
            claim_token=claimed_token,
            scope=orchestrator.scope,
            outcome=resp.outcome,
            turn_kind=plan_v2.turn_kind,
            route_used=resp.provider_usage.route_used,
            validated_plan=plan_v2.model_dump(),
            evidence_envelope=[item.model_dump() for item in resp.evidence_envelope_v2],
            response_payload=payload_for_store,
            session_state=resp.resolved_session_state,
            confirmed_context=confirmed_ctx,
            provider_calls=resp.provider_usage.provider_calls,
            total_ms=round((time.perf_counter() - t0) * 1000.0, 2),
        )
        resp.context_version = new_ver
    return resp

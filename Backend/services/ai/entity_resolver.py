from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Literal

from rapidfuzz import fuzz

from models.report_schemas import MONTHS
from utils.report_scope import function_for_team

REVERSE_MONTHS_BY_NUM: dict[int, str] = {v: k for k, v in MONTHS.items()}

_PERSON_STOPWORDS: frozenset[str] = frozenset(
    {
        "inbound",
        "outbound",
        "support",
        "positions",
        "position",
        "call",
        "center",
        "team",
        "teams",
        "branch",
        "branches",
        "dubai",
        "sharjah",
        "ajman",
        "clinics",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "best",
        "worst",
        "lowest",
        "highest",
        "top",
        "bottom",
        "month",
        "year",
        "score",
        "scores",
        "performance",
        "booking",
        "bookings",
        "attendance",
        "quality",
        "aht",
        "abandon",
        "reachability",
        "agent",
        "agents",
        "employee",
        "employees",
        "performer",
        "performers",
        "new",
        "joiner",
        "joiners",
        "joined",
        "recently",
        "who",
        "what",
        "was",
        "were",
        "is",
        "are",
        "did",
        "does",
        "how",
        "which",
        "where",
        "when",
        "why",
        "the",
        "and",
        "for",
        "in",
        "on",
        "at",
        "to",
        "of",
        "by",
        "with",
        "from",
        "about",
        "his",
        "her",
        "their",
        "show",
        "compare",
        "analyze",
        "diagnose",
        "pms",
        "rcm",
        "coding",
        "submission",
        "resubmission",
        "marketing",
        "pharmacy",
        "csr",
        "sales",
        "finance",
        "hr",
        "it",
        "managerial",
        "corporate",
    }
)


def format_period_label(period_key: str) -> str:
    try:
        yr_s, mo_s = period_key.split("-", 1)
        m_name = REVERSE_MONTHS_BY_NUM.get(int(mo_s), "September")
        return f"{m_name} {int(yr_s)}"
    except Exception:
        return "September 2026"


def format_period_window_label(period_keys: list[str]) -> str:
    if not period_keys:
        return "September 2026"
    ordered = sorted(set(period_keys))
    if len(ordered) == 1:
        return format_period_label(ordered[0])
    first_yr, first_mo = ordered[0].split("-", 1)
    last_yr, last_mo = ordered[-1].split("-", 1)
    first_m_name = REVERSE_MONTHS_BY_NUM.get(int(first_mo), "March")
    last_m_name = REVERSE_MONTHS_BY_NUM.get(int(last_mo), "September")
    if first_yr == last_yr:
        return f"{first_m_name}–{last_m_name} {int(last_yr)}"
    return f"{first_m_name} {int(first_yr)}–{last_m_name} {int(last_yr)}"


@dataclass
class EmployeeHistoryCandidate:
    employee_id: str
    employee_name: str
    team: str
    function: str
    position: str | None = None
    branch: str | None = None
    period_scores: dict[str, float] = field(default_factory=dict)
    earliest_period: str = "2026-09"
    earliest_period_label: str = "September 2026"
    earliest_score: float = 0.0
    latest_period: str = "2026-09"
    latest_period_label: str = "September 2026"
    latest_score: float = 0.0
    best_period: str = "2026-09"
    best_period_label: str = "September 2026"
    best_score: float = 0.0
    best_ties: list[str] = field(default_factory=list)
    worst_period: str = "2026-09"
    worst_period_label: str = "September 2026"
    worst_score: float = 0.0
    worst_ties: list[str] = field(default_factory=list)
    searched_window_label: str = "September 2026"
    record_count: int = 0
    missing_count: int = 0

    @property
    def months_tracked(self) -> int:
        return self.record_count


@dataclass
class EmployeeResolutionResult:
    status: Literal["unique", "ambiguous", "not_found", "none"] = "none"
    matched_employee: EmployeeHistoryCandidate | None = None
    candidates: list[EmployeeHistoryCandidate] = field(default_factory=list)
    extracted_token: str | None = None

    @property
    def selected(self) -> EmployeeHistoryCandidate | None:
        return self.matched_employee

    @property
    def matches(self) -> list[EmployeeHistoryCandidate]:
        return self.candidates


def build_employee_candidates_from_records(
    records: list[Any],
    *,
    team_filter: str | None = None,
    function_filter: str | None = None,
    position_filter: str | None = None,
) -> list[EmployeeHistoryCandidate]:
    """Aggregate authorized employee records across all published months into EmployeeHistoryCandidate objects."""
    by_emp: dict[str, dict[str, Any]] = {}
    all_observed_periods: set[str] = set()

    t_norm = (team_filter or "").strip().casefold()
    fn_norm = (function_filter or "").strip().casefold()
    pos_norm = (position_filter or "").strip().casefold()

    for rec in records:
        rec_level = str(getattr(rec, "performance_level", None) or "Employee").strip()
        if rec_level.casefold() != "employee":
            continue
        raw_team = str(getattr(rec, "team", "") or "").strip()
        raw_pos = str(getattr(rec, "position", "") or "").strip() or None
        display_team = "Support Positions" if (raw_team == "Call Center" and raw_pos) else raw_team
        fn_name = function_for_team(display_team) or function_for_team(raw_team) or "Call Center"

        if t_norm and t_norm not in ("all", ""):
            if t_norm == "support positions":
                if display_team != "Support Positions":
                    continue
            elif t_norm == "call center":
                if fn_name.casefold() != "call center":
                    continue
            elif display_team.casefold() != t_norm and raw_team.casefold() != t_norm:
                continue
        elif fn_norm and fn_norm not in ("all", ""):
            if fn_name.casefold() != fn_norm:
                continue

        if pos_norm and pos_norm not in ("all", ""):
            if not raw_pos or raw_pos.casefold() != pos_norm:
                continue

        emp_id = str(getattr(rec, "employee_id", "") or "").strip()
        emp_name = str(getattr(rec, "employee_name", "") or "").strip()
        if not emp_id or not emp_name:
            continue

        m_name = str(getattr(rec, "month", "") or "September").strip()
        yr_val = int(getattr(rec, "year", 2026) or 2026)
        m_num = MONTHS.get(m_name, 9)
        pk = f"{yr_val:04d}-{m_num:02d}"
        all_observed_periods.add(pk)

        score_val = getattr(rec, "overall_score", None)
        if score_val is None:
            ev_obj = getattr(rec, "evaluation", None)
            score_val = getattr(ev_obj, "score", None) if ev_obj is not None else None
        if score_val is None:
            score_val = 0.0
        score_f = round(float(score_val), 2)

        entry = by_emp.setdefault(
            emp_id,
            {
                "employee_id": emp_id,
                "employee_name": emp_name,
                "team": display_team,
                "function": fn_name,
                "position": raw_pos,
                "branch": getattr(rec, "branch", None),
                "period_scores": {},
            },
        )
        if raw_pos and not entry.get("position"):
            entry["position"] = raw_pos
        entry["period_scores"][pk] = score_f

    total_window_periods = sorted(all_observed_periods) or ["2026-09"]
    window_label = format_period_window_label(total_window_periods)

    candidates: list[EmployeeHistoryCandidate] = []
    for emp_id, info in by_emp.items():
        p_scores: dict[str, float] = info["period_scores"]
        if not p_scores:
            continue
        ordered_p = sorted(p_scores.keys())
        earliest_p = ordered_p[0]
        latest_p = ordered_p[-1]
        max_score = max(p_scores.values())
        min_score = min(p_scores.values())
        best_p_keys = [p for p in ordered_p if abs(p_scores[p] - max_score) < 1e-6]
        worst_p_keys = [p for p in ordered_p if abs(p_scores[p] - min_score) < 1e-6]
        best_p = best_p_keys[-1]
        worst_p = worst_p_keys[0]
        best_ties = [format_period_label(p) for p in best_p_keys] if len(best_p_keys) > 1 else []
        worst_ties = [format_period_label(p) for p in worst_p_keys] if len(worst_p_keys) > 1 else []

        emp_window = format_period_window_label(ordered_p) if len(ordered_p) >= 2 else window_label
        missing_cnt = max(0, len(total_window_periods) - len(ordered_p))

        candidates.append(
            EmployeeHistoryCandidate(
                employee_id=emp_id,
                employee_name=info["employee_name"],
                team=info["team"],
                function=info["function"],
                position=info["position"],
                branch=info["branch"],
                period_scores=p_scores,
                earliest_period=earliest_p,
                earliest_period_label=format_period_label(earliest_p),
                earliest_score=p_scores[earliest_p],
                latest_period=latest_p,
                latest_period_label=format_period_label(latest_p),
                latest_score=p_scores[latest_p],
                best_period=best_p,
                best_period_label=format_period_label(best_p),
                best_score=max_score,
                best_ties=best_ties,
                worst_period=worst_p,
                worst_period_label=format_period_label(worst_p),
                worst_score=min_score,
                worst_ties=worst_ties,
                searched_window_label=emp_window,
                record_count=len(ordered_p),
                missing_count=missing_cnt,
            )
        )

    candidates.sort(key=lambda c: (c.employee_name.casefold(), c.employee_id))
    return candidates


def extract_person_token_from_prompt(prompt: str) -> str | None:
    """Extract a likely person name or employee code token from natural English questions."""
    text = (prompt or "").strip()
    lower = text.casefold()

    # 1. Explicit employee code (EMP101, SGHD70204, etc.)
    code_match = re.search(r"\b(emp[-_ ]?\d+|sgh[da]\d+|e[-_]\d+)\b", lower)
    if code_match:
        return code_match.group(1).strip()

    # 2. Possessive pattern: "<Name>'s best month", "<Name>'s position", "<Name>'s score"
    poss_match = re.search(
        r"\b([a-z][a-z]+(?:\s+[a-z][a-z]+)?)'s\s+(?:best|worst|lowest|highest|position|score|performance|history|record|month|trend)\b",
        lower,
    )
    if poss_match:
        raw_tok = poss_match.group(1).strip()
        tokens = [w for w in raw_tok.split() if w not in _PERSON_STOPWORDS]
        if tokens:
            return " ".join(tokens)

    # 3. Joiner / tenure pattern: "Is <Name> a new joiner", "Did <Name> join"
    joiner_match = re.search(
        r"\b(?:is|was|did)\s+([a-z][a-z]+(?:\s+[a-z][a-z]+)?)\s+(?:a\s+new\s+joiner|join(?:ed)?\b|new\s+in\b)",
        lower,
    )
    if joiner_match:
        raw_tok = joiner_match.group(1).strip()
        tokens = [w for w in raw_tok.split() if w not in _PERSON_STOPWORDS]
        if tokens:
            return " ".join(tokens)

    # 4. "for <Name>" or "about <Name>" when asking best month / score / position
    for_match = re.search(
        r"\b(?:for|about|of)\s+([a-z][a-z]+(?:\s+[a-z][a-z]+)?)(?:\s+in\b|\s+during\b|[\s?.!]*$)",
        lower,
    )
    if for_match:
        raw_tok = for_match.group(1).strip()
        tokens = [w for w in raw_tok.split() if w not in _PERSON_STOPWORDS]
        if tokens:
            return " ".join(tokens)

    return None


def resolve_employee_from_candidates(
    prompt: str = "",
    candidates: list[EmployeeHistoryCandidate] | None = None,
    *,
    team: str | None = None,
    function: str | None = None,
    position: str | None = None,
    explicit_employee_id: str | None = None,
) -> EmployeeResolutionResult:
    """Resolve an employee mention against authorized EmployeeHistoryCandidate entries."""
    cand_list = list(candidates or [])
    if not cand_list:
        return EmployeeResolutionResult(status="none")

    t_norm = (team or "").strip().casefold()
    fn_norm = (function or "").strip().casefold()
    pos_norm = (position or "").strip().casefold()
    filtered_cands: list[EmployeeHistoryCandidate] = []
    for c in cand_list:
        if t_norm and t_norm not in ("all", "call center"):
            if c.team.casefold() != t_norm:
                continue
        elif fn_norm and fn_norm not in ("all", ""):
            if c.function.casefold() != fn_norm:
                continue
        if pos_norm and pos_norm not in ("all", ""):
            if not c.position or c.position.casefold() != pos_norm:
                continue
        filtered_cands.append(c)
    candidates = filtered_cands if filtered_cands else cand_list

    # 1. Explicit employee_id (from choice or session state)
    if explicit_employee_id:
        wanted_id = explicit_employee_id.strip().casefold()
        for c in candidates:
            if c.employee_id.casefold() == wanted_id:
                return EmployeeResolutionResult(
                    status="unique",
                    matched_employee=c,
                    candidates=[c],
                    extracted_token=c.employee_id,
                )

    lower = (prompt or "").strip().casefold()

    # 2. Direct employee_id in prompt
    for c in candidates:
        if re.search(rf"\b{re.escape(c.employee_id.casefold())}\b", lower):
            return EmployeeResolutionResult(
                status="unique",
                matched_employee=c,
                candidates=[c],
                extracted_token=c.employee_id,
            )

    # 3. Exact full name match in prompt
    full_matches = [
        c
        for c in candidates
        if len(c.employee_name.strip()) >= 3
        and re.search(rf"\b{re.escape(c.employee_name.strip().casefold())}\b", lower)
    ]
    if len(full_matches) == 1:
        return EmployeeResolutionResult(
            status="unique",
            matched_employee=full_matches[0],
            candidates=full_matches,
            extracted_token=full_matches[0].employee_name,
        )
    if len(full_matches) > 1:
        return EmployeeResolutionResult(
            status="ambiguous",
            matched_employee=None,
            candidates=full_matches[:3],
            extracted_token=full_matches[0].employee_name,
        )

    extracted = extract_person_token_from_prompt(prompt)

    # 4. Exact first-name or last-name token match across candidates
    search_tokens: list[str] = []
    if extracted:
        search_tokens.append(extracted.casefold())
    else:
        for word in re.findall(r"\b[a-z]{3,}\b", lower):
            if word not in _PERSON_STOPWORDS:
                search_tokens.append(word)

    for tok in search_tokens:
        token_matches = [
            c
            for c in candidates
            if tok == c.employee_name.casefold()
            or tok in [part.casefold() for part in c.employee_name.split()]
        ]
        if len(token_matches) == 1:
            return EmployeeResolutionResult(
                status="unique",
                matched_employee=token_matches[0],
                candidates=token_matches,
                extracted_token=tok.title(),
            )
        if len(token_matches) > 1:
            return EmployeeResolutionResult(
                status="ambiguous",
                matched_employee=None,
                candidates=token_matches[:3],
                extracted_token=tok.title(),
            )

    # 5. Typo-tolerant fuzzy match on extracted token using rapidfuzz
    if extracted and len(extracted) >= 3:
        scored: list[tuple[float, EmployeeHistoryCandidate]] = []
        for c in candidates:
            name_lower = c.employee_name.casefold()
            parts = name_lower.split()
            best_ratio = max(
                [fuzz.WRatio(extracted, name_lower)]
                + [fuzz.ratio(extracted, p) for p in parts]
            )
            if best_ratio >= 86.0:
                scored.append((best_ratio, c))
        scored.sort(key=lambda item: item[0], reverse=True)
        if len(scored) == 1:
            return EmployeeResolutionResult(
                status="unique",
                matched_employee=scored[0][1],
                candidates=[scored[0][1]],
                extracted_token=extracted.title(),
            )
        if len(scored) > 1:
            top_score = scored[0][0]
            close_matches = [c for s, c in scored if top_score - s <= 4.0]
            if len(close_matches) == 1:
                return EmployeeResolutionResult(
                    status="unique",
                    matched_employee=close_matches[0],
                    candidates=close_matches,
                    extracted_token=extracted.title(),
                )
            return EmployeeResolutionResult(
                status="ambiguous",
                matched_employee=None,
                candidates=close_matches[:3],
                extracted_token=extracted.title(),
            )
        return EmployeeResolutionResult(
            status="not_found",
            matched_employee=None,
            candidates=[],
            extracted_token=extracted.title(),
        )

    return EmployeeResolutionResult(status="none")


def project_prompt_with_employee_placeholders(
    prompt: str,
    candidates: list[EmployeeHistoryCandidate],
) -> tuple[str, dict[str, str]]:
    """Replace any employee name or ID mentions with turn-local placeholders (<EMP_1>, <EMP_2>) for cloud routing."""
    projected = str(prompt or "")
    placeholder_map: dict[str, str] = {}
    idx = 1

    # Replace full names first, then individual name tokens that match candidates
    sorted_cands = sorted(candidates, key=lambda c: len(c.employee_name), reverse=True)
    for c in sorted_cands:
        full_pat = re.compile(rf"\b{re.escape(c.employee_name)}\b", re.IGNORECASE)
        if full_pat.search(projected):
            tok = f"<EMP_{idx}>"
            idx += 1
            projected = full_pat.sub(tok, projected)
            placeholder_map[tok] = c.employee_id
            continue
        id_pat = re.compile(rf"\b{re.escape(c.employee_id)}\b", re.IGNORECASE)
        if id_pat.search(projected):
            tok = f"<EMP_{idx}>"
            idx += 1
            projected = id_pat.sub(tok, projected)
            placeholder_map[tok] = c.employee_id
            continue
        first_token = c.employee_name.split()[0] if c.employee_name.split() else ""
        if len(first_token) >= 3 and first_token.casefold() not in _PERSON_STOPWORDS:
            first_pat = re.compile(rf"\b{re.escape(first_token)}\b", re.IGNORECASE)
            if first_pat.search(projected):
                tok = f"<EMP_{idx}>"
                idx += 1
                projected = first_pat.sub(tok, projected)
                placeholder_map[tok] = c.employee_id

    return projected, placeholder_map

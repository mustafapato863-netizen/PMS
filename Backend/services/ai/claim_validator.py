"""Deterministic claim-ledger validator for PMS AI outputs (Workstream B / #99).

Pure Python validator with zero LLM calls and zero database mutations.
Verifies model-authored headlines and bullets against an authoritative
``list[ClaimFact]`` ledger built from ``TypedMetricEvidence``,
``EvidenceItemV2``, and/or ``local_data_explorer`` fact-ledger dicts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from models.ai_schemas import EvidenceItemV2, TypedMetricEvidence
from models.report_schemas import MONTHS

__all__ = [
    "ClaimFact",
    "ClaimValidationResult",
    "build_claim_ledger",
    "validate_claims",
]

_REVERSE_MONTHS_BY_NUM: dict[int, str] = {v: k for k, v in MONTHS.items()}
_CANONICAL_MONTHS: frozenset[str] = frozenset(m.casefold() for m in MONTHS)
_KNOWN_BRANCHES: tuple[str, ...] = ("dubai", "sharjah", "ajman", "clinics")
_ZERO_CLAIM_RE = re.compile(
    r"(?<![A-Za-z0-9.])0(?:\.0+)?(?:\s*%)?(?!(?:\.\d)|\d)|\bzero\b",
    re.IGNORECASE,
)
_NUMBER_TOKEN_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_ISO_PERIOD_RE = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")

# Check 1: Sanity, injection, HTML/script, markdown tables, non-ASCII digits.
_CONTROL_OR_HTML_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f<>]")
_MARKDOWN_TABLE_RE = re.compile(r"(?:\|[^|\n]+\|[^|\n]+\|\s*\n\s*\|(?:\s*:?-+:?\s*\|)+)|(?:\|[^|\n]*\|[^|\n]*\|[^|\n]*\|)")
_PROMPT_INJECTION_RE = re.compile(
    r"\b(?:ignore\s+(?:all\s+|any\s+)?previous|system\s+prompt|jailbreak|disregard\s+(?:all\s+|previous\s+)?instructions?)\b",
    re.IGNORECASE,
)

# Check 5: Magnitude vs. evaluative performance comparators.
_MAGNITUDE_HIGHER_RE = re.compile(
    r"\b(?:higher\s+than|greater\s+than|larger\s+than|bigger\s+than|more\s+(?:[a-z]+\s+){0,3}than)\b",
    re.IGNORECASE,
)
_MAGNITUDE_LOWER_RE = re.compile(
    r"\b(?:lower\s+than|smaller\s+than|less\s+(?:[a-z]+\s+){0,3}than|fewer\s+(?:[a-z]+\s+){0,3}than)\b",
    re.IGNORECASE,
)
_EVAL_BETTER_RE = re.compile(
    r"\b(?:outperformed|beat|exceeded|topped|led|leads|leading|ahead\s+of)\b",
    re.IGNORECASE,
)
_EVAL_WORSE_RE = re.compile(
    r"\b(?:trailed|trails|trailing|lagged|behind)\b",
    re.IGNORECASE,
)
_SUPERLATIVE_BEST_RE = re.compile(r"\b(?:best|strongest)\b", re.IGNORECASE)
_SUPERLATIVE_WORST_RE = re.compile(r"\b(?:worst|weakest)\b", re.IGNORECASE)

# Check 6: Tie disclosure.
_EXCLUSIVE_WINNER_LOSER_RE = re.compile(
    r"\b(?:led|leads|leading|outperformed|beat|topped|sole|highest|lowest|best|worst)\b|"
    r"\b(?:more|fewer|higher|lower|greater|less)\s+(?:[a-z]+\s+){0,3}than\b",
    re.IGNORECASE,
)
_TIE_WORDING_RE = re.compile(r"\b(?:tied|tie|ties|equal|equally|shared)\b", re.IGNORECASE)

# Check 7: Country & scope markers.
_EGY_WORD_RE = re.compile(r"\b(?:egy|egypt)\b", re.IGNORECASE)
_UAE_WORD_RE = re.compile(r"\b(?:uae|emirates|united\s+arab\s+emirates)\b", re.IGNORECASE)

# Check 8: Banned causal leaps and HR hallucinations.
_CAUSAL_RE = re.compile(
    r"\b(?:because|caused\s+by|due\s+to|driven\s+by|as\s+a\s+result\s+of|stemming\s+from|root\s+cause\s+is|attributable\s+to)\b",
    re.IGNORECASE,
)
_CAUSAL_CAVEAT_RE = re.compile(
    r"\b(?:cause\s+is\s+not\s+established|root\s+cause\s+is\s+not\s+established|not\s+attributable\s+to|not\s+caused\s+by|not\s+due\s+to)\b",
    re.IGNORECASE,
)
_HR_HALLUCINATION_RE = re.compile(
    r"\b(?:hired|hire\s+date|joined\s+in|joined\s+on|join\s+date|date\s+of\s+joining|employed\s+since|terminated|resigned|fired|salary|compensation|wage|wages)\b",
    re.IGNORECASE,
)

_COUNT_UNITS = frozenset({"count", "number", "#", "num"})
_PERCENT_UNITS = frozenset({"%", "percent", "percentage", "rate", "score"})
_MINUTE_UNITS = frozenset({"min", "mins", "minute", "minutes"})
_SECOND_UNITS = frozenset({"sec", "secs", "second", "seconds"})
_HOUR_UNITS = frozenset({"hr", "hrs", "hour", "hours"})
_DAY_UNITS = frozenset({"day", "days"})
_DURATION_UNITS = _MINUTE_UNITS | _SECOND_UNITS | _HOUR_UNITS | _DAY_UNITS | frozenset({"duration"})


@dataclass(frozen=True)
class ClaimFact:
    fact_id: str
    part: str = "metric"
    subject: str = ""
    employee_id: str | None = None
    country: str | None = None
    function: str | None = None
    team: str | None = None
    position: str | None = None
    branch: str | None = None
    performance_level: str | None = None
    period: str = ""
    metric_key: str | None = None
    metric_name: str | None = None
    value: float | int | None = None
    target: float | int | None = None
    achievement_percent: float | None = None
    display: str = ""
    unit: str = "%"
    direction: str = "higher_better"
    ties: tuple[str, ...] = ()
    is_missing: bool = False
    scoring_basis_status: str = "unchanged"
    source_link: str | None = None
    sample_size: int | None = None


@dataclass
class ClaimValidationResult:
    valid: bool
    reason_code: str = "ok"
    errors: list[str] = field(default_factory=list)


def _normalize_numeric(val: Any) -> float | int | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return val
    return None


def _normalize_direction(raw: Any, kpi_direction: Any = None) -> str:
    for cand in (kpi_direction, raw):
        if isinstance(cand, str) and cand.strip() in ("higher_better", "lower_better"):
            return cand.strip()
    return "higher_better"


def _normalize_ties(raw: Any) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(x).strip() for x in raw if x is not None and str(x).strip())
    return (str(raw).strip(),) if str(raw).strip() else ()


def build_claim_ledger(
    *,
    typed_evidence: list[TypedMetricEvidence] | None = None,
    evidence_envelope: list[EvidenceItemV2] | None = None,
    fact_ledger: list[dict[str, Any]] | None = None,
) -> list[ClaimFact]:
    """Convert typed evidence, v2 envelopes, or explorer fact-ledger dicts into ``ClaimFact`` entries."""
    ledger: list[ClaimFact] = []

    if fact_ledger:
        for idx, item in enumerate(fact_ledger, start=1):
            if not isinstance(item, dict):
                continue
            part = str(item.get("part") or "metric")
            has_value_key = "value" in item or "actual" in item
            raw_val = item.get("value") if "value" in item else item.get("actual")
            norm_val = _normalize_numeric(raw_val)
            if item.get("is_missing") is True:
                norm_val = None
                is_missing = True
            elif part == "summary" and not has_value_key and not item.get("metric") and not item.get("metric_key"):
                is_missing = False
            else:
                is_missing = norm_val is None

            raw_branch = item.get("branch")
            branch = (
                str(raw_branch).strip()
                if raw_branch and str(raw_branch).strip().casefold() not in ("all", "all branches")
                else None
            )
            raw_sample = _normalize_numeric(item.get("sample_size"))
            ledger.append(
                ClaimFact(
                    fact_id=str(item.get("fact_id") or f"F{idx}"),
                    part=part,
                    subject=str(item.get("subject") or ""),
                    employee_id=str(item["employee_id"]) if item.get("employee_id") else None,
                    country=str(item["country"]) if item.get("country") else (str(item["region"]) if item.get("region") else None),
                    function=str(item["function"]) if item.get("function") else None,
                    team=str(item["team"]) if item.get("team") else None,
                    position=str(item["position"]) if item.get("position") else None,
                    branch=branch,
                    performance_level=str(item["performance_level"]) if item.get("performance_level") else None,
                    period=str(item.get("period") or ""),
                    metric_key=str(item["metric_key"]) if item.get("metric_key") else (str(item["metric"]) if item.get("metric") else None),
                    metric_name=str(item["metric_name"]) if item.get("metric_name") else None,
                    value=norm_val,
                    target=_normalize_numeric(item.get("target")),
                    achievement_percent=(
                        float(item["achievement_percent"])
                        if _normalize_numeric(item.get("achievement_percent")) is not None
                        else None
                    ),
                    display=str(item.get("display") or ("Unavailable" if is_missing else "")),
                    unit=str(item.get("unit") if item.get("unit") is not None else "%"),
                    direction=_normalize_direction(item.get("direction"), item.get("kpi_direction")),
                    ties=_normalize_ties(item.get("ties")),
                    is_missing=is_missing,
                    scoring_basis_status=str(item.get("scoring_basis_status") or "unchanged"),
                    source_link=str(item["source_link"]) if item.get("source_link") else None,
                    sample_size=int(raw_sample) if raw_sample is not None else None,
                )
            )

    if typed_evidence:
        for idx, ev in enumerate(typed_evidence, start=1):
            norm_val = _normalize_numeric(ev.actual)
            is_missing = norm_val is None
            branch = ev.branch if ev.branch and ev.branch.strip().casefold() not in ("all", "all branches") else None
            ledger.append(
                ClaimFact(
                    fact_id=f"T{idx}",
                    part="metric",
                    subject=ev.display_name or ev.kpi_key or ev.team,
                    function=None,
                    team=ev.team,
                    position=ev.position,
                    branch=branch,
                    performance_level=ev.performance_level,
                    period=ev.period,
                    metric_key=ev.kpi_key,
                    metric_name=ev.display_name,
                    value=norm_val,
                    target=_normalize_numeric(ev.target),
                    achievement_percent=ev.achievement_percent,
                    display=ev.actual_display,
                    unit=ev.unit or "%",
                    direction=_normalize_direction(ev.direction),
                    is_missing=is_missing,
                    scoring_basis_status=ev.scoring_basis_status,
                    source_link=ev.source_link,
                    sample_size=ev.sample_size if ev.sample_size else None,
                )
            )

    if evidence_envelope:
        for idx, ev in enumerate(evidence_envelope, start=1):
            norm_val = _normalize_numeric(ev.headline_value)
            is_missing = norm_val is None
            branch = (
                ev.scope.branches[0]
                if len(ev.scope.branches) == 1 and ev.scope.branches[0].strip().casefold() not in ("all", "all branches")
                else None
            )
            subject = ev.metric_display_name or ev.scope.team or ev.scope.function or ""
            ledger.append(
                ClaimFact(
                    fact_id=ev.operation_id or f"E{idx}",
                    part=ev.operation_id or "metric",
                    subject=subject,
                    employee_id=ev.scope.employee_id,
                    function=ev.scope.function,
                    team=ev.scope.team,
                    position=ev.scope.position,
                    branch=branch,
                    performance_level=ev.scope.performance_level,
                    period=", ".join(ev.scope.periods) if ev.scope.periods else "",
                    metric_key=ev.metric_id,
                    metric_name=ev.metric_display_name,
                    value=norm_val,
                    target=_normalize_numeric(ev.target_value),
                    achievement_percent=ev.achievement_percent,
                    display=ev.headline_display or ("Unavailable" if is_missing else str(norm_val)),
                    unit=ev.unit or "%",
                    direction="higher_better",
                    ties=_normalize_ties(ev.ties),
                    is_missing=is_missing,
                    source_link=ev.source_link.route if ev.source_link else None,
                )
            )

    return ledger


def _add_error(errors: list[str], code: str) -> None:
    if code not in errors:
        errors.append(code)


def _has_non_ascii_digit(text: str) -> bool:
    return any(ch.isdigit() and not ch.isascii() for ch in text)


def _allowed_numbers_from_ledger(ledger: list[ClaimFact]) -> set[float]:
    allowed: set[float] = set()
    for fact in ledger:
        for num in (fact.value, fact.target, fact.achievement_percent):
            if num is not None and not isinstance(num, bool):
                if fact.is_missing and num is fact.value:
                    continue
                fval = float(num)
                allowed.add(round(fval, 4))
                allowed.add(round(fval, 1))
        if fact.sample_size is not None:
            allowed.add(float(fact.sample_size))
        if fact.period:
            for yr in _YEAR_RE.findall(fact.period):
                allowed.add(float(yr))
            if not _ISO_PERIOD_RE.match(fact.period.strip()):
                for tok in re.findall(r"\d+(?:\.\d+)?", fact.period):
                    allowed.add(round(float(tok), 4))
                    allowed.add(round(float(tok), 1))
        if fact.employee_id:
            for tok in re.findall(r"\d+", fact.employee_id):
                allowed.add(round(float(tok), 4))
                allowed.add(round(float(tok), 1))
    return allowed


def _value_candidates(val: float | int) -> list[str]:
    fval = float(val)
    cands: list[str] = []
    if fval.is_integer():
        ival = int(fval)
        for c in (str(ival), f"{ival:,}", f"{fval:.1f}"):
            if c not in cands:
                cands.append(c)
    else:
        exact = f"{fval:.4f}".rstrip("0").rstrip(".")
        one_dec = f"{fval:.1f}"
        for c in (exact, one_dec):
            if c not in cands:
                cands.append(c)
    return cands


def _check_unit_match(fact: ClaimFact, text: str, cands: list[str]) -> bool:
    unit = (fact.unit or "").strip().casefold()
    matches: list[re.Match[str]] = []
    for cand in cands:
        for m in re.finditer(rf"(?<![\d.]){re.escape(cand)}(?!(?:\.\d)|\d)", text):
            matches.append(m)
    if not matches:
        return True

    if unit in _COUNT_UNITS:
        bad_pct = re.compile(r"^\s*%")
        bad_word = re.compile(r"^\s*(?:percent|mins?|minutes?|secs?|seconds?|hrs?|hours?|days?)\b", re.IGNORECASE)
        for m in matches:
            tail = text[m.end():m.end() + 20]
            if bad_pct.match(tail) or bad_word.match(tail):
                return False
        return True

    if unit in _PERCENT_UNITS:
        pct_suffix = re.compile(r"^\s*%")
        return any(pct_suffix.match(text[m.end():m.end() + 5]) for m in matches)

    if unit in _DURATION_UNITS:
        pct_suffix = re.compile(r"^\s*(?:%|percent\b)", re.IGNORECASE)
        for m in matches:
            tail = text[m.end():m.end() + 20]
            if pct_suffix.match(tail):
                return False
            if unit in _MINUTE_UNITS and re.match(r"^\s*(?:secs?|seconds?|hrs?|hours?|days?)\b", tail, re.IGNORECASE):
                return False
            if unit in _SECOND_UNITS and re.match(r"^\s*(?:mins?|minutes?|hrs?|hours?|days?)\b", tail, re.IGNORECASE):
                return False
            if unit in _HOUR_UNITS and re.match(r"^\s*(?:mins?|minutes?|secs?|seconds?|days?)\b", tail, re.IGNORECASE):
                return False
            if unit in _DAY_UNITS and re.match(r"^\s*(?:mins?|minutes?|secs?|seconds?|hrs?|hours?)\b", tail, re.IGNORECASE):
                return False
        return True

    return True


def _has_co_tied_peers(fact: ClaimFact) -> bool:
    if len(fact.ties) >= 2:
        return True
    if len(fact.ties) == 1:
        peer = fact.ties[0].strip().casefold()
        subj = fact.subject.strip().casefold()
        return bool(peer) and peer != subj
    return False


def _facts_are_comparable(a: ClaimFact, b: ClaimFact) -> bool:
    if a.metric_key and b.metric_key and a.metric_key != b.metric_key:
        return False
    if a.unit and b.unit and a.unit.casefold() != b.unit.casefold():
        return False
    return True


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?;])\s+", text) if s.strip()]


def _find_subject_pos(subj: str, text_lower: str) -> int:
    subj_cf = subj.strip().casefold()
    if not subj_cf:
        return -1
    pos = text_lower.find(subj_cf)
    if pos >= 0:
        return pos
    first_word = subj_cf.split()[0]
    return text_lower.find(first_word)


def _check_null_coerced_to_zero(ledger: list[ClaimFact], combined_text: str) -> bool:
    missing_facts = [f for f in ledger if f.is_missing or (f.value is None and f.part != "summary")]
    if not missing_facts:
        return False
    has_real_zero = any(
        not f.is_missing and f.value is not None and float(f.value) == 0.0
        for f in ledger
    )
    if not has_real_zero:
        return bool(_ZERO_CLAIM_RE.search(combined_text))

    # A real 0.0 exists on another fact: only reject zero attributed to a missing fact's clause.
    for sent in _split_sentences(combined_text):
        sent_lower = sent.casefold()
        if not _ZERO_CLAIM_RE.search(sent):
            continue
        for fact in missing_facts:
            if not fact.subject:
                continue
            pos = _find_subject_pos(fact.subject, sent_lower)
            if pos < 0:
                continue
            # Look at the local window around the missing subject before any non-missing subject.
            window_end = len(sent_lower)
            for other in ledger:
                if other is fact or other.is_missing or not other.subject:
                    continue
                opos = _find_subject_pos(other.subject, sent_lower)
                if opos > pos:
                    window_end = min(window_end, opos)
            segment = sent_lower[pos:window_end]
            if _ZERO_CLAIM_RE.search(segment) and not re.search(
                r"\b(?:unavailable|missing|not\s+recorded|no\s+data)\b", segment
            ):
                return True
    return False


def validate_claims(
    *,
    headline: str,
    bullets: list[str] | None = None,
    ledger: list[ClaimFact],
    cited_fact_ids: list[str] | None = None,
    required_parts: list[str] | None = None,
) -> ClaimValidationResult:
    """Validate headline + bullets against a ``ClaimFact`` ledger across 8 deterministic checks."""
    errors: list[str] = []
    bullet_list = [b for b in (bullets or []) if isinstance(b, str)]
    all_texts = [headline] + bullet_list

    # 1. Sanity & Injection
    if not isinstance(headline, str) or not headline.strip():
        _add_error(errors, "unsafe_or_too_long")
        return ClaimValidationResult(valid=False, reason_code="unsafe_or_too_long", errors=errors)

    if len(headline.strip()) > 360 or any(len(b.strip()) > 360 for b in bullet_list):
        _add_error(errors, "unsafe_or_too_long")

    for item in all_texts:
        if (
            _has_non_ascii_digit(item)
            or _CONTROL_OR_HTML_RE.search(item)
            or _MARKDOWN_TABLE_RE.search(item)
            or _PROMPT_INJECTION_RE.search(item)
        ):
            _add_error(errors, "unsafe_or_too_long")
            break

    # 2. Fact ID & Required-Part Coverage
    known_by_id = {f.fact_id: f for f in ledger if f.fact_id}
    if cited_fact_ids is not None:
        if any(not isinstance(fid, str) or fid not in known_by_id for fid in cited_fact_ids):
            _add_error(errors, "unknown_fact_id")
        elif not cited_fact_ids or (set(known_by_id.keys()) - set(cited_fact_ids)):
            _add_error(errors, "incomplete_fact_coverage")

    if required_parts is not None:
        ledger_parts = {f.part for f in ledger if f.part}
        if any(part not in ledger_parts for part in required_parts):
            _add_error(errors, "incomplete_fact_coverage")

    combined_text = " ".join(t.strip() for t in all_texts if t and t.strip())
    combined_lower = combined_text.casefold()

    # 3a. Subject presence (Check 5a)
    subject_positions: dict[str, int] = {}
    for fact in ledger:
        if fact.subject:
            pos = _find_subject_pos(fact.subject, combined_lower)
            if pos < 0:
                _add_error(errors, "missing_subject")
            else:
                subject_positions[fact.fact_id] = pos

    # 3b. Null coerced to zero (Check 3)
    if _check_null_coerced_to_zero(ledger, combined_text):
        _add_error(errors, "null_coerced_to_zero")

    # 3c & 4. Numeric presence & Unit fidelity for non-missing facts
    fact_positions: list[tuple[ClaimFact, float, int, int]] = []
    for fact in ledger:
        if fact.is_missing or fact.value is None:
            continue
        fval = float(fact.value)
        cands = _value_candidates(fact.value)
        val_pos = -1
        for cand in cands:
            m_val = re.search(rf"(?<![\d.]){re.escape(cand)}(?!(?:\.\d)|\d)", combined_text)
            if m_val:
                val_pos = m_val.start()
                break
        if val_pos < 0:
            _add_error(errors, "missing_fact_value")
        else:
            if not _check_unit_match(fact, combined_text, cands):
                _add_error(errors, "mismatched_unit")
            if fact.fact_id in subject_positions:
                fact_positions.append((fact, fval, subject_positions[fact.fact_id], val_pos))

    # 7. Period, Country, Branch & Scope Alignment
    allowed_months: set[str] = set()
    allowed_years: set[str] = set()
    for fact in ledger:
        if not fact.period:
            continue
        per_cf = fact.period.casefold()
        for m_name in _CANONICAL_MONTHS:
            if m_name in per_cf:
                allowed_months.add(m_name)
        m_iso = _ISO_PERIOD_RE.match(fact.period.strip())
        if m_iso:
            m_human = _REVERSE_MONTHS_BY_NUM.get(int(m_iso.group(2)))
            if m_human:
                allowed_months.add(m_human.casefold())
        for yr in _YEAR_RE.findall(fact.period):
            allowed_years.add(yr)

    if allowed_months:
        for m_name in _CANONICAL_MONTHS:
            if re.search(rf"\b{re.escape(m_name)}\b", combined_lower) and m_name not in allowed_months:
                _add_error(errors, "mismatched_period")
                break
    if allowed_years:
        for yr in _YEAR_RE.findall(combined_text):
            if yr not in allowed_years:
                _add_error(errors, "mismatched_period")
                break

    countries = {
        fact.country.strip().upper()
        for fact in ledger
        if fact.country and fact.country.strip().upper() in ("EGY", "UAE")
    }
    if countries == {"EGY"} and _UAE_WORD_RE.search(combined_text):
        _add_error(errors, "mismatched_country")
    elif countries == {"UAE"} and _EGY_WORD_RE.search(combined_text):
        _add_error(errors, "mismatched_country")

    allowed_branches: set[str] = set()
    for fact in ledger:
        if fact.branch and fact.branch.strip().casefold() not in ("all", "all branches"):
            allowed_branches.add(fact.branch.strip().casefold())
        for source_text in (fact.subject, fact.team, fact.metric_name):
            if not source_text:
                continue
            sl = source_text.casefold()
            for kb in _KNOWN_BRANCHES:
                if re.search(rf"\b{kb}\b", sl):
                    allowed_branches.add(kb)
    for kb in _KNOWN_BRANCHES:
        if re.search(rf"\b{kb}\b", combined_lower) and kb not in allowed_branches:
            _add_error(errors, "mismatched_branch")
            break

    levels = {
        fact.performance_level.strip().casefold()
        for fact in ledger
        if fact.performance_level and fact.performance_level.strip()
    }
    if levels:
        for lvl in ("employee", "managerial", "corporate"):
            if re.search(rf"\b{lvl}\b", combined_lower) and lvl not in levels:
                # Ignore if the word is literally part of a metric/team/subject name in the ledger.
                in_labels = any(
                    re.search(rf"\b{lvl}\b", str(s).casefold())
                    for fact in ledger
                    for s in (fact.subject, fact.team, fact.metric_name)
                    if s
                )
                if not in_labels:
                    _add_error(errors, "mismatched_scope")
                    break

    # 3d. Invented numbers
    allowed_numbers = _allowed_numbers_from_ledger(ledger)
    for token in _NUMBER_TOKEN_RE.findall(combined_text):
        num_val = float(token.replace(",", ""))
        if round(num_val, 4) not in allowed_numbers and round(num_val, 1) not in allowed_numbers:
            _add_error(errors, "invented_number")
            break

    # 5b & 6. Swapped values, tie disclosure, magnitude & polarity-aware comparisons
    has_tie_in_ledger = any(_has_co_tied_peers(fact) for fact in ledger)
    if not has_tie_in_ledger:
        for i in range(len(fact_positions)):
            f_i, v_i, _, _ = fact_positions[i]
            for j in range(i + 1, len(fact_positions)):
                f_j, v_j, _, _ = fact_positions[j]
                if f_i.subject.casefold() != f_j.subject.casefold() and _facts_are_comparable(f_i, f_j):
                    if round(v_i, 4) == round(v_j, 4):
                        has_tie_in_ledger = True
                        break
            if has_tie_in_ledger:
                break

    if has_tie_in_ledger and _EXCLUSIVE_WINNER_LOSER_RE.search(combined_text) and not _TIE_WORDING_RE.search(combined_text):
        _add_error(errors, "undisclosed_tie")

    # Swapped subject-to-value binding
    for i in range(len(fact_positions)):
        f_i, v_i, s_pos_i, v_pos_i = fact_positions[i]
        for j in range(i + 1, len(fact_positions)):
            f_j, v_j, s_pos_j, v_pos_j = fact_positions[j]
            if round(v_i, 4) == round(v_j, 4) or s_pos_i == s_pos_j or v_pos_i == v_pos_j:
                continue
            if f_i.subject.casefold() == f_j.subject.casefold():
                continue
            if (s_pos_i < s_pos_j) != (v_pos_i < v_pos_j):
                _add_error(errors, "swapped_fact_values")

    # Sentence-level binary & superlative comparison checks
    sentences = _split_sentences(combined_text)
    for sent in sentences:
        sent_lower = sent.casefold()
        present: list[tuple[ClaimFact, float, int]] = []
        for fact, fval, _, _ in fact_positions:
            pos = _find_subject_pos(fact.subject, sent_lower)
            if pos >= 0:
                present.append((fact, fval, pos))
        present.sort(key=lambda item: item[2])

        for i in range(len(present)):
            f_a, v_a, pos_a = present[i]
            for j in range(i + 1, len(present)):
                f_b, v_b, pos_b = present[j]
                if f_a.subject.casefold() == f_b.subject.casefold() or pos_a == pos_b:
                    continue
                if round(v_a, 4) == round(v_b, 4):
                    continue
                between = sent_lower[pos_a:pos_b]
                if _MAGNITUDE_HIGHER_RE.search(between) and not (v_a > v_b):
                    _add_error(errors, "contradictory_comparison")
                if _MAGNITUDE_LOWER_RE.search(between) and not (v_a < v_b):
                    _add_error(errors, "contradictory_comparison")

                effective_dir = f_a.direction if f_a.direction == f_b.direction else "higher_better"
                if effective_dir == "lower_better":
                    # Smaller value is BETTER performance.
                    if _EVAL_BETTER_RE.search(between) and not (v_a < v_b):
                        _add_error(errors, "inverted_polarity")
                    if _EVAL_WORSE_RE.search(between) and not (v_a > v_b):
                        _add_error(errors, "inverted_polarity")
                else:
                    if _EVAL_BETTER_RE.search(between) and not (v_a > v_b):
                        _add_error(errors, "contradictory_comparison")
                    if _EVAL_WORSE_RE.search(between) and not (v_a < v_b):
                        _add_error(errors, "contradictory_comparison")

        # Unary superlatives ("best"/"strongest" vs "worst"/"weakest") when >= 2 comparable facts exist
        if len(present) == 1:
            f_only, v_only, _ = present[0]
            peers = [
                (f_p, v_p)
                for f_p, v_p, _, _ in fact_positions
                if f_p.fact_id != f_only.fact_id and _facts_are_comparable(f_only, f_p) and round(v_p, 4) != round(v_only, 4)
            ]
            if peers:
                is_max = all(v_only > v_p for _, v_p in peers)
                is_min = all(v_only < v_p for _, v_p in peers)
                if f_only.direction == "lower_better":
                    if _SUPERLATIVE_BEST_RE.search(sent_lower) and not is_min:
                        _add_error(errors, "inverted_polarity")
                    if _SUPERLATIVE_WORST_RE.search(sent_lower) and not is_max:
                        _add_error(errors, "inverted_polarity")
                else:
                    if _SUPERLATIVE_BEST_RE.search(sent_lower) and not is_max:
                        _add_error(errors, "contradictory_comparison")
                    if _SUPERLATIVE_WORST_RE.search(sent_lower) and not is_min:
                        _add_error(errors, "contradictory_comparison")

    # 8. Banned Causal Leaps & Employment/HR Hallucinations
    for sent in sentences:
        if _CAUSAL_RE.search(sent) and not _CAUSAL_CAVEAT_RE.search(sent):
            _add_error(errors, "unsupported_causation")
            break

    if _HR_HALLUCINATION_RE.search(combined_text):
        _add_error(errors, "invented_hr_fact")

    return ClaimValidationResult(
        valid=len(errors) == 0,
        reason_code=errors[0] if errors else "ok",
        errors=errors,
    )

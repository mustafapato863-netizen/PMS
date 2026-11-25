"""Searchable local PMS Product Guide loader, validator, and fuzzy retriever.

Loads approved markdown documentation from ``Backend/services/ai/guide_content/``
once per process, validates index metadata, headings, and permitted page IDs,
enforces caller role/scope access, and resolves page destinations strictly
through ``get_authorized_navigation_targets``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any

from models.ai_schemas import AiNavigationTarget, AiPageHelpSection, SessionFilterContext
from services.ai.contextual_assistant import get_authorized_navigation_targets, is_self_only
from utils.report_scope import user_can_access_team_level

GUIDE_CONTENT_DIR = Path(__file__).resolve().parent / "guide_content"

PERMITTED_GUIDE_PAGE_IDS: frozenset[str] = frozenset(
    {
        "corrective_actions",
        "overview",
        "team_dashboard",
        "monthly_evaluation",
        "insights",
        "monthly_presentation",
        "balanced_scorecard",
    }
)

_PAGE_ID_TO_NAV_ID: dict[str, str] = {
    "corrective_actions": "nav-corrective-actions",
    "overview": "nav-monthly-presentation",
    "team_dashboard": "nav-team-dashboard",
    "insights": "nav-insights",
    "monthly_presentation": "nav-monthly-presentation",
    "balanced_scorecard": "nav-balanced-scorecard",
}

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "define",
        "definition", "describe", "do", "does", "explain", "for", "from",
        "how", "i", "in", "info", "is", "it", "me", "mean", "meaning",
        "means", "my", "of", "on", "or", "please", "show", "tell", "the",
        "to", "want", "we", "what", "where", "which", "with", "you",
    }
)

GRADE_DEFINITIONS: dict[str, tuple[str, str, str]] = {
    "A": ("Excellent", "95.0%–100.0%", "Top-tier performance exceeding expectations across weighted KPIs."),
    "B": ("Meet Expectations", "90.0%–94.9%", "On-target performance meeting the 90% PMS benchmark."),
    "C": (
        "Average",
        "80.0%–89.9%",
        "Acceptable mid-range performance, below the 90% Meet Expectations benchmark; usually needs targeted coaching on 1–2 KPI gaps to reach Grade B.",
    ),
    "D": (
        "Below Average",
        "70.0%–79.9%",
        "Underperforming; flagged on the Teams at Risk watchlist and requires focused coaching or a structured improvement plan.",
    ),
    "E": (
        "Unsatisfactory",
        "below 70.0%",
        "Critical performance deficit; flagged as Critical <70% on Teams at Risk and requires immediate corrective action or PIP review.",
    ),
}

_ASKED_GRADE_LETTER_RE = re.compile(
    r"(?:\bgrade\s+([a-e])\b|\b([a-e])\s+grade\b|تقدير\s+([a-e])\b)",
    re.I,
)

_DATA_QUERY_EXCLUDE_RE = re.compile(
    r"\b(?:how\s+many|who\s+(?:is|are|was|were|got|has|have|scored)|list\s+|count\s+|"
    r"compare\s+|\bvs\b|versus|dropped|trend|trajectory|lowest|worst|best|highest|"
    r"top\s+\d+|bottom\s+\d+|rank(?:ed|ing)?|sghd\d+|emp[-_ ]?\d+|"
    r"january|february|march|april|june|july|august|september|october|november|december|"
    r"202[4-9]|203\d|percentage\s+points?|in\s+(?:this|your)\s+(?:answer|reply|response))\b",
    re.I,
)

_SYSTEM_KNOWLEDGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Grade meanings & thresholds (e.g. "what c grade mean", "what does grade C mean", "explain grades")
    re.compile(
        r"\b(?:what\s+(?:does\s+|is\s+|are\s+)?(?:a\s+|the\s+)?(?:grade\s+[a-e]|[a-e]\s+grade|grades?)\s*(?:mean|meaning|threshold|thresholds|scale|range|score)?|"
        r"(?:explain|define|describe|tell\s+me\s+about)\s+(?:the\s+)?(?:grade\s+[a-e]|[a-e]\s+grade|grades?|grading\s+(?:scale|system))|"
        r"(?:grade\s+[a-e]|[a-e]\s+grade)\s+(?:meaning|definition|threshold|range|score)|"
        r"grade\s+(?:thresholds?|scale|definitions?|meanings?|system)|grading\s+(?:scale|system|rules?))\b"
        r"|معنى\s+تقدير|ما\s+معنى\s+(?:التقدير|grade)|تقديرات\s+النظام|درجات\s+التقييم",
        re.I,
    ),
    # Scoring rules, achievement cap, Gap vs Gap Share
    re.compile(
        r"\b(?:what\s+(?:is|does|are)\s+(?:the\s+)?(?:gap\s+share|gap\s+to\s+100|achievement\s+cap|100%\s+cap|scoring\s+(?:formula|rules?)|weighted\s+score|higher\s+is\s+better|lower\s+is\s+better|diagnostic\s+kpi|zero[- ]weight\s+kpi)\b|"
        r"gap\s+(?:vs|versus)\s+gap\s+share|"
        r"how\s+(?:is|are|does|do)\s+(?:the\s+)?(?:gap\s+share|scores?|scoring|grades?|achievement\s+cap|weighted\s+scores?|branch\s+filter)\s+(?:calculated|computed|determined|work)|"
        r"(?:explain|define|describe)\s+(?:the\s+)?(?:gap\s+share|scoring\s+(?:formula|rules?)|achievement\s+cap))\b"
        r"|نسبة\s+الفجوة|حصة\s+الفجوة|طريقة\s+حساب\s+التقييم|معادلة\s+حساب\s+النتيجة",
        re.I,
    ),
    # Teams at Risk, Key Movers, Executive Summary vs Monthly Review, Balanced Scorecard, Roles/RBAC, KPI glossary, System overview
    re.compile(
        r"\b(?:what\s+(?:is|does|are)\s+(?:the\s+)?(?:pms|balanced\s+scorecard|bsc|rbac|teams?\s+at\s+risk|primary\s+bottleneck\s+kpi|key\s+movers|critical\s*<?\s*70%?|falling\s+2\s+mo|below\s+90%?|performance\s+levels?|user\s+roles?|executive\s+summary|monthly\s+review|monthly\s+report|aht|tat|cpl)\b|"
        r"(?:explain|define|describe)\s+(?:the\s+)?(?:pms\s+system|balanced\s+scorecard|bsc|rbac|teams?\s+at\s+risk|performance\s+levels?|user\s+roles?|kpi\s+glossary|kpi\s+directions?)|"
        r"how\s+does\s+(?:pms|the\s+system|balanced\s+scorecard|bsc|branch\s+filter(?:ing)?)\s+work\b|"
        r"(?:tell\s+me|give\s+me)\s+(?:a\s+)?(?:br[ie]{1,2}f|overview|summary|guide)\s+(?:for|about|of)\s+(?:the\s+)?(?:system|pms)\b|"
        r"(?:system|pms|product)\s+(?:overview|guide|brief|breef)|"
        r"(?:what\s+roles|what\s+branches|what\s+kpis)\s+(?:exist|are\s+tracked|are\s+available|are\s+in)\s+(?:in\s+)?(?:pms|the\s+system|uae)\b|"
        r"executive\s+summary\s+(?:vs|versus)\s+monthly\s+(?:review|report)|"
        r"employee\s+(?:vs|versus)\s+managerial\s+(?:vs|versus)\s+corporate)\b"
        r"|نظرة\s+عامة\s+على\s+النظام|ملخص\s+النظام|بطاقة\s+الأداء\s+المتوازن|صلاحيات\s+المستخدمين|دليل\s+مؤشرات\s+الأداء|الفرق\s+المعرضة\s+للخطر",
        re.I,
    ),
)


def extract_asked_grade_letter(prompt: str) -> str | None:
    """Return 'A'..'E' when the user asks specifically about one PMS grade letter."""
    match = _ASKED_GRADE_LETTER_RE.search(prompt or "")
    if not match:
        return None
    for grp in match.groups():
        if grp:
            return grp.upper()
    return None


def is_system_knowledge_question(prompt: str) -> bool:
    """Return True when the prompt asks a general PMS system/concept question (not a live data query)."""
    text = (prompt or "").strip()
    if not text:
        return False
    # Allow explicit "gap vs gap share" or "executive summary vs monthly review" even though they contain "vs"
    has_conceptual_vs = bool(
        re.search(
            r"\b(?:gap\s+(?:vs|versus)\s+gap\s+share|executive\s+summary\s+(?:vs|versus)\s+monthly|"
            r"employee\s+(?:vs|versus)\s+managerial|higher\s+is\s+better\s+(?:vs|versus)\s+lower|"
            r"all\s+actions\s+(?:vs|versus)\s+follow[- ]?up|egy\s+(?:vs|versus)\s+uae\s+regions)\b",
            text,
            re.I,
        )
    )
    if not has_conceptual_vs and _DATA_QUERY_EXCLUDE_RE.search(text):
        return False
    if re.search(r"\bhere\s*[?.!]*$", text, re.I):
        return False
    return any(pat.search(text) for pat in _SYSTEM_KNOWLEDGE_PATTERNS)


def format_guide_matches_for_help(
    prompt: str,
    matches: list[GuideSearchMatch],
    *,
    fallback_page_id: str = "ai_workspace",
) -> tuple[str, list[str], AiPageHelpSection, list[AiNavigationTarget], list[str]]:
    """Format matched Product Guide sections into a clear, grounded contextual help response."""
    primary = matches[0]
    sec = primary.section
    asked_grade = extract_asked_grade_letter(prompt) if sec.id == "pms-grade-scale" else None

    if asked_grade and asked_grade in GRADE_DEFINITIONS:
        label, score_range, desc = GRADE_DEFINITIONS[asked_grade]
        headline = f"Grade {asked_grade} means {label} ({score_range}): {desc}"
    else:
        headline = sec.summary or sec.title

    bullets: list[str] = []
    for step in sec.steps[:6]:
        bullets.append(step)

    if len(matches) > 1 and len(bullets) < 5:
        secondary = matches[1].section
        if secondary.summary and secondary.summary != headline:
            bullets.append(f"{secondary.title}: {secondary.summary}")

    nav_targets: list[AiNavigationTarget] = []
    seen_routes: set[str] = set()
    for m in matches:
        if m.navigation_target and m.navigation_target.route not in seen_routes:
            seen_routes.add(m.navigation_target.route)
            nav_targets.append(m.navigation_target)

    section_payload = AiPageHelpSection(
        page_id=sec.page_id or fallback_page_id,
        page_title=sec.title,
        summary=headline,
        key_elements=bullets[:6],
        available_actions=[
            f"Guide reference: {sec.file} ({sec.title}, v{sec.version})",
        ],
    )

    followups_by_id: dict[str, list[str]] = {
        "pms-grade-scale": [
            "How are KPI scores and the 100% cap calculated?",
            "What is the difference between Gap and Gap Share?",
            "What do the Teams at Risk status badges mean?",
        ],
        "pms-scoring-formula": [
            "What do Grades A through E mean?",
            "What is the difference between Gap and Gap Share?",
            "What KPIs are tracked in PMS?",
        ],
        "pms-gap-vs-gap-share": [
            "What do Grades A through E mean?",
            "What do the Teams at Risk status badges mean?",
            "How are KPI scores calculated?",
        ],
    }
    followups = followups_by_id.get(
        sec.id,
        [
            "What do Grades A through E mean?",
            "How are KPI scores calculated?",
            "Give me an overview of the PMS system",
        ],
    )
    return headline, bullets[:6], section_payload, nav_targets[:3], followups[:3]


class ProductGuideValidationError(ValueError):
    """Raised when guide index or markdown content fails structural validation."""


@dataclass(frozen=True)
class GuideSection:
    id: str
    title: str
    file: str
    heading: str
    page_id: str
    audiences: tuple[str, ...]
    synonyms: tuple[str, ...]
    version: str
    body: str
    summary: str
    steps: tuple[str, ...]
    search_tokens: tuple[str, ...]
    search_token_set: frozenset[str] = frozenset()
    normalized_phrases: tuple[str, ...] = ()
    title_syn_tokens: tuple[str, ...] = ()
    title_syn_token_set: frozenset[str] = frozenset()


@dataclass(frozen=True)
class LoadedProductGuide:
    guide_version: str
    sections: tuple[GuideSection, ...]
    sections_by_id: dict[str, GuideSection]


@dataclass(frozen=True)
class GuideSearchMatch:
    section: GuideSection
    score: float
    navigation_target: AiNavigationTarget | None


def _normalize_text(text: str) -> str:
    """Normalize English/Arabic text and strip punctuation for robust local search."""
    s = (text or "").strip().casefold()
    # Normalize common Arabic letter variants so spelling differences still match
    s = (
        s.replace("\u0623", "\u0627")  # أ -> ا
        .replace("\u0625", "\u0627")  # إ -> ا
        .replace("\u0622", "\u0627")  # آ -> ا
        .replace("\u0629", "\u0647")  # ة -> ه
        .replace("\u0649", "\u064a")  # ى -> ي
    )
    s = re.sub(r"[^a-z0-9\u0600-\u06ff\s-]", " ", s)
    s = s.replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def _tokenize(text: str) -> list[str]:
    norm = _normalize_text(text)
    return [tok for tok in norm.split() if tok and tok not in _STOP_WORDS]


def _extract_markdown_sections(markdown_text: str) -> dict[str, str]:
    """Parse ``## Heading`` sections from a markdown document."""
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None
    for raw_line in markdown_text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", raw_line)
        if m:
            current_heading = m.group(1).strip()
            sections[current_heading] = []
            continue
        if current_heading is not None:
            sections[current_heading].append(raw_line)
    return {heading: "\n".join(lines).strip() for heading, lines in sections.items()}


def _extract_summary_and_steps(body: str) -> tuple[str, tuple[str, ...]]:
    summary = ""
    steps: list[str] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^(?:\d+\.|-|\*)\s+", line):
            cleaned = re.sub(r"^(?:\d+\.|-|\*)\s+", "", line).strip()
            if cleaned:
                steps.append(cleaned)
        elif not summary:
            summary = line
    if not summary and steps:
        summary = steps[0]
    return summary, tuple(steps)


def load_product_guide_from_dir(content_dir: Path) -> LoadedProductGuide:
    """Load and validate guide index and markdown sections from ``content_dir``."""
    index_path = content_dir / "index.json"
    if not index_path.is_file():
        raise ProductGuideValidationError(f"Guide index file not found: {index_path}")

    try:
        raw_index = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ProductGuideValidationError(f"Invalid guide index JSON: {exc}") from exc

    guide_version = str(raw_index.get("guide_version") or "").strip()
    raw_sections = raw_index.get("sections")
    if not guide_version or not isinstance(raw_sections, list) or not raw_sections:
        raise ProductGuideValidationError("Guide index requires non-empty 'guide_version' and 'sections'.")

    resolved_root = content_dir.resolve()
    parsed_files: dict[str, dict[str, str]] = {}
    sections: list[GuideSection] = []
    seen_ids: set[str] = set()

    for entry in raw_sections:
        if not isinstance(entry, dict):
            raise ProductGuideValidationError("Each guide section entry must be an object.")
        sec_id = str(entry.get("id") or "").strip()
        title = str(entry.get("title") or "").strip()
        rel_file = str(entry.get("file") or "").strip()
        heading = str(entry.get("heading") or "").strip()
        page_id = str(entry.get("page_id") or "").strip()
        version = str(entry.get("version") or guide_version).strip()
        audiences_raw = entry.get("audiences")
        synonyms_raw = entry.get("synonyms") or []

        if not sec_id or sec_id in seen_ids:
            raise ProductGuideValidationError(f"Duplicate or missing section id: {sec_id!r}")
        seen_ids.add(sec_id)
        if not title or not rel_file or not heading:
            raise ProductGuideValidationError(f"Section {sec_id!r} missing title, file, or heading.")
        if page_id not in PERMITTED_GUIDE_PAGE_IDS:
            raise ProductGuideValidationError(
                f"Section {sec_id!r} uses unpermitted page_id {page_id!r}; allowed: {sorted(PERMITTED_GUIDE_PAGE_IDS)}"
            )
        if not isinstance(audiences_raw, list) or not audiences_raw:
            raise ProductGuideValidationError(f"Section {sec_id!r} must define non-empty 'audiences'.")

        file_path = (content_dir / rel_file).resolve()
        if resolved_root not in file_path.parents or not file_path.is_file():
            raise ProductGuideValidationError(f"Section {sec_id!r} references missing/invalid file: {rel_file!r}")

        if rel_file not in parsed_files:
            parsed_files[rel_file] = _extract_markdown_sections(file_path.read_text(encoding="utf-8"))

        body = parsed_files[rel_file].get(heading, "").strip()
        if not body:
            raise ProductGuideValidationError(
                f"Section {sec_id!r} heading {heading!r} not found or empty in {rel_file!r}."
            )

        summary, steps = _extract_summary_and_steps(body)
        synonyms = tuple(str(s).strip() for s in synonyms_raw if str(s).strip())
        audiences = tuple(str(a).strip() for a in audiences_raw if str(a).strip())
        tokens = tuple(dict.fromkeys(_tokenize(" ".join([title, *synonyms, body]))))
        normalized_phrases = tuple(
            dict.fromkeys(p for p in (_normalize_text(phrase) for phrase in (title, *synonyms)) if p)
        )
        title_syn_tokens = tuple(dict.fromkeys(_tokenize(" ".join([title, *synonyms]))))

        sections.append(
            GuideSection(
                id=sec_id,
                title=title,
                file=rel_file,
                heading=heading,
                page_id=page_id,
                audiences=audiences,
                synonyms=synonyms,
                version=version,
                body=body,
                summary=summary,
                steps=steps,
                search_tokens=tokens,
                search_token_set=frozenset(tokens),
                normalized_phrases=normalized_phrases,
                title_syn_tokens=title_syn_tokens,
                title_syn_token_set=frozenset(title_syn_tokens),
            )
        )

    return LoadedProductGuide(
        guide_version=guide_version,
        sections=tuple(sections),
        sections_by_id={sec.id: sec for sec in sections},
    )


@lru_cache(maxsize=1)
def get_product_guide() -> LoadedProductGuide:
    """Return the process-cached, validated PMS Product Guide."""
    return load_product_guide_from_dir(GUIDE_CONTENT_DIR)


def is_section_authorized(section: GuideSection, scope: dict[str, Any]) -> bool:
    """Return True iff the caller's role/scope is authorized to read ``section``."""
    role = str(scope.get("role") or "").strip()
    if "*" in section.audiences:
        return True
    if is_self_only(scope):
        return False
    return role in section.audiences


def resolve_guide_navigation_target(
    page_id: str,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
) -> AiNavigationTarget | None:
    """Resolve a guide ``page_id`` exclusively through authorized navigation targets."""
    role = str(scope.get("role") or "").strip()
    if page_id == "monthly_evaluation":
        if role != "Admin":
            return None
        return AiNavigationTarget(
            id="nav-monthly-evaluation-settings",
            label="Open Monthly Evaluation Settings →",
            route="/settings?tab=evaluation",
            description="Configure monthly KPI targets and weights via Save → Preview → Approve → Apply.",
            icon_key="planning",
        )

    targets = get_authorized_navigation_targets(scope, session_state)
    target_id = _PAGE_ID_TO_NAV_ID.get(page_id)
    if target_id:
        for t in targets:
            if t.id == target_id:
                return t

    if page_id == "team_dashboard":
        team_name = (session_state.team or "").strip()
        if team_name and user_can_access_team_level(scope, team_name, session_state.performance_level or "Employee"):
            for t in targets:
                if t.id == "nav-team-dashboard":
                    return t
        # Generic team navigation falls back to authorized Monthly Presentation or Insights
        for fallback_id in ("nav-monthly-presentation", "nav-insights"):
            for t in targets:
                if t.id == fallback_id:
                    return t
        return None

    if page_id == "overview":
        return targets[0] if targets else None

    return None


def _token_fuzzy_similarity(
    query_tok: str,
    candidate_tokens: tuple[str, ...],
    candidate_token_set: frozenset[str] | None = None,
) -> float:
    if not query_tok or not candidate_tokens:
        return 0.0
    if candidate_token_set is not None:
        if query_tok in candidate_token_set:
            return 1.0
    elif query_tok in candidate_tokens:
        return 1.0
    q_len = len(query_tok)
    if q_len <= 2:
        return 0.0
    best = 0.0
    for c_tok in candidate_tokens:
        c_len = len(c_tok)
        if q_len >= 4 and (c_tok.startswith(query_tok) or query_tok.startswith(c_tok)):
            if best < 0.88:
                best = 0.88
            continue
        total_len = q_len + c_len
        min_needed = 0.72 * total_len
        # Mathematical upper bound: matching blocks cannot exceed min(q_len, c_len)
        if 2 * (q_len if q_len < c_len else c_len) < min_needed:
            continue
        # Mathematical upper bound: every matched char in query_tok must occur in c_tok
        common_upper = 0
        for ch in query_tok:
            if ch in c_tok:
                common_upper += 1
        if 2 * common_upper < min_needed:
            continue
        sm = SequenceMatcher(None, query_tok, c_tok)
        if sm.quick_ratio() < 0.72:
            continue
        ratio = sm.ratio()
        if ratio >= 0.72 and ratio > best:
            best = ratio
    return best


def _score_section(query_norm: str, query_tokens: list[str], section: GuideSection) -> float:
    if not query_norm:
        return 0.0

    # 1. Exact or near-exact synonym / title phrase match (pre-normalized at load time)
    best_phrase = 0.0
    q_len = len(query_norm)
    phrases = section.normalized_phrases or tuple(
        p for p in (_normalize_text(phrase) for phrase in (section.title, *section.synonyms)) if p
    )
    for p_norm in phrases:
        if p_norm == query_norm:
            return 1.0
        if p_norm in query_norm or query_norm in p_norm:
            best_phrase = max(best_phrase, 0.90)
        elif abs(q_len - len(p_norm)) <= max(12, q_len // 2):
            sim = SequenceMatcher(None, query_norm, p_norm).ratio()
            if sim >= 0.62:
                best_phrase = max(best_phrase, sim * 0.92)

    # 2. Token-level fuzzy coverage against title + synonyms + section body
    token_score = 0.0
    if query_tokens:
        title_syn_tokens = section.title_syn_tokens or tuple(
            dict.fromkeys(_tokenize(" ".join([section.title, *section.synonyms])))
        )
        title_syn_set = section.title_syn_token_set or frozenset(title_syn_tokens)
        syn_hits = sum(_token_fuzzy_similarity(tok, title_syn_tokens, title_syn_set) for tok in query_tokens)
        syn_score = (syn_hits / len(query_tokens)) * 0.95
        token_score = syn_score
        # Skip scanning body tokens if phrase or title/synonym already beats the 0.82 body ceiling
        if max(best_phrase, syn_score) < 0.82:
            body_set = section.search_token_set or frozenset(section.search_tokens)
            body_hits = sum(_token_fuzzy_similarity(tok, section.search_tokens, body_set) for tok in query_tokens)
            token_score = max(syn_score, (body_hits / len(query_tokens)) * 0.82)

    return round(max(best_phrase, token_score), 4)


def search_product_guide(
    query: str,
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    max_results: int = 3,
    page_id: str | None = None,
    min_score: float = 0.42,
    guide: LoadedProductGuide | None = None,
) -> list[GuideSearchMatch]:
    """Search authorized product guide sections locally with fuzzy typo tolerance."""
    loaded = guide or get_product_guide()
    query_norm = _normalize_text(query)
    query_tokens = _tokenize(query)

    candidates: list[tuple[float, GuideSection]] = []
    for section in loaded.sections:
        if not is_section_authorized(section, scope):
            continue
        if page_id and section.page_id != page_id:
            continue
        score = _score_section(query_norm, query_tokens, section)
        if score < min_score:
            continue
        candidates.append((score, section))

    candidates.sort(key=lambda item: (-item[0], item[1].id))
    top_candidates = candidates[: max(1, min(max_results, 3))]
    return [
        GuideSearchMatch(
            section=sec,
            score=score,
            navigation_target=resolve_guide_navigation_target(sec.page_id, scope, session_state),
        )
        for score, sec in top_candidates
    ]


def get_guide_section_by_id(
    section_id: str,
    *,
    scope: dict[str, Any],
    session_state: SessionFilterContext,
    guide: LoadedProductGuide | None = None,
) -> GuideSearchMatch | None:
    """Fetch a specific guide section by stable ID if authorized."""
    loaded = guide or get_product_guide()
    section = loaded.sections_by_id.get(section_id)
    if section is None or not is_section_authorized(section, scope):
        return None
    nav_target = resolve_guide_navigation_target(section.page_id, scope, session_state)
    return GuideSearchMatch(section=section, score=1.0, navigation_target=nav_target)

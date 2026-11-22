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

from models.ai_schemas import AiNavigationTarget, SessionFilterContext
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
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "i", "in", "is", "it", "me", "my", "of", "on",
        "or", "please", "show", "tell", "the", "to", "want", "we", "what",
        "where", "which", "with", "you",
    }
)


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


def _token_fuzzy_similarity(query_tok: str, candidate_tokens: tuple[str, ...]) -> float:
    if not query_tok or not candidate_tokens:
        return 0.0
    if query_tok in candidate_tokens:
        return 1.0
    best = 0.0
    for c_tok in candidate_tokens:
        if len(query_tok) >= 4 and (c_tok.startswith(query_tok) or query_tok.startswith(c_tok)):
            best = max(best, 0.88)
            continue
        if abs(len(query_tok) - len(c_tok)) > 3:
            continue
        ratio = SequenceMatcher(None, query_tok, c_tok).ratio()
        if ratio >= 0.72 and ratio > best:
            best = ratio
    return best


def _score_section(query_norm: str, query_tokens: list[str], section: GuideSection) -> float:
    if not query_norm:
        return 0.0

    # 1. Exact or near-exact synonym / title phrase match
    best_phrase = 0.0
    for phrase in (section.title, *section.synonyms):
        p_norm = _normalize_text(phrase)
        if not p_norm:
            continue
        if p_norm == query_norm:
            best_phrase = 1.0
            break
        if p_norm in query_norm or query_norm in p_norm:
            best_phrase = max(best_phrase, 0.90)
        else:
            sim = SequenceMatcher(None, query_norm, p_norm).ratio()
            if sim >= 0.62:
                best_phrase = max(best_phrase, sim * 0.92)

    # 2. Token-level fuzzy coverage against title + synonyms + section body
    token_score = 0.0
    if query_tokens:
        title_syn_tokens = tuple(dict.fromkeys(_tokenize(" ".join([section.title, *section.synonyms]))))
        syn_hits = sum(_token_fuzzy_similarity(tok, title_syn_tokens) for tok in query_tokens)
        body_hits = sum(_token_fuzzy_similarity(tok, section.search_tokens) for tok in query_tokens)
        token_score = max(
            (syn_hits / len(query_tokens)) * 0.95,
            (body_hits / len(query_tokens)) * 0.82,
        )

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

    scored: list[GuideSearchMatch] = []
    for section in loaded.sections:
        if not is_section_authorized(section, scope):
            continue
        if page_id and section.page_id != page_id:
            continue
        score = _score_section(query_norm, query_tokens, section)
        if score < min_score:
            continue
        nav_target = resolve_guide_navigation_target(section.page_id, scope, session_state)
        scored.append(GuideSearchMatch(section=section, score=score, navigation_target=nav_target))

    scored.sort(key=lambda item: (-item.score, item.section.id))
    return scored[: max(1, min(max_results, 3))]


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

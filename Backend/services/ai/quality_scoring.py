"""Free, deterministic per-answer quality scoring (quality loop, stage 1).

Pure Python, no model calls, no database access. Scores one answer against the evidence
digest it was built from and returns a small JSON-safe dict stored with the trace.

Behind ``PMS_AI_QUALITY_LOOP_ENABLED`` (default off). English only.
"""
from __future__ import annotations

import os
import re
from typing import Any

QUALITY_SCORE_VERSION = "v1"
LOW_SCORE_THRESHOLD = 80

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)
_MONTH_RE = re.compile(r"\b(" + "|".join(_MONTHS) + r")\b", re.I)
_PCT_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:\.\d+)?)\s*(?:%|pp\b|pts?\b|points?\b)", re.I)

# flag -> points removed from 100
PENALTIES = {
    "empty_answer": 100,
    "no_evidence": 35,
    "ungrounded_number": 25,
    "ranking_lead_mismatch": 40,
    "period_mismatch": 30,
    "guardrail_triggered": 10,
    "compound_part_missing": 20,
}


def quality_loop_enabled() -> bool:
    return os.getenv("PMS_AI_QUALITY_LOOP_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def _walk_numbers(node: Any, out: set[float], depth: int = 0) -> None:
    if depth > 8:
        return
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        out.add(round(float(node), 1))
        out.add(round(float(node) * 100.0, 1))  # ratios stored as 0..1
        return
    if isinstance(node, str):
        for m in re.finditer(r"-?\d+(?:\.\d+)?", node):
            try:
                out.add(round(float(m.group(0)), 1))
            except ValueError:
                pass
        return
    if isinstance(node, dict):
        for v in node.values():
            _walk_numbers(v, out, depth + 1)
    elif isinstance(node, (list, tuple)):
        for v in node:
            _walk_numbers(v, out, depth + 1)


def _ranking_rows(digest: Any) -> tuple[list[dict[str, Any]], str | None]:
    """First query_rankings block in the digest: (rows, sort_order)."""
    stack = [digest]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            qr = cur.get("query_rankings")
            if isinstance(qr, dict) and isinstance(qr.get("rows"), list):
                rows = [r for r in qr["rows"] if isinstance(r, dict) and r.get("name")]
                return rows, qr.get("sort_order")
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return [], None


def score_answer(
    *,
    prompt: str,
    headline: str,
    bullets: list[str] | None,
    outcome: str,
    tool_digest: dict[str, Any] | None,
    non_empty_evidence: bool,
    guardrail_triggered: bool = False,
) -> dict[str, Any]:
    """Return ``{"version", "score", "flags", "low"}`` for one answer. Never raises."""
    try:
        return _score(prompt, headline, bullets or [], outcome, tool_digest or {}, non_empty_evidence, guardrail_triggered)
    except Exception:  # noqa: BLE001 - scoring must never affect a chat turn
        return {"version": QUALITY_SCORE_VERSION, "score": None, "flags": ["scoring_error"], "low": False}


def _score(prompt, headline, bullets, outcome, digest, non_empty_evidence, guardrail_triggered):
    flags: list[str] = []
    if outcome != "answer":
        # Clarifications, refusals and help are not graded for grounding.
        return {"version": QUALITY_SCORE_VERSION, "score": None, "flags": [f"outcome:{outcome}"], "low": False}
    text = " ".join([headline or "", *bullets])
    if not (headline or "").strip():
        flags.append("empty_answer")
    if not non_empty_evidence:
        flags.append("no_evidence")
    if guardrail_triggered:
        flags.append("guardrail_triggered")

    # Grounding: every percent-like figure in the answer must exist in the evidence digest.
    allowed: set[float] = set()
    _walk_numbers(digest, allowed)
    if allowed:
        for m in _PCT_RE.finditer(text):
            val = round(float(m.group(1)), 1)
            if val not in allowed and round(val) not in {round(a) for a in allowed if abs(a) < 1000}:
                flags.append("ungrounded_number")
                break

    # Ranking: the answer must lead with the first ranked row.
    rows, _sort = _ranking_rows(digest)
    if len(rows) >= 2:
        first = str(rows[0]["name"]).casefold()
        others = [str(r["name"]).casefold() for r in rows[1:4]]
        head = (headline or "").casefold()
        pos_first = head.find(first) if first in head else -1
        pos_other = min((head.find(o) for o in others if o and o in head), default=-1)
        if pos_first == -1 and pos_other != -1 or (pos_first != -1 and pos_other != -1 and pos_other < pos_first):
            flags.append("ranking_lead_mismatch")

    # Period: a month named in the question must not be contradicted by the answer.
    asked = {m.lower() for m in _MONTH_RE.findall(prompt or "")}
    said = {m.lower() for m in _MONTH_RE.findall(text)}
    if asked and said and not (asked & said):
        flags.append("period_mismatch")

    # Compound questions: "X and also Y" should not be answered with a single short line.
    if re.search(r"\b(?:also|and\s+then|as\s+well\s+as)\b", prompt or "", re.I) and len(bullets) == 0 and len(text) < 120:
        flags.append("compound_part_missing")

    score = max(0, 100 - sum(PENALTIES.get(f, 0) for f in dict.fromkeys(flags)))
    return {
        "version": QUALITY_SCORE_VERSION,
        "score": score,
        "flags": list(dict.fromkeys(flags)),
        "low": score < LOW_SCORE_THRESHOLD,
    }

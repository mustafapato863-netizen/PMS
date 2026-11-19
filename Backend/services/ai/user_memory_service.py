"""User Memory Service for AI assistant personalization.

Loads, updates, and prunes per-user memory stored in ai_user_memory table.
Reads are strictly read-only (no commits inside load_memory) so they are safe
inside ReadOnlySessionGuard. Writes happen post-turn in a dedicated commit.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.models import AiUserMemory
from services.ai.security_hardening import fence_untrusted_evidence

_PREF_BRIEF_RE = re.compile(r"\b(keep it brief|be brief|short summary|concise|tl;dr|bullet points only)\b", re.I)
_PREF_DETAILED_RE = re.compile(r"\b(more detail|detailed breakdown|full breakdown|in depth|deep dive)\b", re.I)
_PREF_FORMAL_RE = re.compile(r"\b(formal tone|executive style|executive summary)\b", re.I)
_PREF_CASUAL_RE = re.compile(r"\b(casual tone|friendly tone|simple words)\b", re.I)
_GOAL_RE = re.compile(r"\b(?:my goal is|i want to reach|target(?:ing)? grade)\s+([^\n.;]{3,90})", re.I)


def _coerce_user_uuid(user_id: str | uuid.UUID | None) -> uuid.UUID | str | None:
    if isinstance(user_id, uuid.UUID):
        return user_id
    raw = str(user_id or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError, AttributeError):
        return raw


class UserMemoryService:
    """Service for reading and writing governed per-user memory."""

    MAX_INTERACTION_SUMMARY_CHARS = 500
    MAX_FREQUENT_ITEMS = 10
    MAX_MEMORY_XML_CHARS = 1200  # ~300 tokens ceiling
    DECAY_DAYS = 30

    def __init__(self, db: Session) -> None:
        self.db = db

    def load_memory(self, user_id: str | uuid.UUID) -> dict[str, Any] | None:
        """Load user memory (strictly read-only — never commits)."""
        uid = _coerce_user_uuid(user_id)
        if uid is None:
            return None
        try:
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
            if row is None:
                return None
            return {
                "preferences": dict(row.preferences or {}),
                "query_patterns": dict(row.query_patterns or {}),
                "interaction_summary": str(row.interaction_summary or ""),
                "feedback_signals": dict(row.feedback_signals or {}),
            }
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def save_memory(self, user_id: str | uuid.UUID, updates: dict[str, Any]) -> None:
        """Upsert user memory with the given updates (merged into existing)."""
        uid = _coerce_user_uuid(user_id)
        if uid is None:
            return
        try:
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
            if row is None:
                row = AiUserMemory(user_id=uid)
                self.db.add(row)

            if "preferences" in updates and isinstance(updates["preferences"], dict):
                existing = dict(row.preferences or {})
                existing.update(updates["preferences"])
                row.preferences = existing

            if "query_patterns" in updates and isinstance(updates["query_patterns"], dict):
                existing = dict(row.query_patterns or {})
                existing.update(updates["query_patterns"])
                row.query_patterns = existing

            if "interaction_summary" in updates:
                summary = str(updates["interaction_summary"] or "")
                if len(summary) > self.MAX_INTERACTION_SUMMARY_CHARS:
                    summary = summary[: self.MAX_INTERACTION_SUMMARY_CHARS]
                row.interaction_summary = summary

            if "feedback_signals" in updates and isinstance(updates["feedback_signals"], dict):
                existing = dict(row.feedback_signals or {})
                existing.update(updates["feedback_signals"])
                row.feedback_signals = existing

            row.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

    def get_memory_text(self, memory: dict[str, Any] | None) -> str:
        """Convert user memory to a compact, XML-safe text block for prompt injection."""
        if not memory:
            return ""
        lines: list[str] = []
        prefs = memory.get("preferences", {}) or {}
        if prefs:
            if prefs.get("detail_level"):
                lines.append(f"Preferred detail level: {prefs['detail_level']}")
            if prefs.get("communication_style"):
                lines.append(f"Communication style: {prefs['communication_style']}")
            if prefs.get("preferred_metrics"):
                lines.append(f"Preferred metrics: {', '.join(str(m) for m in prefs['preferred_metrics'][:5])}")
            if prefs.get("preferred_teams"):
                lines.append(f"Preferred teams: {', '.join(str(t) for t in prefs['preferred_teams'][:5])}")
            if prefs.get("goal"):
                lines.append(f"Active goal: {prefs['goal']}")

        patterns = memory.get("query_patterns", {}) or {}
        if patterns.get("frequent_topics"):
            lines.append(f"Frequent topics: {', '.join(str(t) for t in patterns['frequent_topics'][:5])}")
        if patterns.get("frequent_teams"):
            top_teams = sorted(patterns["frequent_teams"].items(), key=lambda x: -x[1])[:5]
            lines.append(f"Frequently asked teams: {', '.join(str(t[0]) for t in top_teams)}")
        if patterns.get("frequent_kpis"):
            top_kpis = sorted(patterns["frequent_kpis"].items(), key=lambda x: -x[1])[:5]
            lines.append(f"Frequently asked KPIs: {', '.join(str(k[0]) for k in top_kpis)}")

        summary = memory.get("interaction_summary", "")
        if summary:
            lines.append(f"Recent interaction summary: {summary[:300]}")

        feedback = memory.get("feedback_signals", {}) or {}
        if feedback.get("positive_count", 0) > 0 or feedback.get("negative_count", 0) > 0:
            lines.append(
                f"Feedback: {feedback.get('positive_count', 0)} positive, "
                f"{feedback.get('negative_count', 0)} negative"
            )

        if not lines:
            return ""
        raw = "\n".join(lines)[: self.MAX_MEMORY_XML_CHARS]
        # Escape XML tags to prevent memory-based prompt breakout (Blocker EGM-DC-8)
        escaped = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "&#96;")
        return f"<VERIFIED_USER_MEMORY>\n[User Memory]\n{escaped}\n</VERIFIED_USER_MEMORY>"

    def extract_and_persist_turn_signals(
        self,
        user_id: str | uuid.UUID,
        prompt: str,
        *,
        topic: str | None = None,
        team: str | None = None,
        kpi: str | None = None,
    ) -> bool:
        """Deterministic zero-LLM post-turn extraction and atomic persistence.

        Must be called OUTSIDE ReadOnlySessionGuard (e.g., right after trace logging).
        """
        uid = _coerce_user_uuid(user_id)
        if uid is None:
            return False
        text = str(prompt or "").strip()
        if not text:
            return False

        memory = self.load_memory(uid) or {}
        updates: dict[str, Any] = {}

        # 1. Extract explicit preference / goal cues deterministically
        prefs = dict(memory.get("preferences") or {})
        prefs_changed = False
        if _PREF_BRIEF_RE.search(text):
            prefs["detail_level"] = "brief"
            prefs_changed = True
        elif _PREF_DETAILED_RE.search(text):
            prefs["detail_level"] = "detailed"
            prefs_changed = True

        if _PREF_FORMAL_RE.search(text):
            prefs["communication_style"] = "formal"
            prefs_changed = True
        elif _PREF_CASUAL_RE.search(text):
            prefs["communication_style"] = "casual"
            prefs_changed = True

        goal_match = _GOAL_RE.search(text)
        if goal_match:
            prefs["goal"] = goal_match.group(1).strip()[:120]
            prefs_changed = True

        if prefs_changed:
            updates["preferences"] = prefs

        # 2. Update bounded query patterns
        patterns = dict(memory.get("query_patterns") or {})
        topics = list(patterns.get("frequent_topics") or [])
        teams = dict(patterns.get("frequent_teams") or {})
        kpis = dict(patterns.get("frequent_kpis") or {})

        if topic and topic not in topics:
            topics.append(str(topic)[:50])
            topics = topics[-self.MAX_FREQUENT_ITEMS :]
        if team:
            t_key = str(team)[:60]
            teams[t_key] = int(teams.get(t_key, 0)) + 1
            if len(teams) > self.MAX_FREQUENT_ITEMS:
                teams = dict(sorted(teams.items(), key=lambda kv: -kv[1])[: self.MAX_FREQUENT_ITEMS])
        if kpi:
            k_key = str(kpi)[:60]
            kpis[k_key] = int(kpis.get(k_key, 0)) + 1
            if len(kpis) > self.MAX_FREQUENT_ITEMS:
                kpis = dict(sorted(kpis.items(), key=lambda kv: -kv[1])[: self.MAX_FREQUENT_ITEMS])

        patterns["frequent_topics"] = topics
        patterns["frequent_teams"] = teams
        patterns["frequent_kpis"] = kpis
        patterns["query_count"] = int(patterns.get("query_count", 0)) + 1
        updates["query_patterns"] = patterns

        self.save_memory(uid, updates)
        return True

    def record_query(self, user_id: str | uuid.UUID, topic: str | None = None, team: str | None = None, kpi: str | None = None) -> None:
        """Record a query pattern for future personalization."""
        try:
            uid = _coerce_user_uuid(user_id)
            if uid is None:
                return
            memory = self.load_memory(uid) or {}
            patterns = dict(memory.get("query_patterns") or {})
            patterns.setdefault("frequent_topics", [])
            patterns.setdefault("frequent_teams", {})
            patterns.setdefault("frequent_kpis", {})
            patterns.setdefault("query_count", 0)

            if topic and topic not in patterns["frequent_topics"]:
                patterns["frequent_topics"].append(topic)
                patterns["frequent_topics"] = patterns["frequent_topics"][-self.MAX_FREQUENT_ITEMS :]

            if team:
                patterns["frequent_teams"][team] = patterns["frequent_teams"].get(team, 0) + 1

            if kpi:
                patterns["frequent_kpis"][kpi] = patterns["frequent_kpis"].get(kpi, 0) + 1

            patterns["query_count"] = patterns.get("query_count", 0) + 1

            self.save_memory(uid, {"query_patterns": patterns})
        except Exception:
            pass

    def record_feedback(self, user_id: str | uuid.UUID, positive: bool, correction: str | None = None) -> None:
        """Record feedback signal."""
        try:
            uid = _coerce_user_uuid(user_id)
            if uid is None:
                return
            memory = self.load_memory(uid) or {}
            feedback = dict(memory.get("feedback_signals") or {})
            if positive:
                feedback["positive_count"] = feedback.get("positive_count", 0) + 1
            else:
                feedback["negative_count"] = feedback.get("negative_count", 0) + 1
            if correction:
                corrections = list(feedback.get("corrections") or [])
                corrections.append(correction[:160])
                feedback["corrections"] = corrections[-self.MAX_FREQUENT_ITEMS :]
            self.save_memory(uid, {"feedback_signals": feedback})
        except Exception:
            pass

    def decay_memory(self, user_id: str | uuid.UUID) -> None:
        """Prune old memory entries. Called periodically."""
        uid = _coerce_user_uuid(user_id)
        if uid is None:
            return
        try:
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
            if row is None:
                return
            if row.last_accessed_at:
                last = row.last_accessed_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last).days > self.DECAY_DAYS:
                    row.query_patterns = {}
                    row.interaction_summary = None
                    row.last_accessed_at = datetime.now(timezone.utc)
                    self.db.commit()
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass

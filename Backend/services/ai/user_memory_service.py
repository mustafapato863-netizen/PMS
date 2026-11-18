"""User Memory Service for AI assistant personalization.

Loads, updates, and prunes per-user memory stored in ai_user_memory table.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from models.models import AiUserMemory, User


class UserMemoryService:
    """Service for reading and writing user memory."""

    MAX_INTERACTION_SUMMARY_CHARS = 500
    MAX_FREQUENT_ITEMS = 10
    DECAY_DAYS = 30

    def __init__(self, db: Session) -> None:
        self.db = db

    def load_memory(self, user_id: str) -> dict[str, Any] | None:
        """Load user memory. Returns None if no memory exists."""
        try:
            uid = user_id
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == uid).first()
            if row is None:
                return None
            # Update last_accessed_at
            row.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()
            return {
                "preferences": row.preferences or {},
                "query_patterns": row.query_patterns or {},
                "interaction_summary": row.interaction_summary or "",
                "feedback_signals": row.feedback_signals or {},
            }
        except Exception:
            self.db.rollback()
            return None

    def save_memory(self, user_id: str, updates: dict[str, Any]) -> None:
        """Upsert user memory with the given updates (merged into existing)."""
        try:
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == user_id).first()
            if row is None:
                row = AiUserMemory(user_id=user_id)
                self.db.add(row)

            # Merge preferences
            if "preferences" in updates:
                existing = row.preferences or {}
                existing.update(updates["preferences"])
                row.preferences = existing

            # Merge query_patterns
            if "query_patterns" in updates:
                existing = row.query_patterns or {}
                existing.update(updates["query_patterns"])
                row.query_patterns = existing

            # Update interaction_summary (truncate)
            if "interaction_summary" in updates:
                summary = str(updates["interaction_summary"] or "")
                if len(summary) > self.MAX_INTERACTION_SUMMARY_CHARS:
                    summary = summary[: self.MAX_INTERACTION_SUMMARY_CHARS]
                row.interaction_summary = summary

            # Merge feedback_signals
            if "feedback_signals" in updates:
                existing = row.feedback_signals or {}
                existing.update(updates["feedback_signals"])
                row.feedback_signals = existing

            row.last_accessed_at = datetime.now(timezone.utc)
            self.db.commit()
        except Exception:
            self.db.rollback()

    def get_memory_text(self, memory: dict[str, Any] | None) -> str:
        """Convert user memory to a human-readable text for prompt injection."""
        if not memory:
            return ""
        lines = []
        prefs = memory.get("preferences", {})
        if prefs:
            if prefs.get("detail_level"):
                lines.append(f"Preferred detail level: {prefs['detail_level']}")
            if prefs.get("communication_style"):
                lines.append(f"Communication style: {prefs['communication_style']}")
            if prefs.get("preferred_metrics"):
                lines.append(f"Preferred metrics: {', '.join(prefs['preferred_metrics'])}")
            if prefs.get("preferred_teams"):
                lines.append(f"Preferred teams: {', '.join(prefs['preferred_teams'])}")

        patterns = memory.get("query_patterns", {})
        if patterns.get("frequent_topics"):
            lines.append(f"Frequent topics: {', '.join(patterns['frequent_topics'])}")
        if patterns.get("frequent_teams"):
            top_teams = sorted(patterns["frequent_teams"].items(), key=lambda x: -x[1])[:5]
            lines.append(f"Frequently asked teams: {', '.join(t[0] for t in top_teams)}")
        if patterns.get("frequent_kpis"):
            top_kpis = sorted(patterns["frequent_kpis"].items(), key=lambda x: -x[1])[:5]
            lines.append(f"Frequently asked KPIs: {', '.join(k[0] for k in top_kpis)}")

        summary = memory.get("interaction_summary", "")
        if summary:
            lines.append(f"Recent interaction summary: {summary}")

        feedback = memory.get("feedback_signals", {})
        if feedback.get("positive_count", 0) > 0 or feedback.get("negative_count", 0) > 0:
            lines.append(
                f"Feedback: {feedback.get('positive_count', 0)} positive, "
                f"{feedback.get('negative_count', 0)} negative"
            )

        if not lines:
            return ""
        return "[User Memory]\n" + "\n".join(lines)

    def record_query(self, user_id: str, topic: str | None = None, team: str | None = None, kpi: str | None = None) -> None:
        """Record a query pattern for future personalization."""
        try:
            memory = self.load_memory(user_id) or {}
            patterns = memory.get("query_patterns", {})
            patterns.setdefault("frequent_topics", [])
            patterns.setdefault("frequent_teams", {})
            patterns.setdefault("frequent_kpis", {})
            patterns.setdefault("query_count", 0)

            if topic and topic not in patterns["frequent_topics"]:
                patterns["frequent_topics"].append(topic)
                patterns["frequent_topics"] = patterns["frequent_topics"][-self.MAX_FREQUENT_ITEMS:]

            if team:
                patterns["frequent_teams"][team] = patterns["frequent_teams"].get(team, 0) + 1

            if kpi:
                patterns["frequent_kpis"][kpi] = patterns["frequent_kpis"].get(kpi, 0) + 1

            patterns["query_count"] = patterns.get("query_count", 0) + 1

            self.save_memory(user_id, {"query_patterns": patterns})
        except Exception:
            pass

    def record_feedback(self, user_id: str, positive: bool, correction: str | None = None) -> None:
        """Record feedback signal."""
        try:
            memory = self.load_memory(user_id) or {}
            feedback = memory.get("feedback_signals", {})
            if positive:
                feedback["positive_count"] = feedback.get("positive_count", 0) + 1
            else:
                feedback["negative_count"] = feedback.get("negative_count", 0) + 1
            if correction:
                corrections = feedback.get("corrections", [])
                corrections.append(correction)
                feedback["corrections"] = corrections[-self.MAX_FREQUENT_ITEMS:]
            self.save_memory(user_id, {"feedback_signals": feedback})
        except Exception:
            pass

    def decay_memory(self, user_id: str) -> None:
        """Prune old memory entries. Called periodically."""
        try:
            row = self.db.query(AiUserMemory).filter(AiUserMemory.user_id == user_id).first()
            if row is None:
                return
            # Check if last accessed more than DECAY_DAYS ago
            if row.last_accessed_at and (datetime.now(timezone.utc) - row.last_accessed_at).days > self.DECAY_DAYS:
                # Reset query patterns but keep preferences
                row.query_patterns = {}
                row.interaction_summary = None
                row.last_accessed_at = datetime.now(timezone.utc)
                self.db.commit()
        except Exception:
            self.db.rollback()

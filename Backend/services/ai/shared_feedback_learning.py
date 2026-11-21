"""Aggregate votes on verified answer families into reusable planner guidance."""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.ai_schemas import AiSharedLearningFamily
from models.models import AiInteractionTrace, User


GUIDANCE = {
    "team_scores": (
        "Team score comparisons",
        "For a score comparison between named teams, read the same period and scope for both teams. Report both scores, the percentage-point difference, and any tie.",
    ),
    "period_scores": (
        "Overall score across months",
        "For overall score changes, read the overall PMS score for each requested period. Show both months and scores, and express the change in percentage points.",
    ),
    "ranking_positions": (
        "Employee rankings with positions",
        "When a person ranking also requests positions, include the verified position for each returned person. Carry the verified subject forward only for a single unambiguous person.",
    ),
}
MIN_HELPFUL_USERS = 3
VOTE_WINDOW_DAYS = 90
MAX_VOTES = 500


def shared_learning_families(db: Session) -> list[AiSharedLearningFamily]:
    enabled = os.getenv("PMS_AI_SHARED_VERIFIED_FEEDBACK_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")
    counts: Counter[tuple[str, str]] = Counter()
    if enabled:
        trace = AiInteractionTrace
        family = trace.structured_response["verified_answer_family"].as_string()
        governance = trace.structured_response["feedback_governance"]
        submitted = governance["submitted_at"].as_string()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=VOTE_WINDOW_DAYS)).isoformat()
        latest_per_account = (
            db.query(
                trace.user_id,
                trace.feedback_rating,
                family.label("family"),
                submitted.label("submitted_at"),
                func.row_number().over(
                    partition_by=(family, trace.user_id),
                    order_by=(submitted.desc(), trace.id.desc()),
                ).label("vote_order"),
            )
            .filter(
                trace.non_empty_evidence.is_(True),
                trace.guardrail_triggered.is_(False),
                trace.structured_response["outcome"].as_string() == "answer",
                trace.feedback_rating.in_(("up", "down")),
                family.in_(tuple(GUIDANCE)),
                governance["surface"].as_string() == "workspace_chat",
                governance["pii_quarantined"].as_boolean().is_(False),
                submitted >= cutoff,
            )
            .subquery()
        )
        votes = latest_per_account.c
        rows = (
            db.query(votes.user_id, votes.feedback_rating, votes.family)
            .filter(votes.vote_order == 1)
            .order_by(votes.submitted_at.desc())
            .limit(MAX_VOTES)
            .all()
        )
        latest_votes: dict[tuple[str, UUID], str] = {}
        for user_id, rating, answer_family in rows:
            try:
                account_id = UUID(str(user_id))
            except ValueError:
                continue
            latest_votes.setdefault((answer_family, account_id), rating)
        account_ids = {account_id for _, account_id in latest_votes}
        if account_ids:
            active_accounts = {
                account_id for (account_id,) in
                db.query(User.id).filter(User.id.in_(account_ids), User.is_active.is_(True)).all()
            }
            counts.update(
                (answer_family, rating)
                for (answer_family, account_id), rating in latest_votes.items() if account_id in active_accounts
            )
    return [
        AiSharedLearningFamily(
            family=family,
            label=label,
            helpful_users=counts[family, "up"],
            unhelpful_users=counts[family, "down"],
            active=counts[family, "up"] >= MIN_HELPFUL_USERS and counts[family, "down"] == 0,
        )
        for family, (label, _) in GUIDANCE.items()
    ]


def shared_planner_guidance(db: Session) -> str:
    lines = [GUIDANCE[item.family][1] for item in shared_learning_families(db) if item.active]
    return (
        "\nVerified guidance from shared user feedback (apply only to matching requests):\n"
        + "\n".join(f"- {line}" for line in lines)
        if lines else ""
    )

"""Evaluate English Call Center answers against isolated synthetic records."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

# Prevent the evaluation from using the configured application database or provider.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["PMS_AI_GEMINI_ROUTING_ENABLED"] = "false"
os.environ["PMS_AI_CLASSIFIER_MODE"] = "off"
os.environ["PMS_AI_ROUTER_MODE"] = "hybrid"
os.environ["PMS_AI_PILOT_SCOPES"] = "Call Center,Inbound,Outbound,Support Positions"
os.environ["PMS_AI_BRIEF_DEFAULT_ENABLED"] = "true"

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from pytest import MonkeyPatch

from models.ai_schemas import AiChatRequest, SessionFilterContext
from services.ai.catalog import ai_evidence_cache
from services.ai.orchestrator import PmsAiOrchestrator


def main() -> int:
    helpers = runpy.run_path(str(BACKEND_DIR / "tests" / "test_ai_workspace.py"))
    make_record = helpers["_make_call_center_record"]
    records = []
    for employee_id, name, team, position, month, score in [
        ("EMP001", "Alex Test", "Call Center", "Quality Assurance", "September", 60),
        ("EMP001", "Alex Test", "Call Center", "Quality Assurance", "August", 50),
        ("EMP002", "Blair Test", "Call Center", "Trainer", "September", 88),
        ("EMP003", "Casey Test", "Inbound", "Agent", "September", 92),
        ("EMP004", "Dana Test", "Inbound", "Agent", "September", 65),
        ("EMP003", "Casey Test", "Inbound", "Agent", "August", 80),
        ("EMP004", "Dana Test", "Inbound", "Agent", "August", 78),
        ("EMP005", "Evan Test", "Outbound", "Agent", "September", 75),
    ]:
        record = make_record(employee_id, name, team, score, 10, 30, 40, 60, month=month)
        record.position = position
        records.append(record)

    # Each expected fragment describes the answer, not merely the selected intent.
    cases = [
        ("hi", "answer", ("hi",)),
        ("Hello!", "answer", ("hi",)),
        ("Good morning", "answer", ("hi",)),
        ("Hello there", "answer", ("hi",)),
        ("Who is the lowest performer in the support team and their position in September 2026?", "answer", ("alex test", "quality assurance")),
        ("Who scored lowest in support positions in September 2026?", "answer", ("alex test",)),
        ("Which support employee had the lowest score in September 2026?", "answer", ("alex test",)),
        ("What is Alex Test's position?", "answer", ("quality assurance",)),
        ("Who is the best inbound agent in September 2026?", "answer", ("casey test",)),
        ("Who scored highest in inbound for September 2026?", "answer", ("casey test",)),
        ("Which inbound agent led performance in September 2026?", "answer", ("casey test",)),
        ("Who was the top inbound performer in August 2026?", "answer", ("casey test", "80")),
        ("Who is the worst inbound agent in September 2026?", "answer", ("dana test",)),
        ("Who has the lowest inbound score in September 2026?", "answer", ("dana test",)),
        ("What is the Inbound attendance rate in September 2026?", "answer", ("attendance", "55.6%")),
        ("Show Inbound attendance for September 2026.", "answer", ("attendance", "55.6%")),
        ("What is the booking trend for Inbound?", "answer", ("booking", "august", "september")),
        ("Show the Inbound bookings trend from August to September 2026.", "answer", ("booking", "august", "september")),
        ("Which branch had the most bookings in September 2026?", "answer", ("dubai",)),
        ("Did Dubai or Sharjah have more bookings in September 2026?", "answer", ("dubai",)),
        ("Is Casey Test a new joiner in inbound?", "clarification", ()),
        ("Did Casey Test join inbound recently?", "clarification", ()),
        ("Compare Inbound in August and September 2026.", "answer", ("august", "september")),
        ("Show attendance.", "clarification", ()),
        ("What is attendance?", "clarification", ()),
    ]

    db = helpers["_build_in_memory_db"]()
    scope = {"role": "Admin", "user_id": "evaluation", "has_unrestricted_team_access": True}
    results = []
    try:
        with MonkeyPatch.context() as patcher:
            helpers["_patch_records"](patcher, records)
            ai_evidence_cache.clear()
            for question, expected_outcome, expected_fragments in cases:
                try:
                    response = PmsAiOrchestrator(db, scope).run_chat_turn(
                        AiChatRequest(
                            prompt=question,
                            session_state=SessionFilterContext(
                                function="Call Center", month="September", year=2026
                            ),
                            provider_override="deterministic",
                        )
                    )
                    visible = " ".join([response.headline, *response.narrative_bullets]).casefold()
                    passed = response.outcome == expected_outcome and all(
                        fragment in visible for fragment in expected_fragments
                    )
                    results.append({
                        "question": question,
                        "passed": passed,
                        "outcome": response.outcome,
                        "headline": response.headline,
                        "expected_fragments": expected_fragments,
                    })
                except Exception as exc:
                    results.append({
                        "question": question,
                        "passed": False,
                        "error": type(exc).__name__,
                    })

            # Follow-up uses the actual context returned by the preceding turn.
            try:
                first = PmsAiOrchestrator(db, scope).run_chat_turn(
                    AiChatRequest(
                        prompt="Who is the best inbound agent in September 2026?",
                        session_state=SessionFilterContext(
                            function="Call Center", month="September", year=2026
                        ),
                        provider_override="deterministic",
                    )
                )
                follow_up = PmsAiOrchestrator(db, scope).run_chat_turn(
                    AiChatRequest(
                        prompt="What about August?",
                        session_state=first.resolved_session_state,
                        provider_override="deterministic",
                    )
                )
                visible = " ".join([follow_up.headline, *follow_up.narrative_bullets]).casefold()
                results.append({
                    "question": "Who is the best inbound agent in September 2026? → What about August?",
                    "passed": (
                        follow_up.outcome == "answer"
                        and "august" in visible
                        and "casey test" in visible
                        and "80.0%" in visible
                    ),
                    "outcome": follow_up.outcome,
                    "headline": follow_up.headline,
                    "expected_fragments": ("casey test", "august", "80.0%"),
                })
            except Exception as exc:
                results.append({
                    "question": "Who is the best inbound agent in September 2026? → What about August?",
                    "passed": False,
                    "error": type(exc).__name__,
                })
    finally:
        db.close()

    passed = sum(result["passed"] for result in results)
    print(json.dumps({"passed": passed, "total": len(results), "cases": results}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

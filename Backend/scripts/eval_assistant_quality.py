"""Reproducible English quality eval for the PMS AI assistant.

Runs the real orchestrator on a synthetic dataset (no network, no providers) and scores the
first answer for each case in tests/fixtures/ai_quality_eval_v1.json.

    python scripts/eval_assistant_quality.py            # prints pass rate per category and failures
    python scripts/eval_assistant_quality.py --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("PMS_AI_MODEL_LED_PILOT_ENABLED", "false")
os.environ.setdefault("PMS_AI_SYNTHESIS_ENABLED", "false")
os.environ.setdefault("PMS_AI_INTENT_ENABLED", "false")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from config.database import Base  # noqa: E402
from models.ai_schemas import AiChatMessage, AiChatRequest, SessionFilterContext  # noqa: E402
from scripts.run_phase6_independent_eval import _mk_rec, build_synthetic_holdout_records  # noqa: E402
from services.ai.catalog import ai_evidence_cache  # noqa: E402
from services.ai.orchestrator import PmsAiOrchestrator  # noqa: E402
from services.dashboard_record_service import DashboardRecordService  # noqa: E402
from services.database_record_source import DatabaseRecordSource  # noqa: E402

FIXTURE = BACKEND_DIR / "tests" / "fixtures" / "ai_quality_eval_v1.json"


def build_records():
    records = build_synthetic_holdout_records()
    # Outbound booking rate fell from August to September (gives a real KPI decline to find).
    records += [
        _mk_rec("H-OUT-01", "Dina Soliman", "Outbound", "EGY", 90.0, month="August", booking_rate=33.0),
        _mk_rec("H-OUT-02", "Omar Haddad", "Outbound", "EGY", 90.5, month="August", booking_rate=32.0),
    ]
    return records


def text_of(resp) -> str:
    return "\n".join([resp.headline or "", *(resp.narrative_bullets or []), *(resp.detail_bullets or [])])


def score(case, resp) -> list[str]:
    failures = []
    text = text_of(resp)
    low = text.casefold()
    allowed = case.get("expected_outcomes") or ["answer"]
    if resp.outcome not in allowed:
        failures.append(f"outcome {resp.outcome!r} not in {allowed}")
    for group in case.get("all_of", []):
        if not any(tok.casefold() in low for tok in group):
            failures.append(f"missing any of {group}")
    for tok in case.get("none_of", []):
        if tok.casefold() in low:
            failures.append(f"forbidden {tok!r}")
    return failures


def run(selected: set[str] | None = None) -> list[dict]:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    records = build_records()
    DatabaseRecordSource.get_all = lambda *a, **kw: list(records)
    DashboardRecordService.list_records = lambda *a, **kw: list(records)
    DashboardRecordService.list_analysis_records = lambda *a, **kw: list(records)
    DashboardRecordService.list_record_index = lambda *a, **kw: None
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    results = []
    for case in cases:
        if selected and case["id"] not in selected:
            continue
        ai_evidence_cache.clear()
        orch = PmsAiOrchestrator(db, {"role": "Admin", "user_id": f"q-{case['id']}", "has_unrestricted_team_access": True})
        state, conv, history = SessionFilterContext(), None, []
        turns = [*case.get("setup", []), case["prompt"]]
        resp = None
        try:
            for prompt in turns:
                resp = orch.run_chat_turn(AiChatRequest(
                    conversation_id=conv, prompt=prompt, session_state=state, history=history[-12:],
                    provider_override="deterministic", answer_detail="brief",
                ))
                conv, state = resp.conversation_id, resp.resolved_session_state or state
                history += [AiChatMessage(role="user", content=prompt), AiChatMessage(role="assistant", content=resp.headline)]
            failures = score(case, resp)
            answer = text_of(resp)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failures, answer = [f"error {type(exc).__name__}: {exc}"], ""
        results.append({"id": case["id"], "cat": case["cat"], "prompt": case["prompt"], "passed": not failures, "failures": failures, "answer": answer[:600]})
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("-v", action="store_true")
    args = ap.parse_args()
    results = run(set(args.only) if args.only else None)
    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["cat"]][1] += 1
        by_cat[r["cat"]][0] += r["passed"]
    total = sum(r["passed"] for r in results)
    print(f"PASS {total}/{len(results)}")
    for cat, (p, n) in by_cat.items():
        print(f"  {cat}: {p}/{n}")
    for r in results:
        if not r["passed"]:
            print(f"FAIL {r['id']}: {r['prompt']}\n   {r['failures']}\n   ANSWER: {r['answer'][:300]!r}")
        elif args.v:
            print(f"ok   {r['id']}: {r['answer'][:160]!r}")
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

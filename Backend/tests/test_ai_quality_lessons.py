import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import AiInteractionTrace
from services.ai import quality_lessons as ql


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("PMS_AI_QUALITY_LOOP_ENABLED", "true")
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    ql._cache.update(at=0.0, lessons=[])
    yield s
    s.close()


def _trace(db, judge):
    t = AiInteractionTrace(
        id=uuid.uuid4(), prompt="weakest team in September 2026", sanitized_prompt="weakest team in September 2026",
        session_state={}, tool_calls=[], tool_digest={}, role="Admin",
        structured_response={"outcome": "answer", "judge": judge}, provider_name="x", model_name="y",
        latency_ms=1, non_empty_evidence=True, guardrail_triggered=False,
    )
    db.add(t)
    db.commit()
    return t


FAIL = {"verdict": "fail", "issues": ["wrong_ranking_order"], "correction": {"headline": "Outbound is weakest at 87.0%.", "bullets": []},
        "lesson": {"text": "Lead with the first ranked row.", "status": "pending"}}


def test_pending_lesson_not_used_until_approved(db):
    t = _trace(db, FAIL)
    assert ql.lessons_prompt_block(db) == ""
    assert ql.set_lesson_status(db, str(t.id), "approved")
    assert "Lead with the first ranked row." in ql.lessons_prompt_block(db)
    assert ql.set_lesson_status(db, str(t.id), "rejected")
    assert ql.lessons_prompt_block(db) == ""


def test_regression_case_uses_corrected_figures(db):
    _trace(db, FAIL)
    cases = ql.regression_cases(db)
    assert len(cases) == 1 and cases[0]["all_of"] == [["87.0"]] and cases[0]["cat"] == "regression"


def test_flag_off_returns_nothing(db, monkeypatch):
    t = _trace(db, FAIL)
    ql.set_lesson_status(db, str(t.id), "approved")
    monkeypatch.delenv("PMS_AI_QUALITY_LOOP_ENABLED")
    assert ql.approved_lessons(db) == []


def test_unknown_trace_or_bad_status(db):
    assert ql.set_lesson_status(db, "not-a-uuid", "approved") is False
    with pytest.raises(ValueError):
        ql.set_lesson_status(db, str(uuid.uuid4()), "weird")

import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from config.database import Base
from models.models import AiInteractionTrace
from services.ai import quality_judge as qj

KEYS = [{"slot": "primary", "account": "a1", "token": "t1"}, {"slot": "alternate", "account": "a2", "token": "t2"}]


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("PMS_AI_QUALITY_LOOP_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_QUALITY_SAMPLE_PERCENT", "100")
    monkeypatch.setattr(qj, "_cf_keys", lambda _db: KEYS)
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


def _trace(db, headline="Inbound leads at 92.6%.", rating=None):
    t = AiInteractionTrace(
        id=uuid.uuid4(), prompt="weakest team in September 2026", sanitized_prompt="weakest team in September 2026",
        session_state={}, tool_calls=[], role="Admin",
        tool_digest={"query_rankings": {"rows": [{"name": "Outbound", "score": 87.0}, {"name": "Inbound", "score": 92.6}]}},
        structured_response={"outcome": "answer", "headline": headline, "narrative_bullets": [], "quality": {"low": True, "score": 40}},
        provider_name="x", model_name="y", latency_ms=1, non_empty_evidence=True, guardrail_triggered=False, feedback_rating=rating,
    )
    db.add(t)
    db.commit()
    return t


def _fake(responses, calls):
    def fn(key, model, system, user, max_tokens, timeout):
        calls.append(key["slot"])
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item, 100
    return fn


def test_disabled_by_default(db, monkeypatch):
    monkeypatch.delenv("PMS_AI_QUALITY_LOOP_ENABLED")
    assert qj.run_quality_tick(db)["status"] == "disabled"


def test_fail_verdict_stores_grounded_correction_and_lesson(db, monkeypatch):
    t = _trace(db)
    calls = []
    monkeypatch.setattr(qj, "_chat_cloudflare", _fake([
        json.dumps({"verdict": "fail", "score": 20, "issues": ["wrong_ranking_order"], "notes": "reversed"}),
        json.dumps({"headline": "Outbound is the weakest team at 87.0%.", "bullets": [], "lesson": "Lead with the first ranked row."}),
    ], calls))
    out = qj.run_quality_tick(db)
    assert out["judged"] == 1
    db.refresh(t)
    j = t.structured_response["judge"]
    assert j["verdict"] == "fail" and j["correction"]["headline"].startswith("Outbound")
    assert j["lesson"]["status"] == "pending"


def test_ungrounded_correction_is_rejected(db, monkeypatch):
    t = _trace(db)
    monkeypatch.setattr(qj, "_chat_cloudflare", _fake([
        json.dumps({"verdict": "fail", "issues": ["other"]}),
        json.dumps({"headline": "Outbound is weakest at 61.3%.", "bullets": [], "lesson": "x"}),
    ], []))
    qj.run_quality_tick(db)
    db.refresh(t)
    assert "correction" not in t.structured_response["judge"]
    assert t.structured_response["judge"]["correction_rejected"] == "not_grounded"


def test_fails_over_to_second_key_when_allowance_spent(db, monkeypatch):
    t = _trace(db)
    calls = []
    monkeypatch.setattr(qj, "_chat_cloudflare", _fake([
        qj.AllowanceSpent("3036"), json.dumps({"verdict": "pass", "score": 95, "issues": []}),
    ], calls))
    out = qj.run_quality_tick(db)
    assert calls == ["primary", "alternate"] and out["judged"] == 1
    db.refresh(t)
    assert t.structured_response["judge"]["slot"] == "alternate"


def test_stops_when_both_keys_spent_and_budget_is_per_key(db, monkeypatch):
    _trace(db)
    monkeypatch.setenv("PMS_AI_QUALITY_NEURON_BUDGET_PER_KEY", "10")
    calls = []
    monkeypatch.setattr(qj, "_chat_cloudflare", _fake([json.dumps({"verdict": "pass"})], calls))
    out = qj.run_quality_tick(db)
    assert calls == [] and out["judged"] == 0


def test_daily_cap_and_already_judged_skipped(db, monkeypatch):
    t = _trace(db)
    monkeypatch.setattr(qj, "_chat_cloudflare", _fake([json.dumps({"verdict": "pass"})] * 3, []))
    assert qj.run_quality_tick(db)["judged"] == 1
    assert qj.run_quality_tick(db)["judged"] == 0  # already judged
    used = qj.neurons_used_today(db, datetime.now(timezone.utc))
    assert used.get("primary") == 100


def test_neuron_estimate_matches_published_rates():
    assert qj.estimate_neurons("@cf/openai/gpt-oss-120b", 3000, 500) == 130

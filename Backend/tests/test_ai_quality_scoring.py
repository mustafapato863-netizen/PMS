from services.ai.quality_scoring import quality_loop_enabled, score_answer

DIGEST = {"query_rankings": {"sort_order": "asc", "rows": [
    {"name": "Outbound", "score": 87.0}, {"name": "Inbound", "score": 92.6}]}}


def _s(headline, bullets=None, prompt="weakest team in September 2026", digest=DIGEST, **kw):
    return score_answer(prompt=prompt, headline=headline, bullets=bullets or [], outcome=kw.pop("outcome", "answer"),
                        tool_digest=digest, non_empty_evidence=kw.pop("ev", True), **kw)


def test_good_answer_scores_100():
    r = _s("Outbound is the weakest team in September 2026 at 87.0%.")
    assert r["score"] == 100 and r["flags"] == [] and not r["low"]


def test_ranking_lead_mismatch_flagged():
    r = _s("Inbound leads at 92.6%, ahead of Outbound at 87.0%.")
    assert "ranking_lead_mismatch" in r["flags"] and r["low"]


def test_ungrounded_number_flagged():
    r = _s("Outbound is the weakest team at 61.3%.")
    assert "ungrounded_number" in r["flags"]


def test_period_mismatch_flagged():
    r = _s("Outbound is weakest in March at 87.0%.")
    assert "period_mismatch" in r["flags"]


def test_non_answer_outcomes_not_graded():
    r = _s("Which team?", outcome="clarification")
    assert r["score"] is None and not r["low"]


def test_no_evidence_and_never_raises():
    assert "no_evidence" in _s("Outbound is weakest.", ev=False)["flags"]
    assert score_answer(prompt=None, headline=None, bullets=None, outcome="answer", tool_digest=None,
                        non_empty_evidence=False)["version"] == "v1"


def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PMS_AI_QUALITY_LOOP_ENABLED", raising=False)
    assert quality_loop_enabled() is False
    monkeypatch.setenv("PMS_AI_QUALITY_LOOP_ENABLED", "true")
    assert quality_loop_enabled() is True

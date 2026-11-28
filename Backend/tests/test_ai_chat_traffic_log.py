import logging
from types import SimpleNamespace

from api.routers.ai_workspace import log_ai_chat_traffic


def _payload(**kw):
    plan = SimpleNamespace(intent="ranking", operation_kind_v2="top_n", turn_kind_v2="analytical")
    base = dict(answer_source="model_synthesis", outcome="answer", structured_query=plan,
                capability_mode="performance_query", cache_hit=False, latency_ms=1234,
                headline="Jane Doe (SGHD12345) scored 91%", scope_banner="Secret Team")
    base.update(kw)
    return SimpleNamespace(**base)


def test_logs_labels_only(caplog):
    with caplog.at_level(logging.INFO, logger="pms.ai.traffic"):
        log_ai_chat_traffic(_payload())
    line = caplog.records[-1].getMessage()
    assert "answer_source=model_synthesis" in line
    assert "outcome=answer" in line
    assert "intent=ranking" in line
    assert "latency_ms=1234" in line
    for leaked in ("Jane", "SGHD", "Secret", "91"):
        assert leaked not in line


def test_label_sanitises_free_text(caplog):
    with caplog.at_level(logging.INFO, logger="pms.ai.traffic"):
        log_ai_chat_traffic(_payload(answer_source="Jane Doe!!"))
    assert "answer_source=janedoe" in caplog.records[-1].getMessage()


def test_never_raises_on_bad_payload():
    log_ai_chat_traffic(object())
    log_ai_chat_traffic(None)

import pytest

from services.ai.router import _deterministic_first_question as det_first


@pytest.mark.parametrize("q", [
    "how is the whole company doing in october 2026",
    "lowest 2 employees in inbound october 2026",
    "what is the overall score across the company",
])
def test_simple_questions_skip_model_planner(q):
    assert det_first(q) is True


@pytest.mark.parametrize("q", ["why is inbound low", "compare egypt and uae", "what is the best team in marketing in egypt in september 2026"])
def test_other_questions_keep_model_planner(q):
    assert det_first(q) is False


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("PMS_AI_DETERMINISTIC_FIRST", "off")
    assert det_first("how is the whole company doing") is False


def test_structured_routing_timeout_is_capped(monkeypatch):
    from services.ai.providers import _routing_timeout

    monkeypatch.delenv("PMS_AI_NVIDIA_ROUTING_TIMEOUT_SECONDS", raising=False)
    assert _routing_timeout(15, 40) == 6.0
    assert _routing_timeout(15, 3) == 3
    monkeypatch.setenv("PMS_AI_NVIDIA_ROUTING_TIMEOUT_SECONDS", "0")
    assert _routing_timeout(15, 40) == 15

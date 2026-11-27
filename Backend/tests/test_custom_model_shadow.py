from services.ai import custom_model_shadow as m


def test_default_off(monkeypatch):
    monkeypatch.delenv("PMS_AI_CUSTOM_MODEL", raising=False)
    assert m.mode() == "off"
    assert m.maybe_shadow("q", {"a": 1}, "x") is False


def test_on_value_is_not_enabled(monkeypatch):
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL", "on")
    assert m.mode() == "off"


def test_shadow_respects_sample_and_cap(monkeypatch):
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL", "shadow")
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL_SAMPLE", "0")
    assert m.maybe_shadow("q", {}, "x") is False
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL_SAMPLE", "1")
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL_DAILY_CAP", "0")
    assert m.maybe_shadow("q", {}, "x") is False


def test_shadow_never_raises_without_credentials(monkeypatch):
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL", "shadow")
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL_SAMPLE", "1")
    monkeypatch.setenv("PMS_AI_CUSTOM_MODEL_DAILY_CAP", "5")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    m._run("q", {"score": 96.0}, "live")  # logs an error outcome, does not raise


def test_invented_numbers():
    assert m.invented_numbers("Nadia scored 96.0, rank 1 of 4", "Nadia 96.0") == ["1", "4"]
    assert m.invented_numbers("scored 1,250", "1250") == []

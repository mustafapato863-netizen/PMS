from api.middleware import auth_middleware


def test_legacy_access_is_disabled_in_production(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ALLOW_LEGACY_API_ACCESS", "1")
    monkeypatch.setattr(auth_middleware.settings, "APP_ENV", "production")

    assert auth_middleware._legacy_access_allowed() is False


def test_legacy_access_requires_explicit_development_opt_in(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(auth_middleware.settings, "APP_ENV", "development")
    monkeypatch.delenv("ALLOW_LEGACY_API_ACCESS", raising=False)

    assert auth_middleware._legacy_access_allowed() is False

    monkeypatch.setenv("ALLOW_LEGACY_API_ACCESS", "1")
    assert auth_middleware._legacy_access_allowed() is True

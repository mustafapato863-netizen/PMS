"""The administrator switch hides PMS AI until it is explicitly turned on."""

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers.settings import router as settings_router
from config.database import Base, get_db
from services.ai.feature_gate import read_ai_enabled, require_ai_enabled
import services.ai.feature_gate as feature_gate


def _client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(settings_router, prefix="/api/settings")

    @app.get("/api/ai/ping")
    def ping(_gate=Depends(require_ai_enabled)):
        return {"ok": True}

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return TestClient(app), session_factory


def test_ai_is_off_until_an_admin_enables_it(monkeypatch):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", read_ai_enabled)
    client, _session_factory = _client()

    hidden = client.get("/api/settings/ai-assistant", headers={"X-User-Role": "Admin"})
    assert hidden.status_code == 200
    assert hidden.json()["data"]["enabled"] is False
    assert client.get("/api/ai/ping", headers={"X-User-Role": "Admin"}).status_code == 403

    denied = client.put("/api/settings/ai-assistant", json={"enabled": True}, headers={"X-User-Role": "Manager"})
    assert denied.status_code == 403

    enabled = client.put("/api/settings/ai-assistant", json={"enabled": True}, headers={"X-User-Role": "Admin", "X-User-Id": "legacy"})
    assert enabled.status_code == 200
    assert enabled.json()["data"]["enabled"] is True
    assert client.get("/api/ai/ping", headers={"X-User-Role": "Manager"}).status_code == 200

    disabled = client.put("/api/settings/ai-assistant", json={"enabled": False}, headers={"X-User-Role": "Admin"})
    assert disabled.json()["data"]["enabled"] is False
    assert client.get("/api/ai/ping", headers={"X-User-Role": "Admin"}).status_code == 403


def test_a_missing_setting_row_stays_off():
    _client_unused, session_factory = _client()
    db = session_factory()
    try:
        assert read_ai_enabled(db) is False
    finally:
        db.close()

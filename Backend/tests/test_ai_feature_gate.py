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

def test_ai_switch_migration_repairs_legacy_database_without_losing_settings(monkeypatch):
    """An upgraded database must support the current ProductSetting ORM and admin toggle."""
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    from models.models import ProductSetting

    migration_file = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "5d3a9b1c7e20_add_product_setting_string_value.py"
    )
    spec = importlib.util.spec_from_file_location("ai_settings_value_migration", migration_file)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "c2d3e4f5a6b7"

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    try:
        with engine.begin() as connection:
            # Original d1a8e4c6b720 schema, before value_str existed.
            connection.exec_driver_sql(
                """
                CREATE TABLE product_settings (
                    key VARCHAR(80) PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT 0,
                    updated_at DATETIME,
                    updated_by_user_id CHAR(32)
                )
                """
            )
            connection.exec_driver_sql(
                "INSERT INTO product_settings (key, enabled) VALUES ('ai_enabled', 0)"
            )
            assert "value_str" not in {
                column["name"] for column in inspect(connection).get_columns("product_settings")
            }
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()
            # Re-running the revision on an already-upgraded schema is safe.
            migration.upgrade()
            assert "value_str" in {
                column["name"] for column in inspect(connection).get_columns("product_settings")
            }

        # Audit writes are tested separately; this test uses only the minimal
        # legacy product_settings table to reproduce the original failure.
        monkeypatch.setattr(feature_gate.AuditService, "log_operation", lambda *_args, **_kw: None)
        with sessionmaker(bind=engine)() as db:
            assert read_ai_enabled(db) is False
            assert feature_gate.set_ai_enabled(db, True, None) is True
            assert read_ai_enabled(db) is True
            row = db.query(ProductSetting).filter(ProductSetting.key == "ai_enabled").one()
            row.value_str = "admin_only"
            db.commit()
            assert db.get(ProductSetting, "ai_enabled").value_str == "admin_only"
    finally:
        engine.dispose()

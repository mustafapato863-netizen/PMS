"""Admin-only PMS AI pilot, default-off switch, and model activation boundaries.

The product switch and the Admin dependency are separate. A non-Admin is
rejected on every AI capability route even when the switch is on. Nothing in
startup, seed, or Compose turns the switch or the model on.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from alembic.migration import MigrationContext
from alembic.operations import Operations
from api.routers import ai_corrective_actions, ai_workspace, router as api_router
from api.routers.settings import router as settings_router
from config.database import Base, get_db
from models.models import ProductSetting
from services.ai import feature_gate
from services.ai.config import get_ai_runtime_config
from services.ai.feature_gate import (
    read_ai_enabled,
    require_ai_admin,
    require_ai_corrective_action_pilot_enabled,
    require_ai_diagnostic_session,
    require_ai_enabled,
)
from services.ai.llm_client import local_exploration_enabled, local_intent_enabled, local_synthesis_enabled
from services.permission_seed import PERMISSION_MATRIX, seed_role_permissions

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent

NON_ADMIN_ROLES = (
    "General Manager",
    "Manager",
    "Employee",
    "Executive",
    "Performance Team",
    "Function Viewer",
    "Function Director",
    "Branch Director",
    "Regional Manager",
    "Viewer",
)

CHAT_BODY = {"prompt": "Hi"}
FEEDBACK_BODY = {"trace_id": "trace-1", "rating": "up", "reviewer_verified": True}
REVIEW_BODY = {"reviewer_verified": True}
PROPOSAL_BODY = {
    "proposal_id": "prop-1",
    "team": "Inbound",
    "month": "September",
    "year": 2026,
    "action_text": "Coach the team",
    "evidence_revision": "rev-1",
}


def _walk_calls(dependant) -> list:
    found = []
    call = getattr(dependant, "call", None)
    if call is not None:
        found.append(call)
    for child in getattr(dependant, "dependencies", []) or []:
        found.extend(_walk_calls(child))
    return found


def _api_routes() -> list[tuple[str, str, APIRoute]]:
    found: list[tuple[str, str, APIRoute]] = []

    def walk(router, prefix: str) -> None:
        for route in getattr(router, "routes", []):
            if type(route).__name__ == "_IncludedRouter":
                context = route.include_context
                child_prefix = prefix + (context.prefix or "")
                walk(route.original_router, child_prefix)
                continue
            path = prefix + getattr(route, "path", "")
            if isinstance(route, APIRoute):
                for method in sorted(route.methods - {"HEAD"}):
                    found.append((method, path, route))

    walk(api_router, "")
    return found


def _ai_routes() -> list[tuple[str, str, APIRoute]]:
    return [(method, path, route) for method, path, route in _api_routes() if path.startswith("/ai")]


def _is_pilot_route(route: APIRoute) -> bool:
    """Corrective-action pilot routes (#98) have their own gates, checked below."""
    return route in ai_corrective_actions.router.routes


def _capability_routes() -> list[tuple[str, str, APIRoute]]:
    return [
        item for item in _ai_routes()
        if not item[1].endswith("/diagnostics") and not _is_pilot_route(item[2])
    ]


def _pilot_routes() -> list[tuple[str, str, APIRoute]]:
    return [item for item in _ai_routes() if _is_pilot_route(item[2])]


def _body_for(path: str) -> dict | None:
    if path.endswith("/chat"):
        return CHAT_BODY
    if path.endswith("/feedback"):
        return FEEDBACK_BODY
    if path.endswith("/review"):
        return REVIEW_BODY
    if path.endswith("/proposals/confirm"):
        return PROPOSAL_BODY
    if path.endswith("/conversations"):
        return {}
    return None


def _client(monkeypatch) -> TestClient:
    def boom(*_args, **_kwargs):
        raise HTTPException(status_code=418, detail="handler")

    class Boom:
        def __init__(self, *_args, **_kwargs):
            pass

        def __getattr__(self, _name):
            return boom

    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", lambda db, request: {"role": "Admin", "user_id": "admin"})
    monkeypatch.setattr(ai_workspace, "release_read_transaction", lambda db: None)
    monkeypatch.setattr(ai_workspace, "PmsAiOrchestrator", Boom)
    monkeypatch.setattr(ai_workspace, "AiConversationService", Boom)
    monkeypatch.setattr(ai_workspace, "TrainingTraceLogger", Boom)
    monkeypatch.setattr(ai_workspace, "confirm_corrective_action_proposal", boom)
    monkeypatch.setattr(ai_workspace, "get_ai_catalog", lambda: Boom())
    monkeypatch.setattr(ai_workspace, "build_ai_diagnostics_payload", boom)

    app = FastAPI()
    app.include_router(ai_workspace.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_router_registry_lists_every_ai_capability_route_behind_both_gates():
    routes = _capability_routes()
    inventory = sorted(f"{method} /api{path}" for method, path, _route in routes)
    assert inventory == [
        "DELETE /api/ai/conversations/{conversation_id}",
        "GET /api/ai/catalog",
        "GET /api/ai/conversations/{conversation_id}/context",
        "GET /api/ai/traces/export",
        "GET /api/ai/watching",
        "POST /api/ai/chat",
        "POST /api/ai/conversations",
        "POST /api/ai/feedback",
        "POST /api/ai/proposals/confirm",
        "POST /api/ai/traces/{trace_id}/review",
    ]
    assert ai_workspace.AI_WORKSPACE_ROLES == ["Admin"]
    for _method, _path, route in routes:
        calls = _walk_calls(route.dependant)
        assert require_ai_enabled in calls
        assert require_ai_admin in calls
    diagnostic = [item for item in _ai_routes() if item[1].endswith("/diagnostics")]
    assert [f"{method} /api{path}" for method, path, _route in diagnostic] == ["GET /api/ai/diagnostics"]
    diagnostic_calls = _walk_calls(diagnostic[0][2].dependant)
    assert require_ai_enabled not in diagnostic_calls
    assert require_ai_admin in diagnostic_calls
    assert require_ai_diagnostic_session in diagnostic_calls

    # Every /ai route is either a chat capability, diagnostics, or a pilot route.
    assert len(_ai_routes()) == len(routes) + len(diagnostic) + len(_pilot_routes())
    # The corrective-action pilot is behind session + Admin + its own switch,
    # and deliberately NOT behind the standalone chat switch.
    pilot = _pilot_routes()
    assert [f"{method} /api{path}" for method, path, _route in pilot] == ["POST /api/ai/corrective-action-suggestions"]
    for _method, _path, route in pilot:
        calls = _walk_calls(route.dependant)
        assert require_ai_diagnostic_session in calls
        assert require_ai_admin in calls
        assert require_ai_corrective_action_pilot_enabled in calls
        assert require_ai_enabled not in calls

    control_plane = sorted(
        {path for _method, path, _route in _api_routes() if "ai" in path.casefold() and not path.startswith("/ai")}
    )
    assert control_plane == ["/settings/ai-assistant", "/settings/ai-corrective-action-pilot"]
    for _method, path, route in _api_routes():
        if path != "/settings/ai-assistant":
            continue
        calls = _walk_calls(route.dependant)
        assert require_ai_enabled not in calls
        assert require_ai_admin not in calls


def test_non_admin_is_forbidden_on_every_ai_route_when_the_switch_is_on(monkeypatch):
    client = _client(monkeypatch)
    for method, path, _route in _capability_routes():
        url = "/api" + path.format(conversation_id="conv-1", trace_id="trace-1")
        body = _body_for(path)
        admin = client.request(method, url, headers={"X-User-Role": "Admin"}, json=body)
        assert admin.status_code == 418, (method, url, admin.status_code, admin.text)
        for role in NON_ADMIN_ROLES:
            denied = client.request(method, url, headers={"X-User-Role": role}, json=body)
            assert denied.status_code == 403, (role, method, url, denied.status_code, denied.text)
            assert denied.json()["detail"] == "PMS AI is limited to administrators during the pilot."


def test_ai_routes_stay_closed_for_admin_when_the_switch_is_off(monkeypatch):
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: False)
    client = _client(monkeypatch)
    for method, path, _route in _capability_routes():
        url = "/api" + path.format(conversation_id="conv-1", trace_id="trace-1")
        response = client.request(method, url, headers={"X-User-Role": "Admin"}, json=_body_for(path))
        assert response.status_code == 403
        assert response.json()["detail"] == "PMS AI is turned off."


def test_corrective_action_pilot_route_is_admin_only_and_needs_its_own_switch(monkeypatch):
    class Boom:
        def __init__(self, *_args, **_kwargs):
            pass

        def suggest(self, **_kwargs):
            raise HTTPException(status_code=418, detail="handler")

    monkeypatch.setattr(ai_corrective_actions, "require_authenticated_scope", lambda db, request: {"role": "Admin", "user_id": "admin"})
    monkeypatch.setattr(ai_corrective_actions, "release_read_transaction", lambda db: None)
    monkeypatch.setattr(ai_corrective_actions, "CorrectiveActionDrafter", Boom)
    app = FastAPI()
    app.include_router(ai_corrective_actions.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app, raise_server_exceptions=False)
    url = "/api/ai/corrective-action-suggestions"
    body = {"team": "Inbound", "month": "September", "year": 2026}

    # Chat on, pilot off: the pilot stays closed for Admin.
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: True)
    monkeypatch.setattr(feature_gate, "read_ai_corrective_action_pilot_enabled", lambda db: False)
    closed = client.post(url, headers={"X-User-Role": "Admin"}, json=body)
    assert closed.status_code == 403
    assert closed.json()["detail"] == "The corrective-action pilot is turned off."

    # Pilot on, chat off: Admin reaches the handler, every other role is refused.
    monkeypatch.setattr(feature_gate, "is_ai_enabled", lambda db: False)
    monkeypatch.setattr(feature_gate, "read_ai_corrective_action_pilot_enabled", lambda db: True)
    assert client.post(url, headers={"X-User-Role": "Admin"}, json=body).status_code == 418
    for role in NON_ADMIN_ROLES:
        denied = client.post(url, headers={"X-User-Role": role}, json=body)
        assert denied.status_code == 403, (role, denied.status_code, denied.text)
        assert denied.json()["detail"] == "PMS AI is limited to administrators during the pilot."
    assert client.post(url, json=body).status_code == 401


def test_only_an_admin_can_change_the_switch_and_startup_cannot_enable_it(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(feature_gate, "is_ai_enabled", read_ai_enabled)

    app = FastAPI()
    app.include_router(settings_router, prefix="/api/settings")

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    assert client.get("/api/settings/ai-assistant", headers={"X-User-Role": "Employee"}).json()["data"]["enabled"] is False
    denied = client.put("/api/settings/ai-assistant", json={"enabled": True}, headers={"X-User-Role": "Manager"})
    assert denied.status_code == 403
    assert client.get("/api/settings/ai-assistant", headers={"X-User-Role": "Admin"}).json()["data"]["enabled"] is False

    callers = []
    for path in BACKEND.rglob("*.py"):
        if "tests" in path.parts or path.name == "feature_gate.py":
            continue
        if "set_ai_enabled(" in path.read_text(encoding="utf-8"):
            callers.append(path.relative_to(BACKEND).as_posix())
    assert callers == ["api/routers/settings.py"]
    for role, permissions in PERMISSION_MATRIX.items():
        assert not any("ai" in permission.casefold() for permission in permissions), role


def test_fresh_migration_seed_and_missing_row_leave_ai_off():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    migration = BACKEND / "migrations" / "versions" / "d1a8e4c6b720_add_ai_feature_switch.py"
    spec = importlib.util.spec_from_file_location("ai_feature_switch", migration)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            module.upgrade()
        enabled = connection.execute(text("select enabled from product_settings where key = 'ai_enabled'")).scalar()
    assert enabled in (0, False)
    assert ProductSetting.enabled.default.arg is False

    factory = sessionmaker(bind=engine)
    db = factory()
    try:
        db.execute(text("delete from product_settings"))
        db.commit()
        assert read_ai_enabled(db) is False
    finally:
        db.close()

    seed_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=seed_engine)
    seed_db = sessionmaker(bind=seed_engine)()
    try:
        assert read_ai_enabled(seed_db) is False
        seed_role_permissions(seed_db)
        assert read_ai_enabled(seed_db) is False
        assert seed_db.query(ProductSetting).count() == 0
    finally:
        seed_db.close()

    for name in ("seeding_service.py", "permission_seed.py"):
        assert "ai_enabled" not in (BACKEND / "services" / name).read_text(encoding="utf-8")


def test_model_stays_off_without_credentials_and_production_exploration_cannot_be_enabled(monkeypatch):
    for name in (
        "PMS_AI_INTENT_ENABLED",
        "PMS_AI_SYNTHESIS_ENABLED",
        "PMS_AI_EXPLORATION_ENABLED",
        "CLOUDFLARE_ACCOUNT_ID",
        "CF_ACCOUNT_ID",
        "CLOUDFLARE_API_TOKEN",
        "CF_API_TOKEN",
        "CLOUDFLARE_API_KEY",
        "GEMINI_API_KEY",
        "Gemini_API_KEY",
        "GOOGLE_API_KEY",
        "PMS_AI_LOCAL_ROUTER_ENABLED",
        "PMS_AI_LOCAL_SYNTHESIS_ENABLED",
        "PMS_AI_LOCAL_EXPLORATION_ENABLED",
        "PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
    assert local_intent_enabled() is False
    assert local_synthesis_enabled() is False
    assert local_exploration_enabled() is False

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PMS_AI_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_LOCAL_DATA_EXPLORATION_ENABLED", "true")
    monkeypatch.setenv("PMS_AI_CLASSIFIER_MODE", "enabled")
    assert local_exploration_enabled() is False
    assert get_ai_runtime_config().classifier_mode == "off"


def _hostinger_trigger_keys(workflow: str) -> set[str]:
    """Top-level keys of the workflow `on:` block. Job steps are not triggers."""
    lines = workflow.splitlines()
    start = next(index for index, line in enumerate(lines) if line == "on:")
    keys: set[str] = set()
    for line in lines[start + 1:]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith(" "):
            break
        if line.startswith("  ") and not line.startswith("   ") and line.endswith(":"):
            keys.add(line.strip()[:-1])
    return keys


def test_hostinger_deploy_workflow_has_no_automatic_trigger():
    workflow = (REPO / ".github" / "workflows" / "deploy-hostinger.yml").read_text(encoding="utf-8")
    triggers = _hostinger_trigger_keys(workflow)
    assert "workflow_run" not in triggers
    assert "push" not in triggers
    assert "pull_request" not in triggers
    assert triggers == {"workflow_dispatch"}
    header = workflow.split("on:", 1)[0]
    assert "Dokploy" in header
    assert "manual-only" in header


_REQUIRED_PROVIDER_VARS = (
    "PMS_AI_PRIMARY_PROVIDER",
    "PMS_AI_FALLBACK_PROVIDER",
    "PMS_AI_CLOUDFLARE_ENABLED",
    "PMS_AI_GEMINI_ENABLED",
    "PMS_AI_FALLBACK_ENABLED",
    "PMS_AI_OPENAI_ENABLED",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_AI_MODEL",
    "CLOUDFLARE_AI_MODEL_ALTER",
    "GEMINI_API_KEY",
    "PMS_GEMINI_MODEL",
)

_LEGACY_MARKERS = ("PMS_AI_LLM_", "pms-qwen-pilot", "llama.cpp", "qwen", "OPENAI_API_KEY")


def test_compose_and_deploy_use_only_cloudflare_primary_gemini_fallback():
    for relative in ("docker-compose.yml", "compose.production.yml"):
        text_value = (REPO / relative).read_text(encoding="utf-8")
        for var in _REQUIRED_PROVIDER_VARS:
            assert f"  {var}:" in text_value, f"{relative} must pass {var}"
        assert "PMS_AI_PRIMARY_PROVIDER: ${PMS_AI_PRIMARY_PROVIDER:-cloudflare}" in text_value
        assert "PMS_AI_FALLBACK_PROVIDER: ${PMS_AI_FALLBACK_PROVIDER:-gemini}" in text_value
        assert "PMS_AI_CLOUDFLARE_ENABLED: ${PMS_AI_CLOUDFLARE_ENABLED:-true}" in text_value
        assert "PMS_AI_GEMINI_ENABLED: ${PMS_AI_GEMINI_ENABLED:-true}" in text_value
        assert "PMS_AI_FALLBACK_ENABLED: ${PMS_AI_FALLBACK_ENABLED:-true}" in text_value
        assert "PMS_AI_OPENAI_ENABLED: ${PMS_AI_OPENAI_ENABLED:-false}" in text_value
        assert "CLOUDFLARE_AI_MODEL: ${CLOUDFLARE_AI_MODEL:-@cf/ibm-granite/granite-4.0-h-micro}" in text_value
        assert "CLOUDFLARE_AI_MODEL_ALTER: ${CLOUDFLARE_AI_MODEL_ALTER:-@cf/zai-org/glm-4.7-flash}" in text_value
        assert "PMS_GEMINI_MODEL: ${PMS_GEMINI_MODEL:-gemini-2.5-flash}" in text_value
        # Secrets are pass-through only; no literal default value.
        assert "CLOUDFLARE_API_TOKEN: ${CLOUDFLARE_API_TOKEN:-}" in text_value
        assert "GEMINI_API_KEY: ${GEMINI_API_KEY:-}" in text_value
        for marker in _LEGACY_MARKERS:
            assert marker.casefold() not in text_value.casefold(), f"{relative} still references {marker}"

    workflow = (REPO / ".github" / "workflows" / "deploy-hostinger.yml").read_text(encoding="utf-8")
    assert _hostinger_trigger_keys(workflow) == {"workflow_dispatch"}
    assert "PMS_AI_OPENAI_ENABLED=false" in workflow
    for marker in _LEGACY_MARKERS:
        assert marker.casefold() not in workflow.casefold(), f"deploy workflow still references {marker}"
    for example in (REPO / "DevOps" / ".env.example", REPO / "DevOps" / ".env.hostinger.example"):
        example_text = example.read_text(encoding="utf-8")
        assert "PMS_AI_OPENAI_ENABLED=false" in example_text
        assert "PMS_AI_PRIMARY_PROVIDER=cloudflare" in example_text
        assert "CLOUDFLARE_AI_MODEL_ALTER=@cf/zai-org/glm-4.7-flash" in example_text
        for marker in _LEGACY_MARKERS:
            assert marker.casefold() not in example_text.casefold(), f"{example.name} still references {marker}"


@pytest.mark.parametrize("role", NON_ADMIN_ROLES)
def test_previously_allowed_roles_are_not_in_the_workspace_role_list(role):
    assert role not in ai_workspace.AI_WORKSPACE_ROLES

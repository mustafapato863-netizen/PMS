from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.routers import ai_workspace
from config.database import get_db


def test_training_export_requires_admin_and_reviewed_only(monkeypatch):
    app = FastAPI()

    @app.middleware("http")
    async def test_identity(request: Request, call_next):
        request.state.user = {"role": request.headers.get("x-test-role", "Viewer"), "user_id": "test-user"}
        return await call_next(request)

    app.include_router(ai_workspace.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(ai_workspace, "require_authenticated_scope", lambda db, request: request.state.user)
    monkeypatch.setattr(ai_workspace, "release_read_transaction", lambda db: None)
    calls = []

    class FakeLogger:
        def __init__(self, db):
            pass

        def export_distillation_dataset(self, **kwargs):
            calls.append(kwargs)
            return []

        def record_feedback(self, **kwargs):
            calls.append(kwargs)
            return True, True

    monkeypatch.setattr(ai_workspace, "TrainingTraceLogger", FakeLogger)
    client = TestClient(app)
    assert client.get('/api/ai/traces/export', headers={'x-test-role': 'Manager'}).status_code == 403
    assert client.get('/api/ai/traces/export?verified_only=false', headers={'x-test-role': 'Admin'}).status_code == 422
    assert calls == []
    response = client.get('/api/ai/traces/export', headers={'x-test-role': 'Admin'})
    assert response.status_code == 200
    assert calls[0]['verified_only'] is True
    feedback = client.post(
        '/api/ai/feedback',
        headers={'x-test-role': 'Manager'},
        json={'trace_id': 'test-trace', 'rating': 'up', 'reviewer_verified': True},
    )
    assert feedback.status_code == 200
    assert feedback.json()['is_distillation_eligible'] is False
    assert feedback.json()['reviewer_verified'] is False
    assert calls[-1]['reviewer_verified'] is None

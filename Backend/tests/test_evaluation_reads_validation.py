"""Transport validation only; authorization has its own real-user safety matrix."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import evaluation_settings
from config.database import get_db


@pytest.fixture
def read_client(monkeypatch):
    calls = []
    actor = {"role": "Admin", "user_id": "synthetic-transport-only"}
    monkeypatch.setattr(evaluation_settings, "_actor", lambda *_: actor)

    class Workflow:
        def __init__(self, _db):
            pass

        def reads(self, actor, scope_id, year, months):
            calls.append((actor, scope_id, year, months))
            return {"scope_id": scope_id, "periods": months}

    monkeypatch.setattr(evaluation_settings, "EvaluationWorkflow", Workflow)
    app = FastAPI()
    app.include_router(evaluation_settings.router, prefix="/api/settings/evaluation")
    app.dependency_overrides[get_db] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, calls


@pytest.mark.parametrize("months", ["x", "0", "13", "-1", "7.5", "7,", ",7", "7,,8", "7,7", "1,2,3,4,5,6,7,8,9,10,11,12,1"])
def test_invalid_calendar_month_list_is_422_without_read_work(read_client, months):
    client, calls = read_client
    result = client.get("/api/settings/evaluation/reads", params={"scope_id": "synthetic", "year": 2026, "months": months})
    assert result.status_code == 422
    assert calls == []


@pytest.mark.parametrize("months, expected", [("7", [7]), ("07, 8", [7, 8]), ("1,2,3,4,5,6,7,8,9,10,11,12", list(range(1, 13)))])
def test_exact_calendar_months_keep_requested_order(read_client, months, expected):
    client, calls = read_client
    result = client.get("/api/settings/evaluation/reads", params={"scope_id": "synthetic", "year": 2026, "months": months})
    assert result.status_code == 200
    assert result.json()["data"]["periods"] == expected
    assert len(calls) == 1

"""Tests for Health Check API, Error Logging, and Alerting Middleware
"""

import pytest
import time
from unittest.mock import patch, MagicMock
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from models.models import Base, User, ErrorLog
from api.routers.health import router as health_router
from api.middleware.error_handling_middleware import (
    ErrorHandlingMiddleware,
    install_api_error_handlers,
)
from config.database import get_db
from services.health_check_service import HealthCheckService
from services.error_tracker import ErrorTracker


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create tables (avoiding tables with JSONB/INET columns on SQLite)
    Base.metadata.create_all(bind=engine, tables=[User.__table__, ErrorLog.__table__])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function", autouse=True)
def mock_session_local(db_session):
    """Mock SessionLocal inside the middleware to use our SQLite test db"""
    class MockSessionContext:
        def __enter__(self):
            return db_session
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    with patch("api.middleware.error_handling_middleware.SessionLocal", return_value=MockSessionContext()):
        yield


@pytest.fixture(scope="function")
def test_client(db_session):
    """FastAPI TestClient mounted with health check router & error handling middleware"""
    app = FastAPI()
    install_api_error_handlers(app)
    app.add_middleware(ErrorHandlingMiddleware)
    app.include_router(health_router)
    
    @app.get("/trigger-value-error")
    async def trigger_value_error():
        raise ValueError("Invalid parameter value test")
        
    @app.get("/trigger-runtime-error")
    async def trigger_runtime_error():
        raise RuntimeError("System crash runtime error test")

    @app.get("/trigger-http-403")
    def trigger_http_403():
        raise HTTPException(status_code=403, detail="Forbidden test error")

    @app.get("/validated")
    def validated(value: int = Query(..., ge=1)):
        return {"value": value}

    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


def test_health_check_endpoint_healthy(test_client, db_session):
    """Verify GET /health returns 200 OK and healthy status details"""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.headers["server-timing"].startswith("app;dur=")
    assert float(response.headers["x-response-time-ms"]) >= 0
    
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["details"]["database"]["status"] == "up"
    assert data["details"]["database"]["latency_ms"] is not None


def test_health_probe_is_excluded_from_request_rate_metrics(test_client):
    with patch.object(ErrorTracker, "register_request") as register_request:
        response = test_client.get("/health")
    assert response.status_code == 200
    register_request.assert_not_called()


def test_health_check_endpoint_unhealthy_db(test_client):
    """Verify GET /health returns 503 Service Unavailable when DB is down"""
    mock_report = {
        "status": "unhealthy",
        "timestamp": "2026-06-20T21:00:00Z",
        "details": {
            "database": {
                "status": "down",
                "latency_ms": None,
                "error": "Connection refused"
            },
            "redis": {
                "status": "disabled",
                "latency_ms": None,
                "error": None
            }
        }
    }
    
    with patch.object(HealthCheckService, "check_health", return_value=mock_report):
        response = test_client.get("/health")
        assert response.status_code == 503
        
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["details"]["database"]["status"] == "down"


def test_error_handling_middleware_value_error(test_client, db_session):
    """Verify ValueError is mapped to HTTP 400 and returned as clean JSON response"""
    response = test_client.get("/trigger-value-error")
    assert response.status_code == 400
    
    data = response.json()
    assert data["success"] is False
    assert "Invalid parameter value test" in data["message"]
    assert "request_id" in data
    assert response.headers["x-request-id"] == data["request_id"]
    assert response.headers["server-timing"].startswith("app;dur=")
    
    # 400 Bad Request error should not be logged to error_logs table as a system failure
    count = db_session.query(ErrorLog).count()
    assert count == 0


def test_error_handling_middleware_runtime_error(test_client, db_session):
    """Verify RuntimeError is caught, logged to DB, and returns HTTP 500"""
    response = test_client.get("/trigger-runtime-error")
    assert response.status_code == 500
    
    data = response.json()
    assert data["success"] is False
    assert "An internal server error occurred" in data["message"]
    assert "request_id" in data
    assert response.headers["x-request-id"] == data["request_id"]
    
    # 500 Internal error should be logged to error_logs table
    logs = db_session.query(ErrorLog).all()
    assert len(logs) == 1
    assert logs[0].error_class == "RuntimeError"
    assert "System crash runtime error test" in logs[0].error_message
    assert logs[0].endpoint == "/trigger-runtime-error"
    assert logs[0].method == "GET"
    assert logs[0].request_id == data["request_id"]


def test_runtime_error_is_counted_once(test_client):
    with patch.object(
        ErrorTracker,
        "register_error",
        wraps=ErrorTracker.register_error,
    ) as register_error:
        response = test_client.get("/trigger-runtime-error")
    assert response.status_code == 500
    register_error.assert_called_once()


def test_error_handling_middleware_http_exception(test_client, db_session):
    """Verify HTTPException is correctly mapped and bypassed in DB logging"""
    response = test_client.get("/trigger-http-403")
    assert response.status_code == 403
    
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Forbidden test error"
    assert data["message"] == data["detail"]
    assert data["success"] is False
    assert response.headers["x-request-id"] == data["request_id"]
    
    # 403 Forbidden is a client error, should not be logged to error_logs table
    count = db_session.query(ErrorLog).count()
    assert count == 0


def test_validation_error_keeps_detail_and_adds_canonical_fields(test_client):
    response = test_client.get("/validated", params={"value": 0})
    assert response.status_code == 422
    data = response.json()
    assert data["success"] is False
    assert data["message"] == "Request validation failed"
    assert isinstance(data["detail"], list)
    assert response.headers["x-request-id"] == data["request_id"]


@patch("urllib.request.urlopen")
def test_error_rate_alerting(mock_urlopen, test_client):
    """Verify critical error rate calculations trigger Slack alerting"""
    # Reset in-memory trackers
    from services.error_tracker import _in_memory_requests, _in_memory_errors, _last_alert_time
    _in_memory_requests.clear()
    _in_memory_errors.clear()
    
    # Mock Slack webhook URL to run alert code
    with patch.dict("os.environ", {"SLACK_WEBHOOK_URL": "http://mock-slack-webhook"}):
        # 1. Feed 10 successful requests
        for _ in range(10):
            ErrorTracker.register_request()
            
        # 2. Feed 2 errors (2 / 12 = 16.6% rate)
        ErrorTracker.register_error()
        ErrorTracker.register_error()
        
        # 3. Evaluate error rate (which triggers alert)
        ErrorTracker.evaluate_error_rate()
        
        # Verify Slack API call was triggered
        mock_urlopen.assert_called_once()
        args = mock_urlopen.call_args[0][0]
        assert args.full_url == "http://mock-slack-webhook"
        assert args.get_method() == "POST"

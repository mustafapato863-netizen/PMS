from fastapi.testclient import TestClient

from app import app
from config import settings
from config.settings import parse_cors_origins

client = TestClient(app)
PRODUCTION_ORIGIN = next(
    (origin for origin in settings.CORS_ORIGINS if origin.startswith("https://")),
    settings.CORS_ORIGINS[0],
)

def test_cors_allowed_origins_parsing():
    origins = parse_cors_origins(
        "http://localhost:5173, https://pms-frontend-iota-dusky.vercel.app , https://another-origin.com/ "
    )
    assert "http://localhost:5173" in origins
    assert "https://pms-frontend-iota-dusky.vercel.app" in origins
    assert "https://another-origin.com" in origins
    assert "https://another-origin.com/" not in origins

def test_preflight_allowed_production_origin():
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": PRODUCTION_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization, content-type"
        }
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == PRODUCTION_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_preflight_allowed_local_vite_origin():
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5174"
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_login_post_cors_headers():
    response = client.post(
        "/api/auth/login",
        json={"username": "test", "password": "password"},
        headers={"Origin": PRODUCTION_ORIGIN}
    )
    # Even if auth fails, the CORS headers should be present
    assert response.headers.get("access-control-allow-origin") == PRODUCTION_ORIGIN
    assert response.headers.get("access-control-allow-credentials") == "true"

def test_rejected_unknown_origin():
    # If the origin is unknown, CORSMiddleware will NOT add the ACAO header.
    # It passes the request down. For an OPTIONS request, if it's not a valid preflight,
    # the router or AuthMiddleware might handle it.
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://evil-attacker.com",
            "Access-Control-Request-Method": "POST",
        }
    )
    # The ACAO header should not be the evil origin
    assert response.headers.get("access-control-allow-origin") != "https://evil-attacker.com"

"""Authentication and Password Validation Tests
"""

import pytest
import jwt
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from config import settings
from models.models import Base, RefreshSession, User, RolePermission
from services.password_service import (
    validate_password_strength,
    hash_password,
    verify_password
)
from services.auth_service import AuthenticationService


@pytest.fixture(scope="function")
def db_session():
    """Create in-memory SQLite database session for testing"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    # Create tables
    Base.metadata.create_all(bind=engine, tables=[
        User.__table__,
        RolePermission.__table__,
        RefreshSession.__table__,
    ])
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    yield session
    session.close()


class TestPasswordService:
    """Tests for PasswordService helpers"""
    
    @pytest.mark.parametrize("valid_password", [
        "SecurePassword123!",
        "VeryLongPasswordWithSpecialChar1$",
        "A1b2C3d4E5f6#",
        "P@ssw0rdP@ssw0rd"
    ])
    def test_validate_password_strength_valid(self, valid_password):
        """Verify that valid passwords pass validation without raising ValueError"""
        try:
            validate_password_strength(valid_password)
        except ValueError as e:
            pytest.fail(f"Valid password '{valid_password}' failed validation: {e}")

    @pytest.mark.parametrize("invalid_password, error_substring", [
        ("Short1!", "at least 12 characters long"),
        ("nouppercase123!", "at least one uppercase letter"),
        ("NOLOWERCASE123!", "at least one lowercase letter"),
        ("NoSpecialChar123", "at least one special character"),
        ("NoDigitsHere!!", "at least one digit")
    ])
    def test_validate_password_strength_invalid(self, invalid_password, error_substring):
        """Verify that invalid passwords raise ValueError with descriptive message"""
        with pytest.raises(ValueError) as exc_info:
            validate_password_strength(invalid_password)
        assert error_substring in str(exc_info.value)

    def test_hash_password_not_plaintext(self):
        """Verify that hashed password does not equal plaintext and is securely hashed"""
        password = "SecurePassword123!"
        hashed = hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 20
        # Verify it can be decoded and verified
        assert verify_password(password, hashed) is True
        # Verify invalid password fails verification
        assert verify_password("wrong_password", hashed) is False


class TestAuthenticationService:
    """Tests for AuthenticationService"""

    def test_create_user_success(self, db_session):
        """Test successful user creation"""
        user = AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        assert user.username == "testuser"
        assert user.email == "test@test.com"
        assert user.password_hash != "SecurePassword123!"
        assert verify_password("SecurePassword123!", user.password_hash) is True
        assert user.role == "Viewer"
        assert user.is_active is True
        assert user.failed_login_attempts == 0

    def test_create_user_duplicate_username(self, db_session):
        """Verify duplicate username raises error"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        with pytest.raises(ValueError) as exc:
            AuthenticationService.create_user(db_session, "testuser", "another@test.com", "SecurePassword123!")
        assert "already taken" in str(exc.value)

    def test_create_user_duplicate_email(self, db_session):
        """Verify duplicate email raises error"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        with pytest.raises(ValueError) as exc:
            AuthenticationService.create_user(db_session, "anotheruser", "test@test.com", "SecurePassword123!")
        assert "already registered" in str(exc.value)

    def test_authenticate_user_success(self, db_session):
        """Verify successful authentication and JWT issuance"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!", "Admin")
        
        token = AuthenticationService.authenticate_user(db_session, "testuser", "SecurePassword123!")
        assert token is not None
        
        # Verify token contents
        payload = AuthenticationService.validate_token(token)
        assert payload["username"] == "testuser"
        assert payload["role"] == "Admin"
        
        # Check database last_login updated
        user = db_session.query(User).filter(User.username == "testuser").first()
        assert user.last_login is not None

    def test_authenticate_user_invalid_credentials(self, db_session):
        """Verify failed login increments count and locked flag is checked"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        
        with pytest.raises(ValueError) as exc:
            AuthenticationService.authenticate_user(db_session, "testuser", "WrongPassword123!")
        assert "Invalid username" in str(exc.value)
        
        user = db_session.query(User).filter(User.username == "testuser").first()
        assert user.failed_login_attempts == 1

    def test_account_lockout_after_five_attempts(self, db_session):
        """Verify account locks after 5 failed attempts"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        
        # First 4 attempts
        for i in range(4):
            with pytest.raises(ValueError) as exc:
                AuthenticationService.authenticate_user(db_session, "testuser", "WrongPassword123!")
            assert "Invalid username" in str(exc.value)
            
        user = db_session.query(User).filter(User.username == "testuser").first()
        assert user.failed_login_attempts == 4
        assert user.locked_until is None

        # 5th attempt locks the account
        with pytest.raises(ValueError) as exc:
            AuthenticationService.authenticate_user(db_session, "testuser", "WrongPassword123!")
        assert "locked" in str(exc.value)
        
        assert user.failed_login_attempts == 5
        assert user.locked_until is not None

        # Subsequent attempts fail instantly with lockout message
        with pytest.raises(ValueError) as exc:
            AuthenticationService.authenticate_user(db_session, "testuser", "SecurePassword123!")
        assert "temporarily locked" in str(exc.value)

    def test_lockout_expiration(self, db_session):
        """Verify lockout expires and user can log in again"""
        AuthenticationService.create_user(db_session, "testuser", "test@test.com", "SecurePassword123!")
        user = db_session.query(User).filter(User.username == "testuser").first()
        
        # Manually set locked_until to the past
        user.failed_login_attempts = 5
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=5)
        db_session.commit()
        
        # User should be able to log in successfully
        token = AuthenticationService.authenticate_user(db_session, "testuser", "SecurePassword123!")
        assert token is not None
        assert user.failed_login_attempts == 0
        assert user.locked_until is None

    def test_validate_token_expired(self):
        """Verify validation fails on expired token"""
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": "some_id",
            "username": "some_user",
            "exp": now - timedelta(seconds=10) # expired
        }
        expired_token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
        
        with pytest.raises(ValueError) as exc:
            AuthenticationService.validate_token(expired_token)
        assert "expired" in str(exc.value)

    def test_validate_token_invalid_signature(self):
        """Verify validation fails on tampered token"""
        now = datetime.now(timezone.utc)
        payload = {
            "user_id": "some_id",
            "username": "some_user",
            "exp": now + timedelta(hours=1)
        }
        token = jwt.encode(payload, "wrong_secret", algorithm=settings.JWT_ALGORITHM)
        
        with pytest.raises(ValueError) as exc:
            AuthenticationService.validate_token(token)
        assert "Invalid token" in str(exc.value)

    def test_generate_reset_token(self):
        """Verify reset token is created with 24-hour expiry"""
        user_id = "test_uuid"
        token = AuthenticationService.generate_reset_token(user_id)
        
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        assert payload["user_id"] == user_id
        assert payload["type"] == "reset"
        
        # Check that expiry is about 24 hours from now
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        now = datetime.now(timezone.utc)
        diff = exp - now
        assert diff.total_seconds() > 23 * 3600 # almost 24h


# ============================================================
# INTERACTION AND MIDDLEWARE TESTS
# ============================================================

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from api.middleware.auth_middleware import AuthMiddleware
from api.routers.auth import router as auth_router
from config.database import get_db

@pytest.fixture(scope="function")
def test_client(db_session):
    """Create a test FastAPI client with AuthMiddleware and AuthRouter"""
    test_app = FastAPI()
    test_app.add_middleware(AuthMiddleware)
    
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    test_app.dependency_overrides[get_db] = override_get_db
    test_app.include_router(auth_router, prefix="/api")
    
    @test_app.get("/api/protected")
    async def protected_endpoint(request: Request):
        return {"success": True, "user": request.state.user}

    @test_app.get("/api/health/liveness")
    async def liveness_endpoint():
        return {"status": "alive"}

    @test_app.get("/api/health/readiness")
    async def readiness_endpoint():
        return {"status": "ready"}
        
    client = TestClient(test_app)
    yield client
    test_app.dependency_overrides.clear()


class TestAuthRouterAndMiddleware:
    """Integration tests for AuthMiddleware and Router"""

    def test_login_success(self, test_client, db_session):
        """Test successful login endpoint"""
        AuthenticationService.create_user(db_session, "loginuser", "login@test.com", "SecurePassword123!")
        
        response = test_client.post("/api/auth/login", json={
            "username": "loginuser",
            "password": "SecurePassword123!"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "access_token" in data["data"]
        assert data["data"]["username"] == "loginuser"
        assert data["data"]["role"] == "Viewer"
        assert data["data"]["expires_in"] == settings.JWT_EXPIRE_MINUTES * 60
        assert data["data"]["csrf_token"]
        assert test_client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        assert db_session.query(RefreshSession).count() == 1

    def test_login_honors_remember_me_and_rotates_refresh_token(self, test_client, db_session):
        AuthenticationService.create_user(db_session, "rotateuser", "rotate@test.com", "SecurePassword123!")

        login_response = test_client.post(
            "/api/auth/login",
            json={
                "username": "rotateuser",
                "password": "SecurePassword123!",
                "remember_me": True,
            },
        )
        assert login_response.status_code == 200
        login_data = login_response.json()["data"]
        old_refresh = test_client.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        old_csrf = login_data["csrf_token"]
        first = db_session.query(RefreshSession).one()
        assert first.remember_me is True

        refresh_response = test_client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-Token": old_csrf},
        )
        assert refresh_response.status_code == 200
        assert refresh_response.json()["data"]["access_token"] != login_data["access_token"]
        db_session.refresh(first)
        assert first.revocation_reason == "rotated"
        assert first.replaced_by_session_id is not None
        assert db_session.query(RefreshSession).count() == 2

        # Presenting the rotated token again revokes the entire family.
        test_client.cookies.set(settings.AUTH_REFRESH_COOKIE_NAME, old_refresh)
        reuse_response = test_client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-Token": old_csrf},
        )
        assert reuse_response.status_code == 401
        assert all(row.revoked_at is not None for row in db_session.query(RefreshSession).all())

    def test_new_login_access_token_reaches_protected_route(self, test_client, db_session):
        AuthenticationService.create_user(db_session, "browseruser", "browser@test.com", "SecurePassword123!")
        login_response = test_client.post(
            "/api/auth/login",
            json={"username": "browseruser", "password": "SecurePassword123!"},
        )
        token = login_response.json()["data"]["access_token"]

        protected_response = test_client.get(
            "/api/protected",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert protected_response.status_code == 200
        assert protected_response.json()["user"]["username"] == "browseruser"

    def test_refresh_rejects_invalid_csrf_token(self, test_client, db_session):
        AuthenticationService.create_user(db_session, "csrfuser", "csrf@test.com", "SecurePassword123!")
        response = test_client.post(
            "/api/auth/login",
            json={"username": "csrfuser", "password": "SecurePassword123!"},
        )
        assert response.status_code == 200

        refresh_response = test_client.post(
            "/api/auth/refresh",
            headers={"X-CSRF-Token": "wrong-token"},
        )
        assert refresh_response.status_code == 403

        missing_csrf_response = test_client.post("/api/auth/refresh")
        assert missing_csrf_response.status_code == 403

    def test_refresh_rejects_untrusted_origin_in_hosted_mode(self, test_client, db_session, monkeypatch):
        AuthenticationService.create_user(db_session, "originuser", "origin@test.com", "SecurePassword123!")
        response = test_client.post(
            "/api/auth/login",
            json={"username": "originuser", "password": "SecurePassword123!"},
        )
        csrf_token = response.json()["data"]["csrf_token"]
        monkeypatch.setattr(settings, "APP_ENV", "production")

        refresh_response = test_client.post(
            "/api/auth/refresh",
            headers={
                "Origin": "https://evil.example",
                "X-CSRF-Token": csrf_token,
            },
        )
        assert refresh_response.status_code == 403

    def test_cookie_logout_revokes_refresh_session(self, test_client, db_session):
        AuthenticationService.create_user(db_session, "cookieuser", "cookie@test.com", "SecurePassword123!")
        response = test_client.post(
            "/api/auth/login",
            json={"username": "cookieuser", "password": "SecurePassword123!"},
        )
        csrf_token = response.json()["data"]["csrf_token"]
        logout_response = test_client.post(
            "/api/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logout_response.status_code == 200
        assert db_session.query(RefreshSession).one().revocation_reason == "logout"

    def test_login_invalid_credentials(self, test_client, db_session):
        """Test login with wrong credentials"""
        AuthenticationService.create_user(db_session, "loginuser", "login@test.com", "SecurePassword123!")
        
        response = test_client.post("/api/auth/login", json={
            "username": "loginuser",
            "password": "WrongPassword123!"
        })
        
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data

    def test_login_lockout(self, test_client, db_session):
        """Test login lock out endpoint behavior after 5 failures"""
        AuthenticationService.create_user(db_session, "loginuser", "login@test.com", "SecurePassword123!")
        
        # 5 failed attempts
        for _ in range(5):
            response = test_client.post("/api/auth/login", json={
                "username": "loginuser",
                "password": "WrongPassword123!"
            })
            
        assert response.status_code == 423 # Locked
        assert "lock" in response.json()["detail"].lower()

    def test_protected_route_unauthorized(self, test_client):
        """Test calling protected endpoint without headers"""
        response = test_client.get("/api/protected")
        assert response.status_code == 401
        assert response.json()["success"] is False
        assert "Missing or invalid authorization header" in response.json()["message"]

    @pytest.mark.parametrize("path", ["/api/health/liveness", "/api/health/readiness"])
    def test_health_probe_routes_are_public(self, test_client, path):
        response = test_client.get(path)
        assert response.status_code == 200

    def test_protected_route_invalid_token(self, test_client):
        """Test calling protected endpoint with invalid token"""
        response = test_client.get("/api/protected", headers={"Authorization": "Bearer badtoken"})
        assert response.status_code == 401
        assert response.json()["success"] is False
        assert "Invalid token" in response.json()["message"]

    def test_protected_route_success(self, test_client, db_session):
        """Test calling protected endpoint with valid JWT token"""
        AuthenticationService.create_user(db_session, "protecteduser", "protected@test.com", "SecurePassword123!")
        token = AuthenticationService.authenticate_user(db_session, "protecteduser", "SecurePassword123!")
        
        response = test_client.get("/api/protected", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["user"]["username"] == "protecteduser"

    def test_logout_success(self, test_client, db_session):
        """Test logout endpoint with active session"""
        AuthenticationService.create_user(db_session, "logoutuser", "logout@test.com", "SecurePassword123!")
        token = AuthenticationService.authenticate_user(db_session, "logoutuser", "SecurePassword123!")
        
        # Call logout with authorization header (even though logout is technically exempt from strict reject, it clears the state)
        response = test_client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_user_can_update_own_full_name_without_changing_username(self, test_client, db_session):
        AuthenticationService.create_user(
            db_session,
            "profileuser",
            "profile@test.com",
            "SecurePassword123!",
        )
        token = AuthenticationService.authenticate_user(
            db_session,
            "profileuser",
            "SecurePassword123!",
        )

        response = test_client.put(
            "/api/auth/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "  Ahmed Mohamed Essa  "},
        )

        assert response.status_code == 200
        user = db_session.query(User).filter(User.username == "profileuser").one()
        db_session.refresh(user)
        assert user.full_name == "Ahmed Mohamed Essa"
        assert user.username == "profileuser"
        assert response.json()["data"] == {
            "id": str(user.id),
            "name": "Ahmed Mohamed Essa",
            "username": "profileuser",
        }

    def test_profile_rejects_blank_full_name(self, test_client, db_session):
        AuthenticationService.create_user(
            db_session,
            "profileuser",
            "profile@test.com",
            "SecurePassword123!",
        )
        token = AuthenticationService.authenticate_user(
            db_session,
            "profileuser",
            "SecurePassword123!",
        )

        response = test_client.put(
            "/api/auth/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"full_name": "   "},
        )

        assert response.status_code == 422

    def test_user_can_change_password_with_current_password(self, test_client, db_session):
        AuthenticationService.create_user(
            db_session,
            "passworduser",
            "password@test.com",
            "SecurePassword123!",
        )
        token = AuthenticationService.authenticate_user(
            db_session,
            "passworduser",
            "SecurePassword123!",
        )

        response = test_client.post(
            "/api/auth/profile/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "SecurePassword123!",
                "new_password": "ChangedPassword456!",
            },
        )

        assert response.status_code == 200
        user = db_session.query(User).filter(User.username == "passworduser").one()
        db_session.refresh(user)
        assert verify_password("SecurePassword123!", user.password_hash) is False
        assert verify_password("ChangedPassword456!", user.password_hash) is True
        assert AuthenticationService.authenticate_user(
            db_session,
            "passworduser",
            "ChangedPassword456!",
        )

    def test_password_change_rejects_wrong_current_password_without_writing(self, test_client, db_session):
        user = AuthenticationService.create_user(
            db_session,
            "passworduser",
            "password@test.com",
            "SecurePassword123!",
        )
        original_hash = user.password_hash
        token = AuthenticationService.authenticate_user(
            db_session,
            "passworduser",
            "SecurePassword123!",
        )

        response = test_client.post(
            "/api/auth/profile/password",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "current_password": "WrongPassword123!",
                "new_password": "ChangedPassword456!",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Current password is incorrect."
        db_session.refresh(user)
        assert user.password_hash == original_hash

    def test_password_change_rejects_reuse_and_weak_passwords(self, test_client, db_session):
        AuthenticationService.create_user(
            db_session,
            "passworduser",
            "password@test.com",
            "SecurePassword123!",
        )
        token = AuthenticationService.authenticate_user(
            db_session,
            "passworduser",
            "SecurePassword123!",
        )
        headers = {"Authorization": f"Bearer {token}"}

        reused = test_client.post(
            "/api/auth/profile/password",
            headers=headers,
            json={
                "current_password": "SecurePassword123!",
                "new_password": "SecurePassword123!",
            },
        )
        weak = test_client.post(
            "/api/auth/profile/password",
            headers=headers,
            json={
                "current_password": "SecurePassword123!",
                "new_password": "alllowercase123!",
            },
        )

        assert reused.status_code == 400
        assert "different" in reused.json()["detail"]
        assert weak.status_code == 400
        assert "uppercase" in weak.json()["detail"]


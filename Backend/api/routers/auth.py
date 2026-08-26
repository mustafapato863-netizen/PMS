"""Authentication Router
Provides login and logout endpoints.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from config import settings
from config.database import get_db
from models.schemas import (
    JWTToken,
    LoginPayload,
    PasswordChangePayload,
    ProfileUpdatePayload,
    StandardResponse,
)
from models.models import Team, User, UserTeamAssignment
from services.auth_service import (
    AuthenticationService,
    InvalidCsrfTokenError,
    RefreshTokenError,
    RefreshTokenReuseError,
)
from services.user_identity_service import UserIdentityService
from services.user_profile_service import (
    CurrentPasswordInvalidError,
    PasswordReuseError,
    UserProfileNotFoundError,
    UserProfileService,
)
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.team_identity import logical_team_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _request_origin_is_trusted(request: Request) -> bool:
    origin = request.headers.get("origin")
    if origin:
        return origin.rstrip("/") in settings.CORS_ORIGINS

    referer = request.headers.get("referer")
    if referer:
        parsed = urlsplit(referer)
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/") in settings.CORS_ORIGINS

    # Direct service calls and same-process tests do not carry browser origin
    # metadata. Production browsers send Origin on these POST requests; keep
    # the fallback for non-browser clients and local development.
    return settings.APP_ENV not in {"production", "staging"}


def _require_trusted_cookie_request(request: Request) -> None:
    if not _request_origin_is_trusted(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Untrusted authentication request origin.",
        )


def _request_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    client_host = request.client.host if request.client else None
    return user_agent, client_host


def _set_session_cookies(response: Response, tokens) -> None:
    refresh_max_age = max(1, int((tokens.refresh_expires_at - datetime.now(timezone.utc)).total_seconds()))
    cookie_kwargs = {
        "max_age": refresh_max_age,
        "secure": settings.AUTH_COOKIE_SECURE,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        tokens.refresh_token,
        httponly=True,
        path="/api/auth",
        **cookie_kwargs,
    )
    response.set_cookie(
        settings.AUTH_CSRF_COOKIE_NAME,
        tokens.csrf_token,
        httponly=False,
        path="/api/auth",
        **cookie_kwargs,
    )


def _clear_session_cookies(response: Response) -> None:
    for name in (settings.AUTH_REFRESH_COOKIE_NAME, settings.AUTH_CSRF_COOKIE_NAME):
        response.delete_cookie(
            name,
            path="/api/auth",
            domain=settings.AUTH_COOKIE_DOMAIN,
        )


def _current_user_payload(request: Request) -> dict:
    payload = getattr(request.state, "user", None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return payload


@router.post("/login", response_model=StandardResponse)
async def login(payload: LoginPayload, request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    """
    try:
        user_agent, client_host = _request_metadata(request)
        tokens = AuthenticationService.authenticate_user_with_session(
            db,
            payload.username,
            payload.password,
            remember_me=payload.remember_me,
            user_agent=user_agent,
            ip_address=client_host,
        )

        token_data = JWTToken(
            access_token=tokens.access_token,
            token_type="bearer",
            role=tokens.user.role,
            username=tokens.user.username,
            expires_in=tokens.access_expires_in,
            csrf_token=tokens.csrf_token,
        )
        _set_session_cookies(response, tokens)
        
        return StandardResponse(
            success=True,
            message="Successfully authenticated",
            data=token_data.model_dump()
        )
    except ValueError as e:
        # Check if error message indicates lockout
        if "lock" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Login error: {str(e)}"
        )


@router.post("/refresh", response_model=StandardResponse)
async def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    _require_trusted_cookie_request(request)
    refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
    user_agent, client_host = _request_metadata(request)
    try:
        tokens = AuthenticationService.rotate_refresh_token(
            db,
            refresh_token or "",
            csrf_token=request.headers.get("X-CSRF-Token"),
            user_agent=user_agent,
            ip_address=client_host,
        )
        _set_session_cookies(response, tokens)
        return StandardResponse(
            success=True,
            message="Authentication session refreshed",
            data=JWTToken(
                access_token=tokens.access_token,
                token_type="bearer",
                role=tokens.user.role,
                username=tokens.user.username,
                expires_in=tokens.access_expires_in,
                csrf_token=tokens.csrf_token,
            ).model_dump(),
        )
    except InvalidCsrfTokenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RefreshTokenReuseError:
        logger.warning("Refresh token reuse detected from %s", client_host)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is invalid.")
    except RefreshTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", response_model=StandardResponse)
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    """
    Log out the current user and invalidate the session cache.
    """
    try:
        refresh_token = request.cookies.get(settings.AUTH_REFRESH_COOKIE_NAME)
        if refresh_token:
            _require_trusted_cookie_request(request)
        payload = getattr(request.state, "user", None)
        csrf_token = request.headers.get("X-CSRF-Token")
        AuthenticationService.revoke_session(
            db,
            refresh_token=refresh_token,
            session_id=payload.get("session_id") if isinstance(payload, dict) else None,
            csrf_token=csrf_token,
        )
        if not refresh_token and isinstance(payload, dict) and not payload.get("session_id"):
            AuthenticationService.revoke_legacy_session(payload.get("user_id"))
        _clear_session_cookies(response)
        
        return StandardResponse(
            success=True,
            message="Successfully logged out"
        )
    except InvalidCsrfTokenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Logout error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during logout."
        )


@router.get("/me", response_model=StandardResponse)
async def me(request: Request, db: Session = Depends(get_db)):
    try:
        payload = _current_user_payload(request)
        user_id = payload.get("user_id")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        assignments = (
            db.query(UserTeamAssignment, Team)
            .join(Team, Team.id == UserTeamAssignment.team_id)
            .filter(UserTeamAssignment.user_id == user.id)
            .all()
        )
        accessible_teams = list(dict.fromkeys(logical_team_name(team) for _, team in assignments))
        accessible_team_levels = [
            [logical_team_name(team), level]
            for assignment, team in assignments
            for level in ([assignment.performance_level] if assignment.performance_level else PERFORMANCE_LEVELS)
        ]
        active_team_names = {
            logical_team_name(team)
            for team in db.query(Team).filter(Team.is_active.is_(True)).all()
        }
        active_team_count = len(active_team_names)
        unrestricted_teams = {
            logical_team_name(team)
            for assignment, team in assignments
            if assignment.performance_level is None
        }
        is_general_manager = user.role == "Admin" or (
            user.role == "Manager" and active_team_count > 0 and len(unrestricted_teams) >= active_team_count
        )

        return StandardResponse(
            success=True,
            message="Current user retrieved successfully",
            data={
                "id": str(user.id),
                "username": user.username,
                "name": UserIdentityService.display_name(db, user),
                "role": user.role,
                "employee_id": user.employee_id,
                "accessible_teams": accessible_teams,
                "accessible_team_levels": accessible_team_levels,
                "accessible_team_count": len(accessible_teams),
                "total_team_count": active_team_count,
                "is_general_manager": is_general_manager,
                "is_self_only": user.role == "Agent",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Me lookup error: {e}")
        return StandardResponse(success=False, message="Failed to fetch current user.")


@router.put("/profile", response_model=StandardResponse)
async def update_profile(
    payload: ProfileUpdatePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = _current_user_payload(request).get("user_id")
    try:
        user = UserProfileService(db).update_full_name(user_id, payload.full_name)
        return StandardResponse(
            success=True,
            message="Profile updated successfully",
            data={
                "id": str(user.id),
                "name": user.full_name,
                "username": user.username,
            },
        )
    except UserProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Profile update failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile.",
        ) from exc


@router.post("/profile/password", response_model=StandardResponse)
async def change_password(
    payload: PasswordChangePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    user_id = _current_user_payload(request).get("user_id")
    try:
        UserProfileService(db).change_password(
            user_id,
            payload.current_password,
            payload.new_password,
        )
        AuthenticationService.revoke_all_sessions(db, str(user_id), reason="password_changed")
        return StandardResponse(
            success=True,
            message="Password changed successfully",
        )
    except UserProfileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (CurrentPasswordInvalidError, PasswordReuseError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Password change failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password.",
        ) from exc

# --- Development endpoint to unlock a user account ---
@router.post("/unlock/{user_id}", response_model=StandardResponse)
async def unlock_user(user_id: str, db: Session = Depends(get_db)):
    """Reset failed login attempts and lockout for a user. Intended for admin use during development/testing."""
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        return StandardResponse(success=True, message="User unlocked successfully")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unlock user error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unlock user")

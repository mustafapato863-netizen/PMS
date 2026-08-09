"""Authentication Router
Provides login and logout endpoints.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from config.database import get_db
from models.schemas import (
    JWTToken,
    LoginPayload,
    PasswordChangePayload,
    ProfileUpdatePayload,
    StandardResponse,
)
from models.models import Team, User, UserTeamAssignment
from services.auth_service import AuthenticationService, redis_client
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


def _current_user_payload(request: Request) -> dict:
    payload = getattr(request.state, "user", None)
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return payload


@router.post("/login", response_model=StandardResponse)
async def login(payload: LoginPayload, db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT token.
    """
    try:
        token = AuthenticationService.authenticate_user(db, payload.username, payload.password)
        
        # Get user details for JWTToken schema
        from models.models import User
        user = db.query(User).filter(User.username == payload.username).first()
        
        token_data = JWTToken(
            access_token=token,
            token_type="bearer",
            role=user.role,
            username=user.username
        )
        
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


@router.post("/logout", response_model=StandardResponse)
async def logout(request: Request):
    """
    Log out the current user and invalidate the session cache.
    """
    try:
        # Check if token exists in request state
        if hasattr(request.state, "user"):
            user_id = request.state.user.get("user_id")
            if redis_client:
                try:
                    redis_client.delete(f"session:{user_id}")
                except Exception as ex:
                    logger.warning(f"Failed to clear session in Redis: {ex}")
        
        return StandardResponse(
            success=True,
            message="Successfully logged out"
        )
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

"""Role-Based Access Control Authorization Middleware/Service
"""

import logging
from uuid import UUID
from fastapi import Request, HTTPException, Depends
from starlette.status import HTTP_403_FORBIDDEN
from sqlalchemy.orm import Session
from config.database import get_db
from services.auth_service import redis_client
from models.models import User, RolePermission, UserTeamAssignment
from services.permission_seed import PERMISSION_MATRIX

logger = logging.getLogger(__name__)


class AuthorizationMiddleware:
    """Enforces Role-Based Access Control and team assignment constraints"""

    @staticmethod
    async def check_permission(
        db: Session,
        user_id: str,
        permission: str,
        team_id: str = None
    ) -> bool:
        """
        Check if a user has the required permission, with optional team scope check.
        """
        try:
            # 1. Fetch user role from Redis cache, fallback to database
            role = None
            if redis_client:
                try:
                    role = redis_client.get(f"session:{user_id}")
                except Exception as ex:
                    logger.warning(f"Redis error fetching session: {ex}")

            if not role:
                # Fallback to DB
                import uuid
                try:
                    u_id = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
                except ValueError:
                    return False
                user = db.query(User).filter(User.id == u_id).first()
                if not user:
                    return False
                role = user.role
                # Cache user role for 1 hour
                if redis_client:
                    try:
                        redis_client.set(f"session:{user_id}", role, ex=3600)
                    except Exception as ex:
                        logger.warning(f"Redis error caching session: {ex}")

            # 2. Check permission for the role
            # Admin has unrestricted access to everything
            if role == "Admin":
                return True

            # Check if permission is in role's permissions
            allowed_perms = PERMISSION_MATRIX.get(role, [])
            if permission not in allowed_perms:
                return False

            # 3. For team-scoped operations, verify team assignment
            if team_id:
                # Check team assignment cache in Redis
                cache_key = f"team_assignment:{user_id}:{team_id}"
                has_assignment = None
                if redis_client:
                    try:
                        cached_val = redis_client.get(cache_key)
                        if cached_val is not None:
                            has_assignment = (cached_val == "True")
                    except Exception as ex:
                        logger.warning(f"Redis error fetching team assignment: {ex}")

                if has_assignment is None:
                    # Fallback to DB
                    import uuid
                    try:
                        u_id = uuid.UUID(user_id) if isinstance(user_id, str) else user_id
                        t_id = uuid.UUID(team_id) if isinstance(team_id, str) else team_id
                    except ValueError:
                        return False
                    assignment = db.query(UserTeamAssignment).filter(
                        UserTeamAssignment.user_id == u_id,
                        UserTeamAssignment.team_id == t_id
                    ).first()
                    has_assignment = (assignment is not None)

                    # Cache result for 1 hour (3600 seconds)
                    if redis_client:
                        try:
                            redis_client.set(cache_key, str(has_assignment), ex=3600)
                        except Exception as ex:
                            logger.warning(f"Redis error caching team assignment: {ex}")

                if not has_assignment:
                    return False

            return True
        except Exception as e:
            logger.error(f"Error checking permission: {e}")
            return False


def require_permission(permission: str):
    """
    FastAPI dependency to require a specific permission.
    """
    async def dependency(request: Request, db: Session = Depends(get_db)):
        if not hasattr(request.state, "user") or not request.state.user:
            raise HTTPException(status_code=401, detail="Authentication required")

        user_payload = request.state.user
        user_id = user_payload.get("user_id")

        # Extract team_id if present in path or query
        team_id = request.path_params.get("team_id") or request.query_params.get("team_id")

        has_perm = await AuthorizationMiddleware.check_permission(
            db=db,
            user_id=user_id,
            permission=permission,
            team_id=team_id
        )

        if not has_perm:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' denied for this resource"
            )

        return user_payload

    return dependency

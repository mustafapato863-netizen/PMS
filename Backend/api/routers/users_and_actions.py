import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api.dependencies import require_role
from api.dependencies import get_current_user_scope
from config.database import get_db
from config import settings
from config.socket_config import online_user_ids
from api.middleware.rbac_middleware import require_permission
from models.models import Employee, Team, User, UserTeamAssignment
from models.schemas import StandardResponse, UserRecord, UserUpdateRecord, LoginPayload
from services.auth_service import AuthenticationService
from services.password_service import hash_password
from services.corrective_action_service import CorrectiveActionService
from services.user_identity_service import UserIdentityService
from utils.performance_levels import PERFORMANCE_LEVELS
from utils.team_identity import (
    create_management_team_identity,
    logical_team_name,
    team_level_for_performance,
)

users_router = APIRouter()


def _user_to_public_dict(db: Session, user: User) -> dict:
    online_ids = online_user_ids()
    accessible_teams = list(dict.fromkeys(
        logical_team_name(assignment.team)
        for assignment in user.team_assignments
        if assignment.team
    ))
    accessible_team_levels = [
        [logical_team_name(assignment.team), level]
        for assignment in user.team_assignments
        if assignment.team
        for level in ([assignment.performance_level] if assignment.performance_level else PERFORMANCE_LEVELS)
    ]
    return {
        "id": str(user.id),
        "name": UserIdentityService.display_name(db, user),
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "is_online": str(user.id) in online_ids,
        "last_seen_at": user.last_seen_at.isoformat() if user.last_seen_at else None,
        "accessible_teams": accessible_teams,
        "accessible_team_levels": accessible_team_levels,
        "accessible_team_count": len(accessible_teams),
        "is_general_manager": user.role == "Manager" and len(accessible_teams) > 0,
    }


def _admin_count(db: Session) -> int:
    return db.query(User).filter(User.role == "Admin").count()


def _active_teams(db: Session) -> list[Team]:
    return db.query(Team).filter(Team.is_active.is_(True)).order_by(Team.name.asc()).all()


def _linked_employee_id(db: Session, display_name: str) -> str | None:
    normalized = display_name.strip()
    if not normalized:
        return None
    try:
        employee = (
            db.query(Employee)
            .filter((Employee.employee_id == normalized) | (Employee.name == normalized))
            .first()
        )
        return employee.employee_id if employee else None
    except OperationalError:
        return None


def _replace_team_assignments(
    db: Session,
    user_id,
    team_names: list[str] | None,
    team_levels: list[tuple[str, str]] | None = None,
) -> None:
    db.query(UserTeamAssignment).filter(UserTeamAssignment.user_id == user_id).delete(synchronize_session=False)
    if not team_names and not team_levels:
        return
    teams = _active_teams(db)
    scoped_teams = {
        (logical_team_name(team).casefold(), team.team_level): team
        for team in teams
    }
    if team_levels:
        for team_name, level in dict.fromkeys(team_levels):
            logical_key = str(team_name).strip().casefold()
            desired_level = team_level_for_performance(level)
            team = scoped_teams.get((logical_key, desired_level))
            if not team and desired_level == "management":
                employee_team = scoped_teams.get((logical_key, "employee"))
                if employee_team:
                    team = create_management_team_identity(
                        db,
                        logical_team_name(employee_team),
                        region=employee_team.region,
                    )
                    scoped_teams[(logical_key, "management")] = team
            if not team:
                team = scoped_teams.get((logical_key, "employee"))
            if team:
                db.add(UserTeamAssignment(
                    id=uuid.uuid4(), user_id=user_id, team_id=team.id,
                    performance_level=level, access_level="admin", assigned_by="Admin",
                ))
        return
    for team_name in team_names:
        logical_key = str(team_name).strip().casefold()
        matching_scopes = [
            team for (name, _level), team in scoped_teams.items() if name == logical_key
        ]
        for team in matching_scopes:
            db.add(UserTeamAssignment(
                id=uuid.uuid4(),
                user_id=user_id,
                team_id=team.id,
                performance_level=None,
                access_level="admin",
                assigned_by="Admin",
            ))


def _current_user_id(request: Request) -> str | None:
    payload = getattr(request.state, "user", None) or {}
    if hasattr(payload, "get"):
        user_id = payload.get("user_id")
    else:
        user_id = getattr(payload, "user_id", None)
    if user_id:
        return user_id
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token_payload = AuthenticationService.validate_token(auth_header.split(" ", 1)[1])
            return token_payload.get("user_id")
        except Exception:
            return None
    return None


def _current_user_username(request: Request) -> str | None:
    payload = getattr(request.state, "user", None) or {}
    if hasattr(payload, "get"):
        return payload.get("username")
    return getattr(payload, "username", None)


def _auth_identity_from_request(request: Request) -> tuple[str | None, str | None]:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None, None
    try:
        token_payload = jwt.decode(
            auth_header.split(" ", 1)[1],
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return token_payload.get("user_id"), token_payload.get("username")
    except Exception:
        return None, None


def _current_auth_user_id(request: Request) -> str | None:
    user_id, _ = _auth_identity_from_request(request)
    return user_id


def _request_state_user_id(request: Request) -> str | None:
    payload = getattr(request.state, "user", None)
    if isinstance(payload, dict):
        return payload.get("user_id")
    return getattr(payload, "user_id", None)


def _current_auth_username(request: Request) -> str | None:
    _, username = _auth_identity_from_request(request)
    return username


def _payload_value(payload, key: str):
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


@users_router.get("/", response_model=StandardResponse)
async def get_users(
    db: Session = Depends(get_db),
    _user=Depends(require_permission("manage_users"))
):
    try:
        users = db.query(User).order_by(User.created_at.asc()).all()
        return StandardResponse(
            success=True,
            message="Users retrieved successfully",
            data=[_user_to_public_dict(db, u) for u in users]
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to fetch users.")

@users_router.post("/", response_model=StandardResponse)
async def create_user(
    payload: UserRecord,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("manage_users"))
):
    try:
        full_name = payload.name.strip()
        if not full_name:
            raise HTTPException(status_code=422, detail="Full name is required")
        existing_username = db.query(User).filter(User.username == payload.username.lower()).first()
        existing_email = db.query(User).filter(User.email == f"{payload.username.lower()}@pms.local").first()
        if existing_username or existing_email:
            raise HTTPException(status_code=409, detail="Username already exists")

        new_user = User(
            id=uuid.uuid4(),
            employee_id=_linked_employee_id(db, full_name),
            full_name=full_name,
            username=payload.username.lower(),
            email=f"{payload.username.lower()}@pms.local",
            password_hash=hash_password(payload.password),
            role=payload.role,
            is_active=payload.is_active,
            failed_login_attempts=0,
        )
        db.add(new_user)
        db.commit()
        if new_user.role == "Manager":
            if payload.is_general_manager:
                _replace_team_assignments(
                    db,
                    new_user.id,
                    list(dict.fromkeys(logical_team_name(team) for team in _active_teams(db))),
                )
            else:
                _replace_team_assignments(db, new_user.id, payload.accessible_teams, payload.accessible_team_levels)
            db.commit()
        db.refresh(new_user)
        return StandardResponse(
            success=True,
            message="User created successfully",
            data=_user_to_public_dict(db, new_user)
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message="Failed to create user.")

@users_router.put("/{user_id}", response_model=StandardResponse)
async def update_user_route(
    user_id: str,
    payload: UserUpdateRecord,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("manage_users"))
):
    try:
        auth_header = request.headers.get("Authorization", "")
        current_username = None
        if auth_header.startswith("Bearer "):
            try:
                current_username = jwt.decode(
                    auth_header.split(" ", 1)[1],
                    settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                ).get("username")
            except Exception:
                current_username = None
        existing = db.query(User).filter(User.id == uuid.UUID(str(user_id))).first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        # Protect Super Admin (username 'super') from being modified
        if existing.username == "super":
            raise HTTPException(status_code=400, detail="Cannot modify Super Admin account")

        updates = payload.model_dump(exclude_none=True)
        updates.pop("id", None)
        if "name" in updates:
            updates["name"] = updates["name"].strip()
            if not updates["name"]:
                raise HTTPException(status_code=422, detail="Full name is required")
        if (
            current_username and current_username == existing.username
        ) and updates.get("role") and updates["role"] != "Admin":
            raise HTTPException(status_code=400, detail="Cannot demote your own Admin account")

        if existing.role == "Admin":
            if updates.get("is_active") is False and _admin_count(db) <= 1:
                raise HTTPException(status_code=400, detail="Cannot deactivate the last Admin user")
            if updates.get("role") and updates["role"] != "Admin" and _admin_count(db) <= 1:
                raise HTTPException(status_code=400, detail="Cannot demote the last Admin user")

        if "username" in updates:
            new_username = updates["username"].lower()
            conflict = db.query(User).filter(User.username == new_username, User.id != existing.id).first()
            if conflict:
                raise HTTPException(status_code=409, detail="Username already exists")
            existing.username = new_username
            existing.email = f"{new_username}@pms.local"

        if "name" in updates:
            existing.full_name = updates["name"].strip()

        if "role" in updates:
            existing.role = updates["role"]

        if "is_active" in updates:
            existing.is_active = updates["is_active"]

        password_value = updates.get("password") or updates.get("new_password")
        if password_value:
            from services.password_service import validate_password_strength
            try:
                validate_password_strength(password_value)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            existing.password_hash = hash_password(password_value)
            from services.auth_service import AuthenticationService
            AuthenticationService.revoke_all_sessions(db, str(existing.id), reason="admin_password_changed")

        if "accessible_teams" in updates or "accessible_team_levels" in updates or "is_general_manager" in updates:
            if updates.get("is_general_manager") and existing.role == "Manager":
                _replace_team_assignments(
                    db,
                    existing.id,
                    list(dict.fromkeys(logical_team_name(team) for team in _active_teams(db))),
                )
            elif existing.role == "Manager":
                _replace_team_assignments(
                    db,
                    existing.id,
                    updates.get("accessible_teams"),
                    updates.get("accessible_team_levels"),
                )

        db.commit()
        db.refresh(existing)
        return StandardResponse(
            success=True,
            message="User updated successfully",
            data=_user_to_public_dict(db, existing)
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).exception("Failed to update user %s", user_id)
        try:
            db.rollback()
        except Exception:
            pass
        return StandardResponse(success=False, message="Failed to update user.")

@users_router.post("/{user_id}/toggle-active", response_model=StandardResponse)
async def toggle_user_active_route(
    user_id: str,
    is_active: bool,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("manage_users"))
):
    try:
        auth_header = request.headers.get("Authorization", "")
        current_username = None
        if auth_header.startswith("Bearer "):
            try:
                current_username = jwt.decode(
                    auth_header.split(" ", 1)[1],
                    settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                ).get("username")
            except Exception:
                current_username = None
        existing = db.query(User).filter(User.id == uuid.UUID(str(user_id))).first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        # Protect Super Admin from deactivation
        if existing.username == "super" and not is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate Super Admin account")

        if (
            current_username and current_username == existing.username
        ) and not is_active:
            raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

        if existing.role == "Admin" and not is_active and _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot deactivate the last Admin user")

        existing.is_active = is_active
        db.commit()
        return StandardResponse(
            success=True,
            message="User status updated successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message="Failed to update user status.")

@users_router.delete("/{user_id}", response_model=StandardResponse)
async def delete_user_route(
    user_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user=Depends(require_permission("manage_users"))
):
    try:
        auth_header = request.headers.get("Authorization", "")
        current_username = None
        if auth_header.startswith("Bearer "):
            try:
                current_username = jwt.decode(
                    auth_header.split(" ", 1)[1],
                    settings.JWT_SECRET,
                    algorithms=[settings.JWT_ALGORITHM],
                ).get("username")
            except Exception:
                current_username = None
        existing = db.query(User).filter(User.id == uuid.UUID(str(user_id))).first()
        if not existing:
            raise HTTPException(status_code=404, detail="User not found")
        # Protect Super Admin from deletion
        if existing.username == "super":
            raise HTTPException(status_code=400, detail="Cannot delete Super Admin account")

        if (
            current_username and current_username == existing.username
        ):
            raise HTTPException(status_code=400, detail="Cannot delete your own account")

        if existing.role == "Admin" and _admin_count(db) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last Admin user")

        db.delete(existing)
        db.commit()
        return StandardResponse(
            success=True,
            message="User deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message="Failed to delete user.")

@users_router.post("/login", response_model=StandardResponse)
async def login_user(payload: LoginPayload):
    try:
        # Legacy route kept for compatibility, but DB is the source of truth.
        # Users created through the admin panel are now stored in PostgreSQL.
        from config.database import SessionLocal
        db = SessionLocal()
        try:
            found = db.query(User).filter(User.username == payload.username.strip().lower()).first()
            if not found:
                return StandardResponse(success=False, message="Invalid username, password, or inactive account")

            # Legacy JSON accounts are still supported here if present.
            if found.password_hash and found.is_active:
                from services.password_service import verify_password
                if not verify_password(payload.password, found.password_hash):
                    return StandardResponse(success=False, message="Invalid username, password, or inactive account")

            user_data = _user_to_public_dict(db, found)
            return StandardResponse(
                success=True,
                message="Login successful",
                data=user_data
            )
        finally:
            db.close()
    except Exception as e:
        return StandardResponse(success=False, message="Login failed.")

actions_router = APIRouter()

@actions_router.get("/", response_model=StandardResponse)
async def get_all_corrective_actions(
    request: Request,
    db: Session = Depends(get_db),
    role: str = Depends(require_role(["Admin", "Manager", "Executive"]))
):
    try:
        actions = CorrectiveActionService(db).list_scoped(get_current_user_scope(db, request))
        return StandardResponse(
            success=True,
            message="Retrieved all corrective actions successfully",
            data=actions
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to fetch corrective actions.")


@users_router.get("/notifications", response_model=StandardResponse)
async def get_user_notifications(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = _current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        from models.models import NotificationRecipient, Notification
        from uuid import UUID
        
        recipients = (
            db.query(NotificationRecipient)
            .join(Notification, NotificationRecipient.notification_id == Notification.id)
            .filter(NotificationRecipient.user_id == UUID(user_id))
            .order_by(NotificationRecipient.created_at.desc())
            .all()
        )
        
        data = []
        for r in recipients:
            n = r.notification
            ntype = 'info'
            if n.type == 'action_recorded':
                ntype = 'action'
            elif n.type == 'data_upload':
                ntype = 'upload'
            elif n.type == 'warning':
                ntype = 'error'
            elif n.type == 'system':
                ntype = 'success'
                
            dt = r.created_at if r.created_at else n.created_at
            if dt.tzinfo is None:
                timestamp_str = dt.isoformat() + "Z"
            else:
                timestamp_str = dt.astimezone(__import__('datetime').timezone.utc).isoformat().replace("+00:00", "Z")

            data.append({
                "id": str(r.id),
                "type": ntype,
                "message": n.message,
                "timestamp": timestamp_str,
                "read": r.is_read,
                "meta": n.payload.get("created_by_name") + " - " + n.payload.get("created_by_role") if n.payload and isinstance(n.payload, dict) and n.payload.get("created_by_name") else None
            })
            
        return StandardResponse(
            success=True,
            message="Notifications retrieved successfully",
            data=data
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to fetch notifications.")


@users_router.put("/notifications/{recipient_id}/read", response_model=StandardResponse)
async def mark_notification_read(
    recipient_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = _current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        from models.models import NotificationRecipient
        from uuid import UUID
        from datetime import datetime, timezone
        
        try:
            req_uuid = UUID(recipient_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")
            
        recipient = (
            db.query(NotificationRecipient)
            .filter(
                (NotificationRecipient.id == req_uuid) | (NotificationRecipient.notification_id == req_uuid),
                NotificationRecipient.user_id == UUID(user_id)
            )
            .first()
        )
        if not recipient:
            raise HTTPException(status_code=404, detail="Notification not found")
            
        recipient.is_read = True
        recipient.read_at = datetime.now(timezone.utc)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Notification marked as read successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message="Failed to mark notification as read.")


@users_router.post("/notifications/read-all", response_model=StandardResponse)
async def mark_all_notifications_read(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = _current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        from models.models import NotificationRecipient
        from uuid import UUID
        from datetime import datetime, timezone
        
        db.query(NotificationRecipient).filter(
            NotificationRecipient.user_id == UUID(user_id),
            NotificationRecipient.is_read == False
        ).update(
            {
                "is_read": True,
                "read_at": datetime.now(timezone.utc)
            },
            synchronize_session=False
        )
        db.commit()
        
        return StandardResponse(
            success=True,
            message="All notifications marked as read successfully"
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to mark all notifications as read.")


@users_router.delete("/notifications/clear", response_model=StandardResponse)
async def clear_all_notifications(
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = _current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        from models.models import NotificationRecipient
        from uuid import UUID
        
        db.query(NotificationRecipient).filter(NotificationRecipient.user_id == UUID(user_id)).delete(synchronize_session=False)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="All notifications cleared successfully"
        )
    except Exception as e:
        return StandardResponse(success=False, message="Failed to clear notifications.")


@users_router.delete("/notifications/{recipient_id}", response_model=StandardResponse)
async def delete_notification(
    recipient_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    try:
        user_id = _current_user_id(request)
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")
        
        from models.models import NotificationRecipient
        from uuid import UUID
        
        try:
            req_uuid = UUID(recipient_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")
            
        recipient = (
            db.query(NotificationRecipient)
            .filter(
                (NotificationRecipient.id == req_uuid) | (NotificationRecipient.notification_id == req_uuid),
                NotificationRecipient.user_id == UUID(user_id)
            )
            .first()
        )
        if not recipient:
            raise HTTPException(status_code=404, detail="Notification not found")
            
        db.delete(recipient)
        db.commit()
        
        return StandardResponse(
            success=True,
            message="Notification deleted successfully"
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        return StandardResponse(success=False, message="Failed to delete notification.")

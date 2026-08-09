import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func

from config.database import SessionLocal
from models.models import Notification, NotificationRecipient, Team, User, UserTeamAssignment

logger = logging.getLogger(__name__)


class NotificationService:
    @staticmethod
    def _map_notification_type(notification_data: dict) -> tuple[str, str]:
        ntype = notification_data.get("type", "info")
        db_type = "system"
        if ntype == "action":
            db_type = "action_recorded"
        elif ntype == "upload":
            db_type = "data_upload"
        elif ntype == "error":
            db_type = "warning"
        elif ntype == "success":
            db_type = "system"

        title_map = {
            "action": "Action Assigned",
            "upload": "Data Uploaded",
            "error": "System Error",
            "success": "Operation Success",
            "info": "System Info",
        }
        return db_type, title_map.get(ntype, "Notification")

    @staticmethod
    def save_notification(notification_data: dict, db=None) -> Optional[str]:
        is_local_db = False
        if db is None:
            db = SessionLocal()
            is_local_db = True

        try:
            db_type, title = NotificationService._map_notification_type(notification_data)
            team_name = notification_data.get("team")
            teams = notification_data.get("teams") or notification_data.get("data", {}).get("teams") or []
            is_multi_team = bool(teams)

            notification = Notification(
                id=uuid.uuid4(),
                type=db_type,
                title=title,
                message=notification_data.get("message", ""),
                room="global" if is_multi_team or not team_name else f"team_{team_name}",
                payload=notification_data.get("data"),
                created_at=datetime.now(timezone.utc),
            )
            db.add(notification)
            db.flush()

            recipient_user_ids = set()

            for admin in db.query(User).filter(User.role == "Admin", User.is_active.is_(True)).all():
                recipient_user_ids.add(admin.id)

            if is_multi_team:
                affected_team_names = {str(team) for team in teams if team}
                if affected_team_names:
                    managers = (
                        db.query(User)
                        .join(UserTeamAssignment, User.id == UserTeamAssignment.user_id)
                        .join(Team, UserTeamAssignment.team_id == Team.id)
                        .filter(
                            User.role == "Manager",
                            User.is_active.is_(True),
                            func.lower(func.coalesce(Team.display_name, Team.name)).in_(
                                {name.casefold() for name in affected_team_names}
                            ),
                            Team.is_active.is_(True),
                        )
                        .distinct()
                        .all()
                    )
                    for manager in managers:
                        recipient_user_ids.add(manager.id)
            elif team_name:
                managers = (
                    db.query(User)
                    .join(UserTeamAssignment, User.id == UserTeamAssignment.user_id)
                    .join(Team, UserTeamAssignment.team_id == Team.id)
                    .filter(
                        User.role == "Manager",
                        User.is_active.is_(True),
                        func.lower(func.coalesce(Team.display_name, Team.name))
                        == str(team_name).casefold(),
                        Team.is_active.is_(True),
                    )
                    .all()
                )
                for manager in managers:
                    recipient_user_ids.add(manager.id)

            for user_id in recipient_user_ids:
                db.add(
                    NotificationRecipient(
                        id=uuid.uuid4(),
                        notification_id=notification.id,
                        user_id=user_id,
                        is_read=False,
                        created_at=datetime.now(timezone.utc),
                    )
                )

            if is_local_db:
                db.commit()
            else:
                db.flush()

            return str(notification.id)
        except Exception as exc:
            if is_local_db:
                db.rollback()
            logger.exception("Failed to save notification to database: %s", exc)
            return None
        finally:
            if is_local_db:
                db.close()

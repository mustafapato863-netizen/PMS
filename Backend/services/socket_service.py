"""
Socket.io Service
Handles socket event emission for real-time notifications.
"""

import asyncio
from datetime import datetime
from typing import Optional, Dict, Any



from config.socket_config import broadcast_notification, broadcast_action_recorded, broadcast_data_update


class SocketNotificationService:
    """Service for emitting socket notifications."""

    @staticmethod
    async def notify_file_upload(filename: str, team_name: str, status: str = 'success', teams: list[str] | None = None, details: Dict[str, Any] | None = None):
        """Emit file upload notification."""
        if status == 'success' and teams:
            team_label = "All Teams" if len(teams) > 1 else team_name
            teams_label = f" ({len(teams)} teams)" if len(teams) > 1 else ""
            msg = f"File '{filename}' uploaded successfully for {team_label}{teams_label}"
        else:
            msg = f"File '{filename}' uploaded successfully for {team_name}" if status == 'success' else f"File upload failed for '{filename}'"
        await broadcast_notification({
            'type': 'upload' if status == 'success' else 'error',
            'message': msg,
            'team': team_name,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'data': {
                'filename': filename,
                'team_name': team_name,
                'teams': teams or [],
                'status': status,
                **(details or {}),
            },
        })

    @staticmethod
    async def notify_action_assigned(employee_name: str, action_type: str, team_name: str, created_by_name: str | None = None, created_by_role: str | None = None, is_update: bool = False):
        """Emit action assigned or updated notification with meta information."""
        action_verb = "updated for" if is_update else "assigned to"
        meta = None
        if created_by_name and created_by_role:
            meta = f"By {created_by_name} ({created_by_role})"
        elif created_by_name:
            meta = f"By {created_by_name}"
        payload = {
            "type": "action",
            "message": f"{action_type} {action_verb} {employee_name} in {team_name}",
            "team": team_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "meta": meta,
            "data": {
                "employee_name": employee_name,
                "action_type": action_type,
                "team_name": team_name,
                "created_by_name": created_by_name,
                "created_by_role": created_by_role,
                "employee_id": employee_name,
            },
        }
        await broadcast_notification(payload)
        await broadcast_action_recorded(payload["data"] | {"team": team_name, "timestamp": payload["timestamp"]})

    @staticmethod
    async def notify_performance_updated(team_name: str, metric_name: str, new_value: float):
        """Emit performance data update."""
        await broadcast_data_update('performance_updated', {
            'team_name': team_name,
            'metric_name': metric_name,
            'new_value': new_value,
            'timestamp': datetime.utcnow().isoformat() + "Z",
        })

    @staticmethod
    async def notify_error(error_message: str, user_id: Optional[str] = None):
        """Emit error notification."""
        await broadcast_notification({
            'type': 'error',
            'message': error_message,
            'timestamp': datetime.utcnow().isoformat() + "Z",
            'data': {
                'user_id': user_id,
            },
        })

    @staticmethod
    async def notify_success(success_message: str, team_name: Optional[str] = None):
        """Emit success notification."""
        await broadcast_notification({
            'type': 'success',
            'message': success_message,
            'team': team_name,
            'timestamp': datetime.utcnow().isoformat() + "Z",
        })

    @staticmethod
    async def notify_info(info_message: str, team_name: Optional[str] = None):
        """Emit info notification."""
        await broadcast_notification({
            'type': 'info',
            'message': info_message,
            'team': team_name,
            'timestamp': datetime.utcnow().isoformat() + "Z",
        })

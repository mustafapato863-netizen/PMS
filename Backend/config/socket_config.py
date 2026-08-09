"""
Socket.io Configuration and Setup
Handles real-time communication for notifications and live data updates.
"""

import asyncio
import logging

try:
    from socketio import AsyncServer, AsyncNamespace
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False

    class AsyncNamespace:  # type: ignore[no-redef]
        """No-op namespace used when the optional Socket.IO package is absent."""

        def __init__(self, namespace=None):
            self.namespace = namespace

        async def enter_room(self, sid, room):
            return None

        async def leave_room(self, sid, room):
            return None

    class AsyncServer:  # type: ignore[no-redef]
        """No-op server that preserves REST imports on serverless runtimes."""

        def __init__(self, **kwargs):
            self.namespaces = []

        def register_namespace(self, namespace):
            self.namespaces.append(namespace)

        async def emit(self, *args, **kwargs):
            return None

from config import settings
from services.auth_service import AuthenticationService
from services.notification_service import NotificationService
from services.user_presence_service import UserPresenceService

logger = logging.getLogger(__name__)

if not SOCKETIO_AVAILABLE:
    logger.warning("python-socketio is unavailable; real-time events are disabled.")

SOCKETIO_ENABLED = SOCKETIO_AVAILABLE and settings.PMS_REALTIME_MODE == "in_process"
if SOCKETIO_AVAILABLE and not SOCKETIO_ENABLED:
    logger.info("Socket.IO real-time events are disabled by PMS_REALTIME_MODE.")

# Create global Socket.io instance
sio = AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=list(settings.CORS_ORIGINS),
    ping_timeout=60,
    ping_interval=25,
    client_manager=None,
)

# Track connected clients
connected_clients = {}


def online_user_ids() -> set[str]:
    return {
        str(client["user_id"])
        for client in connected_clients.values()
        if client.get("user_id")
    }


class NotificationNamespace(AsyncNamespace):
    """Handle notification events."""

    async def on_connect(self, sid, environ, auth=None):
        """Client connected."""
        token = auth.get("token") if isinstance(auth, dict) else None
        if not token:
            logger.warning("Rejected unauthenticated socket connection: %s", sid)
            return False
        try:
            payload = AuthenticationService.validate_token(token)
            user_id = str(payload["user_id"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Rejected socket connection with invalid token: %s", sid)
            return False

        was_online = user_id in online_user_ids()
        connected_clients[sid] = {
            'sid': sid,
            'user_id': user_id,
            'timestamp': __import__('datetime').datetime.now(),
            'teams': set(),
            'rooms': {'global'},
            'global_subscriber': True,
            'role': payload.get('role'),
        }
        await self.enter_room(sid, 'global')
        if not was_online:
            await sio.emit(
                'presence_updated',
                {'user_id': user_id, 'is_online': True},
                room='admin',
                namespace='/notifications',
            )
        logger.info("Client %s connected. Total: %s", sid, len(connected_clients))
        return None

    async def on_disconnect(self, sid):
        """Client disconnected."""
        client = connected_clients.pop(sid, None)
        user_id = str(client["user_id"]) if client and client.get("user_id") else None
        if user_id and user_id not in online_user_ids():
            last_seen_at = await asyncio.to_thread(
                UserPresenceService.record_last_seen,
                user_id,
            )
            await sio.emit(
                'presence_updated',
                {
                    'user_id': user_id,
                    'is_online': False,
                    'last_seen_at': last_seen_at.isoformat() if last_seen_at else None,
                },
                room='admin',
                namespace='/notifications',
            )
        logger.info("Client %s disconnected. Total: %s", sid, len(connected_clients))

    async def on_join_room(self, sid, data):
        """Join a socket room."""
        room = data.get('room')
        if not room or sid not in connected_clients:
            return
        await self.enter_room(sid, room)
        if 'rooms' not in connected_clients[sid]:
            connected_clients[sid]['rooms'] = set()
        connected_clients[sid]['rooms'].add(room)
        logger.info("Client %s joined room: %s", sid, room)

    async def on_leave_room(self, sid, data):
        """Leave a socket room."""
        room = data.get('room')
        if not room or sid not in connected_clients:
            return
        await self.leave_room(sid, room)
        if 'rooms' in connected_clients[sid]:
            connected_clients[sid]['rooms'].discard(room)
        logger.info("Client %s left room: %s", sid, room)

    async def on_subscribe_team(self, sid, data):
        """Subscribe to team notifications."""
        team_names = data.get('team_names')
        team_name = data.get('team_name')
        is_global = bool(data.get('global'))
        if sid not in connected_clients:
            return

        client = connected_clients[sid]
        if client.get('role') == 'Admin':
            await self.enter_room(sid, 'admin')
            if 'rooms' not in client:
                client['rooms'] = set()
            client['rooms'].add('admin')

        client['global_subscriber'] = is_global or (not team_name and not team_names)
        if team_names:
            client['teams'] = set(team_names)
            for t in team_names:
                await self.enter_room(sid, f"team_{t}")
                if 'rooms' not in client:
                    client['rooms'] = set()
                client['rooms'].add(f"team_{t}")
            logger.info("Client %s subscribed to teams: %s", sid, team_names)
        elif team_name:
            client['teams'] = {team_name}
            client['global_subscriber'] = False
            await self.enter_room(sid, f"team_{team_name}")
            if 'rooms' not in client:
                client['rooms'] = set()
            client['rooms'].add(f"team_{team_name}")
            logger.info("Client %s subscribed to team: %s", sid, team_name)
        elif is_global:
            client['teams'] = set()
            logger.info("Client %s subscribed globally", sid)


# Register namespace
sio.register_namespace(NotificationNamespace('/notifications'))


def save_notification_to_db(notification_data: dict, db=None) -> str | None:
    """Backward-compatible wrapper around NotificationService."""
    return NotificationService.save_notification(notification_data, db=db)


async def broadcast_notification(notification_data):
    """
    Broadcast notification to all connected clients.
    
    Args:
        notification_data: Dict with keys:
            - type: 'upload' | 'action' | 'error' | 'success' | 'info'
            - message: str
            - team: str (optional, for team-specific notifications)
    """
    db_id = save_notification_to_db(notification_data)
    if db_id:
        notification_data['id'] = db_id

    if not connected_clients:
        logger.info("Notification persisted without active socket clients.")
        return

    team_filter = notification_data.get('team')
    team_filters = set(notification_data.get('teams') or [])

    for sid, client_info in connected_clients.items():
        is_admin = client_info.get('role') == 'Admin' or 'admin' in client_info.get('rooms', set())
        
        if is_admin:
            pass
        elif team_filters:
            client_teams = client_info.get('teams') or set()
            if client_teams.isdisjoint(team_filters) and not client_info.get('global_subscriber'):
                continue
        elif team_filter:
            client_teams = client_info.get('teams') or set()
            if team_filter not in client_teams and not client_info.get('global_subscriber'):
                continue
        elif not client_info.get('global_subscriber'):
            continue

        try:
            await sio.emit('notification', notification_data, to=sid, namespace='/notifications')
        except Exception as e:
            logger.exception("Failed to send notification to %s: %s", sid, e)


async def broadcast_action_recorded(action_data):
    """Broadcast corrective-action updates to all authorized clients."""
    if not connected_clients:
        return

    team_filter = action_data.get('team')

    for sid, client_info in connected_clients.items():
        is_admin = client_info.get('role') == 'Admin' or 'admin' in client_info.get('rooms', set())
        
        if is_admin:
            pass
        elif team_filter:
            client_teams = client_info.get('teams') or set()
            if team_filter not in client_teams and not client_info.get('global_subscriber'):
                continue
        elif not client_info.get('global_subscriber'):
            continue

        try:
            await sio.emit('action_recorded', action_data, to=sid, namespace='/notifications')
        except Exception as e:
            logger.exception("Failed to send action record to %s: %s", sid, e)


async def broadcast_data_update(event_type, data):
    """
    Broadcast data update to all connected clients.
    
    Args:
        event_type: str - Type of data update (e.g., 'performance_updated')
        data: dict - Update data
    """
    if not connected_clients:
        return

    for sid in connected_clients.keys():
        try:
            await sio.emit(event_type, data, to=sid, namespace='/notifications')
        except Exception as e:
            logger.exception("Failed to send update to %s: %s", sid, e)

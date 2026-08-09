from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

import pytest

from config.socket_config import (
    NotificationNamespace,
    connected_clients,
    online_user_ids,
    sio,
)
from services.auth_service import AuthenticationService
from services.user_presence_service import UserPresenceService


@pytest.fixture(autouse=True)
def clear_connected_clients():
    connected_clients.clear()
    yield
    connected_clients.clear()


@pytest.mark.asyncio
async def test_presence_tracks_multiple_connections_for_the_same_user(monkeypatch):
    monkeypatch.setattr(
        AuthenticationService,
        "validate_token",
        lambda token: {"user_id": "user-1", "role": "Admin"},
    )
    emit = AsyncMock()
    seen_at = datetime(2026, 7, 28, 12, 30, tzinfo=timezone.utc)
    record_last_seen = Mock(return_value=seen_at)
    monkeypatch.setattr(sio, "emit", emit)
    monkeypatch.setattr(
        UserPresenceService,
        "record_last_seen",
        record_last_seen,
    )
    namespace = NotificationNamespace("/notifications")
    namespace.enter_room = AsyncMock()

    assert await namespace.on_connect("sid-1", {}, {"token": "valid"}) is None
    assert await namespace.on_connect("sid-2", {}, {"token": "valid"}) is None
    assert online_user_ids() == {"user-1"}
    assert emit.await_count == 1

    await namespace.on_disconnect("sid-1")
    assert online_user_ids() == {"user-1"}
    assert emit.await_count == 1
    record_last_seen.assert_not_called()

    await namespace.on_disconnect("sid-2")
    assert online_user_ids() == set()
    assert emit.await_count == 2
    record_last_seen.assert_called_once_with("user-1")
    assert emit.await_args.args == (
        "presence_updated",
        {
            "user_id": "user-1",
            "is_online": False,
            "last_seen_at": "2026-07-28T12:30:00+00:00",
        },
    )


@pytest.mark.asyncio
async def test_presence_rejects_unauthenticated_connections():
    namespace = NotificationNamespace("/notifications")

    assert await namespace.on_connect("sid-1", {}, None) is False
    assert connected_clients == {}

from unittest.mock import MagicMock, patch

import redis

from services.redis_provider import LazyRedisClient


def test_redis_provider_does_not_connect_during_construction():
    with patch("services.redis_provider.redis.Redis.from_url") as from_url:
        client = LazyRedisClient(
            "redis://example.invalid:6379/0",
            socket_timeout=0.1,
            retry_interval=30,
        )

        from_url.assert_not_called()
        assert client is not None


def test_redis_provider_connects_once_on_first_use():
    redis_connection = MagicMock()
    redis_connection.ping.return_value = True

    with patch(
        "services.redis_provider.redis.Redis.from_url",
        return_value=redis_connection,
    ) as from_url:
        client = LazyRedisClient(
            "redis://localhost:6379/0",
            socket_timeout=0.1,
            retry_interval=30,
        )

        assert bool(client) is True
        assert bool(client) is True

    from_url.assert_called_once()
    redis_connection.ping.assert_called_once()


def test_redis_provider_uses_retry_window_after_failure():
    with patch(
        "services.redis_provider.redis.Redis.from_url",
        side_effect=OSError("connection refused"),
    ) as from_url:
        client = LazyRedisClient(
            "redis://localhost:6379/0",
            socket_timeout=0.1,
            retry_interval=30,
        )

        assert bool(client) is False
        assert bool(client) is False

    from_url.assert_called_once()


def test_redis_provider_enters_retry_window_after_command_failure():
    failed_connection = MagicMock()
    failed_connection.ping.return_value = True
    failed_connection.get.side_effect = redis.ConnectionError("connection lost")

    with patch(
        "services.redis_provider.redis.Redis.from_url",
        return_value=failed_connection,
    ) as from_url:
        client = LazyRedisClient(
            "redis://localhost:6379/0",
            socket_timeout=0.1,
            retry_interval=30,
        )

        try:
            client.get("key")
        except redis.ConnectionError:
            pass

        assert bool(client) is False

    from_url.assert_called_once()

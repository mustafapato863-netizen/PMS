"""Lazy, shared Redis connectivity with a bounded fallback window.

Importing the application must not depend on Redis being reachable. The
provider connects only when a Redis-backed feature is actually used and avoids
repeating connection attempts until the retry window has elapsed.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import redis

from config import settings

logger = logging.getLogger(__name__)


class LazyRedisClient:
    """Redis-compatible proxy that connects on first use, never at import time."""

    def __init__(
        self,
        url: str,
        *,
        socket_timeout: float,
        retry_interval: float,
    ) -> None:
        self._url = url.strip()
        self._socket_timeout = socket_timeout
        self._retry_interval = retry_interval
        self._client: redis.Redis | None = None
        self._retry_after = 0.0
        self._lock = threading.Lock()

    def _connect(self) -> redis.Redis | None:
        if self._client is not None:
            return self._client
        if not self._url or time.monotonic() < self._retry_after:
            return None

        with self._lock:
            if self._client is not None:
                return self._client
            if time.monotonic() < self._retry_after:
                return None

            try:
                client = redis.Redis.from_url(
                    self._url,
                    decode_responses=True,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_timeout,
                )
                client.ping()
                self._client = client
                logger.info("Redis connection established.")
                return client
            except Exception as exc:
                self._retry_after = time.monotonic() + self._retry_interval
                logger.warning(
                    "Redis unavailable; using application fallbacks for %.0f seconds: %s",
                    self._retry_interval,
                    exc,
                )
                return None

    def __bool__(self) -> bool:
        return self._connect() is not None

    def _mark_unavailable(self) -> None:
        with self._lock:
            self._client = None
            self._retry_after = time.monotonic() + self._retry_interval

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        client = self._connect()
        if client is None:
            raise redis.ConnectionError("Redis is unavailable")
        attribute = getattr(client, name)
        if not isinstance(attribute, Callable):
            return attribute

        def guarded_call(*args, **kwargs):
            try:
                return attribute(*args, **kwargs)
            except redis.RedisError:
                self._mark_unavailable()
                raise

        return guarded_call

    def reset(self) -> None:
        """Drop the current connection and retry window (primarily for tests)."""
        with self._lock:
            client = self._client
            self._client = None
            self._retry_after = 0.0
        if client is not None:
            try:
                client.close()
            except Exception:
                logger.debug("Redis client close failed", exc_info=True)


redis_client = LazyRedisClient(
    settings.REDIS_URL,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
    retry_interval=settings.REDIS_RETRY_INTERVAL_SECONDS,
)

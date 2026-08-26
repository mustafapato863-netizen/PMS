"""Redis Caching Service
Provides get and set helpers for performance and team data caches,
falling back to in-memory cache when Redis is unavailable.
"""

import json
import logging
from typing import Any
from services.redis_provider import redis_client
from services.session_cache import SessionCache

logger = logging.getLogger(__name__)

# Process-level in-memory cache fallback (128 MB limit)
in_memory_cache = SessionCache(max_bytes=128 * 1024 * 1024)


class CacheService:
    """Enterprise Redis Caching Service (with in-memory fallback)"""

    @staticmethod
    def get_json(key: str, *, cache_type: str = "response") -> Any | None:
        """Read a versioned JSON response without exposing the full key in logs."""
        if redis_client:
            try:
                value = redis_client.get(key)
                if value is not None:
                    logger.info("cache hit", extra={"cache_type": cache_type})
                    return json.loads(value)
                logger.info("cache miss", extra={"cache_type": cache_type})
            except Exception as exc:
                logger.warning("Redis response cache read failed: %s", exc)
        return in_memory_cache.get_session(key)

    @staticmethod
    def set_json(key: str, value: Any, *, ttl: int, cache_type: str = "response") -> bool:
        """Write a versioned JSON response and retain the local fallback."""
        if redis_client:
            try:
                redis_client.set(key, json.dumps(value, separators=(",", ":")), ex=ttl)
                logger.info("cache set", extra={"cache_type": cache_type, "ttl": ttl})
            except Exception as exc:
                logger.warning("Redis response cache write failed: %s", exc)
        in_memory_cache.set_session(key, value, ttl)
        return True

    @staticmethod
    def get_performance_cache(employee_id: str, month: str, year: int) -> dict:
        """Retrieve performance record from cache"""
        key = f"performance:{employee_id}:{month}:{year}"
        if redis_client:
            try:
                val = redis_client.get(key)
                if val:
                    logger.info("cache hit", extra={"cache_key": key, "cache_type": "performance"})
                    return json.loads(val)
                logger.info("cache miss", extra={"cache_key": key, "cache_type": "performance"})
            except Exception as e:
                logger.warning(f"Redis get performance cache error: {e}")
        return in_memory_cache.get_session(key)

    @staticmethod
    def set_performance_cache(employee_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set performance record in cache"""
        key = f"performance:{employee_id}:{month}:{year}"
        if redis_client:
            try:
                redis_client.set(key, json.dumps(data), ex=ttl)
                logger.info("cache set", extra={"cache_key": key, "cache_type": "performance", "ttl": ttl})
            except Exception as e:
                logger.warning(f"Redis set performance cache error: {e}")
        in_memory_cache.set_session(key, data, ttl)
        return True

    @staticmethod
    def get_team_performance_cache(team_id: str, month: str, year: int) -> dict:
        """Retrieve team performance from cache"""
        key = f"team_performance:{team_id}:{month}:{year}"
        if redis_client:
            try:
                val = redis_client.get(key)
                if val:
                    logger.info("cache hit", extra={"cache_key": key, "cache_type": "team_performance"})
                    return json.loads(val)
                logger.info("cache miss", extra={"cache_key": key, "cache_type": "team_performance"})
            except Exception as e:
                logger.warning(f"Redis get team performance cache error: {e}")
        return in_memory_cache.get_session(key)

    @staticmethod
    def set_team_performance_cache(team_id: str, month: str, year: int, data: dict, ttl: int = 3600) -> bool:
        """Set team performance in cache"""
        key = f"team_performance:{team_id}:{month}:{year}"
        if redis_client:
            try:
                redis_client.set(key, json.dumps(data), ex=ttl)
                logger.info("cache set", extra={"cache_key": key, "cache_type": "team_performance", "ttl": ttl})
            except Exception as e:
                logger.warning(f"Redis set team performance cache error: {e}")
        in_memory_cache.set_session(key, data, ttl)
        return True

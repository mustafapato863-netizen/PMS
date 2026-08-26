"""Cache Invalidation Service
Manages deleting keys and broadcasting pub/sub notifications for cache invalidation.
Also invalidates the in-memory cache fallback.
"""

import json
import logging
import threading
from services.cache_service import redis_client, in_memory_cache

logger = logging.getLogger(__name__)
_fallback_data_version = 0
_fallback_data_version_lock = threading.Lock()
_fallback_config_version = 0
_fallback_config_version_lock = threading.Lock()


class CacheInvalidationService:
    """Handles Redis and in-memory cache invalidation"""

    @staticmethod
    def invalidate_performance_record(employee_id: str, month: str, year: int) -> None:
        """Invalidate performance record keys in both caches"""
        key = f"performance:{employee_id}:{month}:{year}"
        in_memory_cache.invalidate_session(key)
        if not redis_client:
            return
        try:
            redis_client.delete(key)
            message = {
                "action": "invalidate",
                "type": "performance",
                "employee_id": str(employee_id),
                "month": month,
                "year": int(year)
            }
            redis_client.publish("cache_invalidation", json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to invalidate performance record cache: {e}")

    @staticmethod
    def flush_all() -> None:
        """Compatibility name for a safe namespace invalidation."""
        in_memory_cache.invalidate_by_prefix("")
        CacheInvalidationService.bump_data_version()

    @staticmethod
    def bump_data_version() -> int:
        """Publish a post-commit data version without evicting auth/session keys."""

        global _fallback_data_version
        if redis_client:
            try:
                version = int(redis_client.incr("pms:version:data"))
                redis_client.publish(
                    "cache_invalidation",
                    json.dumps({"action": "version_bump", "type": "data", "version": version}),
                )
                return version
            except Exception as exc:
                logger.warning("Failed to bump shared data version: %s", exc)
        with _fallback_data_version_lock:
            _fallback_data_version += 1
            return _fallback_data_version

    @staticmethod
    def get_data_version() -> int:
        if redis_client:
            try:
                value = redis_client.get("pms:version:data")
                return int(value or 0)
            except Exception as exc:
                logger.warning("Failed to read shared data version: %s", exc)
        with _fallback_data_version_lock:
            return _fallback_data_version

    @staticmethod
    def bump_config_version() -> int:
        """Publish a configuration version after a committed configuration change."""

        global _fallback_config_version
        if redis_client:
            try:
                version = int(redis_client.incr("pms:version:config"))
                redis_client.publish(
                    "cache_invalidation",
                    json.dumps({"action": "version_bump", "type": "config", "version": version}),
                )
                return version
            except Exception as exc:
                logger.warning("Failed to bump shared config version: %s", exc)
        with _fallback_config_version_lock:
            _fallback_config_version += 1
            return _fallback_config_version

    @staticmethod
    def get_config_version() -> int:
        if redis_client:
            try:
                value = redis_client.get("pms:version:config")
                return int(value or 0)
            except Exception as exc:
                logger.warning("Failed to read shared config version: %s", exc)
        with _fallback_config_version_lock:
            return _fallback_config_version

    @staticmethod
    def invalidate_team_config(team_id: str, month: str = None, year: int = None) -> None:
        """Invalidate team config/performance keys in both caches"""
        if month and year:
            key = f"team_performance:{team_id}:{month}:{year}"
            in_memory_cache.invalidate_session(key)
        else:
            key = None
            in_memory_cache.invalidate_by_prefix(f"team_performance:{team_id}:")
        if not redis_client:
            return
        try:
            keys_to_delete = []
            if key:
                keys_to_delete.append(key)
            else:
                for k in redis_client.scan_iter(match=f"team_performance:{team_id}:*"):
                    keys_to_delete.append(k)
            if keys_to_delete:
                redis_client.delete(*keys_to_delete)
            message = {
                "action": "invalidate",
                "type": "team",
                "team_id": str(team_id),
                "month": month,
                "year": int(year) if year else None
            }
            redis_client.publish("cache_invalidation", json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to invalidate team config cache: {e}")

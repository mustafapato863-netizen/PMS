"""Cache Invalidation Service
Manages deleting keys and broadcasting pub/sub notifications for cache invalidation.
Also invalidates the in-memory cache fallback.
"""

import json
import logging
from services.cache_service import redis_client, in_memory_cache

logger = logging.getLogger(__name__)


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
        """Invalidate all cached entries in both Redis and in-memory cache."""
        in_memory_cache.invalidate_by_prefix("")
        if redis_client:
            try:
                redis_client.flushdb()
            except Exception as e:
                logger.warning(f"Failed to flush Redis cache: {e}")

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

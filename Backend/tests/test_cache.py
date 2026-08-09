"""Unit and Integration Tests for Caching layers (Redis cache, Invalidation, and LRU Session Cache)
"""

import time
import pytest
from unittest.mock import patch, MagicMock
import redis

from services.cache_service import CacheService
from services.cache_invalidation_service import CacheInvalidationService
from services.session_cache import SessionCache


class TestRedisCacheService:
    """Tests for Redis CacheService operations and fallbacks"""

    @patch("services.cache_service.redis_client")
    def test_get_performance_cache_hit(self, mock_redis):
        """Verify performance cache hit reads and decodes JSON correctly"""
        mock_redis.get.return_value = '{"employee_id": "test_emp", "score": 95.0}'
        
        result = CacheService.get_performance_cache("test_emp", "January", 2026)
        
        assert result is not None
        assert result["employee_id"] == "test_emp"
        assert result["score"] == 95.0
        mock_redis.get.assert_called_once_with("performance:test_emp:January:2026")

    @patch("services.cache_service.redis_client")
    def test_get_performance_cache_miss(self, mock_redis):
        """Verify cache miss returns None"""
        mock_redis.get.return_value = None
        
        result = CacheService.get_performance_cache("test_emp", "January", 2026)
        
        assert result is None

    @patch("services.cache_service.redis_client")
    def test_set_performance_cache(self, mock_redis):
        """Verify set performance cache calls Redis correctly"""
        data = {"score": 95.0}
        
        success = CacheService.set_performance_cache("test_emp", "January", 2026, data, ttl=1800)
        
        assert success is True
        mock_redis.set.assert_called_once_with("performance:test_emp:January:2026", '{"score": 95.0}', ex=1800)

    @patch("services.cache_service.redis_client")
    def test_redis_connection_fallback_on_get(self, mock_redis):
        """Verify transparent fallback to in-memory cache when Redis get raises ConnectionError"""
        # First set via in-memory (simulate earlier cache write)
        from services.cache_service import in_memory_cache
        in_memory_cache.set_session("performance:fallback_get:January:2026", {"score": 95.0}, 3600)
        mock_redis.get.side_effect = redis.ConnectionError("Connection refused")
        
        result = CacheService.get_performance_cache("fallback_get", "January", 2026)
        assert result == {"score": 95.0}

    @patch("services.cache_service.redis_client")
    def test_redis_connection_fallback_on_set(self, mock_redis):
        """Verify transparent fallback to in-memory cache when Redis set raises ConnectionError"""
        mock_redis.set.side_effect = redis.ConnectionError("Connection refused")
        
        success = CacheService.set_performance_cache("fallback_set", "January", 2026, {"score": 95.0})
        assert success is True


class TestCacheInvalidationService:
    """Tests for CacheInvalidationService delete & publish operations"""

    @patch("services.cache_invalidation_service.redis_client")
    def test_invalidate_performance_record(self, mock_redis):
        """Verify invalidation deletes key and publishes cache_invalidation notification"""
        CacheInvalidationService.invalidate_performance_record("test_emp", "January", 2026)
        
        mock_redis.delete.assert_called_once_with("performance:test_emp:January:2026")
        mock_redis.publish.assert_called_once()
        
        # Verify publish argument contains invalidation payload details
        channel, payload_str = mock_redis.publish.call_args[0]
        assert channel == "cache_invalidation"
        assert "invalidate" in payload_str
        assert "test_emp" in payload_str

    @patch("services.cache_invalidation_service.redis_client")
    def test_invalidate_team_config_specific(self, mock_redis):
        """Verify team config invalidation for a specific month deletes the correct key"""
        CacheInvalidationService.invalidate_team_config("team_123", "January", 2026)
        
        mock_redis.delete.assert_called_once_with("team_performance:team_123:January:2026")
        mock_redis.publish.assert_called_once()


class TestSessionCache:
    """Tests for thread-safe in-memory SessionCache with LRU and TTL"""

    def test_set_and_get_cache_success(self):
        """Verify standard get and set flow under expiration limit"""
        cache = SessionCache(max_bytes=1000)
        cache.set_session("user_role:123", "Admin", ttl=10)
        
        assert cache.get_session("user_role:123") == "Admin"

    def test_cache_expiration(self):
        """Verify that expired items return None and get cleaned up"""
        cache = SessionCache(max_bytes=1000)
        cache.set_session("expired_key", "SomeData", ttl=-1)  # already expired
        
        assert cache.get_session("expired_key") is None
        assert "expired_key" not in cache.cache

    def test_lru_eviction(self):
        """Verify that adding entries beyond the capacity limit evicts the least recently used item"""
        # Set max_bytes to a low threshold to trigger eviction
        cache = SessionCache(max_bytes=275)
        
        # Keys and values will take some bytes (approx 90 bytes each)
        cache.set_session("key1", "val1", ttl=60)
        cache.set_session("key2", "val2", ttl=60)
        
        # Query key2 first, then key1. This makes key1 the Most Recently Used (MRU)
        # and key2 the Least Recently Used (LRU).
        assert cache.get_session("key2") is not None
        assert cache.get_session("key1") is not None
        
        # This insertion should force eviction of key2 (the LRU).
        cache.set_session("key3", "val3" * 5, ttl=60)  # larger size
        
        assert cache.get_session("key2") is None  # evicted
        assert cache.get_session("key1") is not None  # kept because accessed recently
        assert cache.get_session("key3") is not None  # newly added

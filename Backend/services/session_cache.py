"""In-Memory Session Cache
Thread-safe LRU dictionary-based cache with TTL tracking and a 1 GB capacity constraint.
"""

import time
import logging
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)


class SessionCache:
    """Thread-safe in-memory cache with TTL and LRU eviction (1 GB capacity limit)"""

    def __init__(self, max_bytes: int = 1024 * 1024 * 1024):  # 1 GB default
        self.max_bytes = max_bytes
        self.cache = OrderedDict()  # key -> (value, expiry_time, size_bytes)
        self.current_bytes = 0
        self.lock = Lock()

    def _get_size(self, key, value) -> int:
        """Estimate size of entry in bytes"""
        import sys
        import json
        try:
            size = sys.getsizeof(key)
            if isinstance(value, (dict, list)):
                size += len(json.dumps(value))
            elif hasattr(value, "model_dump"):
                size += len(json.dumps(value.model_dump()))
            else:
                size += sys.getsizeof(value)
            return size
        except Exception:
            return sys.getsizeof(key) + sys.getsizeof(value)

    def get_session(self, key):
        """Retrieve a session/config from cache if it exists and is not expired"""
        with self.lock:
            if key not in self.cache:
                return None

            value, expiry, size = self.cache[key]

            # Check expiration
            if time.time() > expiry:
                self._delete_entry(key)
                return None

            # Move to end to mark as recently used
            self.cache.move_to_end(key)
            return value

    def set_session(self, key, value, ttl: int) -> None:
        """Set a session/config with a specific TTL (in seconds) and enforce LRU eviction if size limit exceeded"""
        with self.lock:
            # If key already exists, delete it first to update size correctly
            if key in self.cache:
                self._delete_entry(key)

            expiry = time.time() + ttl
            size = self._get_size(key, value)

            # If the entry itself is larger than the maximum allowed size, do not cache
            if size > self.max_bytes:
                logger.warning(f"Cache entry {key} is too large ({size} bytes) for the cache (max {self.max_bytes} bytes). Not caching.")
                return

            # Evict LRU entries until we have enough space
            while self.current_bytes + size > self.max_bytes and self.cache:
                lru_key = next(iter(self.cache))
                self._delete_entry(lru_key)

            self.cache[key] = (value, expiry, size)
            self.current_bytes += size

    def invalidate_session(self, key) -> None:
        """Explicitly invalidate a key"""
        with self.lock:
            if key in self.cache:
                self._delete_entry(key)

    def invalidate_by_prefix(self, prefix: str) -> None:
        """Invalidate all keys starting with the given prefix"""
        with self.lock:
            keys_to_delete = [k for k in self.cache if k.startswith(prefix)]
            for k in keys_to_delete:
                self._delete_entry(k)

    def _delete_entry(self, key) -> None:
        """Helper to delete entry and update current size (must be called with lock)"""
        _, _, size = self.cache.pop(key)
        self.current_bytes -= size

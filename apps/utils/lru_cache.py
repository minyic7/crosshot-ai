"""LRU Cache with TTL support for URL deduplication."""

from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Lock
from typing import Optional


class LRUCache:
    """Thread-safe LRU cache with optional TTL.

    Designed for URL deduplication in long-running crawlers.
    Automatically evicts oldest entries when capacity is reached.

    Example:
        cache = LRUCache(max_size=10000, ttl_seconds=3600)

        if url not in cache:
            cache.add(url)
            # process url...
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: Optional[int] = None):
        """Initialize LRU cache.

        Args:
            max_size: Maximum number of entries. When exceeded, oldest entries are evicted.
            ttl_seconds: Optional TTL in seconds. Entries older than this are considered expired.
        """
        self._max_size = max_size
        self._ttl = timedelta(seconds=ttl_seconds) if ttl_seconds else None
        self._cache: OrderedDict[str, datetime] = OrderedDict()
        self._lock = Lock()

    def __contains__(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            if key not in self._cache:
                return False

            # Check TTL if configured
            if self._ttl:
                added_time = self._cache[key]
                if datetime.utcnow() - added_time > self._ttl:
                    # Expired - remove and return False
                    del self._cache[key]
                    return False

            # Move to end (most recently accessed)
            self._cache.move_to_end(key)
            return True

    def add(self, key: str) -> None:
        """Add key to cache. Evicts oldest if at capacity."""
        with self._lock:
            now = datetime.utcnow()

            if key in self._cache:
                # Update timestamp and move to end
                self._cache[key] = now
                self._cache.move_to_end(key)
                return

            # Evict oldest entries if at capacity
            while len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            self._cache[key] = now

    def clear(self) -> None:
        """Clear all entries."""
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        """Return number of entries (including possibly expired ones)."""
        return len(self._cache)

    @property
    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            now = datetime.utcnow()
            expired_count = 0

            if self._ttl:
                for added_time in self._cache.values():
                    if now - added_time > self._ttl:
                        expired_count += 1

            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl.total_seconds() if self._ttl else None,
                "expired_count": expired_count,
            }

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns number removed."""
        if not self._ttl:
            return 0

        with self._lock:
            now = datetime.utcnow()
            expired_keys = [
                key for key, added_time in self._cache.items()
                if now - added_time > self._ttl
            ]

            for key in expired_keys:
                del self._cache[key]

            return len(expired_keys)

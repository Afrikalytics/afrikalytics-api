"""Redis cache service for public endpoints."""

import json
import logging
from typing import Optional

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None


def get_redis() -> Optional[redis.Redis]:
    """Get Redis connection (lazy init, returns None if unavailable)."""
    global _redis_client
    if _redis_client is None:
        try:
            settings = get_settings()
            _redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            _redis_client.ping()
        except Exception as e:
            logger.warning(f"Redis unavailable, caching disabled: {e}")
            _redis_client = None
    return _redis_client


def cache_get(key: str) -> Optional[dict]:
    """Get cached value by key."""
    client = get_redis()
    if client is None:
        return None
    try:
        data = client.get(key)
        return json.loads(data) if data else None
    except Exception as e:
        logger.warning(f"Cache get failed: {e}")
        return None


def cache_set(key: str, value, ttl: int = 300) -> None:
    """Set cached value with TTL in seconds (default 5 min)."""
    client = get_redis()
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception as e:
        logger.warning(f"Cache set failed: {e}")


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching pattern (for cache invalidation)."""
    client = get_redis()
    if client is None:
        return
    try:
        keys = client.keys(pattern)
        if keys:
            client.delete(*keys)
    except Exception as e:
        logger.warning(f"Cache delete failed: {e}")

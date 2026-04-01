"""Redis cache service for public endpoints."""

import json
import logging
import time
from typing import Optional

import redis

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_last_connect_attempt: float = 0.0
_RETRY_INTERVAL_SECONDS: float = 30.0


def get_redis() -> Optional[redis.Redis]:
    """Get Redis connection (lazy init, retries every 30s if unavailable)."""
    global _redis_client, _last_connect_attempt

    if _redis_client is not None:
        return _redis_client

    now = time.monotonic()
    if now - _last_connect_attempt < _RETRY_INTERVAL_SECONDS:
        return None

    _last_connect_attempt = now
    try:
        settings = get_settings()
        client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_timeout=2,
            socket_connect_timeout=2,
        )
        client.ping()
        _redis_client = client
        logger.info("Redis connected successfully")
    except Exception as e:
        logger.warning("Redis unavailable, caching disabled: %s", e)
        _redis_client = None
    return _redis_client


def redis_health() -> dict:
    """Return Redis health status for the /health endpoint."""
    client = get_redis()
    if client is None:
        return {"status": "disconnected", "message": "Redis not available"}
    try:
        client.ping()
        return {"status": "connected"}
    except Exception as e:
        # Connection lost — reset so next get_redis() retries
        global _redis_client
        _redis_client = None
        return {"status": "error", "message": str(e)}


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

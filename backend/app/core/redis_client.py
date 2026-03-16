"""
Shared Redis client utilities.
"""
from functools import lru_cache
from typing import Optional

from loguru import logger

from app.config import settings

try:
    from redis import Redis
except Exception:  # pragma: no cover - import guard for environments without redis installed
    Redis = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def get_redis_client() -> Optional["Redis"]:
    """
    Return a cached Redis client when REDIS_URL is configured.

    The client is created lazily and actual connectivity is validated during use.
    """
    if not settings.REDIS_URL:
        logger.info("Redis session store disabled: REDIS_URL is not configured")
        return None

    if Redis is None:
        logger.warning("Redis session store disabled: python redis package is not installed")
        return None

    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT_SEC,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SEC,
        health_check_interval=30,
    )


def cleanup_redis_client() -> None:
    """Close the cached Redis client if it exists."""
    try:
        client = get_redis_client()
    except Exception:
        client = None

    if client is None:
        return

    try:
        client.close()
    except Exception as exc:  # pragma: no cover - best effort cleanup
        logger.warning(f"Failed to close Redis client: {exc}")

    get_redis_client.cache_clear()

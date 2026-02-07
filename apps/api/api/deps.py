"""Shared dependencies for API endpoints."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis

from shared.config.settings import get_settings
from shared.queue.redis_queue import TaskQueue

_redis: aioredis.Redis | None = None
_queue: TaskQueue | None = None


async def init_deps() -> None:
    """Initialize shared dependencies (called on app startup)."""
    global _redis, _queue
    settings = get_settings()
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    _queue = TaskQueue(settings.redis_url)


async def close_deps() -> None:
    """Close shared dependencies (called on app shutdown)."""
    global _redis, _queue
    if _redis:
        await _redis.aclose()
    if _queue:
        await _queue.close()


def get_redis() -> aioredis.Redis:
    """Get the shared Redis client."""
    assert _redis is not None, "Redis not initialized — call init_deps() first"
    return _redis


def get_queue() -> TaskQueue:
    """Get the shared TaskQueue."""
    assert _queue is not None, "TaskQueue not initialized — call init_deps() first"
    return _queue

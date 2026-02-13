"""Shared dependencies for API endpoints."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import redis.asyncio as aioredis

from shared.config.settings import get_settings
from shared.queue.redis_queue import TaskQueue

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None
_queue: TaskQueue | None = None
_scheduler_task: asyncio.Task | None = None


async def init_deps() -> None:
    """Initialize shared dependencies (called on app startup)."""
    global _redis, _queue, _scheduler_task
    settings = get_settings()
    _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    _queue = TaskQueue(settings.redis_url)

    # Create PostgreSQL tables if they don't exist
    from shared.db.engine import create_tables

    await create_tables()

    # Ensure OpenSearch index exists
    try:
        from shared.search import ensure_index

        await ensure_index()
    except Exception:
        logger.warning("OpenSearch index setup failed (search will use PG fallback)")

    # Start background topic scheduler
    from api.scheduler import scheduler_loop

    _scheduler_task = asyncio.create_task(scheduler_loop(_queue))


async def close_deps() -> None:
    """Close shared dependencies (called on app shutdown)."""
    global _redis, _queue, _scheduler_task
    if _scheduler_task:
        _scheduler_task.cancel()
    if _redis:
        await _redis.aclose()
    if _queue:
        await _queue.close()

    from shared.db.engine import close_engine

    await close_engine()

    try:
        from shared.search import close_client

        await close_client()
    except Exception:
        pass


def get_redis() -> aioredis.Redis:
    """Get the shared Redis client."""
    assert _redis is not None, "Redis not initialized — call init_deps() first"
    return _redis


def get_queue() -> TaskQueue:
    """Get the shared TaskQueue."""
    assert _queue is not None, "TaskQueue not initialized — call init_deps() first"
    return _queue

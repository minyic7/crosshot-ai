"""Crawler task dispatcher — routes tasks to platform-specific executors.

The crawler agent receives tasks with labels like "crawler:x", "crawler:xhs".
This dispatcher maps labels to the correct platform executor.
Fan-in (pipeline countdown) is handled generically by BaseAgent.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from shared.agent.base import Result
from shared.config.settings import Settings

from .platforms.base import BasePlatformExecutor
from .platforms.x.executor import XExecutor

logger = logging.getLogger(__name__)


def create_executors(
    redis_client: aioredis.Redis,
    settings: Settings,
) -> dict[str, BasePlatformExecutor]:
    """Create platform executors, keyed by task label.

    Add new platforms here as they are implemented.
    """
    return {
        "crawler:x": XExecutor(
            redis_client=redis_client,
            grok_api_key=settings.grok_api_key,
            grok_base_url=settings.grok_base_url,
            grok_model=settings.grok_model,
        ),
        # Future: "crawler:xhs": XHSExecutor(redis_client=redis_client),
    }


async def execute_task(
    task,
    executors: dict[str, BasePlatformExecutor],
) -> Result:
    """Dispatch a task to the appropriate platform executor."""
    executor = executors.get(task.label)
    if executor is None:
        raise ValueError(
            f"No executor for label '{task.label}'. "
            f"Available: {list(executors.keys())}"
        )

    logger.info(
        "Dispatching task %s (label=%s) to %s executor",
        task.id, task.label, executor.platform,
    )
    data = await executor.run(task)
    return Result(data=data)

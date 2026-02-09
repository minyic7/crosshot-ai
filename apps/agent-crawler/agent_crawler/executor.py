"""Crawler task dispatcher — routes tasks to platform-specific executors.

The crawler agent receives tasks with labels like "crawler:x", "crawler:xhs".
This dispatcher maps labels to the correct platform executor.

When a topic_id is present, the crawler handles fan-in:
- Atomically decrements the pending counter in Redis
- Updates pipeline progress
- If last crawler to finish, pushes analyst:summarize
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.agent.base import Result
from shared.config.settings import Settings
from shared.models.task import Task, TaskPriority

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
    task: Task,
    executors: dict[str, BasePlatformExecutor],
    redis_client: aioredis.Redis,
) -> Result:
    """Dispatch a task to the appropriate platform executor.

    Args:
        task: The task to execute.
        executors: Map of label → executor.
        redis_client: Redis client for fan-in tracking.

    Returns:
        Result with the execution data.

    Raises:
        ValueError: If no executor matches the task label.
    """
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

    # Fan-in: if this crawl was triggered by a topic, handle completion tracking
    new_tasks: list[Task] = []
    topic_id = task.payload.get("topic_id")
    if topic_id:
        pipeline_key = f"topic:{topic_id}:pipeline"

        # Atomic: decrement pending counter + update pipeline progress
        pipe = redis_client.pipeline()
        pipe.decr(f"topic:{topic_id}:pending")
        pipe.hincrby(pipeline_key, "done", 1)
        pipe.hset(pipeline_key, "updated_at", datetime.now(timezone.utc).isoformat())
        results = await pipe.execute()
        remaining = results[0]

        logger.info(
            "Topic %s: crawl done, remaining=%s",
            topic_id, max(remaining, 0),
        )

        # Last crawler triggers analyst:summarize
        if remaining <= 0:
            new_tasks.append(
                Task(
                    label="analyst:summarize",
                    priority=TaskPriority.MEDIUM,
                    payload={"topic_id": topic_id},
                    parent_job_id=task.parent_job_id,
                )
            )
            await redis_client.hset(pipeline_key, "phase", "summarizing")
            logger.info("Topic %s: all crawls done, triggering summarize", topic_id)

    return Result(data=data, new_tasks=new_tasks)

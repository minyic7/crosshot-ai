"""Redis-based task queue with priority support.

Uses Redis Sorted Sets for priority ordering.
Each label gets its own sorted set: task:queue:{label}
Task status tracked in Redis Hash: task:status:{task_id}
"""

import json
import logging
from datetime import datetime
from typing import Any

import redis.asyncio as redis

from shared.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """Task queue backed by Redis Sorted Sets.

    Priority ordering: higher TaskPriority value + earlier timestamp = processed first.
    Score formula: priority * 1_000_000_000 + (MAX_TS - created_at_timestamp)
    This ensures high-priority tasks come first, with FIFO within same priority.
    """

    MAX_TS = 2_000_000_000  # ~2033, used to invert timestamp for FIFO ordering

    def __init__(self, redis_url: str) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.aclose()

    async def push(self, task: Task) -> None:
        """Push a task to the queue.

        The task is added to a sorted set keyed by its label.
        Score is computed so higher priority + earlier creation = higher score.
        """
        key = f"task:queue:{task.label}"
        score = task.priority.value * 1_000_000_000 + (
            self.MAX_TS - int(task.created_at.timestamp())
        )
        task.status = TaskStatus.PENDING
        await self._redis.zadd(key, {task.model_dump_json(): score})
        logger.debug("Pushed task %s to %s (score=%s)", task.id, key, score)

    async def pop(self, labels: list[str]) -> Task | None:
        """Pop the highest-priority task from any of the given labels.

        Checks each label's queue and returns the task with the highest score.
        Returns None if all queues are empty.
        """
        best_task: Task | None = None
        best_score: float = -1
        best_key: str = ""

        for label in labels:
            key = f"task:queue:{label}"
            # Peek at the highest-scored item
            results = await self._redis.zrange(key, -1, -1, withscores=True)
            if results:
                task_json, score = results[0]
                if score > best_score:
                    best_score = score
                    best_task = Task.model_validate_json(task_json)
                    best_key = key

        if best_task is None:
            return None

        # Remove from queue atomically
        removed = await self._redis.zrem(best_key, best_task.model_dump_json())
        if not removed:
            # Another consumer grabbed it; try again
            return await self.pop(labels)

        # Mark as running
        best_task.status = TaskStatus.RUNNING
        best_task.started_at = datetime.now()
        await self._set_status(best_task)
        logger.info("Popped task %s from %s", best_task.id, best_key)
        return best_task

    async def mark_done(self, task: Task, result: Any = None) -> None:
        """Mark a task as completed."""
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        await self._set_status(task)
        if result is not None:
            await self._redis.set(
                f"task:result:{task.id}",
                json.dumps(result, default=str),
                ex=86400,  # expire after 24h
            )
        logger.info("Task %s completed", task.id)

    async def mark_failed(self, task: Task, error: str) -> None:
        """Mark a task as failed. Re-queue if retries remain."""
        task.retry_count += 1
        task.error = error

        if task.retry_count < task.max_retries:
            # Re-queue with lower priority
            task.status = TaskStatus.PENDING
            task.priority = min(task.priority, task.priority)  # keep same priority
            await self.push(task)
            logger.warning(
                "Task %s failed (attempt %d/%d), re-queued: %s",
                task.id,
                task.retry_count,
                task.max_retries,
                error,
            )
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            await self._set_status(task)
            await self._redis.lpush("task:dead_letter", task.model_dump_json())
            logger.error(
                "Task %s permanently failed after %d retries: %s",
                task.id,
                task.max_retries,
                error,
            )

    async def get_queue_length(self, label: str) -> int:
        """Get the number of pending tasks for a label."""
        return await self._redis.zcard(f"task:queue:{label}")

    async def _set_status(self, task: Task) -> None:
        """Store task status in Redis Hash."""
        await self._redis.hset(
            f"task:status:{task.id}",
            mapping={
                "status": task.status.value,
                "started_at": task.started_at.isoformat() if task.started_at else "",
                "completed_at": (
                    task.completed_at.isoformat() if task.completed_at else ""
                ),
                "retry_count": str(task.retry_count),
                "error": task.error or "",
            },
        )
        # Expire status after 7 days
        await self._redis.expire(f"task:status:{task.id}", 604800)

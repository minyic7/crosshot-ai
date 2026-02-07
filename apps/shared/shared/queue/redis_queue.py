"""Redis-based task queue with priority support.

Uses Redis Sorted Sets for priority ordering.
Each label gets its own sorted set: task:queue:{label}
Full task state stored as JSON: task:{task_id}
"""

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

        Stores task ID in sorted set (for queue ordering) and
        full task JSON in a separate key (for querying).
        """
        key = f"task:queue:{task.label}"
        score = task.priority.value * 1_000_000_000 + (
            self.MAX_TS - int(task.created_at.timestamp())
        )
        task.status = TaskStatus.PENDING
        await self._redis.zadd(key, {task.id: score})
        await self._store_task(task)
        logger.debug("Pushed task %s to %s (score=%s)", task.id, key, score)

    async def pop(self, labels: list[str], agent_name: str | None = None) -> Task | None:
        """Pop the highest-priority task from any of the given labels.

        Checks each label's queue and returns the task with the highest score.
        Sets assigned_to if agent_name is provided.
        Returns None if all queues are empty.
        """
        best_id: str | None = None
        best_score: float = -1
        best_key: str = ""

        for label in labels:
            key = f"task:queue:{label}"
            results = await self._redis.zrange(key, -1, -1, withscores=True)
            if results:
                task_id, score = results[0]
                if score > best_score:
                    best_score = score
                    best_id = task_id
                    best_key = key

        if best_id is None:
            return None

        # Remove from queue atomically
        removed = await self._redis.zrem(best_key, best_id)
        if not removed:
            return await self.pop(labels, agent_name)

        # Load full task state
        task = await self._load_task(best_id)
        if task is None:
            logger.warning("Task %s in queue but no stored state, skipping", best_id)
            return await self.pop(labels, agent_name)

        # Mark as running
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        if agent_name:
            task.assigned_to = agent_name
        await self._store_task(task)
        logger.info("Popped task %s from %s (assigned_to=%s)", task.id, best_key, agent_name)
        return task

    async def mark_done(self, task: Task, result: Any = None) -> None:
        """Mark a task as completed and store result on the task."""
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now()
        if result is not None:
            task.result = result if isinstance(result, dict) else {"data": result}
        await self._store_task(task)
        await self._redis.lpush("task:recent_completed", task.id)
        await self._redis.ltrim("task:recent_completed", 0, 99)
        logger.info("Task %s completed", task.id)

    async def mark_failed(self, task: Task, error: str) -> None:
        """Mark a task as failed. Re-queue if retries remain."""
        task.retry_count += 1
        task.error = error

        if task.retry_count < task.max_retries:
            task.status = TaskStatus.PENDING
            task.assigned_to = None
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
            await self._store_task(task)
            await self._redis.lpush("task:dead_letter", task.id)
            await self._redis.lpush("task:recent_completed", task.id)
            await self._redis.ltrim("task:recent_completed", 0, 99)
            logger.error(
                "Task %s permanently failed after %d retries: %s",
                task.id,
                task.max_retries,
                error,
            )

    async def get_queue_length(self, label: str) -> int:
        """Get the number of pending tasks for a label."""
        return await self._redis.zcard(f"task:queue:{label}")

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return await self._load_task(task_id)

    async def get_queue_labels(self) -> list[str]:
        """Get all queue labels that have pending tasks."""
        labels = []
        async for key in self._redis.scan_iter("task:queue:*"):
            labels.append(key.removeprefix("task:queue:"))
        return labels

    async def get_recent_completed(self, limit: int = 20) -> list[Task]:
        """Get recently completed/failed tasks."""
        task_ids = await self._redis.lrange("task:recent_completed", 0, limit - 1)
        tasks = []
        for tid in task_ids:
            task = await self._load_task(tid)
            if task:
                tasks.append(task)
        return tasks

    # ──────────────────────────────────────────────
    # Task storage
    # ──────────────────────────────────────────────

    async def _store_task(self, task: Task) -> None:
        """Store full task as JSON string in Redis (7-day expiry)."""
        await self._redis.set(f"task:{task.id}", task.model_dump_json(), ex=604800)

    async def _load_task(self, task_id: str) -> Task | None:
        """Load a task from Redis by ID."""
        data = await self._redis.get(f"task:{task_id}")
        if data is None:
            return None
        return Task.model_validate_json(data)

"""Task model for the agent task queue system."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskPriority(int, Enum):
    """Task priority level. Higher value = higher priority."""

    LOW = 0
    MEDIUM = 1
    HIGH = 2


class Task(BaseModel):
    """A unit of work to be consumed by an agent.

    Tasks flow through the system via Redis Queue, routed by label.
    Each agent subscribes to specific labels and consumes matching tasks.

    Example labels:
        - "crawler:xhs" → consumed by crawler agent (XHS platform)
        - "crawler:x"   → consumed by crawler agent (X platform)
        - "ai:plan"     → consumed by coordinator agent (task planning)
        - "ai:analyze"  → consumed by coordinator agent (data analysis)
        - "ai:schedule" → consumed by coordinator agent (scheduling)
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    payload: dict[str, Any] = Field(default_factory=dict)
    parent_job_id: str | None = None
    assigned_to: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retry_count: int = 0
    max_retries: int = 3
    error: str | None = None
    result: dict[str, Any] | None = None


class RetryLater(Exception):
    """Raise to re-queue a task with a delay instead of counting it as a failure.

    Used when a transient resource is unavailable (e.g. no cookies in the pool).
    The task will be parked and re-queued after ``delay_seconds`` without
    incrementing ``retry_count``.
    """

    def __init__(self, delay_seconds: int = 60, reason: str = ""):
        self.delay_seconds = delay_seconds
        self.reason = reason
        super().__init__(reason or f"Retry after {delay_seconds}s")

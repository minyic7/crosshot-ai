"""Base platform executor — abstract interface for all platform crawlers.

Each platform (X, XHS, etc.) implements its own executor with platform-specific
browser automation, parsing, and data extraction logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shared.models.task import Task


class BasePlatformExecutor(ABC):
    """Abstract base for platform-specific task executors.

    Each platform implements:
    - run(): main dispatch — reads task.payload["action"] and routes to the right method
    - Platform-specific actions (search, get_tweet, get_timeline, etc.)
    - Platform-specific browser automation, parsing, data extraction

    Usage:
        executor = XExecutor(redis=redis, settings=settings)
        result = await executor.run(task)
    """

    @property
    @abstractmethod
    def platform(self) -> str:
        """Platform identifier (e.g., 'x', 'xhs')."""
        ...

    @abstractmethod
    async def run(self, task: Task) -> dict[str, Any]:
        """Execute a platform task. Returns result data dict.

        The task.payload["action"] determines which operation to perform.
        Each platform defines its own set of supported actions.

        Raises:
            ValueError: If action is unknown.
            PlatformError: If the platform operation fails.
        """
        ...

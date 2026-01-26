"""Retry utilities for async operations."""

import asyncio
import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional, Type, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    delay: float = 1.0
    backoff_factor: float = 2.0
    max_delay: float = 30.0
    exceptions: tuple[Type[Exception], ...] = field(default_factory=lambda: (Exception,))

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for given attempt (0-indexed)."""
        delay = self.delay * (self.backoff_factor**attempt)
        return min(delay, self.max_delay)


@dataclass
class RetryResult:
    """Result of a retry operation."""

    success: bool
    value: Any = None
    error: Optional[Exception] = None
    attempts: int = 0
    errors: list[Exception] = field(default_factory=list)


def retry_async(
    config: Optional[RetryConfig] = None,
    *,
    max_retries: Optional[int] = None,
    delay: Optional[float] = None,
    exceptions: Optional[tuple[Type[Exception], ...]] = None,
):
    """Async retry decorator with configurable behavior.

    Usage:
        @retry_async(max_retries=3, delay=1.0)
        async def my_function():
            ...

        # Or with config object
        @retry_async(RetryConfig(max_retries=5))
        async def my_function():
            ...
    """
    if config is None:
        config = RetryConfig()
    else:
        # Make a copy to avoid modifying the original
        config = RetryConfig(
            max_retries=config.max_retries,
            delay=config.delay,
            backoff_factor=config.backoff_factor,
            max_delay=config.max_delay,
            exceptions=config.exceptions,
        )

    # Override config with kwargs if provided
    if max_retries is not None:
        config.max_retries = max_retries
    if delay is not None:
        config.delay = delay
    if exceptions is not None:
        config.exceptions = exceptions

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        delay_time = config.get_delay(attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{config.max_retries} for {func.__name__}: "
                            f"{type(e).__name__}: {e}. Waiting {delay_time:.1f}s..."
                        )
                        await asyncio.sleep(delay_time)
                    else:
                        logger.error(
                            f"All {config.max_retries} retries failed for {func.__name__}: "
                            f"{type(e).__name__}: {e}"
                        )

            raise last_exception

        return wrapper

    return decorator


async def retry_with_result(
    func: Callable[..., T],
    *args,
    config: Optional[RetryConfig] = None,
    **kwargs,
) -> RetryResult:
    """Execute function with retries and return detailed result.

    Useful when you want to handle partial failures gracefully
    without raising exceptions.

    Usage:
        result = await retry_with_result(download_image, url, config=RetryConfig(max_retries=3))
        if not result.success:
            log_failure(result.error, result.attempts)
    """
    if config is None:
        config = RetryConfig()

    errors: list[Exception] = []

    for attempt in range(config.max_retries + 1):
        try:
            value = await func(*args, **kwargs)
            return RetryResult(
                success=True,
                value=value,
                attempts=attempt + 1,
                errors=errors,
            )
        except config.exceptions as e:
            errors.append(e)
            logger.debug(
                f"Attempt {attempt + 1}/{config.max_retries + 1} failed: "
                f"{type(e).__name__}: {e}"
            )

            if attempt < config.max_retries:
                await asyncio.sleep(config.get_delay(attempt))

    return RetryResult(
        success=False,
        error=errors[-1] if errors else None,
        attempts=config.max_retries + 1,
        errors=errors,
    )

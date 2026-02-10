"""CookiesService — acquire and manage cookies for platform crawlers.

Shared across all agents. Provides:
- acquire(platform): Pick the best cookie (round-robin, respects cooldown/fail/rate limits)
- report_success(cookie): Reset fail count, bump use counter
- report_failure(cookie, error): Increment fail count, apply cooldown, deactivate if needed
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import redis.asyncio as aioredis

from shared.models.cookies import CookiesPool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlatformRateConfig:
    """Per-platform rate limiting configuration."""

    daily_limit: int
    min_interval_seconds: int
    max_fail_count: int = 3
    base_cooldown_seconds: int = 60


PLATFORM_RATE_CONFIGS: dict[str, PlatformRateConfig] = {
    "x": PlatformRateConfig(daily_limit=100, min_interval_seconds=30),
    "xhs": PlatformRateConfig(daily_limit=60, min_interval_seconds=60),
}

DEFAULT_RATE_CONFIG = PlatformRateConfig(daily_limit=50, min_interval_seconds=60)


class CookiesService:
    """Manages cookie lifecycle for crawlers."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def acquire(self, platform: str) -> CookiesPool | None:
        """Acquire the best available cookie for a platform.

        Selection criteria (in order):
        1. is_active = True
        2. fail_count < max_fail_count
        3. cooldown_until is None or in the past
        4. use_count_today < daily_limit
        5. last_used_at + min_interval has elapsed
        6. Lowest use_count_today (round-robin)

        Returns None if no suitable cookies are available.
        """
        config = PLATFORM_RATE_CONFIGS.get(platform, DEFAULT_RATE_CONFIG)
        cookie_ids = await self._redis.smembers(f"cookies:index:{platform}")
        if not cookie_ids:
            return None

        now = datetime.now()
        candidates: list[CookiesPool] = []

        for cid in cookie_ids:
            data = await self._redis.get(f"cookies:pool:{cid}")
            if data is None:
                continue
            cookie = CookiesPool.model_validate_json(data)

            # Auto-reset daily counter when date changes
            today = date.today()
            if cookie.use_count_date != today:
                cookie.use_count_today = 0
                cookie.use_count_date = today
                await self._save(cookie)

            # Skip inactive
            if not cookie.is_active:
                continue

            # Skip too many failures
            if cookie.fail_count >= config.max_fail_count:
                continue

            # Skip in cooldown
            if cookie.cooldown_until and cookie.cooldown_until > now:
                continue

            # Skip if daily limit reached
            if cookie.use_count_today >= config.daily_limit:
                continue

            # Skip if minimum interval not elapsed
            if cookie.last_used_at:
                elapsed = (now - cookie.last_used_at).total_seconds()
                if elapsed < config.min_interval_seconds:
                    continue

            candidates.append(cookie)

        if not candidates:
            return None

        # Pick the one with lowest use_count_today (round-robin)
        best = min(candidates, key=lambda c: c.use_count_today)

        # Update last_used_at and use_count_today
        best.last_used_at = now
        best.use_count_today += 1
        best.use_count_date = date.today()
        await self._save(best)

        logger.info(
            "Acquired cookie %s (%s) for platform %s (use_count=%d/%d)",
            best.id[:8], best.name, platform,
            best.use_count_today, config.daily_limit,
        )
        return best

    async def report_success(self, cookie: CookiesPool) -> None:
        """Report successful use of a cookie. Resets fail count."""
        cookie.fail_count = 0
        cookie.cooldown_until = None
        await self._save(cookie)

    async def report_failure(
        self, cookie: CookiesPool, error: str | None = None,
    ) -> None:
        """Report failed use of a cookie.

        Increments fail_count, applies cooldown, deactivates if too many failures.
        """
        config = PLATFORM_RATE_CONFIGS.get(cookie.platform, DEFAULT_RATE_CONFIG)
        cookie.fail_count += 1
        cooldown_secs = config.base_cooldown_seconds * cookie.fail_count
        cookie.cooldown_until = datetime.now() + timedelta(seconds=cooldown_secs)

        if cookie.fail_count >= config.max_fail_count:
            cookie.is_active = False
            logger.warning(
                "Cookie %s (%s) deactivated after %d failures. Last error: %s",
                cookie.id[:8], cookie.name, cookie.fail_count, error,
            )
        else:
            logger.warning(
                "Cookie %s (%s) failed (%d/%d), cooldown %ds. Error: %s",
                cookie.id[:8], cookie.name, cookie.fail_count,
                config.max_fail_count, cooldown_secs, error,
            )

        await self._save(cookie)

    async def _save(self, cookie: CookiesPool) -> None:
        """Persist cookie state to Redis."""
        await self._redis.set(
            f"cookies:pool:{cookie.id}",
            cookie.model_dump_json(),
        )

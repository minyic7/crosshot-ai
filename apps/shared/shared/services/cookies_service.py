"""CookiesService — acquire and manage cookies for platform crawlers.

Shared across all agents. Provides:
- acquire(platform): Pick the best cookie (round-robin, respects cooldown/fail limits)
- report_success(cookie): Reset fail count, bump use counter
- report_failure(cookie, error): Increment fail count, apply cooldown, deactivate if needed
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import redis.asyncio as aioredis

from shared.models.cookies import CookiesPool

logger = logging.getLogger(__name__)

# Deactivate after this many consecutive failures
MAX_FAIL_COUNT = 3

# Cooldown duration after a failure (increases with fail count)
BASE_COOLDOWN_SECONDS = 60


class CookiesService:
    """Manages cookie lifecycle for crawlers."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def acquire(self, platform: str) -> CookiesPool | None:
        """Acquire the best available cookie for a platform.

        Selection criteria (in order):
        1. is_active = True
        2. fail_count < MAX_FAIL_COUNT
        3. cooldown_until is None or in the past
        4. Lowest use_count_today (round-robin)

        Returns None if no suitable cookies are available.
        """
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

            # Skip inactive
            if not cookie.is_active:
                continue

            # Skip too many failures
            if cookie.fail_count >= MAX_FAIL_COUNT:
                continue

            # Skip in cooldown
            if cookie.cooldown_until and cookie.cooldown_until > now:
                continue

            candidates.append(cookie)

        if not candidates:
            return None

        # Pick the one with lowest use_count_today (round-robin)
        best = min(candidates, key=lambda c: c.use_count_today)

        # Update last_used_at and use_count_today
        best.last_used_at = now
        best.use_count_today += 1
        await self._save(best)

        logger.info(
            "Acquired cookie %s (%s) for platform %s (use_count=%d)",
            best.id[:8], best.name, platform, best.use_count_today,
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
        cookie.fail_count += 1
        cooldown_secs = BASE_COOLDOWN_SECONDS * cookie.fail_count
        cookie.cooldown_until = datetime.now() + timedelta(seconds=cooldown_secs)

        if cookie.fail_count >= MAX_FAIL_COUNT:
            cookie.is_active = False
            logger.warning(
                "Cookie %s (%s) deactivated after %d failures. Last error: %s",
                cookie.id[:8], cookie.name, cookie.fail_count, error,
            )
        else:
            logger.warning(
                "Cookie %s (%s) failed (%d/%d), cooldown %ds. Error: %s",
                cookie.id[:8], cookie.name, cookie.fail_count,
                MAX_FAIL_COUNT, cooldown_secs, error,
            )

        await self._save(cookie)

    async def _save(self, cookie: CookiesPool) -> None:
        """Persist cookie state to Redis."""
        await self._redis.set(
            f"cookies:pool:{cookie.id}",
            cookie.model_dump_json(),
        )

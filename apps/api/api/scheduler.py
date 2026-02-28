"""Background scheduler — periodically re-triggers active topics and users."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis

from shared.config.settings import get_settings
from shared.db.engine import get_session_factory
from shared.db.models import TopicRow, UserRow, topic_users
from shared.models.task import Task, TaskPriority
from shared.queue.redis_queue import TaskQueue
from sqlalchemy import select
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 6
CHECK_INTERVAL_SECONDS = 60
PROGRESS_STALE_HOURS = 1  # Reset stuck progress after this duration


async def scheduler_loop(queue: TaskQueue) -> None:
    """Run every 60 seconds, check which active topics/users need re-crawling."""
    logger.info("Scheduler started (check every %ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await _check_and_schedule(queue)
        except Exception:
            logger.warning("Scheduler tick failed", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _check_and_schedule(queue: TaskQueue) -> None:
    factory = get_session_factory()
    async with factory() as session:
        # Load active topics with their attached users
        topic_stmt = (
            select(TopicRow)
            .where(TopicRow.status == "active")
            .options(selectinload(TopicRow.users))
        )
        topic_result = await session.execute(topic_stmt)
        topics = topic_result.scalars().all()

        # Load active standalone users (not attached to any topic)
        attached_ids = select(topic_users.c.user_id).distinct()
        user_stmt = select(UserRow).where(
            UserRow.status == "active",
            UserRow.id.notin_(attached_ids),
        )
        user_result = await session.execute(user_stmt)
        standalone_users = user_result.scalars().all()

    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    now = datetime.now(timezone.utc)
    try:
        # ── Schedule topics ──
        for topic in topics:
            interval_hours = topic.config.get(
                "schedule_interval_hours", DEFAULT_INTERVAL_HOURS
            )
            interval = timedelta(hours=interval_hours)

            if topic.last_crawl_at and (now - topic.last_crawl_at) < interval:
                continue

            progress = await redis_client.hgetall(f"topic:{topic.id}:progress")
            if progress and progress.get("phase") not in (None, "", "done"):
                if _is_progress_stale(progress, now):
                    logger.warning(
                        "Resetting stale progress for topic '%s' (stuck in '%s')",
                        topic.name, progress.get("phase"),
                    )
                    await redis_client.hset(
                        f"topic:{topic.id}:progress", mapping={"phase": "done"}
                    )
                    await redis_client.delete(f"topic:{topic.id}:pending")
                else:
                    continue

            # Include attached users in payload
            users_info = [
                {
                    "user_id": str(u.id),
                    "username": u.username,
                    "platform": u.platform,
                    "profile_url": u.profile_url,
                    "config": u.config,
                }
                for u in topic.users
            ]

            payload: dict = {
                "topic_id": str(topic.id),
                "name": topic.name,
                "platforms": topic.platforms,
                "keywords": topic.keywords,
                "config": topic.config,
            }
            if users_info:
                payload["users"] = users_info

            task = Task(
                label="analyst:analyze",
                priority=TaskPriority.LOW,
                payload=payload,
            )
            await queue.push(task)
            logger.info("Scheduled re-crawl for topic '%s' (%s)", topic.name, topic.id)

        # ── Schedule standalone users ──
        for user in standalone_users:
            interval_hours = user.config.get(
                "schedule_interval_hours", DEFAULT_INTERVAL_HOURS
            )
            interval = timedelta(hours=interval_hours)

            if user.last_crawl_at and (now - user.last_crawl_at) < interval:
                continue

            progress = await redis_client.hgetall(f"user:{user.id}:progress")
            if progress and progress.get("phase") not in (None, "", "done"):
                if _is_progress_stale(progress, now):
                    logger.warning(
                        "Resetting stale progress for user '%s' (stuck in '%s')",
                        user.name, progress.get("phase"),
                    )
                    await redis_client.hset(
                        f"user:{user.id}:progress", mapping={"phase": "done"}
                    )
                    await redis_client.delete(f"user:{user.id}:pending")
                else:
                    continue

            task = Task(
                label="analyst:analyze",
                priority=TaskPriority.LOW,
                payload={
                    "user_id": str(user.id),
                    "name": user.name,
                    "platform": user.platform,
                    "username": user.username,
                    "profile_url": user.profile_url,
                    "config": user.config,
                },
            )
            await queue.push(task)
            logger.info("Scheduled re-crawl for user '%s' (%s)", user.name, user.id)
    finally:
        await redis_client.aclose()


def _is_progress_stale(progress: dict, now: datetime) -> bool:
    """Check if progress has been stuck for longer than PROGRESS_STALE_HOURS."""
    updated_at = progress.get("updated_at")
    if not updated_at:
        return True
    try:
        updated = datetime.fromisoformat(updated_at)
        return (now - updated) > timedelta(hours=PROGRESS_STALE_HOURS)
    except (ValueError, TypeError):
        return True

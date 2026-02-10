"""Background scheduler — periodically re-triggers active topics."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import redis.asyncio as aioredis

from shared.config.settings import get_settings
from shared.db.engine import get_session_factory
from shared.db.models import TopicRow
from shared.models.task import Task, TaskPriority
from shared.queue.redis_queue import TaskQueue
from sqlalchemy import select

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_HOURS = 6
CHECK_INTERVAL_SECONDS = 60


async def scheduler_loop(queue: TaskQueue) -> None:
    """Run every 60 seconds, check which active topics need re-crawling."""
    logger.info("Topic scheduler started (check every %ds)", CHECK_INTERVAL_SECONDS)
    while True:
        try:
            await _check_and_schedule(queue)
        except Exception:
            logger.warning("Scheduler tick failed", exc_info=True)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _check_and_schedule(queue: TaskQueue) -> None:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow).where(TopicRow.status == "active")
        result = await session.execute(stmt)
        topics = result.scalars().all()

    settings = get_settings()
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    now = datetime.now(timezone.utc)
    try:
        for topic in topics:
            interval_hours = topic.config.get(
                "schedule_interval_hours", DEFAULT_INTERVAL_HOURS
            )
            interval = timedelta(hours=interval_hours)

            # Skip if recently crawled
            if topic.last_crawl_at and (now - topic.last_crawl_at) < interval:
                continue

            # Skip if topic already has an active pipeline (analyzing/crawling/summarizing)
            pipeline = await redis_client.hgetall(f"topic:{topic.id}:pipeline")
            if pipeline and pipeline.get("phase") not in (None, "", "done"):
                continue

            # Push analyst:analyze task with low priority (scheduled = background)
            task = Task(
                label="analyst:analyze",
                priority=TaskPriority.LOW,
                payload={
                    "topic_id": str(topic.id),
                    "name": topic.name,
                    "platforms": topic.platforms,
                    "keywords": topic.keywords,
                    "config": topic.config,
                },
            )
            await queue.push(task)
            logger.info("Scheduled re-crawl for topic '%s' (%s)", topic.name, topic.id)
    finally:
        await redis_client.aclose()

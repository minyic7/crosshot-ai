"""Background scheduler — periodically re-triggers active topics."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

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

    now = datetime.now(timezone.utc)
    for topic in topics:
        interval_hours = topic.config.get(
            "schedule_interval_hours", DEFAULT_INTERVAL_HOURS
        )
        interval = timedelta(hours=interval_hours)

        # Skip if recently crawled
        if topic.last_crawl_at and (now - topic.last_crawl_at) < interval:
            continue

        # Push analyst:plan task with low priority (scheduled = background)
        task = Task(
            label="analyst:plan",
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

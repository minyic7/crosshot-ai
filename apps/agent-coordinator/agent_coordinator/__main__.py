"""Coordinator agent entry point — rule-based task dispatcher and completion tracker."""

import asyncio
import logging
import os

import redis.asyncio as aioredis

from shared.agent.base import BaseAgent, Result
from shared.config.settings import get_settings
from shared.models.task import Task, TaskPriority

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def handle_dispatch(
    task: Task,
    redis_client: aioredis.Redis,
) -> Result:
    """Handle coord:dispatch — fan out crawler tasks from analyst's plan."""
    payload = task.payload
    topic_id = payload["topic_id"]
    crawl_plan = payload.get("crawl_plan", [])

    if not crawl_plan:
        logger.warning("coord:dispatch for topic %s has empty crawl_plan", topic_id)
        return Result(data={"error": "empty crawl_plan", "topic_id": topic_id})

    new_tasks = []
    for plan_item in crawl_plan:
        platform = plan_item.get("platform", "x")
        label = f"crawler:{platform}"

        crawler_payload = {
            **plan_item,
            "topic_id": topic_id,
        }

        crawler_task = Task(
            label=label,
            priority=TaskPriority.MEDIUM,
            payload=crawler_payload,
            parent_job_id=task.parent_job_id,
        )
        new_tasks.append(crawler_task)

    # Track pending crawl count in Redis
    pending_key = f"topic:{topic_id}:pending_crawls"
    await redis_client.set(pending_key, len(new_tasks), ex=86400)

    # Clear any previous content_ids list for this cycle
    await redis_client.delete(f"topic:{topic_id}:content_ids")

    logger.info(
        "Dispatched %d crawler tasks for topic %s",
        len(new_tasks),
        topic_id,
    )

    return Result(
        data={"dispatched": len(new_tasks), "topic_id": topic_id},
        new_tasks=new_tasks,
    )


async def handle_crawl_done(
    task: Task,
    redis_client: aioredis.Redis,
) -> Result:
    """Handle coord:crawl_done — track completion, detect errors, notify analyst."""
    payload = task.payload
    topic_id = payload["topic_id"]
    content_ids = payload.get("content_ids", [])
    error = payload.get("error")

    new_tasks: list[Task] = []

    # Accumulate content IDs (even partial results)
    if content_ids:
        await redis_client.rpush(f"topic:{topic_id}:content_ids", *content_ids)
        await redis_client.expire(f"topic:{topic_id}:content_ids", 86400)

    # Error detection → route to analyst:replan
    is_failed = (not content_ids) or error
    if is_failed:
        new_tasks.append(
            Task(
                label="analyst:replan",
                priority=TaskPriority.MEDIUM,
                payload={
                    "topic_id": topic_id,
                    "failed_platform": payload.get("platform"),
                    "error": error,
                    "attempted_query": payload.get("query"),
                },
                parent_job_id=task.parent_job_id,
            )
        )
        logger.warning(
            "Crawl failed for topic %s (platform=%s, query=%s, error=%s)",
            topic_id,
            payload.get("platform"),
            payload.get("query"),
            error,
        )

    # Decrement pending counter
    pending_key = f"topic:{topic_id}:pending_crawls"
    remaining = await redis_client.decr(pending_key)

    logger.info(
        "Crawl done for topic %s: %d content items, %d crawls remaining",
        topic_id,
        len(content_ids),
        remaining,
    )

    if remaining <= 0:
        # All crawls complete — notify analyst to summarize
        await redis_client.delete(pending_key)
        new_tasks.append(
            Task(
                label="analyst:summarize",
                priority=TaskPriority.MEDIUM,
                payload={"topic_id": topic_id},
                parent_job_id=task.parent_job_id,
            )
        )
        logger.info(
            "All crawls done for topic %s, requesting analyst summarize", topic_id
        )

    return Result(
        data={"topic_id": topic_id, "remaining": max(remaining, 0)},
        new_tasks=new_tasks,
    )


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "coordinator")
    settings = get_settings()
    logger.info("Starting coordinator agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)

    # Shared Redis for tracking state
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def _execute(task: Task) -> Result:
        """Rule-based dispatch by label."""
        if task.label == "coord:dispatch":
            return await handle_dispatch(task, redis_client)
        elif task.label == "coord:crawl_done":
            return await handle_crawl_done(task, redis_client)
        else:
            raise ValueError(f"Coordinator has no handler for label: {task.label}")

    agent.execute = _execute

    try:
        await agent.run()
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

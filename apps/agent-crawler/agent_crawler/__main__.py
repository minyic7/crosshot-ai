"""Crawler agent entry point.

The crawler agent pops tasks from Redis, dispatches to the correct
platform executor (X, XHS, etc.), and reports results.
"""

import asyncio
import logging
import os

import redis.asyncio as aioredis

from shared.agent.base import BaseAgent
from shared.config.settings import get_settings

from agent_crawler.executor import create_executors, execute_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "crawler-x")
    settings = get_settings()

    logger.info("Starting crawler agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)

    # Create platform executors (shared Redis connection)
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    executors = create_executors(redis_client, settings)

    # Override execute to use platform dispatcher
    async def _execute(task):
        return await execute_task(task, executors)

    agent.execute = _execute

    try:
        await agent.run()
    finally:
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())

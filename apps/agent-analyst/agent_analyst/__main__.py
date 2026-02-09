"""Analyst agent entry point — AI-driven topic planning and data analysis."""

import asyncio
import logging
import os

from shared.agent.base import BaseAgent
from shared.db.engine import get_session_factory

from agent_analyst.tools.query import make_query_topic_contents
from agent_analyst.tools.summary import make_update_topic_summary
from agent_analyst.tools.topic import make_get_topic_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "analyst")
    logger.info("Starting analyst agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)

    # Create tools with DB/Redis access via closures
    session_factory = get_session_factory()
    redis_client = agent._redis  # reuse agent's redis connection

    agent.tools = [
        make_get_topic_config(session_factory),
        make_query_topic_contents(session_factory, redis_client),
        make_update_topic_summary(session_factory),
    ]

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

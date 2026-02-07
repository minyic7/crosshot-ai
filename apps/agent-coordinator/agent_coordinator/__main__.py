"""Coordinator agent entry point."""

import asyncio
import logging
import os

from shared.agent.base import BaseAgent
from agent_coordinator.tools.plan import submit_task
from agent_coordinator.tools.cookies import get_available_cookies
from agent_coordinator.tools.query import query_contents

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "coordinator")
    logger.info("Starting coordinator agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)
    agent.tools = [submit_task, get_available_cookies, query_contents]

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

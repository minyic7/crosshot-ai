"""Crawler agent entry point."""

import asyncio
import logging
import os

from shared.agent.base import BaseAgent
from agent_crawler.tools.scrape import scrape_page
from agent_crawler.tools.save import save_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "crawler-xhs")
    logger.info("Starting crawler agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)
    agent.tools = [scrape_page, save_results]

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

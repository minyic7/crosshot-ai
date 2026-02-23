"""Searcher agent entry point.

The searcher agent uses the ReAct loop (ai_enabled=true) to autonomously
search the web, evaluate results, and save high-quality findings.
"""

import asyncio
import logging

from shared.agent.base import BaseAgent
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory

from agent_searcher.tools import make_tools

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


async def main() -> None:
    settings = get_settings()
    session_factory = get_session_factory()

    agent = BaseAgent.from_config("searcher")
    agent.tools = make_tools(settings, session_factory, agent)

    logger.info("Starting searcher agent with model=%s", agent.model)
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

"""Analyst agent entry point — deterministic pipeline with targeted LLM calls."""

import asyncio
import logging
import os

from openai import AsyncOpenAI

from shared.agent.base import BaseAgent
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory

from agent_analyst.pipeline import make_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    agent_name = os.environ.get("AGENT_NAME", "analyst")
    logger.info("Starting analyst agent: %s", agent_name)

    agent = BaseAgent.from_config(agent_name)

    settings = get_settings()
    session_factory = get_session_factory()
    redis_client = agent._redis  # reuse agent's redis connection
    llm_client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    # Override execute with deterministic pipeline (bypasses ReAct loop)
    agent.execute = make_pipeline(
        session_factory=session_factory,
        redis_client=redis_client,
        llm_client=llm_client,
        model=settings.grok_model,
        fast_model=settings.grok_fast_model,
    )

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

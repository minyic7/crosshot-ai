"""Analyst agent entry point — AI-driven topic planning and data analysis."""

import asyncio
import logging
import os

from openai import AsyncOpenAI

from shared.agent.base import BaseAgent
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory

from agent_analyst.tools.pipeline import make_set_pipeline_stage
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

    # Create tools with DB/Redis/LLM access via closures
    settings = get_settings()
    session_factory = get_session_factory()
    redis_client = agent._redis  # reuse agent's redis connection
    llm_client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    agent.tools = [
        make_get_topic_config(session_factory),
        make_query_topic_contents(session_factory, llm_client, settings.grok_fast_model),
        make_update_topic_summary(session_factory),
        make_set_pipeline_stage(redis_client),
    ]

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

"""Analyst agent entry point — skill-based ReAct loop with autonomous tool usage."""

import asyncio
import logging
import os
from pathlib import Path

from openai import AsyncOpenAI

from shared.agent.base import BaseAgent
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory
from shared.skills.loader import SkillLoader

from agent_analyst.executor import make_analyst_tools, make_skill_executor

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
    queue = agent._queue  # reuse agent's task queue
    llm_client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    # Load skills from markdown files
    skills_dir = Path(__file__).parent / "skills"
    skills = SkillLoader.load(skills_dir)
    logger.info("Loaded %d skills: %s", len(skills), [s.name for s in skills])

    # Create tools and skill-based executor
    agent.tools = make_analyst_tools(
        session_factory=session_factory,
        redis_client=redis_client,
        queue=queue,
        llm_client=llm_client,
        model=settings.grok_model,
        fast_model=settings.grok_fast_model,
    )
    agent.execute = make_skill_executor(
        agent=agent,
        skills=skills,
        session_factory=session_factory,
        redis_client=redis_client,
        llm_client=llm_client,
        fast_model=settings.grok_fast_model,
    )

    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

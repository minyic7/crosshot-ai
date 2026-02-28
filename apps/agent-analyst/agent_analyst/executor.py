"""Skill-based executor for the analyst agent.

Replaces the hardcoded pipeline with a ReAct loop guided by skill markdowns.
The executor wraps react() with pre-/post-processing for progress tracking.
"""

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from openai import AsyncOpenAI
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.agent.base import BaseAgent, Result
from shared.models.task import Task
from shared.queue.redis_queue import TaskQueue
from shared.skills.models import Skill
from shared.tools.base import Tool

from agent_analyst.prompts import build_analyst_system_prompt
from agent_analyst.tools.alert_tool import make_alert_tool
from agent_analyst.tools.dispatch_tool import make_dispatch_tool
from agent_analyst.tools.gap_tool import make_gap_tool
from agent_analyst.tools.integrate_tool import make_integrate_tool
from agent_analyst.tools.notes_tool import make_notes_tool
from agent_analyst.tools.overview_tool import make_overview_tool
from agent_analyst.tools.progress import set_progress_stage
from agent_analyst.tools.query import mark_detail_ready
from agent_analyst.tools.snapshot_tool import make_snapshot_tool
from agent_analyst.tools.summary import update_entity_summary
from agent_analyst.tools.triage_tool import make_triage_tool

logger = logging.getLogger(__name__)

# Human-friendly tool descriptions for progress UI
_TOOL_MESSAGES: dict[str, str] = {
    "query_entity_overview": "Reviewing entity status...",
    "triage_contents": "Classifying content relevance...",
    "integrate_contents": "Integrating new findings...",
    "analyze_gaps": "Detecting coverage gaps...",
    "dispatch_tasks": "Dispatching crawl tasks...",
    "query_topic_contents": "Reading collected content...",
    "save_metric_snapshot": "Recording metrics...",
    "query_analysis_notes": "Reading analysis notes...",
    "save_analysis_note": "Saving analysis note...",
    "manage_alerts": "Managing alerts...",
}


def make_analyst_tools(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: aioredis.Redis,
    queue: TaskQueue,
    llm_client: AsyncOpenAI,
    model: str,
    fast_model: str,
) -> list[Tool]:
    """Create all analyst tools with their dependencies."""
    return [
        make_overview_tool(session_factory),
        make_triage_tool(session_factory, llm_client, fast_model),
        make_integrate_tool(session_factory, llm_client, model),
        make_gap_tool(session_factory, llm_client, model),
        make_dispatch_tool(session_factory, redis_client, queue),
        # Memory tools (Phase 5)
        make_snapshot_tool(session_factory),
        make_notes_tool(session_factory),
        make_alert_tool(session_factory),
    ]


def make_skill_executor(
    agent: BaseAgent,
    skills: list[Skill],
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: aioredis.Redis,
    llm_client: AsyncOpenAI,
    fast_model: str,
):
    """Create a skill-based execute function that wraps react with pre/post processing.

    Returns an async callable compatible with BaseAgent.execute.
    """

    async def execute(task: Task) -> Result:
        entity_type, entity_id = _extract_entity(task)
        if not entity_id:
            return Result(data={"error": "No entity_id in task payload"})

        try:
            if task.label == "analyst:analyze":
                return await _handle_analyze(task, entity_type, entity_id)
            elif task.label == "analyst:summarize":
                return await _handle_summarize(task, entity_type, entity_id)
            else:
                logger.error("Unknown label: %s", task.label)
                return Result(data={"error": f"Unknown label: {task.label}"})
        except Exception as e:
            logger.error(
                "Executor failed for %s %s: %s", entity_type, entity_id, e,
                exc_info=True,
            )
            await set_progress_stage(
                redis_client, entity_id, "error",
                error_msg=str(e), entity_type=entity_type,
            )
            raise

    async def _handle_analyze(
        task: Task, entity_type: str, entity_id: str,
    ) -> Result:
        """Pre-process → ReAct → post-process for analyst:analyze tasks."""
        # Pre-processing: progress stage + chat rotation
        await set_progress_stage(
            redis_client, entity_id, "analyzing", entity_type=entity_type,
        )

        chat_insights = await _rotate_chat_period(entity_type, entity_id)
        if chat_insights:
            task.payload["chat_insights"] = chat_insights
            logger.info(
                "Chat insights for %s %s: %s",
                entity_type, entity_id, chat_insights[:100],
            )

        # Build per-task system prompt and run ReAct
        system_prompt = build_analyst_system_prompt(skills, task.label)

        async def on_step(tool_name: str, tool_args: dict) -> None:
            await _write_step_progress(entity_type, entity_id, tool_name, tool_args)

        result = await agent.react(task, system_prompt=system_prompt, on_step=on_step)

        # Post-processing: check if dispatch happened
        progress_key = f"{entity_type}:{entity_id}:progress"
        phase = await redis_client.hget(progress_key, "phase")

        if phase != "crawling":
            # No dispatch happened — finalize summary
            await update_entity_summary(
                session_factory,
                topic_id=entity_id if entity_type == "topic" else None,
                user_id=entity_id if entity_type == "user" else None,
                is_preliminary=False,
            )
            await set_progress_stage(
                redis_client, entity_id, "done", entity_type=entity_type,
            )
            logger.info(
                "Analyze complete for %s %s (no crawling needed)",
                entity_type, entity_id,
            )

        return result

    async def _handle_summarize(
        task: Task, entity_type: str, entity_id: str,
    ) -> Result:
        """Pre-process → ReAct → post-process for analyst:summarize tasks."""
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        # Pre-processing: upgrade detail_pending → detail_ready
        await mark_detail_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
        )

        # Build per-task system prompt and run ReAct
        system_prompt = build_analyst_system_prompt(skills, task.label)

        async def on_step(tool_name: str, tool_args: dict) -> None:
            await _write_step_progress(entity_type, entity_id, tool_name, tool_args)

        result = await agent.react(task, system_prompt=system_prompt, on_step=on_step)

        # Post-processing: update attached user stats, set progress done
        if topic_id:
            from agent_analyst.tools.topic import get_entity_config

            entity = await get_entity_config(
                session_factory, topic_id=topic_id,
            )
            attached_user_ids = [u["user_id"] for u in entity.get("users", [])]
            if attached_user_ids:
                await _update_attached_user_stats(attached_user_ids)

        await set_progress_stage(
            redis_client, entity_id, "done", entity_type=entity_type,
        )
        logger.info("Summarize complete for %s %s", entity_type, entity_id)
        return result

    # ── Helpers ──────────────────────────────────────

    async def _write_step_progress(
        entity_type: str, entity_id: str, tool_name: str, tool_args: dict,
    ) -> None:
        """Write a human-friendly progress message to Redis for the UI."""
        msg = _TOOL_MESSAGES.get(tool_name, f"Running {tool_name}...")
        progress_key = f"{entity_type}:{entity_id}:progress"
        await redis_client.hset(progress_key, "step", msg)

    async def _rotate_chat_period(entity_type: str, entity_id: str) -> str:
        """Archive chat messages and extract insights for the analysis cycle."""
        from shared.db.models import ChatMessageRow

        try:
            async with session_factory() as session:
                result = await session.execute(
                    select(ChatMessageRow)
                    .where(
                        ChatMessageRow.entity_type == entity_type,
                        ChatMessageRow.entity_id == entity_id,
                        ChatMessageRow.is_archived == False,  # noqa: E712
                    )
                    .order_by(ChatMessageRow.created_at)
                )
                rows = result.scalars().all()

                if not rows:
                    return ""

                convo_text = "\n".join(
                    f"{'User' if r.role == 'user' else 'Assistant'}: {r.content[:500]}"
                    for r in rows
                )

                # Archive messages
                await session.execute(
                    update(ChatMessageRow)
                    .where(
                        ChatMessageRow.entity_type == entity_type,
                        ChatMessageRow.entity_id == entity_id,
                        ChatMessageRow.is_archived == False,  # noqa: E712
                    )
                    .values(is_archived=True)
                )
                await session.commit()
                logger.info(
                    "Archived %d chat messages for %s %s",
                    len(rows), entity_type, entity_id,
                )

            # Summarize into insights
            response = await llm_client.chat.completions.create(
                model=fast_model,
                messages=[{
                    "role": "user",
                    "content": (
                        "Summarize this conversation between a user and an AI analyst "
                        "into 2-3 bullet points. Focus on: what topics/aspects the user "
                        "cares about, specific questions asked, any suggested focus areas. "
                        "Be concise. Write in the same language as the conversation.\n\n"
                        f"{convo_text[:3000]}"
                    ),
                }],
                temperature=0,
                max_tokens=300,
            )
            return (response.choices[0].message.content or "").strip()

        except Exception as e:
            logger.warning("Chat period rotation failed (non-fatal): %s", e)
            return ""

    async def _update_attached_user_stats(user_ids: list[str]) -> None:
        """Update last_crawl_at and total_contents for attached users."""
        from sqlalchemy import func

        from shared.db.models import ContentRow, UserRow

        try:
            async with session_factory() as session:
                for uid in user_ids:
                    user = await session.get(UserRow, uid)
                    if not user:
                        continue
                    count = await session.scalar(
                        select(func.count()).where(ContentRow.user_id == uid)
                    )
                    if count and count > 0:
                        user.total_contents = count
                        if not user.last_crawl_at:
                            user.last_crawl_at = datetime.now(timezone.utc)
                await session.commit()
            logger.info("Updated stats for %d attached users", len(user_ids))
        except Exception as e:
            logger.warning("Failed to update attached user stats: %s", e)

    return execute


def _extract_entity(task: Task) -> tuple[str, str | None]:
    """Extract (entity_type, entity_id) from task payload."""
    topic_id = task.payload.get("topic_id")
    if topic_id:
        return "topic", topic_id
    user_id = task.payload.get("user_id")
    if user_id:
        return "user", user_id
    return "unknown", None

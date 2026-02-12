"""Deterministic analyst pipeline — replaces the ReAct loop.

LLM is called only where real intelligence is needed:
1. Batch classification (in query_topic_contents, fast-model)
2. Analysis + summary writing (reasoning model, single call)

Everything else is deterministic Python code.
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.agent.base import Result
from shared.models.task import Task

from agent_analyst.prompts import SYSTEM_PROMPT, build_analyze_prompt, build_summarize_prompt
from agent_analyst.tools.pipeline import set_pipeline_stage
from agent_analyst.tools.query import query_topic_contents
from agent_analyst.tools.summary import update_entity_summary
from agent_analyst.tools.topic import get_entity_config

logger = logging.getLogger(__name__)


def _normalize_insights(analysis: dict) -> list[dict]:
    """Convert LLM output to uniform insight format.

    Handles both new format (insights: [{text, sentiment}])
    and legacy format (alerts: [str | {level, message}]).
    """
    # New format: insights with sentiment
    if "insights" in analysis:
        raw = analysis["insights"]
        if isinstance(raw, list):
            result = []
            for item in raw:
                if isinstance(item, dict) and "text" in item:
                    result.append({
                        "text": item["text"],
                        "sentiment": item.get("sentiment", "neutral"),
                    })
                elif isinstance(item, str):
                    result.append({"text": item, "sentiment": "neutral"})
            return result

    # Legacy format: alerts with severity levels
    if "alerts" in analysis:
        raw = analysis["alerts"]
        if isinstance(raw, list):
            result = []
            for item in raw:
                if isinstance(item, dict) and "message" in item:
                    level = item.get("level", "info")
                    sentiment = "negative" if level in ("critical", "warning") else "neutral"
                    result.append({"text": item["message"], "sentiment": sentiment})
                elif isinstance(item, str):
                    result.append({"text": item, "sentiment": "neutral"})
            return result

    return []


def make_pipeline(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: aioredis.Redis,
    llm_client: AsyncOpenAI,
    model: str,
    fast_model: str,
):
    """Create the analyst pipeline execute function.

    Returns an async callable compatible with BaseAgent.execute.
    """

    async def execute(task: Task) -> Result:
        if task.label == "analyst:analyze":
            return await _handle_analyze(task)
        elif task.label == "analyst:summarize":
            return await _handle_summarize(task)
        else:
            logger.error("Unknown label: %s", task.label)
            return Result(data={"error": f"Unknown label: {task.label}"})

    async def _handle_analyze(task: Task) -> Result:
        topic_id = task.payload.get("topic_id")
        user_id = task.payload.get("user_id")
        force_crawl = task.payload.get("force_crawl", False)

        # Determine entity type and ID for pipeline stages
        entity_type = "topic" if topic_id else "user"
        entity_id = topic_id or user_id
        logger.info("Pipeline analyze: %s_id=%s force_crawl=%s", entity_type, entity_id, force_crawl)

        # Step 1: Load entity config [CODE]
        entity = await get_entity_config(session_factory, topic_id=topic_id, user_id=user_id)
        if "error" in entity:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=entity["error"], entity_type=entity_type)
            return Result(data=entity)

        # Collect attached user IDs for content queries
        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]
        # Also include user IDs from the task payload (from scheduler/API)
        payload_users = task.payload.get("users", [])
        for pu in payload_users:
            uid = pu.get("user_id")
            if uid and uid not in attached_user_ids:
                attached_user_ids.append(uid)

        # Step 2: Query + classify contents [CODE + fast-model classification]
        data = await query_topic_contents(
            session_factory, llm_client, fast_model,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in data:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=data["error"], entity_type=entity_type)
            return Result(data=data)

        # Step 3: Detect data gaps [CODE — deterministic rules]
        gaps = _detect_gaps(entity, data, force_crawl)
        logger.info(
            "Gap detection: missing_platforms=%s stale=%s low_volume=%s force=%s",
            gaps["missing_platforms"], gaps["stale"], gaps["low_volume"], gaps["force_crawl"],
        )

        # Step 4: Set pipeline stage [CODE]
        await set_pipeline_stage(redis_client, entity_id, "analyzing", entity_type=entity_type)

        # Step 5: LLM analysis [SINGLE LLM CALL — the only reasoning call]
        analysis = await _llm_analyze(entity, data, gaps)

        # Step 6: Save summary [CODE]
        has_crawl_tasks = bool(analysis.get("crawl_tasks"))
        await update_entity_summary(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            summary=analysis.get("summary", ""),
            summary_data={
                "metrics": data["metrics"],
                "insights": _normalize_insights(analysis),
                "recommended_next_queries": analysis.get("recommended_next_queries", []),
            },
            total_contents=data["data_status"]["total_contents_all_time"],
            is_preliminary=has_crawl_tasks,
        )

        # Step 7: Dispatch or finish [CODE]
        if has_crawl_tasks:
            crawl_tasks = analysis["crawl_tasks"]
            new_tasks = _build_crawler_tasks(entity, crawl_tasks, task.parent_job_id)

            # Also add timeline tasks for attached users (topic mode)
            if topic_id:
                user_timeline_tasks = _build_user_timeline_tasks(
                    entity, payload_users, task.parent_job_id,
                )
                new_tasks.extend(user_timeline_tasks)

            await set_pipeline_stage(redis_client, entity_id, "crawling", total=len(new_tasks), entity_type=entity_type)
            logger.info("Dispatching %d crawler tasks for %s %s", len(new_tasks), entity_type, entity_id)
            return Result(data={"status": "crawling", "tasks": len(new_tasks)}, new_tasks=new_tasks)
        else:
            # Even if no keyword crawl tasks, dispatch timeline tasks for attached users
            new_tasks = []
            if topic_id:
                new_tasks = _build_user_timeline_tasks(entity, payload_users, task.parent_job_id)
            elif user_id:
                # Standalone user: always dispatch timeline crawl
                new_tasks = _build_user_timeline_tasks(entity, [], task.parent_job_id)

            if new_tasks:
                await set_pipeline_stage(redis_client, entity_id, "crawling", total=len(new_tasks), entity_type=entity_type)
                logger.info("Dispatching %d timeline tasks for %s %s", len(new_tasks), entity_type, entity_id)
                return Result(data={"status": "crawling", "tasks": len(new_tasks)}, new_tasks=new_tasks)

            await set_pipeline_stage(redis_client, entity_id, "done", entity_type=entity_type)
            logger.info("Analysis complete for %s %s (no crawling needed)", entity_type, entity_id)
            return Result(data={"status": "done"})

    async def _handle_summarize(task: Task) -> Result:
        topic_id = task.payload.get("topic_id")
        user_id = task.payload.get("user_id")
        entity_type = "topic" if topic_id else "user"
        entity_id = topic_id or user_id
        logger.info("Pipeline summarize: %s_id=%s", entity_type, entity_id)

        # Step 1: Load entity + query enriched data [CODE]
        entity = await get_entity_config(session_factory, topic_id=topic_id, user_id=user_id)
        if "error" in entity:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=entity["error"], entity_type=entity_type)
            return Result(data=entity)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

        data = await query_topic_contents(
            session_factory, llm_client, fast_model,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in data:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=data["error"], entity_type=entity_type)
            return Result(data=data)

        # Step 2: LLM final summary [SINGLE LLM CALL]
        analysis = await _llm_summarize(entity, data)

        # Step 3: Save final summary [CODE]
        await update_entity_summary(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            summary=analysis.get("summary", ""),
            summary_data={
                "metrics": data["metrics"],
                "insights": _normalize_insights(analysis),
                "recommended_next_queries": analysis.get("recommended_next_queries", []),
            },
            total_contents=data["data_status"]["total_contents_all_time"],
            is_preliminary=False,
        )

        # Step 4: Done [CODE]
        await set_pipeline_stage(redis_client, entity_id, "done", entity_type=entity_type)
        logger.info("Summarize complete for %s %s", entity_type, entity_id)
        return Result(data={"status": "done"})

    async def _llm_analyze(entity: dict, data: dict, gaps: dict) -> dict:
        """Single LLM call for analysis + crawl decisions."""
        prompt = build_analyze_prompt(entity, data, gaps)
        return await _call_llm(prompt)

    async def _llm_summarize(entity: dict, data: dict) -> dict:
        """Single LLM call for final summary."""
        prompt = build_summarize_prompt(entity, data)
        return await _call_llm(prompt)

    async def _call_llm(user_prompt: str) -> dict:
        """Make a single LLM call and parse structured JSON response."""
        try:
            response = await llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw = response.choices[0].message.content or "{}"
            result = json.loads(raw)
            logger.info("LLM analysis returned: summary=%d chars, crawl_tasks=%d",
                        len(result.get("summary", "")),
                        len(result.get("crawl_tasks", [])))
            return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response: %s", e)
            return {"summary": raw, "crawl_tasks": [], "insights": [{"text": f"JSON parse error: {e}", "sentiment": "negative"}]}
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return {"summary": "", "crawl_tasks": [], "insights": [{"text": f"LLM error: {e}", "sentiment": "negative"}]}

    return execute


def _detect_gaps(entity: dict, data: dict, force_crawl: bool) -> dict:
    """Deterministic gap detection — no LLM needed."""
    gaps: dict[str, Any] = {
        "missing_platforms": [],
        "stale": False,
        "low_volume": False,
        "force_crawl": force_crawl,
    }

    # Platform coverage: configured but no data
    coverage = data["data_status"]["platform_coverage"]
    for platform in entity.get("platforms", []):
        if platform not in coverage:
            gaps["missing_platforms"].append(platform)

    # Freshness: data older than 1.5x the configured interval
    hours_since = data["data_status"]["hours_since_newest_content"]
    interval = entity.get("config", {}).get("schedule_interval_hours", 6)
    if hours_since is not None and hours_since > interval * 1.5:
        gaps["stale"] = True

    # Volume: too few posts for meaningful analysis
    if data["metrics"]["total_contents"] < 10:
        gaps["low_volume"] = True

    # User-specific: check if users need timeline crawling
    if entity.get("users"):
        gaps["has_users"] = True

    return gaps


def _build_crawler_tasks(
    entity: dict,
    crawl_tasks: list[dict],
    parent_job_id: str | None,
) -> list[Task]:
    """Convert LLM's crawl_tasks into Task objects for the queue."""
    entity_id = entity["id"]
    entity_type = entity.get("type", "topic")

    tasks = []
    for ct in crawl_tasks:
        platform = ct.get("platform", "x")
        label = f"crawler:{platform}"
        payload: dict[str, Any] = {
            "query": ct.get("query", ""),
            "action": ct.get("action", "search"),
        }
        # Set the right entity ID
        if entity_type == "topic":
            payload["topic_id"] = entity_id
        else:
            payload["user_id"] = entity_id

        tasks.append(Task(
            label=label,
            payload=payload,
            parent_job_id=parent_job_id,
        ))
    return tasks


def _build_user_timeline_tasks(
    entity: dict,
    payload_users: list[dict],
    parent_job_id: str | None,
) -> list[Task]:
    """Build timeline crawl tasks for attached users (topic mode) or standalone user."""
    tasks = []
    entity_type = entity.get("type", "topic")

    if entity_type == "user":
        # Standalone user — one timeline task
        username = entity.get("username")
        if username:
            tasks.append(Task(
                label=f"crawler:{entity['platform']}",
                payload={
                    "action": "timeline",
                    "username": username,
                    "user_id": entity["id"],
                    "config": entity.get("config", {}),
                },
                parent_job_id=parent_job_id,
            ))
    else:
        # Topic mode — timeline tasks for each attached user
        users = payload_users or entity.get("users", [])
        for user in users:
            username = user.get("username")
            if not username:
                continue
            platform = user.get("platform", "x")
            tasks.append(Task(
                label=f"crawler:{platform}",
                payload={
                    "action": "timeline",
                    "username": username,
                    "user_id": user.get("user_id") or user.get("id"),
                    "topic_id": entity["id"],
                    "config": user.get("config", {}),
                },
                parent_job_id=parent_job_id,
            ))

    return tasks

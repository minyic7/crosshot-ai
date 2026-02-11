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
from agent_analyst.tools.summary import update_topic_summary
from agent_analyst.tools.topic import get_topic_config

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
        topic_id = task.payload["topic_id"]
        force_crawl = task.payload.get("force_crawl", False)
        logger.info("Pipeline analyze: topic_id=%s force_crawl=%s", topic_id, force_crawl)

        # Step 1: Load topic config [CODE]
        topic = await get_topic_config(session_factory, topic_id)
        if "error" in topic:
            await set_pipeline_stage(redis_client, topic_id, "error", error_msg=topic["error"])
            return Result(data=topic)

        # Step 2: Query + classify contents [CODE + fast-model classification]
        data = await query_topic_contents(session_factory, llm_client, fast_model, topic_id)
        if "error" in data:
            await set_pipeline_stage(redis_client, topic_id, "error", error_msg=data["error"])
            return Result(data=data)

        # Step 3: Detect data gaps [CODE — deterministic rules]
        gaps = _detect_gaps(topic, data, force_crawl)
        logger.info(
            "Gap detection: missing_platforms=%s stale=%s low_volume=%s force=%s",
            gaps["missing_platforms"], gaps["stale"], gaps["low_volume"], gaps["force_crawl"],
        )

        # Step 4: Set pipeline stage [CODE]
        await set_pipeline_stage(redis_client, topic_id, "analyzing")

        # Step 5: LLM analysis [SINGLE LLM CALL — the only reasoning call]
        analysis = await _llm_analyze(topic, data, gaps)

        # Step 6: Save summary [CODE]
        has_crawl_tasks = bool(analysis.get("crawl_tasks"))
        await update_topic_summary(
            session_factory,
            topic_id,
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
            new_tasks = _build_crawler_tasks(topic_id, crawl_tasks, task.parent_job_id)
            await set_pipeline_stage(redis_client, topic_id, "crawling", total=len(new_tasks))
            logger.info("Dispatching %d crawler tasks for topic %s", len(new_tasks), topic_id)
            return Result(data={"status": "crawling", "tasks": len(new_tasks)}, new_tasks=new_tasks)
        else:
            await set_pipeline_stage(redis_client, topic_id, "done")
            logger.info("Analysis complete for topic %s (no crawling needed)", topic_id)
            return Result(data={"status": "done"})

    async def _handle_summarize(task: Task) -> Result:
        topic_id = task.payload["topic_id"]
        logger.info("Pipeline summarize: topic_id=%s", topic_id)

        # Step 1: Load topic + query enriched data [CODE]
        topic = await get_topic_config(session_factory, topic_id)
        if "error" in topic:
            await set_pipeline_stage(redis_client, topic_id, "error", error_msg=topic["error"])
            return Result(data=topic)

        data = await query_topic_contents(session_factory, llm_client, fast_model, topic_id)
        if "error" in data:
            await set_pipeline_stage(redis_client, topic_id, "error", error_msg=data["error"])
            return Result(data=data)

        # Step 2: LLM final summary [SINGLE LLM CALL]
        analysis = await _llm_summarize(topic, data)

        # Step 3: Save final summary [CODE]
        await update_topic_summary(
            session_factory,
            topic_id,
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
        await set_pipeline_stage(redis_client, topic_id, "done")
        logger.info("Summarize complete for topic %s", topic_id)
        return Result(data={"status": "done"})

    async def _llm_analyze(topic: dict, data: dict, gaps: dict) -> dict:
        """Single LLM call for analysis + crawl decisions."""
        prompt = build_analyze_prompt(topic, data, gaps)
        return await _call_llm(prompt)

    async def _llm_summarize(topic: dict, data: dict) -> dict:
        """Single LLM call for final summary."""
        prompt = build_summarize_prompt(topic, data)
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


def _detect_gaps(topic: dict, data: dict, force_crawl: bool) -> dict:
    """Deterministic gap detection — no LLM needed."""
    gaps: dict[str, Any] = {
        "missing_platforms": [],
        "stale": False,
        "low_volume": False,
        "force_crawl": force_crawl,
    }

    # Platform coverage: configured but no data
    coverage = data["data_status"]["platform_coverage"]
    for platform in topic.get("platforms", []):
        if platform not in coverage:
            gaps["missing_platforms"].append(platform)

    # Freshness: data older than 1.5x the configured interval
    hours_since = data["data_status"]["hours_since_newest_content"]
    interval = topic.get("config", {}).get("schedule_interval_hours", 6)
    if hours_since is not None and hours_since > interval * 1.5:
        gaps["stale"] = True

    # Volume: too few posts for meaningful analysis
    if data["metrics"]["total_contents"] < 10:
        gaps["low_volume"] = True

    return gaps


def _build_crawler_tasks(
    topic_id: str,
    crawl_tasks: list[dict],
    parent_job_id: str | None,
) -> list[Task]:
    """Convert LLM's crawl_tasks into Task objects for the queue."""
    tasks = []
    for ct in crawl_tasks:
        platform = ct.get("platform", "x")
        label = f"crawler:{platform}"
        tasks.append(Task(
            label=label,
            payload={
                "topic_id": topic_id,
                "query": ct.get("query", ""),
                "action": ct.get("action", "search"),
            },
            parent_job_id=parent_job_id,
        ))
    return tasks

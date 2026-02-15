"""Incremental knowledge pipeline — replaces the stateless iteration-based analysis.

Pipeline stages:
1. Triage: batch LLM classifies unprocessed content (skip/brief/detail)
2. Integration: reasoning LLM updates knowledge document with new insights
3. Gap detection: deterministic rules find missing data
4. Gap analysis: reasoning LLM decides crawl tasks (only when gaps exist)

Knowledge persists in entity.summary_data["knowledge"] and grows incrementally.
"""

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.agent.base import Result
from shared.models.task import Task

from agent_analyst.prompts import (
    build_gap_analysis_prompt,
    build_integration_prompt,
    build_system_prompt,
    build_triage_prompt,
)
from agent_analyst.tools.pipeline import set_pipeline_stage
from agent_analyst.tools.query import (
    mark_contents_processed,
    mark_detail_ready,
    mark_integrated,
    query_entity_overview,
    query_integration_ready,
    query_unprocessed_contents,
)
from agent_analyst.tools.summary import update_entity_summary
from agent_analyst.tools.topic import get_entity_config

logger = logging.getLogger(__name__)


def _normalize_insights(analysis: dict) -> list[dict]:
    """Convert LLM output to uniform insight format."""
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

        entity_type = "topic" if topic_id else "user"
        entity_id = topic_id or user_id
        logger.info("Pipeline analyze: %s_id=%s force_crawl=%s", entity_type, entity_id, force_crawl)

        # Step 1: Load entity config
        entity = await get_entity_config(session_factory, topic_id=topic_id, user_id=user_id)
        if "error" in entity:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=entity["error"], entity_type=entity_type)
            return Result(data=entity)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]
        payload_users = task.payload.get("users", [])
        for pu in payload_users:
            uid = pu.get("user_id")
            if uid and uid not in attached_user_ids:
                attached_user_ids.append(uid)

        # Step 2: Query entity overview (metrics, data status)
        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in overview:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=overview["error"], entity_type=entity_type)
            return Result(data=overview)

        # Load existing knowledge document
        knowledge_doc = _get_knowledge_doc(entity)

        await set_pipeline_stage(redis_client, entity_id, "analyzing", entity_type=entity_type)

        # Step 3: Triage unprocessed content
        unprocessed = await query_unprocessed_contents(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        detail_content_ids = []
        if unprocessed:
            triage_results = await _llm_triage(entity, unprocessed)
            triage_updates, detail_content_ids = _process_triage_results(unprocessed, triage_results)
            await mark_contents_processed(session_factory, triage_updates)
            logger.info(
                "Triage: %d unprocessed → %d briefed, %d detail, %d skipped",
                len(unprocessed),
                sum(1 for u in triage_updates if u["status"] == "briefed"),
                sum(1 for u in triage_updates if u["status"] == "detail_pending"),
                sum(1 for u in triage_updates if u["status"] == "skipped"),
            )

        # Step 4: Query integration-ready content (briefed + detail_ready from previous cycles)
        integration_ready = await query_integration_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        # Step 5: Knowledge integration (if there's content to integrate)
        if integration_ready:
            analysis = await _llm_integrate(entity, overview, knowledge_doc, integration_ready)
            knowledge_doc = analysis.get("knowledge", knowledge_doc)

            # Save updated knowledge + summary
            await update_entity_summary(
                session_factory,
                topic_id=topic_id,
                user_id=user_id,
                summary=analysis.get("summary", ""),
                summary_data={
                    "knowledge": knowledge_doc,
                    "metrics": overview["metrics"],
                    "insights": _normalize_insights(analysis),
                    "recommended_next_queries": analysis.get("recommended_next_queries", []),
                },
                total_contents=overview["data_status"]["total_contents_all_time"],
                is_preliminary=True,  # may still dispatch crawl tasks
            )

            # Mark integrated
            integrated_ids = [p["id"] for p in integration_ready]
            await mark_integrated(session_factory, integrated_ids)
            logger.info("Integrated %d contents into knowledge", len(integrated_ids))

        # Step 6: Gap detection + crawl task building
        gaps = _detect_gaps(entity, overview, force_crawl)
        logger.info(
            "Gap detection: missing_platforms=%s stale=%s low_volume=%s force=%s",
            gaps["missing_platforms"], gaps["stale"], gaps["low_volume"], gaps["force_crawl"],
        )

        # Build crawler tasks
        new_tasks: list[Task] = []

        # Detail tasks from triage (analyst decides, not crawler)
        if detail_content_ids:
            detail_tasks = _build_detail_tasks(unprocessed, detail_content_ids, entity, task.parent_job_id)
            new_tasks.extend(detail_tasks)
            logger.info("Dispatching %d detail tasks from triage", len(detail_tasks))

        # Search tasks from gap analysis
        has_gaps = (gaps["missing_platforms"] or gaps["stale"] or gaps["low_volume"] or gaps["force_crawl"])
        if has_gaps:
            gap_analysis = await _llm_gap_analysis(entity, overview, gaps, knowledge_doc)
            crawl_tasks = gap_analysis.get("crawl_tasks", [])
            if crawl_tasks:
                search_tasks = _build_crawler_tasks(entity, crawl_tasks, task.parent_job_id)
                new_tasks.extend(search_tasks)
                logger.info("Dispatching %d search tasks from gap analysis", len(search_tasks))

        # Timeline tasks for attached users
        if topic_id:
            user_timeline_tasks = _build_user_timeline_tasks(entity, payload_users, task.parent_job_id)
            new_tasks.extend(user_timeline_tasks)
        elif user_id:
            user_timeline_tasks = _build_user_timeline_tasks(entity, [], task.parent_job_id)
            new_tasks.extend(user_timeline_tasks)

        # Step 7: Dispatch or finish
        if new_tasks:
            await set_pipeline_stage(redis_client, entity_id, "crawling", total=len(new_tasks), entity_type=entity_type)
            logger.info("Dispatching %d total crawler tasks for %s %s", len(new_tasks), entity_type, entity_id)
            return Result(data={"status": "crawling", "tasks": len(new_tasks)}, new_tasks=new_tasks)
        else:
            # If we integrated content but have no crawl tasks, we're done
            if not integration_ready:
                # Nothing to integrate, nothing to crawl — save what we have
                await update_entity_summary(
                    session_factory,
                    topic_id=topic_id,
                    user_id=user_id,
                    summary=entity.get("last_summary", ""),
                    summary_data={
                        "knowledge": knowledge_doc,
                        "metrics": overview["metrics"],
                        "insights": [],
                        "recommended_next_queries": entity.get("previous_recommendations", []),
                    },
                    total_contents=overview["data_status"]["total_contents_all_time"],
                    is_preliminary=False,
                )
            else:
                # Mark as final (was preliminary before)
                await update_entity_summary(
                    session_factory,
                    topic_id=topic_id,
                    user_id=user_id,
                    is_preliminary=False,
                )

            await set_pipeline_stage(redis_client, entity_id, "done", entity_type=entity_type)
            logger.info("Analysis complete for %s %s (no crawling needed)", entity_type, entity_id)
            return Result(data={"status": "done"})

    async def _handle_summarize(task: Task) -> Result:
        """Post-crawl integration — triggered after fan-in from crawler tasks."""
        topic_id = task.payload.get("topic_id")
        user_id = task.payload.get("user_id")
        entity_type = "topic" if topic_id else "user"
        entity_id = topic_id or user_id
        logger.info("Pipeline summarize: %s_id=%s", entity_type, entity_id)

        # Step 1: Load entity + knowledge
        entity = await get_entity_config(session_factory, topic_id=topic_id, user_id=user_id)
        if "error" in entity:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=entity["error"], entity_type=entity_type)
            return Result(data=entity)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]
        knowledge_doc = _get_knowledge_doc(entity)

        # Step 2: Upgrade detail_pending → detail_ready (crawlers have returned)
        await mark_detail_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        # Step 3: Triage any new unprocessed content (from search/timeline crawls)
        unprocessed = await query_unprocessed_contents(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if unprocessed:
            triage_results = await _llm_triage(entity, unprocessed)
            triage_updates, _ = _process_triage_results(unprocessed, triage_results)
            # In summarize, don't dispatch more detail tasks — just brief everything
            for upd in triage_updates:
                if upd["status"] == "detail_pending":
                    upd["status"] = "briefed"
            await mark_contents_processed(session_factory, triage_updates)
            logger.info("Summarize triage: %d new contents processed", len(unprocessed))

        # Step 4: Query all integration-ready content
        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in overview:
            await set_pipeline_stage(redis_client, entity_id, "error", error_msg=overview["error"], entity_type=entity_type)
            return Result(data=overview)

        integration_ready = await query_integration_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        # Step 5: Knowledge integration
        if integration_ready:
            analysis = await _llm_integrate(entity, overview, knowledge_doc, integration_ready)
            knowledge_doc = analysis.get("knowledge", knowledge_doc)

            integrated_ids = [p["id"] for p in integration_ready]
            await mark_integrated(session_factory, integrated_ids)
            logger.info("Summarize: integrated %d contents", len(integrated_ids))
        else:
            # No new content — just re-render summary from existing knowledge
            analysis = {"summary": "", "insights": [], "recommended_next_queries": []}

        # Step 6: Save final summary
        summary = analysis.get("summary", "") or entity.get("last_summary", "")
        await update_entity_summary(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            summary=summary,
            summary_data={
                "knowledge": knowledge_doc,
                "metrics": overview["metrics"],
                "insights": _normalize_insights(analysis),
                "recommended_next_queries": analysis.get("recommended_next_queries", []),
            },
            total_contents=overview["data_status"]["total_contents_all_time"],
            is_preliminary=False,
        )

        await set_pipeline_stage(redis_client, entity_id, "done", entity_type=entity_type)
        logger.info("Summarize complete for %s %s", entity_type, entity_id)
        return Result(data={"status": "done"})

    # ── LLM calls ──────────────────────────────────────

    async def _llm_triage(entity: dict, posts: list[dict]) -> list[dict]:
        """Batch triage using fast model."""
        prompt = build_triage_prompt(entity, posts)
        try:
            response = await llm_client.chat.completions.create(
                model=fast_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            raw = response.choices[0].message.content or "[]"
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            results = json.loads(raw)
            if not isinstance(results, list) or len(results) != len(posts):
                logger.warning(
                    "Triage length mismatch: got %d, expected %d. Defaulting to brief.",
                    len(results) if isinstance(results, list) else 0,
                    len(posts),
                )
                return [{"d": "brief", "kp": None} for _ in posts]
            return results
        except Exception as e:
            logger.warning("Triage LLM call failed (%s), defaulting to brief", e)
            return [{"d": "brief", "kp": None} for _ in posts]

    async def _llm_integrate(entity: dict, overview: dict, knowledge_doc: str, content: list[dict]) -> dict:
        """Knowledge integration using reasoning model."""
        prompt = build_integration_prompt(entity, overview, knowledge_doc, content)
        return await _call_reasoning_llm(prompt)

    async def _llm_gap_analysis(entity: dict, overview: dict, gaps: dict, knowledge_doc: str) -> dict:
        """Gap analysis using reasoning model."""
        prompt = build_gap_analysis_prompt(entity, overview, gaps, knowledge_doc)
        return await _call_reasoning_llm(prompt)

    async def _call_reasoning_llm(user_prompt: str) -> dict:
        """Make a single reasoning LLM call and parse JSON response."""
        try:
            response = await llm_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw = response.choices[0].message.content or "{}"
            result = json.loads(raw)
            logger.info(
                "Reasoning LLM: knowledge=%d chars, summary=%d chars",
                len(result.get("knowledge", "")),
                len(result.get("summary", "")),
            )
            return result
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON: %s", e)
            return {"summary": raw, "knowledge": "", "insights": [{"text": f"JSON parse error: {e}", "sentiment": "negative"}]}
        except Exception as e:
            logger.error("Reasoning LLM call failed: %s", e)
            return {"summary": "", "knowledge": "", "insights": [{"text": f"LLM error: {e}", "sentiment": "negative"}]}

    return execute


# ── Helpers ──────────────────────────────────────


def _get_knowledge_doc(entity: dict) -> str:
    """Extract knowledge document from entity's summary_data."""
    summary_data = entity.get("summary_data") or {}
    if isinstance(summary_data, dict):
        return summary_data.get("knowledge", "")
    return ""


def _process_triage_results(
    posts: list[dict],
    triage_results: list[dict],
) -> tuple[list[dict], list[str]]:
    """Convert triage LLM output to mark_contents_processed updates.

    Returns (updates_list, detail_content_ids).
    """
    updates = []
    detail_ids = []

    for post, tri in zip(posts, triage_results):
        decision = tri.get("d", "brief")
        key_points = tri.get("kp")

        if decision == "skip":
            updates.append({"id": post["id"], "status": "skipped", "key_points": None})
        elif decision == "detail":
            updates.append({"id": post["id"], "status": "detail_pending", "key_points": key_points})
            detail_ids.append(post["id"])
        else:
            # "brief" or unknown — default to brief
            updates.append({"id": post["id"], "status": "briefed", "key_points": key_points})

    return updates, detail_ids


def _detect_gaps(entity: dict, overview: dict, force_crawl: bool) -> dict:
    """Deterministic gap detection — no LLM needed."""
    gaps: dict[str, Any] = {
        "missing_platforms": [],
        "stale": False,
        "low_volume": False,
        "force_crawl": force_crawl,
    }

    coverage = overview["data_status"]["platform_coverage"]
    for platform in entity.get("platforms", []):
        if platform not in coverage:
            gaps["missing_platforms"].append(platform)

    hours_since = overview["data_status"]["hours_since_newest_content"]
    interval = entity.get("config", {}).get("schedule_interval_hours", 6)
    if hours_since is not None and hours_since > interval * 1.5:
        gaps["stale"] = True

    if overview["metrics"]["total_contents"] < 10:
        gaps["low_volume"] = True

    return gaps


def _build_detail_tasks(
    posts: list[dict],
    detail_content_ids: list[str],
    entity: dict,
    parent_job_id: str | None,
) -> list[Task]:
    """Build crawler tasks for content that triage marked as 'detail'.

    These tasks fetch tweet replies/comments for deeper analysis.
    """
    detail_posts = {p["id"]: p for p in posts if p["id"] in detail_content_ids}
    entity_id = entity["id"]
    entity_type = entity.get("type", "topic")

    tasks = []
    for content_id, post in detail_posts.items():
        # Extract tweet_id from source_url (e.g., https://x.com/user/status/12345)
        tweet_id = None
        url = post.get("url", "")
        if "/status/" in url:
            tweet_id = url.split("/status/")[-1].split("?")[0].split("/")[0]

        if not tweet_id:
            continue

        payload: dict[str, Any] = {
            "action": "tweet",
            "tweet_id": tweet_id,
            "username": post.get("author", ""),
            "max_replies": 20,
            "source": "triage_detail",
        }
        if entity_type == "topic":
            payload["topic_id"] = entity_id
        else:
            payload["user_id"] = entity_id

        tasks.append(Task(
            label=f"crawler:{post.get('platform', 'x')}",
            payload=payload,
            parent_job_id=parent_job_id,
        ))

    return tasks


def _build_crawler_tasks(
    entity: dict,
    crawl_tasks: list[dict],
    parent_job_id: str | None,
) -> list[Task]:
    """Convert LLM's crawl_tasks into Task objects."""
    entity_id = entity["id"]
    entity_type = entity.get("type", "topic")

    tasks = []
    for ct in crawl_tasks:
        platform = ct.get("platform", "x")
        payload: dict[str, Any] = {
            "query": ct.get("query", ""),
            "action": ct.get("action", "search"),
        }
        if entity_type == "topic":
            payload["topic_id"] = entity_id
        else:
            payload["user_id"] = entity_id

        tasks.append(Task(
            label=f"crawler:{platform}",
            payload=payload,
            parent_job_id=parent_job_id,
        ))
    return tasks


def _build_user_timeline_tasks(
    entity: dict,
    payload_users: list[dict],
    parent_job_id: str | None,
) -> list[Task]:
    """Build timeline crawl tasks for attached users or standalone user."""
    tasks = []
    entity_type = entity.get("type", "topic")

    if entity_type == "user":
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

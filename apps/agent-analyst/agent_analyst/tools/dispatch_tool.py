"""Tool: dispatch_tasks — build and dispatch crawl tasks to crawler/searcher agents."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.models.task import Task, TaskPriority
from shared.queue.redis_queue import TaskQueue
from shared.tools.base import Tool

from agent_analyst.tools.progress import set_progress_stage
from agent_analyst.tools.query import query_unprocessed_contents
from agent_analyst.tools.topic import get_entity_config

logger = logging.getLogger(__name__)


def make_dispatch_tool(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: aioredis.Redis,
    queue: TaskQueue,
) -> Tool:
    """Create the dispatch_tasks tool."""

    async def dispatch_tasks(
        entity_type: str,
        entity_id: str,
        crawl_tasks: list[dict] | None = None,
        detail_content_ids: list[str] | None = None,
        include_timelines: bool = True,
        parent_job_id: str | None = None,
    ) -> str:
        """Build and dispatch crawl tasks to crawler/searcher agents.

        Sets up fan-in so analyst:summarize is triggered when all complete.
        """
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id
        )
        if "error" in entity:
            return json.dumps(entity, ensure_ascii=False)

        new_tasks: list[Task] = []

        # 1. Detail tasks from triage (fetch tweet replies/comments)
        if detail_content_ids:
            unprocessed = await query_unprocessed_contents(
                session_factory,
                topic_id=topic_id,
                user_id=user_id,
            )
            # Build detail tasks from the content that was marked for detail
            all_posts = {p["id"]: p for p in (unprocessed or [])}
            for content_id in detail_content_ids:
                post = all_posts.get(content_id)
                if not post:
                    continue
                tweet_id = _extract_tweet_id(post.get("url", ""))
                if not tweet_id:
                    continue

                payload: dict[str, Any] = {
                    "action": "tweet",
                    "tweet_id": tweet_id,
                    "username": post.get("author", ""),
                    "max_replies": 20,
                    "source": "triage_detail",
                }
                if topic_id:
                    payload["topic_id"] = entity_id
                else:
                    payload["user_id"] = entity_id

                new_tasks.append(Task(
                    label=f"crawler:{post.get('platform', 'x')}",
                    payload=payload,
                    parent_job_id=parent_job_id,
                    from_agent="analyst",
                ))

        # 2. Search/crawl tasks from gap analysis
        if crawl_tasks:
            for ct in crawl_tasks:
                platform = ct.get("platform", "x")
                payload = {
                    "query": ct.get("query", ""),
                    "action": ct.get("action", "search"),
                }
                if topic_id:
                    payload["topic_id"] = entity_id
                else:
                    payload["user_id"] = entity_id

                if platform == "web":
                    payload["name"] = entity.get("name", "")
                    payload["keywords"] = entity.get("keywords", [])
                    label = "searcher:web"
                else:
                    label = f"crawler:{platform}"

                new_tasks.append(Task(
                    label=label,
                    payload=payload,
                    parent_job_id=parent_job_id,
                    from_agent="analyst",
                ))

        # 3. Timeline tasks for attached users
        if include_timelines:
            timeline_tasks = _build_timeline_tasks(entity, parent_job_id)
            new_tasks.extend(timeline_tasks)

        if not new_tasks:
            return json.dumps({
                "status": "no_tasks",
                "message": "No crawl tasks to dispatch",
            }, ensure_ascii=False)

        # Set up fan-in progress tracking
        await set_progress_stage(
            redis_client,
            entity_id,
            "crawling",
            total=len(new_tasks),
            entity_type=entity_type,
        )

        # Push all tasks to queue and track IDs for child result collection
        task_ids: list[str] = []
        for t in new_tasks:
            await queue.push(t)
            task_ids.append(t.id)

        # Store task IDs in Redis for fan-in child result collection
        task_ids_key = f"{entity_type}:{entity_id}:task_ids"
        await redis_client.delete(task_ids_key)
        await redis_client.sadd(task_ids_key, *task_ids)
        await redis_client.expire(task_ids_key, 86400)

        logger.info(
            "Dispatched %d tasks for %s %s", len(new_tasks), entity_type, entity_id
        )

        return json.dumps({
            "status": "dispatched",
            "total_tasks": len(new_tasks),
            "breakdown": _count_by_label(new_tasks),
        }, ensure_ascii=False)

    return Tool(
        name="dispatch_tasks",
        description=(
            "Build and dispatch crawl tasks to crawler/searcher agents. "
            "Sets up fan-in so analyst:summarize is triggered when all tasks complete. "
            "Pass crawl_tasks from analyze_gaps and detail_content_ids from triage_contents."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["topic", "user"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the topic or user",
                },
                "crawl_tasks": {
                    "type": "array",
                    "description": "Crawl tasks from gap analysis [{platform, query, action}]",
                    "items": {"type": "object"},
                },
                "detail_content_ids": {
                    "type": "array",
                    "description": "Content IDs to fetch detailed replies for (from triage)",
                    "items": {"type": "string"},
                },
                "include_timelines": {
                    "type": "boolean",
                    "description": "Include user timeline crawl tasks",
                    "default": True,
                },
                "parent_job_id": {
                    "type": "string",
                    "description": "Parent job ID for task grouping",
                },
            },
            "required": ["entity_type", "entity_id"],
        },
        func=dispatch_tasks,
    )


def _extract_tweet_id(url: str) -> str | None:
    """Extract tweet ID from a status URL."""
    if "/status/" in url:
        return url.split("/status/")[-1].split("?")[0].split("/")[0]
    return None


def _build_timeline_tasks(entity: dict, parent_job_id: str | None) -> list[Task]:
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
                from_agent="analyst",
            ))
    else:
        for user in entity.get("users", []):
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
                from_agent="analyst",
            ))

    return tasks


def _count_by_label(tasks: list[Task]) -> dict[str, int]:
    """Count tasks by label."""
    counts: dict[str, int] = {}
    for t in tasks:
        counts[t.label] = counts.get(t.label, 0) + 1
    return counts

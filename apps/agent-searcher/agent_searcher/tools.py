"""Tools for the searcher agent — web search, existing data query, and result saving."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.config.settings import Settings
from shared.db.models import ContentRow, TaskRow
from shared.search import index_contents
from shared.tools.base import Tool

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def make_tools(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    agent: Any,
) -> list[Tool]:
    """Create the searcher tool set.

    The agent reference is needed so tools can read the current task context.
    """

    async def _web_search(
        query: str,
        count: int = 10,
        allowed_domains: list[str] | None = None,
        excluded_domains: list[str] | None = None,
    ) -> str:
        """Search the web using Brave Search API."""
        if not settings.brave_api_key:
            return "Error: BRAVE_API_KEY not configured."

        # Apply domain filters to query string
        effective_query = query
        if allowed_domains:
            sites = " OR ".join(f"site:{d}" for d in allowed_domains[:5])
            effective_query = f"{query} ({sites})"
        if excluded_domains:
            exclusions = " ".join(f"-site:{d}" for d in excluded_domains[:5])
            effective_query = f"{effective_query} {exclusions}"

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    BRAVE_SEARCH_URL,
                    params={"q": effective_query, "count": min(count, 20)},
                    headers={
                        "X-Subscription-Token": settings.brave_api_key,
                        "Accept": "application/json",
                    },
                )
                if resp.status_code == 429:
                    return "Rate limited. Wait before searching again."
                resp.raise_for_status()

                data = resp.json()
                results = []
                for item in data.get("web", {}).get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("description", ""),
                        "site_name": item.get("meta_url", {}).get("hostname", ""),
                        "age": item.get("age", ""),
                    })
                return json.dumps(results, ensure_ascii=False)
        except httpx.HTTPStatusError as e:
            return f"Search failed: HTTP {e.response.status_code}"
        except Exception as e:
            return f"Search failed: {e}"

    async def _query_existing(
        topic_id: str | None = None,
        user_id: str | None = None,
        query: str | None = None,
    ) -> str:
        """Query existing data in our database for a topic or user."""
        if not topic_id and not user_id:
            return "Error: provide either topic_id or user_id."

        try:
            async with session_factory() as session:
                # Build base filter
                filters = []
                if topic_id:
                    filters.append(ContentRow.topic_id == topic_id)
                if user_id:
                    filters.append(ContentRow.user_id == user_id)

                # Count by platform
                platform_counts = await session.execute(
                    select(ContentRow.platform, func.count())
                    .where(*filters)
                    .group_by(ContentRow.platform)
                )
                platforms = {row[0]: row[1] for row in platform_counts}
                total = sum(platforms.values())

                # Get recent content titles/text
                recent = await session.execute(
                    select(
                        ContentRow.text,
                        ContentRow.author_username,
                        ContentRow.platform,
                        ContentRow.crawled_at,
                    )
                    .where(*filters)
                    .order_by(ContentRow.crawled_at.desc())
                    .limit(10)
                )
                recent_items = []
                newest_at = None
                for row in recent:
                    text_preview = (row[0] or "")[:100]
                    recent_items.append(
                        f"[@{row[1] or '?'}] ({row[2]}) {text_preview}"
                    )
                    if newest_at is None and row[3]:
                        newest_at = row[3]

                hours_since = None
                if newest_at:
                    delta = datetime.now(timezone.utc) - newest_at.replace(tzinfo=timezone.utc)
                    hours_since = round(delta.total_seconds() / 3600, 1)

            summary = {
                "total_contents": total,
                "platforms": platforms,
                "recent_items": recent_items,
                "hours_since_newest": hours_since,
            }

            # If a text query is provided, also search OpenSearch
            if query:
                try:
                    from shared.search import search_contents

                    ids, os_total = await search_contents(
                        query,
                        topic_id=topic_id,
                        user_id=user_id,
                        limit=5,
                    )
                    summary["search_matches"] = os_total
                    summary["search_note"] = (
                        f"Found {os_total} matching items in OpenSearch for '{query}'"
                    )
                except Exception as e:
                    summary["search_error"] = str(e)

            return json.dumps(summary, ensure_ascii=False, default=str)
        except Exception as e:
            return f"Query failed: {e}"

    async def _save_results(
        topic_id: str | None = None,
        user_id: str | None = None,
        results: list[dict] | None = None,
    ) -> str:
        """Save web search findings to the database."""
        if not results:
            return "No results to save."
        if not topic_id and not user_id:
            return "Error: provide either topic_id or user_id."

        task = agent._current_task
        if not task:
            return "Error: no current task context."

        saved = 0
        content_ids = []
        try:
            async with session_factory() as session:
                # Ensure task row exists (FK requirement)
                await session.execute(
                    pg_insert(TaskRow).values(
                        id=task.id,
                        label=task.label,
                        priority=task.priority,
                        payload=task.payload,
                    ).on_conflict_do_nothing(index_elements=["id"])
                )

                for item in results:
                    url = item.get("url", "")
                    if not url:
                        continue

                    content_id = str(uuid4())
                    # Deterministic platform_content_id from URL for dedup
                    platform_content_id = hashlib.sha256(url.encode()).hexdigest()[:32]

                    stmt = pg_insert(ContentRow).values(
                        id=content_id,
                        task_id=task.id,
                        topic_id=topic_id,
                        user_id=user_id,
                        platform="web",
                        platform_content_id=platform_content_id,
                        source_url=url,
                        author_display_name=item.get("site_name", ""),
                        text=item.get("snippet", ""),
                        data={
                            "title": item.get("title", ""),
                            "description": item.get("snippet", ""),
                            "url": url,
                            "site_name": item.get("site_name", ""),
                            "age": item.get("age", ""),
                        },
                        metrics={},
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["platform", "platform_content_id"],
                        set_={
                            "text": stmt.excluded.text,
                            "data": stmt.excluded.data,
                        },
                    )
                    await session.execute(stmt)
                    content_ids.append(content_id)
                    saved += 1

                await session.commit()

            # Index to OpenSearch (best-effort)
            try:
                os_docs = []
                for i, item in enumerate(results):
                    if i < len(content_ids):
                        os_docs.append({
                            "id": content_ids[i],
                            "topic_id": topic_id,
                            "user_id": user_id,
                            "platform": "web",
                            "text": item.get("snippet", ""),
                            "author_display_name": item.get("site_name", ""),
                            "crawled_at": datetime.now(timezone.utc).isoformat(),
                        })
                await index_contents(os_docs)
            except Exception as e:
                logger.warning("OpenSearch index failed (non-fatal): %s", e)

            return f"Saved {saved} results to database."
        except Exception as e:
            return f"Save failed: {e}"

    return [
        Tool(
            name="web_search",
            description=(
                "Search the web using Brave Search. Returns titles, URLs, and snippets. "
                "Use allowed_domains to restrict to specific sites (e.g., reuters.com). "
                "Use excluded_domains to skip low-quality sites."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in natural language",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results (1-20, default 10)",
                    },
                    "allowed_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Only return results from these domains (max 5). "
                            "E.g. ['reuters.com', 'bloomberg.com']"
                        ),
                    },
                    "excluded_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Exclude results from these domains. "
                            "E.g. ['pinterest.com', 'quora.com']"
                        ),
                    },
                },
                "required": ["query"],
            },
            func=_web_search,
        ),
        Tool(
            name="query_existing",
            description=(
                "Search the existing database for content already collected about a topic or user. "
                "Use this FIRST to understand what data we already have before searching the web. "
                "Provide topic_id or user_id from the task payload."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "topic_id": {
                        "type": "string",
                        "description": "Topic ID from the task payload",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID from the task payload",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional text query to search within existing content",
                    },
                },
            },
            func=_query_existing,
        ),
        Tool(
            name="save_results",
            description=(
                "Save web search findings to the database. Only save high-quality, relevant results. "
                "Provide topic_id or user_id from the task payload."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "topic_id": {
                        "type": "string",
                        "description": "Topic ID from the task payload",
                    },
                    "user_id": {
                        "type": "string",
                        "description": "User ID from the task payload",
                    },
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "url": {"type": "string"},
                                "snippet": {"type": "string"},
                                "site_name": {"type": "string"},
                            },
                            "required": ["title", "url", "snippet"],
                        },
                        "description": "Array of search result objects to save",
                    },
                },
                "required": ["results"],
            },
            func=_save_results,
        ),
    ]

"""Tools for the searcher agent — web search, existing data query, and result saving."""

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tavily import AsyncTavilyClient

from shared.config.settings import Settings
from shared.db.models import ContentRow, TaskRow
from shared.search import index_contents
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_tools(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    agent: Any,
) -> list[Tool]:
    """Create the searcher tool set.

    The agent reference is needed so tools can read the current task context.
    """
    tavily = AsyncTavilyClient(api_key=settings.tavily_api_key) if settings.tavily_api_key else None

    async def _web_search(
        query: str,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        topic: str = "general",
        time_range: str | None = None,
    ) -> str:
        """Search the web using Tavily Search API."""
        if not tavily:
            return "Error: TAVILY_API_KEY not configured."

        try:
            kwargs: dict[str, Any] = {
                "max_results": min(max_results, 20),
                "topic": topic,
            }
            if include_domains:
                kwargs["include_domains"] = include_domains
            if exclude_domains:
                kwargs["exclude_domains"] = exclude_domains
            if time_range:
                kwargs["time_range"] = time_range

            response = await tavily.search(query, **kwargs)

            results = []
            for item in response.get("results", []):
                url = item.get("url", "")
                results.append({
                    "title": item.get("title", ""),
                    "url": url,
                    "content": item.get("content", ""),
                    "score": item.get("score", 0),
                    "site_name": urlparse(url).hostname or "",
                    "published_date": item.get("published_date", ""),
                })
            return json.dumps(results, ensure_ascii=False)
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
                filters = []
                if topic_id:
                    filters.append(ContentRow.topic_id == topic_id)
                if user_id:
                    filters.append(ContentRow.user_id == user_id)

                platform_counts = await session.execute(
                    select(ContentRow.platform, func.count())
                    .where(*filters)
                    .group_by(ContentRow.platform)
                )
                platforms = {row[0]: row[1] for row in platform_counts}
                total = sum(platforms.values())

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
        saved_items: list[tuple[str, dict]] = []  # (actual_id, item) pairs
        try:
            async with session_factory() as session:
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
                        text=item.get("content", ""),
                        data={
                            "title": item.get("title", ""),
                            "content": item.get("content", ""),
                            "url": url,
                            "site_name": item.get("site_name", ""),
                            "score": item.get("score", 0),
                            "published_date": item.get("published_date", ""),
                        },
                        metrics={},
                    )
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["platform", "platform_content_id"],
                        set_={
                            "text": stmt.excluded.text,
                            "data": stmt.excluded.data,
                        },
                    ).returning(ContentRow.id)
                    result_row = await session.execute(stmt)
                    actual_id = str(result_row.scalar())
                    saved_items.append((actual_id, item))
                    saved += 1

                await session.commit()

            # Index to OpenSearch using actual row IDs (not phantom UUIDs)
            try:
                os_docs = [
                    {
                        "id": actual_id,
                        "topic_id": topic_id,
                        "user_id": user_id,
                        "platform": "web",
                        "text": item.get("content", ""),
                        "author_display_name": item.get("site_name", ""),
                        "crawled_at": datetime.now(timezone.utc).isoformat(),
                    }
                    for actual_id, item in saved_items
                ]
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
                "Search the web using Tavily. Returns titles, URLs, content snippets, and relevance scores. "
                "Use include_domains to restrict to specific sites (e.g., reuters.com). "
                "Use exclude_domains to skip low-quality sites. "
                "Set topic to 'news' for recent news or 'finance' for financial data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in natural language",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (1-20, default 10)",
                    },
                    "include_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Only return results from these domains. "
                            "E.g. ['reuters.com', 'bloomberg.com']"
                        ),
                    },
                    "exclude_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Exclude results from these domains. "
                            "E.g. ['pinterest.com', 'quora.com']"
                        ),
                    },
                    "topic": {
                        "type": "string",
                        "enum": ["general", "news", "finance"],
                        "description": "Search topic category (default: general)",
                    },
                    "time_range": {
                        "type": "string",
                        "enum": ["day", "week", "month", "year"],
                        "description": "Filter results by recency",
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
                                "content": {"type": "string"},
                                "site_name": {"type": "string"},
                                "score": {"type": "number"},
                            },
                            "required": ["title", "url", "content"],
                        },
                        "description": "Array of search result objects to save",
                    },
                },
                "required": ["results"],
            },
            func=_save_results,
        ),
    ]

"""XExecutor — platform executor for X (Twitter) crawling tasks.

Dispatches by task.payload["action"]:
- "search": Generate/validate query → execute search → return tweets
- "tweet": Fetch a single tweet by URL/ID (+ replies / hot comments)
- "timeline": Fetch a user's timeline (incremental, target-driven)

Each action: acquire cookie → open stealth browser → run action → save content → report.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import redis.asyncio as aioredis
from openai import AsyncOpenAI

from shared.config import get_settings
from shared.models.task import Task
from shared.services.cookies_service import CookiesService

from ..base import BasePlatformExecutor
from ...services.media_downloader import download_media_batch
from .actions.search import search_tweets
from .actions.timeline import fetch_timeline
from .actions.tweet import fetch_tweet
from .browser import ProxyConfig, XBrowserSession
from .errors import ContentNotFoundError, NoCookiesAvailable, XCrawlerError
from .query_builder import QueryValidationError, XQueryBuilder
from .query_generator import QueryGenerator

logger = logging.getLogger(__name__)


class XExecutor(BasePlatformExecutor):
    """Execute X platform crawling tasks."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        grok_api_key: str = "",
        grok_base_url: str = "https://api.x.ai/v1",
        grok_model: str = "grok-beta",
    ) -> None:
        self._redis = redis_client
        self._cookies_service = CookiesService(redis_client)
        self._proxy = self._load_proxy()

        # AI query generator (lazy — only used for intent mode)
        self._grok_api_key = grok_api_key
        self._grok_base_url = grok_base_url
        self._grok_model = grok_model
        self._query_generator: QueryGenerator | None = None

    @property
    def platform(self) -> str:
        return "x"

    async def run(self, task: Task) -> dict[str, Any]:
        """Dispatch task by action."""
        action = task.payload.get("action")
        if not action:
            raise ValueError("Task payload missing 'action' field")

        # Acquire cookie
        cookie = await self._cookies_service.acquire("x")
        if cookie is None:
            raise NoCookiesAvailable("No active cookies for platform 'x'")

        try:
            async with XBrowserSession(cookies=cookie, proxy=self._proxy) as session:
                if action == "search":
                    result = await self._handle_search(session, task)
                elif action == "tweet":
                    result = await self._handle_tweet(session, task)
                elif action == "timeline":
                    result = await self._handle_timeline(session, task)
                else:
                    raise ValueError(f"Unknown action: {action}")

            await self._cookies_service.report_success(cookie)

            # Download media AFTER browser closes (frees memory for downloads)
            all_content_ids = (
                result.get("content_ids", [])
                + result.get("reply_content_ids", [])
            )
            await self._download_and_update_media(all_content_ids)

            return result

        except (ContentNotFoundError, QueryValidationError):
            # Not a cookie problem — still report success
            await self._cookies_service.report_success(cookie)
            raise

        except XCrawlerError:
            await self._cookies_service.report_failure(cookie)
            raise

    # ──────────────────────────────────────
    # Action handlers
    # ──────────────────────────────────────

    async def _handle_search(
        self, session: XBrowserSession, task: Task,
    ) -> dict[str, Any]:
        """Handle search action.

        Payload supports three modes:
        1. {"action": "search", "query": "from:elonmusk AI"}  → raw query
        2. {"action": "search", "query_builder": {...}}        → builder dict
        3. {"action": "search", "intent": "find AI tweets..."}  → AI hybrid
        """
        payload = task.payload
        max_tweets = payload.get("max_tweets", 100)

        # Tab can be at top-level or inside query_builder dict
        tab = payload.get("search_tab", "Top")

        # Mode 1: Raw query string
        if "query" in payload:
            query = XQueryBuilder.from_raw(payload["query"]).build()

        # Mode 2: Builder dict
        elif "query_builder" in payload:
            builder = XQueryBuilder.from_dict(payload["query_builder"])
            query, builder_tab = builder.build_with_tab()
            # Builder tab overrides default unless top-level explicitly set
            if "search_tab" not in payload:
                tab = builder_tab

        # Mode 3: AI hybrid (intent → query)
        elif "intent" in payload:
            generator = self._get_query_generator()
            query = await generator.generate(payload["intent"])

        else:
            raise ValueError(
                "Search payload must contain 'query', 'query_builder', or 'intent'"
            )

        # Default: filter out pure retweets (duplicate content)
        # Set "include_retweets": true in payload to keep them
        if not payload.get("include_retweets", False):
            if "-is:retweet" not in query:
                query += " -is:retweet"

        logger.info("Executing search: query=%r tab=%s", query, tab)
        await self._report_progress(task.id, {
            "action": "search",
            "target": query[:60],
            "phase": "searching",
            "message": f"Searching: {query[:50]}...",
        })
        tweets = await search_tweets(
            session, query=query, tab=tab, max_tweets=max_tweets,
        )
        await self._report_progress(task.id, {
            "action": "search",
            "target": query[:60],
            "phase": "done",
            "message": f"Found {len(tweets)} tweets",
            "total_found": len(tweets),
        })

        # Save as Content objects
        saved_ids = await self._save_contents(task, tweets)

        result: dict[str, Any] = {
            "action": "search",
            "query": query,
            "tab": tab,
            "tweets_found": len(tweets),
            "content_ids": saved_ids,
        }

        # Add diagnostic info when no tweets or author info missing
        has_author_issue = any(
            not t.get("author", {}).get("username") for t in tweets
        )
        if not tweets or has_author_issue:
            try:
                import json
                raw_graphql = session.interceptor.get_all("SearchTimeline")

                # Extract one raw tweet entry for structure debugging
                raw_tweet_sample = None
                for resp in raw_graphql:
                    try:
                        entries = (
                            resp.get("data", {})
                            .get("search_by_raw_query", {})
                            .get("search_timeline", {})
                            .get("timeline", {})
                            .get("instructions", [{}])[0]
                            .get("entries", [])
                        )
                        for entry in entries:
                            content = entry.get("content", {})
                            if content.get("entryType") == "TimelineTimelineItem":
                                raw_tweet_sample = json.dumps(entry)[:3000]
                                break
                    except (IndexError, KeyError):
                        pass
                    if raw_tweet_sample:
                        break

                result["debug"] = {
                    "page_url": await session.get_page_url(),
                    "page_title": await session.get_page_title(),
                    "graphql_responses_count": len(raw_graphql),
                    "raw_tweet_entry_sample": raw_tweet_sample,
                }
            except Exception as e:
                logger.warning("Failed to capture debug info: %s", e)
                result["debug"] = {"error": str(e)}

        return result

    async def _handle_tweet(
        self, session: XBrowserSession, task: Task,
    ) -> dict[str, Any]:
        """Handle single tweet fetch with replies."""
        payload = task.payload
        max_replies = payload.get("max_replies", 20)
        tweet_id_str = payload.get("tweet_id") or payload.get("url", "")

        await self._report_progress(task.id, {
            "action": "tweet",
            "target": tweet_id_str[:60],
            "phase": "fetching",
            "message": f"Fetching tweet {tweet_id_str[:20]}...",
        })

        result = await fetch_tweet(
            session,
            tweet_url=payload.get("url"),
            tweet_id=payload.get("tweet_id"),
            username=payload.get("username"),
            max_replies=max_replies,
        )

        main_tweet = result["tweet"]
        replies = result["replies"]

        # Save main tweet + all replies as Content
        saved_ids = await self._save_contents(task, [main_tweet])
        reply_ids = await self._save_contents(task, replies)

        return {
            "action": "tweet",
            "tweet_id": main_tweet["tweet_id"],
            "content_ids": saved_ids,
            "replies_found": len(replies),
            "reply_content_ids": reply_ids,
        }

    async def _handle_timeline(
        self, session: XBrowserSession, task: Task,
    ) -> dict[str, Any]:
        """Handle user timeline fetch with incremental exhaustive crawling.

        Features:
        - Pre-loads known tweet IDs from PG to avoid re-processing
        - Target-driven: stops after ``target_new`` fresh tweets found
        - Tracks timeline exhaustion for future crawl cycles
        - Reports real-time progress to Redis for UI display

        Note: Detail task dispatch (fetching comments/quotes for high-value
        tweets) is handled by the analyst pipeline's triage step, not here.
        The crawler is a dumb executor — the analyst decides what needs
        deeper investigation.
        """
        payload = task.payload
        username = payload.get("username")
        if not username:
            raise ValueError("Timeline action requires 'username' in payload")

        user_id = payload.get("user_id")
        config = payload.get("config", {})

        # Pre-load known tweet IDs from PG for incremental crawling
        known_ids = await self._get_known_tweet_ids(user_id, username)

        target_new = config.get("target_new_contents", 50)
        max_pages = config.get("max_scroll_pages", 50)

        await self._report_progress(task.id, {
            "action": "timeline",
            "target": f"@{username}",
            "phase": "loading",
            "message": f"Loading @{username} timeline...",
            "page": 0,
            "max_pages": max_pages,
            "new_count": 0,
            "target_new": target_new,
            "total_found": 0,
        })

        async def on_progress(page: int, new_count: int, total: int) -> None:
            await self._report_progress(task.id, {
                "action": "timeline",
                "target": f"@{username}",
                "phase": "scrolling",
                "message": f"@{username}: page {page}/{max_pages} · {new_count} new / {target_new} target",
                "page": page,
                "max_pages": max_pages,
                "new_count": new_count,
                "target_new": target_new,
                "total_found": total,
            })

        tweets, exhausted = await fetch_timeline(
            session,
            username=username,
            target_new=target_new,
            max_pages=max_pages,
            include_replies=config.get("include_replies_in_timeline", False),
            known_ids=known_ids,
            on_progress=on_progress,
        )

        await self._report_progress(task.id, {
            "action": "timeline",
            "target": f"@{username}",
            "phase": "saving",
            "message": f"Saving {len(tweets)} tweets...",
            "page": max_pages,
            "max_pages": max_pages,
            "new_count": 0,
            "target_new": target_new,
            "total_found": len(tweets),
        })

        saved_ids, new_count = await self._save_contents_dedup(task, tweets)

        # Update timeline exhaustion status on the user row
        if exhausted and user_id:
            await self._mark_timeline_exhausted(user_id)

        await self._report_progress(task.id, {
            "action": "timeline",
            "target": f"@{username}",
            "phase": "done",
            "message": f"Done: {new_count} new tweets" + (" (exhausted)" if exhausted else ""),
            "page": max_pages,
            "max_pages": max_pages,
            "new_count": new_count,
            "target_new": target_new,
            "total_found": len(tweets),
        })

        return {
            "action": "timeline",
            "username": username,
            "tweets_found": len(tweets),
            "content_ids": saved_ids,
            "new_count": new_count,
            "exhausted": exhausted,
        }

    # ──────────────────────────────────────
    # Progress reporting
    # ──────────────────────────────────────

    async def _report_progress(self, task_id: str, data: dict[str, Any]) -> None:
        """Write real-time task progress to Redis for UI display."""
        try:
            import json as _json
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
            await self._redis.set(
                f"task:{task_id}:progress",
                _json.dumps(data, ensure_ascii=False),
                ex=3600,  # 1 hour TTL
            )
        except Exception:
            pass  # best-effort, never block crawling

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    async def _save_contents(
        self, task: Task, tweets: list[dict[str, Any]],
    ) -> list[str]:
        """Save parsed tweets to PostgreSQL."""
        content_ids = [str(uuid4()) for _ in tweets]

        if content_ids:
            await self._save_to_pg(task, tweets, content_ids)

        logger.info("Saved %d content items for task %s", len(content_ids), task.id)
        return content_ids

    async def _save_contents_dedup(
        self, task: Task, tweets: list[dict[str, Any]],
    ) -> tuple[list[str], int]:
        """Save tweets with dedup-aware upsert. Returns (content_ids, new_count)."""
        if not tweets:
            return [], 0

        content_ids = [str(uuid4()) for _ in tweets]
        new_count = await self._save_to_pg_upsert(task, tweets, content_ids)
        logger.info(
            "Saved %d content items (%d new) for task %s",
            len(content_ids), new_count, task.id,
        )
        return content_ids, new_count

    async def _save_to_pg(
        self,
        task: Task,
        tweets: list[dict[str, Any]],
        content_ids: list[str],
    ) -> None:
        """Persist content rows to PostgreSQL for SQL-based analytics."""
        try:
            from shared.db.engine import get_session_factory
            from shared.db.models import ContentRow, TaskRow
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            topic_id = task.payload.get("topic_id")
            user_id = task.payload.get("user_id")
            factory = get_session_factory()
            async with factory() as session:
                # Ensure task exists in PG (ContentRow FK requirement)
                await session.execute(
                    pg_insert(TaskRow).values(
                        id=task.id,
                        label=task.label,
                        priority=task.priority,
                        payload=task.payload,
                    ).on_conflict_do_nothing(index_elements=["id"])
                )

                # Insert content rows (deduplicate by platform+content_id)
                for i, tweet in enumerate(tweets):
                    author = tweet.get("author", {})
                    await session.execute(
                        pg_insert(ContentRow).values(
                            id=content_ids[i],
                            task_id=task.id,
                            topic_id=topic_id,
                            user_id=user_id,
                            platform="x",
                            platform_content_id=tweet.get("tweet_id"),
                            source_url=tweet.get("source_url", ""),
                            author_uid=author.get("user_id"),
                            author_username=author.get("username"),
                            author_display_name=author.get("display_name"),
                            text=tweet.get("text"),
                            lang=tweet.get("lang"),
                            hashtags=tweet.get("hashtags", []),
                            metrics=tweet.get("metrics", {}),
                            data=tweet,
                        ).on_conflict_do_nothing(
                            index_elements=["platform", "platform_content_id"]
                        )
                    )

                await session.commit()
        except Exception as e:
            logger.warning("PG save failed (non-fatal): %s", e)

    async def _save_to_pg_upsert(
        self,
        task: Task,
        tweets: list[dict[str, Any]],
        content_ids: list[str],
    ) -> int:
        """Persist content rows with upsert — updates metrics/text on conflict.

        Returns the number of truly new rows inserted.
        """
        new_count = 0
        try:
            from shared.db.engine import get_session_factory
            from shared.db.models import ContentRow, TaskRow
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            topic_id = task.payload.get("topic_id")
            user_id = task.payload.get("user_id")
            factory = get_session_factory()
            async with factory() as session:
                await session.execute(
                    pg_insert(TaskRow).values(
                        id=task.id,
                        label=task.label,
                        priority=task.priority,
                        payload=task.payload,
                    ).on_conflict_do_nothing(index_elements=["id"])
                )

                for i, tweet in enumerate(tweets):
                    author = tweet.get("author", {})
                    stmt = pg_insert(ContentRow).values(
                        id=content_ids[i],
                        task_id=task.id,
                        topic_id=topic_id,
                        user_id=user_id,
                        platform="x",
                        platform_content_id=tweet.get("tweet_id"),
                        source_url=tweet.get("source_url", ""),
                        author_uid=author.get("user_id"),
                        author_username=author.get("username"),
                        author_display_name=author.get("display_name"),
                        text=tweet.get("text"),
                        lang=tweet.get("lang"),
                        hashtags=tweet.get("hashtags", []),
                        metrics=tweet.get("metrics", {}),
                        data=tweet,
                    )
                    # On conflict: update metrics + text (detect edits)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["platform", "platform_content_id"],
                        set_={
                            "metrics": stmt.excluded.metrics,
                            "text": stmt.excluded.text,
                            "data": stmt.excluded.data,
                        },
                    )
                    result = await session.execute(stmt)
                    # xmax = 0 means a fresh insert (not an update)
                    # For pg_insert ... on_conflict_do_update, rowcount is always 1
                    # We use a simpler heuristic: check if the ID we provided was used
                    # by querying back. Instead, just count via platform_content_id.
                    # Simpler: just check if this tweet_id was in known set before saving.
                    # But we don't have known_ids here, so we rely on the caller.
                    new_count += 1  # provisional — actual new vs update below

                await session.commit()

            # Correct new_count: query how many of our IDs actually exist
            # (the ones that conflicted got a different existing ID)
            async with factory() as session:
                from sqlalchemy import text as sql_text
                row = await session.execute(
                    sql_text(
                        "SELECT COUNT(*) FROM contents WHERE id = ANY(:ids)"
                    ),
                    {"ids": content_ids},
                )
                actually_inserted = row.scalar() or 0
                new_count = actually_inserted

        except Exception as e:
            logger.warning("PG upsert save failed (non-fatal): %s", e)

        return new_count

    async def _get_known_tweet_ids(
        self,
        user_id: str | None,
        username: str,
    ) -> set[str]:
        """Load platform_content_ids for a user from PG for dedup awareness."""
        try:
            from shared.db.engine import get_session_factory
            from sqlalchemy import text as sql_text

            factory = get_session_factory()
            async with factory() as session:
                if user_id:
                    result = await session.execute(
                        sql_text(
                            "SELECT platform_content_id FROM contents "
                            "WHERE platform = 'x' AND user_id = :uid "
                            "AND platform_content_id IS NOT NULL"
                        ),
                        {"uid": user_id},
                    )
                else:
                    result = await session.execute(
                        sql_text(
                            "SELECT platform_content_id FROM contents "
                            "WHERE platform = 'x' AND author_username = :username "
                            "AND platform_content_id IS NOT NULL"
                        ),
                        {"username": username},
                    )
                ids = {row[0] for row in result}
                logger.info("Loaded %d known tweet IDs for @%s", len(ids), username)
                return ids
        except Exception as e:
            logger.warning("Failed to load known tweet IDs: %s", e)
            return set()

    async def _mark_timeline_exhausted(self, user_id: str) -> None:
        """Update user's summary_data to record timeline exhaustion."""
        try:
            from shared.db.engine import get_session_factory
            from shared.db.models import UserRow

            factory = get_session_factory()
            async with factory() as session:
                user = await session.get(UserRow, user_id)
                if user:
                    data = user.summary_data or {}
                    progress = data.get("crawl_progress", {})
                    progress["timeline_exhausted"] = True
                    progress["exhausted_at"] = datetime.now(timezone.utc).isoformat()
                    data["crawl_progress"] = progress
                    user.summary_data = data
                    await session.commit()
                    logger.info("Marked timeline exhausted for user %s", user_id)
        except Exception as e:
            logger.warning("Failed to mark timeline exhausted: %s", e)

    async def _download_and_update_media(
        self, content_ids: list[str],
    ) -> None:
        """Download media for saved content items, update PG records.

        Best-effort: logs errors but never raises.
        """
        settings = get_settings()
        base_path = settings.media_base_path
        if not base_path:
            return

        try:
            from shared.db.engine import get_session_factory
            from shared.db.models import ContentRow
        except Exception:
            logger.warning("PG not available for media update")
            return

        downloaded = 0
        factory = get_session_factory()
        for cid in content_ids:
            try:
                async with factory() as session:
                    row = await session.get(ContentRow, cid)
                    if not row:
                        continue
                    media_items = row.data.get("media", [])
                    if not media_items:
                        continue

                    crawled_date = row.crawled_at.strftime("%Y-%m-%d")
                    updated_media = await download_media_batch(
                        media_items=media_items,
                        platform=row.platform,
                        content_id=str(row.id),
                        crawled_date=crawled_date,
                        base_path=base_path,
                    )

                    # Update PG row
                    new_data = {**row.data, "media": updated_media, "media_downloaded": True}
                    row.data = new_data
                    row.media_downloaded = True
                    await session.commit()
                    downloaded += 1
            except Exception as e:
                logger.warning("Media download failed for content %s: %s", cid, e)

        if downloaded:
            logger.info("Downloaded media for %d/%d content items", downloaded, len(content_ids))

    def _get_query_generator(self) -> QueryGenerator:
        """Lazy init query generator."""
        if self._query_generator is None:
            if not self._grok_api_key:
                raise ValueError("GROK_API_KEY required for intent-based query generation")
            llm = AsyncOpenAI(
                api_key=self._grok_api_key,
                base_url=self._grok_base_url,
            )
            self._query_generator = QueryGenerator(llm, self._grok_model)
        return self._query_generator

    @staticmethod
    def _load_proxy() -> ProxyConfig | None:
        """Load proxy config from environment."""
        server = os.environ.get("PROXY_SERVER")
        if not server:
            return None
        return ProxyConfig(
            server=server,
            username=os.environ.get("PROXY_USERNAME"),
            password=os.environ.get("PROXY_PASSWORD"),
        )

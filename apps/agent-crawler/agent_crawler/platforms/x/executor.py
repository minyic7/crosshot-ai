"""XExecutor — platform executor for X (Twitter) crawling tasks.

Dispatches by task.payload["action"]:
- "search": Generate/validate query → execute search → return tweets
- "tweet": Fetch a single tweet by URL/ID
- "timeline": Fetch a user's timeline

Each action: acquire cookie → open stealth browser → run action → save content → report.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import redis.asyncio as aioredis
from openai import AsyncOpenAI

from shared.models.content import Content
from shared.models.cookies import CookiesPool
from shared.models.task import Task
from shared.services.cookies_service import CookiesService

from ..base import BasePlatformExecutor
from .actions.search import search_tweets
from .actions.timeline import fetch_timeline
from .actions.tweet import fetch_tweet
from .browser import ProxyConfig, XBrowserSession
from .errors import NoCookiesAvailable, XCrawlerError
from .query_builder import XQueryBuilder
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
            return result

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
        tab = payload.get("search_tab", "Top")
        max_tweets = payload.get("max_tweets", 100)

        # Mode 1: Raw query string
        if "query" in payload:
            query = XQueryBuilder.from_raw(payload["query"]).build()

        # Mode 2: Builder dict
        elif "query_builder" in payload:
            query = XQueryBuilder.from_dict(payload["query_builder"]).build()

        # Mode 3: AI hybrid (intent → query)
        elif "intent" in payload:
            generator = self._get_query_generator()
            query = await generator.generate(payload["intent"])

        else:
            raise ValueError(
                "Search payload must contain 'query', 'query_builder', or 'intent'"
            )

        logger.info("Executing search: query=%r tab=%s", query, tab)
        tweets = await search_tweets(
            session, query=query, tab=tab, max_tweets=max_tweets,
        )

        # Save as Content objects
        saved_ids = await self._save_contents(task, tweets)

        return {
            "action": "search",
            "query": query,
            "tab": tab,
            "tweets_found": len(tweets),
            "content_ids": saved_ids,
        }

    async def _handle_tweet(
        self, session: XBrowserSession, task: Task,
    ) -> dict[str, Any]:
        """Handle single tweet fetch."""
        payload = task.payload
        tweet = await fetch_tweet(
            session,
            tweet_url=payload.get("url"),
            tweet_id=payload.get("tweet_id"),
            username=payload.get("username"),
        )

        saved_ids = await self._save_contents(task, [tweet])

        return {
            "action": "tweet",
            "tweet_id": tweet["tweet_id"],
            "content_ids": saved_ids,
        }

    async def _handle_timeline(
        self, session: XBrowserSession, task: Task,
    ) -> dict[str, Any]:
        """Handle user timeline fetch."""
        payload = task.payload
        username = payload.get("username")
        if not username:
            raise ValueError("Timeline action requires 'username' in payload")

        tweets = await fetch_timeline(
            session,
            username=username,
            max_tweets=payload.get("max_tweets", 100),
            include_replies=payload.get("include_replies", False),
        )

        saved_ids = await self._save_contents(task, tweets)

        return {
            "action": "timeline",
            "username": username,
            "tweets_found": len(tweets),
            "content_ids": saved_ids,
        }

    # ──────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────

    async def _save_contents(
        self, task: Task, tweets: list[dict[str, Any]],
    ) -> list[str]:
        """Save parsed tweets as Content objects in Redis."""
        content_ids = []
        for tweet in tweets:
            content = Content(
                task_id=task.id,
                platform="x",
                source_url=tweet.get("source_url", ""),
                data=tweet,
            )
            await self._redis.set(
                f"content:{content.id}",
                content.model_dump_json(),
                ex=604800,  # 7 days
            )
            # Index by platform
            await self._redis.sadd("content:index:x", content.id)
            content_ids.append(content.id)

        logger.info("Saved %d content items for task %s", len(content_ids), task.id)
        return content_ids

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

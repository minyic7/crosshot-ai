"""GraphQL response interceptor for X.

X's web client makes GraphQL API calls to:
    /i/api/graphql/{hash}/{OperationName}

This interceptor captures these responses for structured data extraction
instead of fragile HTML parsing.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from playwright.async_api import Response

from .errors import AuthError, RateLimitError

logger = logging.getLogger(__name__)

# GraphQL operations we care about
TRACKED_OPERATIONS = frozenset({
    "SearchTimeline",
    "TweetDetail",
    "TweetResultByRestId",
    "UserTweets",
    "UserTweetsAndReplies",
    "UserByScreenName",
})


class GraphQLInterceptor:
    """Intercepts X GraphQL API responses from Playwright.

    Usage:
        interceptor = GraphQLInterceptor()
        page.on("response", interceptor.on_response)

        # Navigate / interact with page...

        data = await interceptor.wait_for("SearchTimeline", timeout=15)
    """

    def __init__(self) -> None:
        self._captured: dict[str, list[dict[str, Any]]] = {}
        self._events: dict[str, asyncio.Event] = {}
        self._error: AuthError | RateLimitError | None = None

    async def on_response(self, response: Response) -> None:
        """Playwright response handler. Attach via page.on("response", ...).

        NOTE: Exceptions raised inside Playwright event handlers are swallowed.
        Instead, we store errors and re-raise them in wait_for().
        """
        url = response.url
        if "/i/api/graphql/" not in url:
            return

        # Extract operation name from URL path
        # e.g., /i/api/graphql/abc123/SearchTimeline?variables=...
        try:
            path_part = url.split("/i/api/graphql/")[1]
            operation = path_part.split("?")[0].split("/")[-1]
        except (IndexError, ValueError):
            return

        if operation not in TRACKED_OPERATIONS:
            return

        status = response.status

        # Auth errors — store and signal waiters
        if status in (401, 403):
            logger.error("Auth error (%d) for %s", status, operation)
            self._error = AuthError(f"HTTP {status} on {operation}")
            if operation in self._events:
                self._events[operation].set()
            return

        # Rate limit — store and signal waiters
        if status == 429:
            retry_after = response.headers.get("retry-after")
            retry_secs = int(retry_after) if retry_after else None
            logger.warning("Rate limited on %s (retry_after=%s)", operation, retry_secs)
            self._error = RateLimitError(retry_secs)
            if operation in self._events:
                self._events[operation].set()
            return

        if status != 200:
            logger.warning("Unexpected status %d for %s", status, operation)
            return

        try:
            body = await response.json()
        except Exception:
            logger.warning("Failed to parse JSON from %s response", operation)
            return

        logger.debug("Captured %s response (%d bytes)", operation, len(json.dumps(body)))

        if operation not in self._captured:
            self._captured[operation] = []
        self._captured[operation].append(body)

        # Signal any waiters
        if operation in self._events:
            self._events[operation].set()

    async def wait_for(
        self, operation: str, timeout: float = 15.0,
    ) -> dict[str, Any] | None:
        """Wait for a specific GraphQL operation response.

        Returns the first captured response for this operation,
        or None if timeout is reached. Raises stored errors (429, 401/403).
        """
        # Check for stored errors first
        if self._error is not None:
            raise self._error

        # Already captured?
        if operation in self._captured and self._captured[operation]:
            return self._captured[operation][-1]

        # Wait for it
        event = asyncio.Event()
        self._events[operation] = event
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            # Check for errors that arrived while waiting
            if self._error is not None:
                raise self._error
            results = self._captured.get(operation, [])
            return results[-1] if results else None
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for %s (%ss)", operation, timeout)
            return None
        finally:
            self._events.pop(operation, None)

    def get_all(self, operation: str) -> list[dict[str, Any]]:
        """Get all captured responses for an operation."""
        return self._captured.get(operation, [])

    def clear(self, operation: str | None = None) -> None:
        """Clear captured responses. If operation is None, clear all."""
        if operation:
            self._captured.pop(operation, None)
        else:
            self._captured.clear()
            self._error = None

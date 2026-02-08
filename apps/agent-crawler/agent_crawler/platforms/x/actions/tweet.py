"""TweetAction — fetch a single tweet by URL or ID."""

from __future__ import annotations

import logging
from typing import Any

from ..browser import XBrowserSession
from ..constants import GRAPHQL_WAIT_TIMEOUT
from ..errors import ContentNotFoundError
from ..parsers.tweet import parse_tweet_detail

logger = logging.getLogger(__name__)


async def fetch_tweet(
    session: XBrowserSession,
    tweet_url: str | None = None,
    tweet_id: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Fetch a single tweet via GraphQL interception.

    Provide either tweet_url or (tweet_id + username).

    Returns:
        Parsed tweet dict.

    Raises:
        ContentNotFoundError: If the tweet cannot be found.
    """
    if tweet_url:
        url = tweet_url
    elif tweet_id and username:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif tweet_id:
        # Without username, use x.com/i/web/status/ redirect
        url = f"https://x.com/i/web/status/{tweet_id}"
    else:
        raise ValueError("Provide tweet_url or tweet_id")

    logger.info("Fetching tweet: %s", url)
    session.interceptor.clear()

    await session.goto(url)

    # Wait for TweetDetail or TweetResultByRestId
    data = await session.interceptor.wait_for(
        "TweetDetail", timeout=GRAPHQL_WAIT_TIMEOUT,
    )
    if data is None:
        data = await session.interceptor.wait_for(
            "TweetResultByRestId", timeout=GRAPHQL_WAIT_TIMEOUT,
        )

    if data is None:
        raise ContentNotFoundError(f"No GraphQL response for tweet: {url}")

    parsed = parse_tweet_detail(data)
    if parsed is None:
        raise ContentNotFoundError(f"Tweet not found or unavailable: {url}")

    logger.info("Fetched tweet %s by @%s", parsed["tweet_id"], parsed["author"]["username"])
    return parsed

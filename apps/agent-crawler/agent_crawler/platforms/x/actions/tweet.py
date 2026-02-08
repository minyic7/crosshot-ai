"""TweetAction — fetch a single tweet and its replies."""

from __future__ import annotations

import logging
from typing import Any

from ..browser import XBrowserSession
from ..constants import GRAPHQL_WAIT_TIMEOUT, MAX_SCROLL_PAGES
from ..errors import ContentNotFoundError
from ..parsers.tweet import parse_tweet_detail, parse_tweet_replies

logger = logging.getLogger(__name__)

# Default: first page of replies only (no scroll)
DEFAULT_MAX_REPLIES = 20


async def fetch_tweet(
    session: XBrowserSession,
    tweet_url: str | None = None,
    tweet_id: str | None = None,
    username: str | None = None,
    max_replies: int = DEFAULT_MAX_REPLIES,
) -> dict[str, Any]:
    """Fetch a single tweet and its replies via GraphQL interception.

    Provide either tweet_url or (tweet_id + username).

    Returns:
        Dict with "tweet" (main tweet) and "replies" (list of reply tweets).

    Raises:
        ContentNotFoundError: If the tweet cannot be found.
    """
    if tweet_url:
        url = tweet_url
    elif tweet_id and username:
        url = f"https://x.com/{username}/status/{tweet_id}"
    elif tweet_id:
        url = f"https://x.com/i/web/status/{tweet_id}"
    else:
        raise ValueError("Provide tweet_url or tweet_id")

    logger.info("Fetching tweet: %s (max_replies=%d)", url, max_replies)
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

    # Parse main tweet
    parsed = parse_tweet_detail(data)
    if parsed is None:
        raise ContentNotFoundError(f"Tweet not found or unavailable: {url}")

    main_tweet_id = parsed["tweet_id"]
    logger.info("Fetched tweet %s by @%s", main_tweet_id, parsed["author"]["username"])

    # Parse replies from the same response (first page)
    all_replies: list[dict[str, Any]] = []
    seen_ids: set[str] = {main_tweet_id}

    first_page_replies = parse_tweet_replies(data, main_tweet_id)
    for reply in first_page_replies:
        if reply["tweet_id"] not in seen_ids:
            seen_ids.add(reply["tweet_id"])
            all_replies.append(reply)

    logger.info("First page: %d replies", len(all_replies))

    # Scroll for more replies if needed
    if len(all_replies) < max_replies:
        for page in range(1, MAX_SCROLL_PAGES):
            if len(all_replies) >= max_replies:
                break

            session.interceptor.clear("TweetDetail")
            await session.scroll_down()

            more_data = await session.interceptor.wait_for(
                "TweetDetail", timeout=GRAPHQL_WAIT_TIMEOUT,
            )
            if more_data is None:
                logger.info("No more replies at page %d", page + 1)
                break

            page_replies = parse_tweet_replies(more_data, main_tweet_id)
            new_count = 0
            for reply in page_replies:
                if reply["tweet_id"] not in seen_ids:
                    seen_ids.add(reply["tweet_id"])
                    all_replies.append(reply)
                    new_count += 1

            logger.info("Reply page %d: %d new (total %d)", page + 1, new_count, len(all_replies))
            if new_count == 0:
                break

    all_replies = all_replies[:max_replies]
    logger.info("Tweet %s: %d replies collected", main_tweet_id, len(all_replies))

    return {
        "tweet": parsed,
        "replies": all_replies,
    }

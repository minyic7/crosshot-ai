"""TimelineAction — fetch a user's tweet timeline."""

from __future__ import annotations

import logging
from typing import Any

from ..browser import XBrowserSession
from ..constants import GRAPHQL_WAIT_TIMEOUT, MAX_SCROLL_PAGES
from ..parsers.tweet import parse_user_tweets

logger = logging.getLogger(__name__)


async def fetch_timeline(
    session: XBrowserSession,
    username: str,
    max_pages: int = MAX_SCROLL_PAGES,
    max_tweets: int = 100,
    include_replies: bool = False,
) -> list[dict[str, Any]]:
    """Fetch a user's timeline via GraphQL interception.

    Args:
        session: Active browser session with cookies.
        username: X username (without @).
        max_pages: Maximum scroll iterations.
        max_tweets: Stop after collecting this many tweets.
        include_replies: If True, include replies in results.

    Returns:
        List of parsed tweet dicts.
    """
    username = username.lstrip("@")
    operation = "UserTweetsAndReplies" if include_replies else "UserTweets"
    url = f"https://x.com/{username}"

    logger.info("Fetching timeline: @%s (replies=%s)", username, include_replies)
    session.interceptor.clear()

    await session.goto(url)

    all_tweets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for page in range(max_pages):
        data = await session.interceptor.wait_for(
            operation, timeout=GRAPHQL_WAIT_TIMEOUT,
        )
        if data is None:
            # Try the other operation name
            alt_op = "UserTweets" if include_replies else "UserTweetsAndReplies"
            data = await session.interceptor.wait_for(alt_op, timeout=5.0)

        if data is None:
            logger.info("No more timeline data at page %d", page + 1)
            break

        tweets = parse_user_tweets(data)
        new_count = 0
        for tweet in tweets:
            tid = tweet["tweet_id"]
            if tid not in seen_ids:
                seen_ids.add(tid)
                all_tweets.append(tweet)
                new_count += 1

        logger.info(
            "Timeline page %d: %d new tweets (total %d)",
            page + 1, new_count, len(all_tweets),
        )

        if len(all_tweets) >= max_tweets:
            break
        if new_count == 0:
            break

        session.interceptor.clear(operation)
        await session.scroll_down()

    logger.info(
        "Timeline complete: %d tweets for @%s",
        len(all_tweets), username,
    )
    return all_tweets[:max_tweets]

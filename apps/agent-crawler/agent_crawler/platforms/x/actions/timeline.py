"""TimelineAction — fetch a user's tweet timeline.

Supports incremental exhaustive crawling: uses ``known_ids`` to skip
already-stored tweets and ``target_new`` to stop once enough fresh
content has been discovered.  Returns a ``(tweets, exhausted)`` tuple
so the caller can track whether the full history has been reached.
"""

from __future__ import annotations

import logging
from typing import Any

from ..browser import XBrowserSession
from ..constants import GRAPHQL_WAIT_TIMEOUT
from ..parsers.tweet import parse_user_tweets

logger = logging.getLogger(__name__)

# Default scroll hard-limit for timeline (higher than search because we
# may need to traverse already-known regions to reach older content).
DEFAULT_MAX_PAGES = 50
DEFAULT_TARGET_NEW = 50


async def fetch_timeline(
    session: XBrowserSession,
    username: str,
    max_pages: int = DEFAULT_MAX_PAGES,
    target_new: int = DEFAULT_TARGET_NEW,
    include_replies: bool = False,
    known_ids: set[str] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch a user's timeline via GraphQL interception.

    Args:
        session: Active browser session with cookies.
        username: X username (without @).
        max_pages: Safety hard-limit on scroll iterations.
        target_new: Stop after discovering this many *new* tweets
            (tweets whose ID is not in ``known_ids``).
        include_replies: If True, include replies in results.
        known_ids: Set of tweet IDs already stored in PG.  Used to
            distinguish new vs. already-crawled content.

    Returns:
        ``(tweets, exhausted)`` — all collected tweets and a flag
        indicating whether the timeline has been fully traversed
        (no more content available).
    """
    username = username.lstrip("@")
    known_ids = known_ids or set()
    operation = "UserTweetsAndReplies" if include_replies else "UserTweets"
    url = f"https://x.com/{username}"

    logger.info(
        "Fetching timeline: @%s (replies=%s, target_new=%d, known=%d)",
        username, include_replies, target_new, len(known_ids),
    )
    session.interceptor.clear()

    await session.goto(url)

    all_tweets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    new_count = 0       # truly new tweets (not in known_ids)
    empty_pages = 0     # consecutive pages with 0 tweets from parser

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
            return all_tweets, True  # exhausted

        tweets = parse_user_tweets(data)

        if len(tweets) == 0:
            empty_pages += 1
            if empty_pages >= 2:
                logger.info("Two consecutive empty pages — timeline exhausted")
                return all_tweets, True  # exhausted
            session.interceptor.clear(operation)
            await session.scroll_down()
            continue
        empty_pages = 0

        page_new = 0
        for tweet in tweets:
            tid = tweet["tweet_id"]
            if tid in seen_ids:
                continue
            seen_ids.add(tid)
            all_tweets.append(tweet)
            if tid not in known_ids:
                page_new += 1

        new_count += page_new
        logger.info(
            "Timeline page %d: %d parsed, %d new (total %d, new %d/%d)",
            page + 1, len(tweets), page_new,
            len(all_tweets), new_count, target_new,
        )

        # Target reached
        if new_count >= target_new:
            break

        session.interceptor.clear(operation)
        await session.scroll_down()

    exhausted = False
    logger.info(
        "Timeline complete: %d tweets (%d new) for @%s, exhausted=%s",
        len(all_tweets), new_count, username, exhausted,
    )
    return all_tweets, exhausted

"""SearchAction — execute X search with scroll pagination."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from ..browser import XBrowserSession
from ..constants import GRAPHQL_WAIT_TIMEOUT, MAX_SCROLL_PAGES
from ..parsers.tweet import parse_search_timeline

logger = logging.getLogger(__name__)

# Tab → URL parameter mapping
_TAB_PARAM = {
    "Top": "",       # default, no param needed
    "Latest": "f=live",
    "People": "f=user",
    "Media": "f=image",
    "Lists": "f=list",
}


async def search_tweets(
    session: XBrowserSession,
    query: str,
    tab: str = "Top",
    max_pages: int = MAX_SCROLL_PAGES,
    max_tweets: int = 100,
) -> list[dict[str, Any]]:
    """Execute a search on X and collect results via scroll pagination.

    Args:
        session: Active browser session with cookies.
        query: Validated X search query string.
        tab: Search tab (Top, Latest, People, Media).
        max_pages: Maximum scroll iterations.
        max_tweets: Stop after collecting this many tweets.

    Returns:
        List of parsed tweet dicts.
    """
    # Build search URL
    encoded_query = quote(query)
    tab_param = _TAB_PARAM.get(tab, "")
    url = f"https://x.com/search?q={encoded_query}"
    if tab_param:
        url += f"&{tab_param}"

    logger.info("Searching X: query=%r tab=%s url=%s", query, tab, url)
    session.interceptor.clear()

    await session.goto(url)

    all_tweets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for page in range(max_pages):
        # Wait for SearchTimeline response
        data = await session.interceptor.wait_for(
            "SearchTimeline", timeout=GRAPHQL_WAIT_TIMEOUT,
        )

        if data is None:
            logger.info("No more SearchTimeline data at page %d", page + 1)
            break

        tweets = parse_search_timeline(data)
        new_count = 0
        for tweet in tweets:
            tid = tweet["tweet_id"]
            if tid not in seen_ids:
                seen_ids.add(tid)
                all_tweets.append(tweet)
                new_count += 1

        logger.info(
            "Search page %d: %d new tweets (total %d)",
            page + 1, new_count, len(all_tweets),
        )

        # Stop conditions
        if len(all_tweets) >= max_tweets:
            break
        if new_count == 0:
            logger.info("No new tweets on page %d, stopping", page + 1)
            break

        # Scroll for next page
        session.interceptor.clear("SearchTimeline")
        await session.scroll_down()

    logger.info("Search complete: %d tweets collected for query=%r", len(all_tweets), query)
    return all_tweets[:max_tweets]

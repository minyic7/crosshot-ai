"""SearchAction — execute X search with scroll pagination."""

from __future__ import annotations

import logging
import time
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

# X shows these content gate buttons for sensitive/NSFW search results.
# We try each selector in order and click the first one found.
_CONTENT_GATE_SELECTORS = [
    # "Show" button inside search results sensitive content warning
    '[data-testid="empty_state_button_text"]',
    # Generic "Show" button text
    'button:has-text("Show")',
    # Older X UI variants
    '[role="button"]:has-text("Show")',
]


async def _try_dismiss_content_gate(session: XBrowserSession) -> bool:
    """Try to click through X's sensitive content warning gate.

    Returns True if a gate was found and clicked.
    """
    assert session.page is not None
    for selector in _CONTENT_GATE_SELECTORS:
        try:
            btn = session.page.locator(selector).first
            # wait_for actually waits unlike is_visible() which returns instantly
            await btn.wait_for(state="visible", timeout=3000)
            await btn.click()
            logger.info("Clicked content gate button: %s", selector)
            await session.random_delay(2.0, 3.0)
            return True
        except Exception:
            continue
    return False


async def _debug_empty_results(session: XBrowserSession, query: str) -> None:
    """Capture debugging info when search returns 0 results on page 1."""
    assert session.page is not None
    try:
        # Save screenshot to /tmp for inspection via docker exec
        ts = int(time.time())
        path = f"/tmp/x_search_empty_{ts}.png"
        await session.page.screenshot(path=path, full_page=True)
        logger.warning("0 results for query=%r — screenshot saved: %s", query, path)

        # Log truncated page text to see what X is showing
        body_text = await session.page.inner_text("body")
        logger.warning("Page body text (first 500 chars): %.500s", body_text)
    except Exception as e:
        logger.warning("Failed to capture debug info: %s", e)


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

    # Log page state after navigation for debugging
    current_url = await session.get_page_url()
    page_title = await session.get_page_title()
    logger.info("Page loaded: url=%s title=%r", current_url, page_title)

    all_tweets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for page_num in range(max_pages):
        # Wait for SearchTimeline response
        data = await session.interceptor.wait_for(
            "SearchTimeline", timeout=GRAPHQL_WAIT_TIMEOUT,
        )

        if data is None:
            logger.warning(
                "No SearchTimeline data at page %d (url=%s title=%r)",
                page_num + 1, current_url, page_title,
            )
            break

        tweets = parse_search_timeline(data)

        # Handle X's sensitive content gate: if page 1 returns 0 tweets,
        # check for a "Show" button and click through it.
        if page_num == 0 and len(tweets) == 0:
            await _debug_empty_results(session, query)
            clicked = await _try_dismiss_content_gate(session)
            if clicked:
                session.interceptor.clear("SearchTimeline")
                data = await session.interceptor.wait_for(
                    "SearchTimeline", timeout=GRAPHQL_WAIT_TIMEOUT,
                )
                if data:
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
            page_num + 1, new_count, len(all_tweets),
        )

        # Stop conditions
        if len(all_tweets) >= max_tweets:
            break
        if new_count == 0:
            logger.info("No new tweets on page %d, stopping", page_num + 1)
            break

        # Scroll for next page
        session.interceptor.clear("SearchTimeline")
        await session.scroll_down()

    logger.info("Search complete: %d tweets collected for query=%r", len(all_tweets), query)
    return all_tweets[:max_tweets]

"""X (Twitter) Crawler Implementation.

This module implements the crawler for X (formerly Twitter) platform,
inheriting from BaseCrawler and implementing all required methods.

Architecture:
- Inherits from BaseCrawler for standard interface
- Uses Playwright for browser automation (same as XHS)
- Implements stealth techniques to avoid detection
- Supports both authenticated and unauthenticated scraping
"""

import asyncio
import logging
from typing import List, Optional, Dict, AsyncGenerator
from datetime import datetime, timedelta
from enum import Enum

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from apps.crawler.base import (
    BaseCrawler,
    ContentItem,
    UserItem,
    CommentItem,
    SubCommentItem,
)
from apps.config import get_settings
from apps.utils.lru_cache import LRUCache

logger = logging.getLogger(__name__)


class SortBy(Enum):
    """X search sort options."""
    TOP = "top"  # Top tweets
    LATEST = "latest"  # Latest tweets
    PEOPLE = "people"  # People results
    PHOTOS = "photos"  # Photos only
    VIDEOS = "videos"  # Videos only


class XCrawler(BaseCrawler):
    """X (Twitter) crawler implementation.

    Features:
    - Search tweets by keyword
    - Get tweet details (likes, retweets, replies)
    - Get user profiles
    - Get tweet replies/comments
    - Support for authenticated/unauthenticated access
    - Stealth browser configuration
    - Continuous scrolling with deduplication

    Usage:
        async with XCrawler() as crawler:
            tweets = await crawler.scrape("keyword", max_notes=50)
            for tweet in tweets:
                print(tweet.title, tweet.likes)
    """

    def __init__(self):
        """Initialize X crawler."""
        super().__init__()
        self.platform = "x"
        self.settings = get_settings()

        # Browser state (initialized in __aenter__)
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

        # LRU cache for URL deduplication (10000 items, thread-safe)
        self._url_cache = LRUCache(maxsize=10000)

    # =========================================================================
    # Context Manager (Browser Lifecycle)
    # =========================================================================

    async def __aenter__(self):
        """Initialize browser with stealth configuration."""
        logger.info("Starting X crawler browser...")

        self._playwright = await async_playwright().start()

        # Launch browser with anti-detection args
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.crawler.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )

        # Create context with realistic settings
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Inject stealth JavaScript
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)

        # TODO: Load X cookies from config (if authenticated access needed)
        # cookies = self.settings.x.cookies_json
        # if cookies:
        #     await self._context.add_cookies(cookies)

        logger.info("X crawler browser started successfully")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Cleanup browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("X crawler browser closed")

    # =========================================================================
    # Required Methods (from BaseCrawler)
    # =========================================================================

    async def scrape(
        self,
        keyword: str,
        *,
        sort_by: SortBy = SortBy.TOP,
        max_notes: Optional[int] = None,
        max_scroll: int = 100,
    ) -> List[ContentItem]:
        """Search X for tweets matching keyword.

        Args:
            keyword: Search query
            sort_by: Sort order (TOP/LATEST/PHOTOS/VIDEOS)
            max_notes: Maximum number of tweets to collect (None = unlimited)
            max_scroll: Maximum scroll attempts

        Returns:
            List of ContentItem objects representing tweets
        """
        # TODO: Implement X search
        logger.info(f"Searching X for '{keyword}' (sort={sort_by.value})")
        raise NotImplementedError("X scrape() not yet implemented")

    async def scrape_continuous(
        self,
        keyword: str,
        *,
        sort_by: SortBy = SortBy.TOP,
        max_scroll: int = 100,
        recent_content_urls: Optional[Dict[str, datetime]] = None,
        dedup_window_hours: int = 24,
        min_new_per_scroll: int = 3,
    ) -> AsyncGenerator[ContentItem, None]:
        """Scrape tweets continuously, yielding items one-by-one.

        This generator yields ContentItem objects incrementally during scrolling,
        allowing the caller to process each item immediately.

        Args:
            keyword: Search query
            sort_by: Sort order
            max_scroll: Maximum scroll attempts
            recent_content_urls: Dict of {url: last_scraped_time} for dedup
            dedup_window_hours: Hours within which to skip already-scraped tweets
            min_new_per_scroll: Dynamic stop threshold

        Yields:
            ContentItem objects as they are discovered
        """
        # TODO: Implement continuous scraping
        logger.info(f"Starting continuous scrape for '{keyword}'")
        raise NotImplementedError("X scrape_continuous() not yet implemented")
        # This is a generator, so we need to yield something to avoid errors
        # Remove the line below when implementing
        yield  # type: ignore

    async def scrape_user(
        self,
        user_id: str,
        *,
        load_all_contents: bool = False
    ) -> UserItem:
        """Get X user profile information.

        Args:
            user_id: X user ID or username (@handle)
            load_all_contents: Whether to load all user's tweets

        Returns:
            UserItem with user profile data
        """
        # TODO: Implement user profile scraping
        logger.info(f"Getting X user profile: {user_id}")
        raise NotImplementedError("X scrape_user() not yet implemented")

    async def scrape_comments(
        self,
        content_url: str,
        *,
        load_all: bool = True,
        expand_sub_comments: bool = True,
    ) -> List[CommentItem]:
        """Get replies/comments for an X tweet.

        Args:
            content_url: Tweet URL
            load_all: Whether to load all replies
            expand_sub_comments: Whether to expand threaded replies

        Returns:
            List of CommentItem objects representing replies
        """
        # TODO: Implement comment/reply scraping
        logger.info(f"Getting X tweet replies: {content_url}")
        raise NotImplementedError("X scrape_comments() not yet implemented")

    # =========================================================================
    # Helper Methods (Platform-Specific)
    # =========================================================================

    async def _get_page(self) -> Page:
        """Create a new page in the browser context."""
        if not self._context:
            raise RuntimeError("Browser not initialized. Use 'async with XCrawler()' pattern.")
        return await self._context.new_page()

    def _extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from X URL.

        Examples:
            https://x.com/user/status/1234567890 -> 1234567890
            https://twitter.com/user/status/1234567890 -> 1234567890
        """
        # TODO: Implement tweet ID extraction
        parts = url.split('/status/')
        if len(parts) == 2:
            return parts[1].split('?')[0].split('/')[0]
        return None

    def _extract_user_id(self, url: str) -> Optional[str]:
        """Extract username from X URL.

        Examples:
            https://x.com/elonmusk -> elonmusk
            https://twitter.com/elonmusk -> elonmusk
        """
        # TODO: Implement username extraction
        parts = url.rstrip('/').split('/')
        if len(parts) >= 4:
            return parts[3]
        return None

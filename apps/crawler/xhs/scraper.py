"""XHS (Xiaohongshu) crawler with configurable settings."""

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Self, Set, Dict

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from apps.config import get_settings
from apps.utils.lru_cache import LRUCache
from apps.crawler.base import (
    BaseCrawler,
    CommentItem,
    ContentItem,
    ContentStats,
    SubCommentItem,
    UserInfo,
    UserContentItem,
)
from apps.utils.retry import retry_async

logger = logging.getLogger(__name__)


class SortBy(str, Enum):
    """Search sort options for XHS API.

    These values correspond to the 'sort' parameter in the XHS search API:
    POST /api/sns/web/v1/search/notes

    The filter panel options are:
    - 排序依据: 综合(general), 最新(time_descending), 最多点赞(likes_count),
               最多评论(comments_count), 最多收藏(collects_count)
    - 笔记类型: 不限(0), 视频(2), 图文(1) -> via note_type param
    - 发布时间: 不限, 一天内, 一周内, 半年内 -> via ext_flags param
    """

    # Primary sort options
    GENERAL = "general"  # 综合 (default)
    NEWEST = "time_descending"  # 最新
    MOST_LIKED = "popularity_descending"  # 最多点赞
    MOST_COMMENTS = "comments_count_descending"  # 最多评论
    MOST_COLLECTED = "collects_count_descending"  # 最多收藏

    # Aliases for backwards compatibility
    DEFAULT = "general"
    HOT = "popularity_descending"
    TIME = "time_descending"


class NoteType(int, Enum):
    """Note type filter for XHS API."""

    ALL = 0  # 不限
    IMAGE = 1  # 图文
    VIDEO = 2  # 视频


# JS to extract content stats (likes, collects, comments, shares) from __INITIAL_STATE__
JS_EXTRACT_CONTENT_STATS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    if (!noteId) return null;

    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.note) return null;

    const note = detail.note;
    const interactInfo = note.interactInfo || {};

    // Format count - handles Chinese numerals like "1.2万"
    const formatCount = (count) => {
        if (count === undefined || count === null) return "0";
        return String(count);
    };

    // Extract all image URLs from imageList
    const extractImageUrls = (imageList) => {
        if (!imageList || !Array.isArray(imageList)) return [];
        return imageList.map(img => {
            // Try different URL fields in order of preference
            return img.urlDefault || img.url || img.original || '';
        }).filter(url => url);
    };

    // Extract video URL if this is a video post
    // XHS stores video URLs in: note.video.media.stream.h264[0].masterUrl or h265[0].masterUrl
    const extractVideoUrl = (video) => {
        if (!video) return null;

        // Try direct URL fields first (legacy format)
        if (video.url) return video.url;
        if (video.urlDefault) return video.urlDefault;
        if (video.originUrl) return video.originUrl;

        // New format: video.media.stream contains different codec streams
        if (video.media && video.media.stream) {
            const stream = video.media.stream;
            // Prefer h264 for better compatibility, fallback to h265
            const streams = stream.h264 || stream.h265 || stream.av1 || [];
            if (streams.length > 0) {
                // Get the first stream's masterUrl or backupUrls
                const s = streams[0];
                if (s.masterUrl) return s.masterUrl;
                if (s.backupUrls && s.backupUrls.length > 0) return s.backupUrls[0];
            }
        }

        return null;
    };

    // Get image URLs
    const imageUrls = extractImageUrls(note.imageList);

    // Get video info (for video posts)
    const videoUrl = extractVideoUrl(note.video);

    return {
        noteId: noteId,
        likes: formatCount(interactInfo.likedCount),
        collects: formatCount(interactInfo.collectedCount),
        comments: formatCount(interactInfo.commentCount),
        shares: formatCount(interactInfo.shareCount || 0),
        imageUrls: imageUrls,
        videoUrl: videoUrl,
        type: note.type || 'normal',  // 'normal' for image, 'video' for video
    };
}"""


# JS to extract comments from __INITIAL_STATE__
JS_EXTRACT_COMMENTS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    if (!noteId) return null;

    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.comments) return null;

    // Helper to extract image URLs from pictures array
    const extractImages = (pictures) => {
        if (!pictures || !Array.isArray(pictures)) return [];
        return pictures.map(p => p.urlDefault || p.url || '').filter(url => url);
    };

    // comments is an object with list array
    const commentList = detail.comments.list || [];

    return commentList.map(c => ({
        id: c.id || '',
        content: c.content || '',
        userId: c.userInfo?.userId || '',
        nickname: c.userInfo?.nickname || '',
        avatar: c.userInfo?.image || '',
        likes: String(c.likeCount || 0),
        createTime: c.createTime || 0,
        ipLocation: c.ipLocation || '',
        imageUrls: extractImages(c.pictures),
        subCommentCount: parseInt(c.subCommentCount) || 0,
        // Include sub comments if available
        subComments: (c.subComments || []).map(sc => ({
            id: sc.id || '',
            content: sc.content || '',
            userId: sc.userInfo?.userId || '',
            nickname: sc.userInfo?.nickname || '',
            avatar: sc.userInfo?.image || '',
            likes: String(sc.likeCount || 0),
            createTime: sc.createTime || 0,
            ipLocation: sc.ipLocation || '',
            imageUrls: extractImages(sc.pictures),
        })),
    }));
}"""


class XhsCrawler(BaseCrawler):
    """XHS (Xiaohongshu) crawler with configurable settings.

    Memory Management:
        Uses LRU cache for URL deduplication instead of unbounded Set.
        - Max 10,000 URLs cached (oldest evicted when full)
        - Optional TTL to expire old entries
        - Memory usage capped at ~1-2 MB regardless of runtime duration
    """

    platform = "xhs"  # Platform identifier for cross-platform support

    # Class-level LRU cache shared across instances for long-running processes
    # This persists across scrape sessions while still having bounded memory
    _url_cache = LRUCache(max_size=10000, ttl_seconds=86400)  # 24h TTL

    def __init__(self, headless: Optional[bool] = None):
        """Initialize XHS crawler.

        Args:
            headless: Override headless mode. If None, uses config setting.
                      Set to False to show browser window (useful for manual verification).
        """
        self.settings = get_settings()
        self._headless = headless if headless is not None else self.settings.crawler.headless
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None

    async def __aenter__(self) -> Self:
        """Initialize browser on context enter."""
        self._playwright = await async_playwright().start()

        # Enhanced anti-detection launch args
        self._browser = await self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                '--disable-blink-features=AutomationControlled',  # Hide automation
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )

        # Enhanced anti-detection context settings
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers={
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
            }
        )

        # Hide webdriver property
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            // Override permissions API
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Add chrome object
            window.chrome = {
                runtime: {}
            };

            // Mock plugins
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // Mock languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
        """)

        # Add cookies from config
        cookies = self.settings.xhs.get_cookies()
        if cookies:
            await self._context.add_cookies(cookies)

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @classmethod
    def get_cache_stats(cls) -> dict:
        """Get URL cache statistics for monitoring.

        Returns:
            dict with size, max_size, ttl_seconds, expired_count
        """
        return cls._url_cache.stats

    @classmethod
    def cleanup_cache(cls) -> int:
        """Remove expired entries from URL cache.

        Returns:
            Number of entries removed
        """
        return cls._url_cache.cleanup_expired()

    @staticmethod
    def _extract_content_id(content_url: str) -> Optional[str]:
        """Extract content ID from XHS URL.

        URL formats:
        - https://www.xiaohongshu.com/explore/{content_id}?...
        - https://www.xiaohongshu.com/search_result/{content_id}?...
        """
        if not content_url:
            return None
        import re
        match = re.search(r'/(?:explore|search_result)/([a-f0-9]+)', content_url)
        return match.group(1) if match else None

    async def _get_page(self) -> Page:
        """Get a new page with configured settings."""
        if not self._context:
            raise RuntimeError("Crawler not initialized. Use 'async with' context.")

        page = await self._context.new_page()
        page.set_default_timeout(self.settings.crawler.playwright_timeout)
        return page

    @retry_async(max_retries=3, delay=2.0)
    async def _navigate_with_retry(self, page: Page, url: str) -> None:
        """Navigate to URL with retry."""
        await page.goto(url, wait_until="domcontentloaded")

    async def _safe_evaluate(self, page: Page, script: str, max_retries: int = 3):
        """Safely evaluate JavaScript with retry on navigation errors.

        Handles "Execution context was destroyed" errors that occur when
        the page navigates during evaluation.
        """
        for attempt in range(max_retries):
            try:
                # Wait for page to be in a stable state
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
                result = await page.evaluate(script)
                return result
            except Exception as e:
                error_msg = str(e)
                if "Execution context was destroyed" in error_msg or "navigation" in error_msg.lower():
                    if attempt < max_retries - 1:
                        logger.debug(f"Page navigation during evaluate, retrying ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(2)  # Wait for page to stabilize
                        continue
                    else:
                        logger.warning(f"Evaluate failed after {max_retries} attempts: {e}")
                        raise
                else:
                    raise
        return None

    async def _scroll_page(self, page: Page) -> bool:
        """Scroll page to load more content.

        Returns True if scroll was successful (page actually scrolled).
        Uses multiple smaller scrolls to better trigger lazy loading.
        """
        # Get current scroll position
        before_scroll = await self._safe_evaluate(page, "window.scrollY") or 0

        # Scroll in chunks to better trigger lazy loading
        # Some sites need gradual scrolling to trigger content loading
        await self._safe_evaluate(page, """() => {
            const viewportHeight = window.innerHeight;
            const currentScroll = window.scrollY;
            const targetScroll = currentScroll + viewportHeight * 2;  // Scroll 2 viewport heights
            window.scrollTo({ top: targetScroll, behavior: 'smooth' });
        }""")

        # Wait for smooth scroll to complete
        await asyncio.sleep(0.5)

        # Then scroll to absolute bottom to ensure we're at the end
        await self._safe_evaluate(page, "window.scrollTo(0, document.body.scrollHeight)")

        # Get new scroll position to verify scroll happened
        after_scroll = await self._safe_evaluate(page, "window.scrollY") or 0

        return after_scroll > before_scroll

    async def _open_filter_panel(self, page: Page) -> bool:
        """Open the filter panel by clicking the '筛选' button.

        Returns True if panel opened successfully.
        """
        try:
            # Click the filter button using JavaScript to avoid modal interception
            clicked = await self._safe_evaluate(page, """() => {
                const elements = document.querySelectorAll('*');
                for (const el of elements) {
                    const text = el.innerText?.trim();
                    if (text === '筛选') {
                        const rect = el.getBoundingClientRect();
                        if (rect.left > 1000) {  // Right side of screen
                            el.click();
                            return true;
                        }
                    }
                }
                return false;
            }""")

            if clicked:
                await asyncio.sleep(1)  # Wait for panel animation
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to open filter panel: {e}")
            return False

    async def _close_filter_panel(self, page: Page) -> None:
        """Close the filter panel."""
        try:
            # Try clicking '收起' button first
            collapse_btn = page.locator(".filter-panel >> text=收起").first
            if await collapse_btn.count() > 0:
                await collapse_btn.click()
                await asyncio.sleep(0.5)
                return

            # Fallback: click outside the panel
            await self._safe_evaluate(page, """() => {
                const mask = document.querySelector('.filter-mask');
                if (mask) mask.click();
            }""")
        except Exception as e:
            logger.debug(f"Error closing filter panel: {e}")

    async def _apply_sort_filter(self, page: Page, sort_by: SortBy) -> bool:
        """Apply sort filter via the filter panel.

        Args:
            page: Playwright page
            sort_by: Sort option to select

        Returns:
            True if filter was applied successfully
        """
        # Map SortBy enum to display text in the filter panel
        sort_text_map = {
            SortBy.GENERAL: "综合",
            SortBy.DEFAULT: "综合",
            SortBy.NEWEST: "最新",
            SortBy.TIME: "最新",
            SortBy.MOST_LIKED: "最多点赞",
            SortBy.HOT: "最多点赞",
            SortBy.MOST_COMMENTS: "最多评论",
            SortBy.MOST_COLLECTED: "最多收藏",
        }

        sort_text = sort_text_map.get(sort_by, "综合")

        try:
            # Open filter panel
            if not await self._open_filter_panel(page):
                logger.warning("Could not open filter panel")
                return False

            # Click the sort option within the panel
            option = page.locator(f".filter-panel >> text={sort_text}").first
            if await option.count() > 0:
                await option.click()
                await asyncio.sleep(2)  # Wait for results to refresh
                logger.info(f"Applied sort filter: {sort_text}")

                # Close the panel
                await self._close_filter_panel(page)
                return True
            else:
                logger.warning(f"Sort option '{sort_text}' not found in filter panel")
                await self._close_filter_panel(page)
                return False

        except Exception as e:
            logger.warning(f"Failed to apply sort filter: {e}")
            return False

    async def _apply_note_type_filter(self, page: Page, note_type: NoteType) -> bool:
        """Apply note type filter via the filter panel.

        Args:
            page: Playwright page
            note_type: Note type to filter (IMAGE or VIDEO)

        Returns:
            True if filter was applied successfully
        """
        type_text_map = {
            NoteType.ALL: "不限",
            NoteType.IMAGE: "图文",
            NoteType.VIDEO: "视频",
        }

        type_text = type_text_map.get(note_type, "不限")

        try:
            # Open filter panel if not already open
            panel = page.locator(".filter-panel")
            if await panel.count() == 0:
                if not await self._open_filter_panel(page):
                    return False

            # Click the note type option
            option = page.locator(f".filter-panel >> text={type_text}").first
            if await option.count() > 0:
                await option.click()
                await asyncio.sleep(2)
                logger.info(f"Applied note type filter: {type_text}")

                await self._close_filter_panel(page)
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to apply note type filter: {e}")
            return False

    async def _extract_contents_from_page(self, page: Page) -> list[dict]:
        """Extract content data from current page."""
        result = await self._safe_evaluate(
            page,
            r"""() => {
            const cards = document.querySelectorAll('section.note-item');
            return Array.from(cards).map(card => {
                const titleEl = card.querySelector('.title span');
                const title = titleEl ? titleEl.textContent.trim() : 'N/A';

                const likesEl = card.querySelector('.footer .like-wrapper .count');
                let likes = '0';
                if (likesEl) {
                    likes = likesEl.textContent.trim();  // Keep original format
                }

                const linkEl = card.querySelector('a.cover');
                let contentUrl = '';
                if (linkEl && linkEl.href) {
                    contentUrl = linkEl.href;
                }

                const imgEl = card.querySelector('img');
                const mediaUrls = imgEl && imgEl.src ? [imgEl.src] : [];

                // Extract author info from footer
                const authorLink = card.querySelector('.footer .author-wrapper a, .footer a[href*="/user/profile/"]');
                let userId = '';
                let nickname = '';
                let avatar = '';

                if (authorLink) {
                    const href = authorLink.href || '';
                    const userIdMatch = href.match(/\/user\/profile\/([a-f0-9]+)/);
                    if (userIdMatch) {
                        userId = userIdMatch[1];
                    }
                    const nicknameEl = authorLink.querySelector('.name, span');
                    nickname = nicknameEl ? nicknameEl.textContent.trim() : '';
                    const avatarEl = authorLink.querySelector('img') || card.querySelector('.author-wrapper img');
                    avatar = avatarEl ? avatarEl.src : '';
                }

                // Check if video content
                const isVideo = !!(card.querySelector('[class*="video"], .play-icon, .duration, video'));

                return { title, likes, contentUrl, mediaUrls, userId, nickname, avatar, isVideo };
            });
        }"""
        )
        return result if result else []

    async def scrape_continuous(
        self,
        keyword: str,
        *,
        sort_by: SortBy = SortBy.GENERAL,
        note_type: NoteType = NoteType.ALL,
        max_scroll: int = 100,
        recent_content_urls: Optional[Dict[str, datetime]] = None,
        dedup_window_hours: int = 24,
        min_new_per_scroll: int = 3,
    ):
        """Scrape contents continuously, yielding items one-by-one as found.

        This generator yields ContentItem objects incrementally during scrolling,
        allowing the caller to process each item immediately rather than waiting
        for all items to be collected.

        Args:
            keyword: Search keyword
            sort_by: Sort order (GENERAL/NEWEST/MOST_LIKED/MOST_COMMENTS/MOST_COLLECTED)
            note_type: Note type filter (ALL/IMAGE/VIDEO)
            max_scroll: Maximum scroll attempts before giving up (default 100)
            recent_content_urls: Dict of {content_url: last_scraped_time} for smart dedup
            dedup_window_hours: Hours within which to skip already-scraped contents (default 24)
            min_new_per_scroll: Dynamic stop threshold - if consecutive 3 scrolls add < this, stop (default 3)

        Yields:
            ContentItem objects as they are discovered during scrolling
        """
        # Calculate dedup cutoff time
        dedup_cutoff = datetime.utcnow() - timedelta(hours=dedup_window_hours)

        # Build set of URLs to skip (only those scraped within the dedup window)
        skip_urls: Set[str] = set()
        if recent_content_urls:
            for url, scraped_time in recent_content_urls.items():
                if scraped_time > dedup_cutoff:
                    skip_urls.add(url)

        # Use context manager pattern for standalone usage
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            # Build search URL
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"

            await self._navigate_with_retry(page, search_url)
            await asyncio.sleep(5)

            # Debug: take screenshot
            import os
            screenshot_dir = "/app/data/debug_screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"search_{keyword[:20]}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            logger.info(f"Debug screenshot saved: {screenshot_path}")

            # Check for redirect to error/login
            current_url = page.url
            logger.info(f"Current URL after navigation: {current_url}")

            if "error" in current_url or "login" in current_url:
                error_msg = f"Redirected to error/login page: {current_url}"
                logger.error(error_msg)
                raise Exception(f"XHS anti-scraping detected: {error_msg}")

            # Apply sort filter if not default
            if sort_by != SortBy.GENERAL:
                await self._apply_sort_filter(page, sort_by)
                await asyncio.sleep(2)

            # Apply note type filter if not ALL
            if note_type != NoteType.ALL:
                await self._apply_note_type_filter(page, note_type)
                await asyncio.sleep(2)

            items_yielded = 0
            no_new_content_count = 0
            max_no_new_content = 3

            for scroll_idx in range(max_scroll):
                # Extract current visible contents
                raw_items = await self._extract_contents_from_page(page)

                if not raw_items:
                    raw_items = []

                new_items_this_scroll = 0

                for item in raw_items:
                    content_url = item.get("contentUrl", "")

                    # Skip if no content URL
                    if not content_url:
                        logger.debug("Skip reason: no content URL")
                        continue

                    # Skip if already seen in LRU cache
                    if content_url in self._url_cache:
                        logger.debug(f"Skip reason: already in cache - {content_url[:60]}")
                        continue

                    # Skip if scraped within dedup window (from database)
                    if content_url in skip_urls:
                        self._url_cache.add(content_url)
                        logger.debug(f"Skip reason: scraped within 24h - {content_url[:60]}")
                        continue

                    self._url_cache.add(content_url)

                    # Extract content_id from URL
                    content_id = self._extract_content_id(content_url)

                    # Skip if no content_id extracted
                    if not content_id:
                        logger.debug(f"Skip reason: no content_id extracted from {content_url[:60]}")
                        continue

                    # Enhanced validation
                    title = item.get("title", "").strip()
                    media_urls = item.get("mediaUrls", [])

                    # Only skip if BOTH no title AND no media
                    if (not title or title == "N/A") and not media_urls:
                        logger.debug(f"Skip reason: empty content (no title + no media) - {content_url[:60]}")
                        continue

                    # Build platform_data with author info
                    platform_data = {}
                    if item.get("userId"):
                        platform_data["user_id"] = item.get("userId")
                    if item.get("nickname"):
                        platform_data["nickname"] = item.get("nickname")
                    if item.get("avatar"):
                        platform_data["avatar"] = item.get("avatar")

                    # Flag suspicious content
                    if not title or title == "N/A":
                        platform_data["flag"] = "no_title"
                    if not media_urls:
                        platform_data["flag"] = platform_data.get("flag", "") + ",no_media"

                    # Determine content type
                    content_type = "video" if item.get("isVideo") else "normal"

                    content_item = ContentItem(
                        platform=self.platform,
                        platform_content_id=content_id or "",
                        title=item.get("title", "N/A"),
                        likes=item.get("likes", "0"),
                        collects="0",
                        comments="0",
                        publish_time="",
                        content_url=content_url,
                        media_urls=item.get("mediaUrls", []),
                        content_type=content_type,
                        platform_data=platform_data,
                    )

                    # Yield item immediately
                    yield content_item
                    items_yielded += 1
                    new_items_this_scroll += 1

                # Check dynamic stopping condition
                if new_items_this_scroll < min_new_per_scroll:
                    no_new_content_count += 1
                    logger.debug(f"Low yield: only {new_items_this_scroll} new items after scroll {scroll_idx + 1} (threshold={min_new_per_scroll}), count={no_new_content_count}")
                    if no_new_content_count >= max_no_new_content:
                        logger.info(f"Dynamic stop: {max_no_new_content} consecutive scrolls with <{min_new_per_scroll} new items")
                        break
                else:
                    no_new_content_count = 0
                    logger.debug(f"Good yield: {new_items_this_scroll} new items (>={min_new_per_scroll})")

                # Scroll to load more
                scrolled = await self._scroll_page(page)

                # SAFE: Avoid <5s extremes - raised from 3-9 to 5-14
                import random
                scroll_wait = random.uniform(5, 14)
                await asyncio.sleep(scroll_wait)

                # Extra pause for "browsing feel"
                extra_pause = random.uniform(2, 5)
                await asyncio.sleep(extra_pause)

                logger.debug(f"Scroll wait: {scroll_wait:.1f}s + extra {extra_pause:.1f}s")

            await page.close()

            logger.info(f"Scraped {items_yielded} unique contents for keyword: {keyword} (scrolled {scroll_idx + 1} times)")

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape(
        self,
        keyword: str,
        *,
        sort_by: SortBy = SortBy.GENERAL,
        note_type: NoteType = NoteType.ALL,
        max_notes: Optional[int] = None,
        max_scroll: int = 100,
        recent_content_urls: Optional[Dict[str, datetime]] = None,
        dedup_window_hours: int = 24,
        min_new_per_scroll: int = 3,
    ) -> list[ContentItem]:
        """Scrape contents for a keyword.

        Args:
            keyword: Search keyword
            sort_by: Sort order (GENERAL/NEWEST/MOST_LIKED/MOST_COMMENTS/MOST_COLLECTED)
            note_type: Note type filter (ALL/IMAGE/VIDEO)
            max_notes: Maximum contents to return (default from config)
            max_scroll: Maximum scroll attempts before giving up (default 100)
            recent_content_urls: Dict of {content_url: last_scraped_time} for smart dedup
                - URLs scraped within dedup_window_hours will be SKIPPED (same-day dedup)
                - URLs scraped before dedup_window_hours will be INCLUDED (for update)
            dedup_window_hours: Hours within which to skip already-scraped contents (default 24)
            min_new_per_scroll: Dynamic stop threshold - if consecutive 3 scrolls add < this, stop (default 3)

        Returns:
            List of unique ContentItem objects
        """
        if max_notes is None:
            max_notes = self.settings.crawler.default_max_notes

        # Calculate dedup cutoff time
        dedup_cutoff = datetime.utcnow() - timedelta(hours=dedup_window_hours)

        # Build set of URLs to skip (only those scraped within the dedup window)
        skip_urls: Set[str] = set()
        if recent_content_urls:
            for url, scraped_time in recent_content_urls.items():
                if scraped_time > dedup_cutoff:
                    # Scraped within window - skip it
                    skip_urls.add(url)
                # If scraped before cutoff - don't add to skip, will be re-scraped for update

        # Use context manager pattern for standalone usage
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            # Build search URL
            search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}"

            await self._navigate_with_retry(page, search_url)
            await asyncio.sleep(5)

            # Debug: take screenshot to verify search results
            import os
            screenshot_dir = "/app/data/debug_screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_path = os.path.join(screenshot_dir, f"search_{keyword[:20]}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            logger.info(f"Debug screenshot saved: {screenshot_path}")

            # Also log the current URL to verify we're on search page
            current_url = page.url
            logger.info(f"Current URL after navigation: {current_url}")

            # Check if we got redirected to error or login page
            if "error" in current_url or "login" in current_url:
                error_msg = f"Redirected to error/login page: {current_url}"
                logger.error(error_msg)
                raise Exception(f"XHS anti-scraping detected: {error_msg}")

            # Apply sort filter if not default
            if sort_by != SortBy.GENERAL:
                await self._apply_sort_filter(page, sort_by)
                await asyncio.sleep(2)

            # Apply note type filter if not ALL
            if note_type != NoteType.ALL:
                await self._apply_note_type_filter(page, note_type)
                await asyncio.sleep(2)

            items: list[ContentItem] = []
            no_new_content_count = 0
            max_no_new_content = 3  # Stop after 3 consecutive scrolls with no new content

            for scroll_idx in range(max_scroll):
                # Extract current visible contents
                raw_items = await self._extract_contents_from_page(page)

                if not raw_items:
                    raw_items = []

                items_before = len(items)

                for item in raw_items:
                    content_url = item.get("contentUrl", "")

                    # Skip if no content URL (invalid item)
                    if not content_url:
                        logger.debug("Skip reason: no content URL")
                        continue

                    # Skip if already seen in LRU cache (bounded memory dedup)
                    if content_url in self._url_cache:
                        logger.debug(f"Skip reason: already in cache - {content_url[:60]}")
                        continue

                    # Skip if scraped within dedup window (from database)
                    if content_url in skip_urls:
                        self._url_cache.add(content_url)  # Mark as seen
                        logger.debug(f"Skip reason: scraped within 24h - {content_url[:60]}")
                        continue

                    self._url_cache.add(content_url)

                    # Extract content_id from URL
                    content_id = self._extract_content_id(content_url)

                    # Skip if no content_id extracted (invalid item)
                    if not content_id:
                        logger.debug(f"Skip reason: no content_id extracted from {content_url[:60]}")
                        continue

                    # Enhanced validation: skip truly empty content (minimal intervention)
                    title = item.get("title", "").strip()
                    media_urls = item.get("mediaUrls", [])

                    # Only skip if BOTH conditions met (likely ad/placeholder):
                    # 1. No meaningful title (empty or "N/A")
                    # 2. No media content
                    if (not title or title == "N/A") and not media_urls:
                        logger.debug(f"Skip reason: empty content (no title + no media) - {content_url[:60]}")
                        continue

                    # Build platform_data with author info
                    platform_data = {}
                    if item.get("userId"):
                        platform_data["user_id"] = item.get("userId")
                    if item.get("nickname"):
                        platform_data["nickname"] = item.get("nickname")
                    if item.get("avatar"):
                        platform_data["avatar"] = item.get("avatar")

                    # Flag suspicious content for later filtering/analysis
                    if not title or title == "N/A":
                        platform_data["flag"] = "no_title"
                    if not media_urls:
                        platform_data["flag"] = platform_data.get("flag", "") + ",no_media"

                    # Determine content type
                    content_type = "video" if item.get("isVideo") else "normal"

                    items.append(
                        ContentItem(
                            platform=self.platform,
                            platform_content_id=content_id or "",
                            title=item.get("title", "N/A"),
                            likes=item.get("likes", "0"),
                            collects="0",
                            comments="0",
                            publish_time="",
                            content_url=content_url,
                            media_urls=item.get("mediaUrls", []),
                            content_type=content_type,
                            platform_data=platform_data,
                        )
                    )

                    if len(items) >= max_notes:
                        break

                # Check if we reached target
                if len(items) >= max_notes:
                    logger.info(f"Reached target of {max_notes} contents")
                    break

                # Check if we got new items this scroll - DYNAMIC STOPPING
                items_added = len(items) - items_before
                if items_added < min_new_per_scroll:
                    # Less than threshold → count as "low yield"
                    no_new_content_count += 1
                    logger.debug(f"Low yield: only {items_added} new items after scroll {scroll_idx + 1} (threshold={min_new_per_scroll}), count={no_new_content_count}")
                    if no_new_content_count >= max_no_new_content:
                        logger.info(f"Dynamic stop: {max_no_new_content} consecutive scrolls with <{min_new_per_scroll} new items")
                        break
                else:
                    # Good yield → reset counter
                    no_new_content_count = 0
                    logger.debug(f"Good yield: {items_added} new items (>={min_new_per_scroll})")

                # Scroll to load more
                scrolled = await self._scroll_page(page)

                # SAFE: Avoid <5s extremes - raised from 3-9 to 5-14
                import random
                scroll_wait = random.uniform(5, 14)
                await asyncio.sleep(scroll_wait)

                # Extra pause for "browsing feel" (2-5 seconds)
                extra_pause = random.uniform(2, 5)
                await asyncio.sleep(extra_pause)

                logger.debug(f"Scroll wait: {scroll_wait:.1f}s + extra {extra_pause:.1f}s")

            await page.close()

            logger.info(f"Scraped {len(items)} unique contents for keyword: {keyword} (scrolled {scroll_idx + 1} times)")
            return items

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape_homepage(
        self,
        *,
        max_notes: Optional[int] = None,
        max_scroll: int = 100,
        recent_content_urls: Optional[Dict[str, datetime]] = None,
        dedup_window_hours: int = 24,
        min_new_per_scroll: int = 3,
    ) -> list[ContentItem]:
        """Scrape contents from homepage/explore feed (no search).

        Args:
            max_notes: Maximum contents to return (default from config)
            max_scroll: Maximum scroll attempts before giving up (default 100)
            recent_content_urls: Dict of {content_url: last_scraped_time} for smart dedup
            dedup_window_hours: Hours within which to skip already-scraped contents (default 24)
            min_new_per_scroll: Dynamic stop threshold - if consecutive 3 scrolls add < this, stop (default 3)

        Returns:
            List of unique ContentItem objects
        """
        if max_notes is None:
            max_notes = self.settings.crawler.default_max_notes

        # Calculate dedup cutoff time
        dedup_cutoff = datetime.utcnow() - timedelta(hours=dedup_window_hours)

        # Build set of URLs to skip
        skip_urls: Set[str] = set()
        if recent_content_urls:
            for url, scraped_time in recent_content_urls.items():
                if scraped_time > dedup_cutoff:
                    skip_urls.add(url)

        # Use context manager pattern
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            # Navigate to homepage/explore
            homepage_url = "https://www.xiaohongshu.com/explore"
            await self._navigate_with_retry(page, homepage_url)
            await asyncio.sleep(5)

            items: list[ContentItem] = []
            no_new_content_count = 0
            max_no_new_content = 3

            for scroll_idx in range(max_scroll):
                # Extract current visible contents
                raw_items = await self._extract_contents_from_page(page)

                if not raw_items:
                    raw_items = []

                items_before = len(items)

                for item in raw_items:
                    content_url = item.get("contentUrl", "")

                    # Skip if already seen
                    if content_url in self._url_cache:
                        continue

                    # Skip if scraped within dedup window
                    if content_url in skip_urls:
                        self._url_cache.add(content_url)
                        continue

                    self._url_cache.add(content_url)

                    # Extract content_id from URL
                    content_id = self._extract_content_id(content_url)

                    # Build platform_data with author info
                    platform_data = {}
                    if item.get("userId"):
                        platform_data["author"] = {
                            "user_id": item.get("userId"),
                            "nickname": item.get("nickname", ""),
                            "avatar": item.get("avatar", "")
                        }

                    items.append(ContentItem(
                        platform="xhs",
                        platform_content_id=content_id,
                        content_url=content_url,
                        title=item.get("title", ""),
                        content_type=item.get("type", "normal"),
                        cover_url=item.get("imageUrl", ""),
                        likes_count=item.get("likes", 0),
                        platform_data=platform_data,
                    ))

                    if len(items) >= max_notes:
                        break

                # Check if we reached target
                if len(items) >= max_notes:
                    logger.info(f"Reached target of {max_notes} contents")
                    break

                # Check if we got new items
                items_added = len(items) - items_before
                if items_added == 0:
                    no_new_content_count += 1
                    logger.debug(f"No new items after scroll {scroll_idx + 1}")
                    if no_new_content_count >= max_no_new_content:
                        logger.info(f"No new content after {max_no_new_content} scrolls, stopping")
                        break
                else:
                    no_new_content_count = 0

                # Scroll to load more
                scrolled = await self._scroll_page(page)
                await asyncio.sleep(2.5 if scrolled else 1.0)

            await page.close()

            logger.info(f"Scraped {len(items)} unique contents from homepage (scrolled {scroll_idx + 1} times)")
            return items

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape_comments(
        self,
        content_url: str,
        load_all: bool = False,
        expand_sub_comments: bool = False,
        max_scroll: int = 20,
        return_stats: bool = False,
    ) -> list[CommentItem] | tuple[list[CommentItem], ContentStats | None]:
        """Scrape comments from a content.

        Args:
            content_url: Full URL of the content (must include xsec_token)
            load_all: If True, scroll to load all comments
            expand_sub_comments: If True, click to expand all sub-comments
            max_scroll: Maximum number of scroll attempts when load_all=True
            return_stats: If True, also return content stats (likes, collects, comments count)

        Returns:
            If return_stats=False: list of CommentItem
            If return_stats=True: tuple of (list[CommentItem], ContentStats | None)
        """
        # Use context manager pattern for standalone usage
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            await self._navigate_with_retry(page, content_url)
            await asyncio.sleep(5)

            # Debug: screenshot and log URL for detail page
            import os
            import hashlib
            screenshot_dir = "/app/data/debug_screenshots"
            os.makedirs(screenshot_dir, exist_ok=True)
            url_hash = hashlib.md5(content_url.encode()).hexdigest()[:8]
            screenshot_path = os.path.join(screenshot_dir, f"detail_{url_hash}.png")
            await page.screenshot(path=screenshot_path, full_page=False)
            current_url = page.url
            logger.info(f"Detail page URL: {current_url}")
            if "error" in current_url or "login" in current_url:
                logger.warning(f"Detail page redirected to error/login page")

            # Wait for __INITIAL_STATE__ to be available
            try:
                await page.wait_for_function(
                    "window.__INITIAL_STATE__ && window.__INITIAL_STATE__.note",
                    timeout=10000,
                )
            except Exception as e:
                logger.warning(f"Timeout waiting for __INITIAL_STATE__: {e}")

            if load_all:
                # Scroll .note-scroller to bottom to load all comments
                scroller = page.locator(".note-scroller")
                if await scroller.count() > 0:
                    for _ in range(max_scroll):
                        # Check if there are more comments
                        try:
                            has_more = await self._safe_evaluate(
                                page,
                                """() => {
                                const state = window.__INITIAL_STATE__;
                                if (!state?.note?.noteDetailMap) return false;
                                const noteId = Object.keys(state.note.noteDetailMap)[0];
                                return state.note.noteDetailMap[noteId]?.comments?.hasMore || false;
                            }"""
                            )
                        except Exception:
                            has_more = False

                        if not has_more:
                            break

                        # Scroll to bottom
                        try:
                            await scroller.evaluate(
                                """el => {
                                el.scrollTop = el.scrollHeight;
                                el.dispatchEvent(new Event('scroll', { bubbles: true }));
                            }"""
                            )
                        except Exception as e:
                            logger.debug(f"Scroll error (will retry): {e}")
                            await asyncio.sleep(1)
                            continue
                        await asyncio.sleep(1.5)

            if expand_sub_comments:
                # Click all "展开 X 条回复" buttons to load sub-comments
                for _ in range(max_scroll):
                    # Find and click expand buttons
                    try:
                        clicked = await self._safe_evaluate(
                            page,
                            """() => {
                            const btns = document.querySelectorAll('.show-more');
                            let clicked = 0;
                            for (const btn of btns) {
                                if (btn.textContent.includes('展开') && btn.textContent.includes('回复')) {
                                    btn.click();
                                    clicked++;
                                }
                            }
                            return clicked;
                        }"""
                        )
                    except Exception:
                        clicked = 0

                    if not clicked:
                        break

                    await asyncio.sleep(1.5)

                    # Also check for "查看更多回复" inside expanded comments
                    try:
                        await self._safe_evaluate(
                            page,
                            """() => {
                            const moreLinks = document.querySelectorAll('[class*="more-reply"], [class*="load-more"]');
                            for (const link of moreLinks) {
                                if (link.textContent.includes('更多') || link.textContent.includes('查看')) {
                                    link.click();
                                }
                            }
                        }"""
                        )
                    except Exception:
                        pass
                    await asyncio.sleep(1)

            # Extract comments from __INITIAL_STATE__
            try:
                raw_comments = await self._safe_evaluate(page, JS_EXTRACT_COMMENTS)
            except Exception as e:
                logger.warning(f"Failed to extract comments: {e}")
                raw_comments = None

            # Extract content stats if requested
            content_stats = None
            if return_stats:
                try:
                    raw_stats = await self._safe_evaluate(page, JS_EXTRACT_CONTENT_STATS)
                    if raw_stats:
                        image_urls = raw_stats.get("imageUrls", [])
                        video_url = raw_stats.get("videoUrl") or ""
                        content_type = raw_stats.get("type", "normal")

                        content_stats = ContentStats(
                            platform=self.platform,
                            platform_content_id=raw_stats.get("noteId", ""),
                            likes=raw_stats.get("likes", "0"),
                            collects=raw_stats.get("collects", "0"),
                            comments=raw_stats.get("comments", "0"),
                            shares=raw_stats.get("shares", "0"),
                            image_urls=image_urls,
                            video_url=video_url,
                            content_type=content_type,
                        )
                        logger.debug(
                            f"Content stats: likes={content_stats.likes}, collects={content_stats.collects}, "
                            f"comments={content_stats.comments}, images={len(image_urls)}, video={'yes' if video_url else 'no'}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to extract content stats: {e}")

            # Extract content_id from URL for reference
            content_id = self._extract_content_id(content_url) or ""

            comments = []
            if raw_comments:
                for c in raw_comments:
                    # Parse sub comments
                    sub_comments = []
                    for sc in c.get("subComments", []):
                        sub_comments.append(
                            SubCommentItem(
                                platform=self.platform,
                                platform_comment_id=sc.get("id", ""),
                                platform_user_id=sc.get("userId", ""),
                                content=sc.get("content", ""),
                                nickname=sc.get("nickname", ""),
                                avatar=sc.get("avatar", ""),
                                likes=sc.get("likes", "0"),
                                create_time=sc.get("createTime", 0),
                                ip_location=sc.get("ipLocation", ""),
                                image_urls=sc.get("imageUrls", []),
                            )
                        )

                    comments.append(
                        CommentItem(
                            platform=self.platform,
                            platform_comment_id=c.get("id", ""),
                            platform_content_id=content_id,
                            platform_user_id=c.get("userId", ""),
                            content=c.get("content", ""),
                            nickname=c.get("nickname", ""),
                            avatar=c.get("avatar", ""),
                            likes=c.get("likes", "0"),
                            create_time=c.get("createTime", 0),
                            ip_location=c.get("ipLocation", ""),
                            image_urls=c.get("imageUrls", []),
                            sub_comment_count=c.get("subCommentCount", 0),
                            sub_comments=sub_comments,
                        )
                    )

            await page.close()

            if return_stats:
                return comments, content_stats
            return comments

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape_user(
        self,
        user_id: str,
        load_all_contents: bool = False,
        max_scroll: int = 20,
    ) -> UserInfo:
        """Scrape user profile information.

        Args:
            user_id: User ID (can be obtained from content author info)
            load_all_contents: If True, scroll to load all user contents
            max_scroll: Maximum number of scroll attempts when load_all_contents=True
        """
        # Use context manager pattern for standalone usage
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"
            await self._navigate_with_retry(page, user_url)
            await asyncio.sleep(5)

            if load_all_contents:
                # Scroll page to load more contents (contents load via DOM, not state)
                for _ in range(max_scroll):
                    try:
                        prev_count = await self._safe_evaluate(
                            page, "document.querySelectorAll('section.note-item').length"
                        ) or 0

                        await self._safe_evaluate(page, "window.scrollTo(0, document.body.scrollHeight)")
                        await asyncio.sleep(1.5)

                        new_count = await self._safe_evaluate(
                            page, "document.querySelectorAll('section.note-item').length"
                        ) or 0
                    except Exception:
                        break

                    if new_count == prev_count:
                        break

            # Extract user info from __INITIAL_STATE__
            try:
                raw_user_info = await self._safe_evaluate(
                    page,
                    """() => {
                    const state = window.__INITIAL_STATE__;
                    if (!state?.user) return null;

                    // Handle Vue reactivity - access _value or _rawValue
                    const pageData = state.user.userPageData?._value
                        || state.user.userPageData?._rawValue
                        || state.user.userPageData;

                    if (!pageData) return null;

                    const basic = pageData.basicInfo || {};
                    const interactions = pageData.interactions || [];

                    return {
                        userId: basic.userId || '',
                        nickname: basic.nickname || '',
                        avatar: basic.imageb || basic.image || '',
                        desc: basic.desc || '',
                        gender: basic.gender || 0,
                        ipLocation: basic.ipLocation || '',
                        redId: basic.redId || '',
                        follows: interactions[0]?.count || '0',
                        fans: interactions[1]?.count || '0',
                        interaction: interactions[2]?.count || '0',
                    };
                }"""
                )
            except Exception as e:
                logger.warning(f"Failed to extract user info: {e}")
                raw_user_info = None

            # Extract contents from DOM (more reliable than state for pagination)
            try:
                raw_contents = await self._safe_evaluate(
                    page,
                    """() => {
                    const cards = document.querySelectorAll('section.note-item');
                    return Array.from(cards).map(card => {
                        const linkEl = card.querySelector('a');
                        const titleEl = card.querySelector('.title span, .footer .title');
                        const imgEl = card.querySelector('img');
                        const likeEl = card.querySelector('.like-wrapper .count');

                        // Get content URL which contains content ID and xsec_token
                        const href = linkEl?.href || '';
                        const contentIdMatch = href.match(/explore\\/([a-f0-9]+)/);
                        const xsecMatch = href.match(/xsec_token=([^&]+)/);

                        // Check if video (has video icon or duration)
                        const isVideo = !!card.querySelector('[class*="video"], .play-icon, .duration');

                        return {
                            contentId: contentIdMatch ? contentIdMatch[1] : '',
                            title: titleEl?.textContent?.trim() || '',
                            type: isVideo ? 'video' : 'normal',
                            likes: likeEl?.textContent?.trim() || '0',
                            coverUrl: imgEl?.src || '',
                            xsecToken: xsecMatch ? decodeURIComponent(xsecMatch[1]) : '',
                        };
                    });
                }"""
                )
            except Exception as e:
                logger.warning(f"Failed to extract user contents: {e}")
                raw_contents = None

            await page.close()

            if not raw_user_info:
                return UserInfo(
                    platform=self.platform,
                    platform_user_id=user_id,
                    nickname="",
                    avatar="",
                )

            # Build UserInfo object with platform-specific data in platform_data
            user_contents = [
                UserContentItem(
                    platform=self.platform,
                    platform_content_id=c.get("contentId", ""),
                    title=c.get("title", ""),
                    content_type=c.get("type", "normal"),
                    likes=c.get("likes", "0"),
                    cover_url=c.get("coverUrl", ""),
                    platform_data={"xsec_token": c.get("xsecToken", "")} if c.get("xsecToken") else {},
                )
                for c in (raw_contents or [])
            ]

            # Store XHS-specific red_id in platform_data
            platform_data = {}
            if raw_user_info.get("redId"):
                platform_data["red_id"] = raw_user_info.get("redId")

            return UserInfo(
                platform=self.platform,
                platform_user_id=raw_user_info.get("userId") or user_id,
                nickname=raw_user_info.get("nickname", ""),
                avatar=raw_user_info.get("avatar", ""),
                description=raw_user_info.get("desc", ""),
                gender=raw_user_info.get("gender", 0),
                ip_location=raw_user_info.get("ipLocation", ""),
                follows=raw_user_info.get("follows", "0"),
                fans=raw_user_info.get("fans", "0"),
                interaction=raw_user_info.get("interaction", "0"),
                contents=user_contents,
                platform_data=platform_data,
            )

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

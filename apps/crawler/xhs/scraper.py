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
    NoteItem,
    SubCommentItem,
    UserInfo,
    UserNoteItem,
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


# JS to extract comments from __INITIAL_STATE__
JS_EXTRACT_COMMENTS = """() => {
    const state = window.__INITIAL_STATE__;
    if (!state || !state.note || !state.note.noteDetailMap) return null;

    const noteId = Object.keys(state.note.noteDetailMap)[0];
    if (!noteId) return null;

    const detail = state.note.noteDetailMap[noteId];
    if (!detail || !detail.comments) return null;

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

    # Class-level LRU cache shared across instances for long-running processes
    # This persists across scrape sessions while still having bounded memory
    _url_cache = LRUCache(max_size=10000, ttl_seconds=86400)  # 24h TTL

    def __init__(self):
        self.settings = get_settings()
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None

    async def __aenter__(self) -> Self:
        """Initialize browser on context enter."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.crawler.headless
        )
        self._context = await self._browser.new_context()

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

    async def _scroll_page(self, page: Page) -> None:
        """Scroll page to load more content."""
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

    async def _open_filter_panel(self, page: Page) -> bool:
        """Open the filter panel by clicking the '筛选' button.

        Returns True if panel opened successfully.
        """
        try:
            # Click the filter button using JavaScript to avoid modal interception
            clicked = await page.evaluate("""() => {
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
            await page.evaluate("""() => {
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

    async def _extract_notes_from_page(self, page: Page) -> list[dict]:
        """Extract note data from current page."""
        return await page.evaluate(
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
                let noteUrl = '';
                if (linkEl && linkEl.href) {
                    noteUrl = linkEl.href;
                }

                const imgEl = card.querySelector('img');
                const imageUrls = imgEl && imgEl.src ? [imgEl.src] : [];

                return { title, likes, noteUrl, imageUrls };
            });
        }"""
        )

    async def scrape(
        self,
        keyword: str,
        *,
        sort_by: SortBy = SortBy.GENERAL,
        note_type: NoteType = NoteType.ALL,
        max_notes: Optional[int] = None,
        max_scroll: int = 100,
        recent_note_urls: Optional[Dict[str, datetime]] = None,
        dedup_window_hours: int = 24,
    ) -> list[NoteItem]:
        """Scrape notes for a keyword.

        Args:
            keyword: Search keyword
            sort_by: Sort order (GENERAL/NEWEST/MOST_LIKED/MOST_COMMENTS/MOST_COLLECTED)
            note_type: Note type filter (ALL/IMAGE/VIDEO)
            max_notes: Maximum notes to return (default from config)
            max_scroll: Maximum scroll attempts before giving up (default 100)
            recent_note_urls: Dict of {note_url: last_scraped_time} for smart dedup
                - URLs scraped within dedup_window_hours will be SKIPPED (same-day dedup)
                - URLs scraped before dedup_window_hours will be INCLUDED (for update)
            dedup_window_hours: Hours within which to skip already-scraped notes (default 24)

        Returns:
            List of unique NoteItem objects
        """
        if max_notes is None:
            max_notes = self.settings.crawler.default_max_notes

        # Calculate dedup cutoff time
        dedup_cutoff = datetime.utcnow() - timedelta(hours=dedup_window_hours)

        # Build set of URLs to skip (only those scraped within the dedup window)
        skip_urls: Set[str] = set()
        if recent_note_urls:
            for url, scraped_time in recent_note_urls.items():
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

            # Apply sort filter if not default
            if sort_by != SortBy.GENERAL:
                await self._apply_sort_filter(page, sort_by)
                await asyncio.sleep(2)

            # Apply note type filter if not ALL
            if note_type != NoteType.ALL:
                await self._apply_note_type_filter(page, note_type)
                await asyncio.sleep(2)

            items: list[NoteItem] = []
            no_new_content_count = 0
            max_no_new_content = 3  # Stop after 3 consecutive scrolls with no new content

            for scroll_idx in range(max_scroll):
                # Extract current visible notes
                raw_items = await self._extract_notes_from_page(page)

                if not raw_items:
                    raw_items = []

                items_before = len(items)

                for item in raw_items:
                    note_url = item.get("noteUrl", "")

                    # Skip if already seen in LRU cache (bounded memory dedup)
                    if note_url in self._url_cache:
                        continue

                    # Skip if scraped within dedup window (from database)
                    if note_url in skip_urls:
                        self._url_cache.add(note_url)  # Mark as seen
                        continue

                    self._url_cache.add(note_url)

                    items.append(
                        NoteItem(
                            title=item.get("title", "N/A"),
                            likes=item.get("likes", "0"),
                            collects="0",
                            comments="0",
                            publish_time="",
                            note_url=note_url,
                            image_urls=item.get("imageUrls", []),
                        )
                    )

                    if len(items) >= max_notes:
                        break

                # Check if we reached target
                if len(items) >= max_notes:
                    logger.info(f"Reached target of {max_notes} notes")
                    break

                # Check if we got new items this scroll
                items_added = len(items) - items_before
                if items_added == 0:
                    no_new_content_count += 1
                    logger.debug(f"No new items after scroll {scroll_idx + 1}, count={no_new_content_count}")
                    if no_new_content_count >= max_no_new_content:
                        logger.info(f"No new content after {max_no_new_content} scrolls, stopping")
                        break
                else:
                    no_new_content_count = 0  # Reset counter

                # Scroll to load more
                await self._scroll_page(page)
                await asyncio.sleep(1.5)

            await page.close()

            logger.info(f"Scraped {len(items)} unique notes for keyword: {keyword} (scrolled {scroll_idx + 1} times)")
            return items

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape_comments(
        self,
        note_url: str,
        load_all: bool = False,
        expand_sub_comments: bool = False,
        max_scroll: int = 20,
    ) -> list[CommentItem]:
        """Scrape comments from a note.

        Args:
            note_url: Full URL of the note (must include xsec_token)
            load_all: If True, scroll to load all comments
            expand_sub_comments: If True, click to expand all sub-comments
            max_scroll: Maximum number of scroll attempts when load_all=True
        """
        # Use context manager pattern for standalone usage
        should_close = False
        if not self._context:
            await self.__aenter__()
            should_close = True

        try:
            page = await self._get_page()

            await self._navigate_with_retry(page, note_url)
            await asyncio.sleep(5)

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
                        has_more = await page.evaluate(
                            """() => {
                            const state = window.__INITIAL_STATE__;
                            if (!state?.note?.noteDetailMap) return false;
                            const noteId = Object.keys(state.note.noteDetailMap)[0];
                            return state.note.noteDetailMap[noteId]?.comments?.hasMore || false;
                        }"""
                        )

                        if not has_more:
                            break

                        # Scroll to bottom
                        await scroller.evaluate(
                            """el => {
                            el.scrollTop = el.scrollHeight;
                            el.dispatchEvent(new Event('scroll', { bubbles: true }));
                        }"""
                        )
                        await asyncio.sleep(1.5)

            if expand_sub_comments:
                # Click all "展开 X 条回复" buttons to load sub-comments
                for _ in range(max_scroll):
                    # Find and click expand buttons
                    clicked = await page.evaluate(
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

                    if clicked == 0:
                        break

                    await asyncio.sleep(1.5)

                    # Also check for "查看更多回复" inside expanded comments
                    await page.evaluate(
                        """() => {
                        const moreLinks = document.querySelectorAll('[class*="more-reply"], [class*="load-more"]');
                        for (const link of moreLinks) {
                            if (link.textContent.includes('更多') || link.textContent.includes('查看')) {
                                link.click();
                            }
                        }
                    }"""
                    )
                    await asyncio.sleep(1)

            # Extract comments from __INITIAL_STATE__
            raw_comments = await page.evaluate(JS_EXTRACT_COMMENTS)

            comments = []
            if raw_comments:
                for c in raw_comments:
                    # Parse sub comments
                    sub_comments = []
                    for sc in c.get("subComments", []):
                        sub_comments.append(
                            SubCommentItem(
                                comment_id=sc.get("id", ""),
                                content=sc.get("content", ""),
                                user_id=sc.get("userId", ""),
                                nickname=sc.get("nickname", ""),
                                avatar=sc.get("avatar", ""),
                                likes=sc.get("likes", "0"),
                                create_time=sc.get("createTime", 0),
                                ip_location=sc.get("ipLocation", ""),
                            )
                        )

                    comments.append(
                        CommentItem(
                            comment_id=c.get("id", ""),
                            content=c.get("content", ""),
                            user_id=c.get("userId", ""),
                            nickname=c.get("nickname", ""),
                            avatar=c.get("avatar", ""),
                            likes=c.get("likes", "0"),
                            create_time=c.get("createTime", 0),
                            ip_location=c.get("ipLocation", ""),
                            sub_comment_count=c.get("subCommentCount", 0),
                            sub_comments=sub_comments,
                        )
                    )

            await page.close()
            return comments

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

    async def scrape_user(
        self,
        user_id: str,
        load_all_notes: bool = False,
        max_scroll: int = 20,
    ) -> UserInfo:
        """Scrape user profile information.

        Args:
            user_id: User ID (can be obtained from note author info)
            load_all_notes: If True, scroll to load all user notes
            max_scroll: Maximum number of scroll attempts when load_all_notes=True
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

            if load_all_notes:
                # Scroll page to load more notes (notes load via DOM, not state)
                for _ in range(max_scroll):
                    prev_count = await page.evaluate(
                        "document.querySelectorAll('section.note-item').length"
                    )

                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1.5)

                    new_count = await page.evaluate(
                        "document.querySelectorAll('section.note-item').length"
                    )

                    if new_count == prev_count:
                        break

            # Extract user info from __INITIAL_STATE__
            raw_user_info = await page.evaluate(
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

            # Extract notes from DOM (more reliable than state for pagination)
            raw_notes = await page.evaluate(
                """() => {
                const cards = document.querySelectorAll('section.note-item');
                return Array.from(cards).map(card => {
                    const linkEl = card.querySelector('a');
                    const titleEl = card.querySelector('.title span, .footer .title');
                    const imgEl = card.querySelector('img');
                    const likeEl = card.querySelector('.like-wrapper .count');

                    // Get note URL which contains note ID and xsec_token
                    const href = linkEl?.href || '';
                    const noteIdMatch = href.match(/explore\\/([a-f0-9]+)/);
                    const xsecMatch = href.match(/xsec_token=([^&]+)/);

                    // Check if video (has video icon or duration)
                    const isVideo = !!card.querySelector('[class*="video"], .play-icon, .duration');

                    return {
                        noteId: noteIdMatch ? noteIdMatch[1] : '',
                        title: titleEl?.textContent?.trim() || '',
                        type: isVideo ? 'video' : 'normal',
                        likes: likeEl?.textContent?.trim() || '0',
                        coverUrl: imgEl?.src || '',
                        xsecToken: xsecMatch ? decodeURIComponent(xsecMatch[1]) : '',
                    };
                });
            }"""
            )

            await page.close()

            if not raw_user_info:
                return UserInfo(user_id=user_id, nickname="", avatar="")

            # Build UserInfo object
            user_notes = [
                UserNoteItem(
                    note_id=n.get("noteId", ""),
                    title=n.get("title", ""),
                    type=n.get("type", "normal"),
                    likes=n.get("likes", "0"),
                    cover_url=n.get("coverUrl", ""),
                    xsec_token=n.get("xsecToken", ""),
                )
                for n in (raw_notes or [])
            ]

            return UserInfo(
                user_id=raw_user_info.get("userId") or user_id,
                nickname=raw_user_info.get("nickname", ""),
                avatar=raw_user_info.get("avatar", ""),
                desc=raw_user_info.get("desc", ""),
                gender=raw_user_info.get("gender", 0),
                ip_location=raw_user_info.get("ipLocation", ""),
                red_id=raw_user_info.get("redId", ""),
                follows=raw_user_info.get("follows", "0"),
                fans=raw_user_info.get("fans", "0"),
                interaction=raw_user_info.get("interaction", "0"),
                notes=user_notes,
            )

        finally:
            if should_close:
                await self.__aexit__(None, None, None)

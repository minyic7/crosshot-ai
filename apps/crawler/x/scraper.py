"""X (Twitter) Crawler Implementation.

Optimized Strategy (Based on Community Feedback):
- Following Timeline scraping (primary use case)
- 8-12 sessions per day, 10-20 min each
- 1-4 second delays (X is more relaxed than XHS)
- 15-25 scrolls per session with early stop
- No IP rotation needed (Cookie auth sufficient)
- 2000-3500 tweets/day target

Architecture:
- Inherits from BaseCrawler for standard interface
- Uses Playwright for browser automation with stealth
- Cookie-based authentication (from .env)
- Human behavior simulation (random scrolls, delays)
"""

import asyncio
import json
import logging
import random
from collections import deque
from pathlib import Path
from typing import List, Optional, Dict, AsyncGenerator, Set
from datetime import datetime, timedelta
from enum import Enum

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from apps.crawler.base import (
    BaseCrawler,
    ContentItem,
    UserInfo,
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

    Optimized for Following Timeline scraping with human-like behavior.

    Strategy:
    - 1-4 second delays (faster than XHS)
    - 15-25 scrolls per session
    - Early stop after 3 consecutive scrolls with <5 new tweets
    - No IP rotation (Cookie auth)

    Usage:
        async with XCrawler() as crawler:
            tweets = await crawler.scrape_following_timeline(max_tweets=200)
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
        self._url_cache = LRUCache(max_size=10000)

        # Video URL interception storage with memory bounds
        self._video_urls: deque = deque(maxlen=100)  # Bounded queue (max 100 videos)
        self._video_urls_seen: set = set()  # O(1) lookup for deduplication

        # Strategy parameters (optimized for X)
        self.SCROLL_DELAY_MIN = 1  # seconds (faster than XHS)
        self.SCROLL_DELAY_MAX = 4  # seconds
        self.MAX_SCROLL_COUNT = 25  # per session
        self.EARLY_STOP_THRESHOLD = 3  # consecutive scrolls
        self.EARLY_STOP_MIN_NEW = 5  # min new tweets per scroll

        # Request rate tracking
        self._request_count = 0
        self._request_start_time: Optional[datetime] = None
        self._page_count = 0  # Total pages opened

    # =========================================================================
    # Context Manager (Browser Lifecycle)
    # =========================================================================

    async def __aenter__(self):
        """Initialize browser with stealth configuration and cookies."""
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

        # Create context with realistic settings (en-US for X)
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Set timeouts to prevent indefinite blocking
        self._context.set_default_timeout(60000)  # 60 seconds for all operations
        self._context.set_default_navigation_timeout(60000)  # 60 seconds for navigation

        # Inject stealth JavaScript (enhanced for X)
        await self._context.add_init_script("""
            // Override webdriver property
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

            // Add chrome object
            window.chrome = { runtime: {} };

            // Override plugins and mimeTypes
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            Object.defineProperty(navigator, 'mimeTypes', {
                get: () => [1, 2, 3, 4]
            });

            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Override languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en']
            });
        """)

        # Load X cookies from config (required for Following timeline)
        try:
            cookies_json = self.settings.x.cookies_json
            if cookies_json:
                cookies = json.loads(cookies_json)
                await self._context.add_cookies(cookies)
                logger.info(f"Loaded {len(cookies)} X cookies from config")
            else:
                logger.warning("No X cookies configured - Following timeline may not work")
        except Exception as e:
            logger.error(f"Failed to load X cookies: {e}")

        # Set up network interception for video URLs
        self._context.on('response', self._handle_response)
        logger.info("Network interception enabled for video capture")

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
    # Following Timeline Scraping (Primary Feature)
    # =========================================================================

    async def scrape_home_timeline(
        self,
        *,
        max_tweets: Optional[int] = None,
        max_scroll: Optional[int] = None,
    ) -> List[ContentItem]:
        """Scrape X home timeline (For You feed).

        This scrapes from the main For You tab, which includes:
        - Posts from accounts you follow
        - Recommended/promoted content
        - Reposts and replies

        Args:
            max_tweets: Maximum tweets to collect (None = until early stop)
            max_scroll: Maximum scroll attempts (default: self.MAX_SCROLL_COUNT)

        Returns:
            List of ContentItem objects representing tweets
        """
        logger.info(f"Scraping X home timeline (max_tweets={max_tweets})")

        page = await self._get_page()
        tweets: List[ContentItem] = []
        seen_urls: Set[str] = set()

        try:
            # Navigate to home timeline (For You feed)
            logger.info("Navigating to X home page...")
            await page.goto('https://x.com/home', wait_until='domcontentloaded')
            await self._human_delay(3, 5)
            logger.info("✓ Home timeline loaded (For You feed)")

            # Wait for tweets to load (longer timeout)
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
                logger.info("Timeline loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load timeline: {e}")
                logger.error(f"Current URL: {page.url}")
                # Take screenshot for debugging
                try:
                    screenshot_path = Path("data/debug_screenshots")
                    screenshot_path.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path="data/debug_screenshots/x_crawler_error.png")
                    logger.info("Screenshot saved: data/debug_screenshots/x_crawler_error.png")
                except:
                    pass
                return tweets

            # Scroll and extract tweets
            scroll_count = max_scroll or self.MAX_SCROLL_COUNT
            early_stop_counter = 0

            for i in range(scroll_count):
                logger.info(f"Scroll {i+1}/{scroll_count}")

                # Extract tweets from current view
                new_tweets = await self._extract_tweets_from_page(page, seen_urls)
                tweets.extend(new_tweets)
                logger.info(f"  Extracted {len(new_tweets)} new tweets (total: {len(tweets)})")

                # Early stop check
                if len(new_tweets) < self.EARLY_STOP_MIN_NEW:
                    early_stop_counter += 1
                    logger.info(f"  Early stop counter: {early_stop_counter}/{self.EARLY_STOP_THRESHOLD}")
                    if early_stop_counter >= self.EARLY_STOP_THRESHOLD:
                        logger.info("Early stop triggered - no new tweets")
                        break
                else:
                    early_stop_counter = 0  # Reset

                # Max tweets check
                if max_tweets and len(tweets) >= max_tweets:
                    logger.info(f"Reached max_tweets limit: {max_tweets}")
                    break

                # Human-like scroll
                await self._human_scroll(page)
                await self._human_delay(self.SCROLL_DELAY_MIN, self.SCROLL_DELAY_MAX)

            logger.info(f"Scraping complete. Collected {len(tweets)} tweets")
            return tweets[:max_tweets] if max_tweets else tweets

        finally:
            await page.close()

    async def _extract_tweets_from_page(
        self,
        page: Page,
        seen_urls: Set[str]
    ) -> List[ContentItem]:
        """Extract tweets from current page view.

        Args:
            page: Playwright page object
            seen_urls: Set of already-seen URLs for deduplication

        Returns:
            List of new ContentItem objects (deduplicated)
        """
        # Wait a moment for network requests to complete and videos to load
        await asyncio.sleep(2.0)

        tweets_data = await page.evaluate("""
            () => {
                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                const tweets = [];

                articles.forEach(article => {
                    try {
                        // Author info
                        const authorElement = article.querySelector('[data-testid="User-Name"]');
                        const author = authorElement ? authorElement.innerText.split('\\n')[0] : 'Unknown';
                        const username = authorElement ? authorElement.innerText.split('\\n')[1] : '';

                        // Post text
                        const tweetTextElement = article.querySelector('[data-testid="tweetText"]');
                        const text = tweetTextElement ? tweetTextElement.innerText : '';

                        // Time
                        const timeElement = article.querySelector('time');
                        const timestamp = timeElement ? timeElement.getAttribute('datetime') : '';
                        const timeAgo = timeElement ? timeElement.innerText : '';

                        // Engagement metrics
                        const replyButton = article.querySelector('[data-testid="reply"]');
                        const retweetButton = article.querySelector('[data-testid="retweet"]');
                        const likeButton = article.querySelector('[data-testid="like"]');

                        const replies = replyButton ? replyButton.getAttribute('aria-label') || '0' : '0';
                        const retweets = retweetButton ? retweetButton.getAttribute('aria-label') || '0' : '0';
                        const likes = likeButton ? likeButton.getAttribute('aria-label') || '0' : '0';

                        // URL
                        const linkElement = article.querySelector('a[href*="/status/"]');
                        const url = linkElement ? 'https://x.com' + linkElement.getAttribute('href') : '';

                        // Images
                        const imageElements = article.querySelectorAll('img[src*="pbs.twimg.com/media"]');
                        const images = Array.from(imageElements).map(img => img.src);

                        // Videos
                        const videos = [];
                        const videoElements = article.querySelectorAll('video');
                        videoElements.forEach(video => {
                            // Try to get video source from source tag
                            const source = video.querySelector('source');
                            if (source && source.src) {
                                videos.push(source.src);
                            } else if (video.src) {
                                videos.push(video.src);
                            }
                            // Also try poster as fallback (thumbnail)
                            else if (video.poster && !videos.length) {
                                videos.push(video.poster);
                            }
                        });

                        tweets.push({
                            author,
                            username,
                            text,
                            timestamp,
                            timeAgo,
                            replies,
                            retweets,
                            likes,
                            url,
                            images,
                            videos
                        });
                    } catch (e) {
                        console.error('Error extracting tweet:', e);
                    }
                });

                return tweets;
            }
        """)

        # Convert to ContentItem and deduplicate
        new_tweets = []

        # Build video URL index for smart matching
        # Map tweet IDs to intercepted video URLs
        video_url_map: Dict[str, str] = {}
        unmatched_videos: List[str] = []

        for video_url in self._video_urls:
            # Try to extract tweet ID from video URL
            matched = False
            for data in tweets_data:
                tweet_url = data.get('url', '')
                tweet_id = self._extract_tweet_id(tweet_url)
                if tweet_id and tweet_id in video_url:
                    video_url_map[tweet_id] = video_url
                    matched = True
                    break
            if not matched:
                unmatched_videos.append(video_url)

        total_intercepted = len(self._video_urls)
        if total_intercepted > 0:
            logger.info(f"   Video matching: {len(video_url_map)} matched, {len(unmatched_videos)} unmatched")

        # Index for unmatched videos (fallback assignment)
        unmatched_index = 0

        for data in tweets_data:
            url = data.get('url', '')
            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            # Parse engagement metrics (keep as strings)
            likes = self._parse_engagement(data.get('likes', '0'))
            retweets = self._parse_engagement(data.get('retweets', '0'))
            replies = self._parse_engagement(data.get('replies', '0'))

            # Extract tweet ID from URL
            tweet_id = self._extract_tweet_id(url) or url.split('/')[-1]

            # Use intercepted video URLs with smart matching
            video_urls = []
            dom_videos = data.get('videos', [])
            has_video = bool(dom_videos)  # Tweet has video element in DOM

            # Priority 1: Use matched video URL (by tweet ID)
            if tweet_id in video_url_map:
                video_urls = [video_url_map[tweet_id]]
                logger.info(f"   ✓ Tweet {tweet_id}: matched video by ID")
            # Priority 2: Assign unmatched video to tweets with video elements
            elif has_video and unmatched_index < len(unmatched_videos):
                video_urls = [unmatched_videos[unmatched_index]]
                unmatched_index += 1
                logger.info(f"   ✓ Tweet {tweet_id}: assigned unmatched video")
            # Priority 3: Fallback to DOM-extracted URLs (blob URLs)
            elif dom_videos:
                video_urls = dom_videos
                logger.debug(f"   ⚠ Tweet {tweet_id}: using blob URLs from DOM")

            tweet = ContentItem(
                platform="x",
                platform_content_id=tweet_id,
                title=data.get('text', ''),  # Full tweet text as title
                content_url=url,
                likes=likes,
                collects=retweets,  # Use retweets as collects
                comments=replies,
                publish_time=self._parse_timestamp(data.get('timestamp', '')),
                image_urls=data.get('images', []),
                video_urls=video_urls,  # Use intercepted or blob URLs
                platform_data={
                    'author': data.get('author', 'Unknown'),
                    'username': data.get('username', ''),
                    'author_url': f"https://x.com/{data.get('username', '').replace('@', '')}",
                    'timestamp': data.get('timestamp', ''),
                    'timeAgo': data.get('timeAgo', ''),
                }
            )
            new_tweets.append(tweet)

        # Clear intercepted videos after use to avoid reusing them
        self._video_urls.clear()

        return new_tweets

    def _parse_engagement(self, value: str) -> str:
        """Parse engagement metric (keep as string).

        Examples:
            "123 Likes. Like" -> "123"
            "1.2K Likes" -> "1.2K"
        """
        if not value:
            return "0"
        # Extract first word (number)
        parts = value.split()
        return parts[0] if parts else "0"

    def _parse_timestamp(self, iso_string: str) -> str:
        """Parse ISO timestamp string to string format."""
        if not iso_string:
            return datetime.now().isoformat()
        try:
            # Parse and return as ISO string
            dt = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
            return dt.isoformat()
        except:
            return datetime.now().isoformat()

    async def _human_scroll(self, page: Page):
        """Simulate human-like scrolling behavior.

        Randomly scrolls:
        - Mostly down (90%)
        - Sometimes up briefly then down (10% - simulate re-reading)
        - Variable scroll distance
        """
        if random.random() < 0.1:
            # 10% chance: scroll up briefly then down (simulate re-reading)
            up_distance = random.randint(100, 300)
            await page.evaluate(f'window.scrollBy(0, -{up_distance})')
            await asyncio.sleep(random.uniform(0.5, 1.0))
            down_distance = up_distance + random.randint(400, 800)
            await page.evaluate(f'window.scrollBy(0, {down_distance})')
        else:
            # 90% chance: normal scroll down
            distance = random.randint(600, 1000)  # Variable scroll distance
            await page.evaluate(f'window.scrollBy(0, {distance})')

    async def _human_delay(self, min_sec: float, max_sec: float):
        """Simulate human thinking/reading delay."""
        delay = random.uniform(min_sec, max_sec)
        await asyncio.sleep(delay)

    # =========================================================================
    # Required Methods (from BaseCrawler) - TODO for future
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
            keyword: Search query (e.g., "machine learning", "from:elonmusk", "#python")
            sort_by: Sort order (TOP, LATEST, PHOTOS, VIDEOS, PEOPLE)
            max_notes: Maximum tweets to collect (None = until early stop)
            max_scroll: Maximum scroll attempts (default: 100)

        Returns:
            List of ContentItem objects representing matching tweets

        Example:
            tweets = await crawler.scrape("OpenAI", sort_by=SortBy.LATEST, max_notes=50)
        """
        from urllib.parse import quote

        logger.info(f"Searching X for keyword: '{keyword}' (sort={sort_by.value}, max_notes={max_notes})")

        page = await self._get_page()
        tweets: List[ContentItem] = []
        seen_urls: Set[str] = set()

        try:
            # Build search URL based on sort_by
            encoded_keyword = quote(keyword)
            base_url = f"https://x.com/search?q={encoded_keyword}&src=typed_query"

            # Add filter parameter based on sort_by
            if sort_by == SortBy.LATEST:
                search_url = f"{base_url}&f=live"
            elif sort_by == SortBy.PHOTOS:
                search_url = f"{base_url}&f=image"
            elif sort_by == SortBy.VIDEOS:
                search_url = f"{base_url}&f=video"
            elif sort_by == SortBy.PEOPLE:
                search_url = f"{base_url}&f=user"
            else:  # TOP
                search_url = base_url

            # Navigate to search page
            logger.info(f"Navigating to search: {search_url}")
            await page.goto(search_url, wait_until='domcontentloaded')
            await self._human_delay(3, 5)
            logger.info(f"✓ Search page loaded")

            # Wait for search results to load
            try:
                if sort_by == SortBy.PEOPLE:
                    # People tab has different selector
                    await page.wait_for_selector('[data-testid="UserCell"]', timeout=20000)
                    logger.warning("People search not yet supported - returning empty results")
                    return tweets
                else:
                    # Wait for tweet articles
                    await page.wait_for_selector('article[data-testid="tweet"]', timeout=20000)
                    logger.info("Search results loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load search results: {e}")
                logger.error(f"Current URL: {page.url}")
                # Take screenshot for debugging
                try:
                    screenshot_path = Path("data/debug_screenshots")
                    screenshot_path.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path="data/debug_screenshots/x_search_error.png")
                    logger.info("Screenshot saved: data/debug_screenshots/x_search_error.png")
                except:
                    pass
                return tweets

            # Scroll and extract tweets
            scroll_count = min(max_scroll, self.MAX_SCROLL_COUNT * 4)  # Allow more scrolls for search
            early_stop_counter = 0

            for i in range(scroll_count):
                logger.info(f"Scroll {i+1}/{scroll_count}")

                # Extract tweets from current view
                new_tweets = await self._extract_tweets_from_page(page, seen_urls)
                tweets.extend(new_tweets)
                logger.info(f"  Extracted {len(new_tweets)} new tweets (total: {len(tweets)})")

                # Early stop check
                if len(new_tweets) < self.EARLY_STOP_MIN_NEW:
                    early_stop_counter += 1
                    logger.info(f"  Early stop counter: {early_stop_counter}/{self.EARLY_STOP_THRESHOLD}")
                    if early_stop_counter >= self.EARLY_STOP_THRESHOLD:
                        logger.info("Early stop triggered - no new tweets")
                        break
                else:
                    early_stop_counter = 0  # Reset

                # Max notes check
                if max_notes and len(tweets) >= max_notes:
                    logger.info(f"Reached max_notes limit: {max_notes}")
                    break

                # Human-like scroll
                await self._human_scroll(page)
                await self._human_delay(self.SCROLL_DELAY_MIN, self.SCROLL_DELAY_MAX)

            logger.info(f"Search complete. Collected {len(tweets)} tweets for '{keyword}'")
            return tweets[:max_notes] if max_notes else tweets

        finally:
            await page.close()

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
        """TODO: Implement continuous scraping for search."""
        logger.warning("scrape_continuous() not implemented")
        raise NotImplementedError("Not yet implemented")
        yield  # type: ignore

    async def scrape_user(
        self,
        user_id: str,
        *,
        load_all_contents: bool = False,
        max_retries: int = 2
    ) -> UserInfo:
        """Scrape user profile information from X with retry.

        Args:
            user_id: Username (without @) or user ID
            load_all_contents: Not used for X (kept for compatibility)
            max_retries: Maximum retry attempts (default: 2)

        Returns:
            UserInfo object with profile data
        """
        # Remove @ if present
        username = user_id.replace('@', '')

        last_error = None
        for attempt in range(max_retries + 1):
            if attempt > 0:
                logger.info(f"Retry {attempt}/{max_retries} for @{username}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff: 2s, 4s

            logger.info(f"Scraping user profile: @{username}")
            page = await self._get_page()

            try:
                # Navigate to user profile
                profile_url = f"https://x.com/{username}"
                await page.goto(profile_url, wait_until='domcontentloaded')
                await self._human_delay(2, 4)

                # Wait for profile to load
                try:
                    await page.wait_for_selector('[data-testid="UserName"]', timeout=10000)
                except Exception as e:
                    logger.error(f"Failed to load profile for @{username}: {e}")
                    raise

            # Extract user information using JavaScript
            user_data = await page.evaluate("""
                () => {
                    const data = {};

                    // Display name - try multiple selectors
                    let nameEl = document.querySelector('[data-testid="UserName"] span');
                    if (!nameEl) {
                        const userHeader = document.querySelector('[data-testid="UserName"]');
                        if (userHeader) {
                            const spans = userHeader.querySelectorAll('span');
                            nameEl = spans[0];
                        }
                    }
                    data.name = nameEl ? nameEl.textContent.trim() : '';

                    // Username - extract from URL or screen name element
                    let usernameEl = document.querySelector('[data-testid="UserScreenName"]');
                    if (usernameEl) {
                        // Get the text content and extract username
                        const text = usernameEl.textContent || '';
                        const match = text.match(/@([\\w]+)/);
                        data.username = match ? match[1] : '';
                    }

                    // Fallback: extract from URL
                    if (!data.username) {
                        const urlMatch = window.location.pathname.match(/^\\/([^\\/]+)/);
                        data.username = urlMatch ? urlMatch[1] : '';
                    }

                    // Bio/Description
                    const bioEl = document.querySelector('[data-testid="UserDescription"]');
                    data.bio = bioEl ? bioEl.textContent.trim() : '';

                    // Avatar - try multiple selectors
                    let avatarEl = document.querySelector('a[href$="/photo"] img');
                    if (!avatarEl) {
                        avatarEl = document.querySelector('[data-testid="UserAvatar-Container-"] img');
                    }
                    if (!avatarEl) {
                        const allImgs = document.querySelectorAll('img[src*="profile_images"]');
                        avatarEl = allImgs[0];
                    }
                    data.avatar = avatarEl ? avatarEl.src : '';

                    // Follower/Following counts - more robust extraction
                    const statsLinks = document.querySelectorAll('a[href*="/followers"], a[href*="/following"], a[href*="/verified_followers"]');
                    for (const link of statsLinks) {
                        const text = link.textContent || '';
                        // Match numbers before "Following"
                        if (text.toLowerCase().includes('following')) {
                            const match = text.match(/([\\d,\\.]+[KMB]?)/);
                            data.following = match ? match[1] : '0';
                        }
                        // Match numbers before "Follower"
                        else if (text.toLowerCase().includes('follower')) {
                            const match = text.match(/([\\d,\\.]+[KMB]?)/);
                            data.followers = match ? match[1] : '0';
                        }
                    }

                    // Set defaults if not found
                    if (!data.followers) data.followers = '0';
                    if (!data.following) data.following = '0';

                    // Location
                    const locationEl = document.querySelector('[data-testid="UserLocation"]');
                    data.location = locationEl ? locationEl.textContent.trim() : '';

                    // Website
                    const websiteEl = document.querySelector('[data-testid="UserUrl"] a');
                    data.website = websiteEl ? websiteEl.href : '';

                    // Join date
                    const joinEl = document.querySelector('[data-testid="UserJoinDate"]');
                    data.joinDate = joinEl ? joinEl.textContent.trim() : '';

                    return data;
                }
            """)

            logger.info(f"✓ Scraped profile: @{user_data.get('username', username)} ({user_data.get('name', 'Unknown')})")

            # Create UserInfo object
            user_info = UserInfo(
                platform="x",
                platform_user_id=user_data.get('username', username),
                nickname=user_data.get('name', ''),
                avatar=user_data.get('avatar', ''),
                fans=user_data.get('followers', '0'),  # Fixed: fans not followers
                follows=user_data.get('following', '0'),  # Fixed: follows not following
                description=user_data.get('bio', ''),
                ip_location=user_data.get('location', ''),
                platform_data={
                    'website': user_data.get('website', ''),
                    'joinDate': user_data.get('joinDate', ''),
                    'profile_url': profile_url,  # Move to platform_data
                }
            )

                return user_info

            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt+1} failed for @{username}: {e}")
            finally:
                try:
                    await page.close()
                except Exception:
                    pass  # Page or context already closed

        # All retries failed
        logger.error(f"All {max_retries+1} attempts failed for @{username}")
        raise last_error or RuntimeError(f"Failed to scrape user @{username}")

    async def scrape_comments(
        self,
        content_url: str,
        *,
        load_all: bool = True,
        expand_sub_comments: bool = True,
        max_scrolls: Optional[int] = None,
    ) -> List[CommentItem]:
        """Scrape comments/replies from a tweet.

        Args:
            content_url: URL of the tweet
            load_all: Whether to scroll to load more comments
            expand_sub_comments: Whether to expand nested replies
            max_scrolls: Maximum scroll attempts (default: 3-5, randomized)

        Returns:
            List of CommentItem objects
        """
        logger.info(f"Scraping comments from: {content_url}")

        page = await self._get_page()
        comments: List[CommentItem] = []
        seen_comment_ids: Set[str] = set()

        try:
            # Navigate to tweet detail page
            await page.goto(content_url, wait_until='domcontentloaded')
            await self._human_delay(2, 4)

            # Wait for tweet to load
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
            except Exception as e:
                logger.error(f"Failed to load tweet: {e}")
                return comments

            # Scroll to load more comments (if requested)
            if load_all:
                # Use provided max_scrolls or random 3-5 (reduced from 8-15)
                scroll_count = max_scrolls if max_scrolls else random.randint(3, 5)
                logger.info(f"Loading comments with {scroll_count} scrolls...")

                prev_article_count = 0
                no_new_count = 0

                for i in range(scroll_count):
                    await self._human_scroll(page)
                    await self._human_delay(1, 3)

                    # Early stop: check if new comments loaded
                    article_count = await page.evaluate("document.querySelectorAll('article[data-testid=\"tweet\"]').length")
                    if article_count == prev_article_count:
                        no_new_count += 1
                        if no_new_count >= 2:  # 2 consecutive scrolls with no new comments
                            logger.info(f"Early stop: no new comments after {i+1} scrolls")
                            break
                    else:
                        no_new_count = 0
                    prev_article_count = article_count

                    # Try to expand "Show more replies" buttons
                    if expand_sub_comments and i % 3 == 0:
                        try:
                            show_more_buttons = await page.query_selector_all('div[role="button"]:has-text("Show")')
                            if show_more_buttons:
                                # Click a random one
                                button = random.choice(show_more_buttons[:3])
                                await button.click()
                                await self._human_delay(1, 2)
                        except:
                            pass

            # Clear previous intercepted videos and wait for new ones
            self._video_urls.clear()
            await asyncio.sleep(1.0)  # Wait for network requests

            # Extract all comments
            comment_data_list = await page.evaluate("""
                () => {
                    const comments = [];
                    const articles = document.querySelectorAll('article[data-testid="tweet"]');

                    // Skip first article (it's the main tweet)
                    for (let i = 1; i < articles.length; i++) {
                        const article = articles[i];
                        const data = {};

                        try {
                            // Comment text
                            const textEl = article.querySelector('[data-testid="tweetText"]');
                            data.text = textEl ? textEl.textContent : '';

                            // Author info
                            const authorEl = article.querySelector('[data-testid="User-Name"]');
                            if (authorEl) {
                                const nameEl = authorEl.querySelector('span');
                                data.author = nameEl ? nameEl.textContent : '';

                                const usernameEl = authorEl.querySelector('a[href^="/"]');
                                if (usernameEl) {
                                    const href = usernameEl.getAttribute('href');
                                    data.username = href ? href.substring(1) : '';
                                }
                            }

                            // Comment URL
                            const timeEl = article.querySelector('time');
                            if (timeEl) {
                                const linkEl = timeEl.closest('a');
                                if (linkEl) {
                                    data.url = 'https://x.com' + linkEl.getAttribute('href');
                                }
                            }

                            // Timestamp
                            if (timeEl) {
                                data.timestamp = timeEl.getAttribute('datetime');
                                data.timeAgo = timeEl.textContent;
                            }

                            // Engagement metrics
                            const metrics = article.querySelectorAll('[role="group"] button, [role="group"] a');
                            for (const metric of metrics) {
                                const ariaLabel = metric.getAttribute('aria-label') || '';
                                if (ariaLabel.includes('like')) {
                                    data.likes = ariaLabel;
                                } else if (ariaLabel.includes('repl')) {
                                    data.replies = ariaLabel;
                                } else if (ariaLabel.includes('repost') || ariaLabel.includes('retweet')) {
                                    data.retweets = ariaLabel;
                                }
                            }

                            // Images
                            const imageEls = article.querySelectorAll('img[src*="media"]');
                            data.images = [];
                            for (const img of imageEls) {
                                const src = img.src;
                                if (src && !src.includes('profile_images')) {
                                    data.images.push(src);
                                }
                            }

                            // Videos
                            data.videos = [];
                            const videoEls = article.querySelectorAll('video');
                            for (const video of videoEls) {
                                const source = video.querySelector('source');
                                if (source && source.src) {
                                    data.videos.push(source.src);
                                } else if (video.src) {
                                    data.videos.push(video.src);
                                } else if (video.poster && data.videos.length === 0) {
                                    data.videos.push(video.poster);
                                }
                            }

                            // Avatar
                            const avatarEl = article.querySelector('img[src*="profile_images"]');
                            data.avatar = avatarEl ? avatarEl.src : '';

                            if (data.text || data.author) {
                                comments.push(data);
                            }

                        } catch (e) {
                            console.error('Error extracting comment:', e);
                        }
                    }

                    return comments;
                }
            """)

            # Convert to CommentItem objects
            # Extract tweet ID from content_url for platform_content_id
            tweet_id = self._extract_tweet_id(content_url) or content_url.split('/')[-1]

            # Distribute intercepted video URLs across comments that have videos
            comments_with_videos = [c for c in comment_data_list if c.get('videos')]
            video_index = 0

            for data in comment_data_list:
                # Generate comment ID from URL or text hash
                comment_url = data.get('url', '')
                comment_id = comment_url.split('/')[-1] if comment_url else str(hash(data.get('text', '')))

                # Skip duplicates
                if comment_id in seen_comment_ids:
                    continue
                seen_comment_ids.add(comment_id)

                # Parse engagement metrics
                likes = self._parse_engagement(data.get('likes', '0'))
                replies = self._parse_engagement(data.get('replies', '0'))

                # Parse timestamp to milliseconds
                timestamp_str = data.get('timestamp', '')
                create_time = 0
                if timestamp_str:
                    try:
                        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                        create_time = int(dt.timestamp() * 1000)
                    except:
                        create_time = int(datetime.now().timestamp() * 1000)

                # Parse sub_comment_count
                try:
                    sub_count = int(replies) if replies.isdigit() else 0
                except:
                    sub_count = 0

                # Use intercepted video URLs if available
                video_urls = []
                if data.get('videos'):  # Comment has videos
                    if self._video_urls and video_index < len(self._video_urls):
                        # Use intercepted real URL
                        video_urls = [self._video_urls[video_index]]
                        video_index += 1
                        logger.debug(f"Using intercepted video URL for comment {comment_id}")
                    else:
                        # Fallback to DOM-extracted URLs (blob URLs)
                        video_urls = data.get('videos', [])
                        logger.debug(f"No intercepted URL, using blob URL for comment {comment_id}")

                comment = CommentItem(
                    platform="x",
                    platform_comment_id=comment_id,
                    platform_content_id=tweet_id,
                    platform_user_id=data.get('username', ''),
                    content=data.get('text', ''),
                    nickname=data.get('author', ''),
                    avatar=data.get('avatar', ''),
                    likes=likes,
                    create_time=create_time,
                    image_urls=data.get('images', []),
                    video_urls=video_urls,  # Use intercepted or blob URLs
                    sub_comment_count=sub_count,
                    sub_comments=[],  # TODO: Extract nested replies if needed
                )

                comments.append(comment)

            logger.info(f"✓ Scraped {len(comments)} comments")
            return comments

        except Exception as e:
            logger.error(f"Error scraping comments: {e}")
            return comments
        finally:
            try:
                await page.close()
            except Exception:
                pass  # Page or context already closed

    # =========================================================================
    # Helper Methods
    # =========================================================================

    async def verify_login(self) -> bool:
        """Verify if the current cookies are valid and user is logged in.

        Returns:
            True if logged in, False if cookies expired
        """
        page = await self._get_page()
        try:
            await page.goto('https://x.com/home', wait_until='domcontentloaded')
            await asyncio.sleep(3)

            # Check for login indicators
            current_url = page.url

            # If redirected to login page, cookies are expired
            if '/login' in current_url or '/i/flow/login' in current_url:
                logger.error("Cookie expired: redirected to login page")
                return False

            # Check for login button (not logged in)
            login_button = await page.query_selector('[data-testid="loginButton"]')
            if login_button:
                logger.error("Cookie expired: login button visible")
                return False

            # Check for home timeline content (logged in)
            try:
                await page.wait_for_selector('article[data-testid="tweet"]', timeout=10000)
                logger.info("✓ Login verified: cookies are valid")
                return True
            except:
                # No tweets loaded, might be rate limited or cookie issue
                logger.warning("Could not verify login: no tweets loaded")
                return False

        except Exception as e:
            logger.error(f"Login verification failed: {e}")
            return False
        finally:
            try:
                await page.close()
            except:
                pass

    def _is_browser_healthy(self) -> bool:
        """Check if the browser context is still alive."""
        try:
            # Check if context exists and browser is connected
            if not self._context or not self._browser:
                return False
            if not self._browser.is_connected():
                return False
            return True
        except Exception:
            return False

    async def _restart_browser(self):
        """Restart the browser after a crash."""
        logger.warning("Browser crashed, restarting...")

        # Close existing resources (ignore errors)
        try:
            if self._context:
                await self._context.close()
        except Exception:
            pass
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass

        # Restart browser
        self._browser = await self._playwright.chromium.launch(
            headless=self.settings.crawler.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )

        # Recreate context
        self._context = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/Los_Angeles',
        )

        # Set timeouts
        self._context.set_default_timeout(60000)
        self._context.set_default_navigation_timeout(60000)

        # Inject stealth JavaScript
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'mimeTypes', { get: () => [1, 2, 3, 4] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        """)

        # Reload cookies
        try:
            cookies_json = self.settings.x.cookies_json
            if cookies_json:
                cookies = json.loads(cookies_json)
                await self._context.add_cookies(cookies)
                logger.info(f"Reloaded {len(cookies)} X cookies")
        except Exception as e:
            logger.error(f"Failed to reload X cookies: {e}")

        # Re-enable network interception
        self._context.on('response', self._handle_response)
        self._video_urls.clear()
        self._video_urls_seen.clear()

        logger.info("Browser restarted successfully")

    async def _get_page(self) -> Page:
        """Create a new page in the browser context."""
        if not self._context:
            raise RuntimeError("Browser not initialized. Use 'async with XCrawler()' pattern.")

        # Check browser health and restart if needed
        if not self._is_browser_healthy():
            await self._restart_browser()

        # Track page creation
        self._page_count += 1
        self._request_count += 1
        if self._request_start_time is None:
            self._request_start_time = datetime.now()

        return await self._context.new_page()

    def get_stats(self) -> Dict[str, any]:
        """Get request statistics.

        Returns:
            Dict with pages_opened, requests, duration_minutes, pages_per_hour
        """
        duration = 0
        pages_per_hour = 0

        if self._request_start_time:
            duration = (datetime.now() - self._request_start_time).total_seconds() / 60
            if duration > 0:
                pages_per_hour = (self._page_count / duration) * 60

        return {
            'pages_opened': self._page_count,
            'requests': self._request_count,
            'duration_minutes': round(duration, 1),
            'pages_per_hour': round(pages_per_hour, 1),
        }

    def _extract_tweet_id(self, url: str) -> Optional[str]:
        """Extract tweet ID from X URL."""
        parts = url.split('/status/')
        if len(parts) == 2:
            return parts[1].split('?')[0].split('/')[0]
        return None

    def _extract_user_id(self, url: str) -> Optional[str]:
        """Extract username from X URL."""
        parts = url.rstrip('/').split('/')
        if len(parts) >= 4:
            return parts[3]
        return None

    def _handle_response(self, response):
        """Handle network responses to capture video URLs.

        Intercepts responses and extracts real video URLs (not blob URLs).
        Filters for X video patterns:
        - video.twimg.com
        - /amplify_video/
        - .m3u8 (HLS streams)
        - .mp4 (direct video files)

        Uses bounded deque and set for memory efficiency.
        """
        try:
            url = response.url

            # Filter for video URLs
            is_video = (
                'video.twimg.com' in url or
                '/amplify_video/' in url or
                url.endswith('.m3u8') or
                url.endswith('.mp4') or
                ('/ext_tw_video/' in url and response.status == 200)
            )

            if is_video and url not in self._video_urls_seen:
                # O(1) deduplication check
                self._video_urls.append(url)
                self._video_urls_seen.add(url)
                logger.debug(f"🎥 Intercepted video URL: {url[:100]}...")

                # LRU-style cleanup: keep recent 200 when > 500
                if len(self._video_urls_seen) > 500:
                    # Keep only the most recent 200 URLs
                    recent_urls = list(self._video_urls_seen)[-200:]
                    self._video_urls_seen = set(recent_urls)
                    logger.debug(f"LRU cleanup: kept {len(self._video_urls_seen)} recent video URLs")
        except Exception as e:
            # Silently ignore errors in response handler
            pass

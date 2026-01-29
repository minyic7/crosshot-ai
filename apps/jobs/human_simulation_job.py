"""Human simulation job for long-running scraping sessions.

Simulates real user behavior to avoid detection:
- Random delays between actions
- Varies keywords and sort orders
- Random browsing patterns (some contents viewed, some skipped)
- Occasional comment viewing and user profile visits
- Rest periods between search sessions

This job runs the complete content scraping flow:
1. Search -> Get content list
2. For each selected content:
   - Save content (images, videos)
   - Get author info
   - Get comments (with sub-comments)
   - Save all users
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List

from apps.config import get_settings, reload_settings
from apps.crawler.base import ContentItem
from apps.crawler.xhs.scraper import XhsCrawler, SortBy
from apps.services.data_service import DataService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


# Keyword pools for different categories
KEYWORD_POOLS = {
    "fashion": [
        "穿搭", "时尚穿搭", "日常穿搭", "约会穿搭",
        "韩系穿搭", "日系穿搭", "小众穿搭", "显瘦穿搭",
        "氛围感穿搭", "法式穿搭", "复古穿搭", "温柔穿搭",
        "甜美穿搭", "通勤穿搭", "休闲穿搭", "气质穿搭",
    ],
    "sexy": [
        "战袍", "sexy穿搭", "辣妹穿搭", "性感穿搭",
        "夜店穿搭", "约会战袍", "纯欲穿搭", "热辣穿搭",
        "御姐穿搭", "女团穿搭", "露背装", "吊带裙",
    ],
    "beauty": [
        "美女写真", "女生头像", "女生照片", "小姐姐",
        "女神", "甜妹", "清纯", "氛围美女",
        "自拍", "拍照姿势", "拍照技巧", "人像摄影",
    ],
    "body": [
        "身材管理", "好身材", "马甲线", "蜜桃臀",
        "健身女孩", "瑜伽", "普拉提", "舞蹈",
    ],
    "style": [
        "妆容", "日常妆", "约会妆", "氛围感妆容",
        "发型", "卷发", "直发", "编发",
        "美甲", "穿戴甲", "指甲款式",
    ],
    "travel": [
        "melbourne", "澳洲旅行", "墨尔本攻略", "悉尼",
        "旅行vlog", "海外生活", "留学生活",
    ],
    "food": [
        "美食探店", "咖啡店", "网红餐厅", "烘焙",
        "下午茶", "brunch",
    ],
    "lifestyle": [
        "生活分享", "日常vlog", "开箱", "好物分享",
    ],
}


@dataclass
class SimulationStats:
    """Statistics for the simulation job."""
    searches_completed: int = 0
    contents_viewed: int = 0
    contents_saved: int = 0
    users_saved: int = 0
    comments_saved: int = 0
    breaks_taken: int = 0
    total_break_minutes: float = 0.0
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


@dataclass
class SimulationConfig:
    """Configuration for human simulation."""
    # Duration
    duration_minutes: int = 20

    # Keywords
    keyword_categories: List[str] = field(default_factory=lambda: ["travel", "lifestyle"])

    # Behavior probabilities
    prob_view_content: float = 0.8  # 80% chance to view a content from search
    prob_view_comments: float = 1.0  # Always view comments to get stats
    prob_view_author: float = 1.0  # Always view author profile
    prob_expand_sub_comments: float = 0.3  # 30% chance to expand sub-comments

    # Delays (seconds) - target: 2-3 contents per minute
    delay_between_searches: tuple = (10, 20)  # 10-20 seconds between searches
    delay_reading_content: tuple = (3, 8)  # 3-8 seconds reading content
    delay_reading_comments: tuple = (2, 5)  # 2-5 seconds reading comments
    delay_before_action: tuple = (1, 2)  # 1-2 seconds before any action
    delay_scroll: tuple = (0.5, 1)  # 0.5-1 seconds between scrolls

    # Long break settings (for extended runs)
    enable_hourly_breaks: bool = True  # Enable breaks for runs > 30 min
    break_interval_minutes: int = 60  # Take a break every hour
    break_duration: tuple = (300, 600)  # 5-10 minutes break

    # Limits per search session
    max_contents_per_search: int = 30  # At least 30 per keyword
    max_contents_to_view: int = 20  # View more contents
    max_scroll_count: int = 15  # More scrolls to get 30+ contents

    # Comment loading settings
    load_all_comments: bool = True  # Load all comments (not just first page)
    max_comment_load_more: int = 50  # Maximum "load more" clicks for comments

    # Download settings
    download_images: bool = True
    download_videos: bool = True
    download_avatars: bool = True

    # Logging
    verbose: bool = True


def log(message: str, level: str = "info"):
    """Log with timestamp."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[{timestamp}] {message}")
    if level == "info":
        logger.info(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "error":
        logger.error(message)


async def human_delay(delay_range: tuple, action: str = "", verbose: bool = True):
    """Add random delay to simulate human behavior."""
    delay = random.uniform(delay_range[0], delay_range[1])
    if verbose and action:
        log(f"  {action} (waiting {delay:.1f}s)")
    await asyncio.sleep(delay)


async def simulate_view_content(
    crawler: XhsCrawler,
    service: DataService,
    content: ContentItem,
    config: SimulationConfig,
    stats: SimulationStats,
):
    """Simulate viewing and processing a single content."""
    try:
        log(f"\n  📖 Viewing: {content.title[:40]}...")
        stats.contents_viewed += 1

        # Save content with media
        saved_content = await service.save_content(
            content,
            download_media=config.download_images or config.download_videos
        )
        stats.contents_saved += 1
        log(f"    ✓ Saved content (likes: {saved_content.likes_count_display})")

        # Simulate reading time
        await human_delay(config.delay_reading_content, "Reading content...", config.verbose)

        # Maybe view author profile
        user_id = content.platform_data.get("user_id")
        if user_id and random.random() < config.prob_view_author:
            await human_delay(config.delay_before_action, "Checking author...", config.verbose)
            try:
                user_info = await crawler.scrape_user(user_id, load_all_contents=False)
                if user_info.nickname:
                    saved_user = await service.save_user(user_info, download_avatar=config.download_avatars)
                    stats.users_saved += 1
                    log(f"    ✓ Saved author: {saved_user.nickname} (fans: {saved_user.fans_count_display})")
            except Exception as e:
                log(f"    ⚠ Could not get author: {e}", "warning")

        # Maybe view comments
        if content.content_url and random.random() < config.prob_view_comments:
            await human_delay(config.delay_before_action, "Loading comments...", config.verbose)
            try:
                expand_sub = random.random() < config.prob_expand_sub_comments
                # Use return_stats=True to get content stats from detail page
                comments, content_stats = await crawler.scrape_comments(
                    content.content_url,
                    load_all=config.load_all_comments,  # Load all comments
                    expand_sub_comments=expand_sub,
                    max_scroll=config.max_comment_load_more,  # Max 50 load more clicks
                    return_stats=True,  # Get likes, collects, comments count from detail page
                )

                if comments:
                    # Pass content_stats to update Content record with real stats
                    saved_comments = await service.save_comments(
                        platform=content.platform,
                        platform_content_id=content.platform_content_id,
                        comments=comments,
                        download_avatars=config.download_avatars,
                        content_stats=content_stats,  # Update content with real stats
                    )
                    stats.comments_saved += len(saved_comments)

                    # Count unique users
                    unique_users = set()
                    for c in comments:
                        if c.platform_user_id:
                            unique_users.add(c.platform_user_id)
                        for sc in c.sub_comments:
                            if sc.platform_user_id:
                                unique_users.add(sc.platform_user_id)
                    stats.users_saved += len(unique_users)

                    sub_count = sum(len(c.sub_comments) for c in comments)
                    stats_info = ""
                    if content_stats:
                        stats_info = f" | stats: likes={content_stats.likes}, collects={content_stats.collects}"
                    log(f"    ✓ Saved {len(comments)} comments + {sub_count} sub-comments{stats_info}")

                # Simulate reading comments
                await human_delay(config.delay_reading_comments, "Reading comments...", config.verbose)

            except Exception as e:
                log(f"    ⚠ Could not get comments: {e}", "warning")

    except Exception as e:
        log(f"    ✗ Error viewing content: {e}", "error")
        stats.errors.append(f"View content: {e}")


async def simulate_search_session(
    crawler: XhsCrawler,
    service: DataService,
    config: SimulationConfig,
    stats: SimulationStats,
):
    """Simulate a single search session."""
    # Pick random keyword from configured categories
    category = random.choice(config.keyword_categories)
    keyword = random.choice(KEYWORD_POOLS.get(category, ["melbourne"]))

    # Always use GENERAL sort (XHS default algorithm) - no filter panel needed
    sort_by = SortBy.GENERAL

    log(f"\n{'='*60}")
    log(f"🔍 Searching: '{keyword}' (sort: 综合)")
    log(f"{'='*60}")

    try:
        # Search for contents - use more scrolls to get 30+ contents
        contents = await crawler.scrape(
            keyword,
            sort_by=sort_by,
            max_notes=config.max_contents_per_search,
            max_scroll=config.max_scroll_count,
        )

        stats.searches_completed += 1
        log(f"Found {len(contents)} contents")

        if not contents:
            log("No contents found, skipping this search")
            return

        # Randomly select some contents to view (simulates human selection)
        num_to_view = min(
            random.randint(1, config.max_contents_to_view),
            len(contents)
        )
        contents_to_view = random.sample(contents, num_to_view)

        log(f"Will view {num_to_view}/{len(contents)} contents")

        for i, content in enumerate(contents_to_view, 1):
            # Random chance to skip (simulates user losing interest)
            if random.random() > config.prob_view_content:
                log(f"\n  ⏭️ Skipping content {i}/{num_to_view}")
                continue

            await human_delay(config.delay_before_action, f"Selecting content {i}/{num_to_view}...", config.verbose)
            await simulate_view_content(crawler, service, content, config, stats)

    except Exception as e:
        log(f"✗ Search session error: {e}", "error")
        stats.errors.append(f"Search session: {e}")


async def run_human_simulation(config: Optional[SimulationConfig] = None) -> SimulationStats:
    """Run the human simulation job.

    Args:
        config: Simulation configuration (uses defaults if None)

    Returns:
        SimulationStats with results
    """
    if config is None:
        config = SimulationConfig()

    stats = SimulationStats()
    stats.started_at = datetime.now()
    end_time = stats.started_at + timedelta(minutes=config.duration_minutes)

    log("=" * 70)
    log(" HUMAN SIMULATION JOB")
    log("=" * 70)
    log(f"Duration: {config.duration_minutes} minutes")
    log(f"End time: {end_time.strftime('%H:%M:%S')}")
    log(f"Categories: {config.keyword_categories}")
    log(f"View content prob: {config.prob_view_content*100:.0f}%")
    log(f"View comments prob: {config.prob_view_comments*100:.0f}%")
    log(f"View author prob: {config.prob_view_author*100:.0f}%")
    if config.enable_hourly_breaks and config.duration_minutes > 30:
        log(f"Hourly breaks: {config.break_duration[0]//60}-{config.break_duration[1]//60} min every {config.break_interval_minutes} min")
    log("=" * 70)

    # Reload settings to get latest cookies
    reload_settings()
    settings = get_settings()

    if not settings.xhs.get_cookies():
        log("ERROR: No cookies configured!", "error")
        return stats

    service = DataService()

    try:
        async with XhsCrawler() as crawler:
            log("\n🚀 Browser started, beginning simulation...")

            # Initial delay to simulate user just opening the app
            await human_delay((3, 8), "Initial browsing...", config.verbose)

            session_count = 0
            last_break_time = datetime.now()  # Track when we last took a break

            while datetime.now() < end_time:
                session_count += 1
                remaining = (end_time - datetime.now()).total_seconds() / 60

                log(f"\n{'#'*70}")
                log(f"# Session {session_count} | Remaining: {remaining:.1f} min")
                log(f"# Stats: searches={stats.searches_completed}, contents={stats.contents_saved}, "
                    f"users={stats.users_saved}, comments={stats.comments_saved}")
                log(f"{'#'*70}")

                # Run a search session
                await simulate_search_session(crawler, service, config, stats)

                # Check if we should continue
                if datetime.now() >= end_time:
                    break

                # Check if it's time for an hourly break
                if (config.enable_hourly_breaks and
                    config.duration_minutes > 30 and
                    (datetime.now() - last_break_time).total_seconds() >= config.break_interval_minutes * 60):

                    break_duration = random.uniform(config.break_duration[0], config.break_duration[1])
                    break_minutes = break_duration / 60

                    log(f"\n{'🛏️'*20}")
                    log(f"☕ Taking a {break_minutes:.1f} minute break (simulating user away)...")
                    log(f"  Break started at: {datetime.now().strftime('%H:%M:%S')}")
                    log(f"  Will resume at: {(datetime.now() + timedelta(seconds=break_duration)).strftime('%H:%M:%S')}")
                    log(f"{'🛏️'*20}\n")

                    await asyncio.sleep(break_duration)
                    last_break_time = datetime.now()
                    stats.breaks_taken += 1
                    stats.total_break_minutes += break_minutes

                    log(f"\n{'🚀'*20}")
                    log(f"✨ Break finished! Resuming simulation...")
                    log(f"{'🚀'*20}\n")

                    # Check again if we should continue after break
                    if datetime.now() >= end_time:
                        break

                # Rest between sessions (simulates user taking a break)
                await human_delay(
                    config.delay_between_searches,
                    f"Resting before next search...",
                    config.verbose
                )

    except Exception as e:
        log(f"\n💥 Fatal error: {e}", "error")
        stats.errors.append(f"Fatal: {e}")
        import traceback
        traceback.print_exc()

    stats.ended_at = datetime.now()

    # Final summary
    duration = (stats.ended_at - stats.started_at).total_seconds()
    log("\n" + "=" * 70)
    log(" SIMULATION COMPLETE")
    log("=" * 70)
    log(f"Duration: {duration/60:.1f} minutes")
    log(f"Searches completed: {stats.searches_completed}")
    log(f"Contents viewed: {stats.contents_viewed}")
    log(f"Contents saved: {stats.contents_saved}")
    log(f"Users saved: {stats.users_saved}")
    log(f"Comments saved: {stats.comments_saved}")
    if stats.breaks_taken > 0:
        log(f"Breaks taken: {stats.breaks_taken} ({stats.total_break_minutes:.1f} min total)")
    if stats.errors:
        log(f"Errors: {len(stats.errors)}")
        for err in stats.errors[:5]:
            log(f"  - {err}")
    log("=" * 70)

    # Database verification
    log("\n📊 Database verification:")
    session = service.get_session()
    try:
        from apps.database import User, Content, Comment, ContentHistory
        log(f"  Users: {session.query(User).count()}")
        log(f"  Contents: {session.query(Content).count()}")
        log(f"  Comments: {session.query(Comment).count()}")
        log(f"  History: {session.query(ContentHistory).count()}")
    finally:
        session.close()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run human simulation job")
    parser.add_argument("--duration", type=int, default=20, help="Duration in minutes")
    parser.add_argument("--categories", nargs="+", default=["travel", "lifestyle"],
                        help="Keyword categories to use")
    parser.add_argument("--no-images", action="store_true", help="Skip image downloads")
    parser.add_argument("--no-videos", action="store_true", help="Skip video downloads")
    parser.add_argument("--no-avatars", action="store_true", help="Skip avatar downloads")
    parser.add_argument("--quiet", action="store_true", help="Less output")

    args = parser.parse_args()

    config = SimulationConfig(
        duration_minutes=args.duration,
        keyword_categories=args.categories,
        download_images=not args.no_images,
        download_videos=not args.no_videos,
        download_avatars=not args.no_avatars,
        verbose=not args.quiet,
    )

    asyncio.run(run_human_simulation(config))

"""Human simulation job for long-running scraping sessions.

CONTINUOUS PROCESSING VERSION (2025-2026) - Ultra Conservative for 24/7 Operation:
- **Continuous scroll-and-process**: Processes contents as they're found during scrolling
- **Work/Rest Cycle**: 30-40 min work (randomized) + 20-30 min rest (randomized) per hour
- Real-time 24h dedup: Checks DB per content before processing
- Time-aware: Stops immediately when time limit reached
- Dynamic stopping: Stops when yield drops below threshold
- Keyword rotation: 15min cooldown between same keyword
- Cookie expiry detection: Consecutive empty searches trigger warning
- **Ultra-safe delays**: 7-18s scroll + 3-8s pause + 10-20s reading + 30-60s between searches
- Comment loading: Randomized 8-15 clicks (capped to avoid 403)

WORK/REST CYCLE (Simulates Real Human Behavior):
- Work: 30-40 minutes per cycle (randomized each cycle)
- Rest: 20-30 minutes per cycle (randomized each cycle)
- Effective work time: ~50% (12 hours/day active)
- Expected: 300-360 contents/day at ~12-15/hour effective rate

ULTRA CONSERVATIVE DELAYS (All increased for maximum safety):
- Between searches: 30-60s (was 22-45s)
- Reading content: 10-20s (was 7-13s)
- Reading comments: 8-15s (was 5-9s)
- Before action: 3-6s (was 2-4s)
- Scroll: 7-18s (was 5-14s)
- Extra pause: 3-8s (was 2-5s)

Architecture Benefits (流式处理 vs 批处理):
- Better time control: Can stop mid-search when time runs out
- More natural behavior: Scrolls and reads like a real user with long pauses
- Real-time dedup: Checks DB per content, skips recently-scraped items immediately
- Work/rest cycle: Mimics human attention span and breaks

Complete content scraping flow:
1. Work for 30-40 minutes (randomized):
   a. Search with keyword rotation -> Continuous scrolling
   b. For each content found:
      - Check time limit (stop if exceeded)
      - Check DB for 24h dedup (skip if scraped recently)
      - Save content with media (images, videos)
      - Get author profile info
      - Load comments with randomized depth (8-15 clicks)
      - Save all users from comments
   c. Stop when: work time up OR consecutive 3 scrolls yield <3 items
2. Rest for 20-30 minutes (randomized)
3. Repeat cycle indefinitely
"""

import asyncio
import itertools
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict

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


# Keywords are now provided as command-line arguments
# No more hardcoded keyword pools


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
    keywords: List[str] = field(default_factory=list)  # Empty = browse homepage

    # Behavior probabilities
    prob_view_comments: float = 1.0  # Always view comments to get stats
    prob_view_author: float = 1.0  # Always view author profile
    prob_expand_sub_comments: float = 0.3  # 30% chance to expand sub-comments

    # Delays (seconds) - INCREASED for more natural behavior
    delay_between_searches: tuple = (30, 60)  # 30-60s (increased from 22-45)
    delay_reading_content: tuple = (10, 20)  # 10-20 seconds reading content (increased from 7-13)
    delay_reading_comments: tuple = (8, 15)  # 8-15 seconds reading comments (increased from 5-9)
    delay_before_action: tuple = (3, 6)  # 3-6 seconds before action (increased from 2-4)
    delay_scroll: tuple = (7, 18)  # 7-18s (increased from 5-14)
    delay_scroll_extra: tuple = (3, 8)  # Extra pause for natural browsing (increased from 2-5)

    # Long break settings - HOURLY WORK/REST CYCLE
    enable_hourly_breaks: bool = True  # Enable hourly work/rest cycle
    break_interval_minutes: int = 60  # Work duration per cycle (will be randomized 30-40)
    break_duration: tuple = (1200, 1800)  # 20-30 minutes rest (1200s=20min, 1800s=30min)

    # Limits per search session - CONSERVATIVE for long-term safety
    # Target: 500+ contents/day with SAFE parameters
    max_contents_per_search_min: int = 25  # Minimum contents per search
    max_contents_per_search_max: int = 60  # Maximum contents per search
    max_scroll_count: int = 30  # Maximum scroll attempts
    min_new_contents_per_scroll: int = 3  # Dynamic stop: consecutive 3 scrolls add <3 → stop

    # Comment loading settings - CAPPED at 15 per content (403 risk mitigation)
    # XHS comment section is highly sensitive - >15 clicks triggers 403
    load_all_comments: bool = True  # Load all comments (not just first page)
    max_comment_load_more_min: int = 8  # Minimum comment load clicks (conservative)
    max_comment_load_more_max: int = 15  # Maximum 15 clicks (hard cap for safety)
    comment_load_interval: tuple = (8, 15)  # Delay between comment loads

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

                # Randomize comment load attempts (25-50) - simulates normal user behavior
                max_comment_loads = random.randint(
                    config.max_comment_load_more_min,
                    config.max_comment_load_more_max
                )

                # Use return_stats=True to get content stats from detail page
                comments, content_stats = await crawler.scrape_comments(
                    content.content_url,
                    load_all=config.load_all_comments,  # Load all comments
                    expand_sub_comments=expand_sub,
                    max_scroll=max_comment_loads,  # Random 25-50 clicks
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
                else:
                    log(f"    ⚠ No comments found for this content", "warning")

                # Simulate reading comments
                await human_delay(config.delay_reading_comments, "Reading comments...", config.verbose)

            except Exception as e:
                log(f"    ⚠ Could not get comments: {e}", "warning")

    except Exception as e:
        log(f"    ✗ Error viewing content: {e}", "error")
        stats.errors.append(f"View content: {e}")


async def simulate_browse_homepage_session(
    crawler: XhsCrawler,
    service: DataService,
    config: SimulationConfig,
    stats: SimulationStats,
    end_time: datetime,
):
    """Simulate browsing homepage/explore feed (no search) with time limit.

    Args:
        crawler: XHS crawler instance
        service: Data service instance
        config: Simulation configuration
        stats: Statistics tracker
        end_time: When to stop the simulation
    """
    log(f"\n{'='*60}")
    log(f"📱 Browsing homepage feed (no search)")
    log(f"{'='*60}")

    try:
        # Get recent content URLs for deduplication (24 hour window)
        recent_urls = service.get_content_urls_with_timestamps("xhs", hours=24)

        # Randomize target content count for this browsing session (anti-detection)
        target_contents = random.randint(
            config.max_contents_per_search_min,
            config.max_contents_per_search_max
        )
        log(f"Target: {target_contents} contents (randomized)")

        # Browse homepage/explore with dynamic stopping
        contents = await crawler.scrape_homepage(
            max_notes=target_contents,
            max_scroll=config.max_scroll_count,
            recent_content_urls=recent_urls,
            min_new_per_scroll=config.min_new_contents_per_scroll,
        )

        log(f"Found {len(contents)} contents from feed")

        if not contents:
            log("No contents found in feed, skipping")
            return

        # View contents sequentially with time checking
        log(f"Will view contents (time permitting)")

        for i, content in enumerate(contents, 1):
            # Check time before processing each content
            if datetime.now() >= end_time:
                log(f"⏰ Time limit reached, stopping homepage browsing (processed {i-1}/{len(contents)} contents)")
                break

            await human_delay(config.delay_before_action, f"Selecting content {i}/{len(contents)}...", config.verbose)
            await simulate_view_content(crawler, service, content, config, stats)

            # Check time again after processing
            if datetime.now() >= end_time:
                log(f"⏰ Time limit reached after processing content {i}")
                break

    except Exception as e:
        log(f"✗ Homepage browsing error: {e}", "error")
        stats.errors.append(f"Homepage browsing: {e}")


async def simulate_search_session(
    crawler: XhsCrawler,
    service: DataService,
    config: SimulationConfig,
    stats: SimulationStats,
    keyword: str,
    end_time: datetime,
) -> int:
    """Simulate a single search session with a specific keyword using continuous processing.

    This version processes contents as they are discovered during scrolling, rather than
    collecting all contents first. This provides better time control and more natural behavior.

    Args:
        crawler: XHS crawler instance
        service: Data service instance
        config: Simulation configuration
        stats: Statistics tracker
        keyword: Search keyword
        end_time: When to stop the simulation

    Returns:
        Number of contents found (0 if none, for cookie expiry detection)
    """
    # Always use GENERAL sort (XHS default algorithm)
    sort_by = SortBy.GENERAL

    log(f"\n{'='*60}")
    log(f"🔍 Searching: '{keyword}' (sort: 综合)")
    log(f"{'='*60}")

    try:
        # Get recent content URLs for deduplication (24 hour window)
        recent_urls = service.get_content_urls_with_timestamps("xhs", hours=24)

        stats.searches_completed += 1
        contents_found = 0

        # Use continuous scraping - process each content as it's found
        async for content in crawler.scrape_continuous(
            keyword,
            sort_by=sort_by,
            max_scroll=config.max_scroll_count,
            recent_content_urls=recent_urls,
            min_new_per_scroll=config.min_new_contents_per_scroll,
        ):
            contents_found += 1

            # Check if we have time to process this content
            if datetime.now() >= end_time:
                log(f"⏰ Time limit reached, stopping search (found {contents_found} contents)")
                break

            # Real-time 24h dedup check - query DB for this specific content
            existing_content = service.get_content_by_url(content.content_url, hours=24)
            if existing_content:
                last_scraped = existing_content.scraped_at
                hours_ago = (datetime.utcnow() - last_scraped).total_seconds() / 3600
                log(f"  ⏭️  Skipping (scraped {hours_ago:.1f}h ago): {content.title[:40]}")
                continue

            # Process content immediately
            await human_delay(config.delay_before_action, f"Selecting content {contents_found}...", config.verbose)
            await simulate_view_content(crawler, service, content, config, stats)

            # Check time again after processing
            if datetime.now() >= end_time:
                log(f"⏰ Time limit reached after processing content {contents_found}")
                break

        log(f"Found {contents_found} contents total")

        if contents_found == 0:
            log("No contents found, skipping this search")

        return contents_found  # Return number found for cookie expiry detection

    except Exception as e:
        log(f"✗ Search session error: {e}", "error")
        stats.errors.append(f"Search session: {e}")
        return 0  # Return 0 on error


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
    if config.keywords:
        log(f"Keywords: {config.keywords}")
    else:
        log("Mode: Browse homepage feed (no search)")
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

            # Randomize work period: 30-40 minutes per cycle
            current_work_duration_minutes = random.randint(30, 40)
            log(f"Work cycle: {current_work_duration_minutes} minutes, then rest {config.break_duration[0]//60}-{config.break_duration[1]//60} minutes")

            # Keyword rotation to avoid searching same keyword repeatedly
            keywords_cycle = itertools.cycle(config.keywords) if config.keywords else None
            last_searched: Dict[str, datetime] = {}  # Track when each keyword was last searched
            consecutive_empty_searches = 0  # Track consecutive empty results (cookie expiry detection)

            while datetime.now() < end_time:
                session_count += 1
                remaining = (end_time - datetime.now()).total_seconds() / 60

                log(f"\n{'#'*70}")
                log(f"# Session {session_count} | Remaining: {remaining:.1f} min")
                log(f"# Stats: searches={stats.searches_completed}, contents={stats.contents_saved}, "
                    f"users={stats.users_saved}, comments={stats.comments_saved}")
                log(f"{'#'*70}")

                # Run either search or homepage browsing session
                if config.keywords:
                    # Rotate keywords to avoid short-term repetition
                    keyword = next(keywords_cycle)

                    # Check if this keyword was searched recently (within 15 min)
                    min_interval_minutes = 15
                    if keyword in last_searched:
                        time_since_last = (datetime.now() - last_searched[keyword]).total_seconds() / 60
                        if time_since_last < min_interval_minutes:
                            log(f"⏭️  Skipping '{keyword}' (searched {time_since_last:.1f}min ago, min interval: {min_interval_minutes}min)")
                            # Try next keyword
                            keyword = next(keywords_cycle)

                    last_searched[keyword] = datetime.now()
                    num_contents = await simulate_search_session(crawler, service, config, stats, keyword, end_time)

                    # Cookie expiry detection: track consecutive empty searches
                    if num_contents == 0:
                        consecutive_empty_searches += 1
                        if consecutive_empty_searches >= 3:
                            log(f"⚠️  WARNING: {consecutive_empty_searches} consecutive empty searches - cookies may be expired!", "warning")
                    else:
                        consecutive_empty_searches = 0  # Reset on success

                else:
                    # Browse homepage feed (no search)
                    await simulate_browse_homepage_session(crawler, service, config, stats, end_time)

                # Check if we should continue
                if datetime.now() >= end_time:
                    break

                # Check if it's time for hourly work/rest cycle
                if config.enable_hourly_breaks:
                    time_since_last_break = (datetime.now() - last_break_time).total_seconds() / 60

                    if time_since_last_break >= current_work_duration_minutes:
                        break_duration = random.uniform(config.break_duration[0], config.break_duration[1])
                        break_minutes = break_duration / 60

                        log(f"\n{'🛏️'*20}")
                        log(f"☕ Work cycle complete! Worked for {current_work_duration_minutes} minutes")
                        log(f"   Taking a {break_minutes:.1f} minute break (simulating user away)...")
                        log(f"   Break started at: {datetime.now().strftime('%H:%M:%S')}")
                        log(f"   Will resume at: {(datetime.now() + timedelta(seconds=break_duration)).strftime('%H:%M:%S')}")
                        log(f"{'🛏️'*20}\n")

                        await asyncio.sleep(break_duration)
                        last_break_time = datetime.now()
                        stats.breaks_taken += 1
                        stats.total_break_minutes += break_minutes

                        # Randomize next work period: 30-40 minutes
                        current_work_duration_minutes = random.randint(30, 40)

                        log(f"\n{'🚀'*20}")
                        log(f"✨ Break finished! Resuming simulation...")
                        log(f"   Next work cycle: {current_work_duration_minutes} minutes")
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
    parser.add_argument("--keywords", type=str, default="",
                        help="Comma-separated keywords to search (empty = browse homepage)")
    parser.add_argument("--no-images", action="store_true", help="Skip image downloads")
    parser.add_argument("--no-videos", action="store_true", help="Skip video downloads")
    parser.add_argument("--no-avatars", action="store_true", help="Skip avatar downloads")
    parser.add_argument("--quiet", action="store_true", help="Less output")

    args = parser.parse_args()

    # Parse keywords from comma-separated string
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()] if args.keywords else []

    config = SimulationConfig(
        duration_minutes=args.duration,
        keywords=keywords,
        download_images=not args.no_images,
        download_videos=not args.no_videos,
        download_avatars=not args.no_avatars,
        verbose=not args.quiet,
    )

    asyncio.run(run_human_simulation(config))

"""Human simulation job for X (Twitter) - 24/7 production scraping.

LEVEL 1 COMPLETE IMPLEMENTATION:
- Home timeline browsing (For You feed)
- Complete data collection: content + author + comments + comment authors
- Work/Rest cycle: 40-50 min work + 10-20 min rest
- Conservative delays for complete workflow
- Expected: 30-50 tweets/hour fully processed, ~500-800 tweets/day

COMPLETE WORKFLOW PER TWEET:
1. Save tweet content with media (images)
2. Get and save author profile (name, bio, followers, avatar)
3. Get and save comments/replies (8-15 scrolls to load)
4. Get and save comment authors (up to 10 per tweet)
5. Download all media (images, avatars)

WORK/REST CYCLE (Lighter than XHS):
- Work: 40-50 minutes per cycle (randomized)
- Rest: 10-20 minutes per cycle (randomized)
- Effective work time: ~75% (18 hours/day active)
- X is less strict than XHS, but Level 1 is comprehensive

DELAYS (Optimized for Level 1):
- Scroll: 1-4s (X is relaxed)
- Between tweets: 3-6s (process each fully)
- Before author profile: 1-2s
- Before comments: 2-4s
- Between comment authors: 1-2s
- Session duration: Continuous until work cycle ends

SESSION STRATEGY (Level 1):
- 10-20 tweets per session (reduced from Level 0's 100-200)
- 5-10 scrolls to collect tweets (reduced from 15-25)
- Complete processing: ~2-3 min per tweet
- ~5-10 tweets processed per 30 min session

Complete flow:
1. Work for 40-50 minutes (randomized):
   a. Run home timeline scraping sessions
   b. Each session: scrape 10-20 tweets with scrolling
   c. For each tweet: complete Level 1 workflow
   d. 5-10s delay between sessions
2. Rest for 10-20 minutes (randomized)
3. Repeat cycle indefinitely
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from apps.config import get_settings
from apps.crawler.base import ContentItem
from apps.crawler.x.scraper import XCrawler, SortBy
from apps.services.data_service import DataService


# ============================================================================
# Logging Setup
# ============================================================================

class ShanghaiFormatter(logging.Formatter):
    """Formats log timestamps in Asia/Shanghai timezone."""

    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        shanghai_time = dt + timedelta(hours=8)
        if datefmt:
            return shanghai_time.strftime(datefmt)
        return shanghai_time.strftime('%Y-%m-%d %H:%M:%S')


handler = logging.StreamHandler()
handler.setFormatter(ShanghaiFormatter(
    fmt='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
))

logging.basicConfig(
    level=logging.INFO,
    handlers=[handler]
)
logger = logging.getLogger(__name__)


def log(msg: str, level: str = "info"):
    """Helper for clean logging."""
    if level == "error":
        logger.error(msg)
    else:
        logger.info(msg)


# ============================================================================
# Statistics and Configuration
# ============================================================================

@dataclass
class SimulationStats:
    """Statistics for the simulation job."""
    sessions_completed: int = 0
    tweets_saved: int = 0
    work_cycles: int = 0
    rest_cycles: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class SimulationConfig:
    """Configuration for X human simulation."""
    duration_minutes: int = 10080  # 7 days default

    # Keyword search (optional - if None, uses home timeline)
    keyword: Optional[str] = None

    # Work/Rest cycles (lighter than XHS since X is more relaxed)
    work_min_minutes: int = 40
    work_max_minutes: int = 50
    rest_min_minutes: int = 10
    rest_max_minutes: int = 20

    # Session config
    session_min_minutes: int = 10
    session_max_minutes: int = 20
    tweets_per_session_min: int = 100
    tweets_per_session_max: int = 200

    # Delays (much faster than XHS)
    between_sessions_min: int = 5
    between_sessions_max: int = 10

    # Media download
    download_images: bool = True
    download_videos: bool = False  # TODO: implement video download
    download_avatars: bool = True

    # Simplified mode options (reduce page requests to improve stability)
    skip_author_profile: bool = True  # Skip fetching author profile pages
    skip_comments: bool = False  # Skip fetching comments
    skip_comment_authors: bool = True  # Skip fetching comment author profiles
    max_comment_authors: int = 3  # Max comment authors to fetch (if not skipped)
    max_comment_scrolls: int = 3  # Reduced from 8-15

    verbose: bool = True


# ============================================================================
# Helper Functions
# ============================================================================

async def human_delay(min_sec: float, max_sec: float):
    """Random delay to simulate human behavior."""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


# ============================================================================
# Session Processing
# ============================================================================

async def process_single_tweet(
    crawler: XCrawler,
    service: DataService,
    tweet: ContentItem,
    config: SimulationConfig,
    stats: SimulationStats,
) -> bool:
    """Process a single tweet with configurable workflow.

    Workflow (configurable via SimulationConfig):
    1. Save tweet with media (always)
    2. Get and save author profile (skip_author_profile=False)
    3. Get and save comments (skip_comments=False)
    4. Get and save comment authors (skip_comment_authors=False)

    Returns:
        True if successfully processed, False otherwise
    """
    try:
        # 1. Save tweet content (always)
        saved_content = await service.save_content(
            content_item=tweet,
            download_media=config.download_images,
            source="keyword_search" if config.keyword else "home_timeline"
        )

        # 2. Get and save author profile (optional)
        if not config.skip_author_profile:
            try:
                username = tweet.platform_data.get('username', '').replace('@', '')
                if username:
                    await human_delay(1, 2)
                    user_info = await crawler.scrape_user(username)
                    await service.save_user(
                        user_info=user_info,
                        download_avatar=config.download_avatars
                    )
            except Exception as e:
                log(f"         ⚠️  Error saving author: {e}", "error")
                stats.errors.append(f"Author: {e}")

        # 3. Get and save comments (optional)
        if not config.skip_comments:
            try:
                await human_delay(2, 4)
                comments = await crawler.scrape_comments(
                    tweet.content_url,
                    load_all=True,
                    expand_sub_comments=False,  # Simpler, fewer requests
                    max_scrolls=config.max_comment_scrolls
                )

                if comments:
                    # Save comments
                    await service.save_comments(
                        platform="x",
                        platform_content_id=tweet.platform_content_id,
                        comments=comments,
                        download_avatars=config.download_avatars,
                        download_images=config.download_images
                    )

                    # 4. Save comment authors (optional, limited)
                    if not config.skip_comment_authors:
                        comment_users = set()
                        for comment in comments:
                            if comment.platform_user_id:
                                comment_users.add(comment.platform_user_id)

                        # Limit comment authors
                        sampled_users = list(comment_users)[:config.max_comment_authors]
                        for username in sampled_users:
                            try:
                                await human_delay(1, 2)
                                user_info = await crawler.scrape_user(username)
                                await service.save_user(
                                    user_info=user_info,
                                    download_avatar=config.download_avatars
                                )
                            except Exception as e:
                                log(f"         ⚠️  Error saving comment author @{username}: {e}", "error")
                                stats.errors.append(f"Comment author: {e}")

            except Exception as e:
                log(f"         ⚠️  Error processing comments: {e}", "error")
                stats.errors.append(f"Comments: {e}")

        return True

    except Exception as e:
        log(f"         ❌ Error processing tweet: {e}", "error")
        stats.errors.append(f"Tweet: {e}")
        return False


async def run_scraping_session(
    crawler: XCrawler,
    service: DataService,
    config: SimulationConfig,
    stats: SimulationStats,
    session_num: int = 0,
) -> int:
    """Run a single scraping session on home timeline or keyword search.

    Level 1 implementation:
    - Scrape timeline tweets OR keyword search (if keyword is set)
    - For each tweet: save content + author + comments + comment authors

    Returns:
        Number of tweets successfully processed
    """
    # Randomize tweets target for this session (fewer tweets for Level 1)
    max_tweets = random.randint(10, 20)  # Reduced from 100-200 for Level 1
    max_scrolls = random.randint(5, 10)  # Reduced scrolls

    # Determine scraping mode
    if config.keyword:
        # Keyword search mode - use TOP only (more stable, less crashes)
        sort_by = SortBy.TOP
        log(f"   Starting search session (keyword: '{config.keyword}', sort: {sort_by.value}, target: {max_tweets})")
    else:
        # Home timeline mode
        log(f"   Starting Level 1 session (target: {max_tweets} tweets, max scrolls: {max_scrolls})")

    try:
        # Scrape based on mode
        if config.keyword:
            # Keyword search
            tweets: List[ContentItem] = await crawler.scrape(
                keyword=config.keyword,
                sort_by=sort_by,
                max_notes=max_tweets,
                max_scroll=max_scrolls
            )
        else:
            # Home timeline
            tweets: List[ContentItem] = await crawler.scrape_home_timeline(
                max_tweets=max_tweets,
                max_scroll=max_scrolls
            )

        if not tweets:
            log("   ⚠️  No tweets collected - might be cookie issue", "error")
            return 0

        log(f"   Collected {len(tweets)} tweets, processing with Level 1 workflow...")

        # Process each tweet with complete workflow
        processed_count = 0
        for i, tweet in enumerate(tweets, 1):
            author = tweet.platform_data.get('author', 'Unknown')
            log(f"      [{i}/{len(tweets)}] Processing: {author} - {tweet.title[:40]}...")

            success = await process_single_tweet(
                crawler, service, tweet, config, stats
            )

            if success:
                processed_count += 1

            # Delay between tweets (Level 1 is slower)
            if i < len(tweets):
                await human_delay(3, 6)

        log(f"   ✓ Session complete: {processed_count}/{len(tweets)} tweets fully processed")
        return processed_count

    except Exception as e:
        log(f"   Session error: {e}", "error")
        stats.errors.append(f"Session: {e}")
        return 0


async def work_cycle(
    crawler: XCrawler,
    service: DataService,
    config: SimulationConfig,
    stats: SimulationStats,
    end_time: datetime,
) -> int:
    """Run a work cycle with multiple scraping sessions.

    Returns:
        Number of tweets saved during this work cycle
    """
    # Randomize work duration
    work_duration = random.randint(
        config.work_min_minutes,
        config.work_max_minutes
    )
    work_end = datetime.now() + timedelta(minutes=work_duration)

    # Don't exceed overall end time
    if work_end > end_time:
        work_end = end_time
        work_duration = int((work_end - datetime.now()).total_seconds() / 60)

    log(f"\n{'='*70}")
    log(f"💼 WORK CYCLE {stats.work_cycles + 1} - Duration: {work_duration} min")
    if config.keyword:
        log(f"   Mode: Keyword search ('{config.keyword}')")
    else:
        log(f"   Mode: Home timeline")
    log(f"   End time: {work_end.strftime('%H:%M:%S')}")
    log(f"{'='*70}")

    total_saved = 0
    session_count = 0

    while datetime.now() < work_end:
        session_count += 1
        log(f"\n📊 Session {session_count}")

        saved = await run_scraping_session(crawler, service, config, stats, stats.sessions_completed)
        total_saved += saved
        stats.sessions_completed += 1

        # Check if we should continue
        time_left = (work_end - datetime.now()).total_seconds()
        if time_left < 60:  # Less than 1 minute left
            log(f"   Work cycle ending (time left: {time_left:.0f}s)")
            break

        # Delay before next session (unless it's the last one)
        if datetime.now() < work_end:
            delay = random.randint(
                config.between_sessions_min,
                config.between_sessions_max
            )
            log(f"   💤 Resting {delay}s before next session...")
            await asyncio.sleep(delay)

    stats.work_cycles += 1
    log(f"\n✓ Work cycle complete: {total_saved} tweets saved in {session_count} sessions")
    return total_saved


async def rest_cycle(
    config: SimulationConfig,
    stats: SimulationStats,
    end_time: datetime,
) -> bool:
    """Take a rest break between work cycles.

    Returns:
        True if rest completed, False if end_time was reached
    """
    # Randomize rest duration
    rest_duration = random.randint(
        config.rest_min_minutes,
        config.rest_max_minutes
    )
    rest_end = datetime.now() + timedelta(minutes=rest_duration)

    # Don't exceed overall end time
    if rest_end > end_time:
        return False  # No time for rest

    log(f"\n{'='*70}")
    log(f"😴 REST CYCLE {stats.rest_cycles + 1} - Duration: {rest_duration} min")
    log(f"   Resume at: {rest_end.strftime('%H:%M:%S')}")
    log(f"{'='*70}")

    await asyncio.sleep(rest_duration * 60)

    stats.rest_cycles += 1
    log(f"\n⏰ Rest complete, resuming work...")
    return True


# ============================================================================
# Main Simulation Loop
# ============================================================================

async def run_human_simulation(config: Optional[SimulationConfig] = None) -> SimulationStats:
    """Run the X human simulation job with work/rest cycles.

    This implements a complete 24/7 production scraping strategy:
    - Work for 40-50 minutes (randomized)
    - Multiple sessions per work cycle
    - Rest for 10-20 minutes between cycles
    - Repeat until duration expires
    """
    if config is None:
        config = SimulationConfig()

    stats = SimulationStats()
    stats.started_at = datetime.now()
    end_time = datetime.now() + timedelta(minutes=config.duration_minutes)

    log("=" * 70)
    log("X (TWITTER) HUMAN SIMULATION JOB - 24/7 Production")
    log("=" * 70)
    if config.keyword:
        log(f"Strategy: Keyword search ('{config.keyword}') with work/rest cycles")
    else:
        log(f"Strategy: Home timeline (For You feed) with work/rest cycles")
    log(f"Duration: {config.duration_minutes} minutes ({config.duration_minutes/60:.1f} hours)")
    log(f"Work cycles: {config.work_min_minutes}-{config.work_max_minutes} min")
    log(f"Rest cycles: {config.rest_min_minutes}-{config.rest_max_minutes} min")
    log(f"Sessions: {config.session_min_minutes}-{config.session_max_minutes} min each")
    log(f"Tweets per session: {config.tweets_per_session_min}-{config.tweets_per_session_max}")
    log(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # Use async context manager for efficient resource management
    async with DataService() as service:
        try:
            async with XCrawler() as crawler:
                log("\n🚀 Browser started, beginning simulation...")

                # Main work/rest cycle loop
                while datetime.now() < end_time:
                    # Work cycle
                    saved = await work_cycle(crawler, service, config, stats, end_time)
                    stats.tweets_saved += saved

                    # Check if we have time for rest
                    time_left_minutes = (end_time - datetime.now()).total_seconds() / 60
                    if time_left_minutes < config.rest_min_minutes:
                        log(f"\n⏱️  Less than {config.rest_min_minutes} min left, ending job...")
                        break

                    # Rest cycle
                    rested = await rest_cycle(config, stats, end_time)
                    if not rested:
                        log("\n⏱️  No time for rest cycle, ending job...")
                        break

                    # Check if we should continue
                    if datetime.now() >= end_time:
                        log("\n⏱️  Time limit reached, ending job...")
                        break

        except KeyboardInterrupt:
            log("\n⚠️  Job interrupted by user")
        except Exception as e:
            log(f"\n❌ Job error: {e}", "error")
            stats.errors.append(f"Fatal: {e}")
            raise

    stats.completed_at = datetime.now()

    # Print summary
    log("\n" + "=" * 70)
    log("JOB SUMMARY")
    log("=" * 70)
    duration = (stats.completed_at - stats.started_at).total_seconds()
    log(f"Duration: {duration/60:.1f} minutes ({duration/3600:.1f} hours)")
    log(f"Work cycles: {stats.work_cycles}")
    log(f"Rest cycles: {stats.rest_cycles}")
    log(f"Sessions: {stats.sessions_completed}")
    log(f"Tweets saved: {stats.tweets_saved}")
    if stats.sessions_completed > 0:
        log(f"Average per session: {stats.tweets_saved/stats.sessions_completed:.1f}")
    if duration > 0:
        log(f"Rate: {stats.tweets_saved/(duration/3600):.1f} tweets/hour")
    log(f"Errors: {len(stats.errors)}")
    log("=" * 70)

    return stats


# ============================================================================
# CLI Entry Point
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run X human simulation job")
    parser.add_argument("--keyword", type=str, default=None,
                       help="Search keyword (if not provided, uses home timeline)")
    parser.add_argument("--duration", type=int, default=10080,
                       help="Duration in minutes (default: 7 days = 10080)")
    parser.add_argument("--work-min", type=int, default=40,
                       help="Minimum work cycle duration in minutes (default: 40)")
    parser.add_argument("--work-max", type=int, default=50,
                       help="Maximum work cycle duration in minutes (default: 50)")
    parser.add_argument("--rest-min", type=int, default=10,
                       help="Minimum rest cycle duration in minutes (default: 10)")
    parser.add_argument("--rest-max", type=int, default=20,
                       help="Maximum rest cycle duration in minutes (default: 20)")
    parser.add_argument("--no-images", action="store_true",
                       help="Skip image downloads")
    parser.add_argument("--no-avatars", action="store_true",
                       help="Skip avatar downloads")
    parser.add_argument("--quiet", action="store_true",
                       help="Less verbose output")

    args = parser.parse_args()

    config = SimulationConfig(
        keyword=args.keyword,
        duration_minutes=args.duration,
        work_min_minutes=args.work_min,
        work_max_minutes=args.work_max,
        rest_min_minutes=args.rest_min,
        rest_max_minutes=args.rest_max,
        download_images=not args.no_images,
        download_avatars=not args.no_avatars,
        verbose=not args.quiet,
    )

    asyncio.run(run_human_simulation(config))

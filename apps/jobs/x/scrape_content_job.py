"""Content scraping job for X (Twitter) - Testing & Development Tool.

PURPOSE:
  Quick testing tool for validating X crawler functionality.
  Use this to test cookies, debug features, and verify data flow.
  For production 24/7 operation, use human_simulation_job.py instead.

CORE FUNCTIONALITY TO TEST:
  1. Search tweets (crawler.scrape)
  2. Save tweet with media (service.save_content)
  3. Get author info (crawler.scrape_user, service.save_user)
  4. Load replies (crawler.scrape_comments, all + threaded)
  5. Save replies and reply authors (service.save_comments)
  6. Download images, videos, avatars
  7. Database persistence (all tables: contents, users, comments, history)

USAGE:
  # Quick test with default settings (1 tweet)
  uv run python -m apps.jobs.x.scrape_content_job

  # Test with specific keyword and multiple tweets
  uv run python -m apps.jobs.x.scrape_content_job --keyword "AI" --max-contents 3

  # Test without downloads (faster)
  uv run python -m apps.jobs.x.scrape_content_job --no-images --no-videos

TODO: Implement when XCrawler is ready.
"""

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from apps.config import get_settings
from apps.crawler.base import ContentItem
from apps.crawler.x.scraper import XCrawler
from apps.services.data_service import DataService
from apps.jobs.common import (
    ShanghaiFormatter,
    JobConfig,
    JobStats,
    human_delay,
)


# Configure logging with Shanghai timezone display
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


async def scrape_single_tweet(
    crawler: XCrawler,
    service: DataService,
    content_item: ContentItem,
    config: JobConfig,
    stats: JobStats,
) -> bool:
    """Scrape a single X tweet completely.

    TODO: Implement when XCrawler is ready.

    Returns:
        True if successful, False otherwise
    """
    # TODO: Implement tweet scraping logic
    # Similar structure to XHS scrape_single_content but adapted for X:
    # - service.save_content() for tweet
    # - crawler.scrape_user() for author
    # - crawler.scrape_comments() for replies
    # - service.save_comments() for persistence
    print(f"TODO: Scrape tweet - {content_item.title[:40]}")
    stats.contents_saved += 1
    return True


async def run_scrape_job(config: Optional[JobConfig] = None) -> JobStats:
    """Run a complete X content scraping job.

    TODO: Implement when XCrawler is ready.

    Returns:
        JobStats with results
    """
    if config is None:
        config = JobConfig()

    stats = JobStats()
    stats.started_at = datetime.now()

    print("=" * 70)
    print(" X (TWITTER) CONTENT SCRAPE JOB - TESTING TOOL")
    print("=" * 70)
    print(f"Keyword: {config.keyword}")
    print(f"Max tweets: {config.max_contents}")
    print("=" * 70)

    service = DataService()

    try:
        async with XCrawler() as crawler:
            # TODO: Implement scraping logic
            # 1. Search for tweets: crawler.scrape(keyword, max_notes=...)
            # 2. For each tweet: scrape_single_tweet()
            # 3. Track statistics
            print("TODO: Implement scraping workflow")
            print("This will follow the same structure as XHS scrape_content_job.py")
            print("but use XCrawler instead of XhsCrawler")

            await asyncio.sleep(2)  # Placeholder

    except Exception as e:
        print(f"\nJob error: {e}")
        stats.errors.append(f"Job: {e}")

    stats.completed_at = datetime.now()

    # Print summary
    print("\n" + "=" * 70)
    print(" JOB SUMMARY")
    print("=" * 70)
    duration = (stats.completed_at - stats.started_at).total_seconds()
    print(f"Duration: {duration:.1f} seconds")
    print(f"Tweets scraped: {stats.contents_scraped}")
    print(f"Tweets saved: {stats.contents_saved}")
    print(f"Errors: {len(stats.errors)}")
    print("=" * 70)

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run X content scrape job")
    parser.add_argument("--keyword", default="AI", help="Search keyword")
    parser.add_argument("--max-contents", type=int, default=1, help="Max tweets to scrape")
    parser.add_argument("--no-comments", action="store_true", help="Skip replies")
    parser.add_argument("--no-sub-comments", action="store_true", help="Skip threaded replies")
    parser.add_argument("--no-images", action="store_true", help="Skip image downloads")
    parser.add_argument("--no-videos", action="store_true", help="Skip video downloads")
    parser.add_argument("--no-avatars", action="store_true", help="Skip avatar downloads")
    parser.add_argument("--quiet", action="store_true", help="Less output")

    args = parser.parse_args()

    config = JobConfig(
        keyword=args.keyword,
        max_contents=args.max_contents,
        load_all_comments=not args.no_comments,
        expand_sub_comments=not args.no_sub_comments,
        download_images=not args.no_images,
        download_videos=not args.no_videos,
        download_avatars=not args.no_avatars,
        verbose=not args.quiet,
    )

    asyncio.run(run_scrape_job(config))

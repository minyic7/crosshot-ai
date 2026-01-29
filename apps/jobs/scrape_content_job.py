"""Complete content scraping job.

This job performs a full scrape of a single content:
1. Search for content by keyword
2. Save content info (title, stats, cover, images, videos)
3. Get author info and save (full user profile)
4. Get all comments (scroll down for more)
5. For each comment:
   - Save comment
   - Save commenter user (basic info from comment)
   - If has sub-comments, expand and save them
   - Save sub-commenter users

Database tables involved:
- contents: The content/post
- users: Author and commenters
- comments: Main comments and sub-comments
- content_history: Version snapshots
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from apps.config import get_settings
from apps.crawler.base import ContentItem
from apps.crawler.xhs.scraper import XhsCrawler
from apps.services.data_service import DataService

logger = logging.getLogger(__name__)


@dataclass
class JobStats:
    """Statistics for a scrape job."""
    contents_scraped: int = 0
    contents_saved: int = 0
    users_scraped: int = 0
    users_saved: int = 0
    comments_scraped: int = 0
    comments_saved: int = 0
    sub_comments_scraped: int = 0
    images_downloaded: int = 0
    videos_downloaded: int = 0
    errors: list = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class JobConfig:
    """Configuration for a scrape job."""
    # Search settings
    keyword: str = "melbourne"
    max_contents: int = 1  # How many contents to fully scrape

    # Comment settings
    load_all_comments: bool = True  # Scroll to load all comments
    expand_sub_comments: bool = True  # Expand sub-comments

    # Download settings
    download_images: bool = True
    download_videos: bool = True
    download_avatars: bool = True

    # Human simulation delays (seconds)
    min_delay: float = 2.0
    max_delay: float = 5.0

    # Logging
    verbose: bool = True


async def human_delay(config: JobConfig, action: str = ""):
    """Add random delay to simulate human behavior."""
    delay = random.uniform(config.min_delay, config.max_delay)
    if config.verbose and action:
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] {action} (wait {delay:.1f}s)")
    await asyncio.sleep(delay)


async def scrape_single_content(
    crawler: XhsCrawler,
    service: DataService,
    content_item: ContentItem,
    config: JobConfig,
    stats: JobStats,
) -> bool:
    """Scrape a single content completely.

    Args:
        crawler: The XHS crawler instance
        service: The data service instance
        content_item: The content to scrape
        config: Job configuration
        stats: Job statistics to update

    Returns:
        True if successful, False otherwise
    """
    try:
        content_id = content_item.platform_content_id
        print(f"\n{'='*60}")
        print(f"Scraping content: {content_item.title[:40]}...")
        print(f"ID: {content_id}")
        print(f"Type: {content_item.content_type}")
        print(f"{'='*60}")

        # Step 1: Save content
        print("\n[1/4] Saving content...")
        saved_content = await service.save_content(
            content_item,
            download_media=config.download_images or config.download_videos
        )
        stats.contents_saved += 1
        print(f"  ✓ Content saved: {saved_content.title[:30]}...")
        print(f"    - Likes: {saved_content.likes_count_display}")
        print(f"    - Cover: {saved_content.cover_path or 'N/A'}")

        # Count downloaded media
        if saved_content.get_image_paths():
            stats.images_downloaded += len(saved_content.get_image_paths())
            print(f"    - Images: {len(saved_content.get_image_paths())}")
        if saved_content.get_video_paths():
            stats.videos_downloaded += len(saved_content.get_video_paths())
            print(f"    - Videos: {len(saved_content.get_video_paths())}")

        await human_delay(config, "Preparing to get author info")

        # Step 2: Get and save author info
        print("\n[2/4] Getting author info...")
        user_id = content_item.platform_data.get("user_id")
        if user_id:
            try:
                user_info = await crawler.scrape_user(user_id, load_all_contents=False)
                stats.users_scraped += 1

                if user_info.nickname:
                    saved_user = await service.save_user(
                        user_info,
                        download_avatar=config.download_avatars
                    )
                    stats.users_saved += 1
                    print(f"  ✓ Author saved: {saved_user.nickname}")
                    print(f"    - Fans: {saved_user.fans_count_display}")
                    print(f"    - Avatar: {saved_user.avatar_path or 'N/A'}")
                else:
                    print(f"  ✗ Could not get author info")
            except Exception as e:
                print(f"  ✗ Error getting author: {e}")
                stats.errors.append(f"Author {user_id}: {e}")
        else:
            print(f"  - No author ID found in content data")

        await human_delay(config, "Preparing to get comments")

        # Step 3: Get and save comments
        print("\n[3/4] Getting comments...")
        if content_item.content_url:
            try:
                comments = await crawler.scrape_comments(
                    content_item.content_url,
                    load_all=config.load_all_comments,
                    expand_sub_comments=config.expand_sub_comments,
                )
                stats.comments_scraped += len(comments)

                # Count sub-comments
                total_sub = sum(len(c.sub_comments) for c in comments)
                stats.sub_comments_scraped += total_sub

                print(f"  Found {len(comments)} comments, {total_sub} sub-comments")

                if comments:
                    saved_comments = await service.save_comments(
                        platform=content_item.platform,
                        platform_content_id=content_item.platform_content_id,
                        comments=comments,
                        download_avatars=config.download_avatars,
                    )
                    stats.comments_saved += len(saved_comments)
                    print(f"  ✓ Saved {len(saved_comments)} comments")

                    # Count unique users from comments
                    unique_users = set()
                    for c in comments:
                        if c.platform_user_id:
                            unique_users.add(c.platform_user_id)
                        for sc in c.sub_comments:
                            if sc.platform_user_id:
                                unique_users.add(sc.platform_user_id)
                    stats.users_saved += len(unique_users)
                    print(f"  ✓ Saved {len(unique_users)} commenter users")

            except Exception as e:
                print(f"  ✗ Error getting comments: {e}")
                stats.errors.append(f"Comments: {e}")
        else:
            print(f"  - No content URL available")

        # Step 4: Summary
        print("\n[4/4] Content scrape complete!")
        return True

    except Exception as e:
        print(f"  ✗ Error scraping content: {e}")
        stats.errors.append(f"Content {content_item.platform_content_id}: {e}")
        return False


async def run_scrape_job(config: Optional[JobConfig] = None) -> JobStats:
    """Run a complete content scraping job.

    Args:
        config: Job configuration (uses defaults if None)

    Returns:
        JobStats with results
    """
    if config is None:
        config = JobConfig()

    stats = JobStats()
    stats.started_at = datetime.now()

    print("=" * 70)
    print(" CONTENT SCRAPE JOB")
    print("=" * 70)
    print(f"Keyword: {config.keyword}")
    print(f"Max contents: {config.max_contents}")
    print(f"Load all comments: {config.load_all_comments}")
    print(f"Expand sub-comments: {config.expand_sub_comments}")
    print("=" * 70)

    settings = get_settings()
    service = DataService()

    try:
        async with XhsCrawler() as crawler:
            # Search for contents
            print(f"\nSearching for '{config.keyword}'...")
            contents = await crawler.scrape(
                config.keyword,
                max_notes=config.max_contents,
                max_scroll=3,
            )
            stats.contents_scraped = len(contents)
            print(f"Found {len(contents)} contents")

            if not contents:
                print("No contents found, exiting")
                return stats

            # Process each content
            for i, content_item in enumerate(contents[:config.max_contents], 1):
                print(f"\n{'#'*70}")
                print(f"# Processing content {i}/{min(len(contents), config.max_contents)}")
                print(f"{'#'*70}")

                success = await scrape_single_content(
                    crawler, service, content_item, config, stats
                )

                if i < config.max_contents:
                    await human_delay(config, "Moving to next content")

    except Exception as e:
        print(f"\nJob error: {e}")
        stats.errors.append(f"Job: {e}")
        import traceback
        traceback.print_exc()

    stats.completed_at = datetime.now()

    # Print final summary
    print("\n" + "=" * 70)
    print(" JOB SUMMARY")
    print("=" * 70)
    duration = (stats.completed_at - stats.started_at).total_seconds()
    print(f"Duration: {duration:.1f} seconds")
    print(f"Contents: scraped={stats.contents_scraped}, saved={stats.contents_saved}")
    print(f"Users: scraped={stats.users_scraped}, saved={stats.users_saved}")
    print(f"Comments: scraped={stats.comments_scraped}, saved={stats.comments_saved}")
    print(f"Sub-comments: {stats.sub_comments_scraped}")
    print(f"Images downloaded: {stats.images_downloaded}")
    print(f"Videos downloaded: {stats.videos_downloaded}")
    if stats.errors:
        print(f"Errors: {len(stats.errors)}")
        for err in stats.errors[:5]:
            print(f"  - {err}")
    print("=" * 70)

    # Verify database
    print("\nDatabase verification:")
    session = service.get_session()
    try:
        from apps.database import User, Content, Comment, ContentHistory
        print(f"  Users: {session.query(User).count()}")
        print(f"  Contents: {session.query(Content).count()}")
        print(f"  Comments: {session.query(Comment).count()}")
        print(f"  History: {session.query(ContentHistory).count()}")
    finally:
        session.close()

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run content scrape job")
    parser.add_argument("--keyword", default="melbourne", help="Search keyword")
    parser.add_argument("--max-contents", type=int, default=1, help="Max contents to scrape")
    parser.add_argument("--no-comments", action="store_true", help="Skip comments")
    parser.add_argument("--no-sub-comments", action="store_true", help="Skip sub-comments")
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

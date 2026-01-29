"""Data service for saving scraped data to database with image downloads.

Cross-platform design:
- All entities use composite keys: platform + platform_*_id
- Dual count fields: *_count_num (int for queries) + *_count_display (str for display)
- Platform-specific data stored in platform_data JSON column
- ContentHistory for version-controlled snapshots
"""

import json
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, Generator, Optional, Set

from sqlalchemy.orm import Session

from apps.config import get_settings
from apps.crawler.base import CommentItem, ContentItem, ContentStats, UserInfo
from apps.crawler.media_downloader import MediaDownloader
from apps.database import (
    Comment,
    Content,
    ContentHistory,
    Database,
    User,
    ScrapeLog,
    parse_count,
)

logger = logging.getLogger(__name__)


class DataService:
    """Service for saving scraped data to database with smart caching.

    Supports context manager for efficient resource usage:

        async with DataService() as service:
            await service.save_content(...)
            await service.save_user(...)
        # aiohttp session automatically closed

    Or standalone usage (less efficient for batch operations):

        service = DataService()
        await service.save_content(...)  # Creates session per download
    """

    def __init__(self, db_path: str = "data/xhs.db"):
        self.settings = get_settings()
        self.db = Database(db_path)
        self.db.init_db()
        self.downloader = MediaDownloader()
        self._downloader_context_entered = False

    async def __aenter__(self):
        """Initialize resources for batch operations."""
        await self.downloader.__aenter__()
        self._downloader_context_entered = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up resources."""
        if self._downloader_context_entered:
            await self.downloader.__aexit__(exc_type, exc_val, exc_tb)
            self._downloader_context_entered = False

    def get_session(self) -> Session:
        return self.db.get_session()

    @contextmanager
    def transaction(self) -> Generator[Session, None, None]:
        """Context manager for database transactions."""
        session = self.db.get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_existing_content_urls(
        self,
        platform: str,
        hours: Optional[int] = None,
    ) -> Set[str]:
        """Get content URLs updated within the specified time window.

        Only returns URLs that were updated within the time window,
        since older URLs don't need to be checked for deduplication.

        Args:
            platform: Platform to filter by
            hours: Time window in hours (default: 24 from config)

        Returns:
            Set of content URLs updated within the window
        """
        if hours is None:
            hours = self.settings.cache.note_ttl_hours

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self.transaction() as session:
            contents = (
                session.query(Content.content_url)
                .filter(Content.platform == platform)
                .filter(Content.updated_at >= cutoff)
                .filter(Content.content_url.isnot(None))
                .all()
            )
            return {c.content_url for c in contents}

    # Backward compatibility alias
    def get_existing_note_urls(self, platform: str, hours: Optional[int] = None) -> Set[str]:
        return self.get_existing_content_urls(platform, hours)

    def get_content_urls_with_timestamps(
        self,
        platform: str,
        hours: Optional[int] = None,
    ) -> Dict[str, datetime]:
        """Get content URLs with their updated_at timestamps within time window.

        This is used for smart deduplication:
        - Contents scraped within the window: skip (same-day dedup)
        - Contents not in result (older or new): will be scraped

        Only queries the time window needed for dedup decisions.
        For 100K contents with 24h window, typically returns ~1-5K rows instead of 100K.

        Args:
            platform: Platform to filter by
            hours: Time window in hours (default: 24 from config)

        Returns:
            Dict mapping content_url to updated_at datetime
        """
        if hours is None:
            hours = self.settings.cache.note_ttl_hours

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self.transaction() as session:
            contents = (
                session.query(Content.content_url, Content.updated_at)
                .filter(Content.platform == platform)
                .filter(Content.updated_at >= cutoff)
                .filter(Content.content_url.isnot(None))
                .all()
            )
            return {c.content_url: c.updated_at for c in contents}

    # Backward compatibility alias
    def get_note_urls_with_timestamps(self, platform: str, hours: Optional[int] = None) -> Dict[str, datetime]:
        return self.get_content_urls_with_timestamps(platform, hours)

    def get_recent_content_ids(
        self,
        platform: str,
        hours: Optional[int] = None,
    ) -> Set[str]:
        """Get content IDs that were updated within the TTL window.

        These contents don't need to be re-scraped unless we want to check for changes.
        """
        if hours is None:
            hours = self.settings.cache.note_ttl_hours

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self.transaction() as session:
            contents = (
                session.query(Content.platform_content_id)
                .filter(Content.platform == platform)
                .filter(Content.updated_at >= cutoff)
                .all()
            )
            return {c.platform_content_id for c in contents}

    # Backward compatibility alias
    def get_recent_note_ids(self, platform: str, hours: Optional[int] = None) -> Set[str]:
        return self.get_recent_content_ids(platform, hours)

    async def save_user(
        self,
        user_info: UserInfo,
        download_avatar: bool = True,
        session: Optional[Session] = None,
    ) -> User:
        """Save user info to database using cross-platform schema.

        Args:
            user_info: User info from scraper (with platform fields)
            download_avatar: Whether to download avatar image
            session: Optional existing session (will create new if not provided)

        Returns:
            The saved/updated User object
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            # Check if user exists using composite key
            user = (
                session.query(User)
                .filter_by(
                    platform=user_info.platform,
                    platform_user_id=user_info.platform_user_id,
                )
                .first()
            )

            # Download avatar if needed
            avatar_path = None
            if download_avatar and user_info.avatar:
                avatar_path, _ = await self.downloader.download_avatar(
                    f"{user_info.platform}_{user_info.platform_user_id}",
                    user_info.avatar,
                )

            if user:
                # Update existing user
                user.nickname = user_info.nickname or user.nickname
                user.avatar_url = user_info.avatar or user.avatar_url
                if avatar_path:
                    user.avatar_path = avatar_path
                user.description = user_info.description or user.description
                user.gender = user_info.gender if user_info.gender else user.gender
                user.ip_location = user_info.ip_location or user.ip_location

                # Update stats with dual fields
                user.follows_count_display = user_info.follows or user.follows_count_display
                user.follows_count_num = parse_count(user.follows_count_display)
                user.fans_count_display = user_info.fans or user.fans_count_display
                user.fans_count_num = parse_count(user.fans_count_display)
                user.interaction_count_display = user_info.interaction or user.interaction_count_display
                user.interaction_count_num = parse_count(user.interaction_count_display)

                # Merge platform_data
                existing_data = user.get_platform_data()
                existing_data.update(user_info.platform_data)
                user.set_platform_data(existing_data)
                # updated_at will auto-update via onupdate
            else:
                # Create new user
                user = User(
                    platform=user_info.platform,
                    platform_user_id=user_info.platform_user_id,
                    nickname=user_info.nickname,
                    avatar_url=user_info.avatar,
                    avatar_path=avatar_path,
                    description=user_info.description,
                    gender=user_info.gender,
                    ip_location=user_info.ip_location,
                    follows_count_display=user_info.follows,
                    follows_count_num=parse_count(user_info.follows),
                    fans_count_display=user_info.fans,
                    fans_count_num=parse_count(user_info.fans),
                    interaction_count_display=user_info.interaction,
                    interaction_count_num=parse_count(user_info.interaction),
                )
                user.set_platform_data(user_info.platform_data)
                session.add(user)

            if own_session:
                session.commit()
                # Refresh to get all attributes before returning
                session.refresh(user)

            return user

        except Exception as e:
            if own_session:
                session.rollback()
            raise e

        finally:
            if own_session:
                session.close()

    async def save_content(
        self,
        content_item: ContentItem,
        download_media: bool = True,
        session: Optional[Session] = None,
        source: str = "search",
    ) -> Content:
        """Save content to database with smart caching and history tracking.

        Args:
            content_item: Content info from scraper (with platform fields)
            download_media: Whether to download cover/images/videos
            session: Optional existing session
            source: Source of the scrape ("search", "user_profile", "direct")

        Returns:
            The saved/updated Content object
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            # Check if content exists using composite key
            content = (
                session.query(Content)
                .filter_by(
                    platform=content_item.platform,
                    platform_content_id=content_item.platform_content_id,
                )
                .first()
            )

            # Download media if needed
            cover_path = None
            image_paths = []
            video_paths = []
            content_id_for_media = f"{content_item.platform}_{content_item.platform_content_id}"

            # Determine image and video URLs
            # Use new fields if available, fall back to media_urls for backward compatibility
            image_urls = content_item.image_urls if content_item.image_urls else content_item.media_urls
            video_urls = content_item.video_urls if content_item.video_urls else []

            if download_media:
                # Download cover
                cover_url = content_item.cover_url or (image_urls[0] if image_urls else None)
                if cover_url:
                    cover_path, _ = await self.downloader.download_cover(
                        content_id_for_media, cover_url
                    )
                # Download images
                if image_urls:
                    image_paths, _ = await self.downloader.download_content_images(
                        content_id_for_media, image_urls
                    )
                # Download videos
                if video_urls:
                    video_paths, _ = await self.downloader.download_content_videos(
                        content_id_for_media, video_urls
                    )

            if content:
                # Check for changes and create history if needed
                has_changes = self._has_content_changes(content, content_item)

                if has_changes or self.settings.cache.always_append_on_change:
                    self._create_content_history(
                        session,
                        platform=content_item.platform,
                        platform_content_id=content_item.platform_content_id,
                        content=content,
                        new_item=content_item,
                        source=source,
                    )

                # Update existing content
                content.title = content_item.title or content.title
                content.content_text = content_item.platform_data.get("content") or content.content_text
                content.content_type = content_item.content_type or content.content_type

                # Update stats with dual fields
                content.likes_count_display = content_item.likes or content.likes_count_display
                content.likes_count_num = parse_count(content.likes_count_display)
                content.collects_count_display = content_item.collects or content.collects_count_display
                content.collects_count_num = parse_count(content.collects_count_display)
                content.comments_count_display = content_item.comments or content.comments_count_display
                content.comments_count_num = parse_count(content.comments_count_display)

                if cover_path:
                    content.cover_path = cover_path
                    content.cover_url = content_item.cover_url or (image_urls[0] if image_urls else content.cover_url)
                # Update images
                if image_paths:
                    content.set_image_paths(image_paths)
                if image_urls:
                    content.set_image_urls(image_urls)
                # Update videos
                if video_paths:
                    content.set_video_paths(video_paths)
                if video_urls:
                    content.set_video_urls(video_urls)
                # Legacy media fields for backward compatibility
                if image_paths:
                    content.set_media_paths(image_paths)
                if image_urls:
                    content.set_media_urls(image_urls)
                content.content_url = content_item.content_url or content.content_url

                # Merge platform_data
                existing_data = content.get_platform_data()
                existing_data.update(content_item.platform_data)
                content.set_platform_data(existing_data)
                # updated_at will auto-update via onupdate
            else:
                # Create new content
                content = Content(
                    platform=content_item.platform,
                    platform_content_id=content_item.platform_content_id,
                    title=content_item.title,
                    content_text=content_item.platform_data.get("content"),
                    content_type=content_item.content_type,
                    likes_count_display=content_item.likes,
                    likes_count_num=parse_count(content_item.likes),
                    collects_count_display=content_item.collects,
                    collects_count_num=parse_count(content_item.collects),
                    comments_count_display=content_item.comments,
                    comments_count_num=parse_count(content_item.comments),
                    cover_url=content_item.cover_url or (image_urls[0] if image_urls else None),
                    cover_path=cover_path,
                    content_url=content_item.content_url,
                )
                # Set images
                content.set_image_urls(image_urls)
                content.set_image_paths(image_paths)
                # Set videos
                content.set_video_urls(video_urls)
                content.set_video_paths(video_paths)
                # Legacy media fields for backward compatibility
                content.set_media_urls(image_urls)
                content.set_media_paths(image_paths)
                content.set_platform_data(content_item.platform_data)
                session.add(content)

                # Create first history entry for new content
                self._create_content_history(
                    session,
                    platform=content_item.platform,
                    platform_content_id=content_item.platform_content_id,
                    content=None,
                    new_item=content_item,
                    source=source,
                    change_type="initial",
                )

            if own_session:
                session.commit()
                session.refresh(content)

            return content

        except Exception as e:
            if own_session:
                session.rollback()
            raise e

        finally:
            if own_session:
                session.close()

    # Backward compatibility alias
    async def save_note(self, note_item: ContentItem, download_images: bool = True,
                        session: Optional[Session] = None, source: str = "search") -> Content:
        return await self.save_content(note_item, download_images, session, source)

    # Alias for backward compatibility with download_images parameter
    async def save_content_with_images(self, content_item: ContentItem, download_images: bool = True,
                                       session: Optional[Session] = None, source: str = "search") -> Content:
        return await self.save_content(content_item, download_images, session, source)

    def _get_next_version(
        self,
        session: Session,
        platform: str,
        platform_content_id: str,
    ) -> int:
        """Get the next version number for a content's history."""
        from sqlalchemy import func

        max_version = (
            session.query(func.max(ContentHistory.version))
            .filter_by(
                platform=platform,
                platform_content_id=platform_content_id,
            )
            .scalar()
        )
        return (max_version or 0) + 1

    def _create_content_history(
        self,
        session: Session,
        platform: str,
        platform_content_id: str,
        content: Optional[Content],
        new_item: ContentItem,
        source: str,
        change_type: Optional[str] = None,
    ):
        """Create a history snapshot for a content.

        Args:
            session: Database session
            platform: Platform identifier
            platform_content_id: Platform-specific content ID
            content: Existing content (None for new contents)
            new_item: New content data from scraper
            source: Source of the scrape
            change_type: Override change type (default: auto-detect)
        """
        # Determine change type if not provided
        if change_type is None:
            if content is None:
                change_type = "initial"
            elif self._has_text_change(content, new_item):
                change_type = "content_change"
            elif self._has_stats_change(content, new_item):
                change_type = "stats_change"
            else:
                change_type = "refresh"

        # Build snapshot data
        snapshot_data = {
            "title": new_item.title,
            "content": new_item.platform_data.get("content"),
            "likes": new_item.likes,
            "collects": new_item.collects,
            "comments": new_item.comments,
            "media_urls": new_item.media_urls,
            "source": source,
        }

        version = self._get_next_version(session, platform, platform_content_id)

        history = ContentHistory(
            platform=platform,
            platform_content_id=platform_content_id,
            version=version,
            change_type=change_type,
        )
        history.set_data(snapshot_data)
        session.add(history)

    def _has_content_changes(self, existing: Content, new: ContentItem) -> bool:
        """Check if content has meaningful changes worth recording."""
        if not self.settings.cache.enable_version_compare:
            return False

        return (
            self._has_text_change(existing, new)
            or self._has_stats_change(existing, new)
        )

    def _has_text_change(self, existing: Content, new: ContentItem) -> bool:
        """Check if content text has changed."""
        return (
            (new.title and existing.title != new.title)
            or (new.media_urls and len(new.media_urls) != len(existing.get_media_urls()))
        )

    def _has_stats_change(self, existing: Content, new: ContentItem) -> bool:
        """Check if content stats have changed."""
        return (
            (new.likes and existing.likes_count_display != new.likes)
            or (new.collects and existing.collects_count_display != new.collects)
            or (new.comments and existing.comments_count_display != new.comments)
        )

    async def batch_save_contents(
        self,
        contents: list[ContentItem],
        source: str = "search",
        download_images: bool = True,
    ) -> tuple[int, int]:
        """Batch save contents with deduplication and history tracking.

        Returns:
            Tuple of (new_count, updated_count)
        """
        new_count = 0
        updated_count = 0

        with self.transaction() as session:
            for content_item in contents:
                try:
                    if not content_item.platform_content_id:
                        continue

                    existing = (
                        session.query(Content)
                        .filter_by(
                            platform=content_item.platform,
                            platform_content_id=content_item.platform_content_id,
                        )
                        .first()
                    )

                    # Download images
                    cover_path = None
                    media_paths = []
                    content_id_for_images = f"{content_item.platform}_{content_item.platform_content_id}"

                    if download_images and content_item.media_urls:
                        cover_url = content_item.cover_url or content_item.media_urls[0]
                        cover_path, _ = await self.downloader.download_cover(
                            content_id_for_images, cover_url
                        )
                        media_paths, _ = await self.downloader.download_note_images(
                            content_id_for_images, content_item.media_urls
                        )

                    if existing:
                        # Check for changes and create history
                        has_changes = self._has_content_changes(existing, content_item)

                        if has_changes:
                            self._create_content_history(
                                session,
                                platform=content_item.platform,
                                platform_content_id=content_item.platform_content_id,
                                content=existing,
                                new_item=content_item,
                                source=source,
                            )

                            # Update content
                            existing.title = content_item.title or existing.title
                            existing.likes_count_display = content_item.likes or existing.likes_count_display
                            existing.likes_count_num = parse_count(existing.likes_count_display)
                            existing.collects_count_display = content_item.collects or existing.collects_count_display
                            existing.collects_count_num = parse_count(existing.collects_count_display)
                            existing.comments_count_display = content_item.comments or existing.comments_count_display
                            existing.comments_count_num = parse_count(existing.comments_count_display)
                            if cover_path:
                                existing.cover_path = cover_path
                            if media_paths:
                                existing.set_media_paths(media_paths)

                            # Merge platform_data
                            existing_data = existing.get_platform_data()
                            existing_data.update(content_item.platform_data)
                            existing.set_platform_data(existing_data)

                            updated_count += 1
                    else:
                        # Create new content
                        content = Content(
                            platform=content_item.platform,
                            platform_content_id=content_item.platform_content_id,
                            title=content_item.title,
                            content_type=content_item.content_type,
                            likes_count_display=content_item.likes,
                            likes_count_num=parse_count(content_item.likes),
                            collects_count_display=content_item.collects,
                            collects_count_num=parse_count(content_item.collects),
                            comments_count_display=content_item.comments,
                            comments_count_num=parse_count(content_item.comments),
                            cover_url=content_item.cover_url or (content_item.media_urls[0] if content_item.media_urls else None),
                            cover_path=cover_path,
                            content_url=content_item.content_url,
                        )
                        content.set_media_urls(content_item.media_urls)
                        content.set_media_paths(media_paths)
                        content.set_platform_data(content_item.platform_data)
                        session.add(content)

                        # Create first history entry
                        self._create_content_history(
                            session,
                            platform=content_item.platform,
                            platform_content_id=content_item.platform_content_id,
                            content=None,
                            new_item=content_item,
                            source=source,
                            change_type="initial",
                        )
                        new_count += 1

                except Exception as e:
                    # Log but continue with other contents
                    logger.warning(f"Failed to save content: {e}")
                    continue

        return new_count, updated_count

    # Backward compatibility alias
    async def batch_save_notes(self, notes: list[ContentItem], source: str = "search",
                               download_images: bool = True) -> tuple[int, int]:
        return await self.batch_save_contents(notes, source, download_images)

    async def save_comments(
        self,
        platform: str,
        platform_content_id: str,
        comments: list[CommentItem],
        download_avatars: bool = True,
        download_images: bool = True,
        session: Optional[Session] = None,
        content_stats: Optional[ContentStats] = None,
    ) -> list[Comment]:
        """Save comments to database using cross-platform schema.

        Args:
            platform: Platform identifier
            platform_content_id: Platform-specific content ID
            comments: List of comments from scraper
            download_avatars: Whether to download user avatars
            download_images: Whether to download comment images
            session: Optional existing session
            content_stats: Optional content stats from detail page to update Content record

        Returns:
            List of saved Comment objects
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            # Update content stats if provided
            if content_stats:
                content = (
                    session.query(Content)
                    .filter_by(
                        platform=platform,
                        platform_content_id=platform_content_id,
                    )
                    .first()
                )
                if content:
                    # Update stats from detail page
                    content.likes_count_display = content_stats.likes
                    content.likes_count_num = parse_count(content_stats.likes)
                    content.collects_count_display = content_stats.collects
                    content.collects_count_num = parse_count(content_stats.collects)
                    content.comments_count_display = content_stats.comments
                    content.comments_count_num = parse_count(content_stats.comments)
                    logger.debug(
                        f"Updated content stats for {platform_content_id}: "
                        f"likes={content_stats.likes}, collects={content_stats.collects}, "
                        f"comments={content_stats.comments}"
                    )

            saved_comments = []

            for comment_item in comments:
                # Ensure user exists (create minimal user record)
                if comment_item.platform_user_id:
                    user = (
                        session.query(User)
                        .filter_by(
                            platform=comment_item.platform,
                            platform_user_id=comment_item.platform_user_id,
                        )
                        .first()
                    )
                    if not user:
                        # Download avatar
                        avatar_path = None
                        if download_avatars and comment_item.avatar:
                            avatar_path, _ = await self.downloader.download_avatar(
                                f"{comment_item.platform}_{comment_item.platform_user_id}",
                                comment_item.avatar,
                            )

                        user = User(
                            platform=comment_item.platform,
                            platform_user_id=comment_item.platform_user_id,
                            nickname=comment_item.nickname,
                            avatar_url=comment_item.avatar,
                            avatar_path=avatar_path,
                            ip_location=comment_item.ip_location,
                        )
                        session.add(user)

                # Save main comment
                comment = (
                    session.query(Comment)
                    .filter_by(
                        platform=comment_item.platform,
                        platform_comment_id=comment_item.platform_comment_id,
                    )
                    .first()
                )
                if not comment:
                    # Download comment images
                    image_paths = []
                    if download_images and comment_item.image_urls:
                        comment_media_id = f"{comment_item.platform}_comment_{comment_item.platform_comment_id}"
                        image_paths, _ = await self.downloader.download_content_images(
                            comment_media_id, comment_item.image_urls
                        )

                    comment = Comment(
                        platform=comment_item.platform,
                        platform_comment_id=comment_item.platform_comment_id,
                        content_platform=platform,
                        platform_content_id=platform_content_id,
                        user_platform=comment_item.platform,
                        platform_user_id=comment_item.platform_user_id,
                        comment_text=comment_item.content,
                        likes_count_display=comment_item.likes,
                        likes_count_num=parse_count(comment_item.likes),
                        ip_location=comment_item.ip_location,
                        sub_comment_count=comment_item.sub_comment_count,
                        create_time=comment_item.create_time,
                    )
                    # Set images
                    if comment_item.image_urls:
                        comment.set_image_urls(comment_item.image_urls)
                    if image_paths:
                        comment.set_image_paths(image_paths)
                    session.add(comment)
                    saved_comments.append(comment)

                # Save sub-comments
                for sub_item in comment_item.sub_comments:
                    # Ensure sub-comment user exists
                    if sub_item.platform_user_id:
                        sub_user = (
                            session.query(User)
                            .filter_by(
                                platform=sub_item.platform,
                                platform_user_id=sub_item.platform_user_id,
                            )
                            .first()
                        )
                        if not sub_user:
                            avatar_path = None
                            if download_avatars and sub_item.avatar:
                                avatar_path, _ = await self.downloader.download_avatar(
                                    f"{sub_item.platform}_{sub_item.platform_user_id}",
                                    sub_item.avatar,
                                )

                            sub_user = User(
                                platform=sub_item.platform,
                                platform_user_id=sub_item.platform_user_id,
                                nickname=sub_item.nickname,
                                avatar_url=sub_item.avatar,
                                avatar_path=avatar_path,
                                ip_location=sub_item.ip_location,
                            )
                            session.add(sub_user)

                    # Save sub-comment
                    sub_comment = (
                        session.query(Comment)
                        .filter_by(
                            platform=sub_item.platform,
                            platform_comment_id=sub_item.platform_comment_id,
                        )
                        .first()
                    )
                    if not sub_comment:
                        # Download sub-comment images
                        sub_image_paths = []
                        if download_images and sub_item.image_urls:
                            sub_comment_media_id = f"{sub_item.platform}_comment_{sub_item.platform_comment_id}"
                            sub_image_paths, _ = await self.downloader.download_content_images(
                                sub_comment_media_id, sub_item.image_urls
                            )

                        sub_comment = Comment(
                            platform=sub_item.platform,
                            platform_comment_id=sub_item.platform_comment_id,
                            content_platform=platform,
                            platform_content_id=platform_content_id,
                            user_platform=sub_item.platform,
                            platform_user_id=sub_item.platform_user_id,
                            parent_platform_comment_id=comment_item.platform_comment_id,
                            comment_text=sub_item.content,
                            likes_count_display=sub_item.likes,
                            likes_count_num=parse_count(sub_item.likes),
                            ip_location=sub_item.ip_location,
                            create_time=sub_item.create_time,
                        )
                        # Set images
                        if sub_item.image_urls:
                            sub_comment.set_image_urls(sub_item.image_urls)
                        if sub_image_paths:
                            sub_comment.set_image_paths(sub_image_paths)
                        session.add(sub_comment)
                        saved_comments.append(sub_comment)

            if own_session:
                session.commit()

            return saved_comments

        except Exception as e:
            if own_session:
                session.rollback()
            raise e

        finally:
            if own_session:
                session.close()

    def log_scrape(
        self,
        task_type: str,
        target_id: str,
        platform: str,
        status: str = "success",
        items_count: int = 0,
        duration_ms: int = 0,
        error_message: Optional[str] = None,
    ):
        """Log a scrape operation."""
        session = self.get_session()
        try:
            log = ScrapeLog(
                task_type=task_type,
                target_id=target_id,
                platform=platform,
                status=status,
                items_count=items_count,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            session.add(log)
            session.commit()
        finally:
            session.close()

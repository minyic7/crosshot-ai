"""Data service for saving scraped data to database with image downloads."""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, date
from typing import Dict, Generator, Optional, Set

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from apps.config import get_settings
from apps.crawler.base import CommentItem, NoteItem, UserInfo
from apps.crawler.image_downloader import ImageDownloader
from apps.database import Comment, Database, Note, NoteSnapshot, User, ScrapeLog, UserNoteSnapshot

logger = logging.getLogger(__name__)


class DataService:
    """Service for saving scraped data to database with smart caching."""

    def __init__(self, db_path: str = "data/xhs.db"):
        self.settings = get_settings()
        self.db = Database(db_path)
        self.db.init_db()
        self.downloader = ImageDownloader()

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

    def get_existing_note_urls(self) -> Set[str]:
        """Get all existing note URLs for deduplication.

        DEPRECATED: Use get_note_urls_with_timestamps() for smart dedup instead.
        """
        with self.transaction() as session:
            notes = session.query(Note.note_url).all()
            return {n.note_url for n in notes if n.note_url}

    def get_note_urls_with_timestamps(self) -> Dict[str, datetime]:
        """Get all note URLs with their updated_at timestamps.

        This is used for smart deduplication:
        - Notes scraped within 24 hours: skip (same-day dedup)
        - Notes scraped before 24 hours: re-scrape for updates

        Returns:
            Dict mapping note_url to updated_at datetime
        """
        with self.transaction() as session:
            notes = session.query(Note.note_url, Note.updated_at).all()
            return {
                n.note_url: n.updated_at
                for n in notes
                if n.note_url and n.updated_at
            }

    def get_recent_note_ids(self, hours: Optional[int] = None) -> Set[str]:
        """Get note IDs that were updated within the TTL window.

        These notes don't need to be re-scraped unless we want to check for changes.
        """
        if hours is None:
            hours = self.settings.cache.note_ttl_hours

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        with self.transaction() as session:
            notes = (
                session.query(Note.note_id)
                .filter(Note.updated_at >= cutoff)
                .all()
            )
            return {n.note_id for n in notes}

    async def save_user(
        self,
        user_info: UserInfo,
        download_avatar: bool = True,
        session: Optional[Session] = None,
    ) -> User:
        """Save user info to database.

        Args:
            user_info: User info from scraper
            download_avatar: Whether to download avatar image
            session: Optional existing session (will create new if not provided)

        Returns:
            The saved/updated User object
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            # Check if user exists
            user = session.query(User).filter_by(user_id=user_info.user_id).first()

            # Download avatar if needed
            avatar_path = None
            if download_avatar and user_info.avatar:
                avatar_path, _ = await self.downloader.download_avatar(
                    user_info.user_id, user_info.avatar
                )

            if user:
                # Update existing user
                user.nickname = user_info.nickname or user.nickname
                user.avatar_url = user_info.avatar or user.avatar_url
                if avatar_path:
                    user.avatar_path = avatar_path
                user.description = user_info.desc or user.description
                user.gender = user_info.gender if user_info.gender else user.gender
                user.ip_location = user_info.ip_location or user.ip_location
                user.red_id = user_info.red_id or user.red_id
                user.follows_count = user_info.follows or user.follows_count
                user.fans_count = user_info.fans or user.fans_count
                user.interaction_count = user_info.interaction or user.interaction_count
                # updated_at will auto-update via onupdate
            else:
                # Create new user
                user = User(
                    user_id=user_info.user_id,
                    red_id=user_info.red_id,
                    nickname=user_info.nickname,
                    avatar_url=user_info.avatar,
                    avatar_path=avatar_path,
                    description=user_info.desc,
                    gender=user_info.gender,
                    ip_location=user_info.ip_location,
                    follows_count=user_info.follows,
                    fans_count=user_info.fans,
                    interaction_count=user_info.interaction,
                )
                session.add(user)

            # Save user's notes as daily snapshots (upsert)
            today = date.today()
            for note_item in user_info.notes:
                self._upsert_user_note_snapshot(
                    session,
                    user_id=user_info.user_id,
                    note_id=note_item.note_id,
                    snapshot_date=today,
                    title=note_item.title,
                    note_type=note_item.type,
                    likes_count=note_item.likes,
                    cover_url=note_item.cover_url,
                    xsec_token=note_item.xsec_token,
                )

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

    def _upsert_user_note_snapshot(
        self,
        session: Session,
        user_id: str,
        note_id: str,
        snapshot_date: date,
        **kwargs,
    ):
        """Upsert a user note snapshot (one per user-note-day).

        If snapshot exists for today, update it. Otherwise create new.
        """
        existing = session.query(UserNoteSnapshot).filter_by(
            user_id=user_id,
            note_id=note_id,
            snapshot_date=snapshot_date,
        ).first()

        if existing:
            # Update existing snapshot
            for key, value in kwargs.items():
                if value is not None:
                    setattr(existing, key, value)
        else:
            # Create new snapshot
            snapshot = UserNoteSnapshot(
                user_id=user_id,
                note_id=note_id,
                snapshot_date=snapshot_date,
                **kwargs,
            )
            session.add(snapshot)

    async def save_note(
        self,
        note_item: NoteItem,
        author_user_id: Optional[str] = None,
        download_images: bool = True,
        session: Optional[Session] = None,
        source: str = "search",
    ) -> Note:
        """Save note to database with smart caching and daily snapshot tracking.

        Args:
            note_item: Note info from scraper
            author_user_id: Optional author user ID
            download_images: Whether to download cover/images
            session: Optional existing session
            source: Source of the scrape ("search", "user_profile", "direct")

        Returns:
            The saved/updated Note object
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            # Extract note_id from URL
            note_id = self._extract_note_id(note_item.note_url)
            if not note_id:
                raise ValueError(f"Cannot extract note_id from URL: {note_item.note_url}")

            # Check if note exists
            note = session.query(Note).filter_by(note_id=note_id).first()

            # Download images if needed
            cover_path = None
            image_paths = []
            if download_images:
                # Download cover (use first image as cover)
                if note_item.image_urls:
                    cover_path, _ = await self.downloader.download_cover(
                        note_id, note_item.image_urls[0]
                    )
                    # Download all images
                    image_paths, _ = await self.downloader.download_note_images(
                        note_id, note_item.image_urls
                    )

            # Get previous snapshot for change detection
            today = date.today()
            prev_snapshot = self._get_previous_snapshot(session, note_id, today)

            if note:
                # Check for changes and create/update daily snapshot
                has_changes = self._has_note_changes(note, note_item)

                if has_changes or self.settings.cache.always_append_on_change:
                    self._upsert_note_snapshot(
                        session,
                        note_id=note_id,
                        snapshot_date=today,
                        title=note_item.title or note.title,
                        content=note.content,
                        likes_count=note_item.likes or note.likes_count,
                        collects_count=note_item.collects or note.collects_count,
                        comments_count=note_item.comments or note.comments_count,
                        image_urls=note.image_urls,
                        source=source,
                        has_stats_change=has_changes,
                        prev_snapshot=prev_snapshot,
                    )

                # Update existing note
                note.title = note_item.title or note.title
                note.likes_count = note_item.likes if note_item.likes else note.likes_count
                note.collects_count = note_item.collects if note_item.collects else note.collects_count
                note.comments_count = note_item.comments if note_item.comments else note.comments_count
                if cover_path:
                    note.cover_path = cover_path
                    note.cover_url = note_item.image_urls[0] if note_item.image_urls else note.cover_url
                if image_paths:
                    note.set_image_paths(image_paths)
                    note.set_image_urls(note_item.image_urls)
                note.note_url = note_item.note_url or note.note_url
                # updated_at will auto-update via onupdate
            else:
                # Create new note
                note = Note(
                    note_id=note_id,
                    author_user_id=author_user_id,
                    title=note_item.title,
                    likes_count=note_item.likes,
                    collects_count=note_item.collects,
                    comments_count=note_item.comments,
                    cover_url=note_item.image_urls[0] if note_item.image_urls else None,
                    cover_path=cover_path,
                    note_url=note_item.note_url,
                )
                note.set_image_urls(note_item.image_urls)
                note.set_image_paths(image_paths)
                session.add(note)

                # Create first snapshot for new note
                self._upsert_note_snapshot(
                    session,
                    note_id=note_id,
                    snapshot_date=today,
                    title=note_item.title,
                    likes_count=note_item.likes,
                    collects_count=note_item.collects,
                    comments_count=note_item.comments,
                    source=source,
                )

            if own_session:
                session.commit()
                session.refresh(note)

            return note

        except Exception as e:
            if own_session:
                session.rollback()
            raise e

        finally:
            if own_session:
                session.close()

    def _get_previous_snapshot(
        self,
        session: Session,
        note_id: str,
        today: date,
    ) -> Optional[NoteSnapshot]:
        """Get the most recent snapshot before today for change comparison."""
        return (
            session.query(NoteSnapshot)
            .filter(
                NoteSnapshot.note_id == note_id,
                NoteSnapshot.snapshot_date < today,
            )
            .order_by(NoteSnapshot.snapshot_date.desc())
            .first()
        )

    def _upsert_note_snapshot(
        self,
        session: Session,
        note_id: str,
        snapshot_date: date,
        prev_snapshot: Optional[NoteSnapshot] = None,
        **kwargs,
    ):
        """Upsert a note snapshot (one per note per day).

        If snapshot exists for today, update it. Otherwise create new.
        This prevents data explosion from multiple scrapes per day.
        """
        existing = session.query(NoteSnapshot).filter_by(
            note_id=note_id,
            snapshot_date=snapshot_date,
        ).first()

        # Detect changes compared to previous day
        has_title_change = False
        has_content_change = False
        has_stats_change = kwargs.pop("has_stats_change", False)

        if prev_snapshot:
            if kwargs.get("title") and prev_snapshot.title != kwargs.get("title"):
                has_title_change = True
            if kwargs.get("content") and prev_snapshot.content != kwargs.get("content"):
                has_content_change = True

        if existing:
            # Update existing snapshot (same day)
            for key, value in kwargs.items():
                if value is not None:
                    setattr(existing, key, value)
            existing.has_title_change = has_title_change
            existing.has_content_change = has_content_change
            existing.has_stats_change = has_stats_change
        else:
            # Create new snapshot
            snapshot = NoteSnapshot(
                note_id=note_id,
                snapshot_date=snapshot_date,
                has_title_change=has_title_change,
                has_content_change=has_content_change,
                has_stats_change=has_stats_change,
                **kwargs,
            )
            session.add(snapshot)

    def _has_note_changes(self, existing: Note, new: NoteItem) -> bool:
        """Check if note has meaningful changes worth recording."""
        if not self.settings.cache.enable_version_compare:
            return False

        return (
            (new.title and existing.title != new.title) or
            (new.likes and existing.likes_count != new.likes) or
            (new.collects and existing.collects_count != new.collects) or
            (new.comments and existing.comments_count != new.comments) or
            (new.image_urls and len(new.image_urls) != len(existing.get_image_urls()))
        )

    async def batch_save_notes(
        self,
        notes: list[NoteItem],
        source: str = "search",
        download_images: bool = True,
    ) -> tuple[int, int]:
        """Batch save notes with deduplication and daily snapshot tracking.

        Returns:
            Tuple of (new_count, updated_count)
        """
        new_count = 0
        updated_count = 0
        today = date.today()

        with self.transaction() as session:
            for note_item in notes:
                try:
                    note_id = self._extract_note_id(note_item.note_url)
                    if not note_id:
                        continue

                    existing = session.query(Note).filter_by(note_id=note_id).first()

                    # Download images
                    cover_path = None
                    image_paths = []
                    if download_images and note_item.image_urls:
                        cover_path, _ = await self.downloader.download_cover(
                            note_id, note_item.image_urls[0]
                        )
                        image_paths, _ = await self.downloader.download_note_images(
                            note_id, note_item.image_urls
                        )

                    if existing:
                        # Check for changes and create/update daily snapshot
                        has_changes = self._has_note_changes(existing, note_item)

                        if has_changes:
                            prev_snapshot = self._get_previous_snapshot(session, note_id, today)
                            self._upsert_note_snapshot(
                                session,
                                note_id=note_id,
                                snapshot_date=today,
                                title=note_item.title or existing.title,
                                content=existing.content,
                                likes_count=note_item.likes or existing.likes_count,
                                collects_count=note_item.collects or existing.collects_count,
                                comments_count=note_item.comments or existing.comments_count,
                                image_urls=existing.image_urls,
                                source=source,
                                has_stats_change=has_changes,
                                prev_snapshot=prev_snapshot,
                            )

                            # Update note
                            existing.title = note_item.title or existing.title
                            existing.likes_count = note_item.likes or existing.likes_count
                            existing.collects_count = note_item.collects or existing.collects_count
                            existing.comments_count = note_item.comments or existing.comments_count
                            if cover_path:
                                existing.cover_path = cover_path
                            if image_paths:
                                existing.set_image_paths(image_paths)
                            updated_count += 1
                    else:
                        # Create new note
                        note = Note(
                            note_id=note_id,
                            title=note_item.title,
                            likes_count=note_item.likes,
                            collects_count=note_item.collects,
                            comments_count=note_item.comments,
                            cover_url=note_item.image_urls[0] if note_item.image_urls else None,
                            cover_path=cover_path,
                            note_url=note_item.note_url,
                        )
                        note.set_image_urls(note_item.image_urls)
                        note.set_image_paths(image_paths)
                        session.add(note)

                        # Create first snapshot
                        self._upsert_note_snapshot(
                            session,
                            note_id=note_id,
                            snapshot_date=today,
                            title=note_item.title,
                            likes_count=note_item.likes,
                            collects_count=note_item.collects,
                            comments_count=note_item.comments,
                            source=source,
                        )
                        new_count += 1

                except Exception as e:
                    # Log but continue with other notes
                    logger.warning(f"Failed to save note: {e}")
                    continue

        return new_count, updated_count

    async def save_comments(
        self,
        note_id: str,
        comments: list[CommentItem],
        download_avatars: bool = True,
        session: Optional[Session] = None,
    ) -> list[Comment]:
        """Save comments to database.

        Args:
            note_id: The note ID these comments belong to
            comments: List of comments from scraper
            download_avatars: Whether to download user avatars
            session: Optional existing session

        Returns:
            List of saved Comment objects
        """
        own_session = session is None
        if own_session:
            session = self.get_session()

        try:
            saved_comments = []

            for comment_item in comments:
                # Ensure user exists (create minimal user record)
                if comment_item.user_id:
                    user = session.query(User).filter_by(user_id=comment_item.user_id).first()
                    if not user:
                        # Download avatar
                        avatar_path = None
                        if download_avatars and comment_item.avatar:
                            avatar_path, _ = await self.downloader.download_avatar(
                                comment_item.user_id, comment_item.avatar
                            )

                        user = User(
                            user_id=comment_item.user_id,
                            nickname=comment_item.nickname,
                            avatar_url=comment_item.avatar,
                            avatar_path=avatar_path,
                            ip_location=comment_item.ip_location,
                        )
                        session.add(user)

                # Save main comment
                comment = session.query(Comment).filter_by(comment_id=comment_item.comment_id).first()
                if not comment:
                    comment = Comment(
                        comment_id=comment_item.comment_id,
                        note_id=note_id,
                        user_id=comment_item.user_id,
                        content=comment_item.content,
                        likes_count=comment_item.likes,
                        ip_location=comment_item.ip_location,
                        sub_comment_count=comment_item.sub_comment_count,
                        source_created_at=comment_item.create_time,
                    )
                    session.add(comment)
                    saved_comments.append(comment)

                # Save sub-comments
                for sub_item in comment_item.sub_comments:
                    # Ensure sub-comment user exists
                    if sub_item.user_id:
                        sub_user = session.query(User).filter_by(user_id=sub_item.user_id).first()
                        if not sub_user:
                            avatar_path = None
                            if download_avatars and sub_item.avatar:
                                avatar_path, _ = await self.downloader.download_avatar(
                                    sub_item.user_id, sub_item.avatar
                                )

                            sub_user = User(
                                user_id=sub_item.user_id,
                                nickname=sub_item.nickname,
                                avatar_url=sub_item.avatar,
                                avatar_path=avatar_path,
                                ip_location=sub_item.ip_location,
                            )
                            session.add(sub_user)

                    # Save sub-comment
                    sub_comment = session.query(Comment).filter_by(comment_id=sub_item.comment_id).first()
                    if not sub_comment:
                        sub_comment = Comment(
                            comment_id=sub_item.comment_id,
                            note_id=note_id,
                            user_id=sub_item.user_id,
                            parent_comment_id=comment_item.comment_id,
                            content=sub_item.content,
                            likes_count=sub_item.likes,
                            ip_location=sub_item.ip_location,
                            source_created_at=sub_item.create_time,
                        )
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
                status=status,
                items_count=items_count,
                duration_ms=duration_ms,
                error_message=error_message,
            )
            session.add(log)
            session.commit()
        finally:
            session.close()

    @staticmethod
    def _extract_note_id(note_url: str) -> Optional[str]:
        """Extract note ID from URL."""
        if not note_url:
            return None

        # URL formats:
        # - https://www.xiaohongshu.com/explore/{note_id}?...
        # - https://www.xiaohongshu.com/search_result/{note_id}?...
        import re
        match = re.search(r'/(?:explore|search_result)/([a-f0-9]+)', note_url)
        if match:
            return match.group(1)

        return None

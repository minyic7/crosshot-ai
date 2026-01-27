"""SQLite database models using SQLAlchemy.

Time field conventions:
- created_at: Record creation time (immutable)
- updated_at: Last modification time (auto-updated)
- scraped_at: When data was scraped from source (for snapshots)
- snapshot_date: Date of snapshot (for daily dedup, format: YYYY-MM-DD)
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class User(Base):
    """User profile information."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    red_id = Column(String(64), index=True)  # 小红书号
    nickname = Column(String(128))

    # Avatar
    avatar_url = Column(Text)  # Original URL
    avatar_path = Column(String(256))  # Local path

    description = Column(Text)
    gender = Column(Integer, default=0)  # 0=unknown, 1=male, 2=female
    ip_location = Column(String(32))

    # Stats (stored as strings to preserve "1.2万" format)
    follows_count = Column(String(32), default="0")
    fans_count = Column(String(32), default="0")
    interaction_count = Column(String(32), default="0")

    # Unified time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    notes = relationship("Note", back_populates="author")
    comments = relationship("Comment", back_populates="user")


class Note(Base):
    """Note/post information."""

    __tablename__ = "notes"

    id = Column(Integer, primary_key=True)
    note_id = Column(String(64), unique=True, nullable=False, index=True)
    author_user_id = Column(String(64), ForeignKey("users.user_id"), index=True)

    title = Column(String(512))
    content = Column(Text)
    note_type = Column(String(16), default="normal")  # normal/video

    # Stats (stored as strings to preserve "1.2万" format)
    likes_count = Column(String(32), default="0")
    collects_count = Column(String(32), default="0")
    comments_count = Column(String(32), default="0")

    # Cover image
    cover_url = Column(Text)
    cover_path = Column(String(256))

    # Note images (JSON array)
    image_urls = Column(Text)  # JSON string
    image_paths = Column(Text)  # JSON string

    xsec_token = Column(String(256))
    note_url = Column(Text)

    publish_time = Column(DateTime)

    # Unified time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    # Relationships
    author = relationship("User", back_populates="notes")
    comments = relationship("Comment", back_populates="note")
    snapshots = relationship("NoteSnapshot", back_populates="note")

    def get_image_urls(self) -> list[str]:
        if not self.image_urls:
            return []
        return json.loads(self.image_urls)

    def set_image_urls(self, urls: list[str]):
        self.image_urls = json.dumps(urls) if urls else None

    def get_image_paths(self) -> list[str]:
        if not self.image_paths:
            return []
        return json.loads(self.image_paths)

    def set_image_paths(self, paths: list[str]):
        self.image_paths = json.dumps(paths) if paths else None


class NoteSnapshot(Base):
    """Daily snapshot of a note for tracking changes over time.

    IMPORTANT: Only ONE snapshot per note per day is stored.
    This prevents data explosion from frequent scraping.

    Strategy:
    - First scrape of the day: Create new snapshot
    - Subsequent scrapes same day: Update existing snapshot (upsert)
    - Unique constraint on (note_id, snapshot_date) enforces this

    This limits growth to: max_notes × days_tracked
    e.g., 1000 notes × 365 days = 365,000 rows/year (manageable)
    """

    __tablename__ = "note_snapshots"

    id = Column(Integer, primary_key=True)
    note_id = Column(String(64), ForeignKey("notes.note_id"), nullable=False, index=True)

    # Date of this snapshot (YYYY-MM-DD) - used for daily dedup
    snapshot_date = Column(Date, nullable=False, index=True)

    # Snapshot of note data at this point in time
    title = Column(String(512))
    content = Column(Text)
    likes_count = Column(String(32))
    collects_count = Column(String(32))
    comments_count = Column(String(32))

    # Image URLs at time of snapshot (JSON)
    image_urls = Column(Text)

    # Metadata
    source = Column(String(32))  # "search", "user_profile", "direct"

    # Change tracking flags (compared to previous day's snapshot)
    has_title_change = Column(Boolean, default=False)
    has_content_change = Column(Boolean, default=False)
    has_stats_change = Column(Boolean, default=False)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: only one snapshot per note per day
    __table_args__ = (
        UniqueConstraint("note_id", "snapshot_date", name="uq_note_snapshot_daily"),
    )

    # Relationship
    note = relationship("Note", back_populates="snapshots")


class Comment(Base):
    """Comment on a note."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    comment_id = Column(String(64), unique=True, nullable=False, index=True)
    note_id = Column(String(64), ForeignKey("notes.note_id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), index=True)
    parent_comment_id = Column(String(64), ForeignKey("comments.comment_id"), index=True)

    content = Column(Text, nullable=False)
    likes_count = Column(String(32), default="0")
    ip_location = Column(String(32))
    sub_comment_count = Column(Integer, default=0)

    # Original timestamp from XHS (milliseconds)
    source_created_at = Column(Integer)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)  # When we first saw this comment

    # Relationships
    note = relationship("Note", back_populates="comments")
    user = relationship("User", back_populates="comments")
    parent = relationship("Comment", remote_side=[comment_id], backref="replies")


class SearchTask(Base):
    """Search task record."""

    __tablename__ = "search_tasks"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(256), nullable=False, index=True)
    status = Column(String(16), default="pending")  # pending/running/completed/failed

    notes_found = Column(Integer, default=0)
    comments_scraped = Column(Integer, default=0)
    users_discovered = Column(Integer, default=0)

    error_message = Column(Text)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class SearchTaskNote(Base):
    """Association between search task and notes."""

    __tablename__ = "search_task_notes"

    id = Column(Integer, primary_key=True)
    search_task_id = Column(Integer, ForeignKey("search_tasks.id"), nullable=False)
    note_id = Column(String(64), ForeignKey("notes.note_id"), nullable=False)
    rank_position = Column(Integer)  # Position in search results

    created_at = Column(DateTime, default=datetime.utcnow)


class UserNoteSnapshot(Base):
    """Daily snapshot of user's notes from their profile page.

    Same daily dedup strategy as NoteSnapshot.
    """

    __tablename__ = "user_note_snapshots"

    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    note_id = Column(String(64), nullable=False)

    # Date of this snapshot
    snapshot_date = Column(Date, nullable=False, index=True)

    title = Column(String(512))
    note_type = Column(String(16))
    likes_count = Column(String(32))
    cover_url = Column(Text)
    xsec_token = Column(String(256))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Unique constraint: only one snapshot per user-note pair per day
    __table_args__ = (
        UniqueConstraint("user_id", "note_id", "snapshot_date", name="uq_user_note_snapshot_daily"),
    )


class ScrapeLog(Base):
    """Log of scraping operations."""

    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(32), nullable=False)  # search/comments/user
    target_id = Column(String(128))  # keyword/note_id/user_id

    status = Column(String(16), default="success")  # success/failed
    items_count = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ImageDownloadLog(Base):
    """Log of image download attempts for debugging and tracking."""

    __tablename__ = "image_download_logs"

    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False)
    target_type = Column(String(16))  # "avatar", "cover", "note_image"
    target_id = Column(String(64))  # user_id or note_id

    status = Column(String(16), default="pending")  # pending/success/failed
    local_path = Column(String(256))
    error_message = Column(Text)

    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class Database:
    """Database connection and session management."""

    def __init__(self, db_path: str = "data/xhs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def init_db(self):
        """Create all tables."""
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

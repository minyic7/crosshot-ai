"""Database models with cross-platform support.

Design principles:
- platform + platform_id as composite unique key for all entities
- Core fields as columns for fast querying
- Platform-specific fields in platform_data JSONB
- Dual number fields: *_count_num (int for queries) + *_count_display (text for display)
- History tracking via content_history table (append-only, version controlled)

Time field conventions:
- created_at: Record creation time (immutable)
- updated_at: Last modification time (auto-updated)
- scraped_at: When data was scraped from source
- publish_time: When content was published on platform
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


def parse_count(count_str: str) -> int:
    """Parse count string like '1.2万' to integer.

    Examples:
        '1.2万' -> 12000
        '1525' -> 1525
        '赞' -> 0
        '' -> 0
    """
    if not count_str:
        return 0

    count_str = str(count_str).strip()

    # Handle '赞' or other non-numeric strings
    if not any(c.isdigit() for c in count_str):
        return 0

    # Handle '万' (10,000)
    if '万' in count_str:
        try:
            num = float(count_str.replace('万', ''))
            return int(num * 10000)
        except ValueError:
            return 0

    # Handle '亿' (100,000,000)
    if '亿' in count_str:
        try:
            num = float(count_str.replace('亿', ''))
            return int(num * 100000000)
        except ValueError:
            return 0

    # Regular number
    try:
        # Remove any non-numeric characters except digits and decimal point
        clean = re.sub(r'[^\d.]', '', count_str)
        return int(float(clean)) if clean else 0
    except ValueError:
        return 0


class User(Base):
    """User profile information (cross-platform)."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    platform = Column(String(16), nullable=False, index=True)
    platform_user_id = Column(String(64), nullable=False)

    nickname = Column(String(128))
    avatar_url = Column(Text)
    avatar_path = Column(String(256))
    description = Column(Text)
    gender = Column(Integer, default=0)  # 0=unknown, 1=male, 2=female
    ip_location = Column(String(32))

    # Stats - dual fields for query (num) and display (display)
    follows_count_num = Column(Integer, default=0)
    follows_count_display = Column(String(32), default="0")
    fans_count_num = Column(Integer, default=0)
    fans_count_display = Column(String(32), default="0")
    interaction_count_num = Column(Integer, default=0)
    interaction_count_display = Column(String(32), default="0")

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Platform-specific data as JSON
    # e.g., {"red_id": "@xxx"} for XHS, {"douyin_id": "yyy"} for Douyin
    platform_data = Column(Text)  # JSON string

    # Composite unique constraint
    __table_args__ = (
        UniqueConstraint("platform", "platform_user_id", name="uq_user_platform_id"),
    )

    # Relationships
    contents = relationship("Content", back_populates="author")
    comments = relationship("Comment", back_populates="user")

    def get_platform_data(self) -> dict:
        if not self.platform_data:
            return {}
        return json.loads(self.platform_data)

    def set_platform_data(self, data: dict):
        self.platform_data = json.dumps(data) if data else None


class Content(Base):
    """Content/post information (cross-platform).

    Supports various content types: text, image, video, carousel, reel, story, live, mixed
    """

    __tablename__ = "contents"

    id = Column(Integer, primary_key=True)
    platform = Column(String(16), nullable=False, index=True)
    platform_content_id = Column(String(64), nullable=False)

    # Author reference (composite foreign key)
    author_platform = Column(String(16))
    author_platform_user_id = Column(String(64), index=True)

    title = Column(String(512))
    content_text = Column(Text)
    content_type = Column(String(16), default="normal")  # normal/video/image/carousel/reel/story/live/mixed

    # Stats - dual fields
    likes_count_num = Column(Integer, default=0)
    likes_count_display = Column(String(32), default="0")
    collects_count_num = Column(Integer, default=0)
    collects_count_display = Column(String(32), default="0")
    comments_count_num = Column(Integer, default=0)
    comments_count_display = Column(String(32), default="0")

    # Cover image
    cover_url = Column(Text)
    cover_path = Column(String(256))

    # Images as JSON arrays
    image_urls_json = Column(Text)
    image_paths_json = Column(Text)

    # Videos as JSON arrays
    video_urls_json = Column(Text)
    video_paths_json = Column(Text)

    # Legacy fields for backward compatibility (maps to images)
    media_urls_json = Column(Text)
    media_paths_json = Column(Text)

    content_url = Column(Text)
    publish_time = Column(DateTime)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)

    # Platform-specific data as JSON
    # e.g., {"xsec_token": "xxx"} for XHS
    platform_data = Column(Text)

    # Composite unique constraint
    __table_args__ = (
        UniqueConstraint("platform", "platform_content_id", name="uq_content_platform_id"),
        ForeignKeyConstraint(
            ["author_platform", "author_platform_user_id"],
            ["users.platform", "users.platform_user_id"],
            name="fk_content_author",
        ),
    )

    # Relationships
    author = relationship("User", back_populates="contents")
    comments = relationship("Comment", back_populates="parent_content")
    history = relationship("ContentHistory", back_populates="content")

    def get_image_urls(self) -> list[str]:
        if not self.image_urls_json:
            return []
        return json.loads(self.image_urls_json)

    def set_image_urls(self, urls: list[str]):
        self.image_urls_json = json.dumps(urls) if urls else None

    def get_image_paths(self) -> list[str]:
        if not self.image_paths_json:
            return []
        return json.loads(self.image_paths_json)

    def set_image_paths(self, paths: list[str]):
        self.image_paths_json = json.dumps(paths) if paths else None

    def get_video_urls(self) -> list[str]:
        if not self.video_urls_json:
            return []
        return json.loads(self.video_urls_json)

    def set_video_urls(self, urls: list[str]):
        self.video_urls_json = json.dumps(urls) if urls else None

    def get_video_paths(self) -> list[str]:
        if not self.video_paths_json:
            return []
        return json.loads(self.video_paths_json)

    def set_video_paths(self, paths: list[str]):
        self.video_paths_json = json.dumps(paths) if paths else None

    # Legacy methods for backward compatibility
    def get_media_urls(self) -> list[str]:
        if not self.media_urls_json:
            return []
        return json.loads(self.media_urls_json)

    def set_media_urls(self, urls: list[str]):
        self.media_urls_json = json.dumps(urls) if urls else None

    def get_media_paths(self) -> list[str]:
        if not self.media_paths_json:
            return []
        return json.loads(self.media_paths_json)

    def set_media_paths(self, paths: list[str]):
        self.media_paths_json = json.dumps(paths) if paths else None

    def get_platform_data(self) -> dict:
        if not self.platform_data:
            return {}
        return json.loads(self.platform_data)

    def set_platform_data(self, data: dict):
        self.platform_data = json.dumps(data) if data else None


class ContentHistory(Base):
    """History snapshots of content for tracking changes.

    Append-only table with version control.
    Code should limit to 1 snapshot per content per day, keep last 30.
    """

    __tablename__ = "content_history"

    id = Column(Integer, primary_key=True)
    platform = Column(String(16), nullable=False, index=True)
    platform_content_id = Column(String(64), nullable=False)

    version = Column(Integer, nullable=False)

    # Full snapshot as JSON
    data_json = Column(Text, nullable=False)

    # Change tracking
    change_type = Column(String(32))  # "stats_change", "content_change", "initial"

    scraped_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["platform", "platform_content_id"],
            ["contents.platform", "contents.platform_content_id"],
            name="fk_content_history_content",
        ),
    )

    # Relationship
    content = relationship("Content", back_populates="history")

    def get_data(self) -> dict:
        if not self.data_json:
            return {}
        return json.loads(self.data_json)

    def set_data(self, data: dict):
        self.data_json = json.dumps(data) if data else None


class Comment(Base):
    """Comment on a content (cross-platform)."""

    __tablename__ = "comments"

    id = Column(Integer, primary_key=True)
    platform = Column(String(16), nullable=False, index=True)
    platform_comment_id = Column(String(64), nullable=False)

    # Content reference
    content_platform = Column(String(16), nullable=False)
    platform_content_id = Column(String(64), nullable=False, index=True)

    # User reference
    user_platform = Column(String(16))
    platform_user_id = Column(String(64), index=True)

    # Parent comment for replies
    parent_platform_comment_id = Column(String(64), index=True)

    comment_text = Column(Text, nullable=False)  # Renamed from 'content' to avoid conflict
    likes_count_num = Column(Integer, default=0)
    likes_count_display = Column(String(32), default="0")
    ip_location = Column(String(32))
    sub_comment_count = Column(Integer, default=0)

    # Comment images
    image_urls_json = Column(Text)
    image_paths_json = Column(Text)

    # Comment videos
    video_urls_json = Column(Text)
    video_paths_json = Column(Text)

    # Original timestamp from platform (milliseconds)
    create_time = Column(BigInteger)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)

    # Platform-specific data
    platform_data = Column(Text)

    def get_image_urls(self) -> list[str]:
        if not self.image_urls_json:
            return []
        return json.loads(self.image_urls_json)

    def set_image_urls(self, urls: list[str]):
        self.image_urls_json = json.dumps(urls) if urls else None

    def get_image_paths(self) -> list[str]:
        if not self.image_paths_json:
            return []
        return json.loads(self.image_paths_json)

    def set_image_paths(self, paths: list[str]):
        self.image_paths_json = json.dumps(paths) if paths else None

    def get_video_urls(self) -> list[str]:
        if not self.video_urls_json:
            return []
        return json.loads(self.video_urls_json)

    def set_video_urls(self, urls: list[str]):
        self.video_urls_json = json.dumps(urls) if urls else None

    def get_video_paths(self) -> list[str]:
        if not self.video_paths_json:
            return []
        return json.loads(self.video_paths_json)

    def set_video_paths(self, paths: list[str]):
        self.video_paths_json = json.dumps(paths) if paths else None

    __table_args__ = (
        UniqueConstraint("platform", "platform_comment_id", name="uq_comment_platform_id"),
        ForeignKeyConstraint(
            ["content_platform", "platform_content_id"],
            ["contents.platform", "contents.platform_content_id"],
            name="fk_comment_content",
        ),
        ForeignKeyConstraint(
            ["user_platform", "platform_user_id"],
            ["users.platform", "users.platform_user_id"],
            name="fk_comment_user",
        ),
    )

    # Relationships
    parent_content = relationship("Content", back_populates="comments")
    user = relationship("User", back_populates="comments")


class SearchTask(Base):
    """Search task record."""

    __tablename__ = "search_tasks"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(256), nullable=False, index=True)
    platform = Column(String(16), nullable=False, index=True)
    status = Column(String(16), default="pending")  # pending/running/completed/failed

    contents_found = Column(Integer, default=0)
    comments_scraped = Column(Integer, default=0)
    users_discovered = Column(Integer, default=0)

    error_message = Column(Text)

    # Time fields
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)


class SearchTaskContent(Base):
    """Association between search task and contents."""

    __tablename__ = "search_task_contents"

    id = Column(Integer, primary_key=True)
    search_task_id = Column(Integer, nullable=False, index=True)

    platform = Column(String(16), nullable=False)
    platform_content_id = Column(String(64), nullable=False)
    rank_position = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        ForeignKeyConstraint(
            ["platform", "platform_content_id"],
            ["contents.platform", "contents.platform_content_id"],
            name="fk_search_task_content",
        ),
    )


class ScrapeLog(Base):
    """Log of scraping operations."""

    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True)
    task_type = Column(String(32), nullable=False)  # search/comments/user
    target_id = Column(String(128))  # keyword/content_id/user_id
    platform = Column(String(16))

    status = Column(String(16), default="success")  # success/failed
    items_count = Column(Integer, default=0)
    duration_ms = Column(Integer)
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ImageDownloadLog(Base):
    """Log of image download attempts."""

    __tablename__ = "image_download_logs"

    id = Column(Integer, primary_key=True)
    url = Column(Text, nullable=False, index=True)
    target_type = Column(String(16))  # "avatar", "cover", "content_media"
    target_id = Column(String(64))  # user_id or content_id
    platform = Column(String(16))

    status = Column(String(16), default="pending")  # pending/success/failed
    local_path = Column(String(256))
    error_message = Column(Text)

    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class AgentConfig(Base):
    """Agent type configuration template.

    Each record defines a type of agent that can be instantiated as a Docker container.
    Multiple containers can be spawned from the same AgentConfig with different parameters.
    """

    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False, unique=True)
    display_name = Column(String(256), nullable=False)
    agent_type = Column(String(64), nullable=False, index=True)
    platform = Column(String(16), nullable=False, index=True)
    description = Column(Text)

    # Docker configuration
    command = Column(Text, nullable=False)
    environment_json = Column(Text, default="{}")
    cpu_limit = Column(String(16), default="2.0")
    memory_limit = Column(String(16), default="2G")
    cpu_reservation = Column(String(16), default="0.5")
    memory_reservation = Column(String(16), default="1G")
    restart_policy = Column(String(32), default="on-failure")

    is_active = Column(Integer, default=1)  # 1=active, 0=archived

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_environment(self) -> dict:
        if not self.environment_json:
            return {}
        return json.loads(self.environment_json)

    def set_environment(self, env: dict):
        self.environment_json = json.dumps(env) if env else "{}"


# Aliases for backward compatibility during migration
Note = Content
NoteHistory = ContentHistory
SearchTaskNote = SearchTaskContent


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

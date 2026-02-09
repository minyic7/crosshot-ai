"""SQLAlchemy ORM models — cross-platform schema for Crosshot AI."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    parent_job_id: Mapped[str | None] = mapped_column(Uuid, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=3)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    contents: Mapped[list["ContentRow"]] = relationship(back_populates="task")

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_label_status", "label", "status"),
        Index("ix_tasks_parent_job_id", "parent_job_id"),
        Index("ix_tasks_created_at", "created_at", postgresql_using="btree"),
    )


class ContentRow(Base):
    """Cross-platform content — only universally shared columns are top-level."""

    __tablename__ = "contents"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[str] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    platform_content_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Author (generic across platforms)
    author_uid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Content
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    hashtags: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    # Media
    media_downloaded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Platform-specific (JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    task: Mapped["TaskRow"] = relationship(back_populates="contents")
    media: Mapped[list["ContentMediaRow"]] = relationship(
        back_populates="content", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_contents_platform", "platform"),
        Index("ix_contents_task_id", "task_id"),
        Index(
            "ix_contents_platform_content_id",
            "platform",
            "platform_content_id",
            unique=True,
        ),
        Index("ix_contents_crawled_at", "crawled_at", postgresql_using="btree"),
        Index("ix_contents_author_username", "author_username"),
        Index("ix_contents_hashtags", "hashtags", postgresql_using="gin"),
    )


class ContentMediaRow(Base):
    """Media items belonging to a content entry — cross-platform."""

    __tablename__ = "content_media"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("contents.id", ondelete="CASCADE"), nullable=False
    )
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_local_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    download_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    # Relationships
    content: Mapped["ContentRow"] = relationship(back_populates="media")

    __table_args__ = (Index("ix_content_media_content_id", "content_id"),)


class CookieRow(Base):
    """Cookie pool entry — cross-platform credential management."""

    __tablename__ = "cookies"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    cookies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    use_count_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    cooldown_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (Index("ix_cookies_platform_active", "platform", "is_active"),)

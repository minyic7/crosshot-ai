"""SQLAlchemy ORM models — cross-platform schema for Crosshot AI."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    Uuid,
)
import sqlalchemy as sa
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

    # Temporal context fields
    period_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )
    effectiveness_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("crawl_effectiveness.id", ondelete="SET NULL"), nullable=True
    )
    duration_seconds: Mapped[float | None] = mapped_column(sa.Float, nullable=True)

    # Relationships
    contents: Mapped[list["ContentRow"]] = relationship(back_populates="task")

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_label_status", "label", "status"),
        Index("ix_tasks_parent_job_id", "parent_job_id"),
        Index("ix_tasks_created_at", "created_at", postgresql_using="btree"),
        Index("ix_tasks_period", "period_id"),
        Index("ix_tasks_effectiveness", "effectiveness_id"),
    )


class ContentRow(Base):
    """Cross-platform content — only universally shared columns are top-level."""

    __tablename__ = "contents"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    task_id: Mapped[str] = mapped_column(Uuid, ForeignKey("tasks.id"), nullable=False)
    topic_id: Mapped[str | None] = mapped_column(Uuid, ForeignKey("topics.id"), nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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

    # Knowledge processing — triage + integration status
    processing_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    key_points: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Temporal context fields
    analysis_period_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc)
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Platform-specific (JSONB)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    task: Mapped["TaskRow"] = relationship(back_populates="contents")
    topic: Mapped["TopicRow | None"] = relationship(back_populates="contents", foreign_keys=[topic_id])
    user: Mapped["UserRow | None"] = relationship(back_populates="contents", foreign_keys=[user_id])
    media: Mapped[list["ContentMediaRow"]] = relationship(
        back_populates="content", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_contents_platform", "platform"),
        Index("ix_contents_task_id", "task_id"),
        Index("ix_contents_topic_id", "topic_id"),
        Index("ix_contents_user_id", "user_id"),
        Index(
            "ix_contents_platform_content_id",
            "platform",
            "platform_content_id",
            unique=True,
        ),
        Index("ix_contents_crawled_at", "crawled_at", postgresql_using="btree"),
        Index("ix_contents_processing_status", "processing_status"),
        Index("ix_contents_author_username", "author_username"),
        Index("ix_contents_hashtags", "hashtags", postgresql_using="gin"),
        Index("ix_contents_period", "analysis_period_id"),
        Index("ix_contents_published_at", "published_at", postgresql_using="btree"),
        Index("ix_contents_discovered_at", "discovered_at", postgresql_using="btree"),
        CheckConstraint("relevance_score >= 0 AND relevance_score <= 1", name="valid_content_relevance"),
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


topic_users = Table(
    "topic_users",
    Base.metadata,
    Column("topic_id", Uuid, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class TopicRow(Base):
    """A monitored topic — the top-level entity users create and track."""

    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    type: Mapped[str] = mapped_column(String(16), nullable=False, default="topic")  # 'topic' | 'creator'
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    icon: Mapped[str] = mapped_column(String(8), nullable=False, default="📊")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration
    platforms: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # State
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stats (updated by analyst after summarize)
    total_contents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_crawl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Temporal context fields
    current_period_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_period_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )
    total_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_period_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    contents: Mapped[list["ContentRow"]] = relationship(
        back_populates="topic", foreign_keys="ContentRow.topic_id"
    )
    users: Mapped[list["UserRow"]] = relationship(
        secondary=topic_users, back_populates="topics"
    )

    __table_args__ = (
        Index("ix_topics_status", "status"),
        Index("ix_topics_position", "position"),
        Index("ix_topics_last_period", "last_period_id"),
    )


class UserRow(Base):
    """A tracked user/creator — can be standalone or attached to topics."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_url: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Configuration
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # State
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    is_pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stats
    total_contents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_crawl_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Temporal context fields
    current_period_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_period_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )
    total_periods: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    first_analysis_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_period_duration_hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    topics: Mapped[list["TopicRow"]] = relationship(
        secondary=topic_users, back_populates="users"
    )
    contents: Mapped[list["ContentRow"]] = relationship(
        back_populates="user", foreign_keys="ContentRow.user_id"
    )

    __table_args__ = (
        Index("ix_users_status", "status"),
        Index("ix_users_platform", "platform"),
        Index("ix_users_username", "username"),
        Index("ix_users_last_period", "last_period_id"),
    )


class AnalysisPeriodRow(Base):
    """Complete analysis cycle record — the central timeline spine."""

    __tablename__ = "analysis_periods"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(Uuid, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    period_number: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_hours: Mapped[float] = mapped_column(Float, nullable=False)

    # Lifecycle management
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    superseded_by: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )
    supersession_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Core analysis outputs
    content_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    summary_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    insights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metrics_delta: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Task tracking
    tasks_dispatched: Mapped[list[str]] = mapped_column(
        ARRAY(Uuid), nullable=False, default=list
    )
    tasks_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Chat integration
    chat_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Knowledge evolution
    knowledge_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    knowledge_doc: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowledge_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Quality tracking
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Debugging & operations
    execution_log: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        CheckConstraint("entity_type IN ('topic', 'user')", name="valid_entity_type"),
        CheckConstraint(
            "status IN ('active', 'draft', 'superseded', 'failed', 'archived')",
            name="valid_status",
        ),
        CheckConstraint("period_end > period_start", name="valid_period"),
        CheckConstraint(
            "quality_score >= 0 AND quality_score <= 1", name="valid_quality_score"
        ),
        CheckConstraint(
            "completeness_score >= 0 AND completeness_score <= 1",
            name="valid_completeness_score",
        ),
        Index("idx_periods_analyzed_at", "analyzed_at", postgresql_using="btree"),
        Index("idx_periods_status", "status"),
    )


class PeriodContentSnapshotRow(Base):
    """Junction table + snapshot: which contents belong to which period."""

    __tablename__ = "period_content_snapshots"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    period_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="CASCADE"), nullable=False
    )
    content_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("contents.id", ondelete="CASCADE"), nullable=False
    )
    contribution_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="general"
    )
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_points_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1", name="valid_relevance_score"
        ),
        Index("idx_snapshot_content", "content_id"),
        Index("unique_period_content", "period_id", "content_id", unique=True),
    )


class TemporalEventRow(Base):
    """Significant events tracked across periods (controversies, trends, anomalies)."""

    __tablename__ = "temporal_events"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    period_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(Uuid, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="info")
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    first_detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint("entity_type IN ('topic', 'user')", name="valid_event_entity_type"),
        CheckConstraint(
            "severity IN ('info', 'warning', 'critical')", name="valid_severity"
        ),
        Index("idx_events_period", "period_id"),
        Index("idx_events_entity", "entity_type", "entity_id", "first_detected_at"),
        Index("idx_events_type", "event_type"),
    )


class EventContentRow(Base):
    """Junction table: which contents are related to which events."""

    __tablename__ = "event_contents"

    event_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("temporal_events.id", ondelete="CASCADE"), primary_key=True
    )
    content_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("contents.id", ondelete="CASCADE"), primary_key=True
    )
    relevance_to_event: Mapped[float | None] = mapped_column(Float, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "relevance_to_event >= 0 AND relevance_to_event <= 1",
            name="valid_event_relevance",
        ),
    )


class CrawlEffectivenessRow(Base):
    """Track effectiveness of crawl queries over time — learn what works."""

    __tablename__ = "crawl_effectiveness"

    id: Mapped[str] = mapped_column(Uuid, primary_key=True, default=uuid4)
    period_id: Mapped[str] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(Uuid, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    total_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relevant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_value_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effectiveness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint("entity_type IN ('topic', 'user')", name="valid_crawl_entity_type"),
        CheckConstraint(
            "effectiveness_score >= 0 AND effectiveness_score <= 1",
            name="valid_effectiveness_score",
        ),
        CheckConstraint(
            "avg_relevance >= 0 AND avg_relevance <= 1", name="valid_avg_relevance"
        ),
        CheckConstraint(
            "coverage_ratio >= 0 AND coverage_ratio <= 1", name="valid_coverage_ratio"
        ),
        Index("idx_effectiveness_period", "period_id"),
        Index("idx_effectiveness_entity", "entity_type", "entity_id", "created_at"),
        Index("idx_effectiveness_platform", "platform"),
    )


class ChatMessageRow(Base):
    """Persisted chat messages for topic and user conversations."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(16), nullable=False)  # 'topic' | 'user'
    entity_id: Mapped[str] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # 'user' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Temporal context field
    period_id: Mapped[str | None] = mapped_column(
        Uuid, ForeignKey("analysis_periods.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_chat_messages_entity", "entity_type", "entity_id", "is_archived"),
        Index("ix_chat_messages_period", "period_id"),
    )

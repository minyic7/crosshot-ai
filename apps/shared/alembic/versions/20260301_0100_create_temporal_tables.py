"""Create temporal context tables (analysis_periods, temporal_events, crawl_effectiveness, snapshots)

Revision ID: 20260301_0100
Revises:
Create Date: 2026-03-01 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260301_0100'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable required PostgreSQL extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Create analysis_periods table
    op.create_table(
        'analysis_periods',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('analyzed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('period_number', sa.Integer, nullable=False),
        sa.Column('duration_hours', sa.Float, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('superseded_by', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('supersession_reason', sa.Text, nullable=True),
        sa.Column('content_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('summary', sa.Text, nullable=False),
        sa.Column('summary_short', sa.Text, nullable=True),
        sa.Column('insights', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('metrics_delta', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('tasks_dispatched', postgresql.ARRAY(postgresql.UUID(as_uuid=False)), nullable=False, server_default='{}'),
        sa.Column('tasks_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('chat_summary', sa.Text, nullable=True),
        sa.Column('knowledge_version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('knowledge_doc', sa.Text, nullable=True),
        sa.Column('knowledge_diff', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('completeness_score', sa.Float, nullable=True),
        sa.Column('execution_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("entity_type IN ('topic', 'user')", name='valid_entity_type'),
        sa.CheckConstraint("status IN ('active', 'draft', 'superseded', 'failed', 'archived')", name='valid_status'),
        sa.CheckConstraint('period_end > period_start', name='valid_period'),
        sa.CheckConstraint('quality_score >= 0 AND quality_score <= 1', name='valid_quality_score'),
        sa.CheckConstraint('completeness_score >= 0 AND completeness_score <= 1', name='valid_completeness_score'),
    )

    # Add FK for superseded_by (self-reference)
    op.create_foreign_key(
        'fk_analysis_periods_superseded_by',
        'analysis_periods', 'analysis_periods',
        ['superseded_by'], ['id'],
        ondelete='SET NULL'
    )

    # Set compression on knowledge_doc
    op.execute("ALTER TABLE analysis_periods ALTER COLUMN knowledge_doc SET COMPRESSION pglz")

    # Create indexes for analysis_periods
    op.create_index(
        'unique_active_period_number',
        'analysis_periods',
        ['entity_type', 'entity_id', 'period_number'],
        unique=True,
        postgresql_where=sa.text("status = 'active'")
    )
    op.create_index(
        'idx_periods_topic',
        'analysis_periods',
        ['entity_id'],
        postgresql_where=sa.text("entity_type = 'topic'")
    )
    op.create_index(
        'idx_periods_user',
        'analysis_periods',
        ['entity_id'],
        postgresql_where=sa.text("entity_type = 'user'")
    )
    op.create_index(
        'idx_periods_analyzed_at',
        'analysis_periods',
        ['analyzed_at'],
        postgresql_using='btree'
    )
    op.create_index(
        'idx_periods_status',
        'analysis_periods',
        ['status']
    )

    # Create exclusion constraint for overlapping periods
    op.execute("""
        ALTER TABLE analysis_periods
        ADD CONSTRAINT no_overlapping_periods
        EXCLUDE USING GIST (
            entity_type WITH =,
            entity_id WITH =,
            tstzrange(period_start, period_end) WITH &&
        ) WHERE (status = 'active')
    """)

    # Create period_content_snapshots table
    op.create_table(
        'period_content_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('period_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('content_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('contribution_type', sa.String(32), nullable=False, server_default='general'),
        sa.Column('relevance_score', sa.Float, nullable=True),
        sa.Column('text_snapshot', sa.Text, nullable=True),
        sa.Column('key_points_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint('relevance_score >= 0 AND relevance_score <= 1', name='valid_relevance_score'),
    )

    # FKs for period_content_snapshots (will be added after contents table is confirmed to exist in migration 2)
    # For now, just create the table structure

    # Create indexes for period_content_snapshots
    op.create_index(
        'idx_snapshot_period_covering',
        'period_content_snapshots',
        ['period_id', sa.text('relevance_score DESC')],
        postgresql_include=['content_id', 'contribution_type', 'text_snapshot']
    )
    op.create_index(
        'idx_snapshot_content',
        'period_content_snapshots',
        ['content_id']
    )
    op.create_index(
        'unique_period_content',
        'period_content_snapshots',
        ['period_id', 'content_id'],
        unique=True
    )

    # Create temporal_events table
    op.create_table(
        'temporal_events',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('period_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('event_type', sa.String(32), nullable=False),
        sa.Column('severity', sa.String(16), nullable=False, server_default='info'),
        sa.Column('title', sa.String(256), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('first_detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolution_note', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("entity_type IN ('topic', 'user')", name='valid_event_entity_type'),
        sa.CheckConstraint("severity IN ('info', 'warning', 'critical')", name='valid_severity'),
    )

    # FK for temporal_events.period_id
    op.create_foreign_key(
        'fk_temporal_events_period',
        'temporal_events', 'analysis_periods',
        ['period_id'], ['id'],
        ondelete='CASCADE'
    )

    # Create indexes for temporal_events
    op.create_index(
        'idx_events_period',
        'temporal_events',
        ['period_id']
    )
    op.create_index(
        'idx_events_entity',
        'temporal_events',
        ['entity_type', 'entity_id', 'first_detected_at']
    )
    op.create_index(
        'idx_events_unresolved',
        'temporal_events',
        ['entity_type', 'entity_id', 'resolved_at'],
        postgresql_where=sa.text('resolved_at IS NULL')
    )
    op.create_index(
        'idx_events_type',
        'temporal_events',
        ['event_type']
    )

    # Create event_contents junction table
    op.create_table(
        'event_contents',
        sa.Column('event_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('content_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('relevance_to_event', sa.Float, nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('event_id', 'content_id'),
        sa.CheckConstraint('relevance_to_event >= 0 AND relevance_to_event <= 1', name='valid_event_relevance'),
    )

    # FK for event_contents
    op.create_foreign_key(
        'fk_event_contents_event',
        'event_contents', 'temporal_events',
        ['event_id'], ['id'],
        ondelete='CASCADE'
    )
    # content_id FK will be added in migration 2 after confirming contents table exists

    # Create crawl_effectiveness table
    op.create_table(
        'crawl_effectiveness',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('period_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('platform', sa.String(16), nullable=False),
        sa.Column('query', sa.Text, nullable=False),
        sa.Column('total_found', sa.Integer, nullable=False, server_default='0'),
        sa.Column('relevant_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('high_value_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('effectiveness_score', sa.Float, nullable=True),
        sa.Column('avg_relevance', sa.Float, nullable=True),
        sa.Column('coverage_ratio', sa.Float, nullable=True),
        sa.Column('recommendations', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("entity_type IN ('topic', 'user')", name='valid_crawl_entity_type'),
        sa.CheckConstraint('effectiveness_score >= 0 AND effectiveness_score <= 1', name='valid_effectiveness_score'),
        sa.CheckConstraint('avg_relevance >= 0 AND avg_relevance <= 1', name='valid_avg_relevance'),
        sa.CheckConstraint('coverage_ratio >= 0 AND coverage_ratio <= 1', name='valid_coverage_ratio'),
    )

    # FK for crawl_effectiveness.period_id
    op.create_foreign_key(
        'fk_crawl_effectiveness_period',
        'crawl_effectiveness', 'analysis_periods',
        ['period_id'], ['id'],
        ondelete='CASCADE'
    )

    # Create indexes for crawl_effectiveness
    op.create_index(
        'idx_effectiveness_period',
        'crawl_effectiveness',
        ['period_id']
    )
    op.create_index(
        'idx_effectiveness_entity',
        'crawl_effectiveness',
        ['entity_type', 'entity_id', 'created_at']
    )
    op.create_index(
        'idx_effectiveness_platform',
        'crawl_effectiveness',
        ['platform']
    )
    op.create_index(
        'idx_effectiveness_query_trgm',
        'crawl_effectiveness',
        ['query'],
        postgresql_using='gin',
        postgresql_ops={'query': 'gin_trgm_ops'}
    )
    op.create_index(
        'idx_effectiveness_score',
        'crawl_effectiveness',
        [sa.text('effectiveness_score DESC NULLS LAST')]
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('crawl_effectiveness')
    op.drop_table('event_contents')
    op.drop_table('temporal_events')
    op.drop_table('period_content_snapshots')
    op.drop_table('analysis_periods')

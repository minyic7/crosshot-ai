"""Alter existing tables to support temporal context (topics, users, contents, tasks, chat_messages)

Revision ID: 20260301_0200
Revises: 20260301_0100
Create Date: 2026-03-01 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '20260301_0200'
down_revision: Union[str, None] = '20260301_0100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Alter topics table
    op.add_column('topics', sa.Column('current_period_number', sa.Integer, nullable=True))
    op.add_column('topics', sa.Column('last_period_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('topics', sa.Column('total_periods', sa.Integer, nullable=False, server_default='0'))
    op.add_column('topics', sa.Column('first_analysis_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('topics', sa.Column('avg_period_duration_hours', sa.Float, nullable=True))

    # FK for topics.last_period_id
    op.create_foreign_key(
        'fk_topics_last_period',
        'topics', 'analysis_periods',
        ['last_period_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create indexes for topics
    op.create_index('idx_topics_last_period', 'topics', ['last_period_id'])

    # Alter users table
    op.add_column('users', sa.Column('current_period_number', sa.Integer, nullable=True))
    op.add_column('users', sa.Column('last_period_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('users', sa.Column('total_periods', sa.Integer, nullable=False, server_default='0'))
    op.add_column('users', sa.Column('first_analysis_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('avg_period_duration_hours', sa.Float, nullable=True))

    # FK for users.last_period_id
    op.create_foreign_key(
        'fk_users_last_period',
        'users', 'analysis_periods',
        ['last_period_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create indexes for users
    op.create_index('idx_users_last_period', 'users', ['last_period_id'])

    # Alter contents table
    op.add_column('contents', sa.Column('analysis_period_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('contents', sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('contents', sa.Column('discovered_at', sa.DateTime(timezone=True), nullable=True, server_default=sa.text('NOW()')))
    op.add_column('contents', sa.Column('relevance_score', sa.Float, nullable=True))

    # Add check constraint for relevance_score
    op.create_check_constraint(
        'valid_content_relevance',
        'contents',
        'relevance_score >= 0 AND relevance_score <= 1'
    )

    # FK for contents.analysis_period_id
    op.create_foreign_key(
        'fk_contents_analysis_period',
        'contents', 'analysis_periods',
        ['analysis_period_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create indexes for contents
    op.create_index('idx_contents_period', 'contents', ['analysis_period_id'])
    op.create_index('idx_contents_published_at', 'contents', ['published_at'], postgresql_using='btree')
    op.create_index('idx_contents_discovered_at', 'contents', ['discovered_at'], postgresql_using='btree')
    op.create_index('idx_contents_relevance', 'contents', [sa.text('relevance_score DESC NULLS LAST')])

    # Now add missing FKs to tables created in migration 1
    # period_content_snapshots FKs
    op.create_foreign_key(
        'fk_snapshots_period',
        'period_content_snapshots', 'analysis_periods',
        ['period_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_snapshots_content',
        'period_content_snapshots', 'contents',
        ['content_id'], ['id'],
        ondelete='CASCADE'
    )

    # event_contents.content_id FK
    op.create_foreign_key(
        'fk_event_contents_content',
        'event_contents', 'contents',
        ['content_id'], ['id'],
        ondelete='CASCADE'
    )

    # Alter tasks table
    op.add_column('tasks', sa.Column('period_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('tasks', sa.Column('effectiveness_id', postgresql.UUID(as_uuid=False), nullable=True))
    op.add_column('tasks', sa.Column('duration_seconds', sa.Float, nullable=True))

    # FKs for tasks
    op.create_foreign_key(
        'fk_tasks_period',
        'tasks', 'analysis_periods',
        ['period_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_foreign_key(
        'fk_tasks_effectiveness',
        'tasks', 'crawl_effectiveness',
        ['effectiveness_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create indexes for tasks
    op.create_index('idx_tasks_period', 'tasks', ['period_id'])
    op.create_index('idx_tasks_effectiveness', 'tasks', ['effectiveness_id'])

    # Alter chat_messages table
    op.add_column('chat_messages', sa.Column('period_id', postgresql.UUID(as_uuid=False), nullable=True))

    # FK for chat_messages.period_id
    op.create_foreign_key(
        'fk_chat_messages_period',
        'chat_messages', 'analysis_periods',
        ['period_id'], ['id'],
        ondelete='SET NULL'
    )

    # Create index for chat_messages
    op.create_index('idx_chat_messages_period', 'chat_messages', ['period_id'])


def downgrade() -> None:
    # Remove chat_messages changes
    op.drop_index('idx_chat_messages_period', 'chat_messages')
    op.drop_constraint('fk_chat_messages_period', 'chat_messages', type_='foreignkey')
    op.drop_column('chat_messages', 'period_id')

    # Remove tasks changes
    op.drop_index('idx_tasks_effectiveness', 'tasks')
    op.drop_index('idx_tasks_period', 'tasks')
    op.drop_constraint('fk_tasks_effectiveness', 'tasks', type_='foreignkey')
    op.drop_constraint('fk_tasks_period', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'duration_seconds')
    op.drop_column('tasks', 'effectiveness_id')
    op.drop_column('tasks', 'period_id')

    # Remove cross-table FKs from migration 1
    op.drop_constraint('fk_event_contents_content', 'event_contents', type_='foreignkey')
    op.drop_constraint('fk_snapshots_content', 'period_content_snapshots', type_='foreignkey')
    op.drop_constraint('fk_snapshots_period', 'period_content_snapshots', type_='foreignkey')

    # Remove contents changes
    op.drop_index('idx_contents_relevance', 'contents')
    op.drop_index('idx_contents_discovered_at', 'contents')
    op.drop_index('idx_contents_published_at', 'contents')
    op.drop_index('idx_contents_period', 'contents')
    op.drop_constraint('fk_contents_analysis_period', 'contents', type_='foreignkey')
    op.drop_constraint('valid_content_relevance', 'contents', type_='check')
    op.drop_column('contents', 'relevance_score')
    op.drop_column('contents', 'discovered_at')
    op.drop_column('contents', 'published_at')
    op.drop_column('contents', 'analysis_period_id')

    # Remove users changes
    op.drop_index('idx_users_last_period', 'users')
    op.drop_constraint('fk_users_last_period', 'users', type_='foreignkey')
    op.drop_column('users', 'avg_period_duration_hours')
    op.drop_column('users', 'first_analysis_at')
    op.drop_column('users', 'total_periods')
    op.drop_column('users', 'last_period_id')
    op.drop_column('users', 'current_period_number')

    # Remove topics changes
    op.drop_index('idx_topics_last_period', 'topics')
    op.drop_constraint('fk_topics_last_period', 'topics', type_='foreignkey')
    op.drop_column('topics', 'avg_period_duration_hours')
    op.drop_column('topics', 'first_analysis_at')
    op.drop_column('topics', 'total_periods')
    op.drop_column('topics', 'last_period_id')
    op.drop_column('topics', 'current_period_number')

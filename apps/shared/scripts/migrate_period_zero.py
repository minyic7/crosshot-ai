#!/usr/bin/env python3
"""Data migration: Initialize Period 0 for existing topics and users.

This script creates baseline analysis periods for entities that have data
but no periods yet. Run this AFTER applying the temporal schema migrations.

Usage:
    # From apps/shared directory
    export DATABASE_URL="postgresql+asyncpg://crosshot:crosshot@localhost:5432/crosshot"
    uv run python scripts/migrate_period_zero.py

    # Or with custom DB URL
    uv run python scripts/migrate_period_zero.py --db-url "postgresql+asyncpg://..."

    # Dry run (no commits)
    uv run python scripts/migrate_period_zero.py --dry-run
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, "/Users/minyic/git/crosshot-ai/apps/shared")

from shared.db.models import AnalysisPeriodRow, ContentRow, TopicRow, UserRow


async def create_period_zero_for_topic(session: AsyncSession, topic: TopicRow, dry_run: bool = False) -> bool:
    """Create Period 0 for a topic that has data but no periods."""

    # Check if this topic already has periods
    existing = await session.scalar(
        select(AnalysisPeriodRow)
        .where(
            AnalysisPeriodRow.entity_type == "topic",
            AnalysisPeriodRow.entity_id == topic.id,
        )
        .limit(1)
    )

    if existing:
        print(f"  ⏭️  Topic '{topic.name}' already has periods, skipping")
        return False

    # Get content count and earliest/latest crawl times
    contents = await session.scalars(
        select(ContentRow)
        .where(ContentRow.topic_id == topic.id)
        .order_by(ContentRow.crawled_at)
    )
    content_list = list(contents)

    if not content_list:
        print(f"  ⏭️  Topic '{topic.name}' has no contents, skipping")
        return False

    # Calculate period boundaries
    period_start = content_list[0].crawled_at or topic.created_at
    period_end = topic.last_crawl_at or datetime.now(timezone.utc)
    duration_hours = (period_end - period_start).total_seconds() / 3600.0

    # Build period 0
    period = AnalysisPeriodRow(
        id=str(uuid4()),
        entity_type="topic",
        entity_id=topic.id,
        period_number=0,
        period_start=period_start,
        period_end=period_end,
        analyzed_at=period_end,
        duration_hours=duration_hours,
        content_count=len(content_list),
        status="active",
        summary=topic.last_summary or "Legacy period - migrated from pre-temporal schema",
        summary_short=None,
        insights=topic.summary_data.get("insights", {}) if topic.summary_data else {},
        metrics=topic.summary_data.get("metrics", {}) if topic.summary_data else {},
        metrics_delta={},  # First period has no delta
        tasks_dispatched=[],
        tasks_summary={},
        chat_summary=None,
        knowledge_version=1,
        knowledge_doc=None,
        knowledge_diff=None,
        quality_score=None,
        completeness_score=None,
        execution_log={
            "migration": "period_zero",
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Backfilled from existing data"
        },
    )

    if dry_run:
        print(f"  🔍 [DRY RUN] Would create Period 0 for topic '{topic.name}':")
        print(f"     - Period: {period_start} → {period_end} ({duration_hours:.1f}h)")
        print(f"     - Contents: {len(content_list)}")
        return True

    # Create period
    session.add(period)

    # Update topic to link to this period
    topic.current_period_number = 0
    topic.last_period_id = period.id
    topic.total_periods = 1
    topic.first_analysis_at = period.analyzed_at
    topic.avg_period_duration_hours = duration_hours

    # Update all contents to link to this period
    for content in content_list:
        content.analysis_period_id = period.id
        content.discovered_at = content.crawled_at

    print(f"  ✅ Created Period 0 for topic '{topic.name}':")
    print(f"     - Period: {period_start} → {period_end} ({duration_hours:.1f}h)")
    print(f"     - Contents: {len(content_list)}")

    return True


async def create_period_zero_for_user(session: AsyncSession, user: UserRow, dry_run: bool = False) -> bool:
    """Create Period 0 for a user that has data but no periods."""

    # Check if this user already has periods
    existing = await session.scalar(
        select(AnalysisPeriodRow)
        .where(
            AnalysisPeriodRow.entity_type == "user",
            AnalysisPeriodRow.entity_id == user.id,
        )
        .limit(1)
    )

    if existing:
        print(f"  ⏭️  User '{user.name}' already has periods, skipping")
        return False

    # Get content count and earliest/latest crawl times
    contents = await session.scalars(
        select(ContentRow)
        .where(ContentRow.user_id == user.id)
        .order_by(ContentRow.crawled_at)
    )
    content_list = list(contents)

    if not content_list:
        print(f"  ⏭️  User '{user.name}' has no contents, skipping")
        return False

    # Calculate period boundaries
    period_start = content_list[0].crawled_at or user.created_at
    period_end = user.last_crawl_at or datetime.now(timezone.utc)
    duration_hours = (period_end - period_start).total_seconds() / 3600.0

    # Build period 0
    period = AnalysisPeriodRow(
        id=str(uuid4()),
        entity_type="user",
        entity_id=user.id,
        period_number=0,
        period_start=period_start,
        period_end=period_end,
        analyzed_at=period_end,
        duration_hours=duration_hours,
        content_count=len(content_list),
        status="active",
        summary=user.last_summary or "Legacy period - migrated from pre-temporal schema",
        summary_short=None,
        insights=user.summary_data.get("insights", {}) if user.summary_data else {},
        metrics=user.summary_data.get("metrics", {}) if user.summary_data else {},
        metrics_delta={},  # First period has no delta
        tasks_dispatched=[],
        tasks_summary={},
        chat_summary=None,
        knowledge_version=1,
        knowledge_doc=None,
        knowledge_diff=None,
        quality_score=None,
        completeness_score=None,
        execution_log={
            "migration": "period_zero",
            "migrated_at": datetime.now(timezone.utc).isoformat(),
            "note": "Backfilled from existing data"
        },
    )

    if dry_run:
        print(f"  🔍 [DRY RUN] Would create Period 0 for user '{user.name}':")
        print(f"     - Period: {period_start} → {period_end} ({duration_hours:.1f}h)")
        print(f"     - Contents: {len(content_list)}")
        return True

    # Create period
    session.add(period)

    # Update user to link to this period
    user.current_period_number = 0
    user.last_period_id = period.id
    user.total_periods = 1
    user.first_analysis_at = period.analyzed_at
    user.avg_period_duration_hours = duration_hours

    # Update all contents to link to this period
    for content in content_list:
        content.analysis_period_id = period.id
        content.discovered_at = content.crawled_at

    print(f"  ✅ Created Period 0 for user '{user.name}':")
    print(f"     - Period: {period_start} → {period_end} ({duration_hours:.1f}h)")
    print(f"     - Contents: {len(content_list)}")

    return True


async def migrate_period_zero(db_url: str, dry_run: bool = False):
    """Main migration function."""

    print("=" * 80)
    print("Period 0 Data Migration")
    print("=" * 80)
    print(f"Database: {db_url}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will commit)'}")
    print()

    # Create async engine
    engine = create_async_engine(db_url, echo=False)
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session_maker() as session:
            # Process topics
            print("📊 Processing Topics...")
            print("-" * 80)

            topics = await session.scalars(select(TopicRow).where(TopicRow.status == "active"))
            topic_list = list(topics)

            print(f"Found {len(topic_list)} active topics")
            print()

            topics_migrated = 0
            for topic in topic_list:
                if await create_period_zero_for_topic(session, topic, dry_run):
                    topics_migrated += 1

            print()
            print(f"Topics migrated: {topics_migrated}/{len(topic_list)}")
            print()

            # Process users
            print("👤 Processing Users...")
            print("-" * 80)

            users = await session.scalars(select(UserRow).where(UserRow.status == "active"))
            user_list = list(users)

            print(f"Found {len(user_list)} active users")
            print()

            users_migrated = 0
            for user in user_list:
                if await create_period_zero_for_user(session, user, dry_run):
                    users_migrated += 1

            print()
            print(f"Users migrated: {users_migrated}/{len(user_list)}")
            print()

            # Commit or rollback
            if dry_run:
                print("🔍 DRY RUN - Rolling back (no changes committed)")
                await session.rollback()
            else:
                print("💾 Committing changes...")
                await session.commit()
                print("✅ Migration complete!")

            print()
            print("=" * 80)
            print("Summary")
            print("=" * 80)
            print(f"Topics migrated: {topics_migrated}/{len(topic_list)}")
            print(f"Users migrated: {users_migrated}/{len(user_list)}")
            print(f"Total periods created: {topics_migrated + users_migrated}")

    finally:
        await engine.dispose()


def main():
    parser = argparse.ArgumentParser(
        description="Initialize Period 0 for existing topics and users"
    )
    parser.add_argument(
        "--db-url",
        default="postgresql+asyncpg://crosshot:crosshot@localhost:5432/crosshot",
        help="Database URL (default: from env or localhost)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no commits)",
    )

    args = parser.parse_args()

    # Get DB URL from environment if not specified
    import os
    db_url = os.getenv("DATABASE_URL", args.db_url)

    # Ensure asyncpg driver
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    try:
        asyncio.run(migrate_period_zero(db_url, args.dry_run))
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

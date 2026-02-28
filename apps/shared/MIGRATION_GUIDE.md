# Temporal Schema Migration Guide

## Overview

This migration adds a complete temporal context management system to Crosshot AI, enabling the Analyst agent to maintain long-term memory, track analysis periods, and make data-driven decisions based on historical trends.

## Migration Files

1. **20260301_0100_create_temporal_tables.py** - Creates new temporal tables:
   - `analysis_periods` - Complete analysis cycle records (central timeline spine)
   - `period_content_snapshots` - Junction table linking contents to periods
   - `temporal_events` - Significant events tracked across periods
   - `event_contents` - Junction table linking events to contents
   - `crawl_effectiveness` - Crawl query effectiveness tracking

2. **20260301_0200_alter_existing_tables.py** - Adds temporal context fields to existing tables:
   - `topics` - Adds period tracking fields
   - `users` - Adds period tracking fields
   - `contents` - Adds analysis period linkage and relevance scoring
   - `tasks` - Adds period and effectiveness tracking
   - `chat_messages` - Adds period linkage

3. **20260301_0300_create_views_and_functions.py** - Creates database views and functions:
   - Views: `v_period_timeline`, `v_entity_timeline_summary`, `v_crawl_effectiveness_ranking`
   - Materialized view: `mv_period_metrics_trend`
   - Functions: `get_period_by_number()`, `get_content_timeline()`, `detect_metric_anomalies()`, `recompute_metrics_delta()`

## Running the Migration

### Prerequisites

1. Ensure PostgreSQL 14+ is running
2. Ensure the database user has privileges to create extensions
3. Backup your database before migrating

### Migration Steps

```bash
# Navigate to the shared package
cd /Users/minyic/git/crosshot-ai/apps/shared

# Set the DATABASE_URL environment variable (or use alembic.ini default)
export DATABASE_URL="postgresql://crosshot:crosshot@localhost:5432/crosshot"

# Check current migration status
uv run alembic current

# Review what will be upgraded
uv run alembic upgrade head --sql > preview_migration.sql
cat preview_migration.sql  # Review the SQL

# Run the migration
uv run alembic upgrade head

# Verify migration succeeded
uv run alembic current
```

### Docker Environment

If running in Docker:

```bash
# Enter the api container (or any container with database access)
docker compose exec api bash

# Inside the container
cd /app
export DATABASE_URL="postgresql://crosshot:crosshot@postgres:5432/crosshot"
uv run --package shared alembic upgrade head
```

### Rollback (if needed)

```bash
# Rollback all three migrations
uv run alembic downgrade -1  # Removes views/functions
uv run alembic downgrade -1  # Removes altered columns
uv run alembic downgrade -1  # Removes temporal tables

# Or rollback to a specific revision
uv run alembic downgrade 20260301_0100  # Keep only the first migration
```

## Post-Migration Steps

### 1. Verify Schema

```sql
-- Check that all tables were created
SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '%period%';

-- Check extensions
SELECT * FROM pg_extension WHERE extname IN ('btree_gist', 'pg_trgm');

-- Check views
SELECT viewname FROM pg_views WHERE schemaname = 'public';

-- Check materialized views
SELECT matviewname FROM pg_matviews WHERE schemaname = 'public';
```

### 2. Initialize Period 0 for Existing Entities

For existing topics/users that have data but no periods yet, run this data migration:

```sql
-- Create Period 0 for existing topics (optional - can be done lazily)
INSERT INTO analysis_periods (
    entity_type, entity_id, period_number,
    period_start, period_end, analyzed_at,
    duration_hours, content_count,
    summary, insights, metrics
)
SELECT
    'topic' AS entity_type,
    t.id AS entity_id,
    0 AS period_number,
    t.created_at AS period_start,
    COALESCE(t.last_crawl_at, NOW()) AS period_end,
    COALESCE(t.last_crawl_at, NOW()) AS analyzed_at,
    EXTRACT(EPOCH FROM (COALESCE(t.last_crawl_at, NOW()) - t.created_at)) / 3600.0 AS duration_hours,
    t.total_contents AS content_count,
    COALESCE(t.last_summary, 'Legacy period - no summary available') AS summary,
    '{}'::jsonb AS insights,
    '{}'::jsonb AS metrics
FROM topics t
WHERE t.total_contents > 0
  AND NOT EXISTS (
      SELECT 1 FROM analysis_periods ap
      WHERE ap.entity_type = 'topic' AND ap.entity_id = t.id
  );

-- Update topics to link to their period 0
UPDATE topics t
SET
    current_period_number = 0,
    last_period_id = ap.id,
    total_periods = 1,
    first_analysis_at = ap.analyzed_at
FROM analysis_periods ap
WHERE ap.entity_type = 'topic'
  AND ap.entity_id = t.id
  AND ap.period_number = 0
  AND t.current_period_number IS NULL;

-- Repeat for users
-- (similar SQL as above but with entity_type = 'user')
```

### 3. Refresh Materialized View

The materialized view needs manual refresh:

```sql
REFRESH MATERIALIZED VIEW mv_period_metrics_trend;
```

Set up a cron job or periodic task to refresh it:

```sql
-- In your application code or cron:
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_period_metrics_trend;
```

## Schema Changes Summary

### New Tables (5)

- `analysis_periods` - 25 columns, 6 indexes, 3 check constraints, 1 exclusion constraint
- `period_content_snapshots` - 8 columns, 3 indexes, 1 check constraint
- `temporal_events` - 14 columns, 4 indexes, 2 check constraints
- `event_contents` - 4 columns (2 PKs), 1 check constraint
- `crawl_effectiveness` - 15 columns, 5 indexes, 4 check constraints

### Modified Tables (5)

- `topics` - Added 5 columns (current_period_number, last_period_id, total_periods, first_analysis_at, avg_period_duration_hours)
- `users` - Added 5 columns (same as topics)
- `contents` - Added 4 columns (analysis_period_id, published_at, discovered_at, relevance_score)
- `tasks` - Added 3 columns (period_id, effectiveness_id, duration_seconds)
- `chat_messages` - Added 1 column (period_id)

### Views & Functions

- 3 regular views
- 1 materialized view with index
- 4 PostgreSQL functions (PL/pgSQL)

## Troubleshooting

### Extension Not Found

If you get errors about `btree_gist` or `pg_trgm`:

```sql
-- Ensure you have superuser or rds_superuser role
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
```

### Foreign Key Violations

If you get FK violations during migration, ensure:
1. There are no orphaned records in your current database
2. All referenced IDs exist in parent tables

### Performance Issues

If the migration is slow on large datasets:
1. Consider running it during low-traffic periods
2. The exclusion constraint on `analysis_periods` requires GIST index which can be slow on first build
3. Materialized view refresh can be deferred to after migration

## Next Steps

After successful migration:

1. **Update Application Code** - Modify analyst executor to use the new period-based system
2. **Create Temporal Tools** - Implement query_period_timeline, compare_periods, etc.
3. **Test Period Creation** - Run a full analysis cycle and verify period records are created
4. **Monitor Performance** - Watch query performance on the new indexes
5. **Set Up MV Refresh** - Schedule regular REFRESH of mv_period_metrics_trend

## Architecture Benefits

With this migration complete:

- ✅ Analyst has complete historical context
- ✅ Can query any time range of contents/summaries
- ✅ Track metric trends and detect anomalies
- ✅ Evaluate crawl effectiveness over time
- ✅ Support for re-running analysis (soft deletes via status + superseded_by)
- ✅ Debugging capability via execution_log
- ✅ Event lifecycle tracking (detection → resolution)
- ✅ Proper soft deletes (no data loss on re-analysis)

## References

- **Plan Document**: `/Users/minyic/.claude/plans/twinkling-snacking-pretzel.md`
- **Models File**: `apps/shared/shared/db/models.py`
- **Migration Files**: `apps/shared/alembic/versions/`

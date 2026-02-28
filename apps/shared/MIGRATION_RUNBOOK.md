# Temporal Schema Migration Runbook

## Pre-Migration Checklist

- [ ] Database backup completed
- [ ] All services stopped (or read-only mode)
- [ ] PostgreSQL 14+ confirmed
- [ ] Superuser or extension creation privileges confirmed
- [ ] Estimated downtime window communicated

## Step 1: Backup Database

```bash
# On NAS
SSHPASS='1041420051Yi@' sshpass -e ssh minyic@192.168.0.190

# Inside NAS
docker compose exec -T postgres pg_dump -U crosshot -Fc crosshot > /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/backups/pre_temporal_$(date +%Y%m%d_%H%M%S).dump

# Verify backup exists and has size
ls -lh /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/backups/
```

**Estimated time:** 1-5 minutes depending on database size

## Step 2: Stop Services (Optional but Recommended)

```bash
# On NAS
cd /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai
docker compose stop api crawler analyst

# Keep postgres and redis running
docker compose ps
```

**Why?** Prevents new data writes during migration. Can skip if you're comfortable with in-flight transactions.

## Step 3: Run Schema Migrations

```bash
# On NAS, inside the API container (which has alembic)
docker compose run --rm api bash

# Inside container
cd /app
export DATABASE_URL="postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot"

# Check current state (should show no revisions)
uv run --package shared alembic current

# Preview what will be applied
uv run --package shared alembic upgrade head --sql | head -50

# Apply migrations
uv run --package shared alembic upgrade head

# Verify all three migrations applied
uv run --package shared alembic current
# Should show: 20260301_0300 (head)

exit
```

**Estimated time:** 2-10 seconds (schema-only DDL, no data movement)

**What gets created:**
- ✅ Extensions: btree_gist, pg_trgm
- ✅ Tables: analysis_periods, period_content_snapshots, temporal_events, event_contents, crawl_effectiveness
- ✅ New columns on: topics, users, contents, tasks, chat_messages
- ✅ Views: v_period_timeline, v_entity_timeline_summary, v_crawl_effectiveness_ranking
- ✅ Materialized view: mv_period_metrics_trend
- ✅ Functions: get_period_by_number, get_content_timeline, detect_metric_anomalies, recompute_metrics_delta

## Step 4: Verify Schema

```bash
# On NAS
docker compose exec -T postgres psql -U crosshot -d crosshot <<SQL
-- Check tables created
SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '%period%';

-- Check extensions
SELECT extname, extversion FROM pg_extension WHERE extname IN ('btree_gist', 'pg_trgm');

-- Check views
SELECT viewname FROM pg_views WHERE schemaname = 'public';

-- Check materialized views
SELECT matviewname FROM pg_matviews WHERE schemaname = 'public';

-- Check new columns on topics
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'topics' AND column_name LIKE '%period%';
SQL
```

**Expected output:**
- 4 tables with "period" in name
- 2 extensions (btree_gist, pg_trgm)
- 3 regular views
- 1 materialized view
- 5 new columns on topics (current_period_number, last_period_id, total_periods, first_analysis_at, avg_period_duration_hours)

## Step 5: Backfill Period 0 Data

```bash
# Copy migration script to NAS (from local machine)
scp /Users/minyic/git/crosshot-ai/apps/shared/scripts/migrate_period_zero.py minyic@192.168.0.190:/share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/

# On NAS, run inside API container
docker compose run --rm api bash

# Inside container
cd /app
export DATABASE_URL="postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot"

# DRY RUN first to see what will happen
python /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/migrate_period_zero.py --dry-run

# Review output, then run for real
python /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/migrate_period_zero.py

exit
```

**Estimated time:** 1-30 seconds depending on number of topics/users and contents

**What it does:**
- Creates Period 0 for each topic/user that has contents
- Links all existing contents to their Period 0
- Populates period tracking fields on topics/users
- Preserves existing summary_data as insights/metrics

**Example output:**
```
📊 Processing Topics...
Found 5 active topics
  ✅ Created Period 0 for topic 'AI Safety Research':
     - Period: 2025-01-15 → 2025-02-28 (1056.5h)
     - Contents: 247
  ⏭️  Topic 'Climate Tech' has no contents, skipping

Topics migrated: 3/5
```

## Step 6: Verify Data Migration

```bash
docker compose exec -T postgres psql -U crosshot -d crosshot <<SQL
-- Check period 0 created for topics
SELECT
    t.name,
    t.current_period_number,
    t.total_periods,
    ap.period_number,
    ap.content_count,
    ap.duration_hours,
    ap.status
FROM topics t
LEFT JOIN analysis_periods ap ON t.last_period_id = ap.id
WHERE t.status = 'active'
ORDER BY t.name;

-- Check contents linked to periods
SELECT
    ap.entity_type,
    COUNT(*) as linked_contents
FROM contents c
JOIN analysis_periods ap ON c.analysis_period_id = ap.id
GROUP BY ap.entity_type;

-- Check for orphaned contents (should be 0 or only very recent)
SELECT COUNT(*) as orphaned_contents
FROM contents c
WHERE c.analysis_period_id IS NULL;
SQL
```

**Expected:**
- All active topics/users with contents should have current_period_number = 0
- All existing contents should be linked to a period (analysis_period_id NOT NULL)
- Orphaned contents should be 0 (or only brand new ones created during migration)

## Step 7: Refresh Materialized View

```bash
docker compose exec -T postgres psql -U crosshot -d crosshot <<SQL
-- Initial refresh
REFRESH MATERIALIZED VIEW mv_period_metrics_trend;

-- Verify data
SELECT COUNT(*) FROM mv_period_metrics_trend;
SQL
```

## Step 8: Restart Services

```bash
# On NAS
cd /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai
docker compose up -d

# Verify all services started
docker compose ps

# Check logs for errors
docker compose logs --tail=50 api
docker compose logs --tail=50 analyst
docker compose logs --tail=50 crawler
```

## Step 9: Smoke Test

```bash
# Test API endpoints still work
curl http://192.168.0.190:8000/api/topics

# Check that topics still render correctly
# (Open web UI and verify dashboard loads)

# Check database connections
docker compose logs api | grep -i "database\|postgres"
```

## Step 10: Monitor

Watch for:
- ✅ API requests completing successfully
- ✅ Analyst agent creating new periods (after next analysis cycle)
- ✅ No FK violation errors in logs
- ✅ Query performance normal

```bash
# Watch logs in real-time
docker compose logs -f api analyst crawler

# Check for errors
docker compose logs --since 10m | grep -i error
```

## Rollback Procedure (If Needed)

### Option A: Rollback Migrations (Preferred if no data written yet)

```bash
# On NAS, inside API container
docker compose run --rm api bash

cd /app
export DATABASE_URL="postgresql+asyncpg://crossoft:crossoft@postgres:5432/crossoft"

# Rollback all three migrations
uv run --package shared alembic downgrade -3

# Or rollback to specific revision
uv run --package shared alembic downgrade base

exit
```

### Option B: Restore from Backup (If data corruption or severe issues)

```bash
# On NAS
docker compose stop

# Drop and recreate database
docker compose exec -T postgres psql -U postgres <<SQL
DROP DATABASE crosshot;
CREATE DATABASE crosshot OWNER crosshot;
SQL

# Restore from backup
docker compose exec -T postgres pg_restore -U crosshot -d crosshot < /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai/backups/pre_temporal_YYYYMMDD_HHMMSS.dump

# Restart services
docker compose up -d
```

**Estimated time:** 2-10 minutes depending on backup size

## Post-Migration Validation

Run these queries to confirm everything worked:

```sql
-- 1. Check schema version
SELECT version_num FROM alembic_version;
-- Should be: 20260301_0300

-- 2. Count periods created
SELECT entity_type, COUNT(*)
FROM analysis_periods
WHERE status = 'active'
GROUP BY entity_type;

-- 3. Check period coverage
SELECT
    COUNT(DISTINCT c.topic_id) as topics_with_content,
    COUNT(DISTINCT ap.entity_id) as topics_with_periods
FROM contents c
LEFT JOIN analysis_periods ap ON ap.entity_id = c.topic_id AND ap.entity_type = 'topic'
WHERE c.topic_id IS NOT NULL;
-- Should be equal

-- 4. Verify no overlapping periods (exclusion constraint working)
SELECT entity_type, entity_id, COUNT(*)
FROM analysis_periods
WHERE status = 'active'
GROUP BY entity_type, entity_id
HAVING COUNT(*) > 1;
-- Should return 0 rows

-- 5. Check index usage (after some queries run)
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
WHERE tablename IN ('analysis_periods', 'period_content_snapshots', 'temporal_events')
ORDER BY idx_scan DESC;
```

## Common Issues

### Issue: Extensions not created

**Error:** `ERROR: type "gist" does not exist`

**Fix:**
```sql
-- Connect as superuser
\c crosshot postgres
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
\c crosshot crosshot
```

### Issue: Foreign key violations during data migration

**Error:** `ERROR: insert or update on table "period_content_snapshots" violates foreign key constraint`

**Cause:** Some contents reference deleted topics/users

**Fix:**
```sql
-- Find orphaned contents
SELECT id, topic_id, user_id FROM contents
WHERE (topic_id IS NOT NULL AND topic_id NOT IN (SELECT id FROM topics))
   OR (user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users));

-- Delete orphaned contents (or set FKs to NULL)
DELETE FROM contents
WHERE (topic_id IS NOT NULL AND topic_id NOT IN (SELECT id FROM topics))
   OR (user_id IS NOT NULL AND user_id NOT IN (SELECT id FROM users));
```

### Issue: Migration script can't connect

**Error:** `OSError: [Errno 61] Connection refused`

**Fix:** Use the correct DATABASE_URL for Docker network:
```bash
# From inside Docker container
export DATABASE_URL="postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot"

# From host machine (if postgres port is exposed)
export DATABASE_URL="postgresql+asyncpg://crosshot:crosshot@localhost:5433/crosshot"
```

### Issue: Materialized view refresh slow

**Error:** None, but `REFRESH MATERIALIZED VIEW` hangs

**Cause:** Large dataset, blocking all concurrent access

**Fix:**
```sql
-- Use CONCURRENTLY (requires unique index)
CREATE UNIQUE INDEX mv_period_metrics_trend_unique
ON mv_period_metrics_trend (entity_type, entity_id, period_number);

REFRESH MATERIALIZED VIEW CONCURRENTLY mv_period_metrics_trend;
```

## Performance Monitoring

After migration, monitor these metrics:

```sql
-- Table sizes
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public' AND tablename LIKE '%period%'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- Index usage (should be high for period queries)
SELECT
    schemaname, tablename, indexname,
    idx_scan, idx_tup_read, idx_tup_fetch,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE tablename IN ('analysis_periods', 'period_content_snapshots')
ORDER BY idx_scan DESC;

-- Slow queries (enable pg_stat_statements first)
SELECT
    query,
    calls,
    mean_exec_time,
    total_exec_time
FROM pg_stat_statements
WHERE query LIKE '%analysis_period%'
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Next Steps After Migration

1. **Update Analyst Executor** - Modify to create new periods on each analysis
2. **Implement Temporal Tools** - Add query_period_timeline, compare_periods, etc.
3. **Schedule MV Refresh** - Set up cron to refresh mv_period_metrics_trend daily
4. **Monitor Period Creation** - Verify new periods get created on analysis cycles
5. **Test Re-analysis** - Verify soft delete (superseded_by) works correctly

## Maintenance

### Daily

```bash
# Refresh materialized view
docker compose exec -T postgres psql -U crosshot -d crosshot -c "REFRESH MATERIALIZED VIEW mv_period_metrics_trend;"
```

### Weekly

```sql
-- Check for stale periods (draft status > 1 day old)
SELECT entity_type, entity_id, period_number, status, created_at
FROM analysis_periods
WHERE status = 'draft' AND created_at < NOW() - INTERVAL '1 day';

-- Check for unresolved events
SELECT entity_type, entity_id, event_type, title, first_detected_at
FROM temporal_events
WHERE resolved_at IS NULL
ORDER BY first_detected_at DESC;
```

### Monthly

```sql
-- Archive old superseded periods (optional)
UPDATE analysis_periods
SET status = 'archived'
WHERE status = 'superseded'
  AND created_at < NOW() - INTERVAL '90 days';

-- Vacuum analyze new tables
VACUUM ANALYZE analysis_periods;
VACUUM ANALYZE period_content_snapshots;
VACUUM ANALYZE temporal_events;
```

## Success Criteria

Migration is successful when:

- ✅ All three Alembic migrations applied (version = 20260301_0300)
- ✅ Period 0 created for all topics/users with contents
- ✅ All existing contents linked to periods (orphaned = 0)
- ✅ Views and functions queryable
- ✅ API endpoints still work
- ✅ No FK violation errors in logs
- ✅ Dashboard loads and displays correctly
- ✅ Next analysis cycle creates Period 1 (after analyst executor updated)

## Estimated Total Time

- **Small database** (<1000 contents): 5-10 minutes
- **Medium database** (1000-10000 contents): 10-20 minutes
- **Large database** (>10000 contents): 20-40 minutes

Most time is spent in:
1. Backup/restore (if needed)
2. Data migration script (proportional to content count)
3. Testing and validation

**Actual DDL migration is fast** (< 10 seconds) because it's schema-only.

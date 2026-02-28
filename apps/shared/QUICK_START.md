# Quick Start: Temporal Schema Migration

## TL;DR - Production Migration (NAS)

```bash
# 1. Pull latest code
cd /share/CACHEDEV1_DATA/minyic-volumn/crosshot-ai
git pull

# 2. Backup database
docker compose exec -T postgres pg_dump -U crosshot -Fc crosshot > backups/pre_temporal_$(date +%Y%m%d_%H%M%S).dump

# 3. Run schema migrations
docker compose run --rm api bash -c "cd /app && DATABASE_URL=postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot uv run --package shared alembic upgrade head"

# 4. Backfill Period 0 data
docker compose run --rm api python /app/apps/shared/scripts/migrate_period_zero.py

# 5. Refresh materialized view
docker compose exec -T postgres psql -U crosshot -d crosshot -c "REFRESH MATERIALIZED VIEW mv_period_metrics_trend;"

# 6. Restart services
docker compose restart

# Done! ✅
```

## Dry Run First (Recommended)

```bash
# Preview schema migration SQL
docker compose run --rm api bash -c "cd /app && DATABASE_URL=postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot uv run --package shared alembic upgrade head --sql | less"

# Preview data migration
docker compose run --rm api python /app/apps/shared/scripts/migrate_period_zero.py --dry-run
```

## Verification

```bash
# Check migration version
docker compose exec -T postgres psql -U crosshot -d crosshot -c "SELECT version_num FROM alembic_version;"
# Should show: 20260301_0300

# Check Period 0 created
docker compose exec -T postgres psql -U crosshot -d crosshot -c "SELECT entity_type, COUNT(*) FROM analysis_periods WHERE period_number = 0 GROUP BY entity_type;"

# Check contents linked
docker compose exec -T postgres psql -U crosshot -d crosshot -c "SELECT COUNT(*) as total, COUNT(analysis_period_id) as linked FROM contents;"
```

## Rollback (If Needed)

```bash
# Rollback migrations
docker compose run --rm api bash -c "cd /app && DATABASE_URL=postgresql+asyncpg://crosshot:crosshot@postgres:5432/crosshot uv run --package shared alembic downgrade -3"

# Or restore from backup
docker compose exec -T postgres pg_restore -U crosshot -d crosshot -c < backups/pre_temporal_YYYYMMDD_HHMMSS.dump
```

## What Gets Created

**5 New Tables:**
- `analysis_periods` - Central timeline (Period 0, 1, 2, ...)
- `period_content_snapshots` - Which contents belong to which period
- `temporal_events` - Track controversies, trends (detection → resolution)
- `event_contents` - Which contents relate to which events
- `crawl_effectiveness` - Learn which queries work best

**Modified Tables:**
- `topics`, `users` - Added period tracking fields
- `contents` - Added `analysis_period_id`, `published_at`, `discovered_at`, `relevance_score`
- `tasks` - Added `period_id`, `effectiveness_id`, `duration_seconds`
- `chat_messages` - Added `period_id`

**Views & Functions:**
- 3 views for timeline queries
- 1 materialized view for trend analysis
- 4 PostgreSQL functions for temporal queries

## Expected Timeline

- Schema migration: **< 10 seconds**
- Data migration: **10-60 seconds** (depends on # of contents)
- Verification: **5 seconds**

**Total: 30-90 seconds of downtime** (or zero if run without stopping services)

## Troubleshooting

### "No module named 'shared'"

Wrong directory. Run from inside Docker container with `/app` in PYTHONPATH.

### "Connection refused"

Wrong DATABASE_URL. Use `postgres` as hostname inside Docker, not `localhost`.

### "Extension 'btree_gist' does not exist"

Connect as superuser:
```bash
docker compose exec -T postgres psql -U postgres -d crosshot -c "CREATE EXTENSION btree_gist; CREATE EXTENSION pg_trgm;"
```

### Migration hangs

Check for blocking queries:
```sql
SELECT pid, query, state, wait_event FROM pg_stat_activity WHERE datname = 'crosshot';
```

## Full Documentation

- **[MIGRATION_RUNBOOK.md](./MIGRATION_RUNBOOK.md)** - Complete step-by-step procedure
- **[MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md)** - Migration details and context
- **[TEMPORAL_SCHEMA.md](./TEMPORAL_SCHEMA.md)** - Architecture and design

## After Migration

Next steps to complete temporal context system:

1. ✅ Schema migrated
2. ✅ Period 0 backfilled
3. ⏳ Implement temporal tools (query_period_timeline, compare_periods, etc.)
4. ⏳ Update analyst executor to create periods on each analysis
5. ⏳ Test full analysis cycle with Period 1 creation
6. ⏳ Schedule daily MV refresh

See plan at `/Users/minyic/.claude/plans/twinkling-snacking-pretzel.md`

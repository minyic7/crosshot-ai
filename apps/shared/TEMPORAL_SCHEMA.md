# Temporal Context Management Schema

## Overview

The temporal schema enables the Analyst agent to maintain long-term memory and make data-driven decisions based on historical trends. This is a complete transformation from the previous "snapshot-only" approach to a full time-series architecture.

## Core Concept: Analysis Periods

Every analysis cycle creates an **Analysis Period** record that serves as a complete snapshot of that moment in time. Think of it as a save point in a video game - you can always go back and see exactly what the system knew at any point.

### Key Features

1. **Complete Timeline** - Every analysis is saved with its full context
2. **Queryable History** - Agent can ask "what did we know 3 weeks ago?"
3. **Trend Detection** - Compare metrics across periods to spot anomalies
4. **Soft Deletes** - Re-running analysis creates new period, preserves old one
5. **Effectiveness Learning** - Track which crawl queries work best over time
6. **Event Lifecycle** - Track controversies/trends from detection to resolution

## Schema Architecture

### Central Table: `analysis_periods`

The timeline spine. Every analysis cycle creates one row here.

```
┌─────────────────────────────────────────┐
│       analysis_periods                  │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ entity_type: 'topic' | 'user'          │
│ entity_id → topics.id or users.id      │
│ period_number (1, 2, 3...)             │
│ period_start, period_end               │
│ analyzed_at                             │
│ status: active | superseded | ...       │
│ superseded_by → self (for re-runs)     │
│ summary, summary_short                  │
│ insights JSONB                          │
│ metrics JSONB (follower_count, ...)    │
│ metrics_delta JSONB (computed)          │
│ tasks_dispatched UUID[]                 │
│ knowledge_doc TEXT (compressed)         │
│ execution_log JSONB (debugging)         │
│ quality_score, completeness_score       │
└─────────────────────────────────────────┘
```

**Key Constraints:**
- **Unique period numbers** (per entity, only one active period per number)
- **No overlapping periods** (GIST exclusion constraint)
- **Soft delete chain** (superseded_by creates audit trail)

### Junction Tables

#### `period_content_snapshots`

Links contents to periods + preserves snapshot at analysis time:

```
period_id + content_id + text_snapshot + relevance_score
```

**Why snapshot?** Content might be edited/deleted later, but we preserve what we analyzed.

**Covering index** for fast queries: `(period_id, relevance_score DESC) INCLUDE (content_id, text_snapshot)`

#### `event_contents`

Links events to related contents:

```
event_id + content_id + relevance_to_event
```

Proper junction table (not UUID array) for FK cascade protection.

### Event Tracking: `temporal_events`

Track significant events across their lifecycle:

```
┌─────────────────────────────────────────┐
│       temporal_events                   │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ period_id → analysis_periods.id         │
│ entity_type, entity_id                  │
│ event_type: 'controversy' | 'trend' ... │
│ severity: info | warning | critical     │
│ title, description                      │
│ first_detected_at                       │
│ last_updated_at                         │
│ resolved_at (NULL = still active)       │
│ resolution_note                         │
│ event_metadata JSONB                    │
└─────────────────────────────────────────┘
```

**Lifecycle:**
1. Analyst detects event (e.g., "controversy around AI safety")
2. Event stays active, updated in subsequent periods
3. When resolved, `resolved_at` set + `resolution_note` added
4. Query unresolved events: `WHERE resolved_at IS NULL`

### Effectiveness Tracking: `crawl_effectiveness`

Learn which crawl queries work best:

```
┌─────────────────────────────────────────┐
│       crawl_effectiveness               │
├─────────────────────────────────────────┤
│ id (PK)                                 │
│ period_id → analysis_periods.id         │
│ entity_type, entity_id                  │
│ platform: 'x' | 'xhs' ...              │
│ query TEXT (e.g., "min_faves:50 AI")   │
│ total_found, relevant_count             │
│ high_value_count                        │
│ effectiveness_score (0-1)               │
│ avg_relevance (0-1)                     │
│ recommendations TEXT                    │
└─────────────────────────────────────────┘
```

**Use case:** Analyst sees "query X has 80% effectiveness, query Y only 20%" → prioritize query X next time.

**Trigram index** on `query` for fuzzy matching API syntax.

## Modified Existing Tables

### `topics` and `users` (entity tables)

Added period tracking:

```sql
current_period_number INTEGER       -- Currently on period 5
last_period_id UUID → analysis_periods.id
total_periods INTEGER               -- Created 5 periods total
first_analysis_at TIMESTAMPTZ
avg_period_duration_hours FLOAT
```

### `contents`

Added temporal context:

```sql
analysis_period_id UUID → analysis_periods.id  -- Which period processed this
published_at TIMESTAMPTZ            -- Original publish time
discovered_at TIMESTAMPTZ           -- When we crawled it
relevance_score FLOAT               -- LLM-assigned relevance
```

### `tasks`

Added period linkage:

```sql
period_id UUID → analysis_periods.id
effectiveness_id UUID → crawl_effectiveness.id
duration_seconds FLOAT
```

### `chat_messages`

Added period linkage:

```sql
period_id UUID → analysis_periods.id  -- Which period was this chat during?
```

## Views & Functions

### Regular Views

1. **`v_period_timeline`** - Clean timeline view with unresolved event counts
2. **`v_entity_timeline_summary`** - Per-entity stats (total periods, avg quality, etc.)
3. **`v_crawl_effectiveness_ranking`** - Rank queries by effectiveness with moving average

### Materialized View

**`mv_period_metrics_trend`** - Pre-computed metrics with LAG() for trend comparison

```sql
SELECT period_number, metrics, prev_metrics, prev_prev_metrics
FROM mv_period_metrics_trend
WHERE entity_type = 'topic' AND entity_id = ...
```

**Refresh:** Manual only (not auto-refresh to avoid blocking writes)

### Functions

1. **`get_period_by_number(entity_type, entity_id, period_number)`**
   - Quick lookup: "Get period 3 for topic X"

2. **`get_content_timeline(entity_type, entity_id, start_time, end_time, min_relevance)`**
   - Query: "Show all high-relevance content from last 2 weeks"

3. **`detect_metric_anomalies(entity_type, entity_id, metric_key, threshold_factor)`**
   - Statistical anomaly detection (Z-score based)
   - Example: "follower_count jumped 3 standard deviations"

4. **`recompute_metrics_delta(period_id)`**
   - Recompute delta between current and previous period
   - Useful after manual corrections

## Indexes Strategy

### Why These Indexes?

1. **Partial indexes** (`WHERE entity_type = 'topic'`)
   - Polymorphic pattern: one table for topics + users
   - Separate indexes for each type = faster queries

2. **Covering indexes** (`INCLUDE (col1, col2)`)
   - Index-only scans (no table lookup needed)
   - Critical for period_content_snapshots (hot path)

3. **Expression indexes** (`relevance_score DESC NULLS LAST`)
   - Pre-sorted for "top N" queries
   - Analyst frequently asks "show top 10 relevant posts"

4. **Trigram indexes** (`query gin_trgm_ops`)
   - Fuzzy matching for crawl query text
   - API syntax is variable, need similarity search

5. **GIST exclusion constraint**
   - Prevents overlapping periods at database level
   - Can't be done with normal CHECK constraint

## Data Flow Example

### Creating a New Analysis Period

```python
# 1. Analyst starts analysis
period = AnalysisPeriodRow(
    entity_type='topic',
    entity_id=topic_id,
    period_number=topic.current_period_number + 1,
    period_start=last_period.period_end,  # Continue from last period
    period_end=datetime.now(timezone.utc),
    duration_hours=24.0,
    status='draft'  # Draft until complete
)

# 2. Process contents
for content in unprocessed_contents:
    snapshot = PeriodContentSnapshotRow(
        period_id=period.id,
        content_id=content.id,
        relevance_score=llm_classify(content),
        text_snapshot=content.text[:500],  # Preserve snapshot
        contribution_type='key_finding'
    )
    # Also update content.analysis_period_id = period.id

# 3. Generate summary
period.summary = llm_summarize(snapshots)
period.insights = llm_extract_insights(snapshots)
period.metrics = compute_metrics(topic)
period.metrics_delta = compute_delta(period.metrics, prev_period.metrics)

# 4. Detect events
if controversy_detected:
    event = TemporalEventRow(
        period_id=period.id,
        event_type='controversy',
        severity='warning',
        title='Debate over AI safety standards',
        description=...,
        first_detected_at=datetime.now(timezone.utc)
    )

# 5. Track crawl effectiveness
for task in completed_tasks:
    effectiveness = CrawlEffectivenessRow(
        period_id=period.id,
        platform='x',
        query=task.query,
        total_found=task.result['count'],
        relevant_count=len([c for c in contents if c.relevance_score >= 0.7]),
        effectiveness_score=relevant_count / total_found
    )

# 6. Finalize period
period.status = 'active'
topic.last_period_id = period.id
topic.current_period_number = period.period_number
topic.total_periods += 1
```

### Re-running Analysis (Soft Delete)

```python
# User clicks "Re-analyze" because LLM made a mistake

# 1. Mark old period as superseded
old_period.status = 'superseded'
old_period.supersession_reason = 'User requested re-analysis due to LLM error'

# 2. Create new period with same period_number
new_period = AnalysisPeriodRow(
    entity_type=old_period.entity_type,
    entity_id=old_period.entity_id,
    period_number=old_period.period_number,  # Same number!
    period_start=old_period.period_start,
    period_end=old_period.period_end,
    status='active'
)

# 3. Link via supersession chain
old_period.superseded_by = new_period.id

# 4. Re-run analysis with new LLM call
# ... (same steps as above)

# Now: old analysis preserved for audit, new one is active
# Query: WHERE status = 'active' → gets new one
# Audit: WHERE superseded_by IS NOT NULL → see old ones
```

## Query Patterns

### "Show me the last 5 periods for this topic"

```python
periods = session.scalars(
    select(AnalysisPeriodRow)
    .where(
        AnalysisPeriodRow.entity_type == 'topic',
        AnalysisPeriodRow.entity_id == topic_id,
        AnalysisPeriodRow.status == 'active'
    )
    .order_by(AnalysisPeriodRow.period_number.desc())
    .limit(5)
).all()
```

### "What were the top posts from 2 weeks ago?"

```python
contents = session.execute(
    select(func.get_content_timeline(
        'topic',
        topic_id,
        datetime.now() - timedelta(weeks=2),
        datetime.now() - timedelta(weeks=2, days=-1),
        0.7  # min_relevance
    ))
).all()
```

### "Has follower_count spiked abnormally?"

```python
anomalies = session.execute(
    select(func.detect_metric_anomalies(
        'topic',
        topic_id,
        'follower_count',
        2.0  # 2 standard deviations
    ))
).all()
```

### "Which crawl queries work best?"

```python
best_queries = session.scalars(
    select(CrawlEffectivenessRow)
    .where(
        CrawlEffectivenessRow.entity_type == 'topic',
        CrawlEffectivenessRow.entity_id == topic_id
    )
    .order_by(CrawlEffectivenessRow.effectiveness_score.desc())
    .limit(10)
).all()
```

## Production Considerations

### Storage

- **knowledge_doc**: Compressed with pglz (can be 10KB+ of text)
- **Arrays**: Only for bounded data (tasks_dispatched max ~10 items)
- **No arrays for unbounded**: contents use junction table instead

### Performance

- **Hot path**: period_content_snapshots queries → covering index critical
- **Materialized view**: Refresh during low-traffic windows
- **Partial indexes**: Separate topic/user indexes for polymorphic pattern

### Operational

- **Soft deletes**: Never lose data on re-analysis
- **execution_log**: JSONB for debugging 3AM failures
- **Supersession chain**: Full audit trail of re-runs
- **Status transitions**: draft → active | failed | archived

### Monitoring

```sql
-- Check period creation rate
SELECT DATE_TRUNC('day', analyzed_at), COUNT(*)
FROM analysis_periods
WHERE status = 'active'
GROUP BY 1
ORDER BY 1 DESC;

-- Check quality scores
SELECT AVG(quality_score), AVG(completeness_score)
FROM analysis_periods
WHERE status = 'active' AND analyzed_at > NOW() - INTERVAL '7 days';

-- Check unresolved events
SELECT entity_type, entity_id, COUNT(*)
FROM temporal_events
WHERE resolved_at IS NULL
GROUP BY 1, 2
ORDER BY 3 DESC;
```

## Migration Path

See [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) for complete instructions.

**Key points:**
1. Migrations are split into 3 files for clean rollback
2. Backward compatible (existing code still works)
3. Can initialize Period 0 for existing entities lazily
4. Extensions (btree_gist, pg_trgm) auto-created

## Next Steps

After schema is deployed:

1. **Implement Temporal Tools** (for Analyst ReAct loop)
   - `query_period_timeline(entity_type, entity_id, limit=10)`
   - `query_contents_by_timerange(start, end, min_relevance)`
   - `compare_periods(period_id_1, period_id_2)`
   - `get_unresolved_events(entity_type, entity_id)`

2. **Modify Analyst Executor**
   - Inject period context into system prompt
   - Save complete period record after summarize
   - Track events lifecycle
   - Record crawl effectiveness

3. **Update API Endpoints** (optional for Phase 5)
   - `GET /api/topics/{id}/periods` - Timeline view
   - `GET /api/topics/{id}/events` - Event history
   - `GET /api/topics/{id}/effectiveness` - Query performance

4. **Frontend Enhancements** (optional)
   - Period timeline visualization
   - Metric trend charts
   - Event lifecycle tracking

## Design Rationale

### Why not just expand summary_data JSONB?

- **Queryability**: Can't efficiently query "all periods where follower_count > 1000"
- **Referential integrity**: JSONB can't have FKs to contents
- **Soft deletes**: Can't supersede a JSONB field
- **Indexing**: Can't create partial/covering indexes on JSONB structure

### Why period-based instead of event-sourcing?

- **Bounded context**: Each period is self-contained
- **Simpler queries**: "Get period N" vs "replay events 1-100"
- **Better UX**: Users think in time ranges, not event streams
- **Analyst friendly**: LLM can reason about "periods" more naturally

### Why separate tables for events/effectiveness?

- **Lifecycle tracking**: Events resolve over time, need proper status management
- **Learning feedback**: Effectiveness scores feed back into query planning
- **Clear domains**: Period = analysis snapshot, Event = significant occurrence, Effectiveness = operational metric

## Summary

This schema transforms the Analyst from a stateless summarizer into a **temporal reasoning agent** that:

- ✅ Remembers complete history
- ✅ Compares trends across time
- ✅ Learns which strategies work
- ✅ Tracks events from detection to resolution
- ✅ Supports re-analysis without data loss
- ✅ Provides rich debugging context

All while maintaining backward compatibility and preserving the existing API contract.

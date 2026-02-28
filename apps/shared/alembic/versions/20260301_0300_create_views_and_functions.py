"""Create views, materialized views, and functions for temporal queries

Revision ID: 20260301_0300
Revises: 20260301_0200
Create Date: 2026-03-01 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '20260301_0300'
down_revision: Union[str, None] = '20260301_0200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create v_period_timeline view
    op.execute("""
        CREATE VIEW v_period_timeline AS
        SELECT
            ap.id,
            ap.entity_type,
            ap.entity_id,
            ap.period_number,
            ap.period_start,
            ap.period_end,
            ap.analyzed_at,
            ap.duration_hours,
            ap.status,
            ap.content_count,
            ap.summary_short,
            ap.insights,
            ap.metrics,
            ap.metrics_delta,
            ap.quality_score,
            ap.completeness_score,
            (
                SELECT COUNT(*)
                FROM temporal_events te
                WHERE te.period_id = ap.id AND te.resolved_at IS NULL
            ) AS unresolved_event_count,
            (
                SELECT COUNT(*)
                FROM crawl_effectiveness ce
                WHERE ce.period_id = ap.id
            ) AS crawl_task_count
        FROM analysis_periods ap
        WHERE ap.status = 'active'
        ORDER BY ap.entity_type, ap.entity_id, ap.period_number DESC;
    """)

    # Create v_entity_timeline_summary view
    op.execute("""
        CREATE VIEW v_entity_timeline_summary AS
        SELECT
            entity_type,
            entity_id,
            COUNT(*) AS total_periods,
            MIN(period_start) AS first_period_start,
            MAX(period_end) AS last_period_end,
            AVG(duration_hours) AS avg_period_duration,
            SUM(content_count) AS total_content_across_periods,
            AVG(quality_score) AS avg_quality_score,
            AVG(completeness_score) AS avg_completeness_score
        FROM analysis_periods
        WHERE status = 'active'
        GROUP BY entity_type, entity_id;
    """)

    # Create v_crawl_effectiveness_ranking view
    op.execute("""
        CREATE VIEW v_crawl_effectiveness_ranking AS
        SELECT
            ce.entity_type,
            ce.entity_id,
            ce.platform,
            ce.query,
            ce.effectiveness_score,
            ce.total_found,
            ce.relevant_count,
            ce.high_value_count,
            ce.avg_relevance,
            ce.created_at,
            (
                SELECT AVG(sub.effectiveness_score)
                FROM (
                    SELECT effectiveness_score
                    FROM crawl_effectiveness ce2
                    WHERE ce2.entity_type = ce.entity_type
                      AND ce2.entity_id = ce.entity_id
                      AND ce2.platform = ce.platform
                    ORDER BY ce2.created_at DESC
                    LIMIT 3
                ) sub
            ) AS recent_avg_effectiveness
        FROM crawl_effectiveness ce
        ORDER BY ce.effectiveness_score DESC NULLS LAST;
    """)

    # Create materialized view mv_period_metrics_trend
    op.execute("""
        CREATE MATERIALIZED VIEW mv_period_metrics_trend AS
        SELECT
            ap.entity_type,
            ap.entity_id,
            ap.period_number,
            ap.analyzed_at,
            ap.metrics,
            ap.metrics_delta,
            LAG(ap.metrics, 1) OVER (
                PARTITION BY ap.entity_type, ap.entity_id
                ORDER BY ap.period_number
            ) AS prev_metrics,
            LAG(ap.metrics, 2) OVER (
                PARTITION BY ap.entity_type, ap.entity_id
                ORDER BY ap.period_number
            ) AS prev_prev_metrics
        FROM analysis_periods ap
        WHERE ap.status = 'active'
        ORDER BY ap.entity_type, ap.entity_id, ap.period_number;
    """)

    # Create index on materialized view
    op.create_index(
        'idx_mv_period_metrics_entity',
        'mv_period_metrics_trend',
        ['entity_type', 'entity_id', 'period_number']
    )

    # Create get_period_by_number function
    op.execute("""
        CREATE OR REPLACE FUNCTION get_period_by_number(
            p_entity_type VARCHAR(20),
            p_entity_id UUID,
            p_period_number INTEGER
        ) RETURNS SETOF analysis_periods AS $$
        BEGIN
            RETURN QUERY
            SELECT *
            FROM analysis_periods
            WHERE entity_type = p_entity_type
              AND entity_id = p_entity_id
              AND period_number = p_period_number
              AND status = 'active'
            LIMIT 1;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Create get_content_timeline function
    op.execute("""
        CREATE OR REPLACE FUNCTION get_content_timeline(
            p_entity_type VARCHAR(20),
            p_entity_id UUID,
            p_start_time TIMESTAMPTZ DEFAULT NULL,
            p_end_time TIMESTAMPTZ DEFAULT NULL,
            p_min_relevance DOUBLE PRECISION DEFAULT 0.0
        ) RETURNS TABLE (
            content_id UUID,
            period_id UUID,
            period_number INTEGER,
            contribution_type VARCHAR(32),
            relevance_score DOUBLE PRECISION,
            text_snapshot TEXT,
            period_start TIMESTAMPTZ,
            period_end TIMESTAMPTZ
        ) AS $$
        BEGIN
            RETURN QUERY
            SELECT
                pcs.content_id,
                pcs.period_id,
                ap.period_number,
                pcs.contribution_type,
                pcs.relevance_score,
                pcs.text_snapshot,
                ap.period_start,
                ap.period_end
            FROM period_content_snapshots pcs
            JOIN analysis_periods ap ON pcs.period_id = ap.id
            WHERE ap.entity_type = p_entity_type
              AND ap.entity_id = p_entity_id
              AND ap.status = 'active'
              AND (p_start_time IS NULL OR ap.period_start >= p_start_time)
              AND (p_end_time IS NULL OR ap.period_end <= p_end_time)
              AND (pcs.relevance_score IS NULL OR pcs.relevance_score >= p_min_relevance)
            ORDER BY ap.period_number DESC, pcs.relevance_score DESC NULLS LAST;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Create detect_metric_anomalies function
    op.execute("""
        CREATE OR REPLACE FUNCTION detect_metric_anomalies(
            p_entity_type VARCHAR(20),
            p_entity_id UUID,
            p_metric_key TEXT,
            p_threshold_factor DOUBLE PRECISION DEFAULT 2.0
        ) RETURNS TABLE (
            period_id UUID,
            period_number INTEGER,
            metric_value DOUBLE PRECISION,
            avg_value DOUBLE PRECISION,
            stddev_value DOUBLE PRECISION,
            z_score DOUBLE PRECISION
        ) AS $$
        BEGIN
            RETURN QUERY
            WITH stats AS (
                SELECT
                    AVG((metrics->>p_metric_key)::DOUBLE PRECISION) AS mean_val,
                    STDDEV((metrics->>p_metric_key)::DOUBLE PRECISION) AS stddev_val
                FROM analysis_periods
                WHERE entity_type = p_entity_type
                  AND entity_id = p_entity_id
                  AND status = 'active'
                  AND metrics ? p_metric_key
            )
            SELECT
                ap.id AS period_id,
                ap.period_number,
                (ap.metrics->>p_metric_key)::DOUBLE PRECISION AS metric_value,
                s.mean_val AS avg_value,
                s.stddev_val AS stddev_value,
                CASE
                    WHEN s.stddev_val > 0 THEN
                        ((ap.metrics->>p_metric_key)::DOUBLE PRECISION - s.mean_val) / s.stddev_val
                    ELSE 0
                END AS z_score
            FROM analysis_periods ap, stats s
            WHERE ap.entity_type = p_entity_type
              AND ap.entity_id = p_entity_id
              AND ap.status = 'active'
              AND ap.metrics ? p_metric_key
              AND s.stddev_val > 0
              AND ABS(((ap.metrics->>p_metric_key)::DOUBLE PRECISION - s.mean_val) / s.stddev_val) > p_threshold_factor
            ORDER BY ap.period_number DESC;
        END;
        $$ LANGUAGE plpgsql STABLE;
    """)

    # Create recompute_metrics_delta function
    op.execute("""
        CREATE OR REPLACE FUNCTION recompute_metrics_delta(p_period_id UUID)
        RETURNS JSONB AS $$
        DECLARE
            v_current_metrics JSONB;
            v_prev_metrics JSONB;
            v_delta JSONB;
            v_entity_type VARCHAR(20);
            v_entity_id UUID;
            v_period_number INTEGER;
        BEGIN
            -- Get current period info
            SELECT entity_type, entity_id, period_number, metrics
            INTO v_entity_type, v_entity_id, v_period_number, v_current_metrics
            FROM analysis_periods
            WHERE id = p_period_id AND status = 'active';

            IF NOT FOUND THEN
                RETURN NULL;
            END IF;

            -- Get previous period metrics
            SELECT metrics INTO v_prev_metrics
            FROM analysis_periods
            WHERE entity_type = v_entity_type
              AND entity_id = v_entity_id
              AND period_number = v_period_number - 1
              AND status = 'active';

            -- Compute delta (this is a simple implementation, can be extended)
            IF v_prev_metrics IS NOT NULL THEN
                v_delta := jsonb_build_object(
                    'computed_at', NOW(),
                    'prev_period_number', v_period_number - 1,
                    'note', 'Delta computation requires custom logic per metric'
                );
            ELSE
                v_delta := jsonb_build_object(
                    'note', 'First period, no previous data for delta'
                );
            END IF;

            -- Update the period
            UPDATE analysis_periods
            SET metrics_delta = v_delta,
                updated_at = NOW()
            WHERE id = p_period_id;

            RETURN v_delta;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS recompute_metrics_delta(UUID)")
    op.execute("DROP FUNCTION IF EXISTS detect_metric_anomalies(VARCHAR, UUID, TEXT, DOUBLE PRECISION)")
    op.execute("DROP FUNCTION IF EXISTS get_content_timeline(VARCHAR, UUID, TIMESTAMPTZ, TIMESTAMPTZ, DOUBLE PRECISION)")
    op.execute("DROP FUNCTION IF EXISTS get_period_by_number(VARCHAR, UUID, INTEGER)")

    # Drop materialized view
    op.execute("DROP MATERIALIZED VIEW IF EXISTS mv_period_metrics_trend")

    # Drop views
    op.execute("DROP VIEW IF EXISTS v_crawl_effectiveness_ranking")
    op.execute("DROP VIEW IF EXISTS v_entity_timeline_summary")
    op.execute("DROP VIEW IF EXISTS v_period_timeline")

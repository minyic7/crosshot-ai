"""Tool: save_snapshot — query period-based metrics history for trend analysis."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import AnalysisPeriodRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_snapshot_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the save_snapshot tool (queries period-based metrics history)."""

    async def save_snapshot(
        entity_type: str,
        entity_id: str,
        metrics: dict,
    ) -> str:
        """Save current metrics. Returns recent trend from past periods for comparison."""
        async with session_factory() as session:
            # Query recent periods for trend context
            result = await session.execute(
                select(AnalysisPeriodRow)
                .where(
                    AnalysisPeriodRow.entity_type == entity_type,
                    AnalysisPeriodRow.entity_id == entity_id,
                    AnalysisPeriodRow.status == "active",
                )
                .order_by(AnalysisPeriodRow.period_number.desc())
                .limit(5)
            )
            rows = result.scalars().all()

            trend = [
                {
                    "period": r.period_number,
                    "analyzed_at": r.analyzed_at.isoformat(),
                    "metrics": r.metrics,
                    "content_count": r.content_count,
                }
                for r in rows
            ]

            logger.info(
                "Metrics snapshot for %s %s (current: %s, %d past periods)",
                entity_type, entity_id, list(metrics.keys()), len(trend),
            )
            return json.dumps({
                "status": "recorded",
                "current_metrics": metrics,
                "trend": trend,
                "note": "Metrics will be persisted when the analysis period is saved.",
            }, ensure_ascii=False)

    return Tool(
        name="save_snapshot",
        description=(
            "Record current metrics and view historical trends across past periods. "
            "Call after integration to compare metrics over time."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["topic", "user"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the topic or user",
                },
                "metrics": {
                    "type": "object",
                    "description": "Metrics to record (from get_overview)",
                },
            },
            "required": ["entity_type", "entity_id", "metrics"],
        },
        func=save_snapshot,
    )

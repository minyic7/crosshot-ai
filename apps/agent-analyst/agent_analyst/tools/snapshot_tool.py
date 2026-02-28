"""Tool: save_snapshot — capture metric snapshots for trend analysis."""

import json
import logging

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import MetricSnapshotRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_snapshot_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the save_snapshot tool."""

    async def save_snapshot(
        entity_type: str,
        entity_id: str,
        metrics: dict,
    ) -> str:
        """Save current metrics as a time-series snapshot for trend analysis."""
        async with session_factory() as session:
            snapshot = MetricSnapshotRow(
                entity_type=entity_type,
                entity_id=entity_id,
                metrics=metrics,
            )
            session.add(snapshot)
            await session.commit()

            logger.info("Saved metric snapshot for %s %s", entity_type, entity_id)
            return json.dumps({
                "status": "saved",
                "snapshot_id": str(snapshot.id),
            }, ensure_ascii=False)

    async def query_snapshots(
        entity_type: str,
        entity_id: str,
        limit: int = 10,
    ) -> str:
        """Query recent metric snapshots for trend comparison."""
        async with session_factory() as session:
            result = await session.execute(
                select(MetricSnapshotRow)
                .where(
                    MetricSnapshotRow.entity_type == entity_type,
                    MetricSnapshotRow.entity_id == entity_id,
                )
                .order_by(MetricSnapshotRow.captured_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

            snapshots = [
                {
                    "captured_at": r.captured_at.isoformat(),
                    "metrics": r.metrics,
                }
                for r in rows
            ]
            return json.dumps(snapshots, ensure_ascii=False)

    return Tool(
        name="save_snapshot",
        description=(
            "Save current metrics as a time-series snapshot. "
            "Call after integration to track metric trends over time."
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
                    "description": "Metrics to snapshot (from get_overview)",
                },
            },
            "required": ["entity_type", "entity_id", "metrics"],
        },
        func=save_snapshot,
    )

"""Analysis periods API — timeline of analysis history per entity."""

import logging

from fastapi import APIRouter

from shared.db.engine import get_session_factory
from shared.db.models import AnalysisPeriodRow
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(tags=["periods"])


@router.get("/topics/{topic_id}/periods")
async def get_topic_periods(
    topic_id: str, status: str = "active", limit: int = 20,
) -> dict:
    """Get analysis periods for a topic."""
    return await _get_periods("topic", topic_id, status, limit)


@router.get("/users/{user_id}/periods")
async def get_user_periods(
    user_id: str, status: str = "active", limit: int = 20,
) -> dict:
    """Get analysis periods for a user."""
    return await _get_periods("user", user_id, status, limit)


async def _get_periods(
    entity_type: str, entity_id: str, status: str, limit: int,
) -> dict:
    """Query analysis periods for an entity."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(AnalysisPeriodRow)
            .where(
                AnalysisPeriodRow.entity_type == entity_type,
                AnalysisPeriodRow.entity_id == entity_id,
            )
            .order_by(AnalysisPeriodRow.period_number.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(AnalysisPeriodRow.status == status)

        result = await session.execute(stmt)
        rows = result.scalars().all()

        return {
            "periods": [
                {
                    "id": str(r.id),
                    "period_number": r.period_number,
                    "period_start": r.period_start.isoformat(),
                    "period_end": r.period_end.isoformat(),
                    "analyzed_at": r.analyzed_at.isoformat(),
                    "duration_hours": r.duration_hours,
                    "status": r.status,
                    "content_count": r.content_count,
                    "summary": r.summary,
                    "summary_short": r.summary_short,
                    "insights": r.insights,
                    "metrics": r.metrics,
                    "metrics_delta": r.metrics_delta,
                    "quality_score": r.quality_score,
                    "knowledge_version": r.knowledge_version,
                }
                for r in rows
            ],
            "total": len(rows),
        }

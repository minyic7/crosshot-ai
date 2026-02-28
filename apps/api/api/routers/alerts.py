"""Alerts API — query and manage proactive alerts from analyst."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from shared.db.engine import get_session_factory
from shared.db.models import AlertRow
from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alerts"])


class AlertResponse(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    level: str
    message: str
    created_at: str
    resolved_at: str | None = None


@router.get("/topics/{topic_id}/alerts")
async def get_topic_alerts(topic_id: str, resolved: bool = False) -> list[AlertResponse]:
    """Get alerts for a topic."""
    return await _get_alerts("topic", topic_id, resolved)


@router.get("/users/{user_id}/alerts")
async def get_user_alerts(user_id: str, resolved: bool = False) -> list[AlertResponse]:
    """Get alerts for a user."""
    return await _get_alerts("user", user_id, resolved)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str) -> dict:
    """Mark an alert as resolved."""
    factory = get_session_factory()
    async with factory() as session:
        alert = await session.get(AlertRow, alert_id)
        if not alert:
            return {"error": "Alert not found"}
        alert.resolved_at = datetime.now(timezone.utc)
        await session.commit()
        return {"status": "resolved", "alert_id": alert_id}


async def _get_alerts(
    entity_type: str, entity_id: str, include_resolved: bool,
) -> list[AlertResponse]:
    """Query alerts for an entity."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(AlertRow)
            .where(
                AlertRow.entity_type == entity_type,
                AlertRow.entity_id == entity_id,
            )
            .order_by(AlertRow.created_at.desc())
            .limit(50)
        )
        if not include_resolved:
            stmt = stmt.where(AlertRow.resolved_at.is_(None))

        result = await session.execute(stmt)
        rows = result.scalars().all()

        return [
            AlertResponse(
                id=str(r.id),
                entity_type=r.entity_type,
                entity_id=str(r.entity_id),
                level=r.level,
                message=r.message,
                created_at=r.created_at.isoformat(),
                resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
            )
            for r in rows
        ]

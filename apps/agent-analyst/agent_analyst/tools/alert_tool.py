"""Tool: create_alert — track significant events via temporal_events table."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TemporalEventRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_alert_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the create_alert tool (backed by temporal_events)."""

    async def create_alert(
        entity_type: str,
        entity_id: str,
        level: str,
        message: str,
        event_type: str = "anomaly",
    ) -> str:
        """Create an alert for a notable event or anomaly.

        Levels: info, warning, critical
        Event types: anomaly, controversy, trend_shift, milestone, risk
        """
        now = datetime.now(timezone.utc)
        async with session_factory() as session:
            row = TemporalEventRow(
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                severity=level,
                title=message[:256],
                description=message,
                first_detected_at=now,
                last_updated_at=now,
            )
            session.add(row)
            await session.commit()

            logger.info(
                "Event [%s/%s] for %s %s: %s",
                level, event_type, entity_type, entity_id, message[:80],
            )
            return json.dumps({
                "status": "created",
                "event_id": str(row.id),
                "severity": level,
                "event_type": event_type,
            }, ensure_ascii=False)

    return Tool(
        name="create_alert",
        description=(
            "Create an alert for anomalies, significant changes, or notable events. "
            "Events are tracked across analysis periods with lifecycle management. "
            "Use sparingly — only for genuinely notable situations."
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
                "level": {
                    "type": "string",
                    "enum": ["info", "warning", "critical"],
                    "description": "Alert severity level",
                },
                "message": {
                    "type": "string",
                    "description": "Alert message (Chinese preferred)",
                },
                "event_type": {
                    "type": "string",
                    "enum": ["anomaly", "controversy", "trend_shift", "milestone", "risk"],
                    "description": "Type of event",
                    "default": "anomaly",
                },
            },
            "required": ["entity_type", "entity_id", "level", "message"],
        },
        func=create_alert,
    )

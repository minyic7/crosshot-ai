"""Tool: create_alert — proactive alerts for anomalies and notable events."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import AlertRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_alert_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the create_alert tool."""

    async def create_alert(
        entity_type: str,
        entity_id: str,
        level: str,
        message: str,
    ) -> str:
        """Create an alert for a notable event or anomaly.

        Levels: info, warning, critical
        """
        async with session_factory() as session:
            row = AlertRow(
                entity_type=entity_type,
                entity_id=entity_id,
                level=level,
                message=message,
            )
            session.add(row)
            await session.commit()

            logger.info(
                "Alert [%s] for %s %s: %s",
                level, entity_type, entity_id, message[:80],
            )
            return json.dumps({
                "status": "created",
                "alert_id": str(row.id),
                "level": level,
            }, ensure_ascii=False)

    return Tool(
        name="create_alert",
        description=(
            "Create a proactive alert for anomalies, significant changes, or notable events. "
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
            },
            "required": ["entity_type", "entity_id", "level", "message"],
        },
        func=create_alert,
    )

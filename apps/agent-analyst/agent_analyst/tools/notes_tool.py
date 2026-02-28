"""Tool: save_note — persistent analyst notes tracked as temporal events."""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TemporalEventRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)

# Map note categories to temporal event types
_CATEGORY_TO_EVENT_TYPE = {
    "observation": "observation",
    "trend": "trend_shift",
    "anomaly": "anomaly",
    "strategy": "milestone",
    "follow_up": "risk",
}


def make_notes_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the save_note tool (backed by temporal_events)."""

    async def save_note(
        entity_type: str,
        entity_id: str,
        note: str,
        category: str = "observation",
    ) -> str:
        """Save an analysis note as a temporal event. Notes persist across periods.

        Categories: observation, trend, anomaly, strategy, follow_up
        """
        now = datetime.now(timezone.utc)
        event_type = _CATEGORY_TO_EVENT_TYPE.get(category, "observation")

        async with session_factory() as session:
            row = TemporalEventRow(
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                severity="info",
                title=note[:256],
                description=note,
                first_detected_at=now,
                last_updated_at=now,
                event_metadata={"category": category, "source": "analyst_note"},
            )
            session.add(row)
            await session.commit()

            logger.info(
                "Saved note [%s] for %s %s: %s",
                category, entity_type, entity_id, note[:80],
            )
            return json.dumps({
                "status": "saved",
                "event_id": str(row.id),
                "category": category,
            }, ensure_ascii=False)

    return Tool(
        name="save_note",
        description=(
            "Save a persistent analysis note. Notes are tracked as temporal events "
            "and persist across analysis periods. Use for observations, trends, "
            "anomalies, or follow-up items."
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
                "note": {
                    "type": "string",
                    "description": "The analysis note (Chinese preferred)",
                },
                "category": {
                    "type": "string",
                    "enum": ["observation", "trend", "anomaly", "strategy", "follow_up"],
                    "description": "Note category",
                    "default": "observation",
                },
            },
            "required": ["entity_type", "entity_id", "note"],
        },
        func=save_note,
    )

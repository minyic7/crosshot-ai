"""Tool: save_note — persistent analyst notes that survive summary rewrites."""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import AnalysisNoteRow
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


def make_notes_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the save_note tool."""

    async def save_note(
        entity_type: str,
        entity_id: str,
        note: str,
        category: str = "observation",
    ) -> str:
        """Save an analysis note. Notes persist across summary rewrites.

        Categories: observation, trend, anomaly, strategy, follow_up
        """
        async with session_factory() as session:
            row = AnalysisNoteRow(
                entity_type=entity_type,
                entity_id=entity_id,
                note=note,
                category=category,
            )
            session.add(row)
            await session.commit()

            logger.info(
                "Saved note [%s] for %s %s: %s",
                category, entity_type, entity_id, note[:80],
            )
            return json.dumps({
                "status": "saved",
                "note_id": str(row.id),
                "category": category,
            }, ensure_ascii=False)

    return Tool(
        name="save_note",
        description=(
            "Save a persistent analysis note. Notes survive summary rewrites "
            "and build long-term memory. Use for observations, trends, anomalies, "
            "or follow-up items."
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

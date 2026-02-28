"""Tool: get_overview — query entity metrics and data status."""

import json

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.tools.base import Tool

from agent_analyst.tools.query import query_entity_overview
from agent_analyst.tools.topic import get_entity_config


def make_overview_tool(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Create the get_overview tool."""

    async def get_overview(entity_type: str, entity_id: str) -> str:
        """Get entity config, metrics, and data status."""
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id
        )
        if "error" in entity:
            return json.dumps(entity, ensure_ascii=False)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        # Merge entity info + overview for a complete picture
        result = {
            "entity": {
                "type": entity.get("type", entity_type),
                "id": entity_id,
                "name": entity.get("name"),
                "platforms": entity.get("platforms", []),
                "keywords": entity.get("keywords", []),
                "users": entity.get("users", []),
                "config": entity.get("config", {}),
            },
            "overview": overview,
            "knowledge_doc": _get_knowledge_doc(entity),
        }
        return json.dumps(result, ensure_ascii=False, default=str)

    return Tool(
        name="get_overview",
        description=(
            "Get entity configuration, metrics, and data status. "
            "Call this first to understand the current state before deciding what to do."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["topic", "user"],
                    "description": "Type of entity to query",
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the topic or user",
                },
            },
            "required": ["entity_type", "entity_id"],
        },
        func=get_overview,
    )


def _get_knowledge_doc(entity: dict) -> str:
    """Extract knowledge document from entity's summary_data."""
    summary_data = entity.get("summary_data") or {}
    if isinstance(summary_data, dict):
        return summary_data.get("knowledge", "")
    return ""

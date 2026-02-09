"""get_topic_config tool — reads topic details + previous recommendations from PG."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow
from shared.tools.base import Tool


def make_get_topic_config(session_factory: async_sessionmaker[AsyncSession]) -> Tool:
    """Factory: create tool that reads topic config from PG."""

    async def _get_topic_config(topic_id: str) -> dict:
        async with session_factory() as session:
            topic = await session.get(TopicRow, topic_id)
            if topic is None:
                return {"error": f"Topic {topic_id} not found"}

            # Extract previous recommendations from last cycle's summary_data
            previous_recommendations = []
            if topic.summary_data and isinstance(topic.summary_data, dict):
                previous_recommendations = topic.summary_data.get(
                    "recommended_next_queries", []
                )

            return {
                "id": str(topic.id),
                "name": topic.name,
                "description": topic.description,
                "platforms": topic.platforms,
                "keywords": topic.keywords,
                "config": topic.config,
                "status": topic.status,
                "total_contents": topic.total_contents,
                "previous_recommendations": previous_recommendations,
            }

    return Tool(
        name="get_topic_config",
        description=(
            "Get the configuration and details for a monitoring topic, "
            "including recommended queries from the previous analysis cycle."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "The topic UUID",
                },
            },
            "required": ["topic_id"],
        },
        func=_get_topic_config,
    )

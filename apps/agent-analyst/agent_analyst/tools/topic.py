"""get_topic_config — reads topic details + previous recommendations from PG."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow


async def get_topic_config(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str,
) -> dict:
    """Read topic config from PG."""
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

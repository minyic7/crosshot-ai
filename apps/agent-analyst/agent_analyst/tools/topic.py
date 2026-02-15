"""get_topic_config / get_entity_config — reads topic or user details from PG."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from shared.db.models import TopicRow, UserRow


async def get_topic_config(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str,
) -> dict:
    """Read topic config from PG (legacy — wraps get_entity_config)."""
    return await get_entity_config(session_factory, topic_id=topic_id)


async def get_entity_config(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Read topic or user config from PG, including attached users for topics."""
    async with session_factory() as session:
        if topic_id:
            from sqlalchemy import select

            stmt = (
                select(TopicRow)
                .where(TopicRow.id == topic_id)
                .options(selectinload(TopicRow.users))
            )
            result = await session.execute(stmt)
            topic = result.scalar_one_or_none()
            if topic is None:
                return {"error": f"Topic {topic_id} not found"}

            # Extract previous recommendations from last cycle's summary_data
            previous_recommendations = []
            if topic.summary_data and isinstance(topic.summary_data, dict):
                previous_recommendations = topic.summary_data.get(
                    "recommended_next_queries", []
                )

            # Attached users
            users = [
                {
                    "user_id": str(u.id),
                    "name": u.name,
                    "platform": u.platform,
                    "username": u.username,
                    "profile_url": u.profile_url,
                    "config": u.config,
                    "last_crawl_at": u.last_crawl_at.isoformat() if u.last_crawl_at else None,
                }
                for u in topic.users
            ]

            return {
                "type": "topic",
                "id": str(topic.id),
                "name": topic.name,
                "description": topic.description,
                "platforms": topic.platforms,
                "keywords": topic.keywords,
                "config": topic.config,
                "status": topic.status,
                "total_contents": topic.total_contents,
                "previous_recommendations": previous_recommendations,
                "summary_data": topic.summary_data,
                "last_summary": topic.last_summary,
                "users": users,
            }

        elif user_id:
            user = await session.get(UserRow, user_id)
            if user is None:
                return {"error": f"User {user_id} not found"}

            previous_recommendations = []
            if user.summary_data and isinstance(user.summary_data, dict):
                previous_recommendations = user.summary_data.get(
                    "recommended_next_queries", []
                )

            return {
                "type": "user",
                "id": str(user.id),
                "name": user.name,
                "platform": user.platform,
                "profile_url": user.profile_url,
                "username": user.username,
                "config": user.config,
                "status": user.status,
                "total_contents": user.total_contents,
                "previous_recommendations": previous_recommendations,
                "summary_data": user.summary_data,
                "last_summary": user.last_summary,
                "platforms": [user.platform],
                "keywords": [],
                "users": [],
            }

        return {"error": "Must provide either topic_id or user_id"}

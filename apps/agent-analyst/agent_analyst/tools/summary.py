"""update_topic_summary / update_entity_summary — writes analysis results to PostgreSQL."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow, UserRow


async def update_topic_summary(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str,
    summary: str,
    summary_data: dict | None = None,
    total_contents: int | None = None,
    is_preliminary: bool = False,
) -> dict:
    """Save analysis summary for a topic (legacy — wraps update_entity_summary)."""
    return await update_entity_summary(
        session_factory,
        topic_id=topic_id,
        summary=summary,
        summary_data=summary_data,
        total_contents=total_contents,
        is_preliminary=is_preliminary,
    )


async def update_entity_summary(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
    summary: str = "",
    summary_data: dict | None = None,
    total_contents: int | None = None,
    is_preliminary: bool = False,
) -> dict:
    """Save analysis summary and structured insights for a topic or user."""
    async with session_factory() as session:
        if topic_id:
            entity = await session.get(TopicRow, topic_id)
            if entity is None:
                return {"error": f"Topic {topic_id} not found"}
            entity_key = "topic_id"
            entity_val = topic_id
        elif user_id:
            entity = await session.get(UserRow, user_id)
            if entity is None:
                return {"error": f"User {user_id} not found"}
            entity_key = "user_id"
            entity_val = user_id
        else:
            return {"error": "Must provide either topic_id or user_id"}

        entity.last_summary = summary
        if summary_data is not None:
            entity.summary_data = summary_data
        if total_contents is not None:
            entity.total_contents = total_contents
        if not is_preliminary:
            entity.last_crawl_at = datetime.now(timezone.utc)
        entity.updated_at = datetime.now(timezone.utc)

        await session.commit()
        return {"status": "ok", entity_key: entity_val}

"""update_topic_summary — writes analysis results to PostgreSQL."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow


async def update_topic_summary(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str,
    summary: str,
    summary_data: dict | None = None,
    total_contents: int | None = None,
    is_preliminary: bool = False,
) -> dict:
    """Save analysis summary and structured insights for a topic."""
    async with session_factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": f"Topic {topic_id} not found"}

        topic.last_summary = summary
        if summary_data is not None:
            topic.summary_data = summary_data
        if total_contents is not None:
            topic.total_contents = total_contents
        # Only update last_crawl_at for final reports (not preliminary)
        if not is_preliminary:
            topic.last_crawl_at = datetime.now(timezone.utc)
        topic.updated_at = datetime.now(timezone.utc)

        await session.commit()
        return {"status": "ok", "topic_id": topic_id}

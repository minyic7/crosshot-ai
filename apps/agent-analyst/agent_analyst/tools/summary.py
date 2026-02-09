"""update_topic_summary tool — writes analysis results to PostgreSQL."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow
from shared.tools.base import Tool


def make_update_topic_summary(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Factory: create tool that writes topic summary to PG."""

    async def _update_topic_summary(
        topic_id: str,
        summary: str,
        summary_data: dict | None = None,
        total_contents: int | None = None,
    ) -> dict:
        async with session_factory() as session:
            topic = await session.get(TopicRow, topic_id)
            if topic is None:
                return {"error": f"Topic {topic_id} not found"}

            topic.last_summary = summary
            if summary_data is not None:
                topic.summary_data = summary_data
            if total_contents is not None:
                topic.total_contents = total_contents
            topic.last_crawl_at = datetime.now(timezone.utc)
            topic.updated_at = datetime.now(timezone.utc)

            await session.commit()
            return {"status": "ok", "topic_id": topic_id}

    return Tool(
        name="update_topic_summary",
        description=(
            "Save the analysis summary and structured insights for a topic. "
            "Include recommended_next_queries in summary_data for the next cycle."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "The topic UUID",
                },
                "summary": {
                    "type": "string",
                    "description": "Human-readable summary text (2-3 paragraphs)",
                },
                "summary_data": {
                    "type": "object",
                    "description": (
                        "Structured insights: {metrics, alerts, recommended_next_queries}"
                    ),
                },
                "total_contents": {
                    "type": "integer",
                    "description": "Total number of content items analyzed",
                },
            },
            "required": ["topic_id", "summary"],
        },
        func=_update_topic_summary,
    )

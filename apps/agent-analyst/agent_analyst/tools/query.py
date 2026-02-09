"""query_topic_contents tool — reads content collected for a topic from Redis."""

import json

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.tools.base import Tool


def make_query_topic_contents(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: aioredis.Redis,
) -> Tool:
    """Factory: create tool that queries content for a topic."""

    async def _query_topic_contents(
        topic_id: str,
        platform: str | None = None,
        limit: int = 50,
    ) -> dict:
        # Read content IDs accumulated by coordinator
        content_ids = await redis_client.lrange(
            f"topic:{topic_id}:content_ids", 0, -1
        )

        contents = []
        for cid in content_ids[:limit]:
            raw = await redis_client.get(f"content:{cid}")
            if not raw:
                continue
            content = json.loads(raw)

            # Platform filter
            if platform and content.get("platform") != platform:
                continue

            data = content.get("data", {})
            media = data.get("media", [])
            contents.append(
                {
                    "id": content.get("id"),
                    "platform": content.get("platform"),
                    "source_url": content.get("source_url"),
                    "text": data.get("text", ""),
                    "author": data.get("author", {}).get("display_name", ""),
                    "author_username": data.get("author", {}).get("username", ""),
                    "metrics": data.get("metrics", {}),
                    "has_media": len(media) > 0,
                    "media_types": list({m.get("type") for m in media if m.get("type")}),
                    "hashtags": data.get("hashtags", []),
                    "crawled_at": content.get("crawled_at"),
                }
            )

        return {
            "topic_id": topic_id,
            "total_available": len(content_ids),
            "returned": len(contents),
            "contents": contents,
        }

    return Tool(
        name="query_topic_contents",
        description=(
            "Query all crawled content collected for a specific topic. "
            "Returns text, author, metrics, and hashtags for analysis."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "The topic UUID",
                },
                "platform": {
                    "type": "string",
                    "enum": ["x", "xhs"],
                    "description": "Filter by platform (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max content items to return (default 50)",
                    "default": 50,
                },
            },
            "required": ["topic_id"],
        },
        func=_query_topic_contents,
    )

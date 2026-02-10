"""set_pipeline_stage tool — update topic pipeline progress in Redis."""

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.tools.base import Tool

PIPELINE_TTL = 86400  # 24 hours


def make_set_pipeline_stage(redis_client: aioredis.Redis) -> Tool:
    """Factory: create tool that sets pipeline progress for a topic."""

    async def _set_pipeline_stage(
        topic_id: str,
        phase: str,
        total: int | None = None,
        error_msg: str | None = None,
    ) -> dict:
        pipeline_key = f"topic:{topic_id}:pipeline"
        mapping: dict[str, str] = {
            "phase": phase,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if total is not None:
            mapping["total"] = str(total)
            mapping["done"] = "0"
        if error_msg:
            mapping["error_msg"] = error_msg

        await redis_client.hset(pipeline_key, mapping=mapping)
        await redis_client.expire(pipeline_key, PIPELINE_TTL)

        # When entering crawling phase, set pending counter + on_complete trigger
        if phase == "crawling" and total is not None:
            pending_key = f"topic:{topic_id}:pending"
            on_complete_key = f"topic:{topic_id}:on_complete"
            await redis_client.set(pending_key, total, ex=PIPELINE_TTL)
            await redis_client.set(on_complete_key, json.dumps({
                "label": "analyst:summarize",
                "payload": {"topic_id": topic_id},
                "next_phase": "summarizing",
            }), ex=PIPELINE_TTL)

        return {"status": "ok", "topic_id": topic_id, "phase": phase}

    return Tool(
        name="set_pipeline_stage",
        description=(
            "Update the pipeline progress stage for a topic. "
            "Use phase='analyzing' when starting analysis, 'crawling' with total=N when dispatching crawlers, "
            "'summarizing' for post-crawl analysis, 'done' when complete."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "The topic UUID",
                },
                "phase": {
                    "type": "string",
                    "enum": ["analyzing", "crawling", "summarizing", "done", "error"],
                    "description": "The current pipeline phase",
                },
                "total": {
                    "type": "integer",
                    "description": "Total crawler tasks (required when phase=crawling)",
                },
                "error_msg": {
                    "type": "string",
                    "description": "Error description (when phase=error)",
                },
            },
            "required": ["topic_id", "phase"],
        },
        func=_set_pipeline_stage,
    )

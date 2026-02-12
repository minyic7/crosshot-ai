"""set_pipeline_stage — update topic/user pipeline progress in Redis."""

import json
from datetime import datetime, timezone

import redis.asyncio as aioredis

PIPELINE_TTL = 86400  # 24 hours


async def set_pipeline_stage(
    redis_client: aioredis.Redis,
    entity_id: str,
    phase: str,
    total: int | None = None,
    error_msg: str | None = None,
    entity_type: str = "topic",
) -> dict:
    """Update the pipeline progress stage for a topic or user."""
    pipeline_key = f"{entity_type}:{entity_id}:pipeline"
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
        pending_key = f"{entity_type}:{entity_id}:pending"
        on_complete_key = f"{entity_type}:{entity_id}:on_complete"

        # Build on_complete payload with the right entity key
        on_complete_payload: dict = {
            "label": "analyst:summarize",
            "payload": {f"{entity_type}_id": entity_id},
            "next_phase": "summarizing",
        }

        await redis_client.set(pending_key, total, ex=PIPELINE_TTL)
        await redis_client.set(on_complete_key, json.dumps(on_complete_payload), ex=PIPELINE_TTL)

    return {"status": "ok", f"{entity_type}_id": entity_id, "phase": phase}

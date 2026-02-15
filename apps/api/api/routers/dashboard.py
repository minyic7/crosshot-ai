"""Dashboard stats and admin endpoints.

Aggregates data from Redis for the frontend dashboard page.
Provides admin operations like resetting all data.
"""

import logging

from fastapi import APIRouter
from sqlalchemy import text

from api.deps import get_queue, get_redis
from shared.db.engine import get_session_factory
from shared.models.agent import AgentHeartbeat

logger = logging.getLogger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats")
async def get_stats() -> dict:
    """Aggregate stats for the dashboard: queue depths, agent counts, recent tasks."""
    r = get_redis()
    queue = get_queue()

    # Count agents by status
    agents_online = 0
    agents_busy = 0
    async for key in r.scan_iter("agent:heartbeat:*"):
        data = await r.get(key)
        if data:
            hb = AgentHeartbeat.model_validate_json(data)
            agents_online += 1
            if hb.status == "busy":
                agents_busy += 1

    # Queue depths
    labels = await queue.get_queue_labels()
    total_pending = 0
    queues = {}
    for label in labels:
        length = await queue.get_queue_length(label)
        queues[label] = length
        total_pending += length

    # Recent task counts
    recent = await queue.get_recent_completed(limit=100)
    completed = sum(1 for t in recent if t.status.value == "completed")
    failed = sum(1 for t in recent if t.status.value == "failed")

    return {
        "agents_online": agents_online,
        "agents_busy": agents_busy,
        "total_pending": total_pending,
        "recent_completed": completed,
        "recent_failed": failed,
        "queues": queues,
    }


@router.post("/dashboard/reset")
async def reset_all_data() -> dict:
    """Clear all data from PG, OpenSearch, and Redis."""
    r = get_redis()
    factory = get_session_factory()

    # 1. Truncate all PG tables
    async with factory() as session:
        await session.execute(
            text("TRUNCATE users, topics, contents, content_media, tasks CASCADE")
        )
        await session.commit()
    logger.info("PG: all tables truncated")

    # 2. Delete and recreate OpenSearch index
    try:
        from shared.search import ensure_index, get_client, INDEX_NAME

        client = get_client()
        if await client.indices.exists(index=INDEX_NAME):
            await client.indices.delete(index=INDEX_NAME)
        await ensure_index()
        logger.info("OpenSearch: index recreated")
    except Exception as e:
        logger.warning("OpenSearch reset failed (non-fatal): %s", e)

    # 3. Clear Redis (preserve cookies)
    deleted = 0
    async for key in r.scan_iter("*"):
        key_str = key if isinstance(key, str) else key.decode()
        if key_str.startswith("cookies:"):
            continue
        await r.delete(key)
        deleted += 1
    logger.info("Redis: deleted %d keys (cookies preserved)", deleted)

    return {"status": "cleared"}

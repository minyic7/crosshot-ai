"""Dashboard stats endpoint.

Aggregates data from Redis for the frontend dashboard page.
"""

from fastapi import APIRouter

from api.deps import get_queue, get_redis
from shared.models.agent import AgentHeartbeat

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

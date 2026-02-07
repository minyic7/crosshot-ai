"""Agent monitoring endpoints.

Reads agent heartbeats from Redis and queue lengths to provide
a real-time view of the system.
"""

from fastapi import APIRouter

from api.deps import get_queue, get_redis
from shared.models.agent import AgentHeartbeat

router = APIRouter(tags=["agents"])


@router.get("/agents")
async def list_agents() -> list[dict]:
    """List all agents with their current heartbeat status."""
    r = get_redis()
    agents = []
    async for key in r.scan_iter("agent:heartbeat:*"):
        data = await r.get(key)
        if data:
            heartbeat = AgentHeartbeat.model_validate_json(data)
            agents.append(heartbeat.model_dump(mode="json"))
    return agents


@router.get("/agents/queues")
async def list_queues() -> list[dict]:
    """List all task queues with their pending counts."""
    queue = get_queue()
    labels = await queue.get_queue_labels()
    queues = []
    for label in sorted(labels):
        length = await queue.get_queue_length(label)
        queues.append({"label": label, "pending": length})
    return queues

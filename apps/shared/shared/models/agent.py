"""Agent heartbeat model for monitoring agent status via Redis."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AgentHeartbeat(BaseModel):
    """Agent status stored in Redis as agent:heartbeat:{name}.

    Written by each agent every 10s. Read by the API to display
    agent status on the frontend. Expires after 30s — if an agent
    stops heartbeating, it's considered offline.
    """

    name: str
    labels: list[str]
    status: str = "idle"  # idle | busy | error
    current_task_id: str | None = None
    current_task_label: str | None = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    started_at: datetime = Field(default_factory=datetime.now)
    last_heartbeat: datetime = Field(default_factory=datetime.now)

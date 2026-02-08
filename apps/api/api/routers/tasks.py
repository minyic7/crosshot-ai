"""Task query and creation endpoints."""

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import get_queue, get_redis
from shared.models.task import Task, TaskPriority

router = APIRouter(tags=["tasks"])


class TaskCreate(BaseModel):
    """Request body for creating a task directly."""

    label: str
    payload: dict[str, Any] = {}
    priority: int = 1  # 0=LOW, 1=MEDIUM, 2=HIGH


@router.post("/tasks")
async def create_task(body: TaskCreate) -> dict:
    """Push a task directly to the queue.

    Useful for testing and manual task dispatch.
    """
    queue = get_queue()
    task = Task(
        label=body.label,
        payload=body.payload,
        priority=TaskPriority(body.priority),
    )
    await queue.push(task)
    return {"task_id": task.id, "label": task.label, "status": "pending"}


@router.get("/tasks")
async def list_tasks(
    label: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """List tasks. Returns recent completed + pending queue tasks."""
    queue = get_queue()
    tasks = []

    # Get recently completed/failed tasks
    recent = await queue.get_recent_completed(limit=limit)
    for t in recent:
        if label and t.label != label:
            continue
        if status and t.status.value != status:
            continue
        tasks.append(t.model_dump(mode="json"))

    # Get pending tasks from queue labels
    if not status or status == "pending":
        labels = await queue.get_queue_labels()
        for q_label in labels:
            if label and q_label != label:
                continue
            length = await queue.get_queue_length(q_label)
            if length > 0:
                # We can't easily list sorted set members, but we know the count
                pass

    return {"tasks": tasks[:limit], "total": len(tasks)}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get a specific task by ID."""
    queue = get_queue()
    task = await queue.get_task(task_id)
    if task is None:
        return {"error": "Task not found", "task_id": task_id}
    return task.model_dump(mode="json")


@router.get("/content/{content_id}")
async def get_content(content_id: str) -> dict:
    """Get a crawled content item by ID."""
    redis = get_redis()
    raw = await redis.get(f"content:{content_id}")
    if raw is None:
        return {"error": "Content not found", "content_id": content_id}
    return json.loads(raw)

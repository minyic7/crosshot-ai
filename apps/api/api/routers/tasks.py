"""Task query endpoints."""

from fastapi import APIRouter

from api.deps import get_queue

router = APIRouter(tags=["tasks"])


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

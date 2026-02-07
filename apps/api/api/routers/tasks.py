"""Task query endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=["tasks"])


@router.get("/tasks")
async def list_tasks(
    label: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    """List tasks with optional filters."""
    # TODO: Query Redis for task statuses
    return {"tasks": [], "total": 0}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str) -> dict:
    """Get a specific task's status and result."""
    # TODO: Query Redis for task status
    return {"task_id": task_id, "status": "unknown"}

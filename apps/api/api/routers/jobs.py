"""Job management endpoints.

A Job is a user-facing request that gets decomposed into Tasks by the coordinator.
"""

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import get_queue
from shared.models.task import Task, TaskPriority

router = APIRouter(tags=["jobs"])


class JobCreate(BaseModel):
    """Request body for creating a job."""

    description: str


class JobResponse(BaseModel):
    """Response for a created job."""

    job_id: str
    status: str
    tasks_created: int


@router.post("/jobs", response_model=JobResponse)
async def create_job(body: JobCreate) -> JobResponse:
    """Create a new job from user description.

    Pushes a task with label "ai:plan" to the queue.
    The coordinator agent will pick it up and decompose it into crawler tasks.
    """
    queue = get_queue()
    job_id = str(uuid4())
    task = Task(
        label="ai:plan",
        priority=TaskPriority.MEDIUM,
        payload={"description": body.description, "job_id": job_id},
        parent_job_id=job_id,
    )
    await queue.push(task)
    return JobResponse(job_id=job_id, status="pending", tasks_created=1)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Get job status by checking all tasks with this parent_job_id."""
    queue = get_queue()
    recent = await queue.get_recent_completed(limit=100)
    job_tasks = [t for t in recent if t.parent_job_id == job_id]

    total = len(job_tasks)
    completed = sum(1 for t in job_tasks if t.status.value == "completed")
    failed = sum(1 for t in job_tasks if t.status.value == "failed")

    if total == 0:
        status = "pending"
    elif failed > 0:
        status = "partial"
    elif completed == total:
        status = "completed"
    else:
        status = "running"

    return {
        "job_id": job_id,
        "status": status,
        "progress": {"total": total, "completed": completed, "failed": failed},
    }

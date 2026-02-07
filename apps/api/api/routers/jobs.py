"""Job management endpoints.

A Job is a user-facing request that gets decomposed into Tasks by the coordinator.
"""

from fastapi import APIRouter
from pydantic import BaseModel

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

    This pushes a task with label "ai:plan" to the queue.
    The coordinator agent will pick it up and decompose it into crawler tasks.
    """
    # TODO: Create Task(label="ai:plan") and push to queue
    return JobResponse(job_id="stub", status="pending", tasks_created=0)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    """Get job status and progress."""
    # TODO: Query task statuses for this job
    return {
        "job_id": job_id,
        "status": "pending",
        "progress": {"total": 0, "completed": 0, "failed": 0},
    }

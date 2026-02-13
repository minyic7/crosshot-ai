"""Task query and creation endpoints."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from api.deps import get_queue
from shared.db.engine import get_session_factory
from shared.db.models import ContentRow
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


@router.get("/contents")
async def list_contents(
    platform: str | None = None,
    topic_id: str | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List crawled content items from PostgreSQL."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(ContentRow).order_by(ContentRow.crawled_at.desc())
        count_stmt = select(func.count()).select_from(ContentRow)

        if platform:
            stmt = stmt.where(ContentRow.platform == platform)
            count_stmt = count_stmt.where(ContentRow.platform == platform)
        if topic_id:
            stmt = stmt.where(ContentRow.topic_id == topic_id)
            count_stmt = count_stmt.where(ContentRow.topic_id == topic_id)
        if user_id:
            stmt = stmt.where(ContentRow.user_id == user_id)
            count_stmt = count_stmt.where(ContentRow.user_id == user_id)

        total = (await session.execute(count_stmt)).scalar() or 0
        rows = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()

    contents = [
        {
            "id": str(row.id),
            "task_id": str(row.task_id),
            "topic_id": str(row.topic_id) if row.topic_id else None,
            "platform": row.platform,
            "platform_content_id": row.platform_content_id,
            "source_url": row.source_url,
            "crawled_at": row.crawled_at.isoformat() if row.crawled_at else None,
            "author_username": row.author_username,
            "author_display_name": row.author_display_name,
            "text": row.text,
            "lang": row.lang,
            "hashtags": row.hashtags or [],
            "media_downloaded": row.media_downloaded,
            "metrics": row.metrics or {},
            "data": row.data or {},
        }
        for row in rows
    ]

    return {"contents": contents, "total": total}


@router.get("/content/{content_id}")
async def get_content(content_id: str) -> dict:
    """Get a crawled content item by ID."""
    factory = get_session_factory()
    async with factory() as session:
        row = await session.get(ContentRow, content_id)
    if row is None:
        return {"error": "Content not found", "content_id": content_id}
    return {
        "id": str(row.id),
        "task_id": str(row.task_id),
        "topic_id": str(row.topic_id) if row.topic_id else None,
        "platform": row.platform,
        "platform_content_id": row.platform_content_id,
        "source_url": row.source_url,
        "crawled_at": row.crawled_at.isoformat() if row.crawled_at else None,
        "author_username": row.author_username,
        "author_display_name": row.author_display_name,
        "text": row.text,
        "lang": row.lang,
        "hashtags": row.hashtags or [],
        "media_downloaded": row.media_downloaded,
        "metrics": row.metrics or {},
        "data": row.data or {},
    }


def _content_dict(row: ContentRow) -> dict:
    """Convert a ContentRow to the standard API dict."""
    return {
        "id": str(row.id),
        "task_id": str(row.task_id),
        "topic_id": str(row.topic_id) if row.topic_id else None,
        "platform": row.platform,
        "platform_content_id": row.platform_content_id,
        "source_url": row.source_url,
        "crawled_at": row.crawled_at.isoformat() if row.crawled_at else None,
        "author_username": row.author_username,
        "author_display_name": row.author_display_name,
        "text": row.text,
        "lang": row.lang,
        "hashtags": row.hashtags or [],
        "media_downloaded": row.media_downloaded,
        "metrics": row.metrics or {},
        "data": row.data or {},
    }


@router.get("/content/{content_id}/replies")
async def get_content_replies(content_id: str) -> dict:
    """Get replies/comments for a content item."""
    factory = get_session_factory()
    async with factory() as session:
        parent = await session.get(ContentRow, content_id)
        if parent is None:
            return {"replies": [], "total": 0}

        parent_tweet_id = parent.platform_content_id
        if not parent_tweet_id:
            return {"replies": [], "total": 0}

        stmt = (
            select(ContentRow)
            .where(
                ContentRow.platform == parent.platform,
                ContentRow.data["reply_to"]["tweet_id"].as_string() == parent_tweet_id,
            )
            .order_by(ContentRow.crawled_at)
        )
        rows = (await session.execute(stmt)).scalars().all()

    return {
        "replies": [_content_dict(r) for r in rows],
        "total": len(rows),
    }

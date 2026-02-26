"""Task query and creation endpoints."""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from api.deps import get_queue
from shared.db.engine import get_session_factory
from shared.db.models import ContentRow
from shared.models.task import Task, TaskPriority

logger = logging.getLogger(__name__)

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
    offset: int = 0,
) -> dict:
    """List all tasks from PostgreSQL with filters and pagination."""
    from shared.db.models import TaskRow

    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TaskRow).order_by(TaskRow.created_at.desc())
        count_stmt = select(func.count()).select_from(TaskRow)

        if label:
            stmt = stmt.where(TaskRow.label == label)
            count_stmt = count_stmt.where(TaskRow.label == label)
        if status:
            stmt = stmt.where(TaskRow.status == status)
            count_stmt = count_stmt.where(TaskRow.status == status)

        total = (await session.execute(count_stmt)).scalar() or 0
        rows = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()

    tasks = [
        {
            "id": str(r.id),
            "label": r.label,
            "priority": r.priority,
            "status": r.status,
            "payload": r.payload or {},
            "parent_job_id": str(r.parent_job_id) if r.parent_job_id else None,
            "assigned_to": r.assigned_to,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "retry_count": r.retry_count,
            "max_retries": r.max_retries,
            "error": r.error,
            "result": r.result,
        }
        for r in rows
    ]
    return {"tasks": tasks, "total": total}


@router.get("/tasks/labels")
async def list_task_labels() -> dict:
    """Get distinct task labels with counts by status."""
    from shared.db.models import TaskRow

    factory = get_session_factory()
    async with factory() as session:
        stmt = (
            select(TaskRow.label, TaskRow.status, func.count())
            .group_by(TaskRow.label, TaskRow.status)
        )
        rows = (await session.execute(stmt)).all()

    labels: dict[str, dict[str, int]] = {}
    for label, status, count in rows:
        if label not in labels:
            labels[label] = {}
        labels[label][status] = count

    return {"labels": labels}


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
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List crawled content items. Uses OpenSearch for text search, PG for browsing."""
    factory = get_session_factory()

    # OpenSearch path: text search with relevance ranking
    if search:
        try:
            from shared.search import search_contents

            content_ids, total = await search_contents(
                search,
                platform=platform,
                topic_id=topic_id,
                user_id=user_id,
                limit=limit,
                offset=offset,
            )
            if not content_ids:
                return {"contents": [], "total": total}

            async with factory() as session:
                stmt = select(ContentRow).where(ContentRow.id.in_(content_ids))
                rows = (await session.execute(stmt)).scalars().all()

            # Preserve OpenSearch relevance order
            row_map = {str(r.id): r for r in rows}
            ordered = [row_map[cid] for cid in content_ids if cid in row_map]
            return {"contents": [_content_dict(r) for r in ordered], "total": total}
        except Exception:
            logger.debug("OpenSearch unavailable, falling back to ILIKE", exc_info=True)

    # PG path: browsing or ILIKE fallback
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
        if search:
            pattern = f"%{search}%"
            search_filter = or_(
                ContentRow.text.ilike(pattern),
                ContentRow.author_username.ilike(pattern),
                ContentRow.author_display_name.ilike(pattern),
            )
            stmt = stmt.where(search_filter)
            count_stmt = count_stmt.where(search_filter)

        total = (await session.execute(count_stmt)).scalar() or 0
        rows = (await session.execute(stmt.offset(offset).limit(limit))).scalars().all()

    return {"contents": [_content_dict(r) for r in rows], "total": total}


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

"""Users CRUD API — create, list, update, delete tracked users/creators."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from api.deps import get_queue, get_redis, get_settings
from shared.db.engine import get_session_factory
from shared.db.models import ChatMessageRow, TopicRow, UserRow, topic_users
from shared.models.task import Task, TaskPriority
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


# ── Request models ──────────────────────────────────


class UserCreate(BaseModel):
    name: str
    platform: str
    profile_url: str
    username: str | None = None
    config: dict[str, Any] = {}
    topic_ids: list[str] = []  # optionally attach to topics on creation


class UserUpdate(BaseModel):
    name: str | None = None
    platform: str | None = None
    profile_url: str | None = None
    username: str | None = None
    config: dict[str, Any] | None = None
    status: str | None = None
    is_pinned: bool | None = None
    position: int | None = None


class AttachDetach(BaseModel):
    topic_id: str


class UserReorder(BaseModel):
    items: list[dict[str, Any]]


# ── Helpers ─────────────────────────────────────────


def _user_to_dict(u: UserRow, *, include_topics: bool = False) -> dict:
    d: dict[str, Any] = {
        "id": str(u.id),
        "name": u.name,
        "platform": u.platform,
        "profile_url": u.profile_url,
        "username": u.username,
        "config": u.config,
        "status": u.status,
        "is_pinned": u.is_pinned,
        "position": u.position,
        "total_contents": u.total_contents,
        "last_crawl_at": u.last_crawl_at.isoformat() if u.last_crawl_at else None,
        "last_summary": u.last_summary,
        "summary_data": u.summary_data,
        "created_at": u.created_at.isoformat(),
        "updated_at": u.updated_at.isoformat(),
    }
    if include_topics:
        d["topics"] = [
            {"id": str(t.id), "name": t.name, "icon": t.icon}
            for t in u.topics
        ]
    return d


# ── Endpoints ───────────────────────────────────────


@router.post("/users")
async def create_user(body: UserCreate) -> dict:
    """Create a tracked user, optionally attaching to topics."""
    factory = get_session_factory()

    async with factory() as session:
        user = UserRow(
            name=body.name,
            platform=body.platform,
            profile_url=body.profile_url,
            username=body.username,
            config=body.config,
        )
        session.add(user)
        await session.flush()

        # Attach to topics if requested
        if body.topic_ids:
            for tid in body.topic_ids:
                topic = await session.get(TopicRow, tid)
                if topic:
                    user.topics.append(topic)

        await session.commit()
        await session.refresh(user)

        return {"user": _user_to_dict(user)}


@router.get("/users")
async def list_users(standalone: bool | None = None, status: str | None = None, include_topics: bool = False) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(UserRow)
        if include_topics:
            stmt = stmt.options(selectinload(UserRow.topics))
        stmt = stmt.order_by(
            UserRow.is_pinned.desc(),
            UserRow.position,
            UserRow.created_at.desc(),
        )
        if status:
            stmt = stmt.where(UserRow.status == status)
        else:
            stmt = stmt.where(UserRow.status != "cancelled")

        if standalone is True:
            # Users not attached to any topic
            attached_ids = select(topic_users.c.user_id).distinct()
            stmt = stmt.where(UserRow.id.notin_(attached_ids))

        result = await session.execute(stmt)
        users = result.scalars().all()

        # Batch read progress stages from Redis
        redis = get_redis()
        pipe = redis.pipeline()
        for u in users:
            pipe.hgetall(f"user:{u.id}:progress")
        stages = await pipe.execute()

        user_list = []
        for i, u in enumerate(users):
            d = _user_to_dict(u, include_topics=include_topics)
            stage = stages[i] if stages[i] else None
            if stage and stage.get("phase") == "done":
                stage = None
            d["progress"] = stage
            user_list.append(d)

        return {"users": user_list, "total": len(users)}


@router.get("/users/{user_id}")
async def get_user(user_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(UserRow).where(UserRow.id == user_id).options(
            selectinload(UserRow.topics)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            return {"error": "User not found"}
        return _user_to_dict(user, include_topics=True)


@router.patch("/users/{user_id}")
async def update_user(user_id: str, body: UserUpdate) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        if user is None:
            return {"error": "User not found"}
        update_data = body.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(user, key, value)
        user.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(user)
        return _user_to_dict(user)


@router.delete("/users/{user_id}")
async def delete_user(user_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        if user is None:
            return {"error": "User not found"}
        user.status = "cancelled"
        user.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return {"status": "cancelled", "user_id": user_id}


@router.post("/users/{user_id}/attach")
async def attach_user(user_id: str, body: AttachDetach) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        if user is None:
            return {"error": "User not found"}
        topic = await session.get(TopicRow, body.topic_id)
        if topic is None:
            return {"error": "Topic not found"}

        # Check if already attached
        stmt = select(topic_users).where(
            topic_users.c.topic_id == body.topic_id,
            topic_users.c.user_id == user_id,
        )
        exists = (await session.execute(stmt)).first()
        if exists:
            return {"status": "already_attached"}

        await session.execute(
            topic_users.insert().values(topic_id=body.topic_id, user_id=user_id)
        )
        await session.commit()
        return {"status": "attached", "user_id": user_id, "topic_id": body.topic_id}


@router.post("/users/{user_id}/detach")
async def detach_user(user_id: str, body: AttachDetach) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            delete(topic_users).where(
                topic_users.c.topic_id == body.topic_id,
                topic_users.c.user_id == user_id,
            )
        )
        await session.commit()
        return {"status": "detached", "user_id": user_id, "topic_id": body.topic_id}


@router.get("/users/{user_id}/progress")
async def get_user_progress(user_id: str) -> dict:
    """Get progress state and active crawler task progress for a user."""
    import json

    redis = get_redis()

    user_progress = await redis.hgetall(f"user:{user_id}:progress")
    if not user_progress:
        return {"progress": None, "tasks": []}

    task_ids = await redis.smembers(f"user:{user_id}:task_ids")

    tasks_info = []
    if task_ids:
        pipe = redis.pipeline()
        for tid in task_ids:
            pipe.get(f"task:{tid}")
            pipe.get(f"task:{tid}:progress")
        results = await pipe.execute()

        for i in range(0, len(results), 2):
            task_raw = results[i]
            progress_raw = results[i + 1]
            if not task_raw:
                continue

            task_data = json.loads(task_raw) if isinstance(task_raw, str) else task_raw
            task_progress = json.loads(progress_raw) if progress_raw else None

            tasks_info.append({
                "id": task_data.get("id"),
                "label": task_data.get("label"),
                "status": task_data.get("status"),
                "payload": {
                    "action": task_data.get("payload", {}).get("action"),
                    "username": task_data.get("payload", {}).get("username"),
                    "query": (task_data.get("payload", {}).get("query") or "")[:80],
                },
                "progress": task_progress,
                "started_at": task_data.get("started_at"),
                "completed_at": task_data.get("completed_at"),
            })

    return {"progress": user_progress, "tasks": tasks_info}


@router.post("/users/reorder")
async def reorder_users(body: UserReorder) -> dict:
    """Bulk update user positions for drag-drop reordering."""
    factory = get_session_factory()
    async with factory() as session:
        for item in body.items:
            user = await session.get(UserRow, item["id"])
            if user:
                user.position = item["position"]
                if "is_pinned" in item:
                    user.is_pinned = item["is_pinned"]
        await session.commit()
    return {"status": "ok"}


@router.post("/users/{user_id}/reanalyze")
async def reanalyze_user(user_id: str, crawl: bool = False) -> dict:
    """Re-run analysis on existing data. Set crawl=true to also fetch new data."""
    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        if user is None:
            return {"error": "User not found"}

        queue = get_queue()
        payload: dict[str, Any] = {
            "user_id": str(user.id),
            "name": user.name,
            "platform": user.platform,
            "username": user.username,
            "profile_url": user.profile_url,
            "config": user.config,
        }
        if not crawl:
            payload["skip_crawl"] = True
        task = Task(
            label="analyst:analyze",
            priority=TaskPriority.MEDIUM,
            payload=payload,
        )
        await queue.push(task)

        redis = get_redis()
        progress_key = f"user:{user.id}:progress"
        await redis.hset(progress_key, mapping={
            "phase": "analyzing",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        await redis.expire(progress_key, 86400)

        return {"status": "reanalyzing", "task_id": task.id}


@router.get("/users/{user_id}/trend")
async def get_user_trend(user_id: str, days: int = 30) -> list[dict]:
    """Return per-period content counts + engagement for user trend charts."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    factory = get_session_factory()
    async with factory() as session:
        # Get the user's schedule interval
        user = await session.get(UserRow, user_id)
        if user is None:
            return []
        interval_hours = (user.config or {}).get("schedule_interval_hours", 6)
        interval_secs = interval_hours * 3600

        result = await session.execute(
            text("""
                SELECT TO_TIMESTAMP(
                         FLOOR(EXTRACT(EPOCH FROM crawled_at) / :interval) * :interval
                       ) AS period,
                       COUNT(*) AS posts,
                       COALESCE(SUM((metrics->>'like_count')::int), 0) AS likes,
                       COALESCE(SUM((metrics->>'views_count')::int), 0) AS views,
                       COALESCE(SUM((metrics->>'retweet_count')::int), 0) AS retweets,
                       COALESCE(SUM((metrics->>'reply_count')::int), 0) AS replies,
                       COUNT(*) FILTER (
                           WHERE data->'media' IS NOT NULL
                             AND jsonb_array_length(data->'media') > 0
                       ) AS media_posts
                FROM contents
                WHERE user_id = :uid AND crawled_at >= :since
                GROUP BY period
                ORDER BY period
            """),
            {"uid": user_id, "since": since, "interval": interval_secs},
        )
        return [
            {
                "day": r.period.strftime("%Y-%m-%d %H:%M"),
                "posts": r.posts,
                "likes": r.likes,
                "views": r.views,
                "retweets": r.retweets,
                "replies": r.replies,
                "media_posts": r.media_posts,
            }
            for r in result
        ]


def _sse(data: dict) -> str:
    import json
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


class UserChatRequest(BaseModel):
    messages: list[dict[str, str]]


@router.get("/users/{user_id}/chat/history")
async def get_user_chat_history(user_id: str):
    """Load persisted chat messages for the current period."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ChatMessageRow)
            .where(
                ChatMessageRow.entity_type == "user",
                ChatMessageRow.entity_id == user_id,
                ChatMessageRow.is_archived == False,  # noqa: E712
            )
            .order_by(ChatMessageRow.created_at)
        )
        rows = result.scalars().all()
    return {
        "messages": [
            {"role": r.role, "content": r.content, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
    }


@router.post("/users/{user_id}/chat")
async def chat_user(user_id: str, body: UserChatRequest):
    """Conversational analysis — ask questions about a user's content. Streams SSE."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    factory = get_session_factory()
    async with factory() as session:
        user = await session.get(UserRow, user_id)
        if user is None:
            return {"error": "User not found"}

        # Recent top posts by engagement
        top_result = await session.execute(
            text("""
                SELECT text, author_username, metrics, source_url, platform
                FROM contents
                WHERE user_id = :uid
                ORDER BY (
                    COALESCE((metrics->>'like_count')::int, 0) +
                    COALESCE((metrics->>'retweet_count')::int, 0)
                ) DESC
                LIMIT 20
            """),
            {"uid": user_id},
        )
        top_posts = []
        for r in top_result:
            likes = (r.metrics or {}).get("like_count", 0)
            retweets = (r.metrics or {}).get("retweet_count", 0)
            views = (r.metrics or {}).get("views_count", 0)
            top_posts.append(
                f"[{r.platform}] @{r.author_username or '?'}: "
                f"{(r.text or '')[:200]} "
                f"(likes:{likes} rt:{retweets} views:{views})"
            )

        agg_result = await session.execute(
            text("""
                SELECT COUNT(*) as cnt,
                       COALESCE(SUM((metrics->>'like_count')::int), 0) as likes,
                       COALESCE(SUM((metrics->>'views_count')::int), 0) as views
                FROM contents WHERE user_id = :uid
            """),
            {"uid": user_id},
        )
        agg = agg_result.first()
        stats_text = f"{agg.cnt} posts, {agg.likes} likes, {agg.views} views" if agg else "(no data)"

    posts_text = "\n".join(top_posts[:15]) if top_posts else "(no posts yet)"
    summary_text = user.last_summary or "(no previous summary)"

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    system_prompt = f"""\
You are a social media analyst for the user "{user.name}" (@{user.username or '?'}).
You speak the same language as the user (Chinese if they write Chinese, English for English).
Be concise, insightful, and data-driven. Reference specific posts when relevant.

**Current date: {today} (UTC)**

## Current Data
- Platform: {user.platform}
- Profile: {user.profile_url}
- Stats: {stats_text}
- Last crawl: {user.last_crawl_at.isoformat() if user.last_crawl_at else 'never'}

## Previous Summary
{summary_text[:1000]}

## Top Posts (by engagement)
{posts_text}
"""

    client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    messages_list: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in body.messages:
        messages_list.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    # Persist the new user message (last in the list)
    user_msgs = [m for m in body.messages if m.get("role") == "user"]
    if user_msgs:
        async with factory() as session:
            session.add(ChatMessageRow(
                entity_type="user", entity_id=user_id,
                role="user", content=user_msgs[-1].get("content", ""),
            ))
            await session.commit()

    async def generate():
        accumulated = ""
        try:
            stream = await client.chat.completions.create(
                model=settings.grok_model,
                messages=messages_list,
                temperature=0.7,
                max_tokens=2048,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    accumulated += delta
                    yield _sse({"t": delta})
            yield _sse({"done": True})
            # Persist the assistant response
            if accumulated:
                async with factory() as s:
                    s.add(ChatMessageRow(
                        entity_type="user", entity_id=user_id,
                        role="assistant", content=accumulated,
                    ))
                    await s.commit()
        except Exception as e:
            logger.exception("User chat stream error")
            yield _sse({"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

"""Topics CRUD API — create, list, update, delete monitoring topics."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

from api.deps import get_queue, get_redis
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory
from shared.db.models import ChatMessageRow, TopicRow, UserRow, topic_users
from shared.models.task import Task, TaskPriority
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter(tags=["topics"])


# ── Request models ──────────────────────────────────


class TopicCreate(BaseModel):
    type: str = "topic"
    name: str
    icon: str = "📊"
    description: str | None = None
    platforms: list[str]
    keywords: list[str]
    config: dict[str, Any] = {}


class TopicUpdate(BaseModel):
    type: str | None = None
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    platforms: list[str] | None = None
    keywords: list[str] | None = None
    config: dict[str, Any] | None = None
    status: str | None = None
    is_pinned: bool | None = None
    position: int | None = None


class TopicReorder(BaseModel):
    items: list[dict[str, Any]]


class AssistMessage(BaseModel):
    role: str
    content: str


class TopicAssistRequest(BaseModel):
    messages: list[AssistMessage]
    edit_context: dict | None = None


# ── Helpers ─────────────────────────────────────────


def _topic_to_dict(t: TopicRow, *, include_users: bool = False) -> dict:
    d: dict[str, Any] = {
        "id": str(t.id),
        "type": t.type,
        "name": t.name,
        "icon": t.icon,
        "description": t.description,
        "platforms": t.platforms,
        "keywords": t.keywords,
        "config": t.config,
        "status": t.status,
        "is_pinned": t.is_pinned,
        "position": t.position,
        "total_contents": t.total_contents,
        "last_crawl_at": t.last_crawl_at.isoformat() if t.last_crawl_at else None,
        "last_summary": t.last_summary,
        "summary_data": t.summary_data,
        "created_at": t.created_at.isoformat(),
        "updated_at": t.updated_at.isoformat(),
    }
    if include_users:
        d["users"] = [
            {
                "id": str(u.id),
                "name": u.name,
                "platform": u.platform,
                "username": u.username,
                "profile_url": u.profile_url,
            }
            for u in t.users
        ]
        d["user_count"] = len(t.users)
    return d


async def _dispatch_analyze(
    topic: TopicRow, *, force_crawl: bool = False, skip_crawl: bool = False,
) -> str:
    """Push an analyst:analyze task and set progress stage to 'analyzing'."""
    queue = get_queue()
    payload: dict[str, Any] = {
        "topic_id": str(topic.id),
        "name": topic.name,
        "platforms": topic.platforms,
        "keywords": topic.keywords,
        "config": topic.config,
    }
    if force_crawl:
        payload["force_crawl"] = True
    if skip_crawl:
        payload["skip_crawl"] = True

    # Include attached users info for the analyst
    try:
        users_list = [
            {
                "user_id": str(u.id),
                "username": u.username,
                "platform": u.platform,
                "profile_url": u.profile_url,
                "config": u.config,
            }
            for u in topic.users
        ]
        if users_list:
            payload["users"] = users_list
    except Exception:
        pass  # users relationship not loaded — skip

    task = Task(
        label="analyst:analyze",
        priority=TaskPriority.MEDIUM,
        payload=payload,
    )
    await queue.push(task)

    # Set initial progress stage
    redis = get_redis()
    progress_key = f"topic:{topic.id}:progress"
    await redis.hset(progress_key, mapping={
        "phase": "analyzing",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await redis.expire(progress_key, 86400)

    return task.id


# ── Endpoints ───────────────────────────────────────


@router.post("/topics")
async def create_topic(body: TopicCreate) -> dict:
    """Create a new topic and immediately trigger analyst:analyze."""
    factory = get_session_factory()

    async with factory() as session:
        topic = TopicRow(
            type=body.type,
            name=body.name,
            icon=body.icon,
            description=body.description,
            platforms=body.platforms,
            keywords=body.keywords,
            config=body.config,
        )
        session.add(topic)
        await session.commit()
        await session.refresh(topic)

        task_id = await _dispatch_analyze(topic, force_crawl=True)

        return {
            "topic": _topic_to_dict(topic),
            "task_id": task_id,
        }


@router.get("/topics")
async def list_topics(status: str | None = None, include_users: bool = False) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow)
        if include_users:
            stmt = stmt.options(selectinload(TopicRow.users))
        stmt = stmt.order_by(
            TopicRow.is_pinned.desc(),
            TopicRow.position,
            TopicRow.created_at.desc(),
        )
        if status:
            stmt = stmt.where(TopicRow.status == status)
        else:
            # By default, hide cancelled topics
            stmt = stmt.where(TopicRow.status != "cancelled")
        result = await session.execute(stmt)
        topics = result.scalars().all()

        # Batch read progress stages from Redis
        redis = get_redis()
        pipe = redis.pipeline()
        for t in topics:
            pipe.hgetall(f"topic:{t.id}:progress")
        stages = await pipe.execute()

        topic_list = []
        for i, t in enumerate(topics):
            d = _topic_to_dict(t, include_users=include_users)
            stage = stages[i] if stages[i] else None
            # Filter out 'done' — no need to show completed progress
            if stage and stage.get("phase") == "done":
                stage = None
            d["progress"] = stage
            topic_list.append(d)

        return {
            "topics": topic_list,
            "total": len(topics),
        }


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow).where(TopicRow.id == topic_id).options(
            selectinload(TopicRow.users)
        )
        result = await session.execute(stmt)
        topic = result.scalar_one_or_none()
        if topic is None:
            return {"error": "Topic not found"}
        return _topic_to_dict(topic, include_users=True)


@router.get("/topics/{topic_id}/trend")
async def get_topic_trend(topic_id: str, days: int = 30) -> list[dict]:
    """Return per-period content counts + engagement for trend charts.

    Groups by the topic's schedule_interval_hours (default 6h) instead of by day.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    factory = get_session_factory()
    async with factory() as session:
        # Get the topic's schedule interval
        topic_row = await session.execute(
            text("SELECT config FROM topics WHERE id = :tid"),
            {"tid": topic_id},
        )
        row = topic_row.first()
        interval_hours = 6
        if row and row.config:
            interval_hours = (row.config or {}).get("schedule_interval_hours", 6)

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
                WHERE topic_id = :tid AND crawled_at >= :since
                GROUP BY period
                ORDER BY period
            """),
            {"tid": topic_id, "since": since, "interval": interval_secs},
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


@router.patch("/topics/{topic_id}")
async def update_topic(topic_id: str, body: TopicUpdate) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow).where(TopicRow.id == topic_id).options(
            selectinload(TopicRow.users)
        )
        result = await session.execute(stmt)
        topic = result.scalar_one_or_none()
        if topic is None:
            return {"error": "Topic not found"}

        # Snapshot fields that trigger reanalysis when changed
        old_platforms = set(topic.platforms or [])
        old_keywords = set(topic.keywords or [])

        update_data = body.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(topic, key, value)
        topic.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(topic)

        # Auto-dispatch reanalysis if platforms or keywords changed
        new_platforms = set(topic.platforms or [])
        new_keywords = set(topic.keywords or [])
        if new_platforms != old_platforms or new_keywords != old_keywords:
            force = bool(new_platforms - old_platforms)  # force crawl if new platforms added
            task_id = await _dispatch_analyze(topic, force_crawl=force)
            logger.info(
                "Auto-dispatched reanalysis for topic %s (platforms: %s→%s, keywords: %s→%s, task=%s)",
                topic_id, old_platforms, new_platforms, old_keywords, new_keywords, task_id,
            )

        return _topic_to_dict(topic)


@router.delete("/topics/{topic_id}")
async def delete_topic(topic_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}
        topic.status = "cancelled"
        topic.updated_at = datetime.now(timezone.utc)
        await session.commit()
        return {"status": "cancelled", "topic_id": topic_id}


@router.post("/topics/{topic_id}/reanalyze")
async def reanalyze_topic(topic_id: str, crawl: bool = False) -> dict:
    """Re-run analysis on existing data. Set crawl=true to also fetch new data."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow).where(TopicRow.id == topic_id).options(
            selectinload(TopicRow.users)
        )
        result = await session.execute(stmt)
        topic = result.scalar_one_or_none()
        if topic is None:
            return {"error": "Topic not found"}

        task_id = await _dispatch_analyze(topic, skip_crawl=not crawl)
        return {"status": "reanalyzing", "task_id": task_id}


@router.get("/topics/{topic_id}/progress")
async def get_topic_progress(topic_id: str) -> dict:
    """Get progress state and active crawler task progress for a topic."""
    redis = get_redis()

    topic_progress = await redis.hgetall(f"topic:{topic_id}:progress")
    if not topic_progress:
        return {"progress": None, "tasks": []}

    task_ids = await redis.smembers(f"topic:{topic_id}:task_ids")

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

    return {"progress": topic_progress, "tasks": tasks_info}


@router.post("/topics/reorder")
async def reorder_topics(body: TopicReorder) -> dict:
    """Bulk update topic positions for drag-drop reordering."""
    factory = get_session_factory()
    async with factory() as session:
        for item in body.items:
            topic = await session.get(TopicRow, item["id"])
            if topic:
                topic.position = item["position"]
                if "is_pinned" in item:
                    topic.is_pinned = item["is_pinned"]
        await session.commit()
    return {"status": "ok"}


# ── AI Assist ──────────────────────────────────────────


_ASSIST_SYSTEM_BASE = """\
You are a sharp, concise assistant for CrossHot AI (social media monitoring).
You speak the same language as the user (Chinese if they write Chinese, English if English, mix if they mix).

## Behavior
- Be direct. No greetings, no filler.
- You can propose MULTIPLE actions in one response.
- If the user's request is vague, ask a SHORT clarifying question.
- Proactively suggest monitoring angles the user might not have thought of.
- When the user refines, use update_topic/update_user to modify pending proposals. Only return NEW or CHANGED actions (don't repeat unchanged ones).
- When renaming a topic, use update_topic with original_name. Also update any subscribe actions that reference the old name.
- Briefly explain your choices when helpful.
- **NEVER propose creating a topic or user that already exists** (see existing data below).
- If the user asks to monitor something already covered, suggest refining the existing topic instead.

## Action types
- **create_topic**: Monitor a keyword/theme across platforms
- **create_user**: Track a specific person's timeline
- **subscribe**: Attach a user to a topic (so the topic analysis includes that user's posts)
- **update_topic**: Modify a pending topic proposal (e.g. rename, change keywords)
- **update_user**: Modify a pending user proposal (e.g. rename, change username)

## Action schemas
create_topic:
  {type, name, icon, description, platforms, keywords, schedule_interval_hours}
create_user:
  {type, name, platform, profile_url, username, schedule_interval_hours}
subscribe:
  {type, user_ref, topic_ref}  — use the name/username you proposed
update_topic:
  {type, original_name, ...fields to change} — original_name matches the existing proposal
update_user:
  {type, original_name, ...fields to change} — original_name matches the existing proposal

## Platforms
- **x**: Twitter/X, English-dominant
- **xhs**: 小红书, Chinese-dominant, lifestyle/consumer focus
- **web**: General web search (news, expert analysis, research papers, official announcements)
- Pick platforms matching the topic. Tech/global → x + web. Chinese consumer → xhs. English news → x + web. Deep research → add web.

## Guidelines
- Keywords: general search terms, 5-10 diverse, include English + Chinese for coverage
- Icon: relevant emoji (🤖 AI, 🚗 Tesla, 🎮 gaming) — not default 📊
- Refresh interval: breaking 2-3h, general 6h, niche 12-24h
- profile_url: full URL like https://x.com/username
- When proposing users that belong to a topic, also add a subscribe action

## STRICT response format
Raw JSON only (no markdown, no fences):
{
  "reply": "Your message (1-3 sentences)",
  "actions": [
    {"type": "create_topic", "name": "...", "icon": "...", "description": "...", "platforms": [...], "keywords": [...], "schedule_interval_hours": 6},
    {"type": "create_user", "name": "...", "platform": "x", "profile_url": "https://x.com/...", "username": "...", "schedule_interval_hours": 6},
    {"type": "subscribe", "user_ref": "username", "topic_ref": "topic name"}
  ]
}
If no actions needed (e.g. asking a question), use "actions": []
"""


async def _build_assist_system() -> str:
    """Build the assist system prompt with existing topics/users injected."""
    factory = get_session_factory()
    async with factory() as session:
        topics = (await session.execute(
            select(TopicRow).options(selectinload(TopicRow.users))
        )).scalars().all()
        users = (await session.execute(select(UserRow))).scalars().all()

    existing = "\n## Existing Data (DO NOT duplicate these)\n"
    if topics:
        existing += "Topics:\n"
        for t in topics:
            attached = ", ".join(f"@{u.username}" for u in t.users if u.username)
            existing += f"- {t.icon or ''} {t.name} ({t.status}) platforms={t.platforms} keywords={t.keywords}"
            if attached:
                existing += f" users=[{attached}]"
            existing += "\n"
    else:
        existing += "Topics: (none)\n"

    if users:
        existing += "Users:\n"
        for u in users:
            existing += f"- @{u.username} ({u.platform}, {u.status})\n"
    else:
        existing += "Users: (none)\n"

    return _ASSIST_SYSTEM_BASE + existing


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/topics/assist")
async def assist_topic(body: TopicAssistRequest):
    """Stream AI suggestions via SSE. Events: {t:token}, {done:true,reply,actions}."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    system_prompt = await _build_assist_system()
    if body.edit_context:
        ctx = body.edit_context
        entity_type = ctx.get("type", "topic")
        entity_name = ctx.get("name", "")
        system_prompt += f"""
## Editing Mode
You are helping the user EDIT an existing {entity_type}. Current config:
{json.dumps(ctx, ensure_ascii=False, indent=2)}

Use update_{entity_type} with original_name="{entity_name}" to suggest changes.
Do NOT create new topics/users — only update the existing one.
"""
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for m in body.messages:
        messages.append({"role": m.role, "content": m.content})

    async def generate():
        try:
            stream = await client.chat.completions.create(
                model=settings.grok_model,
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
                stream=True,
            )
            full = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if delta:
                    full += delta
                    yield _sse({"t": delta})

            # Parse complete JSON response
            text = full.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(text)
            actions = data.get("actions", [])
            # Fallback: if model returned old "suggestion" dict instead of "actions" array
            if not actions and isinstance(data.get("suggestion"), dict):
                s = data["suggestion"]
                s.setdefault("type", "create_topic")
                actions = [s]
            yield _sse({
                "done": True,
                "reply": data.get("reply", ""),
                "actions": actions,
            })
        except json.JSONDecodeError:
            yield _sse({"done": True, "reply": full, "actions": []})
        except Exception as e:
            logger.exception("AI assist stream error")
            yield _sse({"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Topic Chat ─────────────────────────────────────────


class TopicChatRequest(BaseModel):
    messages: list[AssistMessage]


@router.get("/topics/{topic_id}/chat/history")
async def get_topic_chat_history(topic_id: str):
    """Load persisted chat messages for the current period."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(ChatMessageRow)
            .where(
                ChatMessageRow.entity_type == "topic",
                ChatMessageRow.entity_id == topic_id,
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


@router.post("/topics/{topic_id}/chat")
async def chat_topic(topic_id: str, body: TopicChatRequest):
    """Conversational analysis — ask questions about topic data. Streams SSE."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}

        # Build context from PG data
        from sqlalchemy import text as sql_text

        # Recent top posts (by engagement, last 7 days max)
        top_result = await session.execute(
            sql_text("""
                SELECT text, author_username, metrics, source_url, platform
                FROM contents
                WHERE topic_id = :tid
                ORDER BY (
                    COALESCE((metrics->>'like_count')::int, 0) +
                    COALESCE((metrics->>'retweet_count')::int, 0)
                ) DESC
                LIMIT 20
            """),
            {"tid": topic_id},
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

        # Metrics summary
        agg_result = await session.execute(
            sql_text("""
                SELECT platform, COUNT(*) as cnt,
                       COALESCE(SUM((metrics->>'like_count')::int), 0) as likes,
                       COALESCE(SUM((metrics->>'views_count')::int), 0) as views
                FROM contents WHERE topic_id = :tid
                GROUP BY platform
            """),
            {"tid": topic_id},
        )
        platform_stats = [
            f"{r.platform}: {r.cnt} posts, {r.likes} likes, {r.views} views"
            for r in agg_result
        ]

    # Build system prompt with injected data
    posts_text = "\n".join(top_posts[:15]) if top_posts else "(no posts yet)"
    stats_text = "; ".join(platform_stats) if platform_stats else "(no data)"
    summary_text = topic.last_summary or "(no previous summary)"

    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    system_prompt = f"""\
You are a social media analyst for the topic "{topic.name}".
You speak the same language as the user (Chinese if they write Chinese, English for English).
Be concise, insightful, and data-driven. Reference specific posts when relevant.

**Current date: {today} (UTC)**

## Current Data
- Platforms monitored: {', '.join(topic.platforms or [])}
- Keywords: {', '.join(topic.keywords or [])}
- Stats: {stats_text}
- Last analysis: {topic.last_crawl_at.isoformat() if topic.last_crawl_at else 'never'}

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
        messages_list.append({"role": m.role, "content": m.content})

    # Persist the new user message (last in the list)
    user_msgs = [m for m in body.messages if m.role == "user"]
    if user_msgs:
        async with factory() as session:
            session.add(ChatMessageRow(
                entity_type="topic", entity_id=topic_id,
                role="user", content=user_msgs[-1].content,
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
                        entity_type="topic", entity_id=topic_id,
                        role="assistant", content=accumulated,
                    ))
                    await s.commit()
        except Exception as e:
            logger.exception("Topic chat stream error")
            yield _sse({"error": str(e)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class TranslateRequest(BaseModel):
    text: str
    target: str = "zh"


@router.post("/translate")
async def translate_text(body: TranslateRequest):
    """Translate text via Grok. Streams SSE tokens."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    lang_name = "Chinese" if body.target == "zh" else "English"
    client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    async def stream():
        try:
            resp = await client.chat.completions.create(
                model=settings.grok_model,
                messages=[
                    {"role": "system", "content": f"Translate the following text to {lang_name}. Output only the translation, nothing else."},
                    {"role": "user", "content": body.text},
                ],
                stream=True,
            )
            async for chunk in resp:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield _sse({"t": delta.content})
            yield _sse({"done": True})
        except Exception as e:
            logger.exception("Translate stream error")
            yield _sse({"error": str(e)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

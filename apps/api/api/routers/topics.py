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
from shared.db.models import TopicRow
from shared.models.task import Task, TaskPriority
from sqlalchemy import func, select, text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["topics"])


# ── Request models ──────────────────────────────────


class TopicCreate(BaseModel):
    name: str
    icon: str = "📊"
    description: str | None = None
    platforms: list[str]
    keywords: list[str]
    config: dict[str, Any] = {}


class TopicUpdate(BaseModel):
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


# ── Helpers ─────────────────────────────────────────


def _topic_to_dict(t: TopicRow) -> dict:
    return {
        "id": str(t.id),
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


async def _dispatch_analyze(
    topic: TopicRow, *, force_crawl: bool = False,
) -> str:
    """Push an analyst:analyze task and set pipeline stage to 'analyzing'."""
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

    task = Task(
        label="analyst:analyze",
        priority=TaskPriority.MEDIUM,
        payload=payload,
    )
    await queue.push(task)

    # Set initial pipeline stage
    redis = get_redis()
    pipeline_key = f"topic:{topic.id}:pipeline"
    await redis.hset(pipeline_key, mapping={
        "phase": "analyzing",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    await redis.expire(pipeline_key, 86400)

    return task.id


# ── Endpoints ───────────────────────────────────────


@router.post("/topics")
async def create_topic(body: TopicCreate) -> dict:
    """Create a new topic and immediately trigger analyst:analyze."""
    factory = get_session_factory()

    async with factory() as session:
        topic = TopicRow(
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
async def list_topics(status: str | None = None) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(TopicRow).order_by(
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

        # Batch read pipeline stages from Redis
        redis = get_redis()
        pipe = redis.pipeline()
        for t in topics:
            pipe.hgetall(f"topic:{t.id}:pipeline")
        stages = await pipe.execute()

        topic_list = []
        for i, t in enumerate(topics):
            d = _topic_to_dict(t)
            stage = stages[i] if stages[i] else None
            # Filter out 'done' — no need to show completed pipelines
            if stage and stage.get("phase") == "done":
                stage = None
            d["pipeline"] = stage
            topic_list.append(d)

        return {
            "topics": topic_list,
            "total": len(topics),
        }


@router.get("/topics/{topic_id}")
async def get_topic(topic_id: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}
        return _topic_to_dict(topic)


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
                       COALESCE(SUM((metrics->>'views_count')::int), 0) AS views
                FROM contents
                WHERE topic_id = :tid AND crawled_at >= :since
                GROUP BY period
                ORDER BY period
            """),
            {"tid": topic_id, "since": since, "interval": interval_secs},
        )
        return [
            {"day": r.period.strftime("%Y-%m-%d %H:%M"), "posts": r.posts, "likes": r.likes, "views": r.views}
            for r in result
        ]


@router.patch("/topics/{topic_id}")
async def update_topic(topic_id: str, body: TopicUpdate) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}
        update_data = body.model_dump(exclude_none=True)
        for key, value in update_data.items():
            setattr(topic, key, value)
        topic.updated_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(topic)
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
async def reanalyze_topic(topic_id: str) -> dict:
    """Re-run analysis — analyst decides if new data is needed."""
    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}

        task_id = await _dispatch_analyze(topic)
        return {"status": "reanalyzing", "task_id": task_id}


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


_ASSIST_SYSTEM = """\
You are a sharp, concise topic creation assistant for CrossHot AI (social media monitoring).
You speak the same language as the user (Chinese if they write Chinese, English if English, mix if they mix).

## Behavior
- Be direct. No greetings, no "很高兴", no filler.
- If the user's request is vague, ask a SHORT clarifying question (what angle? which aspects?).
- Proactively suggest interesting monitoring angles the user might not have thought of.
- When the user refines, update the suggestion — don't repeat what you already said.
- Briefly explain your choices when helpful (e.g. "建议6小时刷新因为这个话题变化快" or "选了双平台因为中英文受众不同").

## Platforms
- **x**: Twitter/X, English-dominant
- **xhs**: 小红书, Chinese-dominant, lifestyle/consumer focus
- Pick platforms that match the topic. Tech/global topics → both. Chinese consumer/lifestyle → xhs. English news → x only.

## Keyword guidelines
- General search terms only (the system handles platform-specific syntax)
- Include both English AND Chinese keywords for multi-platform coverage
- Include: exact names, aliases, abbreviations, trending hashtags (without #), related terms
- 5-10 diverse keywords for good coverage

## Icon
- Pick a highly relevant emoji for the topic (e.g. 🤖 for AI, 🚗 for Tesla, 🎮 for gaming)
- Don't default to 📊 — be creative and specific

## Refresh interval
- Breaking news / fast-moving topics: 2-3 hours
- General monitoring: 6 hours (default)
- Slow-moving / niche topics: 12-24 hours

## STRICT response format
Respond with raw JSON only (no markdown, no fences):
{
  "reply": "Your message (1-3 sentences, same language as user)",
  "suggestion": {
    "name": "Short topic name",
    "icon": "single emoji",
    "description": "1-2 sentence description",
    "platforms": ["x", "xhs"],
    "keywords": ["keyword1", "keyword2", "..."],
    "schedule_interval_hours": 6
  }
}
"""


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/topics/assist")
async def assist_topic(body: TopicAssistRequest):
    """Stream AI suggestions via SSE. Events: {t:token}, {done:true,reply,suggestion}."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    messages: list[dict] = [{"role": "system", "content": _ASSIST_SYSTEM}]
    for m in body.messages:
        messages.append({"role": m.role, "content": m.content})

    async def generate():
        try:
            stream = await client.chat.completions.create(
                model=settings.grok_model,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
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
            yield _sse({
                "done": True,
                "reply": data.get("reply", ""),
                "suggestion": data.get("suggestion", {}),
            })
        except json.JSONDecodeError:
            yield _sse({"done": True, "reply": full, "suggestion": {}})
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

    system_prompt = f"""\
You are a social media analyst for the topic "{topic.name}".
You speak the same language as the user (Chinese if they write Chinese, English for English).
Be concise, insightful, and data-driven. Reference specific posts when relevant.

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

    async def generate():
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
                    yield _sse({"t": delta})
            yield _sse({"done": True})
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

"""Topics CRUD API — create, list, update, delete monitoring topics."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from openai import AsyncOpenAI
from pydantic import BaseModel

from api.deps import get_queue
from shared.config.settings import get_settings
from shared.db.engine import get_session_factory
from shared.db.models import TopicRow
from shared.models.task import Task, TaskPriority
from sqlalchemy import select

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


async def _dispatch_plan(topic: TopicRow) -> str:
    """Push an analyst:plan task for the given topic. Returns task ID."""
    queue = get_queue()
    task = Task(
        label="analyst:plan",
        priority=TaskPriority.MEDIUM,
        payload={
            "topic_id": str(topic.id),
            "name": topic.name,
            "platforms": topic.platforms,
            "keywords": topic.keywords,
            "config": topic.config,
        },
    )
    await queue.push(task)
    return task.id


# ── Endpoints ───────────────────────────────────────


@router.post("/topics")
async def create_topic(body: TopicCreate) -> dict:
    """Create a new topic and immediately trigger analyst:plan."""
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

        plan_task_id = await _dispatch_plan(topic)

        return {
            "topic": _topic_to_dict(topic),
            "plan_task_id": plan_task_id,
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
        return {
            "topics": [_topic_to_dict(t) for t in topics],
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


@router.post("/topics/{topic_id}/refresh")
async def refresh_topic(topic_id: str) -> dict:
    """Manually trigger a new crawl cycle for a topic."""
    factory = get_session_factory()
    async with factory() as session:
        topic = await session.get(TopicRow, topic_id)
        if topic is None:
            return {"error": "Topic not found"}
        if topic.status != "active":
            return {"error": "Topic is not active"}

        plan_task_id = await _dispatch_plan(topic)
        return {"status": "refreshing", "plan_task_id": plan_task_id}


@router.post("/topics/reorder")
async def reorder_topics(body: TopicReorder) -> dict:
    """Bulk update topic positions for drag-drop reordering."""
    factory = get_session_factory()
    async with factory() as session:
        for item in body.items:
            topic = await session.get(TopicRow, item["id"])
            if topic:
                topic.position = item["position"]
        await session.commit()
    return {"status": "ok"}


# ── AI Assist ──────────────────────────────────────────


_ASSIST_SYSTEM = """\
You are a topic configuration assistant for CrossHot AI, a cross-platform social media monitoring system.

The user wants to create a new monitoring topic. Help them define what to monitor.

## Your job
1. Understand what the user wants to monitor
2. Suggest a structured topic configuration
3. Refine based on user feedback

## Supported platforms
- **x** (Twitter/X) — English-dominant, supports hashtags, @mentions
- **xhs** (小红书/Xiaohongshu) — Chinese-dominant, lifestyle/consumer platform

## Guidelines for keywords
- Suggest keywords that are GENERAL search terms, NOT platform-specific syntax
- The system's coordinator handles platform-specific query syntax automatically
- For multi-platform coverage, include BOTH English AND Chinese keywords where relevant
- Include: exact names, aliases, abbreviations, related terms, hashtags (without #)
- Aim for 5-10 diverse keywords for good coverage

## Response format
You MUST respond with valid JSON only, no markdown fences, with this exact structure:
{
  "reply": "Your conversational message to the user (1-3 sentences, can be bilingual)",
  "suggestion": {
    "name": "Short topic name",
    "icon": "single emoji",
    "description": "1-2 sentence description of what this topic monitors",
    "platforms": ["x", "xhs"],
    "keywords": ["keyword1", "keyword2", "..."]
  }
}

Always include both "reply" and "suggestion" in every response.
Refine the suggestion based on user feedback in follow-up messages.
"""


@router.post("/topics/assist")
async def assist_topic(body: TopicAssistRequest) -> dict:
    """Use AI to suggest topic configuration from natural language input."""
    settings = get_settings()
    if not settings.grok_api_key:
        return {"error": "Grok API key not configured"}

    client = AsyncOpenAI(
        api_key=settings.grok_api_key,
        base_url=settings.grok_base_url,
    )

    messages = [{"role": "system", "content": _ASSIST_SYSTEM}]
    for m in body.messages:
        messages.append({"role": m.role, "content": m.content})

    try:
        resp = await client.chat.completions.create(
            model=settings.grok_model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
        )
        raw = resp.choices[0].message.content or "{}"

        # Parse JSON response — strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        import json
        data = json.loads(text)
        return {
            "reply": data.get("reply", ""),
            "suggestion": data.get("suggestion", {}),
        }
    except json.JSONDecodeError:
        logger.warning("AI assist returned non-JSON: %s", raw[:200])
        return {"reply": raw, "suggestion": {}}
    except Exception as e:
        logger.exception("AI assist error")
        return {"error": str(e)}

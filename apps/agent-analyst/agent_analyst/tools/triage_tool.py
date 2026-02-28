"""Tool: triage_contents — batch classify unprocessed content."""

import json
import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.tools.base import Tool

from agent_analyst.prompts import build_triage_prompt
from agent_analyst.tools.query import (
    mark_contents_processed,
    query_unprocessed_contents,
)
from agent_analyst.tools.topic import get_entity_config

logger = logging.getLogger(__name__)


def make_triage_tool(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client: AsyncOpenAI,
    fast_model: str,
) -> Tool:
    """Create the triage_contents tool."""

    async def triage_contents(
        entity_type: str,
        entity_id: str,
        downgrade_detail: bool = False,
    ) -> str:
        """Classify unprocessed content into skip/brief/detail."""
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        # Load entity config for context
        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id
        )
        if "error" in entity:
            return json.dumps(entity, ensure_ascii=False)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

        # Query unprocessed content
        unprocessed = await query_unprocessed_contents(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        if not unprocessed:
            return json.dumps({
                "status": "no_content",
                "message": "No unprocessed content found",
                "detail_content_ids": [],
            }, ensure_ascii=False)

        # LLM triage
        triage_results = await _llm_triage(entity, unprocessed, llm_client, fast_model)
        triage_updates, detail_ids = _process_triage_results(
            unprocessed, triage_results
        )

        # In summarize mode, downgrade detail_pending to briefed
        if downgrade_detail:
            for upd in triage_updates:
                if upd["status"] == "detail_pending":
                    upd["status"] = "briefed"
            detail_ids = []

        # Save to DB
        await mark_contents_processed(session_factory, triage_updates)

        counts = {
            "total": len(unprocessed),
            "briefed": sum(1 for u in triage_updates if u["status"] == "briefed"),
            "detail_pending": sum(
                1 for u in triage_updates if u["status"] == "detail_pending"
            ),
            "skipped": sum(1 for u in triage_updates if u["status"] == "skipped"),
        }
        logger.info(
            "Triage: %d unprocessed → %d briefed, %d detail, %d skipped",
            counts["total"],
            counts["briefed"],
            counts["detail_pending"],
            counts["skipped"],
        )

        return json.dumps({
            "status": "done",
            "counts": counts,
            "detail_content_ids": detail_ids,
        }, ensure_ascii=False)

    return Tool(
        name="triage_contents",
        description=(
            "Classify unprocessed content for processing depth (skip/brief/detail). "
            "Call after get_overview to process new content."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["topic", "user"],
                },
                "entity_id": {
                    "type": "string",
                    "description": "UUID of the topic or user",
                },
                "downgrade_detail": {
                    "type": "boolean",
                    "description": (
                        "If true, downgrade detail_pending to briefed "
                        "(use in summarize phase when no more detail tasks will be dispatched)"
                    ),
                    "default": False,
                },
            },
            "required": ["entity_type", "entity_id"],
        },
        func=triage_contents,
    )


async def _llm_triage(
    entity: dict,
    posts: list[dict],
    llm_client: AsyncOpenAI,
    fast_model: str,
) -> list[dict]:
    """Batch triage using fast model."""
    prompt = build_triage_prompt(entity, posts)
    try:
        response = await llm_client.chat.completions.create(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or "[]"
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        results = json.loads(raw)
        if not isinstance(results, list) or len(results) != len(posts):
            logger.warning(
                "Triage length mismatch: got %d, expected %d. Defaulting to brief.",
                len(results) if isinstance(results, list) else 0,
                len(posts),
            )
            return [{"d": "brief", "kp": None} for _ in posts]
        return results
    except Exception as e:
        logger.warning("Triage LLM call failed (%s), defaulting to brief", e)
        return [{"d": "brief", "kp": None} for _ in posts]


def _process_triage_results(
    posts: list[dict],
    triage_results: list[dict],
) -> tuple[list[dict], list[str]]:
    """Convert triage LLM output to mark_contents_processed updates."""
    updates = []
    detail_ids = []

    for post, tri in zip(posts, triage_results):
        decision = tri.get("d", "brief")
        key_points = tri.get("kp")

        if decision == "skip":
            updates.append({"id": post["id"], "status": "skipped", "key_points": None})
        elif decision == "detail":
            updates.append({
                "id": post["id"],
                "status": "detail_pending",
                "key_points": key_points,
            })
            detail_ids.append(post["id"])
        else:
            updates.append({
                "id": post["id"],
                "status": "briefed",
                "key_points": key_points,
            })

    return updates, detail_ids

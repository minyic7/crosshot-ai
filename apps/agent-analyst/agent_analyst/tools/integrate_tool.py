"""Tool: integrate_knowledge — update knowledge document with new content."""

import json
import logging

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.tools.base import Tool

from agent_analyst.prompts import build_integration_prompt, build_system_prompt
from agent_analyst.tools.query import (
    mark_integrated,
    query_entity_overview,
    query_integration_ready,
)
from agent_analyst.tools.summary import update_entity_summary
from agent_analyst.tools.topic import get_entity_config, get_knowledge_doc

logger = logging.getLogger(__name__)


def make_integrate_tool(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client: AsyncOpenAI,
    model: str,
) -> Tool:
    """Create the integrate_knowledge tool."""

    async def integrate_knowledge(
        entity_type: str,
        entity_id: str,
        is_preliminary: bool = True,
        chat_insights: str = "",
    ) -> str:
        """Integrate new content into the knowledge document and produce a summary."""
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id
        )
        if "error" in entity:
            return json.dumps(entity, ensure_ascii=False)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

        # Load overview for metrics context
        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in overview:
            return json.dumps(overview, ensure_ascii=False)

        # Query integration-ready content
        integration_ready = await query_integration_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )

        knowledge_doc = get_knowledge_doc(entity)

        if not integration_ready:
            # No new content to integrate — save current state
            await update_entity_summary(
                session_factory,
                topic_id=topic_id,
                user_id=user_id,
                summary=entity.get("last_summary", ""),
                summary_data={
                    "knowledge": knowledge_doc,
                    "metrics": overview["metrics"],
                    "insights": [],
                    "recommended_next_queries": entity.get(
                        "previous_recommendations", []
                    ),
                },
                total_contents=overview["data_status"]["total_contents_all_time"],
                is_preliminary=is_preliminary,
            )
            return json.dumps({
                "status": "no_content",
                "message": "No integration-ready content found. Saved current state.",
            }, ensure_ascii=False)

        # LLM integration
        analysis = await _llm_integrate(
            entity, overview, knowledge_doc, integration_ready,
            llm_client, model, chat_insights,
        )
        knowledge_doc = analysis.get("knowledge", knowledge_doc)

        # Save updated knowledge + summary
        await update_entity_summary(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            summary=analysis.get("summary", ""),
            summary_data={
                "knowledge": knowledge_doc,
                "metrics": overview["metrics"],
                "insights": _normalize_insights(analysis),
                "recommended_next_queries": analysis.get(
                    "recommended_next_queries", []
                ),
            },
            total_contents=overview["data_status"]["total_contents_all_time"],
            is_preliminary=is_preliminary,
        )

        # Mark content as integrated
        integrated_ids = [p["id"] for p in integration_ready]
        await mark_integrated(session_factory, integrated_ids)
        logger.info("Integrated %d contents into knowledge", len(integrated_ids))

        return json.dumps({
            "status": "done",
            "integrated_count": len(integrated_ids),
            "summary_length": len(analysis.get("summary", "")),
            "insights_count": len(analysis.get("insights", [])),
        }, ensure_ascii=False)

    return Tool(
        name="integrate_knowledge",
        description=(
            "Integrate new content into the persistent knowledge document. "
            "Updates the knowledge, writes a summary, and marks content as processed. "
            "Call after triage_contents."
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
                "is_preliminary": {
                    "type": "boolean",
                    "description": (
                        "True if crawling may follow (won't update last_crawl_at). "
                        "False for final summary."
                    ),
                    "default": True,
                },
                "chat_insights": {
                    "type": "string",
                    "description": "User conversation insights to prioritize",
                    "default": "",
                },
            },
            "required": ["entity_type", "entity_id"],
        },
        func=integrate_knowledge,
    )


async def _llm_integrate(
    entity: dict,
    overview: dict,
    knowledge_doc: str,
    content: list[dict],
    llm_client: AsyncOpenAI,
    model: str,
    chat_insights: str = "",
) -> dict:
    """Knowledge integration using reasoning model."""
    prompt = build_integration_prompt(
        entity, overview, knowledge_doc, content, chat_insights
    )
    try:
        response = await llm_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        raw = response.choices[0].message.content or "{}"
        result = json.loads(raw)
        logger.info(
            "Integration LLM: knowledge=%d chars, summary=%d chars",
            len(result.get("knowledge", "")),
            len(result.get("summary", "")),
        )
        return result
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON: %s", e)
        return {
            "summary": "",
            "knowledge": knowledge_doc,
            "insights": [{"text": f"JSON parse error: {e}", "sentiment": "negative"}],
        }
    except Exception as e:
        logger.error("Integration LLM call failed: %s", e)
        return {
            "summary": "",
            "knowledge": knowledge_doc,
            "insights": [{"text": f"LLM error: {e}", "sentiment": "negative"}],
        }


def _normalize_insights(analysis: dict) -> list[dict]:
    """Convert LLM output to uniform insight format."""
    if "insights" in analysis:
        raw = analysis["insights"]
        if isinstance(raw, list):
            result = []
            for item in raw:
                if isinstance(item, dict) and "text" in item:
                    result.append({
                        "text": item["text"],
                        "sentiment": item.get("sentiment", "neutral"),
                    })
                elif isinstance(item, str):
                    result.append({"text": item, "sentiment": "neutral"})
            return result
    return []

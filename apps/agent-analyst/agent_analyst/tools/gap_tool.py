"""Tool: analyze_gaps — detect data gaps and plan crawl tasks."""

import json
import logging
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.tools.base import Tool

from agent_analyst.prompts import build_gap_analysis_prompt, build_system_prompt
from agent_analyst.tools.query import query_entity_overview
from agent_analyst.tools.topic import get_entity_config

logger = logging.getLogger(__name__)


def make_gap_tool(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client: AsyncOpenAI,
    model: str,
) -> Tool:
    """Create the analyze_gaps tool."""

    async def analyze_gaps(
        entity_type: str,
        entity_id: str,
        force_crawl: bool = False,
        chat_insights: str = "",
    ) -> str:
        """Detect data gaps and recommend crawl tasks."""
        topic_id = entity_id if entity_type == "topic" else None
        user_id = entity_id if entity_type == "user" else None

        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id
        )
        if "error" in entity:
            return json.dumps(entity, ensure_ascii=False)

        attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in overview:
            return json.dumps(overview, ensure_ascii=False)

        # Deterministic gap detection
        gaps = _detect_gaps(entity, overview, force_crawl)
        logger.info(
            "Gap detection: missing_platforms=%s stale=%s low_volume=%s force=%s",
            gaps["missing_platforms"],
            gaps["stale"],
            gaps["low_volume"],
            gaps["force_crawl"],
        )

        # Check if attached users have been crawled at least once
        users_never_crawled = [
            u for u in entity.get("users", []) if not u.get("last_crawl_at")
        ]
        skip_search = bool(users_never_crawled) and topic_id is not None

        has_gaps = (
            gaps["missing_platforms"]
            or gaps["stale"]
            or gaps["low_volume"]
            or gaps["force_crawl"]
        )

        crawl_tasks: list[dict] = []
        if has_gaps and not skip_search:
            knowledge_doc = _get_knowledge_doc(entity)
            gap_analysis = await _llm_gap_analysis(
                entity, overview, gaps, knowledge_doc,
                llm_client, model, chat_insights,
            )
            crawl_tasks = gap_analysis.get("crawl_tasks", [])

        result: dict[str, Any] = {
            "gaps": gaps,
            "skip_search": skip_search,
            "crawl_tasks": crawl_tasks,
        }
        if skip_search:
            result["skip_reason"] = (
                f"{len(users_never_crawled)} attached user(s) never crawled — "
                "prioritize user timelines first"
            )

        return json.dumps(result, ensure_ascii=False, default=str)

    return Tool(
        name="analyze_gaps",
        description=(
            "Detect data freshness gaps and recommend crawl tasks. "
            "Returns gap analysis results and suggested crawl queries. "
            "Use dispatch_tasks to execute the recommendations."
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
                "force_crawl": {
                    "type": "boolean",
                    "description": "Force crawling regardless of freshness",
                    "default": False,
                },
                "chat_insights": {
                    "type": "string",
                    "description": "User conversation insights to prioritize",
                    "default": "",
                },
            },
            "required": ["entity_type", "entity_id"],
        },
        func=analyze_gaps,
    )


def _detect_gaps(entity: dict, overview: dict, force_crawl: bool) -> dict:
    """Deterministic gap detection — no LLM needed."""
    gaps: dict[str, Any] = {
        "missing_platforms": [],
        "stale": False,
        "low_volume": False,
        "force_crawl": force_crawl,
    }

    coverage = overview["data_status"]["platform_coverage"]
    for platform in entity.get("platforms", []):
        if platform not in coverage:
            gaps["missing_platforms"].append(platform)

    hours_since = overview["data_status"]["hours_since_newest_content"]
    interval = entity.get("config", {}).get("schedule_interval_hours", 6)
    if hours_since is not None and hours_since > interval * 1.5:
        gaps["stale"] = True

    # Only flag low_volume if we haven't crawled recently.
    # Prevents infinite loop when crawlers can't find data.
    if overview["data_status"]["total_contents_all_time"] < 10:
        hours_since_crawl = overview["data_status"].get("hours_since_last_crawl")
        if hours_since_crawl is None or hours_since_crawl > interval:
            gaps["low_volume"] = True

    return gaps


async def _llm_gap_analysis(
    entity: dict,
    overview: dict,
    gaps: dict,
    knowledge_doc: str,
    llm_client: AsyncOpenAI,
    model: str,
    chat_insights: str = "",
) -> dict:
    """Gap analysis using reasoning model."""
    prompt = build_gap_analysis_prompt(
        entity, overview, gaps, knowledge_doc, chat_insights
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
        return json.loads(raw)
    except Exception as e:
        logger.error("Gap analysis LLM call failed: %s", e)
        return {"crawl_tasks": []}


def _get_knowledge_doc(entity: dict) -> str:
    """Extract knowledge document from entity's summary_data."""
    summary_data = entity.get("summary_data") or {}
    if isinstance(summary_data, dict):
        return summary_data.get("knowledge", "")
    return ""

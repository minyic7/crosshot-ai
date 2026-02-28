"""Backfill analysis: triage + integrate all unprocessed content.

Processes unprocessed content in batches:
1. Triage phase: classify as skip/brief/detail (fast model, 100 per batch)
2. Integration phase: update knowledge doc + summary (reasoning model, 200 per batch)

Run inside the analyst container:
    docker compose exec -T analyst uv run --package agent-analyst \
        python /app/apps/shared/scripts/backfill_analysis.py

Options:
    --dry-run           Preview without saving
    --entity-type       Filter to topic or user
    --entity-id         Process a specific entity
    --triage-only       Only run triage phase
    --integrate-only    Only run integration phase
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill")


async def find_entities_with_unprocessed(
    session_factory: async_sessionmaker[AsyncSession],
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> list[tuple[str, str, str, int]]:
    """Find entities with unprocessed content.

    Returns list of (entity_type, entity_id, entity_name, unprocessed_count).
    """
    async with session_factory() as session:
        if entity_id:
            # Specific entity
            etype = entity_type or "topic"
            if etype == "topic":
                result = await session.execute(
                    text("""
                        SELECT 'topic' as etype, t.id::text, t.name,
                               COUNT(c.id) as unprocessed
                        FROM topics t
                        LEFT JOIN contents c ON c.topic_id = t.id
                            AND c.processing_status IS NULL
                        WHERE t.id = :eid
                        GROUP BY t.id, t.name
                    """),
                    {"eid": entity_id},
                )
            else:
                result = await session.execute(
                    text("""
                        SELECT 'user' as etype, u.id::text, u.name,
                               COUNT(c.id) as unprocessed
                        FROM users u
                        LEFT JOIN contents c ON c.user_id = u.id
                            AND c.processing_status IS NULL
                            AND c.topic_id IS NULL
                        WHERE u.id = :eid
                        GROUP BY u.id, u.name
                    """),
                    {"eid": entity_id},
                )
            rows = result.fetchall()
            return [(r[0], r[1], r[2], r[3]) for r in rows if r[3] > 0]

        # Find all entities with unprocessed content
        parts = []
        if entity_type in (None, "topic"):
            parts.append("""
                SELECT 'topic' as etype, t.id::text, t.name,
                       COUNT(c.id) as unprocessed
                FROM topics t
                JOIN contents c ON c.topic_id = t.id
                    AND c.processing_status IS NULL
                GROUP BY t.id, t.name
            """)
        if entity_type in (None, "user"):
            parts.append("""
                SELECT 'user' as etype, u.id::text, u.name,
                       COUNT(c.id) as unprocessed
                FROM users u
                JOIN contents c ON c.user_id = u.id
                    AND c.processing_status IS NULL
                    AND c.topic_id IS NULL
                GROUP BY u.id, u.name
            """)

        query = " UNION ALL ".join(parts) + " ORDER BY unprocessed DESC"
        result = await session.execute(text(query))
        return [(r[0], r[1], r[2], r[3]) for r in result]


async def run_triage(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client,
    fast_model: str,
    entity_type: str,
    entity_id: str,
    dry_run: bool = False,
) -> int:
    """Triage all unprocessed content for an entity in batches of 100."""
    from agent_analyst.tools.query import (
        mark_contents_processed,
        query_unprocessed_contents,
    )
    from agent_analyst.tools.topic import get_entity_config
    from agent_analyst.tools.triage_tool import _llm_triage, _process_triage_results

    topic_id = entity_id if entity_type == "topic" else None
    user_id = entity_id if entity_type == "user" else None

    entity = await get_entity_config(
        session_factory, topic_id=topic_id, user_id=user_id,
    )
    if "error" in entity:
        logger.error("Entity config error: %s", entity["error"])
        return 0

    attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

    total_triaged = 0
    batch_num = 0

    while True:
        batch_num += 1
        unprocessed = await query_unprocessed_contents(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if not unprocessed:
            break

        logger.info("  Triage batch %d: %d items", batch_num, len(unprocessed))

        # LLM triage
        t0 = time.monotonic()
        triage_results = await _llm_triage(entity, unprocessed, llm_client, fast_model)
        elapsed = time.monotonic() - t0
        updates, _detail_ids = _process_triage_results(unprocessed, triage_results)

        # Downgrade detail_pending → briefed (no crawler will run during backfill)
        for upd in updates:
            if upd["status"] == "detail_pending":
                upd["status"] = "briefed"

        counts = {
            "briefed": sum(1 for u in updates if u["status"] == "briefed"),
            "skipped": sum(1 for u in updates if u["status"] == "skipped"),
        }
        logger.info(
            "    → briefed: %d, skipped: %d (%.1fs)",
            counts["briefed"], counts["skipped"], elapsed,
        )

        if not dry_run:
            await mark_contents_processed(session_factory, updates)

        total_triaged += len(unprocessed)

    return total_triaged


async def run_integration(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client,
    model: str,
    entity_type: str,
    entity_id: str,
    dry_run: bool = False,
) -> int:
    """Integrate all triaged content for an entity in batches of 200."""
    from agent_analyst.prompts import build_integration_prompt, build_system_prompt
    from agent_analyst.tools.query import (
        mark_integrated,
        query_entity_overview,
        query_integration_ready,
    )
    from agent_analyst.tools.summary import update_entity_summary
    from agent_analyst.tools.topic import get_entity_config, get_knowledge_doc

    topic_id = entity_id if entity_type == "topic" else None
    user_id = entity_id if entity_type == "user" else None

    entity = await get_entity_config(
        session_factory, topic_id=topic_id, user_id=user_id,
    )
    if "error" in entity:
        logger.error("Entity config error: %s", entity["error"])
        return 0

    attached_user_ids = [u["user_id"] for u in entity.get("users", [])]

    total_integrated = 0
    batch_num = 0

    while True:
        batch_num += 1

        # Refresh entity config each iteration (knowledge_doc gets updated)
        entity = await get_entity_config(
            session_factory, topic_id=topic_id, user_id=user_id,
        )
        knowledge_doc = get_knowledge_doc(entity)

        overview = await query_entity_overview(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if "error" in overview:
            logger.error("Overview error: %s", overview["error"])
            break

        ready = await query_integration_ready(
            session_factory,
            topic_id=topic_id,
            user_id=user_id,
            user_ids=attached_user_ids or None,
        )
        if not ready:
            break

        logger.info("  Integration batch %d: %d items", batch_num, len(ready))

        # LLM integration
        t0 = time.monotonic()
        prompt = build_integration_prompt(
            entity, overview, knowledge_doc, ready,
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
            import json

            raw = response.choices[0].message.content or "{}"
            analysis = json.loads(raw)
        except Exception as e:
            logger.error("Integration LLM failed: %s", e)
            analysis = {
                "summary": "",
                "knowledge": knowledge_doc,
                "insights": [],
            }
        elapsed = time.monotonic() - t0

        new_knowledge = analysis.get("knowledge", knowledge_doc)
        logger.info(
            "    → knowledge: %d chars, summary: %d chars (%.1fs)",
            len(new_knowledge),
            len(analysis.get("summary", "")),
            elapsed,
        )

        if not dry_run:
            # Normalize insights
            insights = []
            for item in analysis.get("insights", []):
                if isinstance(item, dict) and "text" in item:
                    insights.append({
                        "text": item["text"],
                        "sentiment": item.get("sentiment", "neutral"),
                    })
                elif isinstance(item, str):
                    insights.append({"text": item, "sentiment": "neutral"})

            await update_entity_summary(
                session_factory,
                topic_id=topic_id,
                user_id=user_id,
                summary=analysis.get("summary", ""),
                summary_data={
                    "knowledge": new_knowledge,
                    "metrics": overview.get("metrics", {}),
                    "insights": insights,
                    "recommended_next_queries": analysis.get(
                        "recommended_next_queries", []
                    ),
                },
                total_contents=overview.get("data_status", {}).get(
                    "total_contents_all_time"
                ),
                is_preliminary=False,
            )

            integrated_ids = [p["id"] for p in ready]
            await mark_integrated(session_factory, integrated_ids)

        total_integrated += len(ready)

    return total_integrated


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill triage + integration for unprocessed content",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument(
        "--entity-type", choices=["topic", "user"],
        help="Filter to specific entity type",
    )
    parser.add_argument("--entity-id", help="Process a specific entity ID")
    parser.add_argument(
        "--triage-only", action="store_true",
        help="Only run triage phase (skip integration)",
    )
    parser.add_argument(
        "--integrate-only", action="store_true",
        help="Only run integration phase (skip triage)",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no changes will be saved")

    # Setup DB
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL not set")
        sys.exit(1)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

    # Setup LLM
    from openai import AsyncOpenAI

    api_key = os.environ.get("XAI_API_KEY", os.environ.get("GROK_API_KEY", ""))
    base_url = os.environ.get("GROK_BASE_URL", "https://api.x.ai/v1")
    if not api_key:
        logger.error("XAI_API_KEY / GROK_API_KEY not set")
        sys.exit(1)

    llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    fast_model = os.environ.get("GROK_FAST_MODEL", "grok-4-1-fast-non-reasoning")
    reasoning_model = os.environ.get("GROK_MODEL", "grok-4-1-fast-reasoning")

    logger.info("Models: triage=%s, integration=%s", fast_model, reasoning_model)

    # Find entities with unprocessed content
    entities = await find_entities_with_unprocessed(
        session_factory, args.entity_type, args.entity_id,
    )
    if not entities:
        logger.info("No entities with unprocessed content found.")
        await engine.dispose()
        return

    logger.info(
        "Found %d entities with unprocessed content:", len(entities),
    )
    for etype, eid, ename, count in entities:
        logger.info("  %s '%s' (%s): %d unprocessed", etype, ename, eid, count)

    # Process each entity
    grand_triaged = 0
    grand_integrated = 0
    t_start = time.monotonic()

    for etype, eid, ename, count in entities:
        logger.info("=" * 60)
        logger.info("Processing %s '%s' — %d unprocessed", etype, ename, count)

        if not args.integrate_only:
            triaged = await run_triage(
                session_factory, llm_client, fast_model,
                etype, eid, args.dry_run,
            )
            grand_triaged += triaged
            logger.info("Triage complete: %d items for %s '%s'", triaged, etype, ename)

        if not args.triage_only:
            integrated = await run_integration(
                session_factory, llm_client, reasoning_model,
                etype, eid, args.dry_run,
            )
            grand_integrated += integrated
            logger.info(
                "Integration complete: %d items for %s '%s'",
                integrated, etype, ename,
            )

    elapsed = time.monotonic() - t_start
    logger.info("=" * 60)
    logger.info(
        "DONE — triaged: %d, integrated: %d, elapsed: %.0fs",
        grand_triaged, grand_integrated, elapsed,
    )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

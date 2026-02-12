"""Content query functions for the incremental knowledge pipeline.

Provides focused queries for each pipeline stage:
- query_entity_overview: metrics + data status (deterministic)
- query_unprocessed_contents: for triage (processing_status IS NULL)
- query_integration_ready: for knowledge integration (briefed/detail_ready)
- mark_contents_processed: batch update processing_status + key_points
- mark_detail_ready: upgrade detail_pending → detail_ready after crawler returns
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow, UserRow

logger = logging.getLogger(__name__)

TRIAGE_BATCH_LIMIT = 100
INTEGRATION_BATCH_LIMIT = 200


def _build_content_filter(
    topic_id: str | None,
    user_ids: list[str] | None,
) -> tuple[str, dict]:
    """Build a SQL WHERE fragment + params for content ownership filtering."""
    ids = list(user_ids or [])
    if topic_id and ids:
        return "(topic_id = :topic_id OR user_id = ANY(:user_ids))", {
            "topic_id": topic_id, "user_ids": ids,
        }
    elif topic_id:
        return "topic_id = :topic_id", {"topic_id": topic_id}
    elif ids:
        return "user_id = ANY(:user_ids)", {"user_ids": ids}
    else:
        return "FALSE", {}


async def query_entity_overview(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
    user_ids: list[str] | None = None,
) -> dict:
    """Query aggregate metrics + data status for gap detection and context.

    No LLM calls — pure SQL aggregation.
    """
    all_user_ids = list(user_ids or [])
    if user_id and user_id not in all_user_ids:
        all_user_ids.append(user_id)

    async with session_factory() as session:
        if topic_id:
            entity = await session.get(TopicRow, topic_id)
            if entity is None:
                return {"error": f"Topic {topic_id} not found"}
            since_dt = entity.last_crawl_at or entity.created_at
            entity_config = entity.config
            entity_last_summary = entity.last_summary
            entity_summary_data = entity.summary_data
            entity_platforms = entity.platforms or []
        elif user_id:
            entity = await session.get(UserRow, user_id)
            if entity is None:
                return {"error": f"User {user_id} not found"}
            since_dt = entity.last_crawl_at or entity.created_at
            entity_config = entity.config
            entity_last_summary = entity.last_summary
            entity_summary_data = entity.summary_data
            entity_platforms = [entity.platform]
        else:
            return {"error": "Must provide either topic_id or user_id"}

        where, base_params = _build_content_filter(topic_id, all_user_ids or None)
        params = {**base_params, "since": since_dt}

        # Aggregate metrics since last crawl
        agg_result = await session.execute(
            text(f"""
                SELECT
                    platform,
                    COUNT(*) as total,
                    COALESCE(SUM((metrics->>'like_count')::int), 0) as total_likes,
                    COALESCE(SUM((metrics->>'retweet_count')::int), 0) as total_retweets,
                    COALESCE(SUM((metrics->>'reply_count')::int), 0) as total_replies,
                    COALESCE(SUM((metrics->>'views_count')::int), 0) as total_views
                FROM contents
                WHERE {where} AND crawled_at > :since
                GROUP BY platform
            """),
            params,
        )
        platform_metrics = {}
        grand_total = grand_likes = grand_retweets = grand_replies = grand_views = 0
        for row in agg_result:
            platform_metrics[row.platform] = row.total
            grand_total += row.total
            grand_likes += row.total_likes
            grand_retweets += row.total_retweets
            grand_replies += row.total_replies
            grand_views += row.total_views

        # Media count
        media_result = await session.execute(
            text(f"""
                SELECT COUNT(*) as with_media
                FROM contents
                WHERE {where} AND crawled_at > :since
                  AND data->'media' IS NOT NULL
                  AND jsonb_array_length(data->'media') > 0
            """),
            params,
        )
        with_media = media_result.scalar() or 0
        media_pct = round(with_media * 100 / grand_total) if grand_total > 0 else 0

        # Top authors
        authors_result = await session.execute(
            text(f"""
                SELECT author_username as username,
                       COUNT(*) as posts,
                       SUM(COALESCE((metrics->>'like_count')::int, 0) +
                           COALESCE((metrics->>'retweet_count')::int, 0)) as engagement
                FROM contents
                WHERE {where} AND crawled_at > :since
                      AND author_username IS NOT NULL
                GROUP BY author_username
                ORDER BY engagement DESC
                LIMIT 5
            """),
            params,
        )
        top_authors = [
            {"username": r.username, "posts": r.posts, "engagement": r.engagement}
            for r in authors_result
        ]

        # Previous cycle
        prev_metrics = {}
        prev_summary = ""
        if entity_summary_data and isinstance(entity_summary_data, dict):
            prev_metrics = entity_summary_data.get("metrics", {})
        if entity_last_summary:
            prev_summary = entity_last_summary

        # Data status — all-time coverage
        now = datetime.now(timezone.utc)
        coverage_result = await session.execute(
            text(f"""
                SELECT platform, COUNT(*) as count, MAX(crawled_at) as newest_at
                FROM contents
                WHERE {where}
                GROUP BY platform
            """),
            {k: v for k, v in base_params.items()},
        )
        platform_coverage = {}
        total_all_time = 0
        newest_overall = None
        for row in coverage_result:
            platform_coverage[row.platform] = {
                "count": row.count,
                "newest_at": row.newest_at.isoformat() if row.newest_at else None,
            }
            total_all_time += row.count
            if row.newest_at and (newest_overall is None or row.newest_at > newest_overall):
                newest_overall = row.newest_at

        # Unprocessed count
        unprocessed_result = await session.execute(
            text(f"""
                SELECT COUNT(*) FROM contents
                WHERE {where} AND processing_status IS NULL
            """),
            {k: v for k, v in base_params.items()},
        )
        unprocessed_count = unprocessed_result.scalar() or 0

        last_crawl_at = entity.last_crawl_at if hasattr(entity, "last_crawl_at") else None
        hours_since_newest = (
            round((now - newest_overall).total_seconds() / 3600, 1)
            if newest_overall else None
        )
        hours_since_last_crawl = (
            round((now - last_crawl_at).total_seconds() / 3600, 1)
            if last_crawl_at else None
        )
        configured_interval = entity_config.get("schedule_interval_hours", 6)

        return {
            "time_window": {
                "since": since_dt.isoformat(),
                "until": now.isoformat(),
            },
            "data_status": {
                "total_contents_all_time": total_all_time,
                "unprocessed_count": unprocessed_count,
                "hours_since_newest_content": hours_since_newest,
                "hours_since_last_crawl": hours_since_last_crawl,
                "configured_interval_hours": configured_interval,
                "has_previous_summary": bool(entity_last_summary),
                "platform_coverage": platform_coverage,
                "configured_platforms": entity_platforms,
            },
            "metrics": {
                "total_contents": grand_total,
                "total_likes": grand_likes,
                "total_retweets": grand_retweets,
                "total_replies": grand_replies,
                "total_views": grand_views,
                "with_media_pct": media_pct,
                "platforms": platform_metrics,
            },
            "top_authors": top_authors,
            "previous_cycle": {
                "metrics": prev_metrics,
                "summary": prev_summary[:500] if prev_summary else "",
            },
        }


async def query_unprocessed_contents(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
    user_ids: list[str] | None = None,
    limit: int = TRIAGE_BATCH_LIMIT,
) -> list[dict]:
    """Query content with processing_status IS NULL for triage.

    Returns compact representation suitable for batch LLM triage.
    Ordered by engagement (most impactful first).
    """
    all_user_ids = list(user_ids or [])
    if user_id and user_id not in all_user_ids:
        all_user_ids.append(user_id)

    where, base_params = _build_content_filter(topic_id, all_user_ids or None)

    async with session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT c.id, c.platform, c.source_url, c.text,
                       c.author_username, c.author_display_name,
                       c.metrics, c.data->'media' as media_json,
                       c.hashtags
                FROM contents c
                WHERE ({where.replace('topic_id', 'c.topic_id').replace('user_id', 'c.user_id')})
                  AND c.processing_status IS NULL
                ORDER BY (
                    COALESCE((c.metrics->>'like_count')::int, 0) +
                    COALESCE((c.metrics->>'retweet_count')::int, 0)
                ) DESC
                LIMIT :lim
            """),
            {**base_params, "lim": limit},
        )

        posts = []
        for row in result:
            media_items = row.media_json or []
            media_types = list({m.get("type", "unknown") for m in media_items}) if media_items else []
            likes = (row.metrics or {}).get("like_count", 0)
            retweets = (row.metrics or {}).get("retweet_count", 0)
            replies = (row.metrics or {}).get("reply_count", 0)
            views = (row.metrics or {}).get("views_count", 0)
            posts.append({
                "id": str(row.id),
                "platform": row.platform,
                "author": row.author_username or row.author_display_name or "",
                "text": row.text or "",
                "likes": likes,
                "retweets": retweets,
                "replies": replies,
                "views": views,
                "url": row.source_url,
                "media_types": media_types,
                "media_count": len(media_items),
                "hashtags": row.hashtags or [],
            })

        logger.info("Queried %d unprocessed contents for triage", len(posts))
        return posts


async def query_integration_ready(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
    user_ids: list[str] | None = None,
    limit: int = INTEGRATION_BATCH_LIMIT,
) -> list[dict]:
    """Query content ready for knowledge integration.

    Returns contents with processing_status IN ('briefed', 'detail_ready')
    along with their key_points.
    """
    all_user_ids = list(user_ids or [])
    if user_id and user_id not in all_user_ids:
        all_user_ids.append(user_id)

    where, base_params = _build_content_filter(topic_id, all_user_ids or None)

    async with session_factory() as session:
        result = await session.execute(
            text(f"""
                SELECT c.id, c.platform, c.source_url, c.text,
                       c.author_username, c.author_display_name,
                       c.metrics, c.key_points, c.processing_status,
                       c.data->'media' as media_json,
                       c.hashtags, c.crawled_at
                FROM contents c
                WHERE ({where.replace('topic_id', 'c.topic_id').replace('user_id', 'c.user_id')})
                  AND c.processing_status IN ('briefed', 'detail_ready')
                ORDER BY c.crawled_at DESC
                LIMIT :lim
            """),
            {**base_params, "lim": limit},
        )

        posts = []
        for row in result:
            likes = (row.metrics or {}).get("like_count", 0)
            retweets = (row.metrics or {}).get("retweet_count", 0)
            views = (row.metrics or {}).get("views_count", 0)
            posts.append({
                "id": str(row.id),
                "platform": row.platform,
                "author": row.author_username or row.author_display_name or "",
                "text": row.text or "",
                "likes": likes,
                "retweets": retweets,
                "views": views,
                "url": row.source_url,
                "key_points": row.key_points,
                "processing_status": row.processing_status,
                "hashtags": row.hashtags or [],
                "crawled_at": row.crawled_at.isoformat() if row.crawled_at else None,
            })

        logger.info("Queried %d integration-ready contents", len(posts))
        return posts


async def mark_contents_processed(
    session_factory: async_sessionmaker[AsyncSession],
    updates: list[dict],
) -> int:
    """Batch update processing_status and key_points for triaged contents.

    Each update: {"id": content_id, "status": "briefed"|"skipped"|"detail_pending", "key_points": [...] | None}
    Returns number of rows updated.
    """
    if not updates:
        return 0

    updated = 0
    async with session_factory() as session:
        for upd in updates:
            content_id = upd["id"]
            status = upd["status"]
            key_points = upd.get("key_points")

            if key_points is not None:
                # Serialize to JSON string for JSONB column via text() binding
                kp_json = json.dumps(key_points, ensure_ascii=False) if not isinstance(key_points, str) else key_points
                await session.execute(
                    text("""
                        UPDATE contents
                        SET processing_status = :status, key_points = :kp::jsonb
                        WHERE id = :cid
                    """),
                    {"cid": content_id, "status": status, "kp": kp_json},
                )
            else:
                await session.execute(
                    text("""
                        UPDATE contents
                        SET processing_status = :status
                        WHERE id = :cid
                    """),
                    {"cid": content_id, "status": status},
                )
            updated += 1
        await session.commit()

    logger.info("Marked %d contents processed", updated)
    return updated


async def mark_integrated(
    session_factory: async_sessionmaker[AsyncSession],
    content_ids: list[str],
) -> int:
    """Mark contents as integrated into the knowledge document."""
    if not content_ids:
        return 0

    async with session_factory() as session:
        result = await session.execute(
            text("""
                UPDATE contents
                SET processing_status = 'integrated'
                WHERE id = ANY(:ids) AND processing_status IN ('briefed', 'detail_ready')
            """),
            {"ids": content_ids},
        )
        await session.commit()
        count = result.rowcount
        logger.info("Marked %d contents as integrated", count)
        return count


async def mark_detail_ready(
    session_factory: async_sessionmaker[AsyncSession],
    topic_id: str | None = None,
    user_id: str | None = None,
    user_ids: list[str] | None = None,
) -> int:
    """Upgrade detail_pending → detail_ready for contents whose details have been fetched.

    A detail is considered fetched when reply content exists for the same tweet_id.
    """
    all_user_ids = list(user_ids or [])
    if user_id and user_id not in all_user_ids:
        all_user_ids.append(user_id)

    where, base_params = _build_content_filter(topic_id, all_user_ids or None)

    async with session_factory() as session:
        # Simply upgrade all detail_pending to detail_ready
        # (the crawler has completed its fan-in, so all detail fetches are done)
        result = await session.execute(
            text(f"""
                UPDATE contents
                SET processing_status = 'detail_ready'
                WHERE ({where}) AND processing_status = 'detail_pending'
            """),
            base_params,
        )
        await session.commit()
        count = result.rowcount
        if count:
            logger.info("Upgraded %d contents from detail_pending to detail_ready", count)
        return count

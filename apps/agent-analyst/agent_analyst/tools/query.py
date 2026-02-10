"""query_topic_contents tool — SQL aggregation + token-budget sampling from PG."""

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow
from shared.tools.base import Tool

TOKEN_BUDGET = 8000


def make_query_topic_contents(
    session_factory: async_sessionmaker[AsyncSession],
) -> Tool:
    """Factory: create tool that queries and pre-processes topic content from PG."""

    async def _query_topic_contents(topic_id: str) -> dict:
        async with session_factory() as session:
            # Load topic for time window
            topic = await session.get(TopicRow, topic_id)
            if topic is None:
                return {"error": f"Topic {topic_id} not found"}

            # Time window: since last_crawl_at (previous cycle end), or created_at for first cycle
            since_dt = topic.last_crawl_at or topic.created_at

            # 1. SQL Aggregation — accurate metrics over full dataset
            agg_result = await session.execute(
                text("""
                    SELECT
                        platform,
                        COUNT(*) as total,
                        COALESCE(SUM((metrics->>'like_count')::int), 0) as total_likes,
                        COALESCE(SUM((metrics->>'retweet_count')::int), 0) as total_retweets,
                        COALESCE(SUM((metrics->>'reply_count')::int), 0) as total_replies,
                        COALESCE(SUM((metrics->>'views_count')::int), 0) as total_views
                    FROM contents
                    WHERE topic_id = :topic_id AND crawled_at > :since
                    GROUP BY platform
                """),
                {"topic_id": topic_id, "since": since_dt},
            )
            platform_metrics = {}
            grand_total = 0
            grand_likes = 0
            grand_retweets = 0
            grand_replies = 0
            grand_views = 0
            for row in agg_result:
                platform_metrics[row.platform] = row.total
                grand_total += row.total
                grand_likes += row.total_likes
                grand_retweets += row.total_retweets
                grand_replies += row.total_replies
                grand_views += row.total_views

            # 2. Media count
            media_result = await session.execute(
                text("""
                    SELECT COUNT(DISTINCT c.id) as with_media
                    FROM contents c
                    JOIN content_media cm ON cm.content_id = c.id
                    WHERE c.topic_id = :topic_id AND c.crawled_at > :since
                """),
                {"topic_id": topic_id, "since": since_dt},
            )
            with_media = media_result.scalar() or 0
            media_pct = round(with_media * 100 / grand_total) if grand_total > 0 else 0

            # 3. Top posts by engagement — fetch candidates, trim by token budget
            top_result = await session.execute(
                text("""
                    SELECT id, platform, source_url, text,
                           author_display_name, author_username,
                           metrics, hashtags, crawled_at
                    FROM contents
                    WHERE topic_id = :topic_id AND crawled_at > :since
                    ORDER BY (
                        COALESCE((metrics->>'like_count')::int, 0) +
                        COALESCE((metrics->>'retweet_count')::int, 0)
                    ) DESC
                    LIMIT 100
                """),
                {"topic_id": topic_id, "since": since_dt},
            )

            posts = []
            used_tokens = 0
            for row in top_result:
                post_text = row.text or ""
                est_tokens = len(post_text) // 3
                if used_tokens + est_tokens > TOKEN_BUDGET and posts:
                    break
                likes = (row.metrics or {}).get("like_count", 0)
                retweets = (row.metrics or {}).get("retweet_count", 0)
                views = (row.metrics or {}).get("views_count", 0)
                posts.append({
                    "platform": row.platform,
                    "author": row.author_username or row.author_display_name or "",
                    "text": post_text,
                    "likes": likes,
                    "retweets": retweets,
                    "views": views,
                    "hashtags": row.hashtags or [],
                    "url": row.source_url,
                })
                used_tokens += est_tokens

            # 4. Top authors by engagement
            authors_result = await session.execute(
                text("""
                    SELECT author_username as username,
                           COUNT(*) as posts,
                           SUM(COALESCE((metrics->>'like_count')::int, 0) +
                               COALESCE((metrics->>'retweet_count')::int, 0)) as engagement
                    FROM contents
                    WHERE topic_id = :topic_id AND crawled_at > :since
                          AND author_username IS NOT NULL
                    GROUP BY author_username
                    ORDER BY engagement DESC
                    LIMIT 5
                """),
                {"topic_id": topic_id, "since": since_dt},
            )
            top_authors = [
                {"username": r.username, "posts": r.posts, "engagement": r.engagement}
                for r in authors_result
            ]

            # 5. Previous cycle data for trend comparison
            prev_metrics = {}
            prev_summary = ""
            if topic.summary_data and isinstance(topic.summary_data, dict):
                prev_metrics = topic.summary_data.get("metrics", {})
            if topic.last_summary:
                prev_summary = topic.last_summary

            # 6. Data status — all-time coverage + per-platform freshness
            now = datetime.now(timezone.utc)
            coverage_result = await session.execute(
                text("""
                    SELECT
                        platform,
                        COUNT(*) as count,
                        MAX(crawled_at) as newest_at
                    FROM contents
                    WHERE topic_id = :topic_id
                    GROUP BY platform
                """),
                {"topic_id": topic_id},
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

            hours_since_newest = (
                round((now - newest_overall).total_seconds() / 3600, 1)
                if newest_overall else None
            )
            hours_since_last_crawl = (
                round((now - topic.last_crawl_at).total_seconds() / 3600, 1)
                if topic.last_crawl_at else None
            )
            configured_interval = topic.config.get("schedule_interval_hours", 6)

            data_status = {
                "total_contents_all_time": total_all_time,
                "hours_since_newest_content": hours_since_newest,
                "hours_since_last_crawl": hours_since_last_crawl,
                "configured_interval_hours": configured_interval,
                "has_previous_summary": bool(topic.last_summary),
                "platform_coverage": platform_coverage,
                "configured_platforms": topic.platforms or [],
            }

            return {
                "time_window": {
                    "since": since_dt.isoformat(),
                    "until": now.isoformat(),
                },
                "data_status": data_status,
                "metrics": {
                    "total_contents": grand_total,
                    "total_likes": grand_likes,
                    "total_retweets": grand_retweets,
                    "total_replies": grand_replies,
                    "total_views": grand_views,
                    "with_media_pct": media_pct,
                    "platforms": platform_metrics,
                },
                "top_posts": posts,
                "top_posts_count": len(posts),
                "total_in_window": grand_total,
                "top_authors": top_authors,
                "previous_cycle": {
                    "metrics": prev_metrics,
                    "summary": prev_summary[:500] if prev_summary else "",
                },
            }

    return Tool(
        name="query_topic_contents",
        description=(
            "Query all crawled content for a topic with pre-computed metrics. "
            "Returns: data_status (all-time coverage, per-platform freshness, configured_platforms), "
            "SQL-aggregated statistics, top posts by engagement "
            "(selected by token budget), top authors, and previous cycle data for comparison."
        ),
        parameters={
            "type": "object",
            "properties": {
                "topic_id": {
                    "type": "string",
                    "description": "The topic UUID",
                },
            },
            "required": ["topic_id"],
        },
        func=_query_topic_contents,
    )

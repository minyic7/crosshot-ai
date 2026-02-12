"""query_topic_contents — SQL aggregation + classification + token-budget sampling."""

import json
import logging
import math
from datetime import datetime, timezone

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from shared.db.models import TopicRow, UserRow

logger = logging.getLogger(__name__)

TOKEN_BUDGET = 16000


def _build_content_filter(
    topic_id: str | None,
    user_ids: list[str] | None,
) -> tuple[str, dict]:
    """Build a SQL WHERE fragment + params for content ownership filtering.

    Returns (where_clause, base_params) — caller must add extra params like :since.
    """
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


async def query_topic_contents(
    session_factory: async_sessionmaker[AsyncSession],
    llm_client: AsyncOpenAI,
    fast_model: str,
    topic_id: str | None = None,
    user_id: str | None = None,
    user_ids: list[str] | None = None,
) -> dict:
    """Query, classify, and pre-process content for a topic or user.

    Supports three modes:
    - topic_id only: query content belonging to the topic
    - topic_id + user_ids: query topic content + attached users' content
    - user_id only: query a standalone user's content
    """
    # Merge user_id into user_ids list
    all_user_ids = list(user_ids or [])
    if user_id and user_id not in all_user_ids:
        all_user_ids.append(user_id)

    async with session_factory() as session:
        # Load entity for time window and metadata
        if topic_id:
            entity = await session.get(TopicRow, topic_id)
            if entity is None:
                return {"error": f"Topic {topic_id} not found"}
            since_dt = entity.last_crawl_at or entity.created_at
            entity_name = entity.name
            entity_keywords = entity.keywords or []
            entity_config = entity.config
            entity_last_summary = entity.last_summary
            entity_summary_data = entity.summary_data
            entity_platforms = entity.platforms or []
        elif user_id:
            entity = await session.get(UserRow, user_id)
            if entity is None:
                return {"error": f"User {user_id} not found"}
            since_dt = entity.last_crawl_at or entity.created_at
            entity_name = entity.name
            entity_keywords = []
            entity_config = entity.config
            entity_last_summary = entity.last_summary
            entity_summary_data = entity.summary_data
            entity_platforms = [entity.platform]
        else:
            return {"error": "Must provide either topic_id or user_id"}

        where, base_params = _build_content_filter(topic_id, all_user_ids or None)
        params = {**base_params, "since": since_dt}

        # 1. SQL Aggregation — accurate metrics over full dataset
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

        # 3. Top posts by engagement
        top_result = await session.execute(
            text(f"""
                SELECT c.id, c.platform, c.source_url, c.text,
                       c.author_display_name, c.author_username,
                       c.metrics, c.hashtags, c.crawled_at,
                       c.data->'media' as media_json
                FROM contents c
                WHERE ({where.replace('topic_id', 'c.topic_id').replace('user_id', 'c.user_id')})
                  AND c.crawled_at > :since
                ORDER BY (
                    COALESCE((c.metrics->>'like_count')::int, 0) +
                    COALESCE((c.metrics->>'retweet_count')::int, 0)
                ) DESC
                LIMIT 100
            """),
            params,
        )

        raw_posts = []
        for row in top_result:
            post_text = row.text or ""
            likes = (row.metrics or {}).get("like_count", 0)
            retweets = (row.metrics or {}).get("retweet_count", 0)
            views = (row.metrics or {}).get("views_count", 0)
            media_items = row.media_json or []
            media_types = list({m.get("type", "unknown") for m in media_items}) if media_items else []
            raw_posts.append({
                "platform": row.platform,
                "author": row.author_username or row.author_display_name or "",
                "text": post_text,
                "likes": likes,
                "retweets": retweets,
                "views": views,
                "hashtags": row.hashtags or [],
                "url": row.source_url,
                "media_types": media_types,
                "media_count": len(media_items),
            })

        # 4. Classify posts for relevance (batch LLM call)
        classified_posts = await _classify_posts(
            llm_client, fast_model,
            raw_posts, entity_name, entity_keywords,
        )

        # 5. Apply token budget to classified + filtered posts
        posts = []
        used_tokens = 0
        for post in classified_posts:
            est_tokens = len(post["text"]) // 3
            if used_tokens + est_tokens > TOKEN_BUDGET and posts:
                break
            posts.append(post)
            used_tokens += est_tokens

        # 6. Top authors by engagement
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

        # 7. Previous cycle data for trend comparison
        prev_metrics = {}
        prev_summary = ""
        if entity_summary_data and isinstance(entity_summary_data, dict):
            prev_metrics = entity_summary_data.get("metrics", {})
        if entity_last_summary:
            prev_summary = entity_last_summary

        # 8. Data status — all-time coverage + per-platform freshness
        now = datetime.now(timezone.utc)
        coverage_params = {k: v for k, v in base_params.items()}
        coverage_result = await session.execute(
            text(f"""
                SELECT
                    platform,
                    COUNT(*) as count,
                    MAX(crawled_at) as newest_at
                FROM contents
                WHERE {where}
                GROUP BY platform
            """),
            coverage_params,
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

        last_crawl_at = entity.last_crawl_at if hasattr(entity, 'last_crawl_at') else None
        hours_since_newest = (
            round((now - newest_overall).total_seconds() / 3600, 1)
            if newest_overall else None
        )
        hours_since_last_crawl = (
            round((now - last_crawl_at).total_seconds() / 3600, 1)
            if last_crawl_at else None
        )
        configured_interval = entity_config.get("schedule_interval_hours", 6)

        data_status = {
            "total_contents_all_time": total_all_time,
            "hours_since_newest_content": hours_since_newest,
            "hours_since_last_crawl": hours_since_last_crawl,
            "configured_interval_hours": configured_interval,
            "has_previous_summary": bool(entity_last_summary),
            "platform_coverage": platform_coverage,
            "configured_platforms": entity_platforms,
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
            "classification_stats": {
                "total_candidates": len(raw_posts),
                "after_filter": len(classified_posts),
                "in_budget": len(posts),
            },
            "top_authors": top_authors,
            "previous_cycle": {
                "metrics": prev_metrics,
                "summary": prev_summary[:500] if prev_summary else "",
            },
        }


async def _classify_posts(
    llm_client: AsyncOpenAI,
    fast_model: str,
    posts: list[dict],
    topic_name: str,
    keywords: list[str],
) -> list[dict]:
    """Batch-classify posts by relevance using a fast LLM call.

    Adds 'relevance' (1-10) and 'category' fields to each post.
    Filters out irrelevant posts (relevance < 3).
    Returns posts sorted by relevance * log(engagement).
    """
    if not posts:
        return posts

    # Build compact representation for classification
    compact = []
    for i, p in enumerate(posts):
        compact.append({
            "i": i,
            "text": p["text"][:200],
            "author": p["author"],
            "likes": p["likes"],
            "media": p["media_types"],
        })

    prompt = (
        f'Topic: "{topic_name}" | Keywords: {json.dumps(keywords, ensure_ascii=False)}\n\n'
        f"Classify each post's relevance to this topic.\n"
        f"Return a JSON array (same order, same length={len(compact)}):\n"
        f'[{{"r": 1-10, "c": "discussion|news|meme|spam|promo|unrelated"}}, ...]\n\n'
        f"r = relevance to the topic (10=perfectly on-topic, 1=completely unrelated)\n"
        f"c = content category\n\n"
        f"Posts:\n{json.dumps(compact, ensure_ascii=False)}"
    )

    try:
        response = await llm_client.chat.completions.create(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content or "[]"
        # Strip markdown code fences if present
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        classifications = json.loads(raw)

        if not isinstance(classifications, list) or len(classifications) != len(posts):
            logger.warning(
                "Classification length mismatch: got %d, expected %d. Using unclassified.",
                len(classifications) if isinstance(classifications, list) else 0,
                len(posts),
            )
            return posts

        # Attach classification to posts
        for post, cls in zip(posts, classifications):
            post["relevance"] = cls.get("r", 5)
            post["category"] = cls.get("c", "unknown")

        # Filter low-relevance
        before = len(posts)
        filtered = [p for p in posts if p.get("relevance", 5) >= 3]
        logger.info(
            "Classification: %d posts → %d after filtering (removed %d irrelevant)",
            before, len(filtered), before - len(filtered),
        )

        # Sort by relevance * log(engagement + 1) — relevant AND popular first
        def sort_key(p):
            engagement = p["likes"] + p["retweets"]
            return p.get("relevance", 5) * math.log(max(engagement, 1) + 1)

        filtered.sort(key=sort_key, reverse=True)
        return filtered

    except Exception as e:
        logger.warning("Classification failed (%s), using unclassified posts", e)
        return posts

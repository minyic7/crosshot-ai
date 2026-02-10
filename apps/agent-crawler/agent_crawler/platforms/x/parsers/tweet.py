"""Tweet parser — extracts normalized tweet data from X GraphQL responses.

X's GraphQL responses have deeply nested structures. This parser navigates
the JSON and extracts a flat, consistent tweet dict for storage.
"""

from __future__ import annotations

import logging
from typing import Any

from ..errors import ParseError

logger = logging.getLogger(__name__)


def parse_tweet_result(result: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a single tweet result entry from GraphQL.

    Handles both `tweet` and `tweet_with_visibility_results` wrappers.
    Returns None for tombstones / unavailable tweets.
    """
    # Unwrap visibility wrapper
    if "tweet" in result:
        result = result["tweet"]

    # Some results are just type markers (tombstones)
    if result.get("__typename") in ("TweetTombstone", "TweetUnavailable"):
        return None

    core = result.get("core", {})
    legacy = result.get("legacy", {})

    # X uses varying paths for user data across API versions
    user_results = (
        core.get("user_results", {}).get("result", {})
        or core.get("user_result", {}).get("result", {})
    )
    user_legacy = user_results.get("legacy", {})
    # 2026 API: screen_name and name moved to user_results.result.core
    user_core = user_results.get("core", {})

    if not legacy:
        return None

    tweet_id = legacy.get("id_str") or result.get("rest_id", "")
    if not tweet_id:
        return None

    # Author — check new "core" sub-object first, then fall back to "legacy"
    author = {
        "user_id": user_results.get("rest_id", ""),
        "username": (
            user_core.get("screen_name")
            or user_legacy.get("screen_name", "")
        ),
        "display_name": (
            user_core.get("name")
            or user_legacy.get("name", "")
        ),
        "verified": user_results.get("is_blue_verified", False),
        "followers_count": user_legacy.get("followers_count", 0),
    }

    # Metrics
    metrics = {
        "reply_count": legacy.get("reply_count", 0),
        "retweet_count": legacy.get("retweet_count", 0),
        "like_count": legacy.get("favorite_count", 0),
        "quote_count": legacy.get("quote_count", 0),
        "views_count": _get_views(result),
    }

    # Media
    media = _extract_media(legacy)

    # URLs and hashtags
    entities = legacy.get("entities", {})
    urls = [u.get("expanded_url", u.get("url", "")) for u in entities.get("urls", [])]
    hashtags = [h.get("text", "") for h in entities.get("hashtags", [])]

    # Tweet type flags
    is_retweet = "retweeted_status_result" in legacy
    is_reply = bool(legacy.get("in_reply_to_status_id_str"))
    is_quote = "quoted_status_result" in result

    # Quote tweet — recursively parse the quoted tweet
    quoted_tweet = None
    if is_quote:
        quoted_result = result.get("quoted_status_result", {}).get("result")
        if quoted_result:
            quoted_tweet = parse_tweet_result(quoted_result)

    # Reply context
    reply_to = None
    if is_reply:
        reply_to = {
            "tweet_id": legacy.get("in_reply_to_status_id_str", ""),
            "username": legacy.get("in_reply_to_screen_name", ""),
        }

    # Recommend deep crawl for high-engagement tweets
    deep_crawl_recommended = (
        metrics["reply_count"] >= 10
        or metrics["like_count"] >= 100
        or metrics["quote_count"] >= 5
        or is_quote
        or is_reply
    )

    return {
        "tweet_id": tweet_id,
        "text": legacy.get("full_text", ""),
        "created_at": legacy.get("created_at", ""),
        "author": author,
        "metrics": metrics,
        "media": media,
        "urls": urls,
        "hashtags": hashtags,
        "is_retweet": is_retweet,
        "is_reply": is_reply,
        "is_quote": is_quote,
        "quoted_tweet": quoted_tweet,
        "reply_to": reply_to,
        "deep_crawl_recommended": deep_crawl_recommended,
        "lang": legacy.get("lang", ""),
        "source_url": f"https://x.com/{author['username']}/status/{tweet_id}",
    }


def parse_search_timeline(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a SearchTimeline GraphQL response into a list of tweet dicts."""
    tweets = []
    try:
        timeline = (
            data.get("data", {})
            .get("search_by_raw_query", {})
            .get("search_timeline", {})
            .get("timeline", {})
        )
        instructions = timeline.get("instructions", [])

        # Debug: log instruction types so we can spot content gates / empty responses
        instr_types = [i.get("type", "?") for i in instructions]
        logger.debug("SearchTimeline instructions: %s", instr_types)
        if not instructions:
            logger.warning("SearchTimeline response has no instructions (possible content gate or empty result)")

        entries = _extract_entries(instructions)

        for entry in entries:
            tweet_data = _entry_to_tweet_result(entry)
            if tweet_data:
                parsed = parse_tweet_result(tweet_data)
                if parsed:
                    tweets.append(parsed)
    except Exception as e:
        logger.error("Failed to parse SearchTimeline: %s", e)
        raise ParseError(f"SearchTimeline parse failed: {e}") from e

    return tweets


def parse_tweet_detail(data: dict[str, Any]) -> dict[str, Any] | None:
    """Parse a TweetDetail / TweetResultByRestId response.

    Returns the main tweet only (first tweet in the conversation).
    """
    try:
        # TweetResultByRestId format
        result = data.get("data", {}).get("tweetResult", {}).get("result", {})
        if result:
            return parse_tweet_result(result)

        # TweetDetail format (conversation thread)
        instructions = (
            data.get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions", [])
        )
        entries = _extract_entries(instructions)
        for entry in entries:
            tweet_data = _entry_to_tweet_result(entry)
            if tweet_data:
                parsed = parse_tweet_result(tweet_data)
                if parsed:
                    return parsed
    except Exception as e:
        logger.error("Failed to parse TweetDetail: %s", e)
        raise ParseError(f"TweetDetail parse failed: {e}") from e

    return None


def parse_tweet_replies(
    data: dict[str, Any],
    main_tweet_id: str,
) -> list[dict[str, Any]]:
    """Parse replies from a TweetDetail conversation thread.

    Extracts all tweet entries except the main tweet itself.
    Handles both top-level replies (TimelineTimelineItem) and
    conversation threads (TimelineTimelineModule with multiple items).
    """
    replies: list[dict[str, Any]] = []
    try:
        instructions = (
            data.get("data", {})
            .get("threaded_conversation_with_injections_v2", {})
            .get("instructions", [])
        )
        entries = _extract_entries(instructions)

        for entry in entries:
            content = entry.get("content", {})
            entry_type = content.get("entryType", "")

            if entry_type == "TimelineTimelineItem":
                tweet_data = _entry_to_tweet_result(entry)
                if tweet_data:
                    parsed = parse_tweet_result(tweet_data)
                    if parsed and parsed["tweet_id"] != main_tweet_id:
                        replies.append(parsed)

            elif entry_type == "TimelineTimelineModule":
                # Conversation thread — extract all tweets in the module
                items = content.get("items", [])
                for module_item in items:
                    item = module_item.get("item", {}).get("itemContent", {})
                    if item.get("itemType") == "TimelineTweet":
                        tweet_data = item.get("tweet_results", {}).get("result")
                        if tweet_data:
                            parsed = parse_tweet_result(tweet_data)
                            if parsed and parsed["tweet_id"] != main_tweet_id:
                                replies.append(parsed)

    except Exception as e:
        logger.error("Failed to parse replies: %s", e)
        raise ParseError(f"Reply parse failed: {e}") from e

    return replies


def parse_user_tweets(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse a UserTweets / UserTweetsAndReplies response."""
    tweets = []
    try:
        timeline = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline_v2", {})
            .get("timeline", {})
        )
        instructions = timeline.get("instructions", [])
        entries = _extract_entries(instructions)

        for entry in entries:
            tweet_data = _entry_to_tweet_result(entry)
            if tweet_data:
                parsed = parse_tweet_result(tweet_data)
                if parsed:
                    tweets.append(parsed)
    except Exception as e:
        logger.error("Failed to parse UserTweets: %s", e)
        raise ParseError(f"UserTweets parse failed: {e}") from e

    return tweets


# ──────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────

def _extract_entries(instructions: list[dict]) -> list[dict]:
    """Extract timeline entries from GraphQL instructions."""
    entries = []
    for instruction in instructions:
        if instruction.get("type") == "TimelineAddEntries":
            entries.extend(instruction.get("entries", []))
        elif instruction.get("type") == "TimelineReplaceEntry":
            entry = instruction.get("entry")
            if entry:
                entries.append(entry)
    return entries


def _entry_to_tweet_result(entry: dict) -> dict[str, Any] | None:
    """Navigate from a timeline entry to the tweet result dict."""
    content = entry.get("content", {})
    entry_type = content.get("entryType", "")

    if entry_type == "TimelineTimelineItem":
        item = content.get("itemContent", {})
        if item.get("itemType") == "TimelineTweet":
            return item.get("tweet_results", {}).get("result")

    elif entry_type == "TimelineTimelineModule":
        # Thread / conversation module — take the first tweet
        items = content.get("items", [])
        for module_item in items:
            item = module_item.get("item", {}).get("itemContent", {})
            if item.get("itemType") == "TimelineTweet":
                return item.get("tweet_results", {}).get("result")

    return None


def _get_views(result: dict) -> int:
    """Extract view count from tweet result."""
    views = result.get("views", {})
    count = views.get("count")
    if count:
        try:
            return int(count)
        except (ValueError, TypeError):
            pass
    return 0


def _extract_media(legacy: dict) -> list[dict[str, Any]]:
    """Extract media items from tweet legacy data."""
    media_list = []
    extended = legacy.get("extended_entities", {}) or legacy.get("entities", {})
    for m in extended.get("media", []):
        item: dict[str, Any] = {
            "type": m.get("type", "photo"),  # photo, video, animated_gif
            "url": m.get("media_url_https", ""),
        }
        # Video URL
        if m.get("type") in ("video", "animated_gif"):
            variants = m.get("video_info", {}).get("variants", [])
            # Pick highest bitrate mp4
            mp4s = [v for v in variants if v.get("content_type") == "video/mp4"]
            if mp4s:
                best = max(mp4s, key=lambda v: v.get("bitrate", 0))
                item["video_url"] = best.get("url", "")
        media_list.append(item)
    return media_list

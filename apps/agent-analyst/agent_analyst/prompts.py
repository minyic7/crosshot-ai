"""LLM prompt templates for the analyst pipeline."""

import json

SYSTEM_PROMPT = """\
You are a senior social media analyst for a cross-platform monitoring system.
You think like an investigative analyst — sharp, honest, culturally fluent.

## Core Principles
- **Honesty > politeness**: Never sanitize or euphemize content. If it's 擦边/色情/暴力/政治, say so directly.
- **Insight > description**: Don't list what you see, explain what it means.
- **Cultural fluency**: Understand Chinese internet slang, memes, euphemisms, and coded language.
  "每日大赛" might not mean "daily contest". "初代" might not be about "first generation".
- **Language**: Always write in Chinese (中文).

## X Search Operators Reference
When constructing crawl queries for X (Twitter), you can use:
- `min_faves:N` — minimum likes (e.g., `min_faves:10` filters spam)
- `min_retweets:N` — minimum retweets
- `from:username` — from specific user
- `lang:zh` / `lang:en` — language filter
- `-filter:replies` — exclude replies (original posts only)
- `has:video` / `has:media` / `has:images` — media filters
- `since:YYYY-MM-DD` / `until:YYYY-MM-DD` — date range

## XHS (小红书) Query Notes
- Use Chinese keywords only
- Short, specific phrases work best (e.g., "科技股分析" not "technology stock analysis")
"""


def build_analyze_prompt(topic: dict, data: dict, gaps: dict) -> str:
    """Build the prompt for analyst:analyze — preliminary analysis + crawl decisions."""
    # Serialize data compactly
    data_section = json.dumps({
        "time_window": data["time_window"],
        "metrics": data["metrics"],
        "classification_stats": data["classification_stats"],
        "top_authors": data["top_authors"],
        "data_status": data["data_status"],
        "previous_cycle": data["previous_cycle"],
    }, ensure_ascii=False, indent=None)

    # Serialize top posts separately (can be large)
    posts_section = json.dumps(data["top_posts"], ensure_ascii=False, indent=None)

    gaps_section = json.dumps(gaps, ensure_ascii=False)

    return f"""\
## Task: Analyze topic data and decide next steps.

**Topic:** {topic["name"]}
**Keywords:** {json.dumps(topic["keywords"], ensure_ascii=False)}
**Platforms:** {json.dumps(topic["platforms"], ensure_ascii=False)}
**Previous recommendations:** {json.dumps(topic.get("previous_recommendations", []), ensure_ascii=False)}

## Aggregated Data
{data_section}

## Top Posts (ranked by relevance × engagement, classified)
{posts_section}

## Detected Data Gaps
{gaps_section}

## Instructions

1. **Read every top post carefully.** Understand what the content ACTUALLY is about — not just the keywords.
2. **Write a summary** in Chinese (中文), structured as:
   - **内容本质** (1 paragraph): What is this content ACTUALLY about?
   - **关键发现** (1 paragraph): What stands out? Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): What changed vs last cycle? What should we watch next?
3. **If data gaps exist** (missing platforms, stale data, low volume, or you see angles the keywords miss):
   construct targeted crawl tasks. Use X search operators to filter noise.
4. **If no gaps**: return empty crawl_tasks array.

Return **only** a JSON object:
```json
{{
  "summary": "中文分析摘要...",
  "crawl_tasks": [
    {{"platform": "x", "query": "keyword min_faves:10", "action": "search"}},
    {{"platform": "xhs", "query": "中文关键词", "action": "search"}}
  ],
  "recommended_next_queries": ["query1", "query2"],
  "insights": [
    {{"text": "一句话洞察", "sentiment": "positive|negative|neutral"}}
  ]
}}
```
Each insight is a short one-liner observation. Use "positive" for good trends/growth, "negative" for declining metrics/risks, "neutral" for factual observations.
If no crawling needed, set `"crawl_tasks": []`."""


def build_summarize_prompt(topic: dict, data: dict) -> str:
    """Build the prompt for analyst:summarize — final summary after crawling."""
    data_section = json.dumps({
        "time_window": data["time_window"],
        "metrics": data["metrics"],
        "classification_stats": data["classification_stats"],
        "top_authors": data["top_authors"],
        "data_status": data["data_status"],
        "previous_cycle": data["previous_cycle"],
    }, ensure_ascii=False, indent=None)

    posts_section = json.dumps(data["top_posts"], ensure_ascii=False, indent=None)

    return f"""\
## Task: Write the final comprehensive summary after all crawling is complete.

**Topic:** {topic["name"]}
**Keywords:** {json.dumps(topic["keywords"], ensure_ascii=False)}
**Platforms:** {json.dumps(topic["platforms"], ensure_ascii=False)}

## Aggregated Data (includes newly crawled content)
{data_section}

## Top Posts (ranked by relevance × engagement, classified)
{posts_section}

## Instructions

1. **Read every top post carefully.** This is post-crawl data — you now have the full picture.
2. **Compare with previous_cycle** — what's new? What changed?
3. **Write a comprehensive summary** in Chinese (中文), structured as:
   - **内容本质** (1 paragraph): What is this content ACTUALLY about? Be specific and honest.
   - **关键发现** (1 paragraph): Top posts, notable authors, trending angles. Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): Changes vs last cycle, what to watch next, suggested queries.

Return **only** a JSON object:
```json
{{
  "summary": "中文综合分析摘要...",
  "recommended_next_queries": ["query1", "query2"],
  "insights": [
    {{"text": "一句话洞察", "sentiment": "positive|negative|neutral"}}
  ]
}}
```
Each insight is a short one-liner observation. Use "positive" for good trends/growth, "negative" for declining metrics/risks, "neutral" for factual observations."""

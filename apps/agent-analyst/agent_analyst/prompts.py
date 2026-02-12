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


def _build_entity_header(entity: dict) -> str:
    """Build the entity description header for prompts."""
    if entity.get("type") == "user":
        header = f"**User:** {entity['name']} (@{entity.get('username', '?')})\n"
        header += f"**Platform:** {entity.get('platform', '?')}\n"
        if entity.get("profile_url"):
            header += f"**Profile:** {entity['profile_url']}\n"
    else:
        header = f"**Topic:** {entity['name']}\n"
        header += f"**Keywords:** {json.dumps(entity.get('keywords', []), ensure_ascii=False)}\n"
        header += f"**Platforms:** {json.dumps(entity.get('platforms', []), ensure_ascii=False)}\n"
        # Attached users
        users = entity.get("users", [])
        if users:
            user_list = ", ".join(
                f"@{u['username']} ({u['platform']})" for u in users if u.get("username")
            )
            header += f"**Tracked Users:** {user_list}\n"
    header += f"**Previous recommendations:** {json.dumps(entity.get('previous_recommendations', []), ensure_ascii=False)}"
    return header


def _build_data_sections(data: dict, gaps: dict | None = None) -> str:
    """Build the common data + posts + gaps sections."""
    data_section = json.dumps({
        "time_window": data["time_window"],
        "metrics": data["metrics"],
        "classification_stats": data["classification_stats"],
        "top_authors": data["top_authors"],
        "data_status": data["data_status"],
        "previous_cycle": data["previous_cycle"],
    }, ensure_ascii=False, indent=None)

    posts_section = json.dumps(data["top_posts"], ensure_ascii=False, indent=None)

    sections = f"""## Aggregated Data
{data_section}

## Top Posts (ranked by relevance × engagement, classified)
{posts_section}"""

    if gaps is not None:
        gaps_section = json.dumps(gaps, ensure_ascii=False)
        sections += f"\n\n## Detected Data Gaps\n{gaps_section}"

    return sections


def build_analyze_prompt(entity: dict, data: dict, gaps: dict) -> str:
    """Build the prompt for analyst:analyze — preliminary analysis + crawl decisions."""
    header = _build_entity_header(entity)
    sections = _build_data_sections(data, gaps)

    is_user = entity.get("type") == "user"
    subject = f"user @{entity.get('username', entity['name'])}" if is_user else "topic"

    # User-mode: focus on personal content style; Topic-mode: broader trend analysis
    if is_user:
        summary_structure = """\
   - **内容概览** (1 paragraph): What kind of content does this user post? Themes, style, frequency.
   - **关键发现** (1 paragraph): Notable posts, engagement patterns, content shifts. Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): How has their posting changed vs last cycle? What to watch next?"""
    else:
        summary_structure = """\
   - **内容本质** (1 paragraph): What is this content ACTUALLY about?
   - **关键发现** (1 paragraph): What stands out? Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): What changed vs last cycle? What should we watch next?"""

    return f"""\
## Task: Analyze {subject} data and decide next steps.

{header}

{sections}

## Instructions

1. **Read every top post carefully.** Understand what the content ACTUALLY is about — not just the keywords.
2. **Write a summary** in Chinese (中文), structured as:
{summary_structure}
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


def build_summarize_prompt(entity: dict, data: dict) -> str:
    """Build the prompt for analyst:summarize — final summary after crawling."""
    header = _build_entity_header(entity)
    sections = _build_data_sections(data)

    is_user = entity.get("type") == "user"
    subject = f"user @{entity.get('username', entity['name'])}" if is_user else "topic"

    if is_user:
        summary_structure = """\
   - **内容概览** (1 paragraph): What kind of content does this user post? Be specific and honest.
   - **关键发现** (1 paragraph): Top posts, engagement patterns, content themes. Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): Changes vs last cycle, posting frequency shifts, what to watch next."""
    else:
        summary_structure = """\
   - **内容本质** (1 paragraph): What is this content ACTUALLY about? Be specific and honest.
   - **关键发现** (1 paragraph): Top posts, notable authors, trending angles. Cite posts using their `url` field (NOT t.co links from text) as markdown: [@username](url).
   - **趋势与建议** (1 paragraph): Changes vs last cycle, what to watch next, suggested queries."""

    return f"""\
## Task: Write the final comprehensive summary for {subject} after all crawling is complete.

{header}

{sections}

## Instructions

1. **Read every top post carefully.** This is post-crawl data — you now have the full picture.
2. **Compare with previous_cycle** — what's new? What changed?
3. **Write a comprehensive summary** in Chinese (中文), structured as:
{summary_structure}

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

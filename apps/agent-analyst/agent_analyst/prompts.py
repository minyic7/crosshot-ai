"""LLM prompt templates for the incremental knowledge pipeline.

Three prompt types:
1. Triage — fast model classifies content: skip | brief | detail
2. Knowledge integration — reasoning model updates the knowledge document
3. Gap analysis — reasoning model decides crawl tasks
"""

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
        users = entity.get("users", [])
        if users:
            user_list = ", ".join(
                f"@{u['username']} ({u['platform']})" for u in users if u.get("username")
            )
            header += f"**Tracked Users:** {user_list}\n"
    return header


# ── Triage Prompt ──────────────────────────────────────


def build_triage_prompt(
    entity: dict,
    posts: list[dict],
) -> str:
    """Build the batch triage prompt for the fast model.

    For each post, the LLM decides:
    - "skip": spam, irrelevant, duplicate
    - "brief": worth noting, extract 1-2 key points
    - "detail": high-value, warrants fetching comments/quotes
    """
    is_user = entity.get("type") == "user"

    if is_user:
        context = f'User: @{entity.get("username", entity["name"])} ({entity.get("platform", "?")})'
    else:
        context = (
            f'Topic: "{entity["name"]}" | '
            f'Keywords: {json.dumps(entity.get("keywords", []), ensure_ascii=False)}'
        )

    # Build compact post list
    compact = []
    for i, p in enumerate(posts):
        compact.append({
            "i": i,
            "text": p["text"][:300],
            "author": p["author"],
            "likes": p["likes"],
            "retweets": p.get("retweets", 0),
            "replies": p.get("replies", 0),
            "media": p["media_types"],
        })

    return f"""\
{context}

Triage each post for processing depth. Consider relevance, engagement, and information value.

Decisions:
- "skip": Spam, completely irrelevant, low-value duplicate content
- "brief": Worth noting. Extract 1-2 key points (what's the actual insight?).
- "detail": High-value content — many replies/quotes suggest rich discussion. Fetch comments + quoted content for deeper analysis.

Guidelines for "detail":
- Posts with many replies (discussion-worthy) or quoted tweets
- Controversial or trending topics generating debate
- Original analysis/threads from notable authors
- NOT just high likes — high likes + low replies = viral but shallow

Return a JSON array (same order, same length={len(compact)}):
[{{"d": "skip|brief|detail", "kp": ["key point 1", "key point 2"] or null}}, ...]

d = decision
kp = key points (1-2 concise insights, only for "brief" and "detail"; null for "skip")

Posts:
{json.dumps(compact, ensure_ascii=False)}"""


# ── Knowledge Integration Prompt ──────────────────────


def build_integration_prompt(
    entity: dict,
    overview: dict,
    knowledge_doc: str,
    new_content: list[dict],
) -> str:
    """Build the knowledge integration prompt for the reasoning model.

    Takes existing knowledge + new processed content → returns updated knowledge + summary.
    """
    header = _build_entity_header(entity)

    # Build content section from integration-ready items
    content_entries = []
    for p in new_content:
        entry = f"[@{p['author']}]({p['url']}) — "
        if p.get("key_points"):
            entry += " | ".join(
                kp if isinstance(kp, str) else str(kp) for kp in p["key_points"]
            )
        else:
            entry += p["text"][:200]
        entry += f" (likes:{p['likes']} rt:{p['retweets']} views:{p.get('views', 0)})"
        if p.get("processing_status") == "detail_ready":
            entry += " [DETAILED — comments fetched]"
        content_entries.append(entry)

    content_section = "\n".join(content_entries) if content_entries else "(no new content)"

    # Metrics context
    metrics_section = json.dumps({
        "metrics": overview.get("metrics", {}),
        "top_authors": overview.get("top_authors", []),
        "data_status": overview.get("data_status", {}),
    }, ensure_ascii=False, indent=None)

    is_user = entity.get("type") == "user"

    if is_user:
        summary_instructions = """\
Write a comprehensive summary in Chinese (中文), structured as:
- **内容概览**: What kind of content does this user post? Themes, style, frequency.
- **关键发现**: Notable posts, engagement patterns, content shifts. Cite posts using markdown: [@username](url).
- **趋势与建议**: How has their posting changed? What to watch next?"""
    else:
        summary_instructions = """\
Write a comprehensive summary in Chinese (中文), structured as:
- **内容本质**: What is this content ACTUALLY about? Be specific and honest.
- **关键发现**: What stands out? Cite posts using markdown: [@username](url).
- **趋势与建议**: What changed? What to watch next? Suggested queries."""

    knowledge_section = knowledge_doc if knowledge_doc else "(empty — this is the first analysis)"

    return f"""\
## Task: Integrate new content into the knowledge document and write a summary.

{header}

## Current Knowledge Document
{knowledge_section}

## New Content to Integrate ({len(new_content)} items)
{content_section}

## Current Metrics
{metrics_section}

## Previous Summary
{overview.get("previous_cycle", {}).get("summary", "(none)")}

## Instructions

1. **Read each new piece of content carefully.** Understand the actual meaning, not just surface keywords.
2. **Update the knowledge document:**
   - Add new themes, observations, or notable events
   - Update existing themes with new evidence
   - Note sentiment changes or trend shifts
   - Track key figures and their stances
   - Remove or compress outdated observations if the document exceeds ~8000 characters
   - Keep the document in Chinese (中文)
3. **{summary_instructions}**

Return **only** a JSON object:
```json
{{
  "knowledge": "Updated knowledge document (markdown, Chinese)...",
  "summary": "中文综合分析摘要...",
  "insights": [
    {{"text": "一句话洞察", "sentiment": "positive|negative|neutral"}}
  ],
  "recommended_next_queries": ["query1", "query2"]
}}
```
Each insight is a short one-liner. "positive" for good trends, "negative" for risks, "neutral" for factual observations.
The knowledge document should be a structured markdown text that captures cumulative understanding."""


# ── Gap Analysis Prompt ──────────────────────────────


def build_gap_analysis_prompt(
    entity: dict,
    overview: dict,
    gaps: dict,
    knowledge_doc: str,
) -> str:
    """Build the gap analysis prompt — decides what crawl tasks to dispatch.

    Only called when deterministic gap detection found issues.
    """
    header = _build_entity_header(entity)
    header += f"\n**Previous recommendations:** {json.dumps(entity.get('previous_recommendations', []), ensure_ascii=False)}"

    gaps_section = json.dumps(gaps, ensure_ascii=False)
    data_section = json.dumps({
        "data_status": overview.get("data_status", {}),
        "metrics": overview.get("metrics", {}),
    }, ensure_ascii=False, indent=None)

    knowledge_context = ""
    if knowledge_doc:
        # Truncate knowledge for gap analysis (just need high-level themes)
        knowledge_context = f"\n## Current Knowledge Summary\n{knowledge_doc[:2000]}"

    return f"""\
## Task: Decide what additional data to crawl.

{header}

## Data Status
{data_section}

## Detected Gaps
{gaps_section}
{knowledge_context}

## Instructions

Based on the gaps and current knowledge, construct targeted crawl tasks.
Use X search operators to filter noise (min_faves, lang, date range).
Only suggest queries that would meaningfully improve our understanding.

Return **only** a JSON object:
```json
{{
  "crawl_tasks": [
    {{"platform": "x", "query": "keyword min_faves:10", "action": "search"}},
    {{"platform": "xhs", "query": "中文关键词", "action": "search"}}
  ],
  "reasoning": "Brief explanation of why these queries"
}}
```
If no crawling needed, set `"crawl_tasks": []`."""

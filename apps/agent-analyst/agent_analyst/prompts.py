"""LLM prompt templates for the analyst agent.

Prompt types:
1. Analyst system prompt — composed per-task with skills + tool guidance
2. Triage — fast model classifies content: skip | brief | detail
3. Knowledge integration — reasoning model updates the knowledge document
4. Gap analysis — reasoning model decides crawl tasks
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.skills.models import Skill


def build_system_prompt() -> str:
    """Build the system prompt with current date injected."""
    now = datetime.now(timezone.utc)
    return f"""\
You are a senior social media analyst for a cross-platform monitoring system.
You think like an investigative analyst — sharp, honest, culturally fluent.

**Current date: {now.strftime('%Y-%m-%d')} (UTC)**
Always use this date as your reference for "today". When constructing search queries,
focus on recent content (last 7-30 days) unless explicitly asked for historical data.

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


def build_analyst_system_prompt(
    skills: list[Skill],
    task_label: str,
) -> str:
    """Build a per-task system prompt for the analyst ReAct loop.

    Composes: base analyst identity + tool usage guidance + task-specific
    instructions + loaded skills as reference material.
    """
    base = build_system_prompt()

    # Tool usage guidance
    tool_section = """\
## Available Tools

You have the following tools. Call them by name with `entity_type` and `entity_id` from the task payload.

- **get_overview**: Load entity config, metrics, and data status. Call first.
- **triage_contents**: Classify unprocessed content (skip/brief/detail).
- **integrate_knowledge**: Update knowledge document with triaged content. Pass `is_preliminary=True` if crawling may follow.
- **analyze_gaps**: Detect data freshness gaps, recommend crawl tasks. Pass `force_crawl=True` to force.
- **dispatch_tasks**: Build and push crawl tasks to crawler/searcher agents. Sets up fan-in.
- **save_snapshot**: Save current metrics as a time-series snapshot for trend tracking.
- **save_note**: Save a persistent analysis note (survives summary rewrites).
- **create_alert**: Create an alert for anomalies or notable events (use sparingly).

If the task payload contains `chat_insights`, pass them to `integrate_knowledge` and `analyze_gaps`.
After completing all steps, respond with a brief text summary (no tool call) to finish."""

    # Task-specific instructions
    if task_label == "analyst:summarize":
        task_section = """\
## Current Task: Summarize (post-crawl)

All dispatched crawlers have completed. Process their results:

1. Call `get_overview` to see current data status
2. Call `triage_contents` with `downgrade_detail=True` — no more detail tasks will run
3. Call `integrate_knowledge` with `is_preliminary=False` — this is the final summary
4. Call `save_snapshot` with the metrics from get_overview to track trends
5. If anything notable happened, use `save_note` or `create_alert`
6. Respond with a brief summary of what was integrated"""
    else:
        task_section = """\
## Current Task: Analyze

Start a new analysis cycle for this entity:

1. Call `get_overview` to understand current state
2. Call `triage_contents` to classify unprocessed content
3. Call `integrate_knowledge` with `is_preliminary=True` (crawling may follow)
4. Unless `skip_crawl` is set in the payload, call `analyze_gaps` to detect data gaps
5. If gaps found with crawl_tasks, call `dispatch_tasks` with the results
   - Pass `crawl_tasks` from analyze_gaps output
   - Pass `detail_content_ids` from triage_contents output (if any)
   - Set `include_timelines=True` to also crawl attached user timelines
6. Respond with a brief summary of what you did"""

    # Skills reference
    skills_parts = []
    for s in skills:
        if s.prompt_text:
            skills_parts.append(f"### {s.name}: {s.description}\n{s.prompt_text}")
    skills_section = "\n\n".join(skills_parts) if skills_parts else "(no skills loaded)"

    return f"""{base}

{tool_section}

{task_section}

## Skills Reference
{skills_section}"""


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
    chat_insights: str = "",
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

{f"## User Focus Areas (from recent conversation)\\n{chat_insights}" if chat_insights else ""}

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
    chat_insights: str = "",
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

{f"## User Focus Areas (from recent conversation)\\n{chat_insights}\\nPrioritize queries that address these user interests." if chat_insights else ""}

## Instructions

Based on the gaps and current knowledge, construct targeted crawl tasks.

**Platform guidelines:**
- `x`: Use X search operators (min_faves, lang, date range). Always use `since:` with a recent date.
- `xhs`: Use Chinese keywords for Xiaohongshu content.
- `web`: Use for news articles, expert analysis, official announcements, research papers.
  Web queries should be natural language — the searcher agent will autonomously find relevant sources.

**IMPORTANT**: Focus on what's happening NOW — do NOT crawl old/historical data unless explicitly needed.
Only suggest queries that would meaningfully improve our understanding.
Include `web` queries when you need authoritative sources, industry analysis, or information not found on social media.

Return **only** a JSON object:
```json
{{
  "crawl_tasks": [
    {{"platform": "x", "query": "keyword min_faves:10", "action": "search"}},
    {{"platform": "xhs", "query": "中文关键词", "action": "search"}},
    {{"platform": "web", "query": "topic latest news analysis", "action": "search"}}
  ],
  "reasoning": "Brief explanation of why these queries"
}}
```
If no crawling needed, set `"crawl_tasks": []`."""

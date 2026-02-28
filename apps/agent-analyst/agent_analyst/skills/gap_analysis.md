---
name: gap_analysis
description: Detect data gaps and plan crawl tasks
routes_to: [crawler, searcher]
---
# Gap Analysis & Crawl Planning

Use the `analyze_gaps` tool to detect data freshness issues and plan additional crawl tasks.

## What Gap Analysis Does
1. **Deterministic checks**: Missing platforms, stale data, low volume, force_crawl flag
2. **LLM analysis** (only if gaps found): Reasoning model decides specific crawl queries
3. Returns recommended crawl tasks with platform, query, and action

## When to Use
- After integration, to decide if more data is needed
- Skip if `skip_crawl` is set in the task payload
- Skip search gap analysis if attached users have never been crawled (prioritize timelines first)

## After Gap Analysis
If crawl tasks are recommended, use the `dispatch_tasks` tool to send them to crawler/searcher agents.

## Platform Guidelines
- **x (Twitter)**: Use search operators — `min_faves:N`, `lang:zh`, `since:YYYY-MM-DD`, `from:username`
- **xhs (Xiaohongshu)**: Chinese keywords, short specific phrases
- **web**: Natural language queries for news, analysis, official announcements

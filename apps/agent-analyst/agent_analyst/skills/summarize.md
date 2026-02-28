---
name: summarize
description: Post-crawl integration and final summary production
routes_to: []
---
# Summarize (Post-Crawl)

This skill is used when processing `analyst:summarize` tasks — triggered after all crawlers complete (fan-in).

## Workflow
1. Use `get_overview` to load current metrics and data status
2. Use `triage_contents` to classify any new content from crawlers
   - In summarize phase, detail_pending gets downgraded to briefed (no more detail tasks)
3. Use `integrate_knowledge` to fold new content into the knowledge document
4. The final summary is saved automatically by the integrate tool

## Child Results
The task payload may contain `child_results` — structured feedback from completed crawler tasks:
- How many posts each crawler found
- Top posts by engagement
- Any errors encountered

Use this context to inform your analysis — if a crawler found nothing, note the data gap.
If a crawler found a viral post, prioritize analyzing it.

## Completion
After integration, the progress status is set to "done" automatically.
If there are attached users, their stats get updated too.

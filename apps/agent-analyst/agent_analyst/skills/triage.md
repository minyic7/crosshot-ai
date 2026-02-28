---
name: triage
description: Classify unprocessed content for processing depth
routes_to: []
---
# Content Triage

When there is unprocessed content for an entity (topic or user), use the `triage_contents` tool to classify it.

## What Triage Does
- Fetches all unprocessed content from the database
- Uses a fast LLM to classify each post: **skip**, **brief**, or **detail**
- Updates processing status in the database
- Returns a summary of triage results and any content IDs marked for detailed analysis

## When to Use
- At the start of an analysis cycle, before integration
- After crawlers return new content (in the summarize phase)

## Decision Criteria
- **skip**: Spam, completely irrelevant, low-value duplicates
- **brief**: Worth noting — extract 1-2 key points
- **detail**: High-value content with rich discussion (many replies/quotes) — will trigger comment fetching

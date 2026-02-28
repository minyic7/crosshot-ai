---
name: integrate
description: Integrate new content into the persistent knowledge document
routes_to: []
---
# Knowledge Integration

When integration-ready content exists (briefed + detail_ready), use the `integrate_knowledge` tool to update the knowledge document and produce a summary.

## What Integration Does
- Fetches all integration-ready content from the database
- Sends it along with the existing knowledge document to a reasoning LLM
- The LLM updates the knowledge document with new observations, themes, and evidence
- Saves the updated knowledge, summary, and insights to the database
- Marks integrated content as processed

## When to Use
- After triage, when there is integration-ready content
- In the summarize phase, after processing any new content from crawlers

## Key Principles
- The knowledge document is cumulative — new content adds to it, old irrelevant observations get compressed
- Always cite posts using markdown: [@username](url)
- Write in Chinese (中文)
- Insight > description — explain what content means, not just what it says

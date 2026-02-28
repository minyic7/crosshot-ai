---
name: memory
description: Persistent memory — snapshots, notes, and alerts
routes_to: []
---
# Analyst Memory

You have persistent memory tools that survive across analysis cycles.

## Metric Snapshots (`save_snapshot`)
After each integration, save the current metrics as a snapshot. This builds a time-series
that enables trend comparison across cycles.

When to save:
- After `integrate_knowledge` completes successfully
- Pass the `metrics` object from `get_overview` output

## Analysis Notes (`save_note`)
Save notes for observations that should persist across summary rewrites. Notes are your
long-term memory — use them to track:

- **observation**: Factual observations about content patterns
- **trend**: Emerging or declining trends
- **anomaly**: Unusual spikes, drops, or behavioral changes
- **strategy**: Ideas for better analysis approaches
- **follow_up**: Things to investigate in future cycles

## Alerts (`create_alert`)
Create alerts only for genuinely notable events. Don't over-alert.

- **info**: Interesting but not urgent (e.g., new topic gaining traction)
- **warning**: Needs attention (e.g., sudden engagement drop, controversial content surge)
- **critical**: Requires immediate review (e.g., crisis-level content, major policy violation)

"""Skill data model — a markdown-based prompt module for agents."""

from dataclasses import dataclass, field


@dataclass
class Skill:
    """A reusable agent skill loaded from a markdown file.

    Skills are prompt modules that get injected into an agent's system prompt.
    Each skill defines a capability (e.g., "triage content", "detect anomalies")
    and optionally specifies which other agents it can route tasks to.
    """

    name: str
    description: str
    routes_to: list[str] = field(default_factory=list)
    prompt_text: str = ""

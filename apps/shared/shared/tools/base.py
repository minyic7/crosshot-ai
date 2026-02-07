"""Base Tool definition for agent function calling."""

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    """A tool that an agent can use.

    Tools are the hands and feet of agents. Each tool has:
    - name: unique identifier (used by LLM to call the tool)
    - description: what this tool does (shown to LLM)
    - parameters: JSON Schema defining the tool's input
    - func: the actual async function to execute
    """

    name: str
    description: str
    parameters: dict
    func: Callable[..., Any]

    def to_openai_schema(self) -> dict:
        """Convert to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    async def execute(self, **kwargs: Any) -> Any:
        """Execute the tool function."""
        result = self.func(**kwargs)
        # Support both sync and async functions
        if hasattr(result, "__await__"):
            return await result
        return result

    def __repr__(self) -> str:
        return f"Tool(name={self.name!r})"

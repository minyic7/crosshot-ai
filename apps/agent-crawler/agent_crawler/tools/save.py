"""Save results tool — persists scraped data to the database."""

from typing import Any

from shared.tools.base import Tool


async def _save_results(
    task_id: str,
    platform: str,
    data: list[dict[str, Any]],
) -> dict:
    """Save scraped results to the database.

    Args:
        task_id: The task that produced these results.
        platform: Platform name (xhs, x).
        data: List of scraped content items.

    Returns:
        Dict with save status and count.
    """
    # TODO: Implement database persistence
    raise NotImplementedError("save_results not yet implemented")


save_results = Tool(
    name="save_results",
    description="Save scraped content to the database.",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "The task ID"},
            "platform": {
                "type": "string",
                "enum": ["xhs", "x"],
                "description": "Platform name",
            },
            "data": {
                "type": "array",
                "items": {"type": "object"},
                "description": "List of scraped content items",
            },
        },
        "required": ["task_id", "platform", "data"],
    },
    func=_save_results,
)

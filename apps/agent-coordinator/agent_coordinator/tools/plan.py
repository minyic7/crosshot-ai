"""Submit task tool — creates and queues new tasks."""

from shared.tools.base import Tool


async def _submit_task(
    label: str,
    keyword: str | None = None,
    cookies_id: str | None = None,
    priority: str = "medium",
    payload: dict | None = None,
) -> dict:
    """Submit a new task to the queue.

    Args:
        label: Task label for routing (e.g. "crawler:xhs", "ai:analyze").
        keyword: Search keyword (for crawler tasks).
        cookies_id: Which cookies to use (for crawler tasks).
        priority: Task priority (low, medium, high).
        payload: Additional task data.

    Returns:
        Dict with the created task ID.
    """
    # TODO: Implement task creation and queue push
    raise NotImplementedError("submit_task not yet implemented")


submit_task = Tool(
    name="submit_task",
    description="Create a new task and push it to the queue for execution by another agent.",
    parameters={
        "type": "object",
        "properties": {
            "label": {
                "type": "string",
                "enum": ["crawler:xhs", "crawler:x", "ai:analyze", "ai:schedule"],
                "description": "Task label that determines which agent processes it",
            },
            "keyword": {
                "type": "string",
                "description": "Search keyword for crawler tasks",
            },
            "cookies_id": {
                "type": "string",
                "description": "ID of cookies to use from the pool",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Task priority",
                "default": "medium",
            },
            "payload": {
                "type": "object",
                "description": "Additional task data",
            },
        },
        "required": ["label"],
    },
    func=_submit_task,
)

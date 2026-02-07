"""Cookies pool tool — query available credentials from Redis."""

from shared.tools.base import Tool


async def _get_available_cookies(platform: str) -> list[dict]:
    """Get available cookies for a platform.

    Filters out cookies that are:
    - inactive (is_active=False)
    - failed too many times (fail_count >= 3)
    - in cooldown period

    Returns sorted by use_count_today (ascending) for round-robin selection.

    Args:
        platform: Platform name (xhs, x).

    Returns:
        List of available cookies with id, name, and usage stats.
    """
    # TODO: Implement Redis cookies pool query
    raise NotImplementedError("get_available_cookies not yet implemented")


get_available_cookies = Tool(
    name="get_available_cookies",
    description="Get available cookies/credentials for a platform, sorted by least used today.",
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "enum": ["xhs", "x"],
                "description": "Platform to get cookies for",
            },
        },
        "required": ["platform"],
    },
    func=_get_available_cookies,
)

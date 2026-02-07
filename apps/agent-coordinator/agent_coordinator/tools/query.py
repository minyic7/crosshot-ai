"""Query contents tool — retrieve stored data from database."""

from shared.tools.base import Tool


async def _query_contents(
    platform: str | None = None,
    keyword: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Query stored content from the database.

    Args:
        platform: Filter by platform (xhs, x). None = all platforms.
        keyword: Filter by keyword. None = no keyword filter.
        limit: Maximum number of results to return.

    Returns:
        List of content items matching the query.
    """
    # TODO: Implement database query
    raise NotImplementedError("query_contents not yet implemented")


query_contents = Tool(
    name="query_contents",
    description="Query stored crawled content from the database.",
    parameters={
        "type": "object",
        "properties": {
            "platform": {
                "type": "string",
                "enum": ["xhs", "x"],
                "description": "Filter by platform",
            },
            "keyword": {
                "type": "string",
                "description": "Filter by keyword",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results to return",
                "default": 20,
            },
        },
    },
    func=_query_contents,
)

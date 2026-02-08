"""X platform error hierarchy."""


class XCrawlerError(Exception):
    """Base error for X platform operations."""


class AuthError(XCrawlerError):
    """Cookie authentication failed (401/403)."""


class RateLimitError(XCrawlerError):
    """Rate limited by X (429)."""

    def __init__(self, retry_after: int | None = None) -> None:
        self.retry_after = retry_after
        msg = "Rate limited by X"
        if retry_after:
            msg += f" (retry after {retry_after}s)"
        super().__init__(msg)


class ContentNotFoundError(XCrawlerError):
    """Requested content (tweet, user, etc.) does not exist."""


class NoCookiesAvailable(XCrawlerError):
    """No active cookies available for the platform."""


class ParseError(XCrawlerError):
    """Failed to parse X GraphQL response."""


class QueryGenerationError(XCrawlerError):
    """AI failed to generate a valid search query."""

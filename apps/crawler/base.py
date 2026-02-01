"""Base crawler types and classes for cross-platform support.

All crawler implementations should:
1. Set the `platform` field for all returned items
2. Keep counts as strings to preserve original format (e.g., "1.2万")
3. Store platform-specific data in the `platform_data` dict
"""

from abc import ABC, abstractmethod
from typing import Any, Self

from pydantic import BaseModel


class ContentItem(BaseModel):
    """Content item from search results (cross-platform).

    Attributes:
        platform: Platform identifier (e.g., "xhs", "douyin")
        platform_content_id: Platform-specific content ID
        title: Content title
        likes: Likes count as string (e.g., "1.2万")
        collects: Collects count as string
        comments: Comments count as string
        publish_time: Publish time as string
        content_url: Full URL to the content
        cover_url: Cover image URL
        media_urls: List of media URLs (images/videos)
        content_type: Type of content (e.g., "normal", "video", "image", "carousel")
        platform_data: Platform-specific extra data (e.g., xsec_token for XHS)
    """

    platform: str
    platform_content_id: str
    title: str
    likes: str = "0"  # Keep as string to preserve "1.2万" format
    collects: str = "0"
    comments: str = "0"
    publish_time: str = ""
    content_url: str = ""
    cover_url: str = ""
    media_urls: list[str] = []  # Legacy field, prefer image_urls/video_urls
    image_urls: list[str] = []  # Image URLs
    video_urls: list[str] = []  # Video URLs
    content_type: str = "normal"  # normal/video/image/carousel
    platform_data: dict[str, Any] = {}


class SubCommentItem(BaseModel):
    """Sub-comment (reply to a comment) - cross-platform.

    Attributes:
        platform: Platform identifier
        platform_comment_id: Platform-specific comment ID
        platform_user_id: Platform-specific user ID
        content: Comment content
        nickname: User nickname
        avatar: User avatar URL
        likes: Likes count as string
        create_time: Original timestamp in milliseconds
        ip_location: IP location string
        platform_data: Platform-specific extra data
    """

    platform: str
    platform_comment_id: str
    platform_user_id: str
    content: str
    nickname: str
    avatar: str = ""
    likes: str = "0"
    create_time: int = 0  # timestamp in ms
    ip_location: str = ""
    image_urls: list[str] = []  # Comment images
    platform_data: dict[str, Any] = {}


class CommentItem(BaseModel):
    """Comment on a content - cross-platform.

    Attributes:
        platform: Platform identifier
        platform_comment_id: Platform-specific comment ID
        platform_content_id: Platform-specific content ID this comment belongs to
        platform_user_id: Platform-specific user ID
        content: Comment content
        nickname: User nickname
        avatar: User avatar URL
        likes: Likes count as string
        create_time: Original timestamp in milliseconds
        ip_location: IP location string
        sub_comment_count: Number of sub-comments
        sub_comments: List of sub-comments
        platform_data: Platform-specific extra data
    """

    platform: str
    platform_comment_id: str
    platform_content_id: str
    platform_user_id: str
    content: str
    nickname: str
    avatar: str = ""
    likes: str = "0"
    create_time: int = 0  # timestamp in ms
    ip_location: str = ""
    image_urls: list[str] = []  # Comment images
    video_urls: list[str] = []  # Comment videos
    sub_comment_count: int = 0
    sub_comments: list[SubCommentItem] = []
    platform_data: dict[str, Any] = {}


class ContentStats(BaseModel):
    """Statistics and media for a content from detail page - cross-platform.

    This is returned when scraping comments to update content stats and media.

    Attributes:
        platform: Platform identifier
        platform_content_id: Platform-specific content ID
        likes: Likes count as string (e.g., "1.2万")
        collects: Collects count as string
        comments: Comments count as string
        shares: Shares count as string
        image_urls: All image URLs from the content (from detail page)
        video_url: Video URL if this is a video post
        content_type: Content type (normal/video)
    """

    platform: str
    platform_content_id: str
    likes: str = "0"
    collects: str = "0"
    comments: str = "0"
    shares: str = "0"
    image_urls: list[str] = []  # All images from detail page
    video_url: str = ""  # Video URL for video posts
    content_type: str = "normal"  # normal/video


class UserContentItem(BaseModel):
    """A content item from user profile page - cross-platform.

    Attributes:
        platform: Platform identifier
        platform_content_id: Platform-specific content ID
        title: Content title
        content_type: Type of content (e.g., "normal", "video")
        likes: Likes count as string
        cover_url: Cover image URL
        platform_data: Platform-specific extra data (e.g., xsec_token for XHS)
    """

    platform: str
    platform_content_id: str
    title: str
    content_type: str = "normal"
    likes: str = "0"
    cover_url: str = ""
    platform_data: dict[str, Any] = {}


class UserInfo(BaseModel):
    """User profile information - cross-platform.

    Attributes:
        platform: Platform identifier
        platform_user_id: Platform-specific user ID
        nickname: User nickname
        avatar: User avatar URL
        description: User bio/description
        gender: 0=unknown, 1=male, 2=female
        ip_location: IP location string
        follows: Following count as string
        fans: Followers count as string
        interaction: Interaction count as string (likes + collects received)
        contents: List of user's contents
        platform_data: Platform-specific extra data (e.g., red_id for XHS)
    """

    platform: str
    platform_user_id: str
    nickname: str
    avatar: str = ""
    description: str = ""
    gender: int = 0  # 0=unknown, 1=male, 2=female
    ip_location: str = ""
    follows: str = "0"
    fans: str = "0"
    interaction: str = "0"  # 获赞与收藏
    contents: list[UserContentItem] = []
    platform_data: dict[str, Any] = {}


class BaseCrawler(ABC):
    """Base class for all crawlers.

    All crawlers must set the `platform` attribute to identify the platform.
    """

    platform: str = "unknown"  # Subclasses must override

    @abstractmethod
    async def scrape(self, keyword: str) -> list[ContentItem]:
        """Scrape contents for a given keyword."""
        pass

    async def __aenter__(self) -> Self:
        """Default async context manager entry - subclasses can override."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Default async context manager exit - subclasses can override."""
        pass


# Backward compatibility aliases
NoteItem = ContentItem
UserNoteItem = UserContentItem

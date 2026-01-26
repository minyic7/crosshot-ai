from abc import ABC, abstractmethod
from typing import Self

from pydantic import BaseModel


class NoteItem(BaseModel):
    """Note item from search results."""

    title: str
    likes: str  # Keep as string to preserve "1.2万" format
    collects: str
    comments: str
    publish_time: str
    note_url: str
    image_urls: list[str]


class SubCommentItem(BaseModel):
    """Sub-comment (reply to a comment)."""

    comment_id: str
    content: str
    user_id: str
    nickname: str
    avatar: str
    likes: str  # Keep as string
    create_time: int  # timestamp in ms
    ip_location: str = ""


class CommentItem(BaseModel):
    """Comment on a note."""

    comment_id: str
    content: str
    user_id: str
    nickname: str
    avatar: str
    likes: str  # Keep as string
    create_time: int  # timestamp in ms
    ip_location: str = ""
    sub_comment_count: int = 0
    sub_comments: list[SubCommentItem] = []


class UserNoteItem(BaseModel):
    """A note item from user profile page."""

    note_id: str
    title: str
    type: str  # "normal" or "video"
    likes: str
    cover_url: str
    xsec_token: str


class UserInfo(BaseModel):
    """User profile information."""

    user_id: str
    nickname: str
    avatar: str
    desc: str = ""
    gender: int = 0  # 0=unknown, 1=male, 2=female
    ip_location: str = ""
    red_id: str = ""
    follows: str = "0"
    fans: str = "0"
    interaction: str = "0"  # 获赞与收藏
    notes: list[UserNoteItem] = []


class BaseCrawler(ABC):
    """Base class for all crawlers."""

    @abstractmethod
    async def scrape(self, keyword: str) -> list[NoteItem]:
        """Scrape notes for a given keyword."""
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

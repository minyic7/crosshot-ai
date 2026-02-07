"""Content model for crawled data."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Content(BaseModel):
    """A piece of crawled content from a social media platform.

    Core fields are native columns for filtering/querying.
    Everything platform-specific goes into the `data` JSONB blob.

    Example data for XHS:
        {"author": "...", "title": "...", "text": "...",
         "images": [...], "likes": 123, "comments": 45}
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    task_id: str
    platform: str
    source_url: str
    crawled_at: datetime = Field(default_factory=datetime.now)
    data: dict[str, Any] = Field(default_factory=dict)

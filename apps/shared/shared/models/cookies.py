"""Cookies pool model for managing platform credentials."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CookiesPool(BaseModel):
    """A set of cookies/credentials for a platform account.

    Stored in Redis. The scheduler/coordinator selects cookies based on:
    - is_active: must be True
    - fail_count: must be < 3
    - cooldown_until: must be None or in the past
    - use_count_today: prefer lowest (round-robin)
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    platform: str
    name: str
    cookies: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    last_used_at: datetime | None = None
    use_count_today: int = 0
    fail_count: int = 0
    cooldown_until: datetime | None = None

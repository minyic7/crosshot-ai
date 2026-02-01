"""Application configuration using pydantic-settings."""

import json
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CrawlerSettings(BaseSettings):
    """Crawler-specific settings."""

    model_config = SettingsConfigDict(
        env_prefix="CRAWLER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    max_retries: int = Field(default=3, description="Max retry attempts for network requests")
    retry_delay: float = Field(default=1.0, description="Initial delay between retries in seconds")
    default_max_notes: int = Field(default=100, description="Default max notes to scrape per search")
    default_scroll_count: int = Field(default=20, description="Default scroll count for loading more")
    playwright_timeout: int = Field(default=60000, description="Playwright default timeout in ms")
    headless: bool = Field(default=True, description="Run browser in headless mode")


class XhsSettings(BaseSettings):
    """XHS-specific settings including cookies."""

    model_config = SettingsConfigDict(
        env_prefix="XHS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cookies_json: str = Field(
        default="[]",
        description="XHS cookies as JSON array string",
    )

    @field_validator("cookies_json")
    @classmethod
    def validate_cookies(cls, v: str) -> str:
        """Validate that cookies_json is valid JSON."""
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("cookies_json must be a JSON array")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for cookies: {e}")
        return v

    def get_cookies(self) -> list[dict]:
        """Parse and return cookies as list of dicts."""
        return json.loads(self.cookies_json)


class XSettings(BaseSettings):
    """X (Twitter) specific settings including cookies."""

    model_config = SettingsConfigDict(
        env_prefix="X_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cookies_json: str = Field(
        default="[]",
        description="X cookies as JSON array string",
    )

    @field_validator("cookies_json")
    @classmethod
    def validate_cookies(cls, v: str) -> str:
        """Validate that cookies_json is valid JSON."""
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("cookies_json must be a JSON array")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON for cookies: {e}")
        return v

    def get_cookies(self) -> list[dict]:
        """Parse and return cookies as list of dicts."""
        return json.loads(self.cookies_json)


class DatabaseSettings(BaseSettings):
    """Database settings."""

    model_config = SettingsConfigDict(
        env_prefix="DB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    path: str = Field(default="data/xhs.db", description="SQLite database path")


class CacheSettings(BaseSettings):
    """Cache settings for smart caching strategy."""

    model_config = SettingsConfigDict(
        env_prefix="CACHE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    note_ttl_hours: int = Field(
        default=24,
        description="Hours before a cached note is considered stale",
    )
    enable_version_compare: bool = Field(
        default=True,
        description="Enable version comparison for detecting changes",
    )
    always_append_on_change: bool = Field(
        default=True,
        description="Always append new version when changes detected (preserve history)",
    )


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    debug: bool = Field(default=False)

    @property
    def crawler(self) -> CrawlerSettings:
        return CrawlerSettings()

    @property
    def xhs(self) -> XhsSettings:
        return XhsSettings()

    @property
    def x(self) -> XSettings:
        return XSettings()

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings()

    @property
    def cache(self) -> CacheSettings:
        return CacheSettings()


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


def reload_settings() -> Settings:
    """Reload settings (clear cache and return new instance).

    Call this when .env file is updated to pick up new values.
    """
    get_settings.cache_clear()
    return get_settings()

"""Application settings using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings loaded from environment variables / .env file."""

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Database
    db_url: str = "postgresql://crosshot:crosshot@postgres:5432/crosshot"

    # Grok LLM API (OpenAI-compatible)
    grok_api_key: str = ""
    grok_base_url: str = "https://api.x.ai/v1"
    grok_model: str = "grok-4-1-fast-reasoning"
    grok_fast_model: str = "grok-4-1-fast-non-reasoning"

    # OpenSearch
    opensearch_url: str = "http://opensearch:9200"

    # Media storage
    media_base_path: str = "/data/media"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

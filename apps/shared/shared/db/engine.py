"""Async SQLAlchemy engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    """Get or create the async engine (singleton)."""
    global _engine
    if _engine is None:
        from shared.config.settings import get_settings

        url = get_settings().db_url.replace("postgresql://", "postgresql+asyncpg://")
        _engine = create_async_engine(url, echo=False, pool_size=5, max_overflow=10)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory (singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def create_tables() -> None:
    """Create all tables if they don't exist (idempotent)."""
    from shared.db.models import Base

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_engine() -> None:
    """Dispose the engine and release connection pool."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None

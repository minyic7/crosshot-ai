"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api.deps import close_deps, init_deps
from api.routers import agents, cookies, dashboard, health, jobs, tasks, topics, users
from shared.config.settings import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_deps()
    yield
    await close_deps()


app = FastAPI(
    title="Crosshot AI API",
    description="AI-driven multi-platform social media data collection and analysis",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(health.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(cookies.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(topics.router, prefix="/api")
app.include_router(users.router, prefix="/api")

# Serve downloaded media files
_media_path = Path(get_settings().media_base_path)
if _media_path.is_dir():
    app.mount("/media", StaticFiles(directory=str(_media_path)), name="media")

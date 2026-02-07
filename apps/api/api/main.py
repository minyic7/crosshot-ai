"""FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import close_deps, init_deps
from api.routers import agents, cookies, dashboard, health, jobs, tasks


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
app.include_router(jobs.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(agents.router, prefix="/api")
app.include_router(cookies.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")

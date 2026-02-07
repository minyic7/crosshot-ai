"""FastAPI application."""

from fastapi import FastAPI

from api.routers import health, jobs, tasks

app = FastAPI(
    title="Crosshot AI API",
    description="AI-driven multi-platform social media data collection and analysis",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(jobs.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")

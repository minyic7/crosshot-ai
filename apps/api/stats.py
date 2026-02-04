"""Stats API endpoints for dashboard and database page."""

from fastapi import APIRouter, HTTPException, Query

from apps.config import get_settings
from apps.services.stats_service import StatsService

router = APIRouter(prefix="/stats", tags=["stats"])


def _get_service() -> StatsService:
    settings = get_settings()
    return StatsService(db_path=settings.database.path)


@router.get("/overview")
def overview():
    return _get_service().get_overview()


@router.get("/tables")
def tables():
    return _get_service().get_table_stats()


@router.get("/platforms")
def platforms():
    return _get_service().get_platform_breakdown()


@router.get("/content-types")
def content_types():
    return _get_service().get_content_type_breakdown()


@router.get("/search-tasks")
def search_tasks():
    return _get_service().get_search_task_summary()


@router.get("/scrape-health")
def scrape_health(
    hours: int | None = Query(default=None),
    platform: str | None = Query(default=None),
):
    return _get_service().get_scrape_health(hours=hours, platform=platform)


@router.get("/activity")
def activity(limit: int = Query(default=20, le=100)):
    return _get_service().get_recent_activity(limit=limit)


@router.get("/growth")
def growth(days: int = Query(default=7, le=90)):
    return _get_service().get_growth(days=days)


@router.get("/storage")
def storage():
    return _get_service().get_storage_info()


@router.get("/content/list")
def content_list(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    platform: str | None = Query(default=None),
    sort: str = Query(default="newest"),
):
    return _get_service().get_content_list(
        page=page, limit=limit, platform=platform, sort=sort
    )


@router.get("/content/{content_id}")
def content_detail(content_id: int):
    result = _get_service().get_content_detail(content_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return result

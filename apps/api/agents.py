"""Agent management API endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apps.config import get_settings
from apps.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["agents"])


def _get_service() -> AgentService:
    settings = get_settings()
    return AgentService(db_path=settings.database.path)


# ─── Request models ───


class CreateAgentRequest(BaseModel):
    config_id: int
    instance_name: str
    extra_env: dict | None = None


# ─── Container endpoints ───


@router.get("/containers")
def list_containers():
    """List all managed containers with status."""
    return _get_service().list_containers()


@router.get("/containers/{container_id}/stats")
def container_stats(container_id: str):
    """Get CPU/memory stats for a container."""
    return _get_service().get_container_stats(container_id)


@router.get("/containers/{container_id}/logs")
def container_logs(container_id: str, tail: int = Query(default=100, le=1000)):
    """Get container logs (tail N lines)."""
    return {"logs": _get_service().get_container_logs(container_id, tail=tail)}


@router.post("/containers/{container_id}/start")
def start_container(container_id: str):
    """Start a stopped container."""
    result = _get_service().start_container(container_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/containers/{container_id}/stop")
def stop_container(container_id: str):
    """Stop a running container."""
    result = _get_service().stop_container(container_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/containers/{container_id}/restart")
def restart_container(container_id: str):
    """Restart a container."""
    result = _get_service().restart_container(container_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/containers")
def create_agent(req: CreateAgentRequest):
    """Create a new agent container from a config template."""
    result = _get_service().create_agent_instance(
        config_id=req.config_id,
        instance_name=req.instance_name,
        extra_env=req.extra_env,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.delete("/containers/{container_id}")
def remove_container(container_id: str):
    """Remove an API-created container."""
    result = _get_service().remove_container(container_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ─── Config template endpoints ───


@router.get("/configs")
def list_configs():
    """List all agent config templates."""
    return _get_service().list_agent_configs()


@router.get("/configs/{config_id}")
def get_config(config_id: int):
    """Get a specific agent config template."""
    result = _get_service().get_agent_config(config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Config not found")
    return result

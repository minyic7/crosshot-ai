"""Agent service for Docker container management.

Uses Docker SDK to manage sibling containers via mounted Docker socket.
All crosshot containers are identified by the label crosshot.managed=true.
"""

import json
import logging
from datetime import datetime, timezone

import docker
from docker.errors import APIError, DockerException, NotFound

from apps.database.models import AgentConfig, Database

logger = logging.getLogger(__name__)


class AgentService:
    """Service for managing agent configurations and Docker containers."""

    MANAGED_LABEL = "crosshot.managed=true"

    def __init__(self, db_path: str = "data/xhs.db"):
        self.db = Database(db_path)
        self._docker_client: docker.DockerClient | None = None

    @property
    def docker_client(self) -> docker.DockerClient:
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
            except DockerException as e:
                logger.error(f"Failed to connect to Docker: {e}")
                raise
        return self._docker_client

    # ─── Container Operations ───

    def list_containers(self) -> list[dict]:
        """List all crosshot-managed containers with status and metadata."""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": [self.MANAGED_LABEL]},
            )
        except DockerException as e:
            logger.error(f"Docker list failed: {e}")
            return []

        result = []
        for c in containers:
            labels = c.labels or {}
            status = c.status
            simplified = (
                "running" if status == "running"
                else "stopped" if status in ("exited", "created")
                else "error" if status in ("dead", "removing")
                else status
            )

            uptime_seconds = None
            started_at = None
            if status == "running":
                try:
                    started_str = c.attrs.get("State", {}).get("StartedAt", "")
                    if started_str and not started_str.startswith("0001"):
                        started_at = started_str
                        clean = started_str.split(".")[0] + "+00:00"
                        started_dt = datetime.fromisoformat(clean)
                        uptime_seconds = int(
                            (datetime.now(timezone.utc) - started_dt).total_seconds()
                        )
                except Exception:
                    pass

            result.append({
                "id": c.short_id,
                "container_id": c.id,
                "name": c.name,
                "status": simplified,
                "docker_status": status,
                "agent_type": labels.get("crosshot.agent.type", "unknown"),
                "platform": labels.get("crosshot.agent.platform", "unknown"),
                "image": c.image.tags[0] if c.image and c.image.tags else "unknown",
                "started_at": started_at,
                "uptime_seconds": uptime_seconds,
                "created_by": labels.get("crosshot.agent.created_by", "compose"),
            })

        return result

    def get_container_stats(self, container_id: str) -> dict:
        """Get CPU and memory stats for a specific container."""
        try:
            container = self.docker_client.containers.get(container_id)
            stats = container.stats(stream=False)

            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"]
                - stats["precpu_stats"]["system_cpu_usage"]
            )
            num_cpus = stats["cpu_stats"].get("online_cpus", 1)
            cpu_percent = (
                (cpu_delta / system_delta) * num_cpus * 100.0
                if system_delta > 0 else 0.0
            )

            mem_usage = stats["memory_stats"].get("usage", 0)
            mem_limit = stats["memory_stats"].get("limit", 1)
            mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0.0

            return {
                "cpu_percent": round(cpu_percent, 2),
                "memory_usage_mb": round(mem_usage / (1024 * 1024), 1),
                "memory_limit_mb": round(mem_limit / (1024 * 1024), 1),
                "memory_percent": round(mem_percent, 2),
            }
        except NotFound:
            return {"error": "Container not found"}
        except Exception as e:
            return {"error": str(e)}

    def get_container_logs(self, container_id: str, tail: int = 100) -> str:
        """Get container stdout/stderr logs."""
        try:
            container = self.docker_client.containers.get(container_id)
            logs = container.logs(
                tail=tail, timestamps=True, stdout=True, stderr=True
            )
            return logs.decode("utf-8", errors="replace")
        except NotFound:
            return "Container not found"
        except Exception as e:
            return f"Error fetching logs: {e}"

    def start_container(self, container_id: str) -> dict:
        """Start a stopped container."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.start()
            return {"success": True, "message": f"Container {container.name} started"}
        except NotFound:
            return {"success": False, "message": "Container not found"}
        except APIError as e:
            return {"success": False, "message": str(e)}

    def stop_container(self, container_id: str) -> dict:
        """Stop a running container."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.stop(timeout=10)
            return {"success": True, "message": f"Container {container.name} stopped"}
        except NotFound:
            return {"success": False, "message": "Container not found"}
        except APIError as e:
            return {"success": False, "message": str(e)}

    def restart_container(self, container_id: str) -> dict:
        """Restart a container."""
        try:
            container = self.docker_client.containers.get(container_id)
            container.restart(timeout=10)
            return {"success": True, "message": f"Container {container.name} restarted"}
        except NotFound:
            return {"success": False, "message": "Container not found"}
        except APIError as e:
            return {"success": False, "message": str(e)}

    def create_agent_instance(
        self,
        config_id: int,
        instance_name: str,
        extra_env: dict | None = None,
    ) -> dict:
        """Create and start a new agent container from an AgentConfig template."""
        session = self.db.get_session()
        try:
            config = session.query(AgentConfig).filter_by(id=config_id).first()
            if not config:
                return {"success": False, "message": f"AgentConfig {config_id} not found"}

            env = config.get_environment()
            env["PYTHONUNBUFFERED"] = "1"
            if extra_env:
                env.update(extra_env)

            container_name = f"crosshot-ai-{instance_name}"

            image = self._resolve_image()

            labels = {
                "crosshot.managed": "true",
                "crosshot.agent.type": config.agent_type,
                "crosshot.agent.platform": config.platform,
                "crosshot.agent.config_id": str(config.id),
                "crosshot.agent.created_by": "api",
            }

            volumes = self._resolve_volumes()

            container = self.docker_client.containers.run(
                image=image,
                command=config.command,
                name=container_name,
                detach=True,
                environment=env,
                labels=labels,
                volumes=volumes,
                restart_policy={"Name": config.restart_policy},
                mem_limit=config.memory_limit,
                cpu_quota=int(float(config.cpu_limit) * 100000),
                cpu_period=100000,
            )

            return {
                "success": True,
                "message": f"Agent '{container_name}' created and started",
                "container_id": container.short_id,
                "container_name": container_name,
            }

        except Exception as e:
            logger.error(f"Failed to create agent instance: {e}")
            return {"success": False, "message": str(e)}
        finally:
            session.close()

    def remove_container(self, container_id: str) -> dict:
        """Stop and remove a container (only API-created ones)."""
        try:
            container = self.docker_client.containers.get(container_id)
            labels = container.labels or {}

            if labels.get("crosshot.agent.created_by") != "api":
                return {
                    "success": False,
                    "message": "Cannot remove compose-managed containers. Use docker-compose instead.",
                }

            container.stop(timeout=10)
            container.remove()
            return {"success": True, "message": f"Container {container.name} removed"}
        except NotFound:
            return {"success": False, "message": "Container not found"}
        except APIError as e:
            return {"success": False, "message": str(e)}

    # ─── AgentConfig CRUD ───

    def list_agent_configs(self) -> list[dict]:
        """List all active agent config templates."""
        session = self.db.get_session()
        try:
            configs = (
                session.query(AgentConfig)
                .filter(AgentConfig.is_active == 1)
                .order_by(AgentConfig.agent_type, AgentConfig.platform)
                .all()
            )
            return [
                {
                    "id": c.id,
                    "name": c.name,
                    "display_name": c.display_name,
                    "agent_type": c.agent_type,
                    "platform": c.platform,
                    "description": c.description,
                    "command": c.command,
                    "environment": c.get_environment(),
                    "cpu_limit": c.cpu_limit,
                    "memory_limit": c.memory_limit,
                    "restart_policy": c.restart_policy,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in configs
            ]
        finally:
            session.close()

    def get_agent_config(self, config_id: int) -> dict | None:
        """Get a single agent config by ID."""
        session = self.db.get_session()
        try:
            c = session.query(AgentConfig).filter_by(id=config_id).first()
            if not c:
                return None
            return {
                "id": c.id,
                "name": c.name,
                "display_name": c.display_name,
                "agent_type": c.agent_type,
                "platform": c.platform,
                "description": c.description,
                "command": c.command,
                "environment": c.get_environment(),
                "cpu_limit": c.cpu_limit,
                "memory_limit": c.memory_limit,
                "cpu_reservation": c.cpu_reservation,
                "memory_reservation": c.memory_reservation,
                "restart_policy": c.restart_policy,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
        finally:
            session.close()

    # ─── Internal helpers ───

    def _resolve_image(self) -> str:
        """Find the Docker image used by existing crosshot containers."""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": [self.MANAGED_LABEL]},
            )
            for c in containers:
                if c.image and c.image.tags:
                    return c.image.tags[0]
        except Exception:
            pass
        return "crosshot-ai-api:latest"

    def _resolve_volumes(self) -> dict:
        """Extract volume mounts from an existing container to reuse."""
        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={"label": [self.MANAGED_LABEL]},
            )
            for c in containers:
                mounts = c.attrs.get("Mounts", [])
                volumes = {}
                for m in mounts:
                    if m["Type"] == "bind":
                        # Skip docker socket mount
                        if "docker.sock" in m.get("Source", ""):
                            continue
                        volumes[m["Source"]] = {
                            "bind": m["Destination"],
                            "mode": m.get("Mode", "rw"),
                        }
                if volumes:
                    return volumes
        except Exception:
            pass
        return {}

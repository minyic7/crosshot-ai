"""BaseAgent — the core abstraction for all agents in crosshot-ai.

Every agent (crawler, coordinator, analyzer, scheduler) is an instance of
BaseAgent configured with different labels, tools, and system prompts.

Key capabilities:
- Queue consumption: pop tasks from Redis by label, execute, push new tasks
- ReAct loop: Reason + Act cycle using LLM function calling
- Heartbeat: writes status to Redis every 10s for monitoring
- Graceful shutdown: handles SIGTERM/SIGINT for Docker stop
"""

import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

import redis.asyncio as aioredis
import yaml
from openai import AsyncOpenAI

from shared.config.settings import get_settings
from shared.models.agent import AgentHeartbeat
from shared.models.task import RetryLater, Task, TaskStatus
from shared.queue.redis_queue import TaskQueue
from shared.tools.base import Tool

logger = logging.getLogger(__name__)


@dataclass
class Result:
    """Result of executing a task.

    Agents return this from execute(). new_tasks will be pushed back to the queue,
    enabling agent-to-agent communication through the task system.
    """

    data: Any = None
    new_tasks: list[Task] = field(default_factory=list)


class BaseAgent:
    """Base class for all agents. Configured via agents.yaml, not subclassed.

    Usage:
        agent = BaseAgent.from_config("crawler-xhs")
        agent.tools = [scrape_page, save_results]
        await agent.run()
    """

    def __init__(
        self,
        name: str,
        labels: list[str],
        tools: list[Tool] | None = None,
        system_prompt: str = "",
        ai_enabled: bool = False,
        fan_in_enabled: bool = False,
        llm_config: dict | None = None,
    ) -> None:
        self.name = name
        self.labels = labels
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.ai_enabled = ai_enabled
        self.fan_in_enabled = fan_in_enabled
        self.llm_config = llm_config or {}

        # Hierarchy metadata (populated by from_config)
        self.parent: str | None = None
        self.children: list[str] = []
        self.skill_names: list[str] = []

        self._shutdown_event = asyncio.Event()
        self._settings = get_settings()
        self._queue = TaskQueue(self._settings.redis_url)
        self._redis = aioredis.from_url(self._settings.redis_url, decode_responses=True)
        self._llm: AsyncOpenAI | None = None

        # Heartbeat state
        self._current_task: Task | None = None
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._started_at: datetime = datetime.now()

    @classmethod
    def from_config(cls, agent_name: str) -> "BaseAgent":
        """Create an agent from agents.yaml configuration.

        Args:
            agent_name: key in agents.yaml (e.g. "crawler-xhs", "coordinator")

        Returns:
            Configured BaseAgent instance.
        """
        config_path = Path(__file__).parent.parent / "config" / "agents.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        agent_config = config["agents"].get(agent_name)
        if not agent_config:
            raise ValueError(
                f"Agent '{agent_name}' not found in agents.yaml. "
                f"Available: {list(config['agents'].keys())}"
            )

        agent = cls(
            name=agent_name,
            labels=agent_config["labels"],
            system_prompt=agent_config.get("system_prompt", ""),
            ai_enabled=agent_config.get("ai_enabled", False),
            fan_in_enabled=agent_config.get("fan_in", False),
            llm_config=agent_config.get("llm", {}),
        )

        # Hierarchy metadata
        agent.parent = agent_config.get("parent")
        agent.children = agent_config.get("children", [])
        agent.skill_names = agent_config.get("skills", [])

        return agent

    # ──────────────────────────────────────────────
    # Heartbeat
    # ──────────────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Write heartbeat to Redis every 10s. Expires after 30s."""
        while not self._shutdown_event.is_set():
            try:
                heartbeat = AgentHeartbeat(
                    name=self.name,
                    labels=self.labels,
                    status="busy" if self._current_task else "idle",
                    current_task_id=self._current_task.id if self._current_task else None,
                    current_task_label=self._current_task.label if self._current_task else None,
                    tasks_completed=self._tasks_completed,
                    tasks_failed=self._tasks_failed,
                    started_at=self._started_at,
                    last_heartbeat=datetime.now(),
                )
                await self._redis.set(
                    f"agent:heartbeat:{self.name}",
                    heartbeat.model_dump_json(),
                    ex=30,
                )
            except Exception:
                logger.warning("Failed to write heartbeat", exc_info=True)
            await asyncio.sleep(10)

    # ──────────────────────────────────────────────
    # Fan-in (generic progress countdown)
    # ──────────────────────────────────────────────

    @staticmethod
    def _extract_entity(task: Task) -> tuple[str, str] | tuple[None, None]:
        """Extract (entity_type, entity_id) from a task payload."""
        topic_id = task.payload.get("topic_id")
        if topic_id:
            return "topic", topic_id
        user_id = task.payload.get("user_id")
        if user_id:
            return "user", user_id
        return None, None

    async def _handle_fan_in(self, task: Task) -> None:
        """Decrement entity pending counter; trigger on_complete task if last."""
        entity_type, entity_id = self._extract_entity(task)
        if not entity_id:
            return

        pending_key = f"{entity_type}:{entity_id}:pending"
        progress_key = f"{entity_type}:{entity_id}:progress"

        # Atomic: decrement pending + update progress
        pipe = self._redis.pipeline()
        pipe.decr(pending_key)
        pipe.hincrby(progress_key, "done", 1)
        pipe.hset(progress_key, "updated_at", datetime.now(timezone.utc).isoformat())
        results = await pipe.execute()
        remaining = results[0]

        logger.info("%s %s: task done, remaining=%s", entity_type, entity_id, max(remaining, 0))

        if remaining <= 0:
            on_complete_key = f"{entity_type}:{entity_id}:on_complete"
            # Atomic GETDEL prevents race where two agents both read the key
            on_complete_raw = await self._redis.getdel(on_complete_key)
            if on_complete_raw:
                cfg = json.loads(on_complete_raw)
                payload = cfg.get("payload", {})

                # Collect child task results for feedback to parent
                child_results = await self._collect_child_results(
                    entity_type, entity_id,
                )
                if child_results:
                    payload["child_results"] = child_results

                next_task = Task(
                    label=cfg["label"],
                    payload=payload,
                    parent_job_id=task.parent_job_id,
                )
                await self._queue.push(next_task)
                next_phase = cfg.get("next_phase", "summarizing")
                await self._redis.hset(progress_key, "phase", next_phase)
                logger.info(
                    "%s %s: fan-in complete, triggered %s (child_results=%d)",
                    entity_type, entity_id, next_task.label, len(child_results),
                )

            # Clean up task progress keys and pending counter
            task_ids_key = f"{entity_type}:{entity_id}:task_ids"
            task_ids = await self._redis.smembers(task_ids_key)
            cleanup_keys = [pending_key, task_ids_key]
            if task_ids:
                cleanup_keys.extend(f"task:{tid}:progress" for tid in task_ids)
            await self._redis.delete(*cleanup_keys)

    async def _collect_child_results(
        self, entity_type: str, entity_id: str,
    ) -> list[dict]:
        """Collect results from completed child tasks for fan-in feedback.

        Returns a compact summary of each child task's outcome so the parent
        (e.g., analyst:summarize) can review what happened.
        """
        task_ids_key = f"{entity_type}:{entity_id}:task_ids"
        task_ids = await self._redis.smembers(task_ids_key)
        if not task_ids:
            return []

        results: list[dict] = []
        for tid in task_ids:
            raw = await self._redis.get(f"task:{tid}")
            if not raw:
                continue
            try:
                child = json.loads(raw)
                results.append({
                    "task_id": tid,
                    "label": child.get("label", ""),
                    "status": child.get("status", ""),
                    "result": child.get("result"),
                })
            except (json.JSONDecodeError, KeyError):
                pass

        logger.info(
            "Collected %d child results for %s %s", len(results),
            entity_type, entity_id,
        )
        return results

    # ──────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop: consume tasks from queue, execute, push results.

        Runs until SIGTERM/SIGINT is received (Docker stop).
        """
        self._register_signals()
        self._started_at = datetime.now()
        logger.info(
            "Agent '%s' starting | labels=%s | ai_enabled=%s | tools=%s",
            self.name,
            self.labels,
            self.ai_enabled,
            [t.name for t in self.tools],
        )

        # Recover orphaned tasks from PostgreSQL (lost on Redis restart)
        try:
            recovered = await self._queue.recover_from_pg(self.labels)
            if recovered:
                logger.info("Recovered %d orphaned tasks into Redis queue", recovered)
        except Exception:
            logger.warning("Task recovery from PG failed (non-fatal)", exc_info=True)

        # Start heartbeat in background
        heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            while not self._shutdown_event.is_set():
                task = await self._queue.pop(self.labels, agent_name=self.name)

                if task is None:
                    await asyncio.sleep(5)
                    continue

                self._current_task = task
                logger.info(
                    "Executing task %s (label=%s, priority=%s)",
                    task.id,
                    task.label,
                    task.priority.name,
                )

                try:
                    result = await self.execute(task)

                    # Mark task as done
                    await self._queue.mark_done(task, result.data)
                    self._tasks_completed += 1

                    # Push any new tasks produced by this execution
                    sub_task_ids: list[str] = []
                    for new_task in result.new_tasks:
                        await self._queue.push(new_task)
                        sub_task_ids.append(new_task.id)
                        logger.info(
                            "Pushed new task %s (label=%s) from task %s",
                            new_task.id,
                            new_task.label,
                            task.id,
                        )

                    # Store sub-task IDs in Redis for progress tracking
                    if sub_task_ids:
                        et, eid = self._extract_entity(task)
                        if et and eid:
                            key = f"{et}:{eid}:task_ids"
                            await self._redis.delete(key)
                            await self._redis.sadd(key, *sub_task_ids)
                            await self._redis.expire(key, 86400)

                except RetryLater as e:
                    logger.warning(
                        "Task %s deferred for %ds: %s",
                        task.id,
                        e.delay_seconds,
                        e.reason,
                    )
                    await self._queue.requeue_delayed(task, e.delay_seconds)
                except Exception as e:
                    logger.error("Task %s failed: %s", task.id, e, exc_info=True)
                    await self._queue.mark_failed(task, str(e))
                    self._tasks_failed += 1
                finally:
                    # Only fire fan-in when task is truly finished (success
                    # or permanent failure), NOT on retries — otherwise each
                    # retry attempt decrements the pending counter again.
                    if self.fan_in_enabled and task.status in (
                        TaskStatus.COMPLETED,
                        TaskStatus.FAILED,
                    ):
                        try:
                            await self._handle_fan_in(task)
                        except Exception:
                            logger.warning("Fan-in failed for task %s", task.id, exc_info=True)
                    self._current_task = None

        except asyncio.CancelledError:
            logger.info("Agent '%s' cancelled", self.name)
        finally:
            heartbeat_task.cancel()
            await self._redis.delete(f"agent:heartbeat:{self.name}")
            await self._redis.aclose()
            await self._queue.close()
            logger.info("Agent '%s' stopped", self.name)

    # ──────────────────────────────────────────────
    # Task execution
    # ──────────────────────────────────────────────

    async def execute(self, task: Task) -> Result:
        """Execute a task. Override this or rely on ReAct for ai_enabled agents.

        For ai_enabled=True agents, this defaults to the ReAct loop.
        For ai_enabled=False agents, this raises NotImplementedError
        (the caller should set agent.execute = custom_fn or override).
        """
        if self.ai_enabled:
            return await self.react(task)
        raise NotImplementedError(
            f"Agent '{self.name}' has ai_enabled=False. "
            f"Set agent.execute to a custom function or enable AI."
        )

    # ──────────────────────────────────────────────
    # ReAct loop
    # ──────────────────────────────────────────────

    async def react(
        self,
        task: Task,
        max_steps: int = 10,
        system_prompt: str | None = None,
        on_step: Callable[[str, dict], Awaitable[None]] | None = None,
    ) -> Result:
        """ReAct (Reasoning + Acting) loop using LLM function calling.

        1. Send system prompt + task description to LLM with available tools
        2. If LLM returns tool_calls → execute tools → append observations → continue
        3. If LLM returns text (no tool_calls) → parse as final result
        4. Repeat until done or max_steps exceeded

        Args:
            task: The task to process.
            max_steps: Max tool-calling iterations before timeout.
            system_prompt: Override the agent's default system prompt (e.g., for
                per-task dynamic prompts with entity context + skills).
            on_step: Optional async callback invoked before each tool execution
                with (tool_name, tool_args). Used for progress reporting.
        """
        llm = self._get_llm()
        tools_schema = [t.to_openai_schema() for t in self.tools] or None

        messages = [
            {"role": "system", "content": system_prompt or self.system_prompt},
            {
                "role": "user",
                "content": (
                    f"Task ID: {task.id}\n"
                    f"Label: {task.label}\n"
                    f"Payload: {json.dumps(task.payload, ensure_ascii=False)}"
                ),
            },
        ]

        for step in range(max_steps):
            logger.debug("ReAct step %d/%d for task %s", step + 1, max_steps, task.id)

            response = await llm.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools_schema,
            )

            choice = response.choices[0]
            message = choice.message

            # No tool calls → final answer
            if not message.tool_calls:
                return self._parse_final_response(message.content or "")

            # Has tool calls → execute each tool
            messages.append(message.model_dump())
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                logger.info(
                    "ReAct calling tool '%s' with args: %s", tool_name, tool_args
                )

                if on_step:
                    try:
                        await on_step(tool_name, tool_args)
                    except Exception:
                        logger.debug("on_step callback failed", exc_info=True)

                try:
                    observation = await self._execute_tool(tool_name, tool_args)
                except Exception as e:
                    observation = f"Error: {e}"

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(observation, default=str, ensure_ascii=False),
                    }
                )

        raise TimeoutError(
            f"ReAct exceeded {max_steps} steps for task {task.id}"
        )

    # ──────────────────────────────────────────────
    # Tool execution
    # ──────────────────────────────────────────────

    def _get_tool(self, name: str) -> Tool:
        """Find a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        raise ValueError(
            f"Tool '{name}' not found. Available: {[t.name for t in self.tools]}"
        )

    async def _execute_tool(self, name: str, arguments: dict) -> Any:
        """Execute a tool by name with given arguments."""
        tool = self._get_tool(name)
        return await tool.execute(**arguments)

    # ──────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────

    @property
    def model(self) -> str:
        """LLM model name — per-agent override or global default."""
        return self.llm_config.get("model") or self._settings.grok_model

    def _get_llm(self) -> AsyncOpenAI:
        """Get or create the LLM client."""
        if self._llm is None:
            import os

            api_key_env = self.llm_config.get("api_key_env", "")
            api_key = os.environ.get(api_key_env) if api_key_env else None
            self._llm = AsyncOpenAI(
                api_key=api_key or self._settings.grok_api_key,
                base_url=self.llm_config.get("base_url") or self._settings.grok_base_url,
            )
        return self._llm

    def _parse_final_response(self, content: str) -> Result:
        """Parse the LLM's final text response into a Result."""
        # Try to parse as JSON (may contain new_tasks)
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "new_tasks" in data:
                new_tasks = [Task(**t) for t in data["new_tasks"]]
                return Result(data=data.get("data"), new_tasks=new_tasks)
            return Result(data=data)
        except (json.JSONDecodeError, TypeError):
            return Result(data=content)

    def _register_signals(self) -> None:
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown, sig)

    def _handle_shutdown(self, sig: signal.Signals) -> None:
        """Handle shutdown signal."""
        logger.info("Agent '%s' received %s, shutting down...", self.name, sig.name)
        self._shutdown_event.set()

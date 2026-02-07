"""BaseAgent — the core abstraction for all agents in crosshot-ai.

Every agent (crawler, coordinator, analyzer, scheduler) is an instance of
BaseAgent configured with different labels, tools, and system prompts.

Key capabilities:
- Queue consumption: pop tasks from Redis by label, execute, push new tasks
- ReAct loop: Reason + Act cycle using LLM function calling
- Graceful shutdown: handles SIGTERM/SIGINT for Docker stop
"""

import asyncio
import json
import logging
import os
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from openai import AsyncOpenAI

from shared.config.settings import get_settings
from shared.models.task import Task, TaskStatus
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
    ) -> None:
        self.name = name
        self.labels = labels
        self.tools = tools or []
        self.system_prompt = system_prompt
        self.ai_enabled = ai_enabled

        self._shutdown_event = asyncio.Event()
        self._settings = get_settings()
        self._queue = TaskQueue(self._settings.redis_url)
        self._llm: AsyncOpenAI | None = None

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

        return cls(
            name=agent_name,
            labels=agent_config["labels"],
            system_prompt=agent_config.get("system_prompt", ""),
            ai_enabled=agent_config.get("ai_enabled", False),
        )

    # ──────────────────────────────────────────────
    # Main loop
    # ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop: consume tasks from queue, execute, push results.

        Runs until SIGTERM/SIGINT is received (Docker stop).
        """
        self._register_signals()
        logger.info(
            "Agent '%s' starting | labels=%s | ai_enabled=%s | tools=%s",
            self.name,
            self.labels,
            self.ai_enabled,
            [t.name for t in self.tools],
        )

        try:
            while not self._shutdown_event.is_set():
                task = await self._queue.pop(self.labels)

                if task is None:
                    await asyncio.sleep(5)
                    continue

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

                    # Push any new tasks produced by this execution
                    for new_task in result.new_tasks:
                        await self._queue.push(new_task)
                        logger.info(
                            "Pushed new task %s (label=%s) from task %s",
                            new_task.id,
                            new_task.label,
                            task.id,
                        )

                except Exception as e:
                    logger.error("Task %s failed: %s", task.id, e, exc_info=True)
                    await self._queue.mark_failed(task, str(e))

        except asyncio.CancelledError:
            logger.info("Agent '%s' cancelled", self.name)
        finally:
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

    async def react(self, task: Task, max_steps: int = 10) -> Result:
        """ReAct (Reasoning + Acting) loop using LLM function calling.

        1. Send system prompt + task description to LLM with available tools
        2. If LLM returns tool_calls → execute tools → append observations → continue
        3. If LLM returns text (no tool_calls) → parse as final result
        4. Repeat until done or max_steps exceeded
        """
        llm = self._get_llm()
        tools_schema = [t.to_openai_schema() for t in self.tools] or None

        messages = [
            {"role": "system", "content": self.system_prompt},
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
                model=self._settings.grok_model,
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

    def _get_llm(self) -> AsyncOpenAI:
        """Get or create the LLM client."""
        if self._llm is None:
            self._llm = AsyncOpenAI(
                api_key=self._settings.grok_api_key,
                base_url=self._settings.grok_base_url,
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

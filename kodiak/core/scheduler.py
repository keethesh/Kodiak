"""
Event-driven command scheduler for ManagerAgent.

Keeps command execution non-blocking so the manager can replan as results
arrive, while preserving bounded concurrency.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.worker import CommandResult, CommandTask, execute_command


@dataclass
class SchedulerEvent:
    """One scheduler lifecycle event for a command task."""

    event_type: str
    task_id: str
    tool: str
    command: str
    status: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    result: Optional[CommandResult] = None
    message: str = ""


class EventDrivenScheduler:
    """
    Bounded-concurrency scheduler that streams task lifecycle events.

    Events emitted:
      - task_queued
      - task_started
      - task_completed
      - task_failed
      - task_timeout
      - task_cancelled
    """

    def __init__(
        self,
        *,
        global_concurrency: int = 4,
        event_manager: Optional[TUIEventManager] = None,
        scan_id: Optional[str] = None,
        agent_id: str = "manager",
    ) -> None:
        self._sem = asyncio.Semaphore(max(1, int(global_concurrency)))
        self._event_manager = event_manager
        self._scan_id = scan_id
        self._agent_id = agent_id
        self._queue: asyncio.Queue[SchedulerEvent] = asyncio.Queue()
        self._jobs: Dict[str, asyncio.Task] = {}
        self._tasks: Dict[str, CommandTask] = {}
        self._states: Dict[str, str] = {}

    @staticmethod
    def _tool_label(command: str) -> str:
        return command.split()[0] if command.strip() else "cmd"

    async def submit(self, task: CommandTask) -> bool:
        """Submit a command task. Returns False if task_id already exists."""
        if task.task_id in self._jobs:
            return False

        self._tasks[task.task_id] = task
        self._states[task.task_id] = "queued"
        await self._emit_event(
            SchedulerEvent(
                event_type="task_queued",
                task_id=task.task_id,
                tool=self._tool_label(task.command),
                command=task.command,
                status="queued",
            )
        )

        self._jobs[task.task_id] = asyncio.create_task(
            self._run_task(task),
            name=f"kodiak-task-{task.task_id}",
        )
        return True

    async def cancel(self, task_id: str) -> bool:
        """Cancel a task by task_id. Returns True if cancellation was requested."""
        job = self._jobs.get(task_id)
        if not job or job.done():
            return False
        job.cancel()
        return True

    async def cancel_all(self) -> None:
        """Cancel all in-flight tasks and await their teardown."""
        jobs = [j for j in self._jobs.values() if not j.done()]
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    async def next_event(self, timeout_seconds: Optional[float] = None) -> Optional[SchedulerEvent]:
        """Wait for the next scheduler event. Returns None on timeout."""
        if timeout_seconds is None:
            return await self._queue.get()
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            return None

    def has_inflight(self) -> bool:
        return any(not job.done() for job in self._jobs.values())

    @property
    def running_count(self) -> int:
        return sum(1 for state in self._states.values() if state == "running")

    @property
    def pending_count(self) -> int:
        return sum(1 for state in self._states.values() if state == "queued")

    def running_task_ids(self) -> List[str]:
        return [tid for tid, state in self._states.items() if state == "running"]

    def snapshot_states(self) -> Dict[str, str]:
        return dict(self._states)

    async def _run_task(self, task: CommandTask) -> None:
        task_id = task.task_id
        tool = self._tool_label(task.command)
        started = False
        result: Optional[CommandResult] = None

        try:
            async with self._sem:
                started = True
                self._states[task_id] = "running"

                if self._event_manager:
                    try:
                        await self._event_manager.emit_tool_start(
                            tool_name=tool,
                            target=task.command[:80],
                            agent_id=self._agent_id,
                            scan_id=self._scan_id,
                        )
                    except Exception:
                        pass

                await self._emit_event(
                    SchedulerEvent(
                        event_type="task_started",
                        task_id=task_id,
                        tool=tool,
                        command=task.command,
                        status="running",
                    )
                )

                result = await execute_command(task, self._sem)

            if result.timed_out:
                event_type = "task_timeout"
                status = "timeout"
            elif result.exit_code == 0:
                event_type = "task_completed"
                status = "success"
            else:
                event_type = "task_failed"
                status = "failed"

            self._states[task_id] = status

            if self._event_manager:
                try:
                    await self._event_manager.emit_tool_complete(
                        tool_name=tool,
                        result=result,
                        scan_id=self._scan_id,
                    )
                except Exception:
                    pass

            await self._emit_event(
                SchedulerEvent(
                    event_type=event_type,
                    task_id=task_id,
                    tool=tool,
                    command=task.command,
                    status=status,
                    result=result,
                )
            )
        except asyncio.CancelledError:
            self._states[task_id] = "cancelled"
            cancel_result = result or CommandResult(
                task_id=task_id,
                command=task.command,
                rationale=task.rationale,
                stdout="",
                stderr="Task cancelled by manager",
                exit_code=-2,
                duration_seconds=0.0,
                timed_out=False,
            )

            if self._event_manager and started:
                try:
                    await self._event_manager.emit_tool_complete(
                        tool_name=tool,
                        result=cancel_result,
                        scan_id=self._scan_id,
                    )
                except Exception:
                    pass

            await self._emit_event(
                SchedulerEvent(
                    event_type="task_cancelled",
                    task_id=task_id,
                    tool=tool,
                    command=task.command,
                    status="cancelled",
                    result=cancel_result if started else None,
                    message="Cancelled by manager action",
                )
            )
        except Exception as exc:
            logger.warning(f"Scheduler task wrapper failed: {exc} — {task.command[:80]}")
            self._states[task_id] = "failed"
            fail_result = CommandResult(
                task_id=task_id,
                command=task.command,
                rationale=task.rationale,
                stdout="",
                stderr=str(exc)[:500],
                exit_code=-1,
                duration_seconds=0.0,
                timed_out=False,
            )
            await self._emit_event(
                SchedulerEvent(
                    event_type="task_failed",
                    task_id=task_id,
                    tool=tool,
                    command=task.command,
                    status="failed",
                    result=fail_result,
                    message="Scheduler wrapper exception",
                )
            )
        finally:
            self._jobs.pop(task_id, None)

    async def _emit_event(self, event: SchedulerEvent) -> None:
        await self._queue.put(event)


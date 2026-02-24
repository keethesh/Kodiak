"""
Worker — lightweight async tool executor for the Manager-Worker architecture.

Workers make ZERO LLM calls.  They receive a tool name + arguments, execute
the tool via the existing ``ToolInventory`` / ``DockerExecutor`` stack, and
return a structured ``WorkerResult``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import uuid4

from loguru import logger

from kodiak.core.tools.base import ToolResult
from kodiak.core.tools.inventory import ToolInventory
from kodiak.api.events import TUIEventManager


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class WorkerTask:
    """A single unit of work dispatched by the Manager."""
    tool_name: str
    args: Dict[str, Any]
    task_id: str = field(default_factory=lambda: uuid4().hex[:12])


@dataclass
class WorkerResult:
    """Structured result returned to the Manager."""
    task_id: str
    tool_name: str
    target: str
    success: bool
    output: str
    data: Dict[str, Any]
    error: Optional[str]
    duration_seconds: float

    @property
    def summary(self) -> str:
        """One-line human-readable summary for the Manager's scan state."""
        if self.error:
            return f"error: {self.error[:120]}"
        if not self.success:
            return f"failed ({len(self.output)} chars output)"
        # Compact summary: first meaningful line
        for line in self.output.splitlines():
            stripped = line.strip()
            if stripped and len(stripped) > 5:
                return stripped[:150]
        return "completed (no output)"


# ---------------------------------------------------------------------------
# Single-task executor
# ---------------------------------------------------------------------------

async def execute_worker_task(
    task: WorkerTask,
    tool_inventory: ToolInventory,
    semaphore: asyncio.Semaphore,
) -> WorkerResult:
    """
    Execute a single tool call.  Respects concurrency via *semaphore*.

    This is the core worker function — no LLM, no DB writes, no coordination.
    """
    target = task.args.get("target", task.args.get("url", task.args.get("domain", "unknown")))
    t0 = time.monotonic()

    tool = tool_inventory.get(task.tool_name)
    if tool is None:
        return WorkerResult(
            task_id=task.task_id,
            tool_name=task.tool_name,
            target=str(target),
            success=False,
            output="",
            data={},
            error=f"Tool '{task.tool_name}' not found in inventory",
            duration_seconds=0.0,
        )

    try:
        async with semaphore:
            result: ToolResult = await tool.execute(**task.args)

        elapsed = time.monotonic() - t0
        return WorkerResult(
            task_id=task.task_id,
            tool_name=task.tool_name,
            target=str(target),
            success=result.success,
            output=result.output or "",
            data=result.data or {},
            error=result.error,
            duration_seconds=round(elapsed, 2),
        )
    except asyncio.TimeoutError:
        return WorkerResult(
            task_id=task.task_id,
            tool_name=task.tool_name,
            target=str(target),
            success=False,
            output="",
            data={},
            error="Worker task timed out",
            duration_seconds=round(time.monotonic() - t0, 2),
        )
    except Exception as exc:
        logger.warning(f"Worker task {task.tool_name}({target}) failed: {exc}")
        return WorkerResult(
            task_id=task.task_id,
            tool_name=task.tool_name,
            target=str(target),
            success=False,
            output="",
            data={},
            error=str(exc)[:300],
            duration_seconds=round(time.monotonic() - t0, 2),
        )


# ---------------------------------------------------------------------------
# Batch dispatcher
# ---------------------------------------------------------------------------

# Default per-tool concurrency limits
DEFAULT_CONCURRENCY: Dict[str, int] = {
    "nmap": 1,
    "sqlmap": 1,
    "commix": 1,
    "searchsploit": 1,
    "nuclei": 2,
    "ffuf": 2,
    "katana": 2,
    "whatweb": 3,
    "httpx": 3,
    "subfinder": 3,
}


async def dispatch_batch(
    tasks: List[WorkerTask],
    tool_inventory: ToolInventory,
    event_manager: Optional[TUIEventManager] = None,
    scan_id: Optional[str] = None,
    global_concurrency: int = 4,
) -> List[WorkerResult]:
    """
    Run all *tasks* concurrently, respecting per-tool concurrency limits.

    Emits ``tool_start`` / ``tool_complete`` TUI events so the UI stays
    responsive during batch execution.
    """
    if not tasks:
        return []

    # Build per-tool semaphores
    semaphores: Dict[str, asyncio.Semaphore] = {}
    global_sem = asyncio.Semaphore(global_concurrency)

    for task in tasks:
        if task.tool_name not in semaphores:
            limit = DEFAULT_CONCURRENCY.get(task.tool_name, global_concurrency)
            semaphores[task.tool_name] = asyncio.Semaphore(limit)

    async def _run_one(task: WorkerTask) -> WorkerResult:
        tool_sem = semaphores.get(task.tool_name, global_sem)
        target = task.args.get("target", task.args.get("url", task.args.get("domain", "unknown")))

        # Emit tool_start
        if event_manager:
            try:
                await event_manager.emit_tool_start(
                    tool_name=task.tool_name,
                    target=str(target),
                    agent_id="manager",
                    scan_id=scan_id,
                )
            except Exception:
                pass

        # Enforce both global and per-tool concurrency limits.
        async with global_sem:
            result = await execute_worker_task(task, tool_inventory, tool_sem)

        # Emit tool_complete
        if event_manager:
            try:
                await event_manager.emit_tool_complete(
                    tool_name=task.tool_name,
                    result=result,
                    scan_id=scan_id,
                )
            except Exception:
                pass

        return result

    # Dispatch all workers concurrently
    coros = [_run_one(t) for t in tasks]
    results = await asyncio.gather(*coros, return_exceptions=True)

    # Convert exceptions to WorkerResults
    final: List[WorkerResult] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            task = tasks[i]
            target = task.args.get("target", "unknown")
            logger.error(f"Worker exception for {task.tool_name}: {res}")
            final.append(WorkerResult(
                task_id=task.task_id,
                tool_name=task.tool_name,
                target=str(target),
                success=False,
                output="",
                data={},
                error=str(res)[:300],
                duration_seconds=0.0,
            ))
        else:
            final.append(res)

    return final

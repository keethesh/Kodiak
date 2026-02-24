"""
Worker — lightweight async command executor for the structured output architecture.

Workers make ZERO LLM calls.  They receive shell commands from the Manager's
structured output, execute them via DockerExecutor, and return stdout/stderr.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from uuid import uuid4

from loguru import logger

from kodiak.api.events import TUIEventManager


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CommandTask:
    """A single shell command to execute in the Docker sandbox."""
    command: str
    rationale: str
    timeout: int = 300
    task_id: str = field(default_factory=lambda: uuid4().hex[:12])


@dataclass
class CommandResult:
    """Result of executing a shell command."""
    task_id: str
    command: str
    rationale: str
    stdout: str
    stderr: str
    exit_code: int
    duration_seconds: float
    timed_out: bool = False

    def to_prompt_text(self) -> str:
        """Format for inclusion in the next LLM iteration as context."""
        status = "TIMED OUT" if self.timed_out else f"exit={self.exit_code}"
        header = f"[cmd] {self.command} ({status}, {self.duration_seconds:.1f}s)"

        # Combine stdout + stderr, truncate to keep history bounded
        output = self.stdout.strip()
        if self.stderr.strip():
            output += f"\n[stderr] {self.stderr.strip()}"

        # Truncate very long outputs to avoid blowing up the context window
        MAX_OUTPUT = 4000
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n... (truncated, {len(output)} chars total)"

        return f"{header}\n{output}" if output else header


# ---------------------------------------------------------------------------
# Single-command executor
# ---------------------------------------------------------------------------

async def execute_command(
    task: CommandTask,
    semaphore: asyncio.Semaphore,
) -> CommandResult:
    """
    Execute a single shell command inside the Docker sandbox.

    Uses the existing DockerExecutor infrastructure.
    """
    # Lazy import to avoid circular dependency at module load time
    from kodiak.core.tools.executor import get_docker_executor

    t0 = time.monotonic()

    try:
        executor = await get_docker_executor()

        try:
            result = await asyncio.wait_for(
                executor.run_command(["bash", "-c", task.command]),
                timeout=task.timeout,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - t0
            logger.warning(
                f"⏱️  Command timed out after {elapsed:.1f}s: {task.command[:80]}"
            )
            return CommandResult(
                task_id=task.task_id,
                command=task.command,
                rationale=task.rationale,
                stdout="",
                stderr="Command timed out",
                exit_code=-1,
                duration_seconds=round(elapsed, 2),
                timed_out=True,
            )

        elapsed = time.monotonic() - t0
        return CommandResult(
            task_id=task.task_id,
            command=task.command,
            rationale=task.rationale,
            stdout=getattr(result, "stdout", "") or "",
            stderr=getattr(result, "stderr", "") or "",
            exit_code=getattr(result, "exit_code", -1),
            duration_seconds=round(elapsed, 2),
        )

    except Exception as exc:
        logger.warning(f"Command execution failed: {exc} — {task.command[:80]}")
        return CommandResult(
            task_id=task.task_id,
            command=task.command,
            rationale=task.rationale,
            stdout="",
            stderr=str(exc)[:500],
            exit_code=-1,
            duration_seconds=round(time.monotonic() - t0, 2),
        )


# ---------------------------------------------------------------------------
# Batch dispatcher
# ---------------------------------------------------------------------------

async def dispatch_commands(
    commands: List[CommandTask],
    event_manager: Optional[TUIEventManager] = None,
    scan_id: Optional[str] = None,
    global_concurrency: int = 4,
) -> List[CommandResult]:
    """
    Run all commands concurrently, bounded by global_concurrency.

    Emits ``tool_start`` / ``tool_complete`` TUI events so the UI
    stays responsive during execution.
    """
    if not commands:
        return []

    sem = asyncio.Semaphore(global_concurrency)

    async def _run_one(task: CommandTask) -> CommandResult:
        # Extract a short label for TUI display
        label = task.command.split()[0] if task.command.strip() else "cmd"

        if event_manager:
            try:
                await event_manager.emit_tool_start(
                    tool_name=label,
                    target=task.command[:80],
                    agent_id="manager",
                    scan_id=scan_id,
                )
            except Exception:
                pass

        async with sem:
            result = await execute_command(task, sem)

        if event_manager:
            try:
                await event_manager.emit_tool_complete(
                    tool_name=label,
                    result=result,
                    scan_id=scan_id,
                )
            except Exception:
                pass

        return result

    coros = [_run_one(t) for t in commands]
    results = await asyncio.gather(*coros, return_exceptions=True)

    final: List[CommandResult] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            task = commands[i]
            logger.error(f"Command dispatch exception: {res}")
            final.append(CommandResult(
                task_id=task.task_id,
                command=task.command,
                rationale=task.rationale,
                stdout="",
                stderr=str(res)[:500],
                exit_code=-1,
                duration_seconds=0.0,
            ))
        else:
            final.append(res)

    return final

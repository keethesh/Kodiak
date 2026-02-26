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
    timeout: int = 600
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
    timeout_limit: int = 600

    def to_prompt_text(self) -> str:
        """Format for inclusion in the next LLM iteration as context."""
        if self.timed_out:
            status = f"TIMED OUT at {self.timeout_limit}s limit, ran {self.duration_seconds:.1f}s"
        else:
            status = f"exit={self.exit_code}, {self.duration_seconds:.1f}s"
        header = f"[cmd] {self.command} ({status})"

        # Combine stdout + stderr, truncate to keep history bounded
        output = self.stdout.strip()
        if self.stderr.strip():
            output += f"\n[stderr] {self.stderr.strip()}"

        # Truncate very long outputs to avoid blowing up the context window
        MAX_OUTPUT = 16000
        if len(output) > MAX_OUTPUT:
            output = output[:MAX_OUTPUT] + f"\n... (truncated, {len(output)} chars total)"

        return f"{header}\n{output}" if output else header


# ---------------------------------------------------------------------------
# Single-command executor
# ---------------------------------------------------------------------------

_cached_executor: Optional["DockerExecutor"] = None
_executor_lock = asyncio.Lock()

async def _get_cached_executor() -> "DockerExecutor":
    global _cached_executor
    if _cached_executor is not None:
        return _cached_executor
    async with _executor_lock:
        if _cached_executor is not None:
            return _cached_executor
        from kodiak.core.config import settings
        from kodiak.services.executor import get_docker_executor
        _cached_executor = await get_docker_executor(preferred_image=settings.toolbox_image)
        return _cached_executor


async def execute_command(
    task: CommandTask,
    semaphore: asyncio.Semaphore,
) -> CommandResult:
    """
    Execute a single shell command inside the Docker sandbox.

    Uses the existing DockerExecutor infrastructure, caching the executor
    to avoid re-running image availability checks for every task.

    On timeout, captures and returns whatever partial stdout/stderr the
    process produced before being killed — this is critical for long-running
    tools like nmap, nuclei, and sqlmap that emit results incrementally.
    """
    t0 = time.monotonic()

    try:
        executor = await _get_cached_executor()

        # We need direct subprocess control to capture partial output on
        # timeout.  Replicate the executor's docker command construction
        # but manage the process lifecycle ourselves.
        import os
        work_dir = os.getcwd()
        docker_cmd = [
            "docker", "run", "--rm",
            "-v", f"{work_dir}:/workspace",
            "-w", "/workspace",
            executor.image,
            "bash", "-c", task.command,
        ]

        process = await asyncio.create_subprocess_exec(
            *docker_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=task.timeout,
            )
            elapsed = time.monotonic() - t0
            return CommandResult(
                task_id=task.task_id,
                command=task.command,
                rationale=task.rationale,
                stdout=(stdout_bytes or b"").decode(errors="replace").strip(),
                stderr=(stderr_bytes or b"").decode(errors="replace").strip(),
                exit_code=process.returncode or 0,
                duration_seconds=round(elapsed, 2),
                timeout_limit=task.timeout,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Kill the process but harvest whatever output was buffered
            partial_stdout = ""
            partial_stderr = ""
            try:
                process.kill()
                # After kill, communicate() returns remaining buffered data
                remaining_stdout, remaining_stderr = await asyncio.wait_for(
                    process.communicate(), timeout=5,
                )
                partial_stdout = (remaining_stdout or b"").decode(errors="replace").strip()
                partial_stderr = (remaining_stderr or b"").decode(errors="replace").strip()
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass

            elapsed = time.monotonic() - t0
            logger.warning(
                f"⏱️  Command timed out after {elapsed:.1f}s (captured {len(partial_stdout)} chars): "
                f"{task.command[:80]}"
            )
            timeout_note = f"[TIMED OUT after {int(elapsed)}s — partial output below]\n"
            return CommandResult(
                task_id=task.task_id,
                command=task.command,
                rationale=task.rationale,
                stdout=timeout_note + partial_stdout if partial_stdout else "",
                stderr=partial_stderr or "Command timed out",
                exit_code=-1,
                duration_seconds=round(elapsed, 2),
                timed_out=True,
                timeout_limit=task.timeout,
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
            timeout_limit=task.timeout,
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
                timeout_limit=task.timeout,
            ))
        else:
            final.append(res)

    return final

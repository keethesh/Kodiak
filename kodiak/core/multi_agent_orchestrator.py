"""
Multi-Agent Orchestrator — async pipeline of Planner + Analyst + Worker pool.

Replaces the single ManagerAgent brain with three concurrent async tasks:
  1. Planner  (Flash, fast, methodology-driven) → emits WorkUnits
  2. Workers  (no LLM, N concurrent) → execute tools in Docker, write results
  3. Analyst  (Pro, deep thinking) → analyzes results, writes findings/directives

All three share state via SharedScanStore (DB-backed).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import shlex
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from kodiak.core.analyst import AnalystAgent
from kodiak.core.config import settings
from kodiak.core.event_publisher import RuntimeEventPublisher
from kodiak.core.kernel_result import KernelResult
from kodiak.core.planner import PlannerAgent
from kodiak.core.shared_store import SharedScanStore
from kodiak.core.worker import CommandTask, execute_command
from kodiak.database.engine import get_session
from kodiak.database.models import WorkUnit, WorkUnitStatus


_HEAVY_TOOLS = settings.HEAVY_TOOLS



def _tool_name_for_unit(unit: WorkUnit) -> str:
    command = (unit.command_template or "").strip()
    if command:
        segment = command.rsplit("|", 1)[-1].strip()
        try:
            parts = shlex.split(segment, posix=True)
        except ValueError:
            parts = segment.split()
        if parts:
            return parts[0].lower()
    return unit.technique.split("_", 1)[0].lower()


def _unit_primary_target(unit: WorkUnit) -> str:
    """Read the canonical scope from the single-scope target field."""
    return unit.target if unit.target else ""


# ---------------------------------------------------------------------------
# Worker loop (no LLM — just claims and executes)
# ---------------------------------------------------------------------------

async def _worker_loop(
    worker_id: str,
    store: SharedScanStore,
    semaphore: asyncio.Semaphore,
    heavy_semaphore: asyncio.Semaphore,
    event_manager: Optional[RuntimeEventPublisher] = None,
    idle_timeout: float = 30.0,
    scan_id_str: str = "",
    container_label: str = "",
) -> Dict[str, Any]:
    """
    A single worker loop:
      1. Claim a pending WorkUnit from the queue
      2. Execute its command in Docker
      3. Write stdout/stderr back to the WorkUnit
      4. Repeat until stopped or idle too long
    """
    stats = {"executed": 0, "failed": 0, "timed_out": 0}
    idle_start: Optional[float] = None

    while True:
        # Try to claim work
        unit: Optional[WorkUnit] = None
        async for session in get_session():
            unit = await store.claim_work_unit(session, worker_id)

        if unit is None:
            if idle_start is None:
                idle_start = time.monotonic()
            elif time.monotonic() - idle_start > idle_timeout:
                logger.debug(f"🔧 Worker {worker_id}: idle timeout, exiting")
                break
            await asyncio.sleep(2.0)
            continue

        idle_start = None

        # Execute the command
        command = unit.command_template or ""
        if not command:
            async for session in get_session():
                await store.complete_work_unit(
                    session, unit.id,
                    stderr="No command to execute",
                    exit_code=-1,
                    status=WorkUnitStatus.FAILED,
                )
            stats["failed"] += 1
            continue

        # Determine timeout from methodology rule or default
        timeout = 600
        try:
            from kodiak.core.methodology import get_rule_by_technique
            rule = get_rule_by_technique(unit.technique)
            if rule:
                timeout = rule.timeout
        except Exception:
            pass

        tool_name = _tool_name_for_unit(unit)
        primary_target = _unit_primary_target(unit)

        # Emit tool start event
        if event_manager:
            try:
                await event_manager.emit_tool_start(
                    scan_id=scan_id_str,
                    tool_name=tool_name,
                    agent_id=worker_id,
                    target=primary_target or command[:80],
                )
            except Exception:
                pass

        logger.info(f"🔧 Worker {worker_id}: executing {unit.technique} → {command[:80]}")

        task = CommandTask(
            command=command,
            rationale=unit.context or unit.technique,
            timeout=timeout,
            container_label=container_label or "",
        )

        async for session in get_session():
            await store.record_attempt(
                session,
                tool=tool_name,
                target=primary_target,
                status="started",
                reason=unit.context or unit.technique,
                properties={
                    "work_unit_id": str(unit.id),
                    "phase": unit.phase,
                    "worker_id": worker_id,
                    "command": command,
                },
            )

        heavy_ctx = heavy_semaphore if tool_name in _HEAVY_TOOLS else contextlib.nullcontext()
        async with heavy_ctx:
            async with semaphore:
                result = await execute_command(task, semaphore)
        stats["executed"] += 1
        if result.timed_out:
            stats["timed_out"] += 1

        # Write results back
        status = WorkUnitStatus.COMPLETED if result.exit_code == 0 else WorkUnitStatus.FAILED
        if result.timed_out:
            status = WorkUnitStatus.COMPLETED  # Partial output is still useful

        async for session in get_session():
            await store.complete_work_unit(
                session, unit.id,
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
                status=status,
            )
            await store.record_attempt(
                session,
                tool=tool_name,
                target=primary_target,
                status=("timeout" if result.timed_out else "success" if result.exit_code == 0 else "failed"),
                reason=unit.context or unit.technique,
                properties={
                    "work_unit_id": str(unit.id),
                    "phase": unit.phase,
                    "worker_id": worker_id,
                    "exit_code": result.exit_code,
                    "timed_out": result.timed_out,
                    "duration_seconds": result.duration_seconds,
                },
            )

        if event_manager:
            try:
                await event_manager.emit_tool_complete(
                    tool_name=tool_name,
                    result=result,
                    scan_id=scan_id_str,
                )
            except Exception:
                pass

    return stats


# ---------------------------------------------------------------------------
# Multi-Agent Orchestrator
# ---------------------------------------------------------------------------

class MultiAgentOrchestrator:
    """
    Manages the lifecycle of Planner + Analyst + Worker pool.

    Usage:
        orchestrator = MultiAgentOrchestrator(event_manager=em)
        result = await orchestrator.run(
            target="https://example.com",
            project_id=pid,
            scan_id=sid,
        )
    """

    def __init__(
        self,
        event_manager: RuntimeEventPublisher,
        num_workers: int = 4,
        worker_idle_timeout: float = 60.0,
        max_scan_duration: float = 3600.0,
    ):
        self.event_manager = event_manager
        self.num_workers = num_workers
        self.worker_idle_timeout = worker_idle_timeout
        self.max_scan_duration = max_scan_duration
        self._running = False
        self._container_label = "kodiak-scan"

    async def shutdown(self) -> None:
        """
        Gracefully shutdown the orchestrator and cleanup resources.
        
        This method:
        1. Cancels all running tasks
        2. Cleans up orphaned Docker containers
        3. Logs DB metrics
        4. Logs shutdown status
        """
        self._running = False
        logger.info("🛑 Initiating graceful shutdown...")
        
        await self._cleanup_containers()
        
        self._log_metrics()
        
        logger.info("✅ Graceful shutdown complete")

    def _log_metrics(self) -> None:
        """Log database operation metrics for monitoring."""
        try:
            from kodiak.core.shared_store import DBMetrics
            stats = DBMetrics.get_stats()
            if stats["errors"]:
                logger.warning(
                    f"📊 DB Metrics: {sum(stats['operations'].values())} ops, "
                    f"{sum(stats['errors'].values())} errors, "
                    f"error rate: {stats['error_rate']:.2%}"
                )
            DBMetrics.reset()
        except Exception:
            pass

    async def _cleanup_containers(self) -> int:
        """
        Remove orphaned Docker containers created by this scan.
        Returns the number of containers cleaned up.
        """
        try:
            import asyncio
            process = await asyncio.create_subprocess_exec(
                "docker", "ps", "-q", "--filter", f"label=kodiak.scan={self._container_label}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            container_ids = stdout.decode().strip().split("\n")
            container_ids = [cid for cid in container_ids if cid]
            
            if not container_ids:
                return 0
            
            logger.info(f"🧹 Cleaning up {len(container_ids)} orphaned containers")
            
            for container_id in container_ids:
                try:
                    await asyncio.create_subprocess_exec(
                        "docker", "rm", "-f", container_id,
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=asyncio.subprocess.DEVNULL,
                    )
                except Exception:
                    pass
            
            return len(container_ids)
        except Exception as e:
            logger.debug(f"Container cleanup skipped: {e}")
            return 0

    async def run(
        self,
        *,
        target: str,
        instructions: str = "",
        project_id: UUID,
        scan_id: UUID,
        tool_availability: Any = None,
    ) -> KernelResult:
        """
        Run the active multi-agent kernel and return a runtime-neutral result.
        """
        start = time.monotonic()
        scan_id_str = str(scan_id)
        self._running = True
        self._container_label = f"kodiak-scan-{scan_id_str[:8]}"

        from kodiak.database.engine import init_db
        await init_db()

        # 1. Create shared store
        store = SharedScanStore(project_id=project_id, scan_id=scan_id)

        # 2. Use the scan-runner preflight result when provided; otherwise
        # fall back to a direct availability check for programmatic callers.
        if tool_availability is None:
            from kodiak.core.tool_availability import check_tool_availability, get_default_tools_to_check
            tool_availability = await check_tool_availability(get_default_tools_to_check())

        # 3. Create agents with tool availability
        planner = PlannerAgent(
            store=store,
            target=target,
            instructions=instructions,
            event_manager=self.event_manager,
            tool_availability=tool_availability,
        )

        analyst = AnalystAgent(
            store=store,
            instructions=instructions,
            event_manager=self.event_manager,
        )

        # 4. Shared concurrency controls for all workers
        semaphore = asyncio.Semaphore(settings.global_tool_concurrency)
        heavy_semaphore = asyncio.Semaphore(max(1, settings.heavy_tool_parallel_limit))
        planner_done = asyncio.Event()

        async def _run_planner() -> Dict[str, Any]:
            try:
                return await planner.run(
                    cycle_interval=settings.planner_cycle_interval,
                    max_cycles=settings.planner_max_cycles,
                )
            finally:
                planner_done.set()

        # 5. Build async tasks
        planner_task = asyncio.create_task(
            _run_planner(),
            name="planner",
        )

        analyst_task = asyncio.create_task(
            analyst.run(
                poll_interval=settings.analyst_poll_interval,
                max_cycles=settings.analyst_max_cycles,
                planner_done_event=planner_done,
                settle_cycles=settings.analyst_settle_cycles,
                min_results_per_batch=settings.analyst_min_results_per_batch,
            ),
            name="analyst",
        )

        worker_tasks = [
            asyncio.create_task(
                _worker_loop(
                    worker_id=f"worker-{i}",
                    store=store,
                    semaphore=semaphore,
                    heavy_semaphore=heavy_semaphore,
                    event_manager=self.event_manager,
                    idle_timeout=self.worker_idle_timeout,
                    scan_id_str=scan_id_str,
                    container_label=self._container_label,
                ),
                name=f"worker-{i}",
            )
            for i in range(self.num_workers)
        ]

        logger.info(
            f"🚀 Multi-agent pipeline started: "
            f"1 planner (Flash) + 1 analyst (Pro) + {self.num_workers} workers"
        )

        # 6. Run until completion or timeout
        all_tasks = [planner_task, analyst_task] + worker_tasks

        status = "completed"
        task_errors: Dict[str, str] = {}
        try:
            gathered = await asyncio.wait_for(
                asyncio.gather(*all_tasks, return_exceptions=True),
                timeout=self.max_scan_duration,
            )
            for task, outcome in zip(all_tasks, gathered):
                if isinstance(outcome, Exception) and not isinstance(outcome, asyncio.CancelledError):
                    task_errors[task.get_name()] = repr(outcome)
            if task_errors:
                status = "failed"
                logger.error(
                    "Multi-agent pipeline task failures detected: "
                    + ", ".join(f"{name}={err}" for name, err in task_errors.items())
                )
        except asyncio.TimeoutError:
            status = "max_duration"
            logger.warning("⏱️ Multi-agent pipeline hit max_scan_duration; cancelling remaining tasks")
            for task in all_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*all_tasks, return_exceptions=True)
            await self.shutdown()

        except asyncio.CancelledError:
            logger.info("🛑 Multi-agent pipeline cancelled")
            status = "cancelled"
            for task in all_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*all_tasks, return_exceptions=True)
            await self.shutdown()

        elapsed = time.monotonic() - start

        # 7. Collect results
        planner_stats: Dict[str, Any] = {}
        if planner_task.done() and not planner_task.cancelled():
            try:
                planner_stats = planner_task.result()
            except Exception:
                pass

        analyst_result = None
        if analyst_task.done() and not analyst_task.cancelled():
            try:
                analyst_result = analyst_task.result()
            except Exception:
                pass

        worker_stats: List[Dict[str, Any]] = []
        for wt in worker_tasks:
            if wt.done() and not wt.cancelled():
                try:
                    worker_stats.append(wt.result())
                except Exception:
                    pass

        total_executed = sum(ws.get("executed", 0) for ws in worker_stats)
        total_failed = sum(ws.get("failed", 0) for ws in worker_stats)

        # 7. Count findings
        findings_count = 0
        async for session in get_session():
            findings = await store.get_findings(session, limit=1000)
            findings_count = len(findings)

        # 8. Build summary
        analyst_cycles = analyst._cycle_count

        summary = (
            f"Multi-agent scan {status} in {elapsed:.0f}s. "
            f"Planner: {planner_stats.get('cycles', 0)} cycles, "
            f"Workers: {total_executed} commands ({total_failed} failed), "
            f"Analyst: {analyst_cycles} cycles, "
            f"Findings: {findings_count}"
        )
        if task_errors:
            summary += f". Runtime task failures: {len(task_errors)}"

        logger.info(f"✅ {summary}")

        # Token accounting (Planner returns dict, Analyst returns AnalystResult)
        planner_input = planner_stats.get("input_tokens", 0)
        planner_output = planner_stats.get("output_tokens", 0)
        analyst_input = analyst_result.input_tokens if analyst_result else 0
        analyst_output = analyst_result.output_tokens if analyst_result else 0
        analyst_thinking = analyst_result.thinking_tokens if analyst_result else 0
        analyst_cached = analyst_result.cached_tokens if analyst_result else 0
        analyst_cost = analyst_result.total_cost if analyst_result else 0.0

        from kodiak.services.llm import calculate_cost
        planner_model = settings.get_planner_model()
        analyst_model = settings.get_analyst_model()
        
        # Estimate planner cost (fast model)
        planner_cost = calculate_cost(
            model=planner_model,
            input_tokens=planner_input,
            output_tokens=planner_output,
        )
        
        # Use actual cost from OpenRouter for analyst
        total_cost = planner_cost + analyst_cost

        return KernelResult(
            status=status,
            summary=summary,
            findings_count=findings_count,
            iterations=planner_stats.get("cycles", 0) + analyst_cycles,
            task_errors=task_errors,
            total_input_tokens=planner_input + analyst_input,
            total_output_tokens=planner_output + analyst_output,
            total_thinking_tokens=planner_stats.get("thinking_tokens", 0) + analyst_thinking,
            total_cached_tokens=planner_stats.get("cached_tokens", 0) + analyst_cached,
            total_cost_usd=total_cost,
        )

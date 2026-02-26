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
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.analyst import AnalystAgent
from kodiak.core.config import settings
from kodiak.core.manager import ManagerResult
from kodiak.core.planner import PlannerAgent
from kodiak.core.shared_store import SharedScanStore
from kodiak.core.worker import CommandResult, CommandTask, execute_command
from kodiak.database.engine import get_session
from kodiak.database.models import WorkUnit, WorkUnitStatus


# ---------------------------------------------------------------------------
# Worker loop (no LLM — just claims and executes)
# ---------------------------------------------------------------------------

async def _worker_loop(
    worker_id: str,
    store: SharedScanStore,
    semaphore: asyncio.Semaphore,
    event_manager: Optional[TUIEventManager] = None,
    idle_timeout: float = 30.0,
    scan_id_str: str = "",
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

        # Emit tool start event
        tool_name = unit.technique.split("_")[0]
        if event_manager:
            try:
                await event_manager.emit_tool_start(
                    scan_id=scan_id_str,
                    tool_name=tool_name,
                    agent_id=worker_id,
                    target=command[:80],
                )
            except Exception:
                pass

        logger.info(f"🔧 Worker {worker_id}: executing {unit.technique} → {command[:80]}")

        task = CommandTask(
            command=command,
            rationale=unit.context or unit.technique,
            timeout=timeout,
        )
        result: CommandResult = await execute_command(task, semaphore)
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

        # Emit tool completion event
        if event_manager:
            try:
                await event_manager.emit_tool_complete(
                    scan_id=scan_id_str,
                    tool_name=tool_name,
                    agent_id=worker_id,
                    target=command[:80],
                    result={
                        "exit_code": result.exit_code,
                        "duration": result.duration_seconds,
                        "timed_out": result.timed_out,
                        "stdout_len": len(result.stdout),
                    },
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
        event_manager: TUIEventManager,
        num_workers: int = 4,
        worker_idle_timeout: float = 60.0,
        max_scan_duration: float = 3600.0,
    ):
        self.event_manager = event_manager
        self.num_workers = num_workers
        self.worker_idle_timeout = worker_idle_timeout
        self.max_scan_duration = max_scan_duration

    async def run(
        self,
        *,
        target: str,
        instructions: str = "",
        project_id: UUID,
        scan_id: UUID,
    ) -> ManagerResult:
        """
        Run the full multi-agent pipeline. Returns ManagerResult for
        backward compatibility with ScanRunner.
        """
        start = time.monotonic()
        scan_id_str = str(scan_id)

        from kodiak.database.engine import init_db
        await init_db()

        # 1. Create shared store
        store = SharedScanStore(project_id=project_id, scan_id=scan_id)

        # 2. Create agents
        planner = PlannerAgent(
            store=store,
            target=target,
            event_manager=self.event_manager,
        )

        analyst = AnalystAgent(
            store=store,
            event_manager=self.event_manager,
        )

        # 3. Shared concurrency semaphore for all workers
        semaphore = asyncio.Semaphore(settings.global_tool_concurrency)

        # 4. Build async tasks
        planner_task = asyncio.create_task(
            planner.run(cycle_interval=8.0, max_cycles=200),
            name="planner",
        )

        analyst_task = asyncio.create_task(
            analyst.run(poll_interval=15.0, max_cycles=100),
            name="analyst",
        )

        worker_tasks = [
            asyncio.create_task(
                _worker_loop(
                    worker_id=f"worker-{i}",
                    store=store,
                    semaphore=semaphore,
                    event_manager=self.event_manager,
                    idle_timeout=self.worker_idle_timeout,
                    scan_id_str=scan_id_str,
                ),
                name=f"worker-{i}",
            )
            for i in range(self.num_workers)
        ]

        logger.info(
            f"🚀 Multi-agent pipeline started: "
            f"1 planner (Flash) + 1 analyst (Pro) + {self.num_workers} workers"
        )

        # 5. Run until completion or timeout
        all_tasks = [planner_task, analyst_task] + worker_tasks

        try:
            # Wait for the analyst to signal completion, or planner to exhaust,
            # or timeout. The analyst is the "brain" — it decides when done.
            done, pending = await asyncio.wait(
                [planner_task, analyst_task],
                timeout=self.max_scan_duration,
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Give workers time to finish current work
            if pending:
                logger.info("🔧 Waiting for agents to wind down...")
                for task in pending:
                    task.cancel()

            # Signal all workers to stop (they'll exit on next idle check)
            for wt in worker_tasks:
                if not wt.done():
                    wt.cancel()

            # Wait for everything to settle
            await asyncio.gather(*all_tasks, return_exceptions=True)

        except asyncio.CancelledError:
            logger.info("🛑 Multi-agent pipeline cancelled")
            for task in all_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*all_tasks, return_exceptions=True)

        elapsed = time.monotonic() - start

        # 6. Collect results
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
        status = "completed"
        if elapsed >= self.max_scan_duration:
            status = "max_duration"

        summary = (
            f"Multi-agent scan completed in {elapsed:.0f}s. "
            f"Planner: {planner_stats.get('cycles', 0)} cycles, "
            f"Workers: {total_executed} commands ({total_failed} failed), "
            f"Analyst: {analyst_cycles} cycles, "
            f"Findings: {findings_count}"
        )

        logger.info(f"✅ {summary}")

        # Token accounting (Planner returns dict, Analyst returns AnalystResult)
        planner_input = planner_stats.get("input_tokens", 0)
        planner_output = planner_stats.get("output_tokens", 0)
        analyst_input = analyst_result.input_tokens if analyst_result else 0
        analyst_output = analyst_result.output_tokens if analyst_result else 0
        analyst_thinking = analyst_result.thinking_tokens if analyst_result else 0

        from kodiak.services.llm import calculate_cost
        total_cost = calculate_cost(
            model="gemini/gemini-3-flash-preview",
            input_tokens=planner_input,
            output_tokens=planner_output,
        ) + calculate_cost(
            model="gemini/gemini-3.1-pro-preview",
            input_tokens=analyst_input,
            output_tokens=analyst_output,
            thinking_tokens=analyst_thinking,
        )

        return ManagerResult(
            status=status,
            summary=summary,
            findings_count=findings_count,
            iterations=planner_stats.get("cycles", 0) + analyst_cycles,
            total_input_tokens=planner_input + analyst_input,
            total_output_tokens=planner_output + analyst_output,
            total_thinking_tokens=analyst_thinking,
            total_cached_tokens=0,
            total_cost_usd=total_cost,
        )

"""
Scan Runner - Clean implementation of scan execution
"""

import asyncio
import math
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from kodiak.core.agent import KodiakAgent
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.config import settings
from kodiak.core.agent_scaling import resolve_agent_count
from kodiak.api.events import TUIEventManager
from kodiak.database.engine import get_session
from kodiak.database.models import Project, ScanJob, ScanStatus
from kodiak.database import crud


@dataclass
class ScanResult:
    """Result of a completed scan"""
    status: str  # "completed", "failed", "cancelled", "max_iterations"
    summary: str
    nodes_discovered: int
    findings_count: int
    duration_seconds: float
    iterations: int


class ScanRunner:
    """
    Executes a single security scan from start to finish.
    """
    
    def __init__(self, event_manager: TUIEventManager):
        self.event_manager = event_manager
        self._agents: List[KodiakAgent] = []
        self._agent_tasks: List[asyncio.Task] = []
        self._cancel_requested = False
        self._finding_event_count = 0
        self._finding_keys: set[str] = set()
        self._finding_counts_by_severity: Dict[str, int] = {}
    
    async def run(
        self,
        target: str,
        instructions: str = "",
        project_name: Optional[str] = None,
        max_iterations: int = 25,
        agent_count: int = 1,
        role_strategy: str = "role_hinted",
        force_agents: bool = False,
    ) -> ScanResult:
        """
        Execute a complete scan.
        """
        start_time = datetime.now(timezone.utc)
        
        # Default project name
        if not project_name:
            project_name = f"Scan_{target}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        self._cancel_requested = False
        self._agents = []
        self._agent_tasks = []
        self._finding_event_count = 0
        self._finding_keys = set()
        self._finding_counts_by_severity = {}

        agent_resolution = resolve_agent_count(
            requested=agent_count,
            max_agents=settings.max_concurrent_agents,
            force_agents=force_agents,
        )
        if agent_resolution.warning:
            logger.warning(agent_resolution.warning)

        async for session in get_session():
            try:
                # 1. Create project and scan in database
                project = await self._create_project(session, project_name)
                scan_job = await self._create_scan_job(
                    session, project.id, target, instructions
                )
                
                logger.info(f"🎯 Starting scan: {target}")
                scan_id_str = str(scan_job.id)

                async def _capture_scan_event(event: Any) -> None:
                    if event.type != "finding_discovered":
                        return
                    finding = (event.data or {}).get("finding", {})
                    key = self._finding_key(finding)
                    self._finding_event_count += 1
                    if key in self._finding_keys:
                        return
                    self._finding_keys.add(key)
                    severity = str(finding.get("severity", "info")).lower()
                    self._finding_counts_by_severity[severity] = self._finding_counts_by_severity.get(severity, 0) + 1

                self.event_manager.subscribe_scan(scan_id_str, _capture_scan_event)
                
                # Emit scan started event
                await self.event_manager.emit_scan_started(
                    scan_id=scan_id_str,
                    scan_name=project.name,
                    target=target
                )
                
                # 2. Setup Agents
                effective_agents = agent_resolution.effective
                per_agent_iterations = max(1, math.ceil(max_iterations / effective_agents))
                global_heavy_semaphore = asyncio.Semaphore(max(1, settings.heavy_tool_parallel_limit))
                per_tool_semaphores = {
                    "nmap": asyncio.Semaphore(1),
                    "sqlmap": asyncio.Semaphore(1),
                    "nuclei": asyncio.Semaphore(max(1, settings.heavy_tool_parallel_limit)),
                    "ffuf": asyncio.Semaphore(max(1, settings.heavy_tool_parallel_limit)),
                    "katana": asyncio.Semaphore(max(1, settings.heavy_tool_parallel_limit)),
                }
                logger.info(
                    f"Starting {effective_agents} agent(s) with {per_agent_iterations} max iterations each"
                )

                for index in range(effective_agents):
                    role = self._role_for_index(index, role_strategy)
                    tool_inventory = ToolInventory()
                    tool_inventory.initialize_tools()

                    agent = KodiakAgent(
                        agent_id=f"scanner-{scan_job.id}-{index + 1}",
                        tool_inventory=tool_inventory,
                        event_manager=self.event_manager,
                        session=session,
                        role=role,
                        project_id=project.id,
                        global_tool_semaphore=global_heavy_semaphore,
                        tool_semaphores=per_tool_semaphores,
                    )
                    await agent.register_with_hive_mind()
                    self._agents.append(agent)

                # 3. Run Agent Loops
                for index, agent in enumerate(self._agents):
                    goal = self._build_agent_goal(
                        base_instructions=instructions,
                        target=target,
                        role=agent.role,
                        index=index,
                        total=effective_agents,
                        role_strategy=role_strategy,
                    )
                    task = asyncio.create_task(
                        agent.run(
                            goal=goal,
                            target=target,
                            session=session,
                            project_id=project.id,
                            scan_id=scan_job.id,
                            max_iterations=per_agent_iterations,
                        ),
                        name=f"kodiak-agent-{scan_job.id}-{index + 1}",
                    )
                    self._agent_tasks.append(task)

                agent_results = await asyncio.gather(*self._agent_tasks, return_exceptions=True)
                result = self._aggregate_agent_results(
                    agent_results,
                    max_iterations=max_iterations,
                    deduped_finding_count=len(self._finding_keys),
                )
                
                # 4. Finalize
                final_status = (
                    ScanStatus.COMPLETED
                    if result.status == "completed"
                    else ScanStatus.FAILED
                )
                await crud.scan_job.update_status(session, scan_job.id, final_status)
                
                nodes = await crud.node.get_nodes_by_project(session, project.id)
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                scan_result = ScanResult(
                    status=result.status,
                    summary=result.summary,
                    nodes_discovered=len(nodes),
                    findings_count=result.findings_count,
                    duration_seconds=duration,
                    iterations=result.iterations
                )
                
                await self.event_manager.emit_scan_completed(
                    scan_id=scan_id_str,
                    scan_name=project.name,
                    status=final_status,
                    summary={
                        "agents_requested": agent_resolution.requested,
                        "agents_running": agent_resolution.effective,
                        "nodes_discovered": len(nodes),
                        "raw_findings": self._finding_event_count,
                        "deduped_findings": len(self._finding_keys),
                        "duplicate_findings_filtered": max(0, self._finding_event_count - len(self._finding_keys)),
                        "findings_by_severity": self._finding_counts_by_severity,
                        "findings_count": result.findings_count,
                        "duration": duration
                    }
                )
                
                return scan_result
                
            except Exception as e:
                logger.error(f"❌ Scan failed: {e}")
                if 'scan_job' in locals():
                    await crud.scan_job.update_status(session, scan_job.id, ScanStatus.FAILED)
                raise
            finally:
                for agent in self._agents:
                    try:
                        await agent.unregister_from_hive_mind()
                    except Exception as unregister_error:
                        logger.warning(f"Failed to unregister agent {agent.agent_id}: {unregister_error}")
                if 'scan_id_str' in locals():
                    try:
                        self.event_manager.unsubscribe_scan(scan_id_str, _capture_scan_event)
                    except Exception as unsubscribe_error:
                        logger.warning(f"Failed to unsubscribe finding capture handler: {unsubscribe_error}")
    
    async def _create_project(self, session: AsyncSession, name: str) -> Project:
        project = Project(name=name, description=f"Security scan project: {name}")
        return await crud.project.create(session, project)
    
    async def _create_scan_job(
        self,
        session: AsyncSession,
        project_id: UUID,
        target: str,
        instructions: str
    ) -> ScanJob:
        scan = ScanJob(
            project_id=project_id,
            name=f"Scan_{target}",
            status=ScanStatus.RUNNING,
            config={"target": target, "instructions": instructions}
        )
        return await crud.scan_job.create(session, scan)
    
    async def cancel(self):
        """Cancel the scan"""
        logger.info("🛑 Scan cancellation requested")
        self._cancel_requested = True
        for task in self._agent_tasks:
            if not task.done():
                task.cancel()
        if self._agent_tasks:
            await asyncio.gather(*self._agent_tasks, return_exceptions=True)

    def _role_for_index(self, index: int, role_strategy: str) -> str:
        if role_strategy != "role_hinted":
            return "generalist"
        roles = ["scout", "mapper", "attacker", "analyst", "reporter"]
        return roles[index % len(roles)]

    def _build_agent_goal(
        self,
        base_instructions: str,
        target: str,
        role: str,
        index: int,
        total: int,
        role_strategy: str,
    ) -> str:
        base_goal = base_instructions or f"Perform a security scan of {target}"
        if role_strategy != "role_hinted":
            return base_goal

        role_focus = {
            "scout": "prioritize broad discovery and service enumeration",
            "mapper": "prioritize endpoint mapping and technology fingerprinting",
            "attacker": "prioritize focused vulnerability validation on high-value targets",
            "analyst": "prioritize triage, evidence quality, and false-positive reduction",
            "reporter": "prioritize consolidation, impact statements, and concise findings",
        }.get(role, "prioritize useful work without duplicating peers")

        return (
            f"{base_goal}\n\n"
            f"You are agent {index + 1} of {total}.\n"
            f"Role: {role}. Focus: {role_focus}.\n"
            "Avoid repeating commands already attempted by peers unless you change strategy."
        )

    def _aggregate_agent_results(
        self,
        raw_results: List[Any],
        max_iterations: int,
        deduped_finding_count: int = 0,
    ) -> ScanResult:
        successful_results = []
        failures = 0
        cancelled = 0

        for item in raw_results:
            if isinstance(item, asyncio.CancelledError):
                cancelled += 1
                continue
            if isinstance(item, Exception):
                failures += 1
                logger.error(f"Agent task failed: {item}")
                continue
            successful_results.append(item)

        total_iterations = sum(r.iterations for r in successful_results)
        aggregated_findings = sum(r.findings_count for r in successful_results)
        findings_count = deduped_finding_count if deduped_finding_count > 0 else aggregated_findings
        summaries = [r.summary for r in successful_results if r.summary]

        if self._cancel_requested or (cancelled > 0 and not successful_results):
            status = "cancelled"
            summary = "Scan cancelled"
        elif any(r.status == "completed" for r in successful_results):
            status = "completed"
            summary = " | ".join(summaries[:3]) if summaries else "Scan completed"
        elif successful_results and all(r.status == "max_iterations" for r in successful_results):
            status = "max_iterations"
            summary = f"Reached iteration budget ({max_iterations}) across all agents"
        elif failures > 0 and not successful_results:
            status = "failed"
            summary = "All agents failed"
        else:
            status = "failed"
            summary = "Scan ended without completion"

        return ScanResult(
            status=status,
            summary=summary,
            nodes_discovered=0,
            findings_count=findings_count,
            duration_seconds=0,
            iterations=total_iterations,
        )

    def _finding_key(self, finding: Dict[str, Any]) -> str:
        title = str(finding.get("title", "")).strip().lower()
        severity = str(finding.get("severity", "info")).strip().lower()
        target = str(finding.get("target", "")).strip().lower()
        evidence = finding.get("evidence") or {}
        evidence_signature = ""
        if isinstance(evidence, dict):
            for k in ("template_id", "cve_id", "matched_at", "endpoint", "url"):
                value = evidence.get(k)
                if value:
                    evidence_signature = str(value).strip().lower()
                    break
        return "|".join([title, severity, target, evidence_signature])

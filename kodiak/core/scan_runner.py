"""
Scan Runner - Clean implementation of scan execution
"""

import asyncio
import math
import shlex
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
from kodiak.core.tool_scheduler import ToolScheduler
from kodiak.core.reporting import write_scan_report
from kodiak.api.events import TUIEventManager
from kodiak.database.engine import get_session
from kodiak.database.models import Project, ScanJob, ScanStatus
from kodiak.database import crud
from kodiak.services.executor import get_docker_executor


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
        self._finding_records: Dict[str, Dict[str, Any]] = {}
        self._tool_scheduler: Optional[ToolScheduler] = None
        self._docker_tool_map = {
            "nmap": "nmap",
            "nuclei": "nuclei",
            "subfinder": "subfinder",
            "httpx": "httpx",
            "katana": "katana",
            "ffuf": "ffuf",
            "whatweb": "whatweb",
            "sqlmap": "sqlmap",
            "commix": "commix",
            "searchsploit": "searchsploit",
        }
    
    async def run(
        self,
        target: str,
        instructions: str = "",
        project_name: Optional[str] = None,
        max_iterations: int = 25,
        agent_count: int = 1,
        role_strategy: str = "role_hinted",
        force_agents: bool = False,
        report_format: str = "json+md",
        report_path: Optional[str] = None,
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
        self._finding_records = {}

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
                    session, project.id, target, instructions, report_format, report_path
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
                    self._finding_records[key] = finding
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
                preflight_inventory = ToolInventory()
                preflight_inventory.initialize_tools()
                allowed_tools, missing_tools = await self._preflight_available_tools(preflight_inventory)
                if missing_tools:
                    logger.warning(
                        "Tool preflight disabled unavailable toolbox tools for this scan: "
                        + ", ".join(sorted(missing_tools))
                    )
                logger.info(
                    f"Tool preflight complete: {len(allowed_tools)} enabled, {len(missing_tools)} disabled"
                )

                if settings.tool_scheduler == "queue":
                    self._tool_scheduler = ToolScheduler(queue_limit=settings.tool_queue_limit)
                    self._tool_scheduler.register_tool("nmap", concurrency=1)
                    self._tool_scheduler.register_tool("sqlmap", concurrency=1)
                    self._tool_scheduler.register_tool(
                        "nuclei", concurrency=max(1, settings.heavy_tool_parallel_limit)
                    )
                    self._tool_scheduler.register_tool(
                        "ffuf", concurrency=max(1, settings.heavy_tool_parallel_limit)
                    )
                    self._tool_scheduler.register_tool(
                        "katana", concurrency=max(1, settings.heavy_tool_parallel_limit)
                    )
                    await self._tool_scheduler.start()

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
                        tool_scheduler=self._tool_scheduler,
                        allowed_tools=allowed_tools,
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
                
                attempts = await crud.attempt.get_attempts_by_scan(session, scan_job.id, limit=400)
                report_data = {
                    "scan_id": scan_id_str,
                    "scan_name": project.name,
                    "project_id": str(project.id),
                    "target": target,
                    "status": result.status,
                    "summary": {
                        "agents_requested": agent_resolution.requested,
                        "agents_running": agent_resolution.effective,
                        "nodes_discovered": len(nodes),
                        "raw_findings": self._finding_event_count,
                        "deduped_findings": len(self._finding_keys),
                        "duplicate_findings_filtered": max(0, self._finding_event_count - len(self._finding_keys)),
                        "findings_by_severity": self._finding_counts_by_severity,
                        "findings_count": result.findings_count,
                        "duration_seconds": duration,
                        "iterations": result.iterations,
                    },
                    "findings": list(self._finding_records.values()),
                    "attempts": [
                        {
                            "tool": a.tool,
                            "target": a.target,
                            "status": a.status,
                            "reason": a.reason,
                            "agent_id": (a.properties or {}).get("agent_id"),
                            "created_at": a.created_at,
                        }
                        for a in attempts
                    ],
                }
                report_paths: Dict[str, str] = {}
                try:
                    report_paths = write_scan_report(
                        report_data=report_data,
                        report_dir=report_path or settings.report_output_path,
                        report_format=report_format,
                    )
                except Exception as report_error:
                    logger.warning(f"Failed to write report artifact(s): {report_error}")
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
                        "duration": duration,
                        "report_paths": report_paths,
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
                if self._tool_scheduler is not None:
                    try:
                        await self._tool_scheduler.stop()
                    except Exception as scheduler_error:
                        logger.warning(f"Failed to stop tool scheduler cleanly: {scheduler_error}")
                    self._tool_scheduler = None
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
        instructions: str,
        report_format: str,
        report_path: Optional[str],
    ) -> ScanJob:
        scan = ScanJob(
            project_id=project_id,
            name=f"Scan_{target}",
            status=ScanStatus.RUNNING,
            config={
                "target": target,
                "instructions": instructions,
                "report_format": report_format,
                "report_path": report_path,
            }
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

    async def _preflight_available_tools(self, inventory: ToolInventory) -> tuple[List[str], List[str]]:
        """
        Probe Docker toolbox capabilities once per scan and gate unavailable
        Docker-backed tools from agent tool lists.
        """
        registered_tools = list(inventory.list_tools().keys())
        probe_tools = [tool for tool in registered_tools if tool in self._docker_tool_map]
        if not probe_tools:
            return registered_tools, []

        try:
            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image=settings.toolbox_image,
                fallback_entrypoint="",
            )

            probe_pairs = [f"{tool}:{self._docker_tool_map[tool]}" for tool in probe_tools]
            script_parts = [
                f"for pair in {' '.join(shlex.quote(pair) for pair in probe_pairs)}; do",
                "  tool=${pair%%:*}",
                "  bin=${pair##*:}",
                "  if command -v \"$bin\" >/dev/null 2>&1; then",
                "    echo \"$tool=1\"",
                "  else",
                "    echo \"$tool=0\"",
                "  fi",
                "done",
            ]
            command = ["/bin/bash", "-lc", " ".join(script_parts)]
            result = await executor.run_command(command)
            if result.exit_code != 0:
                logger.warning(
                    "Tool preflight probe failed (non-zero exit). Keeping all tools enabled. "
                    f"stderr={result.stderr}"
                )
                return registered_tools, []

            status_map: Dict[str, bool] = {}
            for line in (result.stdout or "").splitlines():
                cleaned = line.strip()
                if "=" not in cleaned:
                    continue
                name, value = cleaned.split("=", 1)
                name = name.strip()
                if name in self._docker_tool_map:
                    status_map[name] = value.strip() == "1"

            unknown = [name for name in probe_tools if name not in status_map]
            if unknown:
                logger.warning(
                    "Tool preflight received incomplete probe output; keeping these tools enabled: "
                    + ", ".join(sorted(unknown))
                )

            missing = sorted([name for name in probe_tools if status_map.get(name) is False])
            if not missing:
                return registered_tools, []

            allowed = [name for name in registered_tools if name not in set(missing)]
            return allowed, missing
        except Exception as e:
            logger.warning(f"Tool preflight probe failed unexpectedly. Keeping all tools enabled: {e}")
            return registered_tools, []

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

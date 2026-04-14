"""Scan Runner - active scan-kernel execution wrapper."""

import asyncio
import shlex
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from kodiak.core.kernel_result import KernelResult
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.config import settings
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
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost_usd: float = 0.0


class ScanRunner:
    """
    Executes a single security scan from start to finish.

    Uses the active multi-agent kernel:
    planner + analyst + worker pool.
    """
    
    def __init__(self, event_manager: TUIEventManager):
        self.event_manager = event_manager
        self._cancel_requested = False
        self._manager_task: Optional[asyncio.Task] = None
        self._finding_event_count = 0
        self._finding_keys: set[str] = set()
        self._finding_counts_by_severity: Dict[str, int] = {}
        self._finding_records: Dict[str, Dict[str, Any]] = {}
        # HARDCODED: sourced from registry.py — single source of truth for all tool binaries
        from kodiak.core.tools.registry import get_docker_tool_map as _get_docker_tool_map
        self._docker_tool_map = _get_docker_tool_map()

    
    async def run(
        self,
        target: str,
        instructions: str = "",
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
        scan_id: Optional[str] = None,
        scan_name: Optional[str] = None,
        max_iterations: int = 30,
        agent_count: int = 1,
        worker_count: Optional[int] = None,
        role_strategy: str = "role_hinted",
        report_format: str = "json+md",
        report_path: Optional[str] = None,
        event_scheduler: Optional[bool] = None,
    ) -> ScanResult:
        """
        Execute a complete scan using the active multi-agent kernel.

        ``agent_count``, ``role_strategy``, and ``event_scheduler`` are accepted
        for compatibility but ignored by the active runtime.
        """
        start_time = datetime.now(timezone.utc)
        
        if not project_name:
            project_name = f"Scan_{target}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        self._cancel_requested = False
        self._manager_task = None
        self._finding_event_count = 0
        self._finding_keys = set()
        self._finding_counts_by_severity = {}
        self._finding_records = {}

        async for session in get_session():
            try:
                # 1. Get or create project (reuse existing for prior knowledge)
                project = await self._get_or_create_project(session, project_name, project_id)
                scan_job = await self._prepare_scan_job(
                    session=session,
                    project_id=project.id,
                    target=target,
                    instructions=instructions,
                    report_format=report_format,
                    report_path=report_path,
                    scan_id=scan_id,
                    scan_name=scan_name,
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
                
                await self.event_manager.emit_scan_started(
                    scan_id=scan_id_str,
                    scan_name=project.name,
                    target=target
                )
                
                # 2. Preflight Docker toolbox
                tool_inventory = ToolInventory()
                tool_inventory.initialize_tools()
                allowed_tools, missing_tools = await self._preflight_available_tools(tool_inventory)
                if missing_tools:
                    logger.warning(
                        "Tool preflight disabled unavailable toolbox tools: "
                        + ", ".join(sorted(missing_tools))
                    )
                logger.info(
                    f"Tool preflight: {len(allowed_tools)} enabled, {len(missing_tools)} disabled"
                )

                dns_warning = await self._preflight_dns_check()
                if dns_warning:
                    instructions = f"{instructions}\n\n[PREFLIGHT WARNING] {dns_warning}" if instructions else f"[PREFLIGHT WARNING] {dns_warning}"

                # 3. Run the active multi-agent kernel.
                from kodiak.core.multi_agent_orchestrator import MultiAgentOrchestrator

                if event_scheduler is not None:
                    logger.warning("event_scheduler is deprecated and ignored by the active runtime")
                if role_strategy != "role_hinted":
                    logger.warning("role_strategy is deprecated and ignored by the active runtime")
                if agent_count != 1:
                    logger.warning("agent_count is deprecated; use worker_count/--workers instead")

                effective_workers = max(1, int(worker_count or settings.multi_agent_workers))
                orchestrator = MultiAgentOrchestrator(
                    event_manager=self.event_manager,
                    num_workers=effective_workers,
                    max_scan_duration=float(settings.multi_agent_max_duration),
                )
                logger.info(f"Starting Multi-Agent Pipeline with {effective_workers} workers")
                kernel_result = await orchestrator.run(
                    target=target,
                    instructions=instructions,
                    project_id=project.id,
                    scan_id=scan_job.id,
                )
                
                # 4. Finalize
                final_status = (
                    ScanStatus.COMPLETED
                    if kernel_result.status == "completed"
                    else ScanStatus.FAILED
                )
                await crud.scan_job.update_status(session, scan_job.id, final_status)
                
                nodes = await crud.node.get_nodes_by_project(session, project.id)
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                scan_result = ScanResult(
                    status=kernel_result.status,
                    summary=self._build_scan_summary(kernel_result),
                    nodes_discovered=len(nodes),
                    findings_count=kernel_result.findings_count,
                    duration_seconds=duration,
                    iterations=kernel_result.iterations,
                    total_input_tokens=kernel_result.total_input_tokens,
                    total_output_tokens=kernel_result.total_output_tokens,
                    total_thinking_tokens=kernel_result.total_thinking_tokens,
                    total_cached_tokens=kernel_result.total_cached_tokens,
                    total_cost_usd=kernel_result.total_cost_usd,
                )
                
                attempts = await crud.attempt.get_attempts_by_scan(session, scan_job.id, limit=400)
                report_data = {
                    "scan_id": scan_id_str,
                    "scan_name": project.name,
                    "project_id": str(project.id),
                    "target": target,
                    "status": kernel_result.status,
                    "summary": {
                        "nodes_discovered": len(nodes),
                        "raw_findings": self._finding_event_count,
                        "deduped_findings": len(self._finding_keys),
                        "findings_by_severity": self._finding_counts_by_severity,
                        "findings_count": kernel_result.findings_count,
                        "duration_seconds": duration,
                        "iterations": kernel_result.iterations,
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
                        "nodes_discovered": len(nodes),
                        "raw_findings": self._finding_event_count,
                        "deduped_findings": len(self._finding_keys),
                        "findings_by_severity": self._finding_counts_by_severity,
                        "findings_count": manager_result.findings_count,
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
                if 'scan_id_str' in locals():
                    try:
                        self.event_manager.unsubscribe_scan(scan_id_str, _capture_scan_event)
                    except Exception as unsubscribe_error:
                        logger.warning(f"Failed to unsubscribe finding capture: {unsubscribe_error}")
    
    async def _get_or_create_project(
        self,
        session: AsyncSession,
        name: str,
        project_id: Optional[str] = None,
    ) -> Project:
        """Return an existing project by id or name, or create a new one."""
        if project_id:
            existing = await crud.project.get(session, UUID(str(project_id)))
            if not existing:
                raise ValueError(f"Unknown project_id: {project_id}")
            return existing
        existing = await crud.project.get_by_name(session, name)
        if existing:
            logger.info(f"♻️  Reusing project '{name}' ({existing.id})")
            return existing
        project = Project(name=name, description=f"Security scan project: {name}")
        return await crud.project.create(session, project)

    async def _prepare_scan_job(
        self,
        session: AsyncSession,
        project_id: UUID,
        target: str,
        instructions: str,
        report_format: str,
        report_path: Optional[str],
        scan_id: Optional[str] = None,
        scan_name: Optional[str] = None,
    ) -> ScanJob:
        config = {
            "target": target,
            "instructions": instructions,
            "report_format": report_format,
            "report_path": report_path,
        }
        if scan_id:
            existing = await crud.scan_job.get(session, UUID(str(scan_id)))
            if not existing:
                raise ValueError(f"Unknown scan_id: {scan_id}")
            existing.project_id = project_id
            existing.name = scan_name or existing.name
            existing.status = ScanStatus.RUNNING
            existing.updated_at = datetime.now(timezone.utc)
            existing.config = {**(existing.config or {}), **config}
            session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return existing

        scan = ScanJob(
            project_id=project_id,
            name=scan_name or f"Scan_{target}",
            status=ScanStatus.RUNNING,
            config=config,
        )
        return await crud.scan_job.create(session, scan)

    async def cancel(self):
        """Cancel the scan"""
        logger.info("🛑 Scan cancellation requested")
        self._cancel_requested = True
        if self._manager_task and not self._manager_task.done():
            self._manager_task.cancel()
            await asyncio.gather(self._manager_task, return_exceptions=True)

    async def _preflight_dns_check(self) -> str | None:
        """
        Verify that the Docker sandbox can resolve DNS.
        Returns a warning string if DNS is unavailable, else None.
        """
        try:
            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image=settings.toolbox_image,
                fallback_entrypoint="",
            )
            result = await executor.run_command(
                ["/bin/bash", "-c", "getent hosts google.com >/dev/null 2>&1 && echo ok || echo fail"]
            )
            if result.stdout.strip() != "ok":
                warning = (
                    "Sandbox DNS resolution (UDP/53) appears to be BLOCKED. "
                    "Direct hostname lookups will fail. Use numeric IPs where possible, "
                    "or use DNS-over-HTTPS (e.g. curl --doh-url https://1.1.1.1/dns-query). "
                    "Tool flags: nmap -n (skip DNS), nuclei --system-resolvers (or set --resolver), "
                    "ffuf add -H 'Host:' header manually."
                )
                logger.warning(f"DNS preflight failed: {warning}")
                return warning
        except Exception as exc:
            logger.debug(f"DNS preflight check skipped: {exc}")
        return None

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
            probe_wordlist = " ".join(shlex.quote(pair) for pair in probe_pairs)
            script = (
                f"for pair in {probe_wordlist}; do\n"
                "  tool=${pair%%:*}\n"
                "  bin=${pair##*:}\n"
                "  if command -v \"$bin\" >/dev/null 2>&1; then\n"
                "    echo \"$tool=1\"\n"
                "  else\n"
                "    echo \"$tool=0\"\n"
                "  fi\n"
                "done"
            )
            command = ["/bin/bash", "-lc", script]
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

    def _build_scan_summary(self, kernel_result: KernelResult) -> str:
        return kernel_result.summary

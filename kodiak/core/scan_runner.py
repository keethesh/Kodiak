"""
Scan Runner - Clean implementation of scan execution
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from uuid import UUID
from dataclasses import dataclass

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from kodiak.core.agent import KodiakAgent
from kodiak.core.tools.inventory import ToolInventory
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
        self._agent: Optional[KodiakAgent] = None
    
    async def run(
        self,
        target: str,
        instructions: str = "",
        project_name: Optional[str] = None,
        max_iterations: int = 25
    ) -> ScanResult:
        """
        Execute a complete scan.
        """
        start_time = datetime.now(timezone.utc)
        
        # Default project name
        if not project_name:
            project_name = f"Scan_{target}_{start_time.strftime('%Y%m%d_%H%M%S')}"
        
        async for session in get_session():
            try:
                # 1. Create project and scan in database
                project = await self._create_project(session, project_name)
                scan_job = await self._create_scan_job(
                    session, project.id, target, instructions
                )
                
                logger.info(f"🎯 Starting scan: {target}")
                
                # Emit scan started event
                await self.event_manager.emit_scan_started(
                    scan_id=str(scan_job.id),
                    scan_name=project.name,
                    target=target
                )
                
                # 2. Setup Agent
                tool_inventory = ToolInventory()
                tool_inventory.initialize_tools()
                
                self._agent = KodiakAgent(
                    agent_id=f"scanner-{scan_job.id}",
                    tool_inventory=tool_inventory,
                    event_manager=self.event_manager,
                    session=session,
                    role="scout",
                    project_id=project.id
                )
                
                await self._agent.register_with_hive_mind()
                
                # 3. Run Agent Loop
                result = await self._agent.run(
                    goal=instructions or f"Perform a security scan of {target}",
                    target=target,
                    session=session,
                    project_id=project.id,
                    scan_id=scan_job.id,
                    max_iterations=max_iterations
                )
                
                # 4. Finalize
                final_status = ScanStatus.COMPLETED if result.status == "completed" else ScanStatus.FAILED
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
                    scan_id=str(scan_job.id),
                    scan_name=project.name,
                    status=final_status,
                    summary={
                        "nodes_discovered": len(nodes),
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

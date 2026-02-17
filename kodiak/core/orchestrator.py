"""
Orchestrator - Backward-compatible wrapper around ScanRunner

Legacy orchestrator that used a task-polling pattern is now replaced
by a streamlined ScanRunner execution model.
"""

from typing import Dict, Optional, List
from uuid import UUID
from loguru import logger

from kodiak.core.scan_runner import ScanRunner
from kodiak.api.events import TUIEventManager
from kodiak.core.tools.inventory import ToolInventory


class Orchestrator:
    """
    Backward-compatible wrapper around ScanRunner for the TUI.
    """
    
    def __init__(self, tool_inventory=None):
        # We now use the event_manager singleton indirectly or specifically
        self.event_manager = TUIEventManager()
        self._runner: Optional[ScanRunner] = None
        self._running = False
        
        # Keep inventory for compatibility if needed
        self.tool_inventory = tool_inventory or ToolInventory()
        logger.info("Orchestrator (wrapper) initialized")

    async def start(self):
        """No-op for backward compatibility (scheduler loop is gone)"""
        self._running = True
        logger.info("Orchestrator wrapper started (legacy scheduler disabled)")

    async def stop(self):
        """Stop the orchestrator and clean up runner"""
        self._running = False
        if self._runner:
            await self._runner.cancel()
        logger.info("Orchestrator stopped")

    async def start_scan(self, scan_id: UUID):
        """
        Start a scan using ScanRunner.
        """
        from kodiak.database.engine import get_session
        from kodiak.database.crud import scan_job as crud_scan
        
        if self._runner:
            logger.warning(f"Scan runner already active. Only one scan at a time supported in this version.")
            return

        async for session in get_session():
            scan = await crud_scan.get(session, scan_id)
            if not scan:
                logger.error(f"Scan {scan_id} not found")
                return
            
            target = scan.config.get("target")
            instructions = scan.config.get("instructions", "")
            
            logger.info(f"Starting scan {scan_id} for target {target} via ScanRunner wrapper")
            
            self._runner = ScanRunner(self.event_manager)
            try:
                # We run this in the background if we want the call to return immediately,
                # but legacy start_scan was expected to just 'initiate'.
                # However, the TUI usually expects to watch events.
                asyncio.create_task(self._runner.run(
                    target=target,
                    instructions=instructions,
                    project_name=scan.name
                ))
            except Exception as e:
                logger.error(f"Failed to launch ScanRunner: {e}")
                self._runner = None

    async def stop_scan(self, scan_id: UUID):
        """Stop a specific scan"""
        if self._runner:
            await self._runner.cancel()
            self._runner = None
            return 1
        return 0

    def get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        return list(self.tool_inventory.list_tools().keys())


# Singleton instance
orchestrator = Orchestrator()

import asyncio
from typing import Dict, Optional
from uuid import UUID

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.database import get_session
from kodiak.database.crud import scan_job as crud_scan, project as crud_project
from kodiak.database.models import ScanJob, ScanStatus

class Orchestrator:
    """
    Manages the lifecycle of scans and the state machine.
    """
    
    def __init__(self):
        self._active_scans: Dict[UUID, asyncio.Task] = {}

    async def start_scan(self, scan_id: UUID):
        """
        Start or Resume a scan.
        """
        if scan_id in self._active_scans:
            logger.warning(f"Scan {scan_id} is already active.")
            return

        async for session in get_session():
            scan = await crud_scan.get(session, scan_id)
            if not scan:
                logger.error(f"Scan {scan_id} not found.")
                return
            
            # Update status to RUNNING
            await crud_scan.update_status(session, scan_id, ScanStatus.RUNNING)
            
            # Start the background loop
            task = asyncio.create_task(self._scan_loop(scan_id))
            self._active_scans[scan_id] = task
            logger.info(f"Started scan loop for {scan_id}")
            break # Only need one session from generator

    async def _scan_loop(self, scan_id: UUID):
        """
        The main state machine loop for a scan.
        """
        try:
            while True:
                # 1. Load fresh state from DB
                async for session in get_session():
                    scan = await crud_scan.get(session, scan_id)
                    if not scan or scan.status != ScanStatus.RUNNING:
                        logger.info(f"Scan {scan_id} stopped or paused. Exiting loop.")
                        return

                    # 2. Determine Next Step (The "Graph" Logic)
                    # Simple Logic:
                    # A. Check for Targets (Roots)
                    # B. If Root exists and not scanned -> Run Nmap
                    
                    # Check for any assets
                    from kodiak.database.models import Asset
                    from kodiak.core.agent import KodiakAgent
                    
                    # Define a transient agent for this loop iteration
                    # In future, we might persist agent instances
                    agent = KodiakAgent(agent_id=f"worker-{scan_id}")

                    # A. Check for Root Asset (Target)
                    # We assume the config has the target, and we should create the asset if missing
                    target = scan.config.get("target")
                    if target:
                        # Check if asset exists
                        # TODO: proper CRUD for this check
                        # For now, simplistic logic
                        pass

                    # B. Demo Logic: Just run Nmap on the target if it exists in config
                    if target:
                        logger.info(f"Orchestrator: Dispatching Nmap on {target}")
                        result = await agent.act("nmap", {
                            "target": target, 
                            "ports": "80,443", 
                            "fast_mode": True,
                            "version_detect": True
                        })
                        logger.info(f"Scan Result: {result.get('success')}")
                        
                        # Mark as completed to stop infinite loop for this demo
                        await crud_scan.update_status(session, scan_id, ScanStatus.COMPLETED)
                        return
                    
                    await asyncio.sleep(5) # Throttle loop

        except asyncio.CancelledError:
            logger.info(f"Scan {scan_id} cancelled.")
        except Exception as e:
            logger.exception(f"Error in scan loop {scan_id}: {e}")
            # Update DB to failed
            async for session in get_session():
                await crud_scan.update_status(session, scan_id, ScanStatus.FAILED)
                break
    
    async def stop_scan(self, scan_id: UUID):
        if scan_id in self._active_scans:
            self._active_scans[scan_id].cancel()
            del self._active_scans[scan_id]
            
        async for session in get_session():
            await crud_scan.update_status(session, scan_id, ScanStatus.PAUSED)
            break
        logger.info(f"Stopped scan {scan_id}")

orchestrator = Orchestrator()

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

                    if target:
                        logger.info(f"Orchestrator: Starting Phased Scan on {target}")
                        
                        # --- PHASE 1: RECONNAISSANCE ---
                        logger.info(">>> PHASE 1: RECONNAISSANCE <<<")
                        history_recon = []
                        history_recon.append({
                            "role": "user", 
                            "content": f"Begin RECON phase for {target}. Find subdomains and live hosts. Do NOT run active scans yet."
                        })
                        
                        recon_tools = ["subfinder_enumerate", "httpx_probe", "terminal_execute"]
                        recon_prompt = (
                            "You are KODIAK (Phase: RECON). Focus ONLY on discovery. "
                            "1. Use subfinder to find subdomains. "
                            "2. Use httpx to check which ones are alive. "
                            "3. Stop when you have a list of live targets."
                        )
                        
                        # Run Recon Loop (Short)
                        for step in range(8):
                            try:
                                response = await agent.think(history_recon, allowed_tools=recon_tools, system_prompt=recon_prompt)
                                
                                # Process Response
                                msg_dict = response.dict() if hasattr(response, 'dict') else dict(response)
                                history_recon.append(msg_dict)
                                
                                if response.tool_calls:
                                    for tool_call in response.tool_calls:
                                        fn_name = tool_call.function.name
                                        fn_args = {
                                            **json.loads(tool_call.function.arguments),
                                            # We assume orchestrator injects session implicitly via act() but JSON args are from LLM
                                        } 
                                        import json # ensure import
                                        
                                        logger.info(f"[Recon] Executing: {fn_name}")
                                        result = await agent.act(fn_name, fn_args, session=session, project_id=scan.project_id)
                                        
                                        history_recon.append({
                                            "role": "tool",
                                            "tool_call_id": tool_call.id,
                                            "content": json.dumps(result)
                                        })
                                else:
                                    logger.info(f"[Recon] Agent: {response.content}")
                                    if "completed" in str(response.content).lower():
                                        break
                            except Exception as e:
                                logger.error(f"Recon Error: {e}")
                                break
                        
                        # --- PHASE 2: ACTIVE SCANNING ---
                        logger.info(">>> PHASE 2: ACTIVE SCANNING <<<")
                        
                        # In a real system, we'd query the DB for the assets found in Phase 1
                        # For this MVP, we rely on the agent's own memory/history or we explicitly query DB.
                        # Let's query the DB to give the agent a "Summary of Targets"
                        
                        # Fetch confirmed assets (simplification)
                        # assets = await crud_asset.get_by_project(session, scan.project_id) 
                        # We'll just prompt it to scan what it found or general target scope if DB query is complex here.
                        
                        history_exploit = []
                        history_exploit.append({
                            "role": "user", 
                            "content": f"Begin EXPLOIT phase for {target}. Scan the live hosts identified in Phase 1 for vulnerabilities using Nmap and Nuclei."
                        })
                        
                        exploit_tools = ["nmap", "nuclei_scan", "terminal_execute"]
                        exploit_prompt = (
                            "You are KODIAK (Phase: EXPLOIT). Your goal is to find vulnerabilities. "
                            "1. Run Nmap on identified live hosts. "
                            "2. Run Nuclei on web endpoints. "
                            "3. Report critical findings."
                        )
                        
                        for step in range(10):
                             try:
                                response = await agent.think(history_exploit, allowed_tools=exploit_tools, system_prompt=exploit_prompt)
                                
                                msg_dict = response.dict() if hasattr(response, 'dict') else dict(response)
                                history_exploit.append(msg_dict)
                                
                                if response.tool_calls:
                                    for tool_call in response.tool_calls:
                                        fn_name = tool_call.function.name
                                        fn_args = json.loads(tool_call.function.arguments)
                                        
                                        logger.info(f"[Exploit] Executing: {fn_name}")
                                        result = await agent.act(fn_name, fn_args, session=session, project_id=scan.project_id)
                                        
                                        history_exploit.append({
                                            "role": "tool",
                                            "tool_call_id": tool_call.id,
                                            "content": json.dumps(result)
                                        })
                                else:
                                    logger.info(f"[Exploit] Agent: {response.content}")
                                    if "completed" in str(response.content).lower():
                                        break
                             except Exception as e:
                                logger.error(f"Exploit Error: {e}")
                                break

                        # Mark as completed
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

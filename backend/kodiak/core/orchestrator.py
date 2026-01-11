import asyncio
from typing import Dict, Optional
from uuid import UUID
import json

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
            
            # Start the background tasks
            # We treat these as "Subagents" running in parallel
            manager_task = asyncio.create_task(self._manager_worker(scan_id))
            discovery_task = asyncio.create_task(self._discovery_worker(scan_id))
            exploit_task = asyncio.create_task(self._exploit_worker(scan_id))
            
            self._active_scans[scan_id] = [manager_task, discovery_task, exploit_task]
            logger.info(f"Started Subagent Swarm (Manager + Workers) for {scan_id}")
            break # Only need one session from generator

    async def _manager_worker(self, scan_id: UUID):
        """
        The Boss.
        Decides the HIGH LEVEL STRATEGY.
        Can stop/start workers (logically) or change their instructions.
        """
        from kodiak.core.agent import KodiakAgent
        logger.info(f"Manager Agent started for {scan_id}")
        
        agent = KodiakAgent(agent_id=f"manager-{scan_id}")
        
        try:
             async for session in get_session():
                scan = await crud_scan.get(session, scan_id)
                target = scan.config.get("target") if scan else None
                if not target: return
                
                # The Manager sees the BIG PICTURE
                history = [{"role": "user", "content": f"You are the Mission Manager for {target}. Orchestrate the Scout and Attacker to complete the pentest."}]
                
                # Main Loop
                while True:
                    # 1. Refresh Context (What have we found?)
                    # Simplification: Manager just ensures workers are running with correct instructions for now
                    # Future: Query DB stats
                    
                    tools = ["manage_mission"]
                    user_directives = scan.config.get("instructions", "")
                    
                    system_prompt = (
                        "You are KODIAK MANAGER. You control the swarm."
                        "You have two workers: 'scout' (Discovery) and 'attacker' (Exploitation)."
                        "Use 'manage_mission' to set their instructions based on the User's Goal."
                        f"\n\nUSER GOAL: {user_directives}"
                    )
                    
                    response = await agent.think(history, allowed_tools=tools, system_prompt=system_prompt)
                    
                    if response.tool_calls:
                         for tool_call in response.tool_calls:
                            fn_name = tool_call.function.name
                            fn_args = json.loads(tool_call.function.arguments)
                            
                            logger.info(f"[Manager] Command: {fn_name} -> {fn_args}")
                            
                            # EXECUTE: Update Config in DB
                            if fn_name == "manage_mission":
                                role = fn_args.get("role")
                                action = fn_args.get("action")
                                new_instr = fn_args.get("instructions")
                                
                                # Update Scan Config
                                # We need to be careful with concurrent DB updates here?
                                # SQLModel/SQLAlchemy handle simple updates well usually
                                
                                # Re-fetch to be safe
                                s = await crud_scan.get(session, scan_id)
                                current_config = dict(s.config) # copy
                                directives = current_config.get("directives", {})
                                
                                directives[role] = {"action": action, "instructions": new_instr}
                                current_config["directives"] = directives
                                
                                s.config = current_config
                                session.add(s)
                                await session.commit()
                                await session.refresh(s)
                                
                                history.append({
                                    "role": "tool", 
                                    "tool_call_id": tool_call.id,
                                    "content": "Directives updated in database."
                                })
                    
                    await asyncio.sleep(10) # Manager thinks every 10s
                    
        except Exception as e:
            logger.exception(f"Manager Worker failed: {e}")

    async def _discovery_worker(self, scan_id: UUID):
        """
        Subagent 1: The Scout.
        Focus: Finds assets (Subdomains, IPs, Live Hosts) and saves them to DB.
        """
        from kodiak.core.agent import KodiakAgent
        logger.info(f"Discovery Agent started for {scan_id}")
        
        try:
            async for session in get_session():
                scan = await crud_scan.get(session, scan_id)
                target = scan.config.get("target") if scan else None
                if not target: return
                
                # Instructions from Manager (via Config)
                directives = scan.config.get("directives", {}).get("scout", {})
                manager_instr = directives.get("instructions", "")
                action = directives.get("action", "start")
                
                if action == "stop":
                    logger.info("[Scout] Paused by Manager.")
                    await asyncio.sleep(5)
                    continue

                user_instructions = scan.config.get("instructions", "")
                
                agent = KodiakAgent(agent_id=f"scout-{scan_id}")
                
                # RECON LOOP
                history = [{"role": "user", "content": f"Find subdomains and live hosts for {target}."}]
                tools = ["subfinder_enumerate", "httpx_probe", "terminal_execute"]
                system_prompt = (
                    "You are the SCOUT AGENT. Your ONLY job is discovery."
                    "1. Find subdomains."
                    "2. Verify they are alive."
                    "3. Do NOT run active scans (nmap/nuclei)."
                    f"\n\nUser Context: {user_instructions}"
                    f"\nMANAGER ORDERS: {manager_instr}"
                )
                
                for _ in range(10): # Max steps for recon
                    # Check stop signal
                    # (Simplified: if scan status changed)
                    
                    response = await agent.think(history, allowed_tools=tools, system_prompt=system_prompt)
                    
                    # Log & Execute
                    if response.tool_calls:
                         for tool_call in response.tool_calls:
                            fn_name = tool_call.function.name
                            fn_args = json.loads(tool_call.function.arguments)
                            
                            logger.info(f"[Scout] Executing: {fn_name}")
                            result = await agent.act(fn_name, fn_args, session=session, project_id=scan.project_id, scan_id=scan_id)
                            
                            history.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": json.dumps(result)
                            })
                    else:
                        logger.info(f"[Scout] Thought: {response.content}")
                        history.append(response.dict() if hasattr(response, 'dict') else dict(response))
                        if "completed" in str(response.content).lower():
                            break
                            
                logger.info("Discovery Agent finished.")
                return 

        except Exception as e:
            logger.exception(f"Discovery Worker failed: {e}")

    async def _exploit_worker(self, scan_id: UUID):
        """
        Subagent 2: The Attacker.
        Focus: Polling the DB for new 'unscanned' assets and nuking them.
        """
        from kodiak.core.agent import KodiakAgent
        from kodiak.database.models import Asset
        from sqlmodel import select
        
        logger.info(f"Exploit Agent started for {scan_id}")
        
        agent = KodiakAgent(agent_id=f"attacker-{scan_id}")
        
        try:
            # Poll Loop
            while True:
                async for session in get_session():
                    scan = await crud_scan.get(session, scan_id)
                    if not scan or scan.status != ScanStatus.RUNNING:
                        return

                    # 1. Find Unscanned Assets
                    # We need assets belonging to this project/scan
                    # Simplification: Fetch one unscanned asset
                    statement = select(Asset).where(
                        Asset.project_id == scan.project_id,
                        Asset.scanned == False,
                        Asset.type == "endpoint" # Only scan live endpoints for now
                    ).limit(1)
                    
                    result = await session.execute(statement)
                    asset = result.scalar_one_or_none()
                    
                    if asset:
                        # Lock it
                        asset.scanned = True
                        session.add(asset)
                        await session.commit()
                        
                        target_host = asset.value
                        logger.info(f"[Attacker] Picked up target: {target_host}")
                        
                        # Check Manager Directives
                        directives = scan.config.get("directives", {}).get("attacker", {})
                        manager_instr = directives.get("instructions", "")
                        action = directives.get("action", "start")
                        
                        if action == "stop":
                             logger.info("[Attacker] Paused by Manager.")
                             await asyncio.sleep(5)
                             continue
                        
                        # Attack it!
                        # We create a mini-session for this target
                        history = [{"role": "user", "content": f"Scan {target_host} for vulnerabilities."}]
                        tools = ["nmap", "nuclei_scan"] # Focused set
                        system_prompt = (
                            "You are the ATTACKER. Find vulnerabilities. High impact only."
                            f"\nMANAGER ORDERS: {manager_instr}"
                        )
                        
                        # Quick exploit loop (3 steps max per asset)
                        for _ in range(3):
                             response = await agent.think(history, allowed_tools=tools, system_prompt=system_prompt)
                             if response.tool_calls:
                                for tool_call in response.tool_calls:
                                    fn_name = tool_call.function.name
                                    fn_args = json.loads(tool_call.function.arguments)
                                    await agent.act(fn_name, fn_args, session=session, project_id=scan.project_id, scan_id=scan_id)
                             else:
                                 break
                    else:
                        # No targets yet, wait for Scout
                        await asyncio.sleep(5)
                        
        except Exception as e:
            logger.exception(f"Exploit Worker failed: {e}")

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

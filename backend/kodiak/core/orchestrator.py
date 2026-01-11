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

                    # B. AI-Driven Loop
                    if target:
                        logger.info(f"Orchestrator: Starting AI Loop on {target}")
                        
                        # Initialize History
                        # TODO: Load history from DB if resuming
                        history = []
                        history.append({
                            "role": "user", 
                            "content": f"Perform a comprehensive penetration test on {target}. Start with subdomain enumeration, then probe for live hosts, then scan ports and vulnerabilities. Report all findings."
                        })
                        
                        # LIMIT steps to prevent infinite loops and cost
                        MAX_STEPS = 15
                        
                        for step in range(MAX_STEPS):
                            logger.info(f"Step {step+1}/{MAX_STEPS}")
                            
                            # 1. THINK
                            # Check if we should stop? (handled by outer loop check)
                            
                            try:
                                response_message = await agent.think(history)
                            except Exception as e:
                                logger.error(f"LLM Error: {e}")
                                break
                                
                            # Append assistant response to history
                            # We need to convert the message object to a dict for next iteration context
                            # LiteLLM/OpenAI objects usually convert to dict easily
                            # Pydantic v2 usually has model_dump()
                            msg_dict = response_message.dict() if hasattr(response_message, 'dict') else dict(response_message)
                            history.append(msg_dict)
                            
                            # 2. ACT
                            if response_message.tool_calls:
                                for tool_call in response_message.tool_calls:
                                    fn_name = tool_call.function.name
                                    fn_args_str = tool_call.function.arguments
                                    import json
                                    try:
                                        fn_args = json.loads(fn_args_str)
                                    except:
                                        fn_args = {}
                                    
                                    logger.info(f"Agent executing: {fn_name}({fn_args})")
                                    
                                    # Execute with Persistence Context
                                    # scan.project_id available from loaded scan object
                                    result = await agent.act(
                                        fn_name, 
                                        fn_args, 
                                        session=session, 
                                        project_id=scan.project_id
                                    )
                                    
                                    # Append result
                                    history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps(result)
                                    })
                            else:
                                # No tool calls? Maybe it's done or asking a question
                                logger.info(f"Agent Message: {response_message.content}")
                                if "Scan Completed" in str(response_message.content):
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

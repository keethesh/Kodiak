import asyncio
from typing import Dict, Optional, List, Any
from uuid import UUID
import json

from loguru import logger
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.database import get_session
from kodiak.database.crud import scan_job as crud_scan, project as crud_project
from kodiak.database.models import ScanJob, ScanStatus, Task
from kodiak.core.tools.inventory import inventory
from sqlmodel import select

class Orchestrator:
    """
    The Swarm Kernel.
    Instead of hardcoded loops, it acts as a 'Task Scheduler'.
    It polls the 'Task' table (Blackboard) and spawns workers for pending tasks.
    """
    
    def __init__(self, tool_inventory=None):
        self._active_workers: Dict[UUID, asyncio.Task] = {} # Task.id -> asyncio.Task
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False
        self.tool_inventory = tool_inventory or inventory
        
        # Cache available tools for validation
        self._available_tools = list(self.tool_inventory.list_tools().keys())
        logger.info(f"Orchestrator initialized with {len(self._available_tools)} available tools: {self._available_tools}")

    def get_available_tools(self) -> List[str]:
        """Get list of available tool names from inventory"""
        return self._available_tools.copy()
    
    def validate_tool_exists(self, tool_name: str) -> bool:
        """Validate that a tool exists in the inventory"""
        return tool_name in self._available_tools
    
    def _parse_task_directive(self, directive_str: str) -> Dict[str, Any]:
        """
        Parse and validate task directive JSON string.
        
        Args:
            directive_str: JSON string containing task directive
            
        Returns:
            Dict containing parsed directive, or empty dict if invalid
        """
        if not directive_str:
            logger.warning("Empty directive string provided")
            return {}
            
        try:
            directive = json.loads(directive_str)
            
            # Validate directive structure
            if not isinstance(directive, dict):
                logger.error(f"Directive must be a JSON object, got: {type(directive)}")
                return {}
            
            # Validate required fields
            required_fields = ["goal", "role"]
            missing_fields = [field for field in required_fields if field not in directive]
            if missing_fields:
                logger.warning(f"Directive missing required fields: {missing_fields}")
                # Set defaults for missing fields
                if "goal" not in directive:
                    directive["goal"] = "Execute assigned task."
                if "role" not in directive:
                    directive["role"] = "specialist"
            
            # Validate role is a valid string
            if not isinstance(directive.get("role"), str):
                logger.warning(f"Invalid role type: {type(directive.get('role'))}, defaulting to 'specialist'")
                directive["role"] = "specialist"
            
            # Validate goal is a valid string
            if not isinstance(directive.get("goal"), str):
                logger.warning(f"Invalid goal type: {type(directive.get('goal'))}, setting default")
                directive["goal"] = "Execute assigned task."
            
            logger.debug(f"Successfully parsed directive: {directive}")
            return directive
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse directive JSON: {e}")
            logger.error(f"Invalid directive string: {directive_str}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error parsing directive: {e}")
            return {}
    
    def get_tools_for_role(self, role: str) -> List[str]:
        """Get appropriate tools for a specific agent role"""
        # Get all available tools
        all_tools = self.get_available_tools()
        
        # Role-based tool filtering (can be expanded based on requirements)
        if role == "scout":
            # Scout agents focus on reconnaissance and discovery
            preferred_tools = [
                "nmap", "subfinder", "httpx", "nuclei", "web_search",
                "terminal_execute", "browser_navigate"
            ]
        elif role == "attacker":
            # Attacker agents focus on exploitation
            preferred_tools = [
                "sqlmap", "commix", "nuclei", "browser_navigate", 
                "terminal_execute", "python_execute", "proxy_request"
            ]
        elif role == "manager":
            # Manager agents coordinate and analyze
            preferred_tools = [
                "web_search", "terminal_execute", "browser_navigate",
                "nmap", "nuclei", "httpx"
            ]
        else:
            # Generalist agents get access to all tools
            preferred_tools = all_tools
        
        # Filter to only include tools that actually exist
        valid_tools = [tool for tool in preferred_tools if tool in all_tools]
        
        # If no preferred tools are available, fall back to all available tools
        if not valid_tools:
            valid_tools = all_tools
            
        logger.debug(f"Tools for role '{role}': {valid_tools}")
        return valid_tools

    async def start(self):
        """
        Start the global scheduler loop.
        """
        if self._running: 
            logger.warning("Orchestrator is already running")
            return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Orchestrator Scheduler started and polling for tasks every 2 seconds")

    async def stop(self):
        """
        Stop the orchestrator and clean up all workers.
        """
        logger.info("Stopping orchestrator...")
        self._running = False
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all workers
        cancelled_count = len(self._active_workers)
        for task_id, worker in self._active_workers.items():
            logger.debug(f"Cancelling worker for task {task_id}")
            worker.cancel()
        
        self._active_workers.clear()
        logger.info(f"Orchestrator stopped, cancelled {cancelled_count} workers")

    async def start_scan(self, scan_id: UUID):
        """
        Bootstraps a scan by creating the initial 'Root Task' for the Manager.
        """
        async for session in get_session():
            scan = await crud_scan.get(session, scan_id)
            if not scan: 
                logger.error(f"Cannot start scan {scan_id}: scan not found")
                return
            
            # Validate scan configuration
            if not scan.config.get("target"):
                logger.error(f"Cannot start scan {scan_id}: missing target in configuration")
                await crud_scan.update_status(session, scan_id, ScanStatus.FAILED)
                await session.commit()
                return
            
            # Check if scan is already running
            if scan.status == ScanStatus.RUNNING:
                logger.warning(f"Scan {scan_id} is already running")
                return
            
            # Check if there's already a root task for this scan
            existing_task_stmt = select(Task).where(
                Task.project_id == scan.project_id,
                Task.name == "Mission Manager"
            )
            existing_task_result = await session.execute(existing_task_stmt)
            existing_task = existing_task_result.scalar_one_or_none()
            
            if existing_task and existing_task.status in ["pending", "running"]:
                logger.info(f"Root task already exists for scan {scan_id}, updating scan status")
                await crud_scan.update_status(session, scan_id, ScanStatus.RUNNING)
                await session.commit()
                return
            
            # The Goal comes from the user config
            user_goal = scan.config.get("instructions", "Conduct a full penetration test.")
            target = scan.config.get("target")
            
            # Create root task
            root_task = Task(
                project_id=scan.project_id,
                name="Mission Manager",
                status="pending",
                assigned_agent_id=f"manager-{scan_id}",
                directive=json.dumps({
                    "goal": user_goal,
                    "target": target,
                    "role": "manager",
                    "scan_id": str(scan_id)
                })
            )
            
            try:
                session.add(root_task)
                await crud_scan.update_status(session, scan_id, ScanStatus.RUNNING)
                await session.commit()
                logger.info(f"Bootstrapped Root Task {root_task.id} for Scan {scan_id}")
                logger.info(f"Target: {target}, Goal: {user_goal}")
                # The scheduler loop will pick this up automatically!
            except Exception as e:
                logger.error(f"Failed to create root task for scan {scan_id}: {e}")
                await session.rollback()
                await crud_scan.update_status(session, scan_id, ScanStatus.FAILED)
                await session.commit()
                raise

    async def stop_scan(self, scan_id: UUID):
        """
        Stop a scan by cancelling associated workers and updating scan status.
        """
        async for session in get_session():
            scan = await crud_scan.get(session, scan_id)
            if not scan:
                logger.warning(f"Scan {scan_id} not found for stopping")
                return 0
            
            # Check if scan can be stopped
            if scan.status not in [ScanStatus.RUNNING, ScanStatus.PENDING]:
                logger.warning(f"Cannot stop scan {scan_id} with status {scan.status}")
                return 0
            
            # Find and cancel workers for tasks associated with this scan's project
            try:
                # Get all tasks for this project
                statement = select(Task).where(Task.project_id == scan.project_id)
                results = await session.execute(statement)
                project_tasks = results.scalars().all()
                
                # Cancel active workers for these tasks
                cancelled_workers = []
                for task in project_tasks:
                    if task.id in self._active_workers:
                        worker = self._active_workers[task.id]
                        worker.cancel()
                        del self._active_workers[task.id]
                        cancelled_workers.append(task.id)
                        
                        # Update task status to cancelled
                        task.status = "cancelled"
                        task.result = "Scan stopped by user"
                        session.add(task)
                
                # Update scan status
                await crud_scan.update_status(session, scan_id, ScanStatus.PAUSED)
                await session.commit()
                
                logger.info(f"Stopped scan {scan_id}, cancelled {len(cancelled_workers)} workers: {cancelled_workers}")
                return len(cancelled_workers)
                
            except Exception as e:
                logger.error(f"Error stopping scan {scan_id}: {e}")
                await session.rollback()
                # Try to update scan status to failed
                try:
                    await crud_scan.update_status(session, scan_id, ScanStatus.FAILED)
                    await session.commit()
                except Exception as status_error:
                    logger.error(f"Failed to update scan status after stop error: {status_error}")
                raise

    async def _scheduler_loop(self):
        """
        The Heartbeat. Polls for pending tasks and spawns workers.
        """
        while self._running:
            try:
                async for session in get_session():
                    # Find pending tasks
                    statement = select(Task).where(Task.status == "pending")
                    results = await session.execute(statement)
                    pending_tasks = results.scalars().all()
                    
                    for task in pending_tasks:
                        if task.id in self._active_workers:
                            continue
                            
                        # Mark as running
                        task.status = "running"
                        session.add(task)
                        await session.commit()
                        
                        # Spawn Worker
                        worker_task = asyncio.create_task(self._worker_wrapper(task.id, task.project_id))
                        self._active_workers[task.id] = worker_task
                        logger.info(f"Spawned Worker for Task {task.id} ({task.assigned_agent_id})")
                
                await asyncio.sleep(2) # Check every 2s
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler Loop Error: {e}")
                await asyncio.sleep(5)

    async def _worker_wrapper(self, task_id: UUID, project_id: UUID):
        """
        Wrapper to handle worker lifecycle and update Task status on completion.
        """
        from kodiak.api.events import event_manager
        
        try:
            await self._run_agent_for_task(task_id, project_id)
            status = "completed"
            result = "Task finished successfully."
        except Exception as e:
            logger.exception(f"Worker {task_id} crashed: {e}")
            status = "failed"
            result = str(e)
            
        # cleanup
        if task_id in self._active_workers:
            del self._active_workers[task_id]
            
        # Update DB
        try:
            async for session in get_session():
                task = await session.get(Task, task_id)
                if task:
                    task.status = status
                    task.result = result
                    session.add(task)
                    await session.commit()
                    
                    # Check if this was a root task (Mission Manager) and emit scan completion events
                    if task.name == "Mission Manager":
                        # Find the associated scan
                        scan_stmt = select(ScanJob).where(ScanJob.project_id == project_id)
                        scan_result = await session.execute(scan_stmt)
                        scan = scan_result.scalar_one_or_none()
                        
                        if scan and event_manager:
                            if status == "completed":
                                # Get task summary for the scan
                                task_stmt = select(Task).where(Task.project_id == project_id)
                                task_result = await session.execute(task_stmt)
                                all_tasks = task_result.scalars().all()
                                
                                task_summary = {}
                                for t in all_tasks:
                                    task_summary[t.status] = task_summary.get(t.status, 0) + 1
                                
                                await event_manager.emit_scan_completed(
                                    scan_id=str(scan.id),
                                    scan_name=scan.name,
                                    status="completed",
                                    summary={
                                        "total_tasks": len(all_tasks),
                                        "task_breakdown": task_summary,
                                        "target": scan.config.get("target"),
                                        "completion_reason": "Mission completed successfully"
                                    }
                                )
                            else:
                                await event_manager.emit_scan_failed(
                                    scan_id=str(scan.id),
                                    scan_name=scan.name,
                                    error=result,
                                    details={
                                        "task_id": str(task_id),
                                        "agent_id": task.assigned_agent_id,
                                        "target": scan.config.get("target"),
                                        "failure_reason": "Root task failed"
                                    }
                                )
                            
                            # Update scan status
                            from kodiak.database.crud import scan_job as crud_scan
                            final_status = "completed" if status == "completed" else "failed"
                            await crud_scan.update_status(session, scan.id, final_status)
                            await session.commit()
                            
        except Exception as db_e:
            logger.error(f"Failed to update task status {task_id}: {db_e}")

    async def _run_agent_for_task(self, task_id: UUID, project_id: UUID):
        """
        The Generic Agent Runtime.
        Instantiates an Agent with the specific Task Context.
        """
        from kodiak.core.agent import KodiakAgent
        from kodiak.api.events import event_manager
        
        async for session in get_session():
            task = await session.get(Task, task_id)
            if not task: 
                logger.error(f"Task {task_id} not found")
                return
            
            # Extract and validate directive
            directive = self._parse_task_directive(task.directive)
            if not directive:
                logger.error(f"Invalid directive for task {task_id}: {task.directive}")
                return
                
            role = directive.get("role", "specialist")
            goal = directive.get("goal", "Execute assigned task.")
            target = directive.get("target", "unknown")
            
            logger.info(f"Starting agent {task.assigned_agent_id} for task {task_id}")
            logger.info(f"Role: {role}, Goal: {goal}, Target: {target}")
            
            try:
                # Instantiate Agent with proper dependencies
                agent = KodiakAgent(
                    agent_id=task.assigned_agent_id, 
                    tool_inventory=self.tool_inventory,
                    event_manager=event_manager,
                    session=session, 
                    role=role, 
                    project_id=project_id
                )
                
                # Register agent with hive mind for coordination
                await agent.register_with_hive_mind()
                
                # Initial Memory
                history = [{"role": "user", "content": f"MISSION: {goal}"}]
                
                # Get appropriate tools for the agent's role with validation
                tools = self.get_tools_for_role(role)
                
                # Validate all tools exist in inventory
                validated_tools = []
                for tool_name in tools:
                    if self.validate_tool_exists(tool_name):
                        validated_tools.append(tool_name)
                    else:
                        logger.warning(f"Tool '{tool_name}' not found in inventory, skipping")
                
                if not validated_tools:
                    logger.error(f"No valid tools available for role '{role}', using all available tools")
                    validated_tools = self.get_available_tools()
                
                logger.info(f"Agent {agent.agent_id} assigned tools: {validated_tools}")
                
                # THINK-ACT LOOP with proper error handling
                max_iterations = 20
                iteration_count = 0
                
                for iteration in range(max_iterations):
                    iteration_count = iteration + 1
                    
                    # Check if task was cancelled externally
                    await session.refresh(task)
                    if task.status == "cancelled":
                        logger.info(f"Task {task_id} was cancelled, stopping agent")
                        return
                    
                    try:
                        # Agent thinks about next action
                        logger.debug(f"Agent {agent.agent_id} thinking (iteration {iteration_count}/{max_iterations})")
                        
                        # Emit agent thinking event
                        await event_manager.emit_agent_thinking(
                            agent_id=agent.agent_id,
                            message=f"Analyzing situation and planning next action (iteration {iteration_count})",
                            scan_id=str(project_id)
                        )
                        
                        response = await agent.think(history, allowed_tools=validated_tools)
                        
                        # Check for task completion
                        if response.content and ("TASK_COMPLETE" in str(response.content) or "MISSION COMPLETE" in str(response.content)):
                            logger.info(f"Agent {agent.agent_id} completed task after {iteration_count} iterations")
                            return
                        
                        # Process tool calls
                        if response.tool_calls:
                            for tool_call in response.tool_calls:
                                fn_name = tool_call.function.name
                                try:
                                    fn_args = json.loads(tool_call.function.arguments)
                                except json.JSONDecodeError as e:
                                    logger.error(f"Invalid tool arguments for {fn_name}: {e}")
                                    history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps({"error": f"Invalid arguments: {str(e)}"})
                                    })
                                    continue
                                
                                logger.info(f"[{agent.agent_id}] Executing tool: {fn_name}")
                                
                                # Validate tool exists before execution
                                if not self.validate_tool_exists(fn_name):
                                    error_msg = f"Tool '{fn_name}' not found in inventory"
                                    logger.error(error_msg)
                                    history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps({"error": error_msg})
                                    })
                                    continue
                                
                                # Execute tool through agent
                                try:
                                    result = await agent.act(fn_name, fn_args, session=session, project_id=project_id, task_id=task_id)
                                    
                                    # Add result to conversation history
                                    history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps(result)
                                    })
                                    
                                    logger.debug(f"Tool {fn_name} executed successfully")
                                    
                                except Exception as tool_error:
                                    logger.error(f"Tool execution failed for {fn_name}: {tool_error}")
                                    history.append({
                                        "role": "tool",
                                        "tool_call_id": tool_call.id,
                                        "content": json.dumps({"error": f"Tool execution failed: {str(tool_error)}"})
                                    })
                        else:
                            # No tool calls, add agent response to history
                            history.append({
                                "role": "assistant",
                                "content": response.content or "No response content"
                            })
                        
                        # Brief pause between iterations
                        await asyncio.sleep(1)
                        
                    except Exception as think_error:
                        logger.error(f"Agent thinking failed on iteration {iteration_count}: {think_error}")
                        
                        # Add error to history and continue
                        history.append({
                            "role": "user",
                            "content": f"Error occurred: {str(think_error)}. Please continue with your mission."
                        })
                        
                        # Wait a bit longer on errors
                        await asyncio.sleep(2)
                
                # If we reach here, agent hit max iterations
                logger.warning(f"Agent {agent.agent_id} reached maximum iterations ({max_iterations}) without completing task")
                
            except Exception as agent_error:
                logger.error(f"Agent initialization or execution failed: {agent_error}")
                raise
            
            finally:
                # Unregister agent from hive mind
                try:
                    await agent.unregister_from_hive_mind()
                except Exception as e:
                    logger.warning(f"Failed to unregister agent from hive mind: {e}")


orchestrator = Orchestrator(tool_inventory=inventory)

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
    The Swarm Kernel.
    Instead of hardcoded loops, it acts as a 'Task Scheduler'.
    It polls the 'Task' table (Blackboard) and spawns workers for pending tasks.
    """
    
    def __init__(self):
        self._active_workers: Dict[UUID, asyncio.Task] = {} # Task.id -> asyncio.Task
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """
        Start the global scheduler loop.
        """
        if self._running: return
        self._running = True
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        logger.info("Orchestrator Scheduler started.")

    async def stop(self):
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
        
        # Cancel all workers
        for task_id, worker in self._active_workers.items():
            worker.cancel()
        self._active_workers.clear()

    async def start_scan(self, scan_id: UUID):
        """
        Bootstraps a scan by creating the initial 'Root Task' for the Manager.
        """
        async for session in get_session():
            scan = await crud_scan.get(session, scan_id)
            if not scan: return
            
            # Create Root Task if not exists
            # We check if there's already a root task for this project?
            # For now, simplistic: Create a "Mission" task
            from kodiak.database.models import Task
            
            # The Goal comes from the user config
            user_goal = scan.config.get("instructions", "Conduct a full penetration test.")
            
            root_task = Task(
                project_id=scan.project_id,
                name="Mission Manager",
                status="pending",
                assigned_agent_id=f"manager-{scan_id}",
                directive=json.dumps({
                    "goal": user_goal,
                    "target": scan.config.get("target"),
                    "role": "manager"
                })
            )
            session.add(root_task)
            await crud_scan.update_status(session, scan_id, ScanStatus.RUNNING)
            await session.commit()
            logger.info(f"Bootstrapped Root Task {root_task.id} for Scan {scan_id}")
            # The scheduler loop will pick this up automatically!

    async def _scheduler_loop(self):
        """
        The Heartbeat. Polls for pending tasks and spawns workers.
        """
        from kodiak.database.models import Task
        from sqlmodel import select
        
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
        from kodiak.database.models import Task
        
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
        except Exception as db_e:
            logger.error(f"Failed to update task status {task_id}: {db_e}")

    async def _run_agent_for_task(self, task_id: UUID, project_id: UUID):
        """
        The Generic Agent Runtime.
        Instantiates an Agent with the specific Task Context.
        """
        from kodiak.core.agent import KodiakAgent
        from kodiak.database.models import Task
        
        async for session in get_session():
            task = await session.get(Task, task_id)
            if not task: return
            
            # Extract Directive
            try:
                directive = json.loads(task.properties.get("directive", "{}")) if hasattr(task, "properties") else json.loads(getattr(task, "directive", "{}"))
            except:
                directive = {}
                
            role = directive.get("role", "specialist")
            goal = directive.get("goal", "Execute assigned task.")
            
            # Instantiate Agent
            agent = KodiakAgent(agent_id=task.assigned_agent_id, session=session) # Pass session? usually per tool
            
            # Initial Memory
            history = [{"role": "user", "content": f"MISSION: {goal}"}]
            
            # Different available tools based on Role?
            # For now, broad access, safety middleware restricts
            tools = ["spawn_agent", "terminal_execute", "browser_navigate", "search_web"]
            
            system_prompt = (
                f"You are a specialized agent: {role.upper()}.\n"
                f"Your Goal: {goal}\n"
                "You are part of a Hive Mind. You DO NOT need to report back extensively."
                "Just execute the work and save findings to the Blackboard."
                "If you need help, use 'spawn_agent' to create a sub-worker."
                "When finished, simply output 'TASK_COMPLETE'."
            )
            
            # THINK LOOP
            for _ in range(20): # Safety limit
                # Check if task was cancelled externally?
                await session.refresh(task)
                if task.status == "cancelled":
                    return

                response = await agent.think(history, allowed_tools=tools, system_prompt=system_prompt)
                
                if "TASK_COMPLETE" in str(response.content):
                    logger.info(f"Agent {agent.agent_id} completed task.")
                    return

                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        fn_name = tool_call.function.name
                        fn_args = json.loads(tool_call.function.arguments)
                        
                        logger.info(f"[{agent.agent_id}] Tool: {fn_name}")
                        
                        # Handle 'spawn_agent' specifically if not in standard toolbox yet
                        # Or delegate to agent.act()
                        
                        result = await agent.act(fn_name, fn_args, session=session, project_id=project_id, task_id=task_id)
                        
                        history.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        })
                else:
                    history.append(response.dict() if hasattr(response, 'dict') else dict(response))
                
                await asyncio.sleep(1) # Breathe


orchestrator = Orchestrator()

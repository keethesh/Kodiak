from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from kodiak.database import get_session
from kodiak.database.models import Task

router = APIRouter()

@router.get("/pending", response_model=List[Task])
async def get_pending_approvals(session: AsyncSession = Depends(get_session)):
    """
    Get all tasks paused for approval.
    """
    stmt = select(Task).where(Task.status == "paused")
    tasks = (await session.execute(stmt)).scalars().all()
    return tasks

@router.post("/{task_id}/{action}")
async def resolve_approval(task_id: UUID, action: str, session: AsyncSession = Depends(get_session)):
    """
    Action: 'approve' or 'deny'.
    """
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if action == "approve":
        task.status = "pending" # Resume! (Orchestrator will pick it up as if new, effectively retrying the step?)
        # Wait, if we set it to pending, Orchestrator spawns a fresh worker.
        # Ideally we want to resume the OLD worker.
        # But our async workers crash/return on pause? 
        # Check agent.py: it returns error.
        # Orchestrator generic loop handles completed/failed.
        # If it returned specific "PAUSED" status?
        
        # Architecture decision:
        # A "PAUSED" task needs to be "RESUMED".
        # If we set status="pending", Orchestrator spawns a NEW worker.
        # Does the new worker know to pick up where left off?
        # The agent is stateless-ish. It reads history.
        # BUT the specific tool call that failed IS NOT IN HISTORY yet (it was blocked).
        # So re-running the agent with same history = it tries the tool AGAIN.
        # This time, we need to ALLOW it.
        
        # How do we whitelist the 2nd attempt?
        # We need to add an "Approved" flag to the Task properties?
        props = task.properties or {}
        approved_tools = props.get("approved_tools", [])
        
        # Extract the tool that was blocked
        req = props.get("approval_request", {})
        tool_name = req.get("tool")
        if tool_name:
            approved_tools.append(tool_name)
            props["approved_tools"] = approved_tools
            task.properties = props
            
        task.status = "pending" # Restart worker
        session.add(task)
        await session.commit()
        return {"status": "resumed"}
        
    elif action == "deny":
        task.status = "failed"
        task.result = "User Denied Action."
        session.add(task)
        await session.commit()
        return {"status": "denied"}
        
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

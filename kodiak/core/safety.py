from typing import Dict, Any, Optional, Tuple
from uuid import UUID
import json
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger

class SafetyShield:
    """
    The Guardian.
    Intercepts every tool execution to ensure it complies with:
    1. Scope (Whitelist/Blacklist)
    2. Risk Profile (Approval Matrix)
    """
    
    def __init__(self):
        # Tools that are ALWAYS safe
        self.GREEN_TOOLS = {"whois_lookup", "dns_resolve", "search_web", "spawn_agent", "terminal_execute"} # terminal is risky but generic, we check cmd
        
        # Tools that need notification (Amber)
        self.AMBER_TOOLS = {"spider_crawl", "browser_navigate"}
        
        # Tools that MUST wait for approval (Red)
        self.RED_TOOLS = {"sqlmap_scan", "commix_scan", "nmap_scan_all_ports", "exploit_run"}
        
    async def check_tool_safety(self, tool_name: str, args: Dict[str, Any], project_id: UUID, session: AsyncSession, task_id: Optional[UUID] = None) -> Tuple[bool, str]:
        """
        Returns (IsSafe, Reason).
        If False, the Agent should PAUSE and request approval.
        """
        # 0. Check for Pre-Approval (Resume Logic)
        if task_id:
            from kodiak.database.models import Task
            task = await session.get(Task, task_id)
            if task and task.properties:
                approved = task.properties.get("approved_tools", [])
                if tool_name in approved:
                    return True, "Pre-Approved by User"
        
        # 1. SCOPE CHECK (Simulated)
        # In real implementation, we check args['url'] against project.scope
        target = args.get("target") or args.get("url") or args.get("host")
        if target:
            # check_scope(target, project_id)
            pass

        # 2. RISK CHECK
        if tool_name in self.RED_TOOLS:
            return False, f"Risk Level: RED. Tool '{tool_name}' requires explicit approval."
            
        if tool_name == "terminal_execute":
            cmd = args.get("command", "")
            if "rm " in cmd or "sudo " in cmd or "shutdown" in cmd:
                return False, f"Risk Level: CRITICAL. Dangerous Command: {cmd}"
                
        return True, "Safe"

    async def request_approval(self, task_id: UUID, tool_name: str, args: Dict[str, Any], session: AsyncSession):
        """
        Pauses the task and flags it for user review.
        """
        from kodiak.database.models import Task
        
        task = await session.get(Task, task_id)
        if not task: return
        
        # Update Task to PAUSED status
        task.status = "paused"
        
        # Store context in properties
        props = task.properties or {}
        props["approval_request"] = {
            "tool": tool_name,
            "args": args,
            "timestamp": "now"
        }
        task.properties = props
        
        session.add(task)
        await session.commit()
        logger.warning(f"Task {task_id} PAUSED for approval on {tool_name}")

safety = SafetyShield()

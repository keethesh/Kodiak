from typing import List, Optional
from uuid import UUID
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from loguru import logger
import tldextract

from kodiak.database.engine import engine
# Attempt to import ScanJob but handle potential circular imports if needed (usually fine in function scope or with Pydantic)
# from kodiak.database.models import ScanJob

class ScopeManager:
    """
    Ensures the agent stays within the authorized scope.
    """
    def __init__(self, allowed_domains: List[str] = None):
        self.allowed_domains = allowed_domains or []

    def is_allowed(self, target: str) -> bool:
        if not self.allowed_domains:
            # If no scope defined, allow nothing (Safety First) or everything? 
            # In a pentest context, undefined scope is dangerous.
            # But during dev/testing, might default to permissive if explicitly configured.
            return False 
            
        # Parse target
        # Check if target is sub-domain of allowed domains
        for allowed in self.allowed_domains:
            if self._is_subdomain(target, allowed):
                return True
        return False

    def _is_subdomain(self, target: str, parent: str) -> bool:
        """
        Checks if target is subdomain of parent.
        """
        target = target.lower().strip()
        parent = parent.lower().strip()
        
        if target == parent:
            return True
        if target.endswith("." + parent):
            return True
        return False

class ApprovalManager:
    """
    Manages human-in-the-loop approvals for risky actions.
    """
    async def request_approval(self, scan_id: UUID, tool_name: str, args: dict) -> bool:
        """
        Pauses execution and waits for user approval via DB.
        """
        # TODO: Implement DB-backed approval request
        # 1. Create ApprovalRequest in DB
        # 2. Poll for status change OR return False/Pending
        
        logger.warning(f"Blocking action requested: {tool_name} {args}")
        # For MVP, we might just log and auto-deny or allow specific safe ones
        return True # Auto-allow for now until UI is ready
        
# Global Safety Instance (can be re-initialized per scan context)
safety = ScopeManager()

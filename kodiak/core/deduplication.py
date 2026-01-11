"""
Attempt tracking and deduplication service.
Prevents infinite loops by tracking tool execution attempts and implementing smart deduplication logic.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from uuid import UUID
from loguru import logger

from kodiak.database.models import Attempt
from kodiak.database.crud import attempt as attempt_crud


class DeduplicationService:
    """
    Service for tracking tool execution attempts and preventing infinite loops.
    Implements smart deduplication logic based on tool type, target, and execution history.
    """
    
    def __init__(self):
        # Configuration for deduplication behavior
        self.max_failed_attempts = 3  # Maximum failed attempts before skipping
        self.success_cache_duration = timedelta(hours=24)  # How long to cache successful attempts
        self.failure_retry_delay = timedelta(minutes=30)  # Minimum time between retry attempts
        
        # Tools that should always be allowed to retry (e.g., reconnaissance tools)
        self.always_retry_tools = {
            "web_search", "terminal_execute", "proxy_request"
        }
        
        # Tools that should be strictly deduplicated (e.g., vulnerability scanners)
        self.strict_dedup_tools = {
            "nmap", "nuclei", "sqlmap", "commix", "subfinder"
        }

    def _normalize_target(self, tool: str, target: str) -> str:
        """
        Normalize target string for consistent deduplication.
        Different tools may have different target formats.
        """
        if not target:
            return "unknown"
        
        # For URL-based tools, normalize the URL
        if tool in {"proxy_request", "web_search", "nuclei"}:
            # Remove query parameters and fragments for deduplication
            if "?" in target:
                target = target.split("?")[0]
            if "#" in target:
                target = target.split("#")[0]
            # Ensure consistent trailing slash handling
            if target.endswith("/") and len(target) > 1:
                target = target[:-1]
        
        # For network tools, normalize IP/port format
        elif tool in {"nmap", "subfinder"}:
            # Normalize IP ranges and port specifications
            target = target.strip().lower()
        
        # For command-based tools, normalize command structure
        elif tool == "terminal_execute":
            # For terminal commands, we might want to normalize whitespace
            target = " ".join(target.split())
        
        return target.lower().strip()

    def _generate_attempt_key(self, tool: str, target: str, args: Dict[str, Any]) -> str:
        """
        Generate a unique key for this attempt based on tool, target, and relevant args.
        This key is used for deduplication logic.
        """
        normalized_target = self._normalize_target(tool, target)
        
        # Include relevant args in the key for tools where args matter
        key_components = [tool, normalized_target]
        
        # For some tools, specific arguments affect the outcome
        if tool == "nmap":
            # Include scan type and port range in key
            if "scan_type" in args:
                key_components.append(f"scan_type:{args['scan_type']}")
            if "ports" in args:
                key_components.append(f"ports:{args['ports']}")
        elif tool == "nuclei":
            # Include template selection in key
            if "templates" in args:
                key_components.append(f"templates:{args['templates']}")
        elif tool == "sqlmap":
            # Include specific parameters that affect testing
            if "data" in args:
                # Hash the data to avoid storing sensitive info
                data_hash = hashlib.md5(str(args["data"]).encode()).hexdigest()[:8]
                key_components.append(f"data_hash:{data_hash}")
        
        # Create a hash of the key components for consistent length
        key_string = "|".join(key_components)
        return hashlib.sha256(key_string.encode()).hexdigest()[:16]

    async def should_skip_attempt(
        self, 
        session: Any, 
        project_id: UUID, 
        tool: str, 
        target: str, 
        args: Dict[str, Any]
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if this tool execution attempt should be skipped based on deduplication logic.
        
        Returns:
            Tuple of (should_skip: bool, reason: Optional[str])
        """
        try:
            normalized_target = self._normalize_target(tool, target)
            
            # Check for recent successful attempts
            existing_attempt = await attempt_crud.get_by_tool_and_target(
                session, project_id, tool, normalized_target
            )
            
            if existing_attempt:
                # If we have a recent successful attempt, skip for strict dedup tools
                if (existing_attempt.status == "success" and 
                    tool in self.strict_dedup_tools):
                    
                    # Check if the success is still within cache duration
                    time_since_success = datetime.utcnow() - existing_attempt.timestamp
                    if time_since_success < self.success_cache_duration:
                        return True, f"Tool {tool} already succeeded on {normalized_target} within {self.success_cache_duration}"
                
                # Check failed attempt limits
                if existing_attempt.status == "failure":
                    failed_count = await attempt_crud.count_failed_attempts(
                        session, project_id, tool, normalized_target
                    )
                    
                    if failed_count >= self.max_failed_attempts and tool not in self.always_retry_tools:
                        return True, f"Tool {tool} has failed {failed_count} times on {normalized_target}, skipping"
                    
                    # Check if enough time has passed since last failure
                    time_since_failure = datetime.utcnow() - existing_attempt.timestamp
                    if time_since_failure < self.failure_retry_delay:
                        return True, f"Tool {tool} failed recently on {normalized_target}, waiting for retry delay"
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking deduplication for {tool} on {target}: {e}")
            # On error, allow the attempt to proceed
            return False, None

    async def record_attempt(
        self, 
        session: Any, 
        project_id: UUID, 
        tool: str, 
        target: str, 
        status: str, 
        reason: Optional[str] = None
    ) -> Attempt:
        """
        Record a tool execution attempt in the database.
        
        Args:
            session: Database session
            project_id: Project UUID
            tool: Tool name
            target: Target identifier
            status: "success", "failure", or "skipped"
            reason: Optional reason for the status
            
        Returns:
            Created Attempt record
        """
        try:
            normalized_target = self._normalize_target(tool, target)
            
            attempt_record = Attempt(
                project_id=project_id,
                tool=tool,
                target=normalized_target,
                status=status,
                reason=reason,
                timestamp=datetime.utcnow()
            )
            
            return await attempt_crud.create(session, attempt_record)
            
        except Exception as e:
            logger.error(f"Error recording attempt for {tool} on {target}: {e}")
            raise

    async def get_attempt_history(
        self, 
        session: Any, 
        project_id: UUID, 
        tool: Optional[str] = None, 
        limit: int = 50
    ) -> list[Attempt]:
        """
        Get attempt history for context injection into agent prompts.
        
        Args:
            session: Database session
            project_id: Project UUID
            tool: Optional tool filter
            limit: Maximum number of attempts to return
            
        Returns:
            List of recent Attempt records
        """
        try:
            if tool:
                return await attempt_crud.get_attempts_by_tool(session, project_id, tool, limit)
            else:
                return await attempt_crud.get_attempts_by_project(session, project_id, limit)
                
        except Exception as e:
            logger.error(f"Error getting attempt history for project {project_id}: {e}")
            return []

    async def get_deduplication_stats(self, session: Any, project_id: UUID) -> Dict[str, Any]:
        """
        Get statistics about deduplication for monitoring and debugging.
        
        Returns:
            Dictionary with deduplication statistics
        """
        try:
            attempts = await attempt_crud.get_attempts_by_project(session, project_id, 1000)
            
            stats = {
                "total_attempts": len(attempts),
                "successful_attempts": len([a for a in attempts if a.status == "success"]),
                "failed_attempts": len([a for a in attempts if a.status == "failure"]),
                "skipped_attempts": len([a for a in attempts if a.status == "skipped"]),
                "tools_used": len(set(a.tool for a in attempts)),
                "unique_targets": len(set(a.target for a in attempts)),
                "recent_activity": len([a for a in attempts if (datetime.utcnow() - a.timestamp) < timedelta(hours=1)])
            }
            
            # Tool-specific stats
            tool_stats = {}
            for attempt in attempts:
                if attempt.tool not in tool_stats:
                    tool_stats[attempt.tool] = {"success": 0, "failure": 0, "skipped": 0}
                tool_stats[attempt.tool][attempt.status] += 1
            
            stats["tool_breakdown"] = tool_stats
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting deduplication stats for project {project_id}: {e}")
            return {"error": str(e)}


# Global instance
deduplication_service = DeduplicationService()
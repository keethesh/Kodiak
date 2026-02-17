"""
Hive Mind - Global state synchronization for Kodiak agents
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional
from uuid import UUID

from loguru import logger


class HiveMind:
    """
    Coordination layer that allows multiple agents to share discoveries,
    avoid duplicate work, and maintain a shared view of the target.
    """
    
    def __init__(self):
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._discoveries: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        logger.info("Hive Mind initialized")

    async def register_agent(self, agent_id: str, project_id: str, role: str):
        """Register an agent with the Hive Mind"""
        async with self._lock:
            self._agents[agent_id] = {
                "project_id": project_id,
                "role": role,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "last_seen": datetime.now(timezone.utc).isoformat()
            }
            logger.debug(f"Agent {agent_id} ({role}) registered with Hive Mind for project {project_id}")

    async def unregister_agent(self, agent_id: str):
        """Unregister an agent"""
        async with self._lock:
            if agent_id in self._agents:
                del self._agents[agent_id]
                logger.debug(f"Agent {agent_id} unregistered from Hive Mind")

    async def share_discovery(self, agent_id: str, project_id: str, discovery: Dict[str, Any], scan_id: Optional[str] = None) -> Dict[str, Any]:
        """Share a discovery with the Hive Mind"""
        async with self._lock:
            discovery_entry = {
                "agent_id": agent_id,
                "project_id": project_id,
                "scan_id": scan_id,
                "discovery": discovery,
                "discovered_at": datetime.now(timezone.utc).isoformat()
            }
            self._discoveries.append(discovery_entry)
            
            # Keep only the last 1000 discoveries to avoid memory bloat
            if len(self._discoveries) > 1000:
                self._discoveries = self._discoveries[-1000:]
            
            logger.debug(f"Discovery shared by {agent_id} for project {project_id}: {discovery.get('type', 'unknown')}")
            return discovery_entry

    async def get_shared_discoveries(self, project_id: str, since: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get discoveries shared for a project"""
        async with self._lock:
            project_discoveries = [d for d in self._discoveries if d["project_id"] == project_id]
            
            if since:
                project_discoveries = [d for d in project_discoveries if d["discovered_at"] > since]
            
            return project_discoveries

    async def get_active_agents(self, project_id: str) -> Dict[str, Dict[str, Any]]:
        """Get active agents for a project"""
        async with self._lock:
            return {aid: info for aid, info in self._agents.items() if info["project_id"] == project_id}


# Global instance
hive_mind = HiveMind()

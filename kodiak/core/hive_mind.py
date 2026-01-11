import asyncio
from datetime import datetime
from typing import Dict, Optional, Set, Any, List

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.database.models import CommandCache, Node
from kodiak.database.engine import engine


class HiveMindState:
    """
    Shared state container for agent discoveries and coordination.
    Enables state synchronization across all active agents.
    """
    
    def __init__(self):
        # Shared discoveries: project_id -> list of discoveries
        self._discoveries: Dict[str, List[Dict[str, Any]]] = {}
        # Active agents: agent_id -> agent info
        self._active_agents: Dict[str, Dict[str, Any]] = {}
        # Discovery subscribers: project_id -> set of agent_ids
        self._discovery_subscribers: Dict[str, Set[str]] = {}
        # Lock for thread-safe operations
        self._lock = asyncio.Lock()
    
    async def register_agent(self, agent_id: str, project_id: str, role: str = "generalist"):
        """Register an agent as active in the Hive Mind"""
        async with self._lock:
            self._active_agents[agent_id] = {
                "project_id": project_id,
                "role": role,
                "registered_at": datetime.utcnow().isoformat()
            }
            
            # Subscribe agent to project discoveries
            if project_id not in self._discovery_subscribers:
                self._discovery_subscribers[project_id] = set()
            self._discovery_subscribers[project_id].add(agent_id)
            
            logger.info(f"Agent {agent_id} registered with Hive Mind for project {project_id}")
    
    async def unregister_agent(self, agent_id: str):
        """Unregister an agent from the Hive Mind"""
        async with self._lock:
            if agent_id in self._active_agents:
                project_id = self._active_agents[agent_id].get("project_id")
                del self._active_agents[agent_id]
                
                # Remove from discovery subscribers
                if project_id and project_id in self._discovery_subscribers:
                    self._discovery_subscribers[project_id].discard(agent_id)
                
                logger.info(f"Agent {agent_id} unregistered from Hive Mind")
    
    async def share_discovery(self, agent_id: str, project_id: str, discovery: Dict[str, Any]):
        """Share a discovery with all agents in the same project"""
        async with self._lock:
            if project_id not in self._discoveries:
                self._discoveries[project_id] = []
            
            # Add metadata to discovery
            discovery_with_meta = {
                **discovery,
                "discovered_by": agent_id,
                "discovered_at": datetime.utcnow().isoformat()
            }
            self._discoveries[project_id].append(discovery_with_meta)
            
            logger.info(f"Agent {agent_id} shared discovery: {discovery.get('type', 'unknown')} - {discovery.get('name', 'unnamed')}")
            
            return discovery_with_meta
    
    async def get_discoveries(self, project_id: str, since: datetime = None) -> List[Dict[str, Any]]:
        """Get all discoveries for a project, optionally filtered by time"""
        async with self._lock:
            discoveries = self._discoveries.get(project_id, [])
            
            if since:
                since_str = since.isoformat()
                discoveries = [d for d in discoveries if d.get("discovered_at", "") > since_str]
            
            return discoveries.copy()
    
    async def get_active_agents(self, project_id: str = None) -> Dict[str, Dict[str, Any]]:
        """Get all active agents, optionally filtered by project"""
        async with self._lock:
            if project_id:
                return {
                    agent_id: info 
                    for agent_id, info in self._active_agents.items() 
                    if info.get("project_id") == project_id
                }
            return self._active_agents.copy()
    
    async def clear_project_state(self, project_id: str):
        """Clear all state for a project (useful for scan completion)"""
        async with self._lock:
            if project_id in self._discoveries:
                del self._discoveries[project_id]
            if project_id in self._discovery_subscribers:
                del self._discovery_subscribers[project_id]
            logger.info(f"Cleared Hive Mind state for project {project_id}")


class CommandLock:
    """
    The Hive Mind's synchronization primitive.
    Prevents multiple agents from running the same command string simultaneously.
    Uses DB for long-term caching and memory for active lock coordination.
    Integrates with EventManager for real-time coordination updates.
    """

    def __init__(self, event_manager=None):
        self._running_commands: Dict[str, asyncio.Future] = {}
        # We don't keep long-term cache in memory anymore, we use DB.
        # But we might keep a short-term LRU if needed. For now, DB is authoritative.
        self._subscribers: Dict[str, Set[str]] = {}  # command -> set of agent_ids
        self._event_manager = event_manager
        self._state = HiveMindState()

    def set_event_manager(self, event_manager):
        """Set the event manager for broadcasting coordination events"""
        self._event_manager = event_manager
        logger.info("Hive Mind EventManager configured")
    
    @property
    def state(self) -> HiveMindState:
        """Access the shared state container"""
        return self._state

    def is_running(self, command_str: str) -> bool:
        return command_str in self._running_commands
    
    def get_running_commands(self) -> Dict[str, Set[str]]:
        """Get all currently running commands and their subscribers"""
        return {cmd: subs.copy() for cmd, subs in self._subscribers.items() if cmd in self._running_commands}

    async def acquire(self, command_str: str, agent_id: str, scan_id: str = None) -> bool:
        """
        Try to acquire the lock for a command.
        Returns True if acquired (you are the leader).
        Returns False if already running (you should wait).
        Emits coordination events via EventManager.
        """
        if command_str in self._running_commands:
            if command_str not in self._subscribers:
                self._subscribers[command_str] = set()
            self._subscribers[command_str].add(agent_id)
            logger.info(f"Agent {agent_id} subscribing to existing command: {command_str}")
            
            # Emit waiting event
            await self._emit_coordination_event(
                command_str, "waiting", agent_id, scan_id,
                {"subscribers": len(self._subscribers[command_str])}
            )
            return False

        # Create a future that will be set when the command completes
        self._running_commands[command_str] = asyncio.Future()
        self._subscribers[command_str] = {agent_id}
        logger.info(f"Agent {agent_id} acquired lock for: {command_str}")
        
        # Emit acquired event
        await self._emit_coordination_event(
            command_str, "acquired", agent_id, scan_id
        )
        return True
    
    async def _emit_coordination_event(self, command: str, status: str, agent_id: str, scan_id: str = None, extra_data: Dict = None):
        """Emit a Hive Mind coordination event via EventManager"""
        try:
            if self._event_manager:
                # Use the websocket manager's hive mind update method
                from kodiak.services.websocket_manager import manager
                await manager.send_hive_mind_update(
                    command=command,
                    status=status,
                    agent_id=agent_id
                )
        except Exception as e:
            logger.warning(f"Failed to emit Hive Mind coordination event: {e}")

    async def wait_for_result(self, command_str: str, agent_id: str = None, scan_id: str = None) -> str:
        """
        Wait for an existing command to finish and return its output.
        Emits coordination events via EventManager.
        """
        if command_str not in self._running_commands:
            # Maybe it finished just before we called this? Check Cache.
            cached = await self.get_cached_result(command_str)
            if cached:
                return cached
            raise ValueError(f"Command {command_str} is not running or cached.")

        logger.info(f"Waiting for result of: {command_str}")
        
        # Emit waiting event
        if agent_id:
            await self._emit_coordination_event(
                command_str, "waiting", agent_id, scan_id
            )
        
        result = await self._running_commands[command_str]
        
        # Emit received event
        if agent_id:
            await self._emit_coordination_event(
                command_str, "received", agent_id, scan_id
            )
        
        return result

    async def release(self, command_str: str, output: str, agent_id: str = None, scan_id: str = None):
        """
        Release the lock, save to DB, and notify all subscribers.
        Emits coordination events via EventManager.
        """
        if command_str not in self._running_commands:
            return

        future = self._running_commands[command_str]
        subscribers = self._subscribers.get(command_str, set())
        
        # 1. Save to Database (Persist the knowledge)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                # Naive normalization of key. TODO: better key parsing if command_hash isn't just the key
                # Assuming command_str IS the key we want to store.
                # In base.py we construct it as "tool_name:json_args".
                parts = command_str.split(":", 1)
                tool_name = parts[0]
                args_json = parts[1] if len(parts) > 1 else "{}"
                
                cache_entry = CommandCache(
                    command_hash=command_str,
                    tool_name=tool_name,
                    args_json=args_json,
                    output=output
                )
                session.add(cache_entry)
                await session.commit()
                logger.info(f"Persisted result for {command_str} to Hive Mind (DB).")
        except Exception as e:
            logger.error(f"Failed to persist {command_str} result to DB: {e}")
        
        # 2. Notify waiters (The subscribers)
        if not future.done():
            future.set_result(output)
            
        # 3. Cleanup Memory
        del self._running_commands[command_str]
        self._subscribers.pop(command_str, set())
        
        # 4. Emit completion event
        await self._emit_coordination_event(
            command_str, "completed", agent_id, scan_id,
            {"subscribers_notified": len(subscribers)}
        )
        
        logger.info(f"Released lock for {command_str}. Notified {len(subscribers)} agents.")

    async def get_cached_result(self, command_str: str, scan_id: str = None) -> Optional[str]:
        """
        Check if we already have a result for this command in the DB.
        Emits cache hit event via EventManager.
        """
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                statement = select(CommandCache).where(CommandCache.command_hash == command_str)
                result = await session.exec(statement)
                entry = result.first()
                if entry:
                    logger.info(f"Hive Mind Cache Hit: {command_str}")
                    
                    # Emit cache hit event
                    await self._emit_coordination_event(
                        command_str, "cached", None, scan_id
                    )
                    
                    return entry.output
        except Exception as e:
            logger.warning(f"Hive Mind Cache Lookup Error: {e}")
            return None
        return None
    
    async def share_discovery(self, agent_id: str, project_id: str, discovery: Dict[str, Any], scan_id: str = None) -> Dict[str, Any]:
        """
        Share a discovery with all agents in the same project.
        This enables state synchronization across agents.
        """
        result = await self._state.share_discovery(agent_id, project_id, discovery)
        
        # Emit discovery event via EventManager
        if self._event_manager:
            try:
                await self._event_manager.emit_discovery(result, scan_id)
            except Exception as e:
                logger.warning(f"Failed to emit discovery event: {e}")
        
        return result
    
    async def get_shared_discoveries(self, project_id: str, since: datetime = None) -> List[Dict[str, Any]]:
        """Get all shared discoveries for a project"""
        return await self._state.get_discoveries(project_id, since)
    
    async def register_agent(self, agent_id: str, project_id: str, role: str = "generalist"):
        """Register an agent with the Hive Mind for state synchronization"""
        await self._state.register_agent(agent_id, project_id, role)
    
    async def unregister_agent(self, agent_id: str):
        """Unregister an agent from the Hive Mind"""
        await self._state.unregister_agent(agent_id)
    
    async def get_active_agents(self, project_id: str = None) -> Dict[str, Dict[str, Any]]:
        """Get all active agents in the Hive Mind"""
        return await self._state.get_active_agents(project_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Hive Mind statistics"""
        return {
            "running_commands": len(self._running_commands),
            "total_subscribers": sum(len(subs) for subs in self._subscribers.values()),
            "commands": list(self._running_commands.keys())
        }

# Global Hive Mind Instance
hive_mind = CommandLock()

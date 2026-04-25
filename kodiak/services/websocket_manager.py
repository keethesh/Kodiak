"""
WebSocket Manager Compatibility Shim

This module provides backward compatibility for code that references
the old WebSocket-based event system. Since Kodiak is now CLI/TUI-first,
this manager is a no-op that silently drops WebSocket calls.

For actual event broadcasting, use kodiak.api.events.EventManager instead.
"""

from typing import Any, Dict
from loguru import logger


class NoOpWebSocketManager:
    """
    No-op WebSocket manager for backward compatibility.
    All methods are async no-ops that log and return silently.
    """
    
    async def send_tool_update(
        self,
        scan_id: str,
        tool_name: str,
        status: str,
        data: Dict[str, Any] = None
    ):
        """No-op: Tool update events are handled by EventManager"""
        logger.debug(f"WebSocket no-op: tool_update for {tool_name} (status={status})")
    
    async def send_hive_mind_update(
        self,
        command: str,
        status: str,
        agent_id: str = None
    ):
        """No-op: Hive mind events are handled by EventManager"""
        logger.debug(f"WebSocket no-op: hive_mind_update (command={command}, status={status})")
    
    async def broadcast(
        self,
        event_type: str,
        data: Dict[str, Any] = None,
        scan_id: str = None
    ):
        """No-op: Broadcast events are handled by EventManager"""
        logger.debug(f"WebSocket no-op: broadcast (event_type={event_type})")
    
    async def send_agent_update(
        self,
        scan_id: str,
        agent_id: str,
        message: str,
        data: Dict[str, Any] = None
    ):
        """No-op: Agent updates are handled by EventManager"""
        logger.debug(f"WebSocket no-op: agent_update for {agent_id}")


# Global instance for backward compatibility
manager = NoOpWebSocketManager()

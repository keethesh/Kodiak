from typing import List, Dict, Any
from uuid import UUID
import json
import time

from fastapi import WebSocket
from loguru import logger

class ConnectionManager:
    def __init__(self):
        # scan_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # Global connections (not tied to specific scans)
        self.global_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket, scan_id: str = None):
        await websocket.accept()
        
        if scan_id:
            # Scan-specific connection
            if scan_id not in self.active_connections:
                self.active_connections[scan_id] = []
            self.active_connections[scan_id].append(websocket)
            logger.info(f"WebSocket client connected to scan {scan_id}")
        else:
            # Global connection
            self.global_connections.append(websocket)
            logger.info(f"WebSocket client connected globally")

    def disconnect(self, websocket: WebSocket, scan_id: str = None):
        if scan_id and scan_id in self.active_connections:
            if websocket in self.active_connections[scan_id]:
                self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]
            logger.info(f"WebSocket client disconnected from scan {scan_id}")
        elif websocket in self.global_connections:
            self.global_connections.remove(websocket)
            logger.info(f"WebSocket client disconnected globally")

    async def broadcast(self, scan_id: str, message: dict):
        """Broadcast message to all clients connected to a specific scan"""
        if scan_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send WS message to scan {scan_id}: {e}")
                    disconnected.append(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn, scan_id)

    async def broadcast_global(self, message: dict):
        """Broadcast message to all global connections"""
        disconnected = []
        for connection in self.global_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send global WS message: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_tool_update(self, scan_id: str, tool_name: str, status: str, data: Dict[str, Any] = None):
        """Send tool execution update"""
        message = {
            "type": "tool_update",
            "timestamp": time.time(),
            "scan_id": scan_id,
            "tool_name": tool_name,
            "status": status,  # "started", "completed", "failed"
            "data": data or {}
        }
        await self.broadcast(scan_id, message)

    async def send_agent_update(self, scan_id: str, agent_id: str, status: str, message_text: str = None):
        """Send agent status update"""
        message = {
            "type": "agent_update",
            "timestamp": time.time(),
            "scan_id": scan_id,
            "agent_id": agent_id,
            "status": status,  # "thinking", "executing", "completed", "error"
            "message": message_text
        }
        await self.broadcast(scan_id, message)

    async def send_finding_update(self, scan_id: str, finding: Dict[str, Any]):
        """Send new finding discovered"""
        message = {
            "type": "finding_update",
            "timestamp": time.time(),
            "scan_id": scan_id,
            "finding": finding
        }
        await self.broadcast(scan_id, message)

    async def send_session_update(self, session_type: str, session_id: str, status: str, data: Dict[str, Any] = None):
        """Send session update (terminal, python, proxy)"""
        message = {
            "type": "session_update",
            "timestamp": time.time(),
            "session_type": session_type,  # "terminal", "python", "proxy"
            "session_id": session_id,
            "status": status,  # "started", "active", "stopped"
            "data": data or {}
        }
        await self.broadcast_global(message)

    async def send_hive_mind_update(self, command: str, status: str, agent_id: str = None):
        """Send hive mind coordination update"""
        message = {
            "type": "hive_mind_update",
            "timestamp": time.time(),
            "command": command,
            "status": status,  # "locked", "executing", "completed", "cached"
            "agent_id": agent_id
        }
        await self.broadcast_global(message)

    async def send_log_message(self, scan_id: str, level: str, message_text: str, source: str = None):
        """Send log message"""
        message = {
            "type": "log_message",
            "timestamp": time.time(),
            "scan_id": scan_id,
            "level": level,  # "info", "warning", "error", "debug"
            "message": message_text,
            "source": source
        }
        await self.broadcast(scan_id, message)

    async def send_graph_update(self, scan_id: str, nodes: List[Dict[str, Any]] = None, edges: List[Dict[str, Any]] = None):
        """Send graph visualization update"""
        message = {
            "type": "graph_update",
            "timestamp": time.time(),
            "scan_id": scan_id,
            "nodes": nodes or [],
            "edges": edges or []
        }
        await self.broadcast(scan_id, message)

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            "total_scan_connections": sum(len(conns) for conns in self.active_connections.values()),
            "active_scans": len(self.active_connections),
            "global_connections": len(self.global_connections),
            "scan_details": {
                scan_id: len(conns) for scan_id, conns in self.active_connections.items()
            }
        }

manager = ConnectionManager()

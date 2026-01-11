from typing import List, Dict, Any
import asyncio
import json
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

class ExternalEvent:
    """
    Standard event structure for frontend.
    """
    def __init__(self, type: str, data: Dict[str, Any], project_id: str = None):
        self.type = type
        self.data = data
        self.project_id = project_id
    
    def to_json(self):
        return json.dumps({
            "type": self.type,
            "data": self.data,
            "project_id": self.project_id
        })

class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts events.
    """
    def __init__(self):
        # scan_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, scan_id: str):
        await websocket.accept()
        if scan_id not in self.active_connections:
            self.active_connections[scan_id] = []
        self.active_connections[scan_id].append(websocket)
        logger.info(f"Client connected to scan {scan_id}")

    def disconnect(self, websocket: WebSocket, scan_id: str):
        if scan_id in self.active_connections:
            if websocket in self.active_connections[scan_id]:
                self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]

    async def broadcast(self, message: str, scan_id: str):
        """
        Send raw message to all clients listening to scan_id.
        """
        if scan_id in self.active_connections:
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send to client: {e}")
                    # Could clean up dead connections here

    async def emit(self, event: ExternalEvent, scan_id: str):
        await self.broadcast(event.to_json(), scan_id)

# Global Manager
event_manager = ConnectionManager()

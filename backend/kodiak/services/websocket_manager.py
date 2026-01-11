from typing import List, Dict
from uuid import UUID

from fastapi import WebSocket
from loguru import logger

class ConnectionManager:
    def __init__(self):
        # scan_id -> list of websockets
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, scan_id: str):
        await websocket.accept()
        if scan_id not in self.active_connections:
            self.active_connections[scan_id] = []
        self.active_connections[scan_id].append(websocket)
        logger.info(f"WebSocket client connected to scan {scan_id}")

    def disconnect(self, websocket: WebSocket, scan_id: str):
        if scan_id in self.active_connections:
            if websocket in self.active_connections[scan_id]:
                self.active_connections[scan_id].remove(websocket)
            if not self.active_connections[scan_id]:
                del self.active_connections[scan_id]
        logger.info(f"WebSocket client disconnected from scan {scan_id}")

    async def broadcast(self, scan_id: str, message: dict):
        if scan_id in self.active_connections:
            for connection in self.active_connections[scan_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send WS message: {e}")
                    # Cleanup could happen here, but disconnect usually handles it

manager = ConnectionManager()

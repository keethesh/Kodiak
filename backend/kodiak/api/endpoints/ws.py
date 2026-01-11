from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from kodiak.services.websocket_manager import manager

router = APIRouter()

@router.websocket("/ws/{scan_id}")
async def websocket_endpoint(websocket: WebSocket, scan_id: str):
    await manager.connect(websocket, scan_id)
    try:
        while True:
            # We just listen for now, maybe handle ping/pong or client commands
            data = await websocket.receive_text()
            # Echo or process (optional)
    except WebSocketDisconnect:
        manager.disconnect(websocket, scan_id)

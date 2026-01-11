from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from kodiak.services.websocket_manager import manager
import json

router = APIRouter()

@router.websocket("/ws/{scan_id}")
async def websocket_endpoint(websocket: WebSocket, scan_id: str):
    """WebSocket endpoint for scan-specific updates"""
    await manager.connect(websocket, scan_id)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "scan_id": scan_id,
            "message": f"Connected to scan {scan_id}"
        })
        
        while True:
            # Listen for client messages (ping/pong, commands, etc.)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "request_status":
                    # Send current scan status
                    await websocket.send_json({
                        "type": "status_response",
                        "scan_id": scan_id,
                        "status": "active"  # This would come from actual scan state
                    })
                
            except json.JSONDecodeError:
                # Handle non-JSON messages (like ping frames)
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, scan_id)

@router.websocket("/ws")
async def global_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for global updates (sessions, hive mind, etc.)"""
    await manager.connect(websocket)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "global_connection_established",
            "message": "Connected to global updates"
        })
        
        while True:
            # Listen for client messages
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "request_stats":
                    # Send connection statistics
                    stats = manager.get_connection_stats()
                    await websocket.send_json({
                        "type": "stats_response",
                        "stats": stats
                    })
                
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

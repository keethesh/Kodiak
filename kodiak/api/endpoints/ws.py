from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from kodiak.services.websocket_manager import manager
import json

router = APIRouter()

def get_event_manager():
    """Dependency to get EventManager instance"""
    from main import get_event_manager
    return get_event_manager()

def get_tool_inventory():
    """Dependency to get ToolInventory instance"""
    from main import get_tool_inventory
    return get_tool_inventory()

@router.websocket("/ws/{scan_id}")
async def websocket_endpoint(websocket: WebSocket, scan_id: str):
    """WebSocket endpoint for scan-specific updates"""
    await manager.connect(websocket, scan_id)
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "scan_id": scan_id,
            "message": f"Connected to scan {scan_id}",
            "event_manager_available": get_event_manager() is not None,
            "tools_available": len(get_tool_inventory().list_tools()) if get_tool_inventory() else 0
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
                        "status": "active",  # This would come from actual scan state
                        "event_manager_status": "active" if get_event_manager() else "inactive"
                    })
                elif message.get("type") == "request_tools":
                    # Send available tools
                    tool_inventory = get_tool_inventory()
                    tools = tool_inventory.list_tools() if tool_inventory else {}
                    await websocket.send_json({
                        "type": "tools_response",
                        "scan_id": scan_id,
                        "tools": tools
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
            "message": "Connected to global updates",
            "event_manager_available": get_event_manager() is not None,
            "tools_available": len(get_tool_inventory().list_tools()) if get_tool_inventory() else 0
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
                    
                    # Add EventManager and ToolInventory stats
                    event_manager = get_event_manager()
                    tool_inventory = get_tool_inventory()
                    
                    stats.update({
                        "event_manager_active": event_manager is not None,
                        "tools_registered": len(tool_inventory.list_tools()) if tool_inventory else 0
                    })
                    
                    # Add Hive Mind stats if available
                    try:
                        from kodiak.core.hive_mind import hive_mind
                        stats.update({
                            "hive_mind_stats": hive_mind.get_stats()
                        })
                    except Exception:
                        pass
                    
                    await websocket.send_json({
                        "type": "stats_response",
                        "stats": stats
                    })
                
            except json.JSONDecodeError:
                pass
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)

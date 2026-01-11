from typing import List, Dict, Any, Optional
import asyncio
import json
import time
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

# Import the existing WebSocketManager
from kodiak.services.websocket_manager import manager as websocket_manager
from kodiak.core.error_handling import (
    ErrorHandler, EventBroadcastingError, handle_errors, ErrorCategory
)

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

class EventManager:
    """
    Unified event manager for tool execution events.
    Integrates with the existing WebSocketManager for client notifications.
    """
    def __init__(self, websocket_manager):
        self.websocket_manager = websocket_manager
        logger.info("EventManager initialized")
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_tool_start(self, tool_name: str, target: str, agent_id: str, scan_id: str = None):
        """Broadcast tool execution start event"""
        try:
            logger.info(f"Tool {tool_name} started by agent {agent_id} on target {target}")
            
            if scan_id:
                await self.websocket_manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=tool_name,
                    status="started",
                    data={
                        "target": target,
                        "agent_id": agent_id,
                        "timestamp": time.time()
                    }
                )
            
            # Also send agent update
            if scan_id:
                await self.websocket_manager.send_agent_update(
                    scan_id=scan_id,
                    agent_id=agent_id,
                    status="executing",
                    message_text=f"Executing {tool_name} on {target}"
                )
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit tool start event for {tool_name}",
                event_type="tool_start",
                details={
                    "tool_name": tool_name,
                    "target": target,
                    "agent_id": agent_id,
                    "scan_id": scan_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_tool_progress(self, tool_name: str, progress: dict, scan_id: str = None):
        """Broadcast tool execution progress"""
        try:
            logger.debug(f"Tool {tool_name} progress: {progress}")
            
            if scan_id:
                await self.websocket_manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=tool_name,
                    status="progress",
                    data={
                        "progress": progress,
                        "timestamp": time.time()
                    }
                )
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit tool progress event for {tool_name}",
                event_type="tool_progress",
                details={
                    "tool_name": tool_name,
                    "progress": progress,
                    "scan_id": scan_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_tool_complete(self, tool_name: str, result, scan_id: str = None):
        """Broadcast tool execution completion"""
        try:
            status = "completed" if result.success else "failed"
            logger.info(f"Tool {tool_name} {status}")
            
            if scan_id:
                await self.websocket_manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=tool_name,
                    status=status,
                    data={
                        "success": result.success,
                        "output": result.output if hasattr(result, 'output') else None,
                        "error": result.error if hasattr(result, 'error') else None,
                        "data": result.data if hasattr(result, 'data') else None,
                        "timestamp": time.time()
                    }
                )
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit tool complete event for {tool_name}",
                event_type="tool_complete",
                details={
                    "tool_name": tool_name,
                    "result_success": getattr(result, 'success', None),
                    "scan_id": scan_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_agent_thinking(self, agent_id: str, message: str, scan_id: str = None):
        """Broadcast agent thinking event"""
        try:
            logger.debug(f"Agent {agent_id} thinking: {message}")
            
            if scan_id:
                await self.websocket_manager.send_agent_update(
                    scan_id=scan_id,
                    agent_id=agent_id,
                    status="thinking",
                    message_text=message
                )
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit agent thinking event for {agent_id}",
                event_type="agent_thinking",
                details={
                    "agent_id": agent_id,
                    "message": message,
                    "scan_id": scan_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_scan_started(self, scan_id: str, scan_name: str, target: str, agent_id: str = None):
        """Broadcast scan started event"""
        try:
            logger.info(f"Scan {scan_id} started: {scan_name} targeting {target}")
            
            await self.websocket_manager.broadcast(scan_id, {
                "type": "scan_started",
                "timestamp": time.time(),
                "scan_id": scan_id,
                "scan_name": scan_name,
                "target": target,
                "agent_id": agent_id,
                "status": "running"
            })
            
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit scan started event for scan {scan_id}",
                event_type="scan_started",
                details={
                    "scan_id": scan_id,
                    "scan_name": scan_name,
                    "target": target,
                    "agent_id": agent_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_scan_completed(self, scan_id: str, scan_name: str, status: str, summary: Dict[str, Any] = None):
        """Broadcast scan completed event"""
        try:
            logger.info(f"Scan {scan_id} completed with status: {status}")
            
            await self.websocket_manager.broadcast(scan_id, {
                "type": "scan_completed",
                "timestamp": time.time(),
                "scan_id": scan_id,
                "scan_name": scan_name,
                "status": status,
                "summary": summary or {},
                "completed_at": time.time()
            })
            
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit scan completed event for scan {scan_id}",
                event_type="scan_completed",
                details={
                    "scan_id": scan_id,
                    "scan_name": scan_name,
                    "status": status,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_scan_failed(self, scan_id: str, scan_name: str, error: str, details: Dict[str, Any] = None):
        """Broadcast scan failed event"""
        try:
            logger.error(f"Scan {scan_id} failed: {error}")
            
            await self.websocket_manager.broadcast(scan_id, {
                "type": "scan_failed",
                "timestamp": time.time(),
                "scan_id": scan_id,
                "scan_name": scan_name,
                "status": "failed",
                "error": error,
                "details": details or {},
                "failed_at": time.time()
            })
            
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit scan failed event for scan {scan_id}",
                event_type="scan_failed",
                details={
                    "scan_id": scan_id,
                    "scan_name": scan_name,
                    "error": error,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_finding_discovered(self, scan_id: str, finding: Dict[str, Any], agent_id: str = None):
        """Broadcast finding discovered event"""
        try:
            logger.info(f"New finding discovered in scan {scan_id}: {finding.get('title', 'Unknown')}")
            
            await self.websocket_manager.broadcast(scan_id, {
                "type": "finding_discovered",
                "timestamp": time.time(),
                "scan_id": scan_id,
                "agent_id": agent_id,
                "finding": {
                    "id": finding.get("id"),
                    "title": finding.get("title", "Unknown Finding"),
                    "severity": finding.get("severity", "info"),
                    "description": finding.get("description", ""),
                    "target": finding.get("target"),
                    "evidence": finding.get("evidence", {}),
                    "discovered_at": time.time()
                }
            })
            
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit finding discovered event for scan {scan_id}",
                event_type="finding_discovered",
                details={
                    "scan_id": scan_id,
                    "finding": finding,
                    "agent_id": agent_id,
                    "original_error": str(e)
                }
            )
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_error(self, error: Dict[str, Any], scan_id: str = None):
        """Broadcast error event to clients"""
        try:
            logger.warning(f"Broadcasting error event: {error}")
            
            if scan_id:
                await self.websocket_manager.send_error_notification(
                    scan_id=scan_id,
                    error=error
                )
                
        except Exception as e:
            # Don't create recursive error handling for error events
            logger.error(f"Failed to emit error event: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get EventManager health status"""
        try:
            ws_stats = self.websocket_manager.get_connection_stats()
            return {
                "healthy": True,
                "websocket_manager": ws_stats.get("healthy", True),
                "total_connections": ws_stats.get("total_scan_connections", 0) + ws_stats.get("global_connections", 0)
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }

# Legacy ConnectionManager for backward compatibility
class ConnectionManager:
    """
    Legacy connection manager - kept for backward compatibility.
    Delegates to the new EventManager.
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

# Global instances
event_manager = EventManager(websocket_manager)
legacy_connection_manager = ConnectionManager()

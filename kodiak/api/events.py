"""
Event management for Kodiak TUI

Provides event broadcasting and management for the TUI interface.
Adapted from the original WebSocket-based event system.
"""

from typing import List, Dict, Any, Optional, Callable
import asyncio
import json
import time
from loguru import logger

from kodiak.core.error_handling import (
    ErrorHandler, EventBroadcastingError, handle_errors, ErrorCategory
)


class TUIEvent:
    """
    Standard event structure for TUI.
    """
    def __init__(self, type: str, data: Dict[str, Any], project_id: str = None):
        self.type = type
        self.data = data
        self.project_id = project_id
        self.timestamp = time.time()
    
    def to_dict(self):
        return {
            "type": self.type,
            "data": self.data,
            "project_id": self.project_id,
            "timestamp": self.timestamp
        }


class TUIEventManager:
    """
    Event manager for TUI interface.
    Manages event broadcasting to TUI components.
    """
    def __init__(self):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.scan_handlers: Dict[str, List[Callable]] = {}
        logger.info("TUIEventManager initialized")
    
    def subscribe(self, event_type: str, handler: Callable):
        """Subscribe to global events"""
        if event_type not in self.event_handlers:
            self.event_handlers[event_type] = []
        self.event_handlers[event_type].append(handler)
    
    def subscribe_scan(self, scan_id: str, handler: Callable):
        """Subscribe to events for a specific scan"""
        if scan_id not in self.scan_handlers:
            self.scan_handlers[scan_id] = []
        self.scan_handlers[scan_id].append(handler)
    
    def unsubscribe(self, event_type: str, handler: Callable):
        """Unsubscribe from global events"""
        if event_type in self.event_handlers:
            if handler in self.event_handlers[event_type]:
                self.event_handlers[event_type].remove(handler)
    
    def unsubscribe_scan(self, scan_id: str, handler: Callable):
        """Unsubscribe from scan events"""
        if scan_id in self.scan_handlers:
            if handler in self.scan_handlers[scan_id]:
                self.scan_handlers[scan_id].remove(handler)
    
    async def emit(self, event: TUIEvent, scan_id: str = None):
        """Emit an event to subscribers"""
        try:
            # Emit to global handlers
            if event.type in self.event_handlers:
                for handler in self.event_handlers[event.type]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"Error in event handler: {e}")
            
            # Emit to scan-specific handlers
            if scan_id and scan_id in self.scan_handlers:
                for handler in self.scan_handlers[scan_id]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(event)
                        else:
                            handler(event)
                    except Exception as e:
                        logger.error(f"Error in scan event handler: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to emit event {event.type}: {e}")
    
    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_tool_start(self, tool_name: str, target: str, agent_id: str, scan_id: str = None):
        """Broadcast tool execution start event"""
        try:
            logger.info(f"Tool {tool_name} started by agent {agent_id} on target {target}")
            
            event = TUIEvent("tool_start", {
                "tool_name": tool_name,
                "target": target,
                "agent_id": agent_id,
                "status": "started"
            })
            
            await self.emit(event, scan_id)
                
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
            
            event = TUIEvent("tool_progress", {
                "tool_name": tool_name,
                "progress": progress
            })
            
            await self.emit(event, scan_id)
                
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
            
            event = TUIEvent("tool_complete", {
                "tool_name": tool_name,
                "status": status,
                "success": result.success,
                "output": result.output if hasattr(result, 'output') else None,
                "error": result.error if hasattr(result, 'error') else None,
                "data": result.data if hasattr(result, 'data') else None
            })
            
            await self.emit(event, scan_id)
                
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
            
            event = TUIEvent("agent_thinking", {
                "agent_id": agent_id,
                "message": message,
                "status": "thinking"
            })
            
            await self.emit(event, scan_id)
                
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
            
            event = TUIEvent("scan_started", {
                "scan_id": scan_id,
                "scan_name": scan_name,
                "target": target,
                "agent_id": agent_id,
                "status": "running"
            })
            
            await self.emit(event, scan_id)
            
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
            
            event = TUIEvent("scan_completed", {
                "scan_id": scan_id,
                "scan_name": scan_name,
                "status": status,
                "summary": summary or {},
                "completed_at": time.time()
            })
            
            await self.emit(event, scan_id)
            
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
            
            event = TUIEvent("scan_failed", {
                "scan_id": scan_id,
                "scan_name": scan_name,
                "status": "failed",
                "error": error,
                "details": details or {},
                "failed_at": time.time()
            })
            
            await self.emit(event, scan_id)
            
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
            
            event = TUIEvent("finding_discovered", {
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
            
            await self.emit(event, scan_id)
            
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
        """Broadcast error event"""
        try:
            logger.warning(f"Broadcasting error event: {error}")
            
            event = TUIEvent("error", {
                "error": error
            })
            
            await self.emit(event, scan_id)
                
        except Exception as e:
            # Don't create recursive error handling for error events
            logger.error(f"Failed to emit error event: {e}")
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get EventManager health status"""
        try:
            return {
                "healthy": True,
                "global_handlers": len(self.event_handlers),
                "scan_handlers": len(self.scan_handlers),
                "total_handlers": sum(len(handlers) for handlers in self.event_handlers.values()) + 
                                sum(len(handlers) for handlers in self.scan_handlers.values())
            }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e)
            }


# Global instance
event_manager = TUIEventManager()


# Legacy compatibility - for any code that still imports the old names
class EventManager(TUIEventManager):
    """Legacy compatibility class"""
    pass


class ExternalEvent(TUIEvent):
    """Legacy compatibility class"""
    pass

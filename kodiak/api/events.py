"""
Event management for Kodiak TUI

Provides event broadcasting and management for the TUI interface.
Adapted from the original WebSocket-based event system.
"""

from typing import List, Dict, Any, Callable
import asyncio
import time
from loguru import logger

from kodiak.core.error_handling import (
    EventBroadcastingError, handle_errors, ErrorCategory
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
    def __init__(self, tui_bridge: Any = None):
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.scan_handlers: Dict[str, List[Callable]] = {}
        self.tui_bridge = tui_bridge
        logger.info("TUIEventManager initialized")

    async def _send_bridge_tool_update(
        self,
        scan_id: str | None,
        tool_name: str,
        status: str,
        data: Dict[str, Any] | None = None,
    ) -> None:
        if not scan_id or not self.tui_bridge or not hasattr(self.tui_bridge, "send_tool_update"):
            return
        await self.tui_bridge.send_tool_update(
            scan_id=scan_id,
            tool_name=tool_name,
            status=status,
            data=data or {},
        )

    async def _send_bridge_agent_update(
        self,
        scan_id: str | None,
        agent_id: str,
        message: str,
        data: Dict[str, Any] | None = None,
    ) -> None:
        if not scan_id or not self.tui_bridge or not hasattr(self.tui_bridge, "send_agent_update"):
            return
        await self.tui_bridge.send_agent_update(
            scan_id=scan_id,
            agent_id=agent_id,
            message=message,
            data=data or {},
        )

    async def _send_bridge_finding_update(self, scan_id: str | None, finding: Dict[str, Any]) -> None:
        if not scan_id or not self.tui_bridge or not hasattr(self.tui_bridge, "send_finding_update"):
            return
        await self.tui_bridge.send_finding_update(scan_id=scan_id, finding=finding)

    @staticmethod
    def _normalize_tool_result(result: Any) -> Dict[str, Any]:
        """Normalize different tool result shapes into one payload."""
        if hasattr(result, "success"):
            success = bool(getattr(result, "success"))
            status = "completed" if success else "failed"
            output = getattr(result, "output", None)
            error = getattr(result, "error", None)
            data = dict(getattr(result, "data", {}) or {})
            exit_code = getattr(result, "exit_code", None)
            timed_out = bool(getattr(result, "timed_out", False))
            if output is None and hasattr(result, "stdout"):
                output = getattr(result, "stdout", None)
            if error is None and hasattr(result, "stderr"):
                error = getattr(result, "stderr", None)
            if exit_code is not None:
                data.setdefault("exit_code", exit_code)
            if timed_out:
                data.setdefault("timed_out", timed_out)
                status = "timeout"
                success = False
            return {
                "success": success,
                "status": status,
                "output": output,
                "error": error,
                "data": data,
            }

        exit_code = getattr(result, "exit_code", None)
        timed_out = bool(getattr(result, "timed_out", False))
        stdout = getattr(result, "stdout", None)
        stderr = getattr(result, "stderr", None)

        if timed_out:
            return {
                "success": False,
                "status": "timeout",
                "output": stdout,
                "error": stderr or "Command timed out",
                "data": {
                    "exit_code": exit_code,
                    "timed_out": True,
                    "duration_seconds": getattr(result, "duration_seconds", None),
                },
            }

        success = bool(exit_code == 0)
        error = stderr if not success else None
        if not error and not success and exit_code is not None:
            error = f"Command exited with code {exit_code}"
        return {
            "success": success,
            "status": "completed" if success else "failed",
            "output": stdout,
            "error": error,
            "data": {
                "exit_code": exit_code,
                "timed_out": timed_out,
                "duration_seconds": getattr(result, "duration_seconds", None),
            },
        }
    
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
            if scan_id and event.project_id is None:
                event.project_id = scan_id

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
            
            await self._send_bridge_tool_update(
                scan_id,
                tool_name,
                "started",
                {"target": target, "agent_id": agent_id},
            )
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
            normalized = self._normalize_tool_result(result)
            status = normalized["status"]
             
            if not normalized["success"] and normalized["error"]:
                logger.error(f"Tool {tool_name} failed: {normalized['error']}")
            else:
                logger.info(f"Tool {tool_name} {status}")
             
            event = TUIEvent("tool_complete", {
                "tool_name": tool_name,
                "status": status,
                "success": normalized["success"],
                "output": normalized["output"],
                "error": normalized["error"],
                "data": normalized["data"],
            })
            
            await self._send_bridge_tool_update(
                scan_id,
                tool_name,
                status,
                {
                    "success": normalized["success"],
                    "output": normalized["output"],
                    "error": normalized["error"],
                    "data": normalized["data"],
                },
            )
            await self.emit(event, scan_id)
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit tool complete event for {tool_name}",
                event_type="tool_complete",
                details={
                    "tool_name": tool_name,
                    "result_success": normalized["success"] if 'normalized' in locals() else None,
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
            
            await self._send_bridge_agent_update(
                scan_id,
                agent_id,
                message,
                {"status": "thinking"},
            )
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
    async def emit_agent_thought(self, agent_id: str, thought: str, scan_id: str = None):
        """Broadcast agent's raw thinking/reasoning content"""
        try:
            logger.info(f"🤔 Agent {agent_id} thought:\n{thought}")
            
            event = TUIEvent("agent_thought", {
                "agent_id": agent_id,
                "thought": thought,
                "status": "thought_generated"
            })
            
            await self.emit(event, scan_id)
                
        except Exception as e:
            raise EventBroadcastingError(
                message=f"Failed to emit agent thought event for {agent_id}",
                event_type="agent_thought",
                details={
                    "agent_id": agent_id,
                    "thought": thought,
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
            
            await self._send_bridge_finding_update(scan_id, finding)
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

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_discovery(self, discovery: Dict[str, Any], scan_id: str = None):
        """Broadcast a discovery/finding payload."""
        try:
            await self._send_bridge_finding_update(scan_id, discovery)
            event = TUIEvent("discovery", {"discovery": discovery})
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit discovery event",
                event_type="discovery",
                details={"scan_id": scan_id, "original_error": str(e)},
            )

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_note_saved(self, category: str, target: str, preview: str, scan_id: str = None):
        """Broadcast engagement note saved event."""
        try:
            event = TUIEvent("note_saved", {
                "category": category,
                "target": target,
                "preview": preview,
            })
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit note_saved event",
                event_type="note_saved",
                details={"category": category, "target": target, "scan_id": scan_id, "original_error": str(e)},
            )

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_finding_saved(self, title: str, severity: str, target: str, scan_id: str = None):
        """Broadcast enriched finding saved event."""
        try:
            event = TUIEvent("finding_saved", {
                "title": title,
                "severity": severity,
                "target": target,
            })
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit finding_saved event",
                event_type="finding_saved",
                details={"title": title, "severity": severity, "scan_id": scan_id, "original_error": str(e)},
            )

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_phase_advanced(self, old_phase: str, new_phase: str, scan_id: str = None):
        """Broadcast scan phase advancement."""
        try:
            logger.info(f"📍 Phase advanced: {old_phase.upper()} → {new_phase.upper()}")
            event = TUIEvent("phase_advanced", {
                "old_phase": old_phase,
                "new_phase": new_phase,
            })
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit phase_advanced event",
                event_type="phase_advanced",
                details={"old_phase": old_phase, "new_phase": new_phase, "scan_id": scan_id, "original_error": str(e)},
            )

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_prior_knowledge_loaded(self, notes_count: int, findings_count: int, scan_id: str = None):
        """Broadcast prior engagement knowledge loaded."""
        try:
            logger.info(f"🧠 Prior knowledge loaded: {notes_count} notes, {findings_count} findings")
            event = TUIEvent("prior_knowledge_loaded", {
                "notes_count": notes_count,
                "findings_count": findings_count,
            })
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit prior_knowledge_loaded event",
                event_type="prior_knowledge_loaded",
                details={"notes_count": notes_count, "findings_count": findings_count, "scan_id": scan_id, "original_error": str(e)},
            )

    @handle_errors(ErrorCategory.EVENT_BROADCASTING, reraise=False)
    async def emit_llm_response(
        self,
        iteration: int,
        raw_json: str,
        input_tokens: int,
        output_tokens: int,
        thinking_tokens: int,
        cached_tokens: int,
        cost_usd: float,
        scan_id: str = None,
    ):
        """Broadcast a single LLM response with token usage (verbose/debug use)."""
        try:
            event = TUIEvent("llm_response", {
                "iteration": iteration,
                "raw_json": raw_json,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "thinking_tokens": thinking_tokens,
                "cached_tokens": cached_tokens,
                "cost_usd": cost_usd,
            })
            await self.emit(event, scan_id)
        except Exception as e:
            raise EventBroadcastingError(
                message="Failed to emit llm_response event",
                event_type="llm_response",
                details={"iteration": iteration, "scan_id": scan_id, "original_error": str(e)},
            )
    
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

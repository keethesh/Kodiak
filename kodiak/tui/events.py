"""
TUI Event System

This module provides Textual-compatible event classes for the Kodiak TUI.
"""

from typing import Any, Dict, Optional
from textual.message import Message
from datetime import datetime

from kodiak.tui.state import AgentState, ScanState, ProjectState, AgentStatus, ScanStatus


class KodiakMessage(Message):
    """Base class for all Kodiak TUI messages"""
    
    def __init__(self, data: Any = None, source: Optional[str] = None) -> None:
        super().__init__()
        self.data = data
        self.source = source
        self.timestamp = datetime.now()


class AgentStatusChanged(KodiakMessage):
    """Message sent when an agent's status changes"""
    
    def __init__(
        self, 
        scan_id: str, 
        agent_id: str, 
        old_status: AgentStatus, 
        new_status: AgentStatus,
        task: Optional[str] = None,
        agent: Optional[AgentState] = None
    ) -> None:
        super().__init__(
            data={
                "scan_id": scan_id,
                "agent_id": agent_id,
                "old_status": old_status,
                "new_status": new_status,
                "task": task,
                "agent": agent
            }
        )
        self.scan_id = scan_id
        self.agent_id = agent_id
        self.old_status = old_status
        self.new_status = new_status
        self.task = task
        self.agent = agent


class AssetDiscovered(KodiakMessage):
    """Message sent when a new asset/node is discovered"""
    
    def __init__(
        self, 
        scan_id: str, 
        node_type: str, 
        node_data: Dict[str, Any],
        agent_id: Optional[str] = None
    ) -> None:
        super().__init__(
            data={
                "scan_id": scan_id,
                "node_type": node_type,
                "node_data": node_data,
                "agent_id": agent_id
            }
        )
        self.scan_id = scan_id
        self.node_type = node_type
        self.node_data = node_data
        self.agent_id = agent_id


class FindingCreated(KodiakMessage):
    """Message sent when a new finding is created"""
    
    def __init__(
        self, 
        scan_id: str, 
        finding_id: str,
        title: str,
        severity: str,
        description: str,
        target: Optional[str] = None,
        agent_id: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(
            data={
                "scan_id": scan_id,
                "finding_id": finding_id,
                "title": title,
                "severity": severity,
                "description": description,
                "target": target,
                "agent_id": agent_id,
                "evidence": evidence or {}
            }
        )
        self.scan_id = scan_id
        self.finding_id = finding_id
        self.title = title
        self.severity = severity
        self.description = description
        self.target = target
        self.agent_id = agent_id
        self.evidence = evidence or {}


class ScanStatusChanged(KodiakMessage):
    """Message sent when a scan's status changes"""
    
    def __init__(
        self, 
        scan_id: str, 
        old_status: ScanStatus, 
        new_status: ScanStatus,
        scan_state: Optional[ScanState] = None
    ) -> None:
        super().__init__(
            data={
                "scan_id": scan_id,
                "old_status": old_status,
                "new_status": new_status,
                "scan_state": scan_state
            }
        )
        self.scan_id = scan_id
        self.old_status = old_status
        self.new_status = new_status
        self.scan_state = scan_state


class ProjectChanged(KodiakMessage):
    """Message sent when the current project changes"""
    
    def __init__(
        self, 
        project_id: Optional[str], 
        project_state: Optional[ProjectState] = None
    ) -> None:
        super().__init__(
            data={
                "project_id": project_id,
                "project_state": project_state
            }
        )
        self.project_id = project_id
        self.project_state = project_state


class ScanChanged(KodiakMessage):
    """Message sent when the current scan changes"""
    
    def __init__(
        self, 
        scan_id: Optional[str], 
        scan_state: Optional[ScanState] = None
    ) -> None:
        super().__init__(
            data={
                "scan_id": scan_id,
                "scan_state": scan_state
            }
        )
        self.scan_id = scan_id
        self.scan_state = scan_state


class ToolStarted(KodiakMessage):
    """Message sent when a tool starts execution"""
    
    def __init__(
        self, 
        tool_name: str, 
        target: str, 
        agent_id: str,
        scan_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(
            data={
                "tool_name": tool_name,
                "target": target,
                "agent_id": agent_id,
                "scan_id": scan_id,
                "parameters": parameters or {}
            }
        )
        self.tool_name = tool_name
        self.target = target
        self.agent_id = agent_id
        self.scan_id = scan_id
        self.parameters = parameters or {}


class ToolCompleted(KodiakMessage):
    """Message sent when a tool completes execution"""
    
    def __init__(
        self, 
        tool_name: str, 
        success: bool,
        agent_id: str,
        scan_id: Optional[str] = None,
        output: Optional[str] = None,
        error: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(
            data={
                "tool_name": tool_name,
                "success": success,
                "agent_id": agent_id,
                "scan_id": scan_id,
                "output": output,
                "error": error,
                "data": data or {}
            }
        )
        self.tool_name = tool_name
        self.success = success
        self.agent_id = agent_id
        self.scan_id = scan_id
        self.output = output
        self.error = error
        self.data = data or {}


class AgentThinking(KodiakMessage):
    """Message sent when an agent is thinking/reasoning"""
    
    def __init__(
        self, 
        agent_id: str, 
        message: str,
        scan_id: Optional[str] = None
    ) -> None:
        super().__init__(
            data={
                "agent_id": agent_id,
                "message": message,
                "scan_id": scan_id
            }
        )
        self.agent_id = agent_id
        self.message = message
        self.scan_id = scan_id


class LogMessage(KodiakMessage):
    """Message sent for log entries"""
    
    def __init__(
        self, 
        level: str, 
        message: str,
        source: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(
            data={
                "level": level,
                "message": message,
                "source": source,
                "details": details or {}
            },
            source=source
        )
        self.level = level
        self.message = message
        self.details = details or {}


class RefreshRequested(KodiakMessage):
    """Message sent when a refresh is requested"""
    
    def __init__(self, component: Optional[str] = None) -> None:
        super().__init__(
            data={"component": component}
        )
        self.component = component


class NavigationRequested(KodiakMessage):
    """Message sent when navigation is requested"""
    
    def __init__(
        self, 
        screen_name: str, 
        parameters: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(
            data={
                "screen_name": screen_name,
                "parameters": parameters or {}
            }
        )
        self.screen_name = screen_name
        self.parameters = parameters or {}


class ErrorOccurred(KodiakMessage):
    """Message sent when an error occurs"""
    
    def __init__(
        self, 
        error_type: str, 
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None
    ) -> None:
        super().__init__(
            data={
                "error_type": error_type,
                "error_message": error_message,
                "details": details or {}
            },
            source=source
        )
        self.error_type = error_type
        self.error_message = error_message
        self.details = details or {}


# Event type constants for easy reference
class EventTypes:
    """Constants for event types"""
    AGENT_STATUS_CHANGED = "agent_status_changed"
    ASSET_DISCOVERED = "asset_discovered"
    FINDING_CREATED = "finding_created"
    SCAN_STATUS_CHANGED = "scan_status_changed"
    PROJECT_CHANGED = "project_changed"
    SCAN_CHANGED = "scan_changed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    AGENT_THINKING = "agent_thinking"
    LOG_MESSAGE = "log_message"
    REFRESH_REQUESTED = "refresh_requested"
    NAVIGATION_REQUESTED = "navigation_requested"
    ERROR_OCCURRED = "error_occurred"


# Message class mapping for easy lookup
MESSAGE_CLASSES = {
    EventTypes.AGENT_STATUS_CHANGED: AgentStatusChanged,
    EventTypes.ASSET_DISCOVERED: AssetDiscovered,
    EventTypes.FINDING_CREATED: FindingCreated,
    EventTypes.SCAN_STATUS_CHANGED: ScanStatusChanged,
    EventTypes.PROJECT_CHANGED: ProjectChanged,
    EventTypes.SCAN_CHANGED: ScanChanged,
    EventTypes.TOOL_STARTED: ToolStarted,
    EventTypes.TOOL_COMPLETED: ToolCompleted,
    EventTypes.AGENT_THINKING: AgentThinking,
    EventTypes.LOG_MESSAGE: LogMessage,
    EventTypes.REFRESH_REQUESTED: RefreshRequested,
    EventTypes.NAVIGATION_REQUESTED: NavigationRequested,
    EventTypes.ERROR_OCCURRED: ErrorOccurred,
}
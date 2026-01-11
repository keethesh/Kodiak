"""
TUI State Management

This module provides reactive state management for the Kodiak TUI.
"""

from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime
from loguru import logger

from kodiak.database.models import Project, ScanJob, Finding, Node


class AgentStatus(str, Enum):
    """Agent status enumeration"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ScanStatus(str, Enum):
    """Scan status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentState:
    """State for a single agent"""
    id: str
    name: str
    status: AgentStatus = AgentStatus.IDLE
    current_task: Optional[str] = None
    last_activity: Optional[datetime] = None
    message_count: int = 0
    findings_count: int = 0
    tools_used: List[str] = field(default_factory=list)
    
    def update_status(self, status: AgentStatus, task: Optional[str] = None):
        """Update agent status"""
        self.status = status
        if task:
            self.current_task = task
        self.last_activity = datetime.now()


@dataclass
class ProjectState:
    """State for a project"""
    id: str
    name: str
    description: str
    target: str
    created_at: datetime
    updated_at: datetime
    scan_count: int = 0
    finding_count: int = 0
    last_scan_status: Optional[ScanStatus] = None


@dataclass
class ScanState:
    """State for a scan"""
    id: str
    project_id: str
    name: str
    target: str
    status: ScanStatus
    agent_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    agents: Dict[str, AgentState] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    nodes: List[Node] = field(default_factory=list)
    
    def get_agent_by_id(self, agent_id: str) -> Optional[AgentState]:
        """Get agent by ID"""
        return self.agents.get(agent_id)
    
    def add_agent(self, agent: AgentState):
        """Add an agent to the scan"""
        self.agents[agent.id] = agent
    
    def update_agent_status(self, agent_id: str, status: AgentStatus, task: Optional[str] = None):
        """Update agent status"""
        if agent_id in self.agents:
            self.agents[agent_id].update_status(status, task)
    
    def add_finding(self, finding: Finding):
        """Add a finding to the scan"""
        self.findings.append(finding)
    
    def add_node(self, node: Node):
        """Add a node to the scan"""
        self.nodes.append(node)


class StateChangeEvent:
    """Event for state changes"""
    def __init__(self, event_type: str, data: Any, source: Optional[str] = None):
        self.event_type = event_type
        self.data = data
        self.source = source
        self.timestamp = datetime.now()


class AppState:
    """
    Main application state manager
    
    Provides reactive state management with event notifications.
    """
    
    def __init__(self):
        self.projects: Dict[str, ProjectState] = {}
        self.scans: Dict[str, ScanState] = {}
        self.current_project_id: Optional[str] = None
        self.current_scan_id: Optional[str] = None
        
        # Event system
        self._listeners: Dict[str, List[Callable]] = {}
        self._global_listeners: List[Callable] = []
        
        logger.info("AppState initialized")
    
    # Event system methods
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to specific event type"""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)
    
    def subscribe_all(self, callback: Callable):
        """Subscribe to all events"""
        self._global_listeners.append(callback)
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from specific event type"""
        if event_type in self._listeners:
            if callback in self._listeners[event_type]:
                self._listeners[event_type].remove(callback)
    
    def unsubscribe_all(self, callback: Callable):
        """Unsubscribe from all events"""
        if callback in self._global_listeners:
            self._global_listeners.remove(callback)
    
    def emit(self, event_type: str, data: Any, source: Optional[str] = None):
        """Emit an event to all subscribers"""
        event = StateChangeEvent(event_type, data, source)
        
        # Notify specific listeners
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(event))
                    else:
                        callback(event)
                except Exception as e:
                    logger.error(f"Error in event callback: {e}")
        
        # Notify global listeners
        for callback in self._global_listeners:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in global event callback: {e}")
    
    # Project management
    def add_project(self, project: Project):
        """Add a project to state"""
        project_state = ProjectState(
            id=str(project.id),
            name=project.name,
            description=project.description or "",
            target=project.target or "",
            created_at=project.created_at,
            updated_at=project.updated_at
        )
        self.projects[project_state.id] = project_state
        self.emit("project_added", project_state)
    
    def update_project(self, project: Project):
        """Update a project in state"""
        if str(project.id) in self.projects:
            project_state = self.projects[str(project.id)]
            project_state.name = project.name
            project_state.description = project.description or ""
            project_state.target = project.target or ""
            project_state.updated_at = project.updated_at
            self.emit("project_updated", project_state)
    
    def remove_project(self, project_id: str):
        """Remove a project from state"""
        if project_id in self.projects:
            project_state = self.projects.pop(project_id)
            self.emit("project_removed", project_state)
    
    def get_project(self, project_id: str) -> Optional[ProjectState]:
        """Get a project by ID"""
        return self.projects.get(project_id)
    
    def get_all_projects(self) -> List[ProjectState]:
        """Get all projects"""
        return list(self.projects.values())
    
    def set_current_project(self, project_id: Optional[str]):
        """Set the current project"""
        self.current_project_id = project_id
        self.emit("current_project_changed", project_id)
    
    # Scan management
    def add_scan(self, scan: ScanJob):
        """Add a scan to state"""
        scan_state = ScanState(
            id=str(scan.id),
            project_id=str(scan.project_id),
            name=scan.name,
            target=scan.target,
            status=ScanStatus(scan.status.value),
            agent_count=scan.agent_count or 1,
            created_at=scan.created_at,
            started_at=scan.started_at,
            completed_at=scan.completed_at
        )
        self.scans[scan_state.id] = scan_state
        self.emit("scan_added", scan_state)
    
    def update_scan_status(self, scan_id: str, status: ScanStatus):
        """Update scan status"""
        if scan_id in self.scans:
            scan_state = self.scans[scan_id]
            old_status = scan_state.status
            scan_state.status = status
            
            if status == ScanStatus.RUNNING and not scan_state.started_at:
                scan_state.started_at = datetime.now()
            elif status in [ScanStatus.COMPLETED, ScanStatus.FAILED, ScanStatus.CANCELLED]:
                scan_state.completed_at = datetime.now()
            
            self.emit("scan_status_changed", {
                "scan_id": scan_id,
                "old_status": old_status,
                "new_status": status,
                "scan_state": scan_state
            })
    
    def get_scan(self, scan_id: str) -> Optional[ScanState]:
        """Get a scan by ID"""
        return self.scans.get(scan_id)
    
    def get_scans_for_project(self, project_id: str) -> List[ScanState]:
        """Get all scans for a project"""
        return [scan for scan in self.scans.values() if scan.project_id == project_id]
    
    def set_current_scan(self, scan_id: Optional[str]):
        """Set the current scan"""
        self.current_scan_id = scan_id
        self.emit("current_scan_changed", scan_id)
    
    # Agent management
    def add_agent_to_scan(self, scan_id: str, agent_id: str, agent_name: str):
        """Add an agent to a scan"""
        if scan_id in self.scans:
            agent_state = AgentState(id=agent_id, name=agent_name)
            self.scans[scan_id].add_agent(agent_state)
            self.emit("agent_added", {
                "scan_id": scan_id,
                "agent": agent_state
            })
    
    def update_agent_status(self, scan_id: str, agent_id: str, status: AgentStatus, task: Optional[str] = None):
        """Update agent status"""
        if scan_id in self.scans:
            scan_state = self.scans[scan_id]
            if agent_id in scan_state.agents:
                old_status = scan_state.agents[agent_id].status
                scan_state.update_agent_status(agent_id, status, task)
                self.emit("agent_status_changed", {
                    "scan_id": scan_id,
                    "agent_id": agent_id,
                    "old_status": old_status,
                    "new_status": status,
                    "task": task,
                    "agent": scan_state.agents[agent_id]
                })
    
    def get_agent(self, scan_id: str, agent_id: str) -> Optional[AgentState]:
        """Get an agent by scan and agent ID"""
        if scan_id in self.scans:
            return self.scans[scan_id].get_agent_by_id(agent_id)
        return None
    
    # Finding management
    def add_finding(self, scan_id: str, finding: Finding):
        """Add a finding to a scan"""
        if scan_id in self.scans:
            self.scans[scan_id].add_finding(finding)
            self.emit("finding_added", {
                "scan_id": scan_id,
                "finding": finding
            })
    
    def get_findings_for_scan(self, scan_id: str) -> List[Finding]:
        """Get all findings for a scan"""
        if scan_id in self.scans:
            return self.scans[scan_id].findings
        return []
    
    # Node management (attack surface)
    def add_node(self, scan_id: str, node: Node):
        """Add a node to a scan"""
        if scan_id in self.scans:
            self.scans[scan_id].add_node(node)
            self.emit("node_added", {
                "scan_id": scan_id,
                "node": node
            })
    
    def get_nodes_for_scan(self, scan_id: str) -> List[Node]:
        """Get all nodes for a scan"""
        if scan_id in self.scans:
            return self.scans[scan_id].nodes
        return []
    
    # Utility methods
    def get_current_project(self) -> Optional[ProjectState]:
        """Get the current project"""
        if self.current_project_id:
            return self.get_project(self.current_project_id)
        return None
    
    def get_current_scan(self) -> Optional[ScanState]:
        """Get the current scan"""
        if self.current_scan_id:
            return self.get_scan(self.current_scan_id)
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get application statistics"""
        total_findings = sum(len(scan.findings) for scan in self.scans.values())
        active_scans = sum(1 for scan in self.scans.values() if scan.status == ScanStatus.RUNNING)
        
        return {
            "total_projects": len(self.projects),
            "total_scans": len(self.scans),
            "active_scans": active_scans,
            "total_findings": total_findings,
            "current_project_id": self.current_project_id,
            "current_scan_id": self.current_scan_id
        }


# Global state instance
app_state = AppState()
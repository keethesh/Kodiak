"""
Core Bridge for TUI

This module provides the bridge between the TUI and the core Kodiak functionality.
It handles database initialization, orchestrator integration, and event conversion.
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from loguru import logger

from kodiak.database.engine import init_db, get_session
from kodiak.database.crud import project as crud_project, scan_job as crud_scan
from kodiak.database.models import Project, ScanJob, Finding, Node
from kodiak.core.orchestrator import orchestrator
from kodiak.core.config import settings
from kodiak.api.events import event_manager as core_event_manager

from kodiak.tui.state import app_state, AgentStatus, ScanStatus
from kodiak.tui.events import (
    AgentStatusChanged, AssetDiscovered, FindingCreated, ScanStatusChanged,
    ToolStarted, ToolCompleted, AgentThinking, LogMessage, ErrorOccurred
)


class CoreBridge:
    """
    Bridge between TUI and core Kodiak functionality
    
    Handles:
    - Database initialization and management
    - Orchestrator integration
    - Event conversion between core events and TUI messages
    - State synchronization
    """
    
    def __init__(self, app):
        self.app = app
        self.initialized = False
        self._event_subscriptions = []
        logger.info("CoreBridge initialized")
    
    async def initialize(self):
        """Initialize the core bridge"""
        try:
            logger.info("Initializing CoreBridge...")
            
            # Initialize database
            await self._init_database()
            
            # Load initial data
            await self._load_initial_data()
            
            # Set up event subscriptions
            self._setup_event_subscriptions()
            
            self.initialized = True
            logger.info("CoreBridge initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize CoreBridge: {e}")
            raise
    
    async def shutdown(self):
        """Shutdown the core bridge"""
        try:
            logger.info("Shutting down CoreBridge...")
            
            # Clean up event subscriptions
            self._cleanup_event_subscriptions()
            
            # Stop orchestrator if running
            # TODO: Add orchestrator shutdown if needed
            
            logger.info("CoreBridge shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during CoreBridge shutdown: {e}")
    
    async def _init_database(self):
        """Initialize the database"""
        try:
            logger.info("Initializing database...")
            await init_db()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    async def _load_initial_data(self):
        """Load initial data into state"""
        try:
            logger.info("Loading initial data...")
            
            async for session in get_session():
                # Load projects
                projects = await crud_project.get_all(session)
                for project in projects:
                    app_state.add_project(project)
                
                # Load scans
                scans = await crud_scan.get_all(session)
                for scan in scans:
                    app_state.add_scan(scan)
                
                logger.info(f"Loaded {len(projects)} projects and {len(scans)} scans")
                break
                
        except Exception as e:
            logger.error(f"Failed to load initial data: {e}")
            # Don't raise - we can continue without initial data
    
    def _setup_event_subscriptions(self):
        """Set up event subscriptions from core to TUI"""
        try:
            # Subscribe to core events and convert them to TUI messages
            core_event_manager.subscribe("tool_start", self._on_tool_start)
            core_event_manager.subscribe("tool_complete", self._on_tool_complete)
            core_event_manager.subscribe("agent_thinking", self._on_agent_thinking)
            core_event_manager.subscribe("scan_started", self._on_scan_started)
            core_event_manager.subscribe("scan_completed", self._on_scan_completed)
            core_event_manager.subscribe("scan_failed", self._on_scan_failed)
            core_event_manager.subscribe("finding_discovered", self._on_finding_discovered)
            core_event_manager.subscribe("error", self._on_error)
            
            logger.info("Event subscriptions set up")
            
        except Exception as e:
            logger.error(f"Failed to set up event subscriptions: {e}")
    
    def _cleanup_event_subscriptions(self):
        """Clean up event subscriptions"""
        try:
            # Unsubscribe from core events
            core_event_manager.unsubscribe("tool_start", self._on_tool_start)
            core_event_manager.unsubscribe("tool_complete", self._on_tool_complete)
            core_event_manager.unsubscribe("agent_thinking", self._on_agent_thinking)
            core_event_manager.unsubscribe("scan_started", self._on_scan_started)
            core_event_manager.unsubscribe("scan_completed", self._on_scan_completed)
            core_event_manager.unsubscribe("scan_failed", self._on_scan_failed)
            core_event_manager.unsubscribe("finding_discovered", self._on_finding_discovered)
            core_event_manager.unsubscribe("error", self._on_error)
            
            logger.info("Event subscriptions cleaned up")
            
        except Exception as e:
            logger.error(f"Failed to clean up event subscriptions: {e}")
    
    # Event handlers - convert core events to TUI messages
    async def _on_tool_start(self, event):
        """Handle tool start event from core"""
        try:
            data = event.data
            tool_name = data.get("tool_name")
            target = data.get("target")
            agent_id = data.get("agent_id")
            scan_id = data.get("scan_id")
            
            # Update state
            if scan_id and agent_id:
                app_state.update_agent_status(scan_id, agent_id, AgentStatus.EXECUTING, f"Running {tool_name}")
            
            # Send TUI message
            message = ToolStarted(
                tool_name=tool_name,
                target=target,
                agent_id=agent_id,
                scan_id=scan_id
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling tool start event: {e}")
    
    async def _on_tool_complete(self, event):
        """Handle tool complete event from core"""
        try:
            data = event.data
            tool_name = data.get("tool_name")
            success = data.get("success", False)
            agent_id = data.get("agent_id")
            scan_id = data.get("scan_id")
            output = data.get("output")
            error = data.get("error")
            
            # Update state
            if scan_id and agent_id:
                status = AgentStatus.IDLE if success else AgentStatus.FAILED
                app_state.update_agent_status(scan_id, agent_id, status)
            
            # Send TUI message
            message = ToolCompleted(
                tool_name=tool_name,
                success=success,
                agent_id=agent_id,
                scan_id=scan_id,
                output=output,
                error=error
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling tool complete event: {e}")
    
    async def _on_agent_thinking(self, event):
        """Handle agent thinking event from core"""
        try:
            data = event.data
            agent_id = data.get("agent_id")
            message_text = data.get("message")
            scan_id = data.get("scan_id")
            
            # Update state
            if scan_id and agent_id:
                app_state.update_agent_status(scan_id, agent_id, AgentStatus.THINKING, message_text)
            
            # Send TUI message
            message = AgentThinking(
                agent_id=agent_id,
                message=message_text,
                scan_id=scan_id
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling agent thinking event: {e}")
    
    async def _on_scan_started(self, event):
        """Handle scan started event from core"""
        try:
            data = event.data
            scan_id = data.get("scan_id")
            
            # Update state
            if scan_id:
                app_state.update_scan_status(scan_id, ScanStatus.RUNNING)
            
            # Send TUI message
            message = ScanStatusChanged(
                scan_id=scan_id,
                old_status=ScanStatus.PENDING,
                new_status=ScanStatus.RUNNING
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling scan started event: {e}")
    
    async def _on_scan_completed(self, event):
        """Handle scan completed event from core"""
        try:
            data = event.data
            scan_id = data.get("scan_id")
            
            # Update state
            if scan_id:
                app_state.update_scan_status(scan_id, ScanStatus.COMPLETED)
            
            # Send TUI message
            message = ScanStatusChanged(
                scan_id=scan_id,
                old_status=ScanStatus.RUNNING,
                new_status=ScanStatus.COMPLETED
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling scan completed event: {e}")
    
    async def _on_scan_failed(self, event):
        """Handle scan failed event from core"""
        try:
            data = event.data
            scan_id = data.get("scan_id")
            error = data.get("error")
            
            # Update state
            if scan_id:
                app_state.update_scan_status(scan_id, ScanStatus.FAILED)
            
            # Send TUI message
            message = ScanStatusChanged(
                scan_id=scan_id,
                old_status=ScanStatus.RUNNING,
                new_status=ScanStatus.FAILED
            )
            self.app.post_message(message)
            
            # Also send error message
            error_message = ErrorOccurred(
                error_type="scan_failed",
                error_message=f"Scan {scan_id} failed: {error}",
                source="core_bridge"
            )
            self.app.post_message(error_message)
            
        except Exception as e:
            logger.error(f"Error handling scan failed event: {e}")
    
    async def _on_finding_discovered(self, event):
        """Handle finding discovered event from core"""
        try:
            data = event.data
            scan_id = data.get("scan_id")
            finding_data = data.get("finding", {})
            agent_id = data.get("agent_id")
            
            # Send TUI message
            message = FindingCreated(
                scan_id=scan_id,
                finding_id=finding_data.get("id", "unknown"),
                title=finding_data.get("title", "Unknown Finding"),
                severity=finding_data.get("severity", "info"),
                description=finding_data.get("description", ""),
                target=finding_data.get("target"),
                agent_id=agent_id,
                evidence=finding_data.get("evidence", {})
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling finding discovered event: {e}")
    
    async def _on_error(self, event):
        """Handle error event from core"""
        try:
            data = event.data
            error_info = data.get("error", {})
            
            # Send TUI message
            message = ErrorOccurred(
                error_type=error_info.get("type", "unknown"),
                error_message=error_info.get("message", "Unknown error"),
                details=error_info.get("details", {}),
                source="core"
            )
            self.app.post_message(message)
            
        except Exception as e:
            logger.error(f"Error handling error event: {e}")
    
    # Public API methods for TUI to interact with core
    async def create_project(self, name: str, description: str = "", target: str = "") -> Optional[str]:
        """Create a new project"""
        try:
            async for session in get_session():
                project = await crud_project.create(
                    session,
                    name=name,
                    description=description,
                    target=target
                )
                app_state.add_project(project)
                logger.info(f"Created project: {project.name} (ID: {project.id})")
                return str(project.id)
        except Exception as e:
            logger.error(f"Failed to create project: {e}")
            return None
    
    async def create_scan(
        self, 
        project_id: str, 
        name: str, 
        target: str, 
        agent_count: int = 1,
        instructions: str = ""
    ) -> Optional[str]:
        """Create a new scan"""
        try:
            async for session in get_session():
                scan = await crud_scan.create(
                    session,
                    project_id=int(project_id),
                    name=name,
                    target=target,
                    agent_count=agent_count,
                    instructions=instructions
                )
                app_state.add_scan(scan)
                logger.info(f"Created scan: {scan.name} (ID: {scan.id})")
                return str(scan.id)
        except Exception as e:
            logger.error(f"Failed to create scan: {e}")
            return None
    
    async def start_scan(self, scan_id: str) -> bool:
        """Start a scan"""
        try:
            # TODO: Integrate with orchestrator to actually start the scan
            logger.info(f"Starting scan: {scan_id}")
            
            # For now, just update the status
            app_state.update_scan_status(scan_id, ScanStatus.RUNNING)
            
            return True
        except Exception as e:
            logger.error(f"Failed to start scan: {e}")
            return False
    
    async def stop_scan(self, scan_id: str) -> bool:
        """Stop a scan"""
        try:
            # TODO: Integrate with orchestrator to actually stop the scan
            logger.info(f"Stopping scan: {scan_id}")
            
            # For now, just update the status
            app_state.update_scan_status(scan_id, ScanStatus.CANCELLED)
            
            return True
        except Exception as e:
            logger.error(f"Failed to stop scan: {e}")
            return False
    
    async def get_projects(self) -> List[Project]:
        """Get all projects from database"""
        try:
            async for session in get_session():
                projects = await crud_project.get_all(session)
                return projects
        except Exception as e:
            logger.error(f"Failed to get projects: {e}")
            return []
    
    async def get_scans_for_project(self, project_id: str) -> List[ScanJob]:
        """Get all scans for a project"""
        try:
            async for session in get_session():
                scans = await crud_scan.get_by_project_id(session, int(project_id))
                return scans
        except Exception as e:
            logger.error(f"Failed to get scans for project {project_id}: {e}")
            return []
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the core bridge"""
        return {
            "initialized": self.initialized,
            "database_connected": True,  # TODO: Add actual database health check
            "orchestrator_status": "ready",  # TODO: Add actual orchestrator status
            "event_subscriptions": len(self._event_subscriptions),
            "app_state_stats": app_state.get_stats()
        }


# Global bridge instance - will be initialized by the app
core_bridge: Optional[CoreBridge] = None


def get_core_bridge() -> Optional[CoreBridge]:
    """Get the global core bridge instance"""
    return core_bridge


def set_core_bridge(bridge: CoreBridge):
    """Set the global core bridge instance"""
    global core_bridge
    core_bridge = bridge
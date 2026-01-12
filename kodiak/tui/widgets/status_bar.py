"""
StatusBar Widget

A widget that displays app name, current context, and scan status.
Updates dynamically based on application state.
"""

from typing import Optional
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.app import ComposeResult

from kodiak.tui.state import app_state, ScanStatus, ProjectState, ScanState


class StatusBar(Widget):
    """
    Status bar widget that displays:
    - App name and version
    - Current project/scan context
    - Scan status and progress
    """
    
    DEFAULT_CSS = """
    StatusBar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
    }
    
    StatusBar > Horizontal {
        height: 1;
        align: center middle;
    }
    
    StatusBar .app-name {
        color: $accent;
        text-style: bold;
    }
    
    StatusBar .context {
        color: $text;
        margin-left: 2;
    }
    
    StatusBar .status {
        color: $success;
        margin-left: 2;
    }
    
    StatusBar .status-running {
        color: $warning;
        text-style: bold;
    }
    
    StatusBar .status-failed {
        color: $error;
        text-style: bold;
    }
    
    StatusBar .status-completed {
        color: $success;
        text-style: bold;
    }
    """
    
    # Reactive properties
    current_project: reactive[Optional[ProjectState]] = reactive(None)
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_name = "🐻 Kodiak"
        self.version = "v1.0.0"
        
        # Subscribe to state changes
        app_state.subscribe("current_project_changed", self._on_project_changed)
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("scan_status_changed", self._on_scan_status_changed)
    
    def compose(self) -> ComposeResult:
        """Compose the status bar layout"""
        with Horizontal():
            yield Static(f"{self.app_name} {self.version}", classes="app-name", id="app-name")
            yield Static("", id="context", classes="context")
            yield Static("", id="status", classes="status")
    
    def on_mount(self) -> None:
        """Initialize status bar when mounted"""
        self.current_project = app_state.get_current_project()
        self.current_scan = app_state.get_current_scan()
        self._update_display()
    
    def _on_project_changed(self, event):
        """Handle project change events"""
        self.current_project = app_state.get_current_project()
        self._update_display()
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        self.current_scan = app_state.get_current_scan()
        self._update_display()
    
    def _on_scan_status_changed(self, event):
        """Handle scan status change events"""
        if self.current_scan and event.data.get("scan_id") == self.current_scan.id:
            self.current_scan = event.data.get("scan_state", self.current_scan)
            self._update_display()
    
    def _update_display(self):
        """Update the status bar display"""
        context_widget = self.query_one("#context", Static)
        status_widget = self.query_one("#status", Static)
        
        # Update context
        context_text = self._build_context_text()
        context_widget.update(context_text)
        
        # Update status
        status_text, status_class = self._build_status_text()
        status_widget.update(status_text)
        status_widget.set_class(status_class, "status")
    
    def _build_context_text(self) -> str:
        """Build the context text showing current project/scan"""
        if not self.current_project:
            return "No project selected"
        
        context = f"📁 {self.current_project.name}"
        
        if self.current_scan:
            context += f" → 🔍 {self.current_scan.name}"
        
        return context
    
    def _build_status_text(self) -> tuple[str, str]:
        """Build the status text and CSS class"""
        if not self.current_scan:
            return "Ready", "status"
        
        status = self.current_scan.status
        agent_count = len(self.current_scan.agents)
        finding_count = len(self.current_scan.findings)
        
        if status == ScanStatus.RUNNING:
            active_agents = sum(1 for agent in self.current_scan.agents.values() 
                              if agent.status.value in ["executing", "thinking"])
            return f"🔄 Running ({active_agents}/{agent_count} agents, {finding_count} findings)", "status-running"
        
        elif status == ScanStatus.COMPLETED:
            return f"✅ Completed ({finding_count} findings)", "status-completed"
        
        elif status == ScanStatus.FAILED:
            return f"❌ Failed ({finding_count} findings)", "status-failed"
        
        elif status == ScanStatus.PAUSED:
            return f"⏸️ Paused ({finding_count} findings)", "status"
        
        elif status == ScanStatus.PENDING:
            return f"⏳ Pending ({agent_count} agents)", "status"
        
        else:
            return f"📊 {status.value.title()}", "status"
    
    def watch_current_project(self, project: Optional[ProjectState]) -> None:
        """React to current project changes"""
        self._update_display()
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        self._update_display()
    
    def set_context(self, project: Optional[ProjectState], scan: Optional[ScanState] = None):
        """Manually set the context (useful for testing)"""
        self.current_project = project
        self.current_scan = scan
        self._update_display()
    
    def refresh_status(self):
        """Force refresh the status display"""
        self.current_project = app_state.get_current_project()
        self.current_scan = app_state.get_current_scan()
        self._update_display()
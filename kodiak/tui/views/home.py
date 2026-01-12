"""
HomeScreen View

The main home screen displaying project list and recent activity.
Implements keyboard shortcuts for navigation and project management.
"""

from typing import Optional, List
from datetime import datetime
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Button
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.message import Message
from loguru import logger

from kodiak.tui.state import app_state, ProjectState, ScanState, ScanStatus
from kodiak.tui.widgets import StatusBar


class ProjectSelected(Message):
    """Message sent when a project is selected"""
    def __init__(self, project_id: str) -> None:
        super().__init__()
        self.project_id = project_id


class HomeScreen(Screen):
    """
    Home screen - project list and main navigation
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("n", "new_scan", "New Scan"),
        Binding("d", "delete_project", "Delete"),
        Binding("r", "resume_scan", "Resume"),
        Binding("enter", "select_project", "Select"),
        Binding("escape", "quit", "Quit"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    HomeScreen {
        layout: vertical;
    }
    
    #welcome-container {
        height: 3;
        align: center middle;
        background: $primary;
        margin-bottom: 1;
    }
    
    #welcome-text {
        text-align: center;
        text-style: bold;
    }
    
    #main-content {
        height: 1fr;
        margin: 0 1;
    }
    
    #projects-container {
        height: 2fr;
        border: solid $primary;
        margin-bottom: 1;
    }
    
    #projects-title {
        dock: top;
        height: 1;
        background: $primary;
        text-align: center;
        text-style: bold;
    }
    
    DataTable {
        height: 1fr;
    }
    
    #activity-container {
        height: 1fr;
        border: solid $primary;
    }
    
    #activity-title {
        dock: top;
        height: 1;
        background: $primary;
        text-align: center;
        text-style: bold;
    }
    
    #activity-content {
        height: 1fr;
        padding: 1;
    }
    
    #empty-message {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    
    .status-running { color: $warning; }
    .status-completed { color: $success; }
    .status-failed { color: $error; }
    .status-paused { color: $primary; }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_project_id: Optional[str] = None
    
    def compose(self) -> ComposeResult:
        """Compose the home screen layout"""
        yield Header()
        
        with Container(id="welcome-container"):
            yield Static("🐻 Welcome to Kodiak - LLM Penetration Testing Suite", id="welcome-text")
        
        with Vertical(id="main-content"):
            with Container(id="projects-container"):
                yield Static("Projects", id="projects-title")
                yield DataTable(id="projects-table")
            
            with Container(id="activity-container"):
                yield Static("Recent Activity", id="activity-title")
                yield Static("", id="activity-content")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the home screen"""
        self._setup_projects_table()
        self._load_projects()
        self._load_recent_activity()
        
        # Subscribe to state changes
        app_state.subscribe("project_added", self._on_project_changed)
        app_state.subscribe("project_updated", self._on_project_changed)
        app_state.subscribe("project_removed", self._on_project_changed)
        app_state.subscribe("scan_status_changed", self._on_scan_changed)
    
    def _setup_projects_table(self):
        """Set up the projects DataTable"""
        table = self.query_one("#projects-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        
        # Add columns
        table.add_column("Name", key="name", width=25)
        table.add_column("Target", key="target", width=30)
        table.add_column("Status", key="status", width=12)
        table.add_column("Findings", key="findings", width=10)
        table.add_column("Last Updated", key="updated", width=20)
    
    def _load_projects(self):
        """Load projects from state into the table"""
        table = self.query_one("#projects-table", DataTable)
        table.clear()
        
        projects = app_state.get_all_projects()
        
        if not projects:
            # Show empty message
            return
        
        for project in projects:
            # Get latest scan status for this project
            scans = app_state.get_scans_for_project(project.id)
            latest_scan = scans[-1] if scans else None
            
            status = "No scans"
            status_class = ""
            finding_count = 0
            
            if latest_scan:
                status = latest_scan.status.value.title()
                finding_count = len(latest_scan.findings)
                
                if latest_scan.status == ScanStatus.RUNNING:
                    status = f"🔄 {status}"
                    status_class = "status-running"
                elif latest_scan.status == ScanStatus.COMPLETED:
                    status = f"✅ {status}"
                    status_class = "status-completed"
                elif latest_scan.status == ScanStatus.FAILED:
                    status = f"❌ {status}"
                    status_class = "status-failed"
                elif latest_scan.status == ScanStatus.PAUSED:
                    status = f"⏸️ {status}"
                    status_class = "status-paused"
            
            # Format updated time
            updated = project.updated_at.strftime("%Y-%m-%d %H:%M")
            
            table.add_row(
                project.name,
                project.target or "N/A",
                status,
                str(finding_count),
                updated,
                key=project.id
            )
        
        # Select first row if available
        if projects:
            table.move_cursor(row=0)
            self.selected_project_id = projects[0].id
    
    def _load_recent_activity(self):
        """Load recent activity from all projects"""
        activity_content = self.query_one("#activity-content", Static)
        
        # Get recent scans across all projects
        all_scans: List[ScanState] = []
        for project in app_state.get_all_projects():
            scans = app_state.get_scans_for_project(project.id)
            all_scans.extend(scans)
        
        # Sort by created_at descending
        all_scans.sort(key=lambda s: s.created_at, reverse=True)
        
        # Take last 5
        recent_scans = all_scans[:5]
        
        if not recent_scans:
            activity_content.update("No recent activity. Press 'n' to create a new scan.")
            return
        
        # Build activity text
        activity_lines = []
        for scan in recent_scans:
            project = app_state.get_project(scan.project_id)
            project_name = project.name if project else "Unknown"
            
            status_icon = {
                ScanStatus.RUNNING: "🔄",
                ScanStatus.COMPLETED: "✅",
                ScanStatus.FAILED: "❌",
                ScanStatus.PAUSED: "⏸️",
                ScanStatus.PENDING: "⏳",
            }.get(scan.status, "❓")
            
            time_str = scan.created_at.strftime("%H:%M")
            activity_lines.append(
                f"{status_icon} [{time_str}] {project_name}: {scan.name} - {scan.status.value}"
            )
        
        activity_content.update("\n".join(activity_lines))
    
    def _on_project_changed(self, event):
        """Handle project change events"""
        self._load_projects()
        self._load_recent_activity()
    
    def _on_scan_changed(self, event):
        """Handle scan status change events"""
        self._load_projects()
        self._load_recent_activity()
    
    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the projects table"""
        if event.row_key:
            self.selected_project_id = str(event.row_key.value)
    
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Handle row highlight in the projects table"""
        if event.row_key:
            self.selected_project_id = str(event.row_key.value)
    
    def action_quit(self) -> None:
        """Quit the application"""
        self.app.exit()
    
    def action_new_scan(self) -> None:
        """Navigate to new scan screen"""
        from kodiak.tui.views.new_scan import NewScanScreen
        self.app.push_screen(NewScanScreen())
    
    def action_select_project(self) -> None:
        """Select the current project and navigate to mission control"""
        if self.selected_project_id:
            app_state.set_current_project(self.selected_project_id)
            
            # Get latest scan for this project
            scans = app_state.get_scans_for_project(self.selected_project_id)
            if scans:
                app_state.set_current_scan(scans[-1].id)
            
            from kodiak.tui.views.mission_control import MissionControlScreen
            self.app.push_screen(MissionControlScreen())
        else:
            self.notify("No project selected", severity="warning")
    
    def action_delete_project(self) -> None:
        """Delete the selected project (with confirmation)"""
        if not self.selected_project_id:
            self.notify("No project selected", severity="warning")
            return
        
        project = app_state.get_project(self.selected_project_id)
        if project:
            # TODO: Show confirmation dialog
            self.notify(f"Delete project '{project.name}'? (Not implemented yet)", severity="information")
    
    def action_resume_scan(self) -> None:
        """Resume a paused scan"""
        if not self.selected_project_id:
            self.notify("No project selected", severity="warning")
            return
        
        scans = app_state.get_scans_for_project(self.selected_project_id)
        if scans:
            latest_scan = scans[-1]
            if latest_scan.status == ScanStatus.PAUSED:
                # TODO: Implement resume functionality
                self.notify(f"Resuming scan '{latest_scan.name}'... (Not implemented yet)", severity="information")
            else:
                self.notify("Latest scan is not paused", severity="warning")
        else:
            self.notify("No scans for this project", severity="warning")
    
    def action_go_home(self) -> None:
        """Go to home screen (Global shortcut)"""
        # Already on home, just refresh
        self.refresh_data()
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def refresh_data(self):
        """Refresh all data on the screen"""
        self._load_projects()
        self._load_recent_activity()
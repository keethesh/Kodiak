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
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home"),
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
    
    #logo-container {
        height: auto;
        align: center middle;
        padding: 1 0;
        background: $surface;
    }
    
    #ascii-logo {
        text-align: center;
        color: $accent;
    }
    
    #tagline {
        text-align: center;
        color: $text-muted;
        text-style: italic;
        margin-bottom: 1;
    }
    
    #quick-actions {
        height: 3;
        align: center middle;
        margin-bottom: 1;
    }
    
    #quick-actions Button {
        margin: 0 1;
        min-width: 18;
    }
    
    #new-scan-btn {
        background: $accent;
        color: $background;
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
    
    #empty-state {
        height: 100%;
        align: center middle;
    }
    
    #empty-message {
        text-align: center;
        color: $text-muted;
        text-style: italic;
    }
    
    #empty-hint {
        text-align: center;
        color: $accent;
        margin-top: 1;
    }
    
    .status-running { color: $warning; }
    .status-completed { color: $success; }
    .status-failed { color: $error; }
    .status-paused { color: $primary; }
    """
    
    # ASCII Logo for Kodiak
    LOGO = """
╔═╗┌─┐┌┬┐┬┌─┐┬┌─
╠═╝│ │ │││├─┤├┴┐
╩  └─┘─┴┘┴┴ ┴┴ ┴
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.selected_project_id: Optional[str] = None
    
    def compose(self) -> ComposeResult:
        """Compose the home screen layout"""
        yield Header()
        
        # Logo section
        with Container(id="logo-container"):
            yield Static(self.LOGO.strip(), id="ascii-logo")
            yield Static("🐻 LLM-Powered Penetration Testing Suite", id="tagline")
        
        # Quick action buttons
        with Horizontal(id="quick-actions"):
            yield Button("🔍 New Scan", id="new-scan-btn", variant="success")
            yield Button("📊 View Findings", id="findings-btn", variant="default")
            yield Button("⚙️ Settings", id="settings-btn", variant="default")
        
        with Vertical(id="main-content"):
            with Container(id="projects-container"):
                yield Static("📁 Projects", id="projects-title")
                yield DataTable(id="projects-table")
            
            with Container(id="activity-container"):
                yield Static("📋 Recent Activity", id="activity-title")
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
        """Delete the selected project (Requirement 3.7)"""
        if not self.selected_project_id:
            self.notify("No project selected", severity="warning")
            return
        
        project = app_state.get_project(self.selected_project_id)
        if project:
            # For now, just remove from state (Requirement 3.7)
            app_state.remove_project(self.selected_project_id)
            self.notify(f"Deleted project '{project.name}'", severity="information")
            self.selected_project_id = None
            self.refresh_data()
    
    def action_resume_scan(self) -> None:
        """Resume a paused scan (Requirement 3.8)"""
        if not self.selected_project_id:
            self.notify("No project selected", severity="warning")
            return
        
        scans = app_state.get_scans_for_project(self.selected_project_id)
        if scans:
            latest_scan = scans[-1]
            if latest_scan.status == ScanStatus.PAUSED:
                app_state.update_scan_status(latest_scan.id, ScanStatus.RUNNING)
                self.notify(f"Resumed scan '{latest_scan.name}'", severity="information")
                self.refresh_data()
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
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "new-scan-btn":
            self.action_new_scan()
        elif button_id == "findings-btn":
            from kodiak.tui.views.findings import FindingsScreen
            self.app.push_screen(FindingsScreen())
        elif button_id == "settings-btn":
            from kodiak.tui.views.settings import SettingsScreen
            self.app.push_screen(SettingsScreen())
"""
MissionControlScreen View

Main dashboard showing agents, attack surface graph, and activity log.
Implements split layout with tab navigation between panels.
"""

from typing import Optional
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from loguru import logger

from kodiak.tui.state import app_state, ScanState, ScanStatus
from kodiak.tui.widgets import AgentPanel, GraphTree, ActivityLog, StatusBar


class MissionControlScreen(Screen):
    """
    Mission Control - main dashboard for monitoring scans
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home"),
        Binding("tab", "focus_next_panel", "Next Panel"),
        Binding("shift+tab", "focus_prev_panel", "Prev Panel"),
        Binding("g", "show_graph", "Graph"),
        Binding("f", "show_findings", "Findings"),
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("enter", "select_item", "Select"),
        Binding("escape", "go_home", "Back"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    MissionControlScreen {
        layout: vertical;
    }
    
    #status-bar {
        dock: top;
        height: 1;
        background: $primary;
    }
    
    #main-content {
        height: 1fr;
        margin: 0 1;
    }
    
    #left-panel {
        width: 1fr;
        height: 100%;
        margin-right: 1;
    }
    
    #right-panel {
        width: 2fr;
        height: 100%;
    }
    
    #agents-container {
        height: 1fr;
        margin-bottom: 1;
    }
    
    #graph-container {
        height: 1fr;
    }
    
    #activity-container {
        height: 100%;
    }
    
    .panel-title {
        dock: top;
        height: 1;
        background: $primary;
        text-align: center;
        text-style: bold;
    }
    
    #scan-info {
        dock: top;
        height: 2;
        background: $surface;
        padding: 0 1;
    }
    
    #scan-status {
        text-style: bold;
    }
    
    .status-running { color: $warning; }
    .status-completed { color: $success; }
    .status-failed { color: $error; }
    .status-paused { color: $primary; }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_panel = 0  # 0=agents, 1=graph, 2=activity
        self.panels = ["agents", "graph", "activity"]
    
    def compose(self) -> ComposeResult:
        """Compose the mission control layout"""
        yield Header()
        
        # Scan info bar
        with Container(id="scan-info"):
            yield Static("", id="scan-status")
        
        # Main content with split layout
        with Horizontal(id="main-content"):
            # Left panel - Agents
            with Vertical(id="left-panel"):
                with Container(id="agents-container"):
                    yield AgentPanel(id="agent-panel")
            
            # Right panel - Graph and Activity
            with Vertical(id="right-panel"):
                with Container(id="graph-container"):
                    yield GraphTree(id="graph-tree")
                
                with Container(id="activity-container"):
                    yield ActivityLog(id="activity-log")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the mission control screen"""
        self._update_scan_info()
        self._focus_panel(0)
        
        # Subscribe to state changes
        app_state.subscribe("scan_status_changed", self._on_scan_status_changed)
        app_state.subscribe("agent_status_changed", self._on_agent_changed)
        app_state.subscribe("finding_added", self._on_finding_added)
        app_state.subscribe("node_added", self._on_node_added)
        
        # Log that we're on mission control
        activity_log = self.query_one("#activity-log", ActivityLog)
        current_scan = app_state.get_current_scan()
        if current_scan:
            activity_log.add_log("INFO", f"Mission Control active for: {current_scan.name}", source="System")
    
    def _update_scan_info(self):
        """Update the scan info display"""
        scan_status = self.query_one("#scan-status", Static)
        
        current_scan = app_state.get_current_scan()
        current_project = app_state.get_current_project()
        
        if not current_scan or not current_project:
            scan_status.update("No scan selected")
            return
        
        # Build status text
        status = current_scan.status
        status_icon = {
            ScanStatus.RUNNING: "🔄",
            ScanStatus.COMPLETED: "✅",
            ScanStatus.FAILED: "❌",
            ScanStatus.PAUSED: "⏸️",
            ScanStatus.PENDING: "⏳",
        }.get(status, "❓")
        
        agent_count = len(current_scan.agents)
        finding_count = len(current_scan.findings)
        node_count = len(current_scan.nodes)
        
        info_text = (
            f"{status_icon} {current_project.name} → {current_scan.name} | "
            f"Status: {status.value.title()} | "
            f"Agents: {agent_count} | "
            f"Findings: {finding_count} | "
            f"Nodes: {node_count}"
        )
        
        scan_status.update(info_text)
        
        # Update CSS class based on status
        scan_status.remove_class("status-running", "status-completed", "status-failed", "status-paused")
        if status == ScanStatus.RUNNING:
            scan_status.add_class("status-running")
        elif status == ScanStatus.COMPLETED:
            scan_status.add_class("status-completed")
        elif status == ScanStatus.FAILED:
            scan_status.add_class("status-failed")
        elif status == ScanStatus.PAUSED:
            scan_status.add_class("status-paused")
    
    def _on_scan_status_changed(self, event):
        """Handle scan status changes"""
        self._update_scan_info()
        
        activity_log = self.query_one("#activity-log", ActivityLog)
        data = event.data
        new_status = data.get("new_status")
        if new_status:
            activity_log.add_log("INFO", f"Scan status changed to: {new_status.value}", source="System")
    
    def _on_agent_changed(self, event):
        """Handle agent status changes"""
        self._update_scan_info()
    
    def _on_finding_added(self, event):
        """Handle new findings"""
        self._update_scan_info()
        
        activity_log = self.query_one("#activity-log", ActivityLog)
        data = event.data
        finding = data.get("finding")
        if finding:
            activity_log.add_log(
                "SUCCESS", 
                f"New finding: {finding.title} ({finding.severity})", 
                source="System"
            )
    
    def _on_node_added(self, event):
        """Handle new nodes"""
        self._update_scan_info()
    
    def _focus_panel(self, index: int):
        """Focus a specific panel"""
        self.current_panel = index % len(self.panels)
        panel_name = self.panels[self.current_panel]
        
        if panel_name == "agents":
            self.query_one("#agent-panel", AgentPanel).focus()
        elif panel_name == "graph":
            self.query_one("#graph-tree", GraphTree).focus()
        elif panel_name == "activity":
            self.query_one("#activity-log", ActivityLog).focus()
    
    def action_quit(self) -> None:
        """Quit the application"""
        self.app.exit()
    
    def action_go_home(self) -> None:
        """Return to home screen"""
        self.app.pop_screen()
    
    def action_focus_next_panel(self) -> None:
        """Focus the next panel"""
        self._focus_panel(self.current_panel + 1)
    
    def action_focus_prev_panel(self) -> None:
        """Focus the previous panel"""
        self._focus_panel(self.current_panel - 1)
    
    def action_show_graph(self) -> None:
        """Show expanded graph view"""
        from kodiak.tui.views.graph import GraphScreen
        self.app.push_screen(GraphScreen())
    
    def action_show_findings(self) -> None:
        """Show findings view"""
        from kodiak.tui.views.findings import FindingsScreen
        self.app.push_screen(FindingsScreen())
    
    def action_toggle_pause(self) -> None:
        """Toggle pause/resume for the current scan"""
        current_scan = app_state.get_current_scan()
        if not current_scan:
            self.notify("No scan selected", severity="warning")
            return
        
        if current_scan.status == ScanStatus.RUNNING:
            app_state.update_scan_status(current_scan.id, ScanStatus.PAUSED)
            self.notify("Scan paused", severity="information")
        elif current_scan.status == ScanStatus.PAUSED:
            app_state.update_scan_status(current_scan.id, ScanStatus.RUNNING)
            self.notify("Scan resumed", severity="information")
        else:
            self.notify(f"Cannot pause/resume scan in {current_scan.status.value} state", severity="warning")
    
    def action_select_item(self) -> None:
        """Select the current item in the focused panel"""
        panel_name = self.panels[self.current_panel]
        
        if panel_name == "agents":
            agent_panel = self.query_one("#agent-panel", AgentPanel)
            agent = agent_panel.get_selected_agent()
            if agent:
                from kodiak.tui.views.agent_chat import AgentChatScreen
                self.app.push_screen(AgentChatScreen(agent_id=agent.id))
        elif panel_name == "graph":
            graph_tree = self.query_one("#graph-tree", GraphTree)
            node = graph_tree.get_selected_node()
            if node and node.node.type == "vulnerability":
                # Navigate to finding detail
                from kodiak.tui.views.finding_detail import FindingDetailScreen
                self.app.push_screen(FindingDetailScreen(node_id=node.id))
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def on_agent_selected(self, event) -> None:
        """Handle agent selection from AgentPanel"""
        from kodiak.tui.views.agent_chat import AgentChatScreen
        self.app.push_screen(AgentChatScreen(agent_id=event.agent_id))
    
    def on_node_selected(self, event) -> None:
        """Handle node selection from GraphTree"""
        node_data = event.node_data
        node = node_data.get("node")
        
        if node and node.type == "vulnerability":
            from kodiak.tui.views.finding_detail import FindingDetailScreen
            self.app.push_screen(FindingDetailScreen(node_id=event.node_id))
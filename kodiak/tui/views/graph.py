"""
GraphScreen View

Full-screen attack surface graph view with search and navigation.
"""

from typing import Optional
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, Input
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from loguru import logger

from kodiak.tui.state import app_state
from kodiak.tui.widgets import GraphTree


class GraphScreen(Screen):
    """
    Expanded Graph View - full-screen attack surface visualization
    
    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("escape", "go_back", "Back"),
        Binding("slash", "search", "Search"),
        Binding("e", "expand_all", "Expand All"),
        Binding("c", "collapse_all", "Collapse All"),
        Binding("enter", "select_node", "Select"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    GraphScreen {
        layout: vertical;
    }
    
    #graph-header {
        dock: top;
        height: 2;
        background: $primary;
        padding: 0 1;
    }
    
    #graph-title {
        text-style: bold;
        height: 1;
    }
    
    #graph-stats {
        height: 1;
        color: $text-muted;
    }
    
    #search-container {
        dock: top;
        height: 3;
        padding: 0 1;
        display: none;
    }
    
    #search-container.visible {
        display: block;
    }
    
    #search-input {
        height: 3;
    }
    
    #graph-container {
        height: 1fr;
        margin: 1;
    }
    
    #legend {
        dock: bottom;
        height: 2;
        background: $surface;
        padding: 0 1;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_visible = False
    
    def compose(self) -> ComposeResult:
        """Compose the graph screen layout"""
        yield Header()
        
        # Graph header
        with Container(id="graph-header"):
            yield Static("🌐 Attack Surface Graph", id="graph-title")
            yield Static("", id="graph-stats")
        
        # Search container (hidden by default)
        with Container(id="search-container"):
            yield Input(placeholder="Search nodes...", id="search-input")
        
        # Graph container
        with Container(id="graph-container"):
            yield GraphTree(id="graph-tree")
        
        # Legend
        yield Static(
            "🎯 Target  📡 Host  🔌 Port  ⚙️ Service  🌐 Endpoint  🔓 Vulnerability  "
            "| 🔴 Critical  🟠 High  🟡 Medium  🟢 Low",
            id="legend"
        )
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the graph screen"""
        self._update_stats()
        
        # Focus the graph tree
        graph_tree = self.query_one("#graph-tree", GraphTree)
        graph_tree.focus()
        
        # Subscribe to node changes
        app_state.subscribe("node_added", self._on_node_added)
    
    def _update_stats(self):
        """Update the graph statistics"""
        stats = self.query_one("#graph-stats", Static)
        
        graph_tree = self.query_one("#graph-tree", GraphTree)
        total_nodes = len(graph_tree.tree_nodes)
        vulnerabilities = graph_tree.find_vulnerabilities()
        severity_counts = graph_tree.get_vulnerability_count_by_severity()
        
        stats_text = f"Nodes: {total_nodes} | Vulnerabilities: {len(vulnerabilities)}"
        
        if severity_counts:
            severity_parts = []
            for severity in ["critical", "high", "medium", "low"]:
                if severity in severity_counts:
                    severity_parts.append(f"{severity.title()}: {severity_counts[severity]}")
            if severity_parts:
                stats_text += f" ({', '.join(severity_parts)})"
        
        stats.update(stats_text)
    
    def _on_node_added(self, event):
        """Handle new nodes"""
        self._update_stats()
    
    def action_quit(self) -> None:
        """Quit the application (Global shortcut)"""
        self.app.exit()
    
    def action_go_home(self) -> None:
        """Go to home screen (Global shortcut)"""
        # Pop all screens and go to home
        while len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        
        # If we're not on home, push home screen
        from kodiak.tui.views.home import HomeScreen
        if not isinstance(self.app.screen, HomeScreen):
            self.app.push_screen(HomeScreen())
    
    def action_show_help(self) -> None:
        """Show help overlay (Global shortcut)"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def action_go_back(self) -> None:
        """Return to mission control"""
        self.app.pop_screen()
    
    def action_search(self) -> None:
        """Toggle search mode"""
        search_container = self.query_one("#search-container", Container)
        
        if self.search_visible:
            search_container.remove_class("visible")
            self.search_visible = False
            self.query_one("#graph-tree", GraphTree).focus()
        else:
            search_container.add_class("visible")
            self.search_visible = True
            self.query_one("#search-input", Input).focus()
    
    def action_expand_all(self) -> None:
        """Expand all tree nodes"""
        graph_tree = self.query_one("#graph-tree", GraphTree)
        graph_tree.expand_all()
        self.notify("Expanded all nodes")
    
    def action_collapse_all(self) -> None:
        """Collapse all tree nodes"""
        graph_tree = self.query_one("#graph-tree", GraphTree)
        graph_tree.collapse_all()
        self.notify("Collapsed all nodes")
    
    def action_select_node(self) -> None:
        """Select the current node"""
        graph_tree = self.query_one("#graph-tree", GraphTree)
        node = graph_tree.get_selected_node()
        
        if node and node.node.type == "vulnerability":
            from kodiak.tui.views.finding_detail import FindingDetailScreen
            self.app.push_screen(FindingDetailScreen(node_id=node.id))
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle search input"""
        if event.input.id == "search-input":
            query = event.value.strip()
            if query:
                self._perform_search(query)
            else:
                self.action_search()  # Close search
    
    def _perform_search(self, query: str):
        """Perform search and highlight results"""
        graph_tree = self.query_one("#graph-tree", GraphTree)
        matches = graph_tree.search_nodes(query)
        
        if matches:
            self.notify(f"Found {len(matches)} matching nodes")
            # TODO: Highlight/navigate to first match
        else:
            self.notify(f"No nodes matching '{query}'", severity="warning")
    
    def on_node_selected(self, event) -> None:
        """Handle node selection from GraphTree"""
        node_data = event.node_data
        node = node_data.get("node")
        
        if node and node.type == "vulnerability":
            from kodiak.tui.views.finding_detail import FindingDetailScreen
            self.app.push_screen(FindingDetailScreen(node_id=event.node_id))
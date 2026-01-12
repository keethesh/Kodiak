"""
FindingsScreen View

Vulnerability report view showing findings grouped by severity.
Supports filtering and export functionality.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
- 9.1: Display summary count of findings by severity level
- 9.2: Group findings by severity: Critical, High, Medium, Low, Info
- 9.3: Display each finding with: title, location, discovering agent, timestamp
- 9.4: Navigate to Finding_Detail_View on Enter
- 9.5: Export findings to file (JSON, Markdown, or HTML) on 'e'
- 9.6: Support filtering by severity, type, or agent
- 9.7: Update in real-time as new findings are discovered
"""

from typing import Optional, List
import json
from datetime import datetime
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, Button, Input, Select
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from loguru import logger

from kodiak.tui.state import app_state
from kodiak.tui.widgets import FindingsList
from kodiak.tui.widgets.findings_list import FindingSelected


class FindingsScreen(Screen):
    """
    Findings View - vulnerability report
    
    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("escape", "go_back", "Back"),
        Binding("e", "export_findings", "Export"),
        Binding("1", "filter_critical", "Critical"),
        Binding("2", "filter_high", "High"),
        Binding("3", "filter_medium", "Medium"),
        Binding("4", "filter_low", "Low"),
        Binding("5", "filter_info", "Info"),
        Binding("0", "clear_filter", "All"),
        Binding("a", "cycle_agent_filter", "Agent"),
        Binding("t", "cycle_type_filter", "Type"),
        Binding("enter", "select_finding", "Details"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    FindingsScreen {
        layout: vertical;
    }
    
    #findings-header {
        dock: top;
        height: 4;
        background: $primary;
        padding: 0 1;
    }
    
    #findings-title {
        text-style: bold;
        height: 1;
    }
    
    #findings-summary {
        height: 1;
    }
    
    #filter-hint {
        height: 1;
        color: $text-muted;
    }
    
    #active-filters {
        height: 1;
        color: $accent;
    }
    
    #findings-container {
        height: 1fr;
        margin: 1;
    }
    
    #export-container {
        dock: bottom;
        height: 3;
        background: $surface;
        padding: 0 1;
        align: center middle;
    }
    
    .export-btn {
        margin-right: 1;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_severity_filter: Optional[str] = None
        self.current_agent_filter: Optional[str] = None
        self.current_type_filter: Optional[str] = None
        self._available_agents: List[str] = []
        self._available_types: List[str] = []
        self._agent_filter_index: int = -1
        self._type_filter_index: int = -1
    
    def compose(self) -> ComposeResult:
        """Compose the findings screen layout"""
        yield Header()
        
        # Findings header
        with Container(id="findings-header"):
            yield Static("🔓 Security Findings", id="findings-title")
            yield Static("", id="findings-summary")
            yield Static("Filter: 1-5=Severity 0=All | A=Agent T=Type | E=Export", id="filter-hint")
            yield Static("", id="active-filters")
        
        # Findings container
        with Container(id="findings-container"):
            yield FindingsList(id="findings-list")
        
        # Export buttons
        with Horizontal(id="export-container"):
            yield Button("Export JSON", id="export-json", classes="export-btn")
            yield Button("Export Markdown", id="export-md", classes="export-btn")
            yield Button("Export HTML", id="export-html", classes="export-btn")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the findings screen"""
        self._update_available_filters()
        self._update_summary()
        self._update_active_filters_display()
        
        # Focus the findings list
        findings_list = self.query_one("#findings-list", FindingsList)
        findings_list.focus()
        
        # Subscribe to finding changes
        app_state.subscribe("finding_added", self._on_finding_added)
    
    def _update_available_filters(self):
        """Update the list of available agents and types for filtering"""
        findings_list = self.query_one("#findings-list", FindingsList)
        findings = findings_list.findings
        
        # Collect unique agents
        agents = set()
        types = set()
        for finding in findings:
            # Get agent from evidence or properties
            agent = None
            if finding.evidence and isinstance(finding.evidence, dict):
                agent = finding.evidence.get("discovered_by") or finding.evidence.get("agent")
            if agent:
                agents.add(agent)
            
            # Get finding type from node or properties
            if finding.node and hasattr(finding.node, 'type'):
                types.add(finding.node.type)
            elif finding.evidence and isinstance(finding.evidence, dict):
                finding_type = finding.evidence.get("type") or finding.evidence.get("vulnerability_type")
                if finding_type:
                    types.add(finding_type)
        
        self._available_agents = sorted(list(agents))
        self._available_types = sorted(list(types))
    
    def _update_summary(self):
        """Update the findings summary"""
        summary = self.query_one("#findings-summary", Static)
        
        findings_list = self.query_one("#findings-list", FindingsList)
        total = findings_list.get_total_count()
        severity_counts = findings_list.get_severity_counts()
        
        summary_parts = [f"Total: {total}"]
        
        severity_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        
        for severity in ["critical", "high", "medium", "low", "info"]:
            if severity in severity_counts:
                icon = severity_icons.get(severity, "⚪")
                summary_parts.append(f"{icon} {severity.title()}: {severity_counts[severity]}")
        
        summary.update(" | ".join(summary_parts))
    
    def _update_active_filters_display(self):
        """Update the display of active filters"""
        active_filters = self.query_one("#active-filters", Static)
        
        filter_parts = []
        if self.current_severity_filter:
            filter_parts.append(f"Severity: {self.current_severity_filter.title()}")
        if self.current_agent_filter:
            filter_parts.append(f"Agent: {self.current_agent_filter}")
        if self.current_type_filter:
            filter_parts.append(f"Type: {self.current_type_filter}")
        
        if filter_parts:
            active_filters.update("Active Filters: " + " | ".join(filter_parts))
        else:
            active_filters.update("")
    
    def _on_finding_added(self, event):
        """Handle new findings"""
        self._update_available_filters()
        self._update_summary()
    
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
    
    def action_filter_critical(self) -> None:
        """Filter to show only critical findings"""
        self._apply_severity_filter("critical")
    
    def action_filter_high(self) -> None:
        """Filter to show only high findings"""
        self._apply_severity_filter("high")
    
    def action_filter_medium(self) -> None:
        """Filter to show only medium findings"""
        self._apply_severity_filter("medium")
    
    def action_filter_low(self) -> None:
        """Filter to show only low findings"""
        self._apply_severity_filter("low")
    
    def action_filter_info(self) -> None:
        """Filter to show only info findings"""
        self._apply_severity_filter("info")
    
    def action_clear_filter(self) -> None:
        """Clear all filters"""
        self.current_severity_filter = None
        self.current_agent_filter = None
        self.current_type_filter = None
        self._agent_filter_index = -1
        self._type_filter_index = -1
        
        findings_list = self.query_one("#findings-list", FindingsList)
        findings_list.clear_filter()
        findings_list.set_filter_agent(None)
        findings_list.set_filter_type(None)
        
        self._update_summary()
        self._update_active_filters_display()
        self.notify("Showing all findings")
    
    def _apply_severity_filter(self, severity: str):
        """Apply a severity filter"""
        self.current_severity_filter = severity
        findings_list = self.query_one("#findings-list", FindingsList)
        findings_list.set_filter_severity(severity)
        self._update_summary()
        self._update_active_filters_display()
        self.notify(f"Filtered to {severity} findings")
    
    def action_cycle_agent_filter(self) -> None:
        """Cycle through available agent filters"""
        if not self._available_agents:
            self.notify("No agents to filter by", severity="warning")
            return
        
        # Cycle through agents (including None to clear)
        self._agent_filter_index = (self._agent_filter_index + 1) % (len(self._available_agents) + 1)
        
        if self._agent_filter_index == len(self._available_agents):
            # Clear agent filter
            self.current_agent_filter = None
            findings_list = self.query_one("#findings-list", FindingsList)
            findings_list.set_filter_agent(None)
            self.notify("Agent filter cleared")
        else:
            # Apply agent filter
            agent = self._available_agents[self._agent_filter_index]
            self.current_agent_filter = agent
            findings_list = self.query_one("#findings-list", FindingsList)
            findings_list.set_filter_agent(agent)
            self.notify(f"Filtered to agent: {agent}")
        
        self._update_active_filters_display()
    
    def action_cycle_type_filter(self) -> None:
        """Cycle through available type filters"""
        if not self._available_types:
            self.notify("No types to filter by", severity="warning")
            return
        
        # Cycle through types (including None to clear)
        self._type_filter_index = (self._type_filter_index + 1) % (len(self._available_types) + 1)
        
        if self._type_filter_index == len(self._available_types):
            # Clear type filter
            self.current_type_filter = None
            findings_list = self.query_one("#findings-list", FindingsList)
            findings_list.set_filter_type(None)
            self.notify("Type filter cleared")
        else:
            # Apply type filter
            finding_type = self._available_types[self._type_filter_index]
            self.current_type_filter = finding_type
            findings_list = self.query_one("#findings-list", FindingsList)
            findings_list.set_filter_type(finding_type)
            self.notify(f"Filtered to type: {finding_type}")
        
        self._update_active_filters_display()
    
    def action_select_finding(self) -> None:
        """View details of selected finding (Requirement 9.4)"""
        findings_list = self.query_one("#findings-list", FindingsList)
        finding = findings_list.get_selected_finding()
        
        if finding:
            from kodiak.tui.views.finding_detail import FindingDetailScreen
            self.app.push_screen(FindingDetailScreen(finding_id=str(finding.id)))
        else:
            self.notify("No finding selected", severity="warning")
    
    def action_export_findings(self) -> None:
        """Export findings (default to JSON)"""
        self._export_json()
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle export button presses"""
        button_id = event.button.id
        
        if button_id == "export-json":
            self._export_json()
        elif button_id == "export-md":
            self._export_markdown()
        elif button_id == "export-html":
            self._export_html()
    
    def _export_json(self):
        """Export findings to JSON"""
        findings_list = self.query_one("#findings-list", FindingsList)
        findings = findings_list.findings
        
        if not findings:
            self.notify("No findings to export", severity="warning")
            return
        
        # Build export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_findings": len(findings),
            "findings": []
        }
        
        for finding in findings:
            # Get target from node or evidence
            target = self._get_finding_target(finding)
            # Get agent from evidence
            agent = self._get_finding_agent(finding)
            
            export_data["findings"].append({
                "id": str(finding.id),
                "title": finding.title,
                "severity": finding.severity,
                "target": target,
                "description": finding.description,
                "evidence": finding.evidence,
                "discovered_by": agent,
                "created_at": finding.created_at.isoformat() if finding.created_at else None,
            })
        
        # Save to file
        filename = f"kodiak_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(filename, 'w') as f:
                json.dump(export_data, f, indent=2)
            self.notify(f"Exported to {filename}", severity="information")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")
    
    def _get_finding_target(self, finding) -> str:
        """Get target from finding, node, or evidence"""
        if hasattr(finding, 'target') and finding.target:
            return finding.target
        if finding.node and hasattr(finding.node, 'name'):
            return finding.node.name
        if finding.evidence and isinstance(finding.evidence, dict):
            return finding.evidence.get("target") or finding.evidence.get("url") or "N/A"
        return "N/A"
    
    def _get_finding_agent(self, finding) -> str:
        """Get discovering agent from finding evidence"""
        if finding.evidence and isinstance(finding.evidence, dict):
            return finding.evidence.get("discovered_by") or finding.evidence.get("agent") or "Unknown"
        return "Unknown"
    
    def _export_markdown(self):
        """Export findings to Markdown"""
        findings_list = self.query_one("#findings-list", FindingsList)
        findings = findings_list.findings
        
        if not findings:
            self.notify("No findings to export", severity="warning")
            return
        
        # Build markdown content
        lines = [
            "# Kodiak Security Findings Report",
            f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"\nTotal Findings: {len(findings)}",
            "\n---\n"
        ]
        
        # Group by severity
        severity_order = ["critical", "high", "medium", "low", "info"]
        for severity in severity_order:
            severity_findings = [f for f in findings if (f.severity or "info").lower() == severity]
            if severity_findings:
                lines.append(f"\n## {severity.title()} ({len(severity_findings)})\n")
                
                for finding in severity_findings:
                    target = self._get_finding_target(finding)
                    agent = self._get_finding_agent(finding)
                    timestamp = finding.created_at.strftime("%Y-%m-%d %H:%M:%S") if finding.created_at else "N/A"
                    
                    lines.append(f"### {finding.title}\n")
                    lines.append(f"- **Target:** {target}")
                    lines.append(f"- **Discovered By:** {agent}")
                    lines.append(f"- **Timestamp:** {timestamp}")
                    lines.append(f"- **Description:** {finding.description or 'N/A'}")
                    if finding.evidence:
                        lines.append(f"- **Evidence:** {finding.evidence}")
                    lines.append("")
        
        # Save to file
        filename = f"kodiak_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        try:
            with open(filename, 'w') as f:
                f.write("\n".join(lines))
            self.notify(f"Exported to {filename}", severity="information")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")
    
    def _export_html(self):
        """Export findings to HTML"""
        findings_list = self.query_one("#findings-list", FindingsList)
        findings = findings_list.findings
        
        if not findings:
            self.notify("No findings to export", severity="warning")
            return
        
        # Build HTML content
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Kodiak Security Findings Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #333; }}
        .finding {{ border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .critical {{ border-left: 5px solid #dc3545; }}
        .high {{ border-left: 5px solid #fd7e14; }}
        .medium {{ border-left: 5px solid #ffc107; }}
        .low {{ border-left: 5px solid #28a745; }}
        .info {{ border-left: 5px solid #17a2b8; }}
        .severity {{ font-weight: bold; text-transform: uppercase; }}
        .meta {{ color: #666; font-size: 0.9em; margin-top: 5px; }}
    </style>
</head>
<body>
    <h1>🐻 Kodiak Security Findings Report</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Total Findings: {len(findings)}</p>
    <hr>
"""
        
        for finding in findings:
            severity = (finding.severity or "info").lower()
            target = self._get_finding_target(finding)
            agent = self._get_finding_agent(finding)
            timestamp = finding.created_at.strftime("%Y-%m-%d %H:%M:%S") if finding.created_at else "N/A"
            
            html += f"""
    <div class="finding {severity}">
        <h3>{finding.title}</h3>
        <p><span class="severity">{severity}</span></p>
        <p><strong>Target:</strong> {target}</p>
        <p><strong>Description:</strong> {finding.description or 'N/A'}</p>
        <p class="meta">Discovered by: {agent} | Time: {timestamp}</p>
    </div>
"""
        
        html += """
</body>
</html>
"""
        
        # Save to file
        filename = f"kodiak_findings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        try:
            with open(filename, 'w') as f:
                f.write(html)
            self.notify(f"Exported to {filename}", severity="information")
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")
    
    def on_finding_selected(self, event: FindingSelected) -> None:
        """Handle finding selection from FindingsList (Requirement 9.4)"""
        from kodiak.tui.views.finding_detail import FindingDetailScreen
        self.app.push_screen(FindingDetailScreen(finding_id=event.finding_id))
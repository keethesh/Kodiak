"""
FindingDetailScreen View

Detailed view of a single security finding with evidence and actions.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
- 10.1: Display vulnerability title and severity prominently
- 10.2: Display location information: URL, parameter, method
- 10.3: Display evidence: request/response data, payloads used
- 10.4: Display remediation recommendations
- 10.5: Copy proof-of-concept to clipboard on 'c'
- 10.6: Trigger re-test on 'r'
- 10.7: Return to previous view on Escape
"""

from typing import Optional
import json
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, Button, TextArea
from textual.containers import Vertical, Horizontal, Container, ScrollableContainer
from textual.binding import Binding
from loguru import logger

from kodiak.tui.state import app_state
from kodiak.database.models import Finding


class FindingDetailScreen(Screen):
    """
    Finding Detail View - complete vulnerability details
    
    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("escape", "go_back", "Back"),
        Binding("c", "copy_poc", "Copy PoC"),
        Binding("r", "retest", "Re-test"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    FindingDetailScreen {
        layout: vertical;
    }
    
    #detail-header {
        dock: top;
        height: 5;
        background: $primary;
        padding: 0 1;
    }
    
    #finding-title {
        text-style: bold;
        height: 2;
    }
    
    #finding-severity {
        height: 1;
    }
    
    #finding-meta {
        height: 1;
        color: $text-muted;
    }
    
    #detail-content {
        height: 1fr;
        margin: 1;
    }
    
    .section {
        margin-bottom: 1;
        border: solid $primary;
        padding: 1;
    }
    
    .section-title {
        text-style: bold;
        background: $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    
    .section-content {
        padding: 0 1;
    }
    
    .field-label {
        text-style: bold;
        color: $accent;
    }
    
    .field-value {
        margin-left: 2;
    }
    
    #evidence-area {
        height: auto;
        max-height: 15;
        border: solid $surface;
    }
    
    #action-container {
        dock: bottom;
        height: 3;
        background: $surface;
        padding: 0 1;
        align: center middle;
    }
    
    .action-btn {
        margin-right: 1;
    }
    
    .severity-critical {
        color: $error;
        text-style: bold;
    }
    
    .severity-high {
        color: #fd7e14;
        text-style: bold;
    }
    
    .severity-medium {
        color: $warning;
    }
    
    .severity-low {
        color: $success;
    }
    
    .severity-info {
        color: $primary;
    }
    """
    
    def __init__(self, finding_id: str, **kwargs):
        super().__init__(**kwargs)
        self.finding_id = finding_id
        self.finding: Optional[Finding] = None
    
    def compose(self) -> ComposeResult:
        """Compose the finding detail screen layout"""
        yield Header()
        
        # Detail header
        with Container(id="detail-header"):
            yield Static("Loading...", id="finding-title")
            yield Static("", id="finding-severity")
            yield Static("Press C to copy PoC | R to re-test | Escape to go back", id="finding-meta")
        
        # Scrollable content area
        with ScrollableContainer(id="detail-content"):
            # Location section (Requirement 10.2)
            with Vertical(classes="section", id="location-section"):
                yield Static("📍 Location", classes="section-title")
                yield Static("", id="location-content", classes="section-content")
            
            # Evidence section (Requirement 10.3)
            with Vertical(classes="section", id="evidence-section"):
                yield Static("🔍 Evidence", classes="section-title")
                yield Static("", id="evidence-content", classes="section-content")
            
            # Remediation section (Requirement 10.4)
            with Vertical(classes="section", id="remediation-section"):
                yield Static("🛡️ Remediation", classes="section-title")
                yield Static("", id="remediation-content", classes="section-content")
            
            # Additional details section
            with Vertical(classes="section", id="details-section"):
                yield Static("📋 Additional Details", classes="section-title")
                yield Static("", id="details-content", classes="section-content")
        
        # Action buttons
        with Horizontal(id="action-container"):
            yield Button("Copy PoC (C)", id="copy-poc-btn", classes="action-btn")
            yield Button("Re-test (R)", id="retest-btn", classes="action-btn")
            yield Button("Back (Esc)", id="back-btn", classes="action-btn")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the finding detail screen"""
        self._load_finding()
    
    def _load_finding(self):
        """Load the finding data"""
        # Try to find the finding in the current scan's findings
        current_scan = app_state.get_current_scan()
        if current_scan:
            for finding in current_scan.findings:
                if str(finding.id) == self.finding_id:
                    self.finding = finding
                    break
        
        if self.finding:
            self._display_finding()
        else:
            self._display_not_found()

    def _display_finding(self):
        """Display the finding details"""
        if not self.finding:
            return
        
        # Update title (Requirement 10.1)
        title = self.query_one("#finding-title", Static)
        title.update(f"🔓 {self.finding.title or 'Untitled Finding'}")
        
        # Update severity with color (Requirement 10.1)
        severity = self.query_one("#finding-severity", Static)
        severity_value = (self.finding.severity or "info").lower()
        severity_icon = self._get_severity_icon(severity_value)
        severity.update(f"Severity: {severity_icon} {severity_value.upper()}")
        severity.add_class(f"severity-{severity_value}")
        
        # Update location (Requirement 10.2)
        self._update_location_section()
        
        # Update evidence (Requirement 10.3)
        self._update_evidence_section()
        
        # Update remediation (Requirement 10.4)
        self._update_remediation_section()
        
        # Update additional details
        self._update_details_section()
    
    def _update_location_section(self):
        """Update the location section (Requirement 10.2)"""
        location_content = self.query_one("#location-content", Static)
        
        lines = []
        
        # Get target/URL
        target = self._get_finding_target()
        lines.append(f"URL/Target: {target}")
        
        # Get parameter if available
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            parameter = self.finding.evidence.get("parameter") or self.finding.evidence.get("param")
            if parameter:
                lines.append(f"Parameter: {parameter}")
            
            method = self.finding.evidence.get("method") or self.finding.evidence.get("http_method")
            if method:
                lines.append(f"Method: {method}")
            
            endpoint = self.finding.evidence.get("endpoint") or self.finding.evidence.get("path")
            if endpoint:
                lines.append(f"Endpoint: {endpoint}")
        
        # Get node info if available
        if self.finding.node:
            if hasattr(self.finding.node, 'type'):
                lines.append(f"Node Type: {self.finding.node.type}")
            if hasattr(self.finding.node, 'name'):
                lines.append(f"Node Name: {self.finding.node.name}")
        
        location_content.update("\n".join(lines) if lines else "No location information available")
    
    def _update_evidence_section(self):
        """Update the evidence section (Requirement 10.3)"""
        evidence_content = self.query_one("#evidence-content", Static)
        
        lines = []
        
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            # Request data
            request = self.finding.evidence.get("request")
            if request:
                lines.append("Request:")
                if isinstance(request, dict):
                    lines.append(f"  {json.dumps(request, indent=2)}")
                else:
                    lines.append(f"  {request}")
            
            # Response data
            response = self.finding.evidence.get("response")
            if response:
                lines.append("\nResponse:")
                if isinstance(response, dict):
                    lines.append(f"  {json.dumps(response, indent=2)}")
                else:
                    # Truncate long responses
                    response_str = str(response)
                    if len(response_str) > 500:
                        response_str = response_str[:500] + "... [truncated]"
                    lines.append(f"  {response_str}")
            
            # Payload
            payload = self.finding.evidence.get("payload") or self.finding.evidence.get("payloads")
            if payload:
                lines.append("\nPayload(s):")
                if isinstance(payload, list):
                    for p in payload:
                        lines.append(f"  • {p}")
                else:
                    lines.append(f"  {payload}")
            
            # Proof of concept
            poc = self.finding.evidence.get("poc") or self.finding.evidence.get("proof_of_concept")
            if poc:
                lines.append("\nProof of Concept:")
                lines.append(f"  {poc}")
            
            # Additional evidence fields
            for key, value in self.finding.evidence.items():
                if key not in ["request", "response", "payload", "payloads", "poc", 
                              "proof_of_concept", "target", "url", "parameter", "param",
                              "method", "http_method", "endpoint", "path", "discovered_by",
                              "agent", "type", "vulnerability_type"]:
                    lines.append(f"\n{key.replace('_', ' ').title()}:")
                    if isinstance(value, (dict, list)):
                        lines.append(f"  {json.dumps(value, indent=2)}")
                    else:
                        lines.append(f"  {value}")
        
        evidence_content.update("\n".join(lines) if lines else "No evidence available")
    
    def _update_remediation_section(self):
        """Update the remediation section (Requirement 10.4)"""
        remediation_content = self.query_one("#remediation-content", Static)
        
        if self.finding.remediation:
            remediation_content.update(self.finding.remediation)
        elif self.finding.evidence and isinstance(self.finding.evidence, dict):
            remediation = self.finding.evidence.get("remediation") or self.finding.evidence.get("recommendation")
            if remediation:
                remediation_content.update(remediation)
            else:
                remediation_content.update("No remediation recommendations available")
        else:
            remediation_content.update("No remediation recommendations available")
    
    def _update_details_section(self):
        """Update the additional details section"""
        details_content = self.query_one("#details-content", Static)
        
        lines = []
        
        # Description
        if self.finding.description:
            lines.append(f"Description: {self.finding.description}")
        
        # CVE ID
        if self.finding.cve_id:
            lines.append(f"CVE ID: {self.finding.cve_id}")
        
        # Discovered by
        agent = self._get_finding_agent()
        lines.append(f"Discovered By: {agent}")
        
        # Timestamp
        if self.finding.created_at:
            lines.append(f"Discovered At: {self.finding.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Finding ID
        lines.append(f"Finding ID: {self.finding_id}")
        
        details_content.update("\n".join(lines) if lines else "No additional details")
    
    def _display_not_found(self):
        """Display not found message"""
        title = self.query_one("#finding-title", Static)
        title.update("❌ Finding Not Found")
        
        severity = self.query_one("#finding-severity", Static)
        severity.update(f"Finding ID: {self.finding_id}")
        
        location_content = self.query_one("#location-content", Static)
        location_content.update("The requested finding could not be found.")
    
    def _get_finding_target(self) -> str:
        """Get target from finding, node, or evidence"""
        if hasattr(self.finding, 'target') and self.finding.target:
            return self.finding.target
        if self.finding.node and hasattr(self.finding.node, 'name'):
            return self.finding.node.name
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            return self.finding.evidence.get("target") or self.finding.evidence.get("url") or "N/A"
        return "N/A"
    
    def _get_finding_agent(self) -> str:
        """Get discovering agent from finding evidence"""
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            return self.finding.evidence.get("discovered_by") or self.finding.evidence.get("agent") or "Unknown"
        return "Unknown"
    
    def _get_severity_icon(self, severity: str) -> str:
        """Get the appropriate icon for severity"""
        severity_icons = {
            "critical": "🔴",
            "high": "🟠",
            "medium": "🟡",
            "low": "🟢",
            "info": "🔵",
        }
        return severity_icons.get(severity.lower(), "⚪")
    
    def _get_poc_text(self) -> str:
        """Get the proof-of-concept text for copying"""
        if not self.finding:
            return ""
        
        poc_parts = []
        
        # Title and severity
        poc_parts.append(f"# {self.finding.title}")
        poc_parts.append(f"Severity: {(self.finding.severity or 'info').upper()}")
        poc_parts.append("")
        
        # Target
        target = self._get_finding_target()
        poc_parts.append(f"Target: {target}")
        poc_parts.append("")
        
        # Evidence
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            # Payload
            payload = self.finding.evidence.get("payload") or self.finding.evidence.get("payloads")
            if payload:
                poc_parts.append("Payload:")
                if isinstance(payload, list):
                    for p in payload:
                        poc_parts.append(f"  {p}")
                else:
                    poc_parts.append(f"  {payload}")
                poc_parts.append("")
            
            # PoC
            poc = self.finding.evidence.get("poc") or self.finding.evidence.get("proof_of_concept")
            if poc:
                poc_parts.append("Proof of Concept:")
                poc_parts.append(poc)
                poc_parts.append("")
            
            # Request
            request = self.finding.evidence.get("request")
            if request:
                poc_parts.append("Request:")
                if isinstance(request, dict):
                    poc_parts.append(json.dumps(request, indent=2))
                else:
                    poc_parts.append(str(request))
                poc_parts.append("")
        
        # Description
        if self.finding.description:
            poc_parts.append("Description:")
            poc_parts.append(self.finding.description)
        
        return "\n".join(poc_parts)
    
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
        """Return to previous view (Requirement 10.7)"""
        self.app.pop_screen()
    
    def action_copy_poc(self) -> None:
        """Copy proof-of-concept to clipboard (Requirement 10.5)"""
        poc_text = self._get_poc_text()
        
        if poc_text:
            try:
                import pyperclip
                pyperclip.copy(poc_text)
                self.notify("Proof-of-concept copied to clipboard!", severity="information")
            except ImportError:
                # pyperclip not available, try alternative methods
                try:
                    import subprocess
                    # Try Windows clip command
                    process = subprocess.Popen(['clip'], stdin=subprocess.PIPE)
                    process.communicate(poc_text.encode('utf-8'))
                    self.notify("Proof-of-concept copied to clipboard!", severity="information")
                except Exception:
                    self.notify("Could not copy to clipboard. Install pyperclip for clipboard support.", severity="warning")
                    logger.warning("Clipboard copy failed - pyperclip not installed")
        else:
            self.notify("No proof-of-concept data available", severity="warning")
    
    def action_retest(self) -> None:
        """Trigger re-test of the vulnerability (Requirement 10.6)"""
        if not self.finding:
            self.notify("No finding to re-test", severity="warning")
            return
        
        # Emit a re-test event
        app_state.emit("retest_finding", {
            "finding_id": self.finding_id,
            "finding": self.finding,
            "target": self._get_finding_target()
        })
        
        self.notify(f"Re-test triggered for: {self.finding.title}", severity="information")
        logger.info(f"Re-test triggered for finding: {self.finding_id}")
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        try:
            from kodiak.tui.views.help import HelpScreen
            self.app.push_screen(HelpScreen())
        except ImportError:
            self.notify("Help screen not available", severity="warning")
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "copy-poc-btn":
            self.action_copy_poc()
        elif button_id == "retest-btn":
            self.action_retest()
        elif button_id == "back-btn":
            self.action_go_back()

"""
FindingsList Widget

A widget that displays findings grouped by severity with summary counts.
Supports filtering and color-coding by severity.
"""

from typing import List, Dict, Optional, Set
from textual.widget import Widget
from textual.widgets import ListView, ListItem, Static, Collapsible
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.message import Message

from kodiak.tui.state import app_state, ScanState
from kodiak.database.models import Finding


class FindingSelected(Message):
    """Message sent when a finding is selected"""
    
    def __init__(self, finding_id: str, finding: Finding) -> None:
        super().__init__()
        self.finding_id = finding_id
        self.finding = finding


class FindingItem(ListItem):
    """Individual finding list item"""
    
    def __init__(self, finding: Finding, **kwargs):
        super().__init__(**kwargs)
        self.finding = finding
        self._update_content()
    
    def _update_content(self):
        """Update the finding item content"""
        severity_icon = self._get_severity_icon(self.finding.severity)
        title = self.finding.title or "Untitled Finding"
        
        # Get target from node or evidence (Requirement 9.3)
        target = "Unknown Target"
        if hasattr(self.finding, 'target') and self.finding.target:
            target = self.finding.target
        elif self.finding.node and hasattr(self.finding.node, 'name'):
            target = self.finding.node.name
        elif self.finding.evidence and isinstance(self.finding.evidence, dict):
            target = self.finding.evidence.get("target") or self.finding.evidence.get("url") or "Unknown Target"
        
        # Get agent info from evidence (Requirement 9.3)
        agent = "Unknown"
        if self.finding.evidence and isinstance(self.finding.evidence, dict):
            agent = self.finding.evidence.get("discovered_by") or self.finding.evidence.get("agent") or "Unknown"
        
        # Get timestamp (Requirement 9.3)
        timestamp = ""
        if self.finding.created_at:
            timestamp = self.finding.created_at.strftime("%H:%M:%S")
        
        # Truncate long titles and targets
        if len(title) > 35:
            title = title[:32] + "..."
        if len(target) > 25:
            target = target[:22] + "..."
        if len(agent) > 10:
            agent = agent[:7] + "..."
        
        # Format: icon title (target) [agent] timestamp
        content = f"{severity_icon} {title} ({target}) [{agent}] {timestamp}"
        
        # Clear existing content and add new
        self.remove_children()
        self.mount(Static(content))
    
    def _get_severity_icon(self, severity: str) -> str:
        """Get the appropriate icon for severity"""
        severity_icons = {
            "critical": "🔴",  # Red circle
            "high": "🟠",      # Orange circle
            "medium": "🟡",    # Yellow circle
            "low": "🟢",       # Green circle
            "info": "🔵",      # Blue circle
        }
        return severity_icons.get(severity.lower() if severity else "info", "⚪")


class SeverityGroup(Widget):
    """A collapsible group for findings of a specific severity"""
    
    def __init__(self, severity: str, findings: List[Finding], **kwargs):
        super().__init__(**kwargs)
        self.severity = severity
        self.findings = findings
        self.expanded = True
    
    def compose(self) -> ComposeResult:
        """Compose the severity group"""
        severity_icon = self._get_severity_icon(self.severity)
        count = len(self.findings)
        title = f"{severity_icon} {self.severity.title()} ({count})"
        
        with Collapsible(title=title, collapsed=not self.expanded):
            yield ListView(id=f"findings-{self.severity}")
    
    def on_mount(self) -> None:
        """Initialize the severity group"""
        self._populate_findings()
    
    def _populate_findings(self):
        """Populate the findings list"""
        findings_list = self.query_one(f"#findings-{self.severity}", ListView)
        
        for finding in self.findings:
            finding_item = FindingItem(finding)
            findings_list.append(finding_item)
    
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
    
    def update_findings(self, findings: List[Finding]):
        """Update the findings in this group"""
        self.findings = findings
        
        # Update title
        collapsible = self.query_one(Collapsible)
        severity_icon = self._get_severity_icon(self.severity)
        count = len(self.findings)
        collapsible.title = f"{severity_icon} {self.severity.title()} ({count})"
        
        # Clear and repopulate
        findings_list = self.query_one(f"#findings-{self.severity}", ListView)
        findings_list.clear()
        self._populate_findings()


class FindingsList(Widget):
    """
    Widget that displays findings grouped by severity.
    Shows summary counts and supports filtering.
    """
    
    DEFAULT_CSS = """
    FindingsList {
        border: solid $primary;
        height: 100%;
        min-height: 10;
    }
    
    FindingsList > Vertical {
        height: 100%;
    }
    
    FindingsList .title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    
    FindingsList .summary {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        text-align: center;
        padding: 0 1;
    }
    
    FindingsList .content {
        height: 1fr;
        overflow-y: auto;
    }
    
    FindingsList .empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    
    FindingsList Collapsible {
        margin: 0 1;
    }
    
    FindingsList ListView {
        height: auto;
        max-height: 10;
        border: none;
        margin-left: 2;
    }
    
    FindingsList ListItem {
        height: 1;
        padding: 0 1;
    }
    
    FindingsList ListItem:hover {
        background: $primary 20%;
    }
    
    FindingsList ListItem.-selected {
        background: $accent;
        color: $text-selected;
    }
    
    FindingsList .critical {
        color: $error;
        text-style: bold;
    }
    
    FindingsList .high {
        color: $warning;
        text-style: bold;
    }
    
    FindingsList .medium {
        color: $warning;
    }
    
    FindingsList .low {
        color: $success;
    }
    
    FindingsList .info {
        color: $primary;
    }
    """
    
    # Reactive properties
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    findings: reactive[List[Finding]] = reactive([])
    filter_severity: reactive[Optional[str]] = reactive(None)
    filter_agent: reactive[Optional[str]] = reactive(None)
    filter_type: reactive[Optional[str]] = reactive(None)
    selected_finding_id: reactive[Optional[str]] = reactive(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.severity_groups: Dict[str, SeverityGroup] = {}
        self.severity_order = ["critical", "high", "medium", "low", "info"]
        
        # Subscribe to state changes
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("finding_added", self._on_finding_added)
    
    def compose(self) -> ComposeResult:
        """Compose the findings list layout"""
        with Vertical():
            yield Static("Findings", classes="title", id="title")
            yield Static("", classes="summary", id="summary")
            yield Vertical(id="content", classes="content")
    
    def on_mount(self) -> None:
        """Initialize findings list when mounted"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_findings()
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_findings()
    
    def _on_finding_added(self, event):
        """Handle finding added events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            finding = data.get("finding")
            if finding:
                self._add_finding(finding)
    
    def _refresh_findings(self):
        """Refresh the entire findings list"""
        content = self.query_one("#content", Vertical)
        content.remove_children()
        self.severity_groups.clear()
        
        if not self.current_scan:
            self.findings = []
            content.mount(Static("No scan selected", classes="empty"))
            self._update_summary()
            return
        
        # Get findings from current scan
        all_findings = app_state.get_findings_for_scan(self.current_scan.id)
        
        # Apply filters (Requirement 9.6)
        filtered_findings = self._apply_filters(all_findings)
        self.findings = filtered_findings
        
        if not filtered_findings:
            if all_findings:
                content.mount(Static("No findings match current filters", classes="empty"))
            else:
                content.mount(Static("No findings discovered yet", classes="empty"))
            self._update_summary()
            return
        
        # Group findings by severity
        grouped_findings = self._group_findings_by_severity(filtered_findings)
        
        # Create severity groups
        for severity in self.severity_order:
            if severity in grouped_findings:
                severity_findings = grouped_findings[severity]
                if not self.filter_severity or self.filter_severity == severity:
                    group = SeverityGroup(severity, severity_findings)
                    group.add_class(severity)
                    self.severity_groups[severity] = group
                    content.mount(group)
        
        self._update_summary()
    
    def _apply_filters(self, findings: List[Finding]) -> List[Finding]:
        """Apply all active filters to findings list (Requirement 9.6)"""
        filtered = findings
        
        # Filter by severity
        if self.filter_severity:
            filtered = [f for f in filtered if (f.severity or "info").lower() == self.filter_severity.lower()]
        
        # Filter by agent
        if self.filter_agent:
            def matches_agent(finding: Finding) -> bool:
                if finding.evidence and isinstance(finding.evidence, dict):
                    agent = finding.evidence.get("discovered_by") or finding.evidence.get("agent")
                    return agent == self.filter_agent
                return False
            filtered = [f for f in filtered if matches_agent(f)]
        
        # Filter by type
        if self.filter_type:
            def matches_type(finding: Finding) -> bool:
                # Check node type
                if finding.node and hasattr(finding.node, 'type') and finding.node.type == self.filter_type:
                    return True
                # Check evidence type
                if finding.evidence and isinstance(finding.evidence, dict):
                    finding_type = finding.evidence.get("type") or finding.evidence.get("vulnerability_type")
                    return finding_type == self.filter_type
                return False
            filtered = [f for f in filtered if matches_type(f)]
        
        return filtered
    
    def _group_findings_by_severity(self, findings: List[Finding]) -> Dict[str, List[Finding]]:
        """Group findings by severity level"""
        grouped = {}
        for finding in findings:
            severity = finding.severity.lower() if finding.severity else "info"
            if severity not in grouped:
                grouped[severity] = []
            grouped[severity].append(finding)
        
        # Sort findings within each group by title
        for severity_findings in grouped.values():
            severity_findings.sort(key=lambda f: f.title or "")
        
        return grouped
    
    def _add_finding(self, finding: Finding):
        """Add a single finding to the appropriate group"""
        severity = finding.severity.lower() if finding.severity else "info"
        
        # Add to findings list
        self.findings = self.findings + [finding]
        
        # Update or create severity group
        if severity in self.severity_groups:
            # Update existing group
            group_findings = [f for f in self.findings if (f.severity or "info").lower() == severity]
            self.severity_groups[severity].update_findings(group_findings)
        else:
            # Create new group if it doesn't exist and passes filter
            if not self.filter_severity or self.filter_severity == severity:
                group_findings = [f for f in self.findings if (f.severity or "info").lower() == severity]
                group = SeverityGroup(severity, group_findings)
                group.add_class(severity)
                self.severity_groups[severity] = group
                
                # Insert in correct position
                content = self.query_one("#content", Vertical)
                insert_index = self._get_insert_index(severity)
                content.mount(group, before=insert_index)
        
        self._update_summary()
    
    def _get_insert_index(self, severity: str) -> Optional[int]:
        """Get the index where to insert a new severity group"""
        try:
            severity_index = self.severity_order.index(severity)
        except ValueError:
            return None
        
        content = self.query_one("#content", Vertical)
        for i, child in enumerate(content.children):
            if isinstance(child, SeverityGroup):
                try:
                    child_index = self.severity_order.index(child.severity)
                    if severity_index < child_index:
                        return i
                except ValueError:
                    continue
        
        return None
    
    def _update_summary(self):
        """Update the summary display"""
        summary = self.query_one("#summary", Static)
        
        if not self.findings:
            summary.update("No findings")
            return
        
        # Count findings by severity
        severity_counts = {}
        for finding in self.findings:
            severity = finding.severity.lower() if finding.severity else "info"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        
        # Build summary text
        total = len(self.findings)
        summary_parts = [f"Total: {total}"]
        
        for severity in self.severity_order:
            if severity in severity_counts:
                count = severity_counts[severity]
                icon = self._get_severity_icon(severity)
                summary_parts.append(f"{icon}{count}")
        
        summary_text = " | ".join(summary_parts)
        
        if self.filter_severity:
            summary_text += f" (filtered: {self.filter_severity})"
        
        summary.update(summary_text)
    
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
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle finding selection"""
        if event.item and hasattr(event.item, 'finding'):
            finding = event.item.finding
            self.selected_finding_id = str(finding.id)
            
            # Post finding selected message
            self.post_message(FindingSelected(str(finding.id), finding))
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        self._refresh_findings()
    
    def watch_filter_severity(self, severity: Optional[str]) -> None:
        """React to severity filter changes"""
        self._refresh_findings()
    
    def watch_filter_agent(self, agent: Optional[str]) -> None:
        """React to agent filter changes"""
        self._refresh_findings()
    
    def watch_filter_type(self, finding_type: Optional[str]) -> None:
        """React to type filter changes"""
        self._refresh_findings()
    
    def set_filter_severity(self, severity: Optional[str]):
        """Set severity filter"""
        self.filter_severity = severity.lower() if severity else None
    
    def set_filter_agent(self, agent: Optional[str]):
        """Set agent filter (Requirement 9.6)"""
        self.filter_agent = agent
    
    def set_filter_type(self, finding_type: Optional[str]):
        """Set type filter (Requirement 9.6)"""
        self.filter_type = finding_type
    
    def clear_filter(self):
        """Clear all filters"""
        self.filter_severity = None
        self.filter_agent = None
        self.filter_type = None
    
    def get_selected_finding(self) -> Optional[Finding]:
        """Get the currently selected finding"""
        if self.selected_finding_id:
            for finding in self.findings:
                if str(finding.id) == self.selected_finding_id:
                    return finding
        return None
    
    def get_findings_by_severity(self, severity: str) -> List[Finding]:
        """Get all findings of a specific severity"""
        return [f for f in self.findings if (f.severity or "info").lower() == severity.lower()]
    
    def get_severity_counts(self) -> Dict[str, int]:
        """Get count of findings by severity"""
        counts = {}
        for finding in self.findings:
            severity = finding.severity.lower() if finding.severity else "info"
            counts[severity] = counts.get(severity, 0) + 1
        return counts
    
    def get_total_count(self) -> int:
        """Get total number of findings"""
        return len(self.findings)
    
    def expand_all(self):
        """Expand all severity groups"""
        for group in self.severity_groups.values():
            collapsible = group.query_one(Collapsible)
            collapsible.collapsed = False
    
    def collapse_all(self):
        """Collapse all severity groups"""
        for group in self.severity_groups.values():
            collapsible = group.query_one(Collapsible)
            collapsible.collapsed = True
    
    def refresh(self):
        """Force refresh the findings list"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_findings()
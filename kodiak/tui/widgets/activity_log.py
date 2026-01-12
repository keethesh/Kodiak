"""
ActivityLog Widget

A scrolling log display that shows agent activities and system events.
Auto-scrolls on new entries with timestamp formatting.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from textual.widget import Widget
from textual.widgets import RichLog, Static
from textual.containers import Vertical
from textual.reactive import reactive
from textual.app import ComposeResult
from rich.text import Text
from rich.console import Console

from kodiak.tui.state import app_state, ScanState


class LogEntry:
    """Represents a single log entry"""
    
    def __init__(
        self,
        timestamp: datetime,
        level: str,
        message: str,
        source: Optional[str] = None,
        agent_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.timestamp = timestamp
        self.level = level.upper()
        self.message = message
        self.source = source
        self.agent_id = agent_id
        self.details = details or {}
    
    def format_timestamp(self) -> str:
        """Format timestamp for display"""
        return self.timestamp.strftime("%H:%M:%S")
    
    def get_level_color(self) -> str:
        """Get color for log level"""
        level_colors = {
            "DEBUG": "dim white",
            "INFO": "blue",
            "SUCCESS": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        return level_colors.get(self.level, "white")
    
    def get_level_icon(self) -> str:
        """Get icon for log level"""
        level_icons = {
            "DEBUG": "🔍",
            "INFO": "ℹ️",
            "SUCCESS": "✅",
            "WARNING": "⚠️",
            "ERROR": "❌",
            "CRITICAL": "🚨",
        }
        return level_icons.get(self.level, "📝")
    
    def to_rich_text(self) -> Text:
        """Convert to Rich Text object for display"""
        text = Text()
        
        # Timestamp
        text.append(f"[{self.format_timestamp()}] ", style="dim white")
        
        # Level icon and text
        icon = self.get_level_icon()
        color = self.get_level_color()
        text.append(f"{icon} {self.level:<8} ", style=color)
        
        # Source/Agent
        if self.agent_id:
            text.append(f"[Agent-{self.agent_id}] ", style="cyan")
        elif self.source:
            text.append(f"[{self.source}] ", style="magenta")
        
        # Message
        text.append(self.message, style="white")
        
        return text


class ActivityLog(Widget):
    """
    Scrolling activity log widget that displays agent activities and system events.
    Auto-scrolls to show new entries and supports filtering.
    """
    
    DEFAULT_CSS = """
    ActivityLog {
        border: solid $primary;
        height: 100%;
        min-height: 10;
    }
    
    ActivityLog > Vertical {
        height: 100%;
    }
    
    ActivityLog .title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    
    ActivityLog RichLog {
        height: 1fr;
        border: none;
        scrollbar-gutter: stable;
    }
    
    ActivityLog .empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """
    
    # Reactive properties
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    auto_scroll: reactive[bool] = reactive(True)
    max_entries: reactive[int] = reactive(1000)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.entries: List[LogEntry] = []
        self.filtered_entries: List[LogEntry] = []
        self.filter_level: Optional[str] = None
        self.filter_agent: Optional[str] = None
        
        # Subscribe to state changes
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("agent_status_changed", self._on_agent_status_changed)
        app_state.subscribe("tool_started", self._on_tool_started)
        app_state.subscribe("tool_completed", self._on_tool_completed)
        app_state.subscribe("finding_added", self._on_finding_added)
        app_state.subscribe("node_added", self._on_node_added)
    
    def compose(self) -> ComposeResult:
        """Compose the activity log layout"""
        with Vertical():
            yield Static("Activity Log", classes="title", id="title")
            yield RichLog(id="log-display", auto_scroll=True, max_lines=self.max_entries)
    
    def on_mount(self) -> None:
        """Initialize activity log when mounted"""
        self.current_scan = app_state.get_current_scan()
        self._add_system_log("INFO", "Activity log initialized")
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        old_scan = self.current_scan
        self.current_scan = app_state.get_current_scan()
        
        if old_scan != self.current_scan:
            if self.current_scan:
                self._add_system_log("INFO", f"Switched to scan: {self.current_scan.name}")
            else:
                self._add_system_log("INFO", "No scan selected")
    
    def _on_agent_status_changed(self, event):
        """Handle agent status change events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            agent_id = data.get("agent_id")
            new_status = data.get("new_status")
            task = data.get("task")
            
            message = f"Status changed to {new_status.value}"
            if task:
                message += f" - {task}"
            
            self._add_agent_log("INFO", message, agent_id)
    
    def _on_tool_started(self, event):
        """Handle tool started events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            tool_name = data.get("tool_name")
            target = data.get("target")
            agent_id = data.get("agent_id")
            
            message = f"Started {tool_name}"
            if target:
                message += f" on {target}"
            
            self._add_agent_log("INFO", message, agent_id)
    
    def _on_tool_completed(self, event):
        """Handle tool completed events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            tool_name = data.get("tool_name")
            success = data.get("success")
            agent_id = data.get("agent_id")
            error = data.get("error")
            
            if success:
                message = f"Completed {tool_name} successfully"
                level = "SUCCESS"
            else:
                message = f"Failed {tool_name}"
                if error:
                    message += f": {error}"
                level = "ERROR"
            
            self._add_agent_log(level, message, agent_id)
    
    def _on_finding_added(self, event):
        """Handle finding added events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            finding = data.get("finding")
            if finding:
                message = f"Found {finding.severity} vulnerability: {finding.title}"
                self._add_system_log("SUCCESS", message)
    
    def _on_node_added(self, event):
        """Handle node added events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            node = data.get("node")
            if node:
                message = f"Discovered {node.node_type.value}: {node.name or node.value}"
                self._add_system_log("INFO", message)
    
    def _add_system_log(self, level: str, message: str, details: Optional[Dict[str, Any]] = None):
        """Add a system log entry"""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            source="System",
            details=details
        )
        self._add_entry(entry)
    
    def _add_agent_log(self, level: str, message: str, agent_id: str, details: Optional[Dict[str, Any]] = None):
        """Add an agent log entry"""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            agent_id=agent_id,
            details=details
        )
        self._add_entry(entry)
    
    def _add_entry(self, entry: LogEntry):
        """Add a log entry and update display"""
        self.entries.append(entry)
        
        # Trim entries if we exceed max
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries:]
        
        # Apply filters and update display
        if self._passes_filter(entry):
            self.filtered_entries.append(entry)
            self._update_display(entry)
    
    def _passes_filter(self, entry: LogEntry) -> bool:
        """Check if entry passes current filters"""
        if self.filter_level and entry.level != self.filter_level:
            return False
        
        if self.filter_agent and entry.agent_id != self.filter_agent:
            return False
        
        return True
    
    def _update_display(self, entry: LogEntry):
        """Update the display with a new entry"""
        log_display = self.query_one("#log-display", RichLog)
        log_display.write(entry.to_rich_text())
    
    def _refresh_display(self):
        """Refresh the entire display"""
        log_display = self.query_one("#log-display", RichLog)
        log_display.clear()
        
        # Apply filters
        self.filtered_entries = [entry for entry in self.entries if self._passes_filter(entry)]
        
        # Display filtered entries
        for entry in self.filtered_entries:
            log_display.write(entry.to_rich_text())
    
    def add_log(self, level: str, message: str, source: Optional[str] = None, 
                agent_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        """Add a custom log entry"""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=level,
            message=message,
            source=source,
            agent_id=agent_id,
            details=details
        )
        self._add_entry(entry)
    
    def clear_log(self):
        """Clear all log entries"""
        self.entries.clear()
        self.filtered_entries.clear()
        log_display = self.query_one("#log-display", RichLog)
        log_display.clear()
        self._add_system_log("INFO", "Log cleared")
    
    def set_filter_level(self, level: Optional[str]):
        """Set log level filter"""
        self.filter_level = level.upper() if level else None
        self._refresh_display()
        
        if level:
            self._add_system_log("INFO", f"Filtering by level: {level}")
        else:
            self._add_system_log("INFO", "Removed level filter")
    
    def set_filter_agent(self, agent_id: Optional[str]):
        """Set agent filter"""
        self.filter_agent = agent_id
        self._refresh_display()
        
        if agent_id:
            self._add_system_log("INFO", f"Filtering by agent: {agent_id}")
        else:
            self._add_system_log("INFO", "Removed agent filter")
    
    def clear_filters(self):
        """Clear all filters"""
        self.filter_level = None
        self.filter_agent = None
        self._refresh_display()
        self._add_system_log("INFO", "Cleared all filters")
    
    def export_log(self, filename: str) -> bool:
        """Export log entries to a file"""
        try:
            with open(filename, 'w') as f:
                f.write("Kodiak Activity Log Export\n")
                f.write("=" * 50 + "\n\n")
                
                for entry in self.entries:
                    f.write(f"[{entry.timestamp.isoformat()}] ")
                    f.write(f"{entry.level:<8} ")
                    
                    if entry.agent_id:
                        f.write(f"[Agent-{entry.agent_id}] ")
                    elif entry.source:
                        f.write(f"[{entry.source}] ")
                    
                    f.write(f"{entry.message}\n")
                    
                    if entry.details:
                        f.write(f"  Details: {entry.details}\n")
                    
                    f.write("\n")
            
            self._add_system_log("SUCCESS", f"Log exported to {filename}")
            return True
            
        except Exception as e:
            self._add_system_log("ERROR", f"Failed to export log: {str(e)}")
            return False
    
    def get_entry_count(self) -> int:
        """Get total number of entries"""
        return len(self.entries)
    
    def get_filtered_entry_count(self) -> int:
        """Get number of filtered entries"""
        return len(self.filtered_entries)
    
    def get_level_counts(self) -> Dict[str, int]:
        """Get count of entries by level"""
        counts = {}
        for entry in self.entries:
            counts[entry.level] = counts.get(entry.level, 0) + 1
        return counts
    
    def watch_auto_scroll(self, auto_scroll: bool) -> None:
        """React to auto scroll changes"""
        log_display = self.query_one("#log-display", RichLog)
        log_display.auto_scroll = auto_scroll
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        # This is handled by the event subscription
        pass
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the log"""
        log_display = self.query_one("#log-display", RichLog)
        log_display.scroll_end()
    
    def scroll_to_top(self):
        """Scroll to the top of the log"""
        log_display = self.query_one("#log-display", RichLog)
        log_display.scroll_home()
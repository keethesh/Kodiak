"""
HelpScreen View

Help overlay showing keyboard shortcuts and navigation guide.
"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Vertical, Container, ScrollableContainer
from textual.binding import Binding


class HelpScreen(Screen):
    """
    Help screen showing keyboard shortcuts
    
    Requirements: 12.7
    """
    
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("question_mark", "close", "Close"),
    ]
    
    CSS = """
    HelpScreen {
        layout: vertical;
        background: $surface 80%;
    }
    
    #help-container {
        width: 80%;
        height: 90%;
        margin: 2 auto;
        background: $surface;
        border: solid $primary;
        padding: 1 2;
    }
    
    #help-title {
        text-align: center;
        text-style: bold;
        height: 2;
        background: $primary;
        margin-bottom: 1;
    }
    
    .section-title {
        text-style: bold;
        color: $accent;
        margin-top: 1;
    }
    
    .shortcut {
        margin-left: 2;
    }
    
    .key {
        text-style: bold;
        color: $warning;
    }
    
    #close-hint {
        dock: bottom;
        height: 1;
        text-align: center;
        color: $text-muted;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="help-container"):
            yield Static("🐻 Kodiak TUI - Keyboard Shortcuts", id="help-title")
            
            with ScrollableContainer():
                # Global shortcuts
                yield Static("Global Shortcuts", classes="section-title")
                yield Static("  q         - Quit application", classes="shortcut")
                yield Static("  h         - Go to home screen", classes="shortcut")
                yield Static("  ?         - Show this help", classes="shortcut")
                yield Static("  Escape    - Go back / Cancel", classes="shortcut")
                
                # Home screen
                yield Static("\nHome Screen", classes="section-title")
                yield Static("  n         - Create new scan", classes="shortcut")
                yield Static("  d         - Delete selected project", classes="shortcut")
                yield Static("  r         - Resume paused scan", classes="shortcut")
                yield Static("  Enter     - Open selected project", classes="shortcut")
                yield Static("  ↑/↓       - Navigate projects", classes="shortcut")
                
                # New scan screen
                yield Static("\nNew Scan Screen", classes="section-title")
                yield Static("  Tab       - Move between fields", classes="shortcut")
                yield Static("  Enter     - Start scan", classes="shortcut")
                yield Static("  Escape    - Cancel and go back", classes="shortcut")
                
                # Mission control
                yield Static("\nMission Control", classes="section-title")
                yield Static("  Tab       - Cycle between panels", classes="shortcut")
                yield Static("  g         - Open graph view", classes="shortcut")
                yield Static("  f         - Open findings view", classes="shortcut")
                yield Static("  p         - Pause/Resume scan", classes="shortcut")
                yield Static("  Enter     - Select agent for chat", classes="shortcut")
                
                # Agent chat
                yield Static("\nAgent Chat", classes="section-title")
                yield Static("  ←/→       - Switch between agents", classes="shortcut")
                yield Static("  Enter     - Send message", classes="shortcut")
                yield Static("  Escape    - Return to mission control", classes="shortcut")
                
                # Graph view
                yield Static("\nGraph View", classes="section-title")
                yield Static("  ↑/↓       - Navigate nodes", classes="shortcut")
                yield Static("  ←/→       - Collapse/Expand", classes="shortcut")
                yield Static("  /         - Search nodes", classes="shortcut")
                yield Static("  Enter     - View finding details", classes="shortcut")
                yield Static("  Escape    - Go back", classes="shortcut")
                
                # Findings view
                yield Static("\nFindings View", classes="section-title")
                yield Static("  1-5       - Filter by severity", classes="shortcut")
                yield Static("  0         - Show all findings", classes="shortcut")
                yield Static("  a         - Cycle agent filter", classes="shortcut")
                yield Static("  t         - Cycle type filter", classes="shortcut")
                yield Static("  e         - Export findings", classes="shortcut")
                yield Static("  Enter     - View finding details", classes="shortcut")
                yield Static("  Escape    - Go back", classes="shortcut")
                
                # Finding detail
                yield Static("\nFinding Detail", classes="section-title")
                yield Static("  c         - Copy proof-of-concept", classes="shortcut")
                yield Static("  r         - Re-test vulnerability", classes="shortcut")
                yield Static("  Escape    - Go back", classes="shortcut")
            
            yield Static("Press Escape, Q, or ? to close", id="close-hint")
        
        yield Footer()
    
    def action_close(self) -> None:
        """Close the help screen"""
        self.app.pop_screen()
    
    def on_key(self, event) -> None:
        """Close help on any key press (except navigation)"""
        if event.key not in ["up", "down", "pageup", "pagedown"]:
            self.app.pop_screen()

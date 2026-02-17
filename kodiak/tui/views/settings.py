"""
SettingsScreen View

A screen for viewing application configuration and status.
"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, Button, Label
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding

from kodiak.core.config import settings

class SettingsScreen(Screen):
    """Settings screen - view app configuration"""
    
    BINDINGS = [
        Binding("h", "go_home", "Home"),
        Binding("escape", "go_back", "Back"),
        Binding("q", "quit", "Quit"),
    ]
    
    CSS = """
    SettingsScreen {
        align: center middle;
    }
    
    #settings-container {
        width: 80;
        height: auto;
        padding: 2;
        border: solid $primary;
        background: $surface;
    }
    
    #settings-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 2;
    }
    
    .setting-item {
        height: auto;
        margin-bottom: 1;
        padding: 0 1;
    }
    
    .setting-label {
        width: 25;
        color: $text-muted;
        text-style: bold;
    }
    
    .setting-value {
        color: $text;
    }
    
    #back-btn-container {
        margin-top: 2;
        align: center middle;
    }
    
    #back-btn {
        min-width: 20;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Header()
        
        with Container(id="settings-container"):
            yield Static("⚙️ Application Settings", id="settings-title")
            
            with Vertical():
                # LLM Provider
                with Horizontal(classes="setting-item"):
                    yield Label("LLM Model:", classes="setting-label")
                    yield Label(settings.llm_model, classes="setting-value")
                
                # Database Type
                with Horizontal(classes="setting-item"):
                    yield Label("Database Type:", classes="setting-label")
                    db_type = "SQLite" if settings.is_sqlite else "PostgreSQL"
                    yield Label(db_type, classes="setting-value")
                
                # Version info
                with Horizontal(classes="setting-item"):
                    yield Label("Kodiak Version:", classes="setting-label")
                    yield Label(f"v{settings.VERSION}", classes="setting-value")
                
                # Debug mode
                with Horizontal(classes="setting-item"):
                    yield Label("Debug Mode:", classes="setting-label")
                    debug_status = "Enabled" if settings.debug else "Disabled"
                    yield Label(debug_status, classes="setting-value")
                
                # Log level
                with Horizontal(classes="setting-item"):
                    yield Label("Log Level:", classes="setting-label")
                    yield Label(settings.log_level, classes="setting-value")

            with Container(id="back-btn-container"):
                yield Button("Back to Home", variant="primary", id="back-btn")
                
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.action_go_back()

    def action_go_back(self) -> None:
        """Return to previous screen"""
        self.app.pop_screen()

    def action_go_home(self) -> None:
        """Return to home screen"""
        while len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        from kodiak.tui.views.home import HomeScreen
        if not isinstance(self.app.screen, HomeScreen):
            self.app.push_screen(HomeScreen())

    def action_quit(self) -> None:
        """Quit application"""
        self.app.exit()

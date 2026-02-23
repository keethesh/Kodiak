"""
Configuration Wizard for Kodiak

A TUI-based wizard that guides users through setting up Kodiak configuration.
Uses Textual for a modern terminal interface.
"""

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Static, Button, Input, 
    RadioButton, RadioSet, Label, ProgressBar, LoadingIndicator
)
import asyncio
from kodiak.database.engine import init_db
from loguru import logger
from rich.panel import Panel
from rich.text import Text


# Gemini model configurations (Gemini-only runtime)
LLM_PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "description": "Gemini-only mode",
        "env_var": "GOOGLE_API_KEY",
        "default_model": "gemini/gemini-3.1-pro-preview",
        "models": ["gemini/gemini-3.1-pro-preview", "gemini/gemini-3-flash-preview"],
    }
}


class WelcomeScreen(Screen):
    """Welcome screen for the configuration wizard."""
    
    CSS = """
    WelcomeScreen {
        align: center middle;
    }
    
    #welcome-container {
        width: 70;
        height: auto;
        padding: 2;
        border: round $primary;
        background: $surface;
    }
    
    #welcome-title {
        text-align: center;
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    
    #welcome-description {
        text-align: center;
        margin-bottom: 2;
    }
    
    Button {
        width: 100%;
        margin-top: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("🐻 Welcome to Kodiak", id="welcome-title"),
            Static(
                "This wizard will help you configure Kodiak for first use.\n\n"
                "You'll need:\n"
                "• A Google Gemini API key\n"
                "• Docker installed (for security tools)\n\n"
                "Configuration will be saved to ~/.kodiak/config.env",
                id="welcome-description"
            ),
            Button("Get Started →", variant="primary", id="start-btn"),
            Button("Skip Configuration", variant="default", id="skip-btn"),
            id="welcome-container"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.app.push_screen(ProviderScreen())
        elif event.button.id == "skip-btn":
            self.app.exit(result=None)


class ProviderScreen(Screen):
    """Screen for selecting LLM provider."""
    
    CSS = """
    ProviderScreen {
        align: center middle;
    }
    
    #provider-container {
        width: 80;
        height: auto;
        padding: 2;
        border: round $primary;
        background: $surface;
    }
    
    #provider-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    RadioSet {
        margin: 1 0;
    }
    
    .provider-option {
        padding: 1;
        margin: 0 0 1 0;
    }
    
    #button-row {
        margin-top: 2;
    }
    
    Button {
        margin-right: 1;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("Step 1: Select LLM Provider", id="provider-title"),
            RadioSet(
                RadioButton("🌟 Google Gemini (Recommended)", id="gemini"),
                id="provider-radio"
            ),
            Horizontal(
                Button("← Back", variant="default", id="back-btn"),
                Button("Next →", variant="primary", id="next-btn"),
                id="button-row"
            ),
            id="provider-container"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "next-btn":
            radio_set = self.query_one("#provider-radio", RadioSet)
            if radio_set.pressed_button:
                provider_id = radio_set.pressed_button.id
                self.app.config_data["provider"] = provider_id
                self.app.push_screen(ApiKeyScreen())


class ApiKeyScreen(Screen):
    """Screen for entering API key."""
    
    CSS = """
    ApiKeyScreen {
        align: center middle;
    }
    
    #apikey-container {
        width: 80;
        height: auto;
        padding: 2;
        border: round $primary;
        background: $surface;
    }
    
    #apikey-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    Input {
        margin: 1 0;
    }
    
    #button-row {
        margin-top: 2;
    }
    """
    
    def compose(self) -> ComposeResult:
        provider = self.app.config_data.get("provider", "gemini")
        provider_info = LLM_PROVIDERS.get(provider, LLM_PROVIDERS["gemini"])
        
        yield Container(
            Static(f"Step 2: Enter {provider_info['name']} API Key", id="apikey-title"),
            Static(f"Environment variable: {provider_info['env_var']}"),
            Input(placeholder="Paste your API key here...", password=True, id="api-key-input"),
            Static("Choose default Gemini model:"),
            RadioSet(
                RadioButton("Gemini 3.1 Pro (Recommended)", id="gemini-pro", value=True),
                RadioButton("Gemini 3 Flash", id="gemini-flash"),
                id="model-radio",
            ),
            Static("[dim]Your key is stored locally and never shared.[/dim]"),
            Horizontal(
                Button("← Back", variant="default", id="back-btn"),
                Button("Next →", variant="primary", id="next-btn"),
                id="button-row"
            ),
            id="apikey-container"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "next-btn":
            api_key_input = self.query_one("#api-key-input", Input)
            api_key = api_key_input.value.strip()
            model_radio = self.query_one("#model-radio", RadioSet)
            selected_model = "gemini/gemini-3.1-pro-preview"
            if model_radio.pressed_button and model_radio.pressed_button.id == "gemini-flash":
                selected_model = "gemini/gemini-3-flash-preview"
            
            if api_key:
                self.app.config_data["api_key"] = api_key
                self.app.config_data["llm_model"] = selected_model
                self.app.push_screen(DatabaseScreen())
            else:
                self.notify("Please enter an API key", severity="error")


class DatabaseScreen(Screen):
    """Screen for selecting database type."""
    
    CSS = """
    DatabaseScreen {
        align: center middle;
    }
    
    #db-container {
        width: 80;
        height: auto;
        padding: 2;
        border: round $primary;
        background: $surface;
    }
    
    #db-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    
    RadioSet {
        margin: 1 0;
    }
    
    #button-row {
        margin-top: 2;
    }
    """
    
    def compose(self) -> ComposeResult:
        yield Container(
            Static("Step 3: Select Database Mode", id="db-title"),
            RadioSet(
                RadioButton("📦 SQLite (Zero-config, recommended for getting started)", id="sqlite", value=True),
                RadioButton("🐘 PostgreSQL (Production, requires Docker or external DB)", id="postgres"),
                id="db-radio"
            ),
            Horizontal(
                Button("← Back", variant="default", id="back-btn"),
                Button("Finish →", variant="primary", id="finish-btn"),
                id="button-row"
            ),
            id="db-container"
        )
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "finish-btn":
            radio_set = self.query_one("#db-radio", RadioSet)
            if radio_set.pressed_button:
                self.app.config_data["db_type"] = radio_set.pressed_button.id
            else:
                self.app.config_data["db_type"] = "sqlite"
            
            # Save configuration and exit
            self.app.save_configuration()
            self.app.push_screen(SuccessScreen())


    async def _do_initialize(self) -> None:
        """Background worker for initialization"""
        try:
            self.query_one("#success-container").display = False
            self.query_one("#loading-container").display = True
            
            # Run the database initialization
            await init_db()
            
            # Wait a moment for effect
            await asyncio.sleep(1)
            
            # Exit with special result to signal launch
            self.app.exit(result={"launch_tui": True})
            
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            self.query_one("#loading-container").display = False
            self.query_one("#success-container").display = True
            self.notify(f"Initialization failed: {str(e)}", severity="error")

    def compose(self) -> ComposeResult:
        with Container(id="success-container"):
            yield Static("✅ Configuration Complete!", id="success-title")
            yield Static(
                "Kodiak is now configured and ready to use.\n\n"
                "You can now initialize the system and launch the interface immediately.",
                id="success-msg"
            )
            yield Button("Initialize & Launch 🚀", variant="success", id="launch-btn")
            yield Button("Exit to Terminal", variant="default", id="done-btn")
        
        with Container(id="loading-container"):
            yield Static("Initializing Kodiak...", id="loading-title")
            yield LoadingIndicator()
            yield Static("This may take a moment to set up the database.", id="loading-msg")

    def on_mount(self) -> None:
        self.query_one("#loading-container").display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "done-btn":
            self.app.exit(result=self.app.config_data)
        elif event.button.id == "launch-btn":
            self.run_worker(self._do_initialize())

    CSS = """
    SuccessScreen {
        align: center middle;
    }
    
    #success-container, #loading-container {
        width: 70;
        height: auto;
        padding: 2;
        border: round $success;
        background: $surface;
    }
    
    #loading-container {
        border: round $accent;
        align: center middle;
    }
    
    #success-title, #loading-title {
        text-align: center;
        text-style: bold;
        color: $success;
        margin-bottom: 1;
    }
    
    #loading-title { color: $accent; }
    
    #success-msg, #loading-msg {
        text-align: center;
        margin-bottom: 2;
    }
    
    Button {
        width: 100%;
        margin-top: 1;
    }
    
    LoadingIndicator {
        height: 3;
        margin: 1 0;
    }
    """


class ConfigWizardApp(App):
    """Kodiak Configuration Wizard TUI Application."""
    
    TITLE = "Kodiak Configuration Wizard"
    CSS_PATH = None
    
    BINDINGS = [
        Binding("escape", "quit", "Quit"),
        Binding("q", "quit", "Quit"),
    ]
    
    def __init__(self):
        super().__init__()
        self.config_data = {}
    
    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())
    
    def action_quit(self) -> None:
        self.exit(result=None)
    
    def save_configuration(self) -> None:
        """Save the configuration to ~/.kodiak/config.env"""
        kodiak_dir = Path.home() / ".kodiak"
        kodiak_dir.mkdir(exist_ok=True)
        
        config_file = kodiak_dir / "config.env"
        
        # Build configuration lines
        lines = [
            "# Kodiak Configuration",
            "# Generated by 'kodiak config'",
            ""
        ]
        
        provider = self.config_data.get("provider", "gemini")
        provider_info = LLM_PROVIDERS.get(provider, LLM_PROVIDERS["gemini"])
        
        # LLM Configuration
        selected_model = self.config_data.get("llm_model", provider_info["default_model"])
        lines.append(f"KODIAK_LLM_MODEL={selected_model}")
        
        if self.config_data.get("api_key"):
            lines.append(f"{provider_info['env_var']}={self.config_data['api_key']}")
        
        # Database Configuration
        db_type = self.config_data.get("db_type", "sqlite")
        lines.append(f"KODIAK_DB_TYPE={db_type}")
        
        # Write configuration
        config_file.write_text("\n".join(lines) + "\n")
        
        # Set restrictive permissions (ignore errors on Windows)
        try:
            config_file.chmod(0o600)
        except Exception:
            pass


def run_config_wizard() -> Optional[dict]:
    """Run the configuration wizard and return the configuration data."""
    app = ConfigWizardApp()
    return app.run()


if __name__ == "__main__":
    result = run_config_wizard()
    if result:
        print(f"\nConfiguration saved: {result}")
    else:
        print("\nConfiguration cancelled.")

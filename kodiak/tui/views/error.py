"""
Error Screen for TUI

Displays error messages and recovery options to the user.
"""

from typing import Dict, Any, Optional
from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.screen import Screen
from textual.widgets import Static, Button, Markdown
from textual.binding import Binding


class ErrorScreen(Screen):
    """Screen for displaying errors to the user"""
    
    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "quit_app", "Quit App"),
        Binding("r", "retry", "Retry"),
    ]
    
    def __init__(
        self,
        title: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        super().__init__()
        self.error_title = title
        self.error_message = message
        self.error_details = details or {}
        self.recoverable = recoverable
    
    def compose(self) -> ComposeResult:
        """Compose the error screen"""
        
        # Create error content
        error_content = f"""
# ❌ {self.error_title}

{self.error_message}

## Details

"""
        
        # Add details if available
        if self.error_details:
            for key, value in self.error_details.items():
                error_content += f"- **{key.replace('_', ' ').title()}**: {value}\n"
        
        # Add troubleshooting section
        error_content += """

## Troubleshooting

### Database Connection Issues
- Ensure PostgreSQL is running
- Check your database configuration in `.env`
- Verify network connectivity to database server
- Run `kodiak init` to initialize the database

### Configuration Issues
- Run `kodiak config` to reconfigure LLM settings
- Check that all required environment variables are set
- Verify API keys are valid and have proper permissions

### General Issues
- Check the logs for more detailed error information
- Ensure all dependencies are installed: `poetry install`
- Try restarting the application

"""
        
        with Container(id="error-container"):
            yield Static(f"Error: {self.error_title}", id="error-header")
            yield Markdown(error_content, id="error-content")
            
            with Horizontal(id="error-buttons"):
                if self.recoverable:
                    yield Button("Retry", id="retry-button", variant="primary")
                    yield Button("Continue Anyway", id="continue-button", variant="default")
                yield Button("Quit Application", id="quit-button", variant="error")
    
    def action_dismiss(self) -> None:
        """Dismiss the error screen if recoverable"""
        if self.recoverable:
            self.dismiss()
    
    def action_quit_app(self) -> None:
        """Quit the entire application"""
        self.app.exit(1)
    
    def action_retry(self) -> None:
        """Retry the failed operation"""
        if self.recoverable:
            # Go back to home and let user retry
            self.dismiss()
            self.app.action_go_home()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "retry-button":
            self.action_retry()
        elif event.button.id == "continue-button":
            self.dismiss()
        elif event.button.id == "quit-button":
            self.action_quit_app()


class DatabaseErrorScreen(ErrorScreen):
    """Specialized error screen for database issues"""
    
    def __init__(self, error_message: str, database_url: str):
        super().__init__(
            title="Database Connection Failed",
            message=error_message,
            details={
                "database_url": database_url,
                "suggested_action": "Check database configuration and connectivity"
            },
            recoverable=True
        )


class ConfigurationErrorScreen(ErrorScreen):
    """Specialized error screen for configuration issues"""
    
    def __init__(self, error_message: str, config_key: str = None):
        details = {"suggested_action": "Run 'kodiak config' to reconfigure"}
        if config_key:
            details["config_key"] = config_key
        
        super().__init__(
            title="Configuration Error",
            message=error_message,
            details=details,
            recoverable=True
        )


class CriticalErrorScreen(ErrorScreen):
    """Specialized error screen for critical, non-recoverable errors"""
    
    def __init__(self, error_message: str, error_details: Dict[str, Any] = None):
        super().__init__(
            title="Critical Error",
            message=error_message,
            details=error_details,
            recoverable=False
        )
"""
Main Kodiak TUI Application

This module contains the main Textual application class for Kodiak.
"""

from typing import Optional, Dict, Any
import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Container
from textual.screen import Screen
from textual.binding import Binding
from textual.message import Message
from loguru import logger

from kodiak.core.config import settings
from kodiak.tui.core_bridge import CoreBridge, set_core_bridge


class KodiakApp(App):
    """Main Kodiak TUI Application"""
    
    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "Kodiak - LLM Penetration Testing Suite"
    SUB_TITLE = f"v{settings.VERSION}"
    
    # Global shortcuts (Requirements 12.1, 12.7)
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("question_mark", "show_help", "Help", priority=True),
    ]
    
    def __init__(self, debug: bool = False):
        self._debug_mode = debug
        self.core_bridge = None
        super().__init__()
        
        if debug:
            logger.info("KodiakApp initialized in debug mode")
    
    @property
    def debug(self) -> bool:
        """Get debug mode status"""
        return getattr(self, '_debug_mode', False)
    
    def on_mount(self) -> None:
        """Called when the app is mounted"""
        logger.info("Kodiak TUI starting...")
        # Start with the home screen
        from kodiak.tui.views.home import HomeScreen
        self.push_screen(HomeScreen())
    
    def action_quit(self) -> None:
        """Quit the application (Requirement 12.1)"""
        logger.info("Kodiak TUI shutting down...")
        self.exit()
    
    def action_go_home(self) -> None:
        """Go to home screen (Requirement 12.1)"""
        # Pop all screens and go to home
        while len(self.screen_stack) > 1:
            self.pop_screen()
        
        # If we're not on home, push home screen
        from kodiak.tui.views.home import HomeScreen
        if not isinstance(self.screen, HomeScreen):
            self.push_screen(HomeScreen())
    
    def action_show_help(self) -> None:
        """Show help overlay (Requirement 12.1, 12.7)"""
        from kodiak.tui.views.help import HelpScreen
        self.push_screen(HelpScreen())
    
    async def on_startup(self) -> None:
        """Called when the app starts up with comprehensive error handling"""
        logger.info("Kodiak TUI startup starting...")
        
        try:
            # Initialize core bridge
            self.core_bridge = CoreBridge(self)
            set_core_bridge(self.core_bridge)
            await self.core_bridge.initialize()
            
            logger.info("Kodiak TUI startup complete")
            
        except Exception as e:
            logger.error(f"Failed to start Kodiak TUI: {e}")
            
            # Show error screen to user
            from kodiak.tui.views.error import ErrorScreen
            error_screen = ErrorScreen(
                title="Startup Failed",
                message=f"Failed to initialize Kodiak: {str(e)}",
                details={
                    "error_type": type(e).__name__,
                    "database_url": settings.database_url,
                    "debug_mode": self.debug
                },
                recoverable=False
            )
            self.push_screen(error_screen)
    
    async def on_shutdown(self) -> None:
        """Called when the app shuts down with error handling"""
        logger.info("Kodiak TUI shutdown starting...")
        
        try:
            # Shutdown core bridge
            if self.core_bridge:
                await self.core_bridge.shutdown()
            
            logger.info("Kodiak TUI shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during Kodiak TUI shutdown: {e}")
            # Don't raise during shutdown - just log
    
    def handle_error_message(self, message) -> None:
        """Handle error messages from core bridge"""
        from kodiak.tui.events import ErrorOccurred
        
        if isinstance(message, ErrorOccurred):
            logger.error(f"Error from {message.source}: {message.error_message}")
            
            # Show error notification to user
            if message.error_type == "database_unavailable":
                self.notify(
                    "Database connection lost. Some features may not work.",
                    severity="error",
                    timeout=10
                )
            elif message.error_type == "database_init_failed":
                self.notify(
                    "Database initialization failed. Please check your configuration.",
                    severity="error",
                    timeout=15
                )
            elif not message.recoverable:
                # Show critical error screen
                from kodiak.tui.views.error import ErrorScreen
                error_screen = ErrorScreen(
                    title="Critical Error",
                    message=message.error_message,
                    details=message.details,
                    recoverable=message.recoverable
                )
                self.push_screen(error_screen)
            else:
                # Show recoverable error as notification
                self.notify(
                    f"Error: {message.error_message}",
                    severity="error",
                    timeout=8
                )
    
    def on_message(self, message: Message) -> None:
        """Handle messages from the application"""
        from kodiak.tui.events import ErrorOccurred, LogMessage
        
        if isinstance(message, ErrorOccurred):
            self.handle_error_message(message)
        elif isinstance(message, LogMessage):
            if message.level == "error":
                self.notify(message.message, severity="error")
            elif message.level == "warning":
                self.notify(message.message, severity="warning")
            elif message.level == "info":
                self.notify(message.message, severity="information")
        
        # Let parent handle other messages
        super().on_message(message)


if __name__ == "__main__":
    app = KodiakApp(debug=True)
    app.run()
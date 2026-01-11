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


class KodiakScreen(Screen):
    """Base screen class for all Kodiak screens"""
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "home", "Home", priority=True),
        Binding("question_mark", "help", "Help", priority=True),
    ]
    
    def action_quit(self) -> None:
        """Quit the application"""
        self.app.exit()
    
    def action_home(self) -> None:
        """Go to home screen"""
        self.app.push_screen("home")
    
    def action_help(self) -> None:
        """Show help overlay"""
        self.app.push_screen("help")


class HomeScreen(KodiakScreen):
    """Home screen - project list and main navigation"""
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("🐻 Welcome to Kodiak TUI", id="welcome"),
            Static("Press 'n' to create a new scan", id="instructions"),
            Static("Press '?' for help", id="help-hint"),
            id="home-container"
        )
        yield Footer()
    
    BINDINGS = [
        *KodiakScreen.BINDINGS,
        Binding("n", "new_scan", "New Scan"),
        Binding("r", "refresh", "Refresh"),
    ]
    
    def action_new_scan(self) -> None:
        """Create a new scan"""
        self.app.push_screen("new_scan")
    
    def action_refresh(self) -> None:
        """Refresh the project list"""
        # TODO: Implement refresh logic
        pass


class HelpScreen(KodiakScreen):
    """Help screen showing keyboard shortcuts"""
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Kodiak TUI Help", id="help-title"),
            Static("", id="help-spacer"),
            Static("Global Shortcuts:", id="help-global-title"),
            Static("  q - Quit application", id="help-quit"),
            Static("  h - Go to home screen", id="help-home"),
            Static("  ? - Show this help", id="help-help"),
            Static("", id="help-spacer2"),
            Static("Home Screen:", id="help-home-title"),
            Static("  n - Create new scan", id="help-new"),
            Static("  r - Refresh project list", id="help-refresh"),
            Static("", id="help-spacer3"),
            Static("Press any key to close help", id="help-close"),
            id="help-container"
        )
        yield Footer()
    
    def on_key(self, event) -> None:
        """Close help on any key press"""
        self.app.pop_screen()


class KodiakApp(App):
    """Main Kodiak TUI Application"""
    
    CSS_PATH = "styles.tcss"
    TITLE = "Kodiak - LLM Penetration Testing Suite"
    SUB_TITLE = f"v{settings.VERSION}"
    
    SCREENS = {
        "home": HomeScreen,
        "help": HelpScreen,
    }
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
    ]
    
    def __init__(self, debug: bool = False):
        self._debug_mode = debug
        self._kodiak_screen_stack = []
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
        self.push_screen("home")
    
    def action_quit(self) -> None:
        """Quit the application"""
        logger.info("Kodiak TUI shutting down...")
        self.exit()
    
    def push_screen(self, screen_name: str) -> None:
        """Push a screen onto the stack"""
        if screen_name in self.SCREENS:
            self._kodiak_screen_stack.append(screen_name)
            super().push_screen(self.SCREENS[screen_name]())
        else:
            logger.warning(f"Unknown screen: {screen_name}")
    
    def pop_screen(self) -> None:
        """Pop the current screen from the stack"""
        if self._kodiak_screen_stack:
            self._kodiak_screen_stack.pop()
        super().pop_screen()
    
    def get_current_screen_name(self) -> Optional[str]:
        """Get the name of the current screen"""
        return self._kodiak_screen_stack[-1] if self._kodiak_screen_stack else None
    
    async def on_startup(self) -> None:
        """Called when the app starts up"""
        logger.info("Kodiak TUI startup starting...")
        
        try:
            # Initialize core bridge
            self.core_bridge = CoreBridge(self)
            set_core_bridge(self.core_bridge)
            await self.core_bridge.initialize()
            
            logger.info("Kodiak TUI startup complete")
            
        except Exception as e:
            logger.error(f"Failed to start Kodiak TUI: {e}")
            # Show error to user and exit
            self.exit(1)
    
    async def on_shutdown(self) -> None:
        """Called when the app shuts down"""
        logger.info("Kodiak TUI shutdown starting...")
        
        try:
            # Shutdown core bridge
            if self.core_bridge:
                await self.core_bridge.shutdown()
            
            logger.info("Kodiak TUI shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during Kodiak TUI shutdown: {e}")


if __name__ == "__main__":
    app = KodiakApp(debug=True)
    app.run()
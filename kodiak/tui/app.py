"""
Main Kodiak TUI Application — Tabbed Single-Screen Architecture
"""

from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer, TabbedContent, TabPane
from loguru import logger

from kodiak.core.config import settings
from kodiak.tui.core_bridge import CoreBridge, set_core_bridge


class KodiakApp(App):
    """Kodiak TUI — AI-Powered Penetration Testing Suite"""

    CSS_PATH = Path(__file__).parent / "styles.tcss"
    TITLE = "Kodiak"
    SUB_TITLE = f"AI Penetration Testing Suite  v{settings.VERSION}"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("question_mark", "show_help", "Help"),
        Binding("n", "new_scan", "New Scan"),
        Binding("1", "switch_tab('dashboard')", "Dashboard", show=False),
        Binding("2", "switch_tab('recon')", "Recon", show=False),
        Binding("3", "switch_tab('findings')", "Findings", show=False),
        Binding("4", "switch_tab('logs')", "Logs", show=False),
        Binding("5", "switch_tab('config')", "Config", show=False),
    ]

    def __init__(self, debug: bool = False, target: Optional[str] = None):
        self._debug_mode = debug
        self._initial_target = target
        self.core_bridge: Optional[CoreBridge] = None
        super().__init__()

    @property
    def debug(self) -> bool:
        return getattr(self, "_debug_mode", False)

    def compose(self) -> ComposeResult:
        from kodiak.tui.views.dashboard import DashboardView
        from kodiak.tui.views.recon import ReconView
        from kodiak.tui.views.findings_tab import FindingsView
        from kodiak.tui.views.logs_tab import LogsView
        from kodiak.tui.views.config_tab import ConfigView

        yield Header()
        with TabbedContent(initial="dashboard"):
            with TabPane("🏠 Dashboard", id="dashboard"):
                yield DashboardView(id="dashboard-view")
            with TabPane("🌐 Recon & Surface", id="recon"):
                yield ReconView(id="recon-view")
            with TabPane("🔒 Findings", id="findings"):
                yield FindingsView(id="findings-view")
            with TabPane("📋 Logs", id="logs"):
                yield LogsView(id="logs-view")
            with TabPane("⚙️ Config", id="config"):
                yield ConfigView(id="config-view")
        yield Footer()

    async def on_startup(self) -> None:
        """Initialize core bridge on startup."""
        logger.info("Kodiak TUI starting…")
        try:
            self.core_bridge = CoreBridge(self)
            set_core_bridge(self.core_bridge)
            await self.core_bridge.initialize()
            logger.info("Kodiak TUI ready.")
        except Exception as e:
            logger.error(f"Startup failed: {e}")
            self.notify(
                f"Startup error: {str(e)[:120]}\nRun 'kodiak init' to initialize the database.",
                severity="error",
                timeout=20,
            )

    async def on_shutdown(self) -> None:
        """Shutdown core bridge cleanly."""
        try:
            if self.core_bridge:
                await self.core_bridge.shutdown()
        except Exception as e:
            logger.error(f"Shutdown error: {e}")

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_quit(self) -> None:
        logger.info("Kodiak TUI exiting.")
        self.exit()

    def action_show_help(self) -> None:
        from kodiak.tui.views.help import HelpScreen
        self.push_screen(HelpScreen())

    def action_new_scan(self) -> None:
        from kodiak.tui.views.new_scan import NewScanModal
        self.push_screen(NewScanModal())

    def action_switch_tab(self, tab_id: str) -> None:
        try:
            tc = self.query_one(TabbedContent)
            tc.active = tab_id
        except Exception:
            pass


if __name__ == "__main__":
    KodiakApp(debug=True).run()
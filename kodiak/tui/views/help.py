"""
Help Screen — Modal overlay with keyboard shortcuts reference.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static
from textual.widgets import Rule


class HelpScreen(ModalScreen):
    """Help overlay — keyboard shortcuts reference."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("question_mark", "close", "Close"),
        Binding("ctrl+c", "close", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-box {
        background: $surface;
        border: round $primary;
        padding: 2 3;
        width: 68;
        height: auto;
        max-height: 90%;
    }

    #help-title {
        color: $primary;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    .help-section {
        color: $lavender;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    .help-row {
        color: $subtext0;
        padding: 0 2;
    }

    #close-hint {
        text-align: center;
        color: $muted;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-box"):
            yield Static("⌨  Keyboard Shortcuts", id="help-title")
            yield Rule()

            yield Static("Global", classes="help-section")
            for key, desc in [
                ("q / Escape", "Quit"),
                ("?",          "Toggle this help"),
                ("n",          "New Scan modal"),
                ("1 – 5",      "Switch tabs"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Static("Dashboard (Tab 1)", classes="help-section")
            for key, desc in [
                ("r",     "Refresh data"),
                ("Enter", "Select / open project"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Static("Recon & Surface (Tab 2)", classes="help-section")
            for key, desc in [
                ("↑ / ↓",       "Navigate tree"),
                ("← / →",       "Collapse / expand node"),
                ("Enter",       "Select node for details"),
                ("r",           "Refresh surface"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Static("Findings (Tab 3)", classes="help-section")
            for key, desc in [
                ("↑ / ↓",    "Navigate findings"),
                ("Enter",    "Select finding for detail"),
                ("c",        "Filter by critical"),
                ("1",        "Clear filters"),
                ("e",        "Export to JSON"),
                ("r",        "Refresh"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Static("Logs (Tab 4)", classes="help-section")
            for key, desc in [
                ("c", "Clear log view"),
                ("r", "Refresh all"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Static("Config (Tab 5)", classes="help-section")
            for key, desc in [
                ("r",     "Refresh health status"),
            ]:
                yield Static(f"  [bold cyan]{key:<18}[/bold cyan] {desc}", classes="help-row")

            yield Rule()
            yield Static("[dim]Press [bold cyan]?[/bold cyan] or [bold cyan]Escape[/bold cyan] to close[/dim]", id="close-hint")

    def action_close(self) -> None:
        self.dismiss()

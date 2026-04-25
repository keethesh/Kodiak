"""
Logs & Execution Tab — Single-agent status, execution log, tool table, engagement notes.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import DataTable, RichLog, Static

from kodiak.tui.state import app_state, AgentStatus


_LEVEL_MARKUP = {
    "ERROR":   "[bold red]",
    "WARN":    "[yellow]",
    "WARNING": "[yellow]",
    "INFO":    "[blue]",
    "SUCCESS": "[bold green]",
    "DEBUG":   "[dim]",
}

_NOTE_CAT_ICONS = {
    "recon_intel":  "🔭",
    "behavioral":   "🧠",
    "attack_hint":  "⚡",
    "dead_end":     "🚫",
    "general":      "📌",
}


class LogsView(Static):
    """Logs & Execution tab — single-agent monitoring."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
        Binding("c", "clear_logs", "Clear", show=False),
    ]

    DEFAULT_CSS = """
    LogsView {
        layout: vertical;
        height: 1fr;
    }

    #agent-status-bar {
        height: 3;
        background: $surface;
        border: round #45475a;
        padding: 0 2;
        margin-bottom: 1;
        align: left middle;
    }

    #agent-status-bar.running {
        border: round #a6e3a1;
        color: #a6e3a1;
    }

    #agent-status-bar.idle {
        border: round #45475a;
        color: #a6adc8;
    }

    #agent-status-bar.error {
        border: round #f38ba8;
        color: #f38ba8;
    }

    #logs-main {
        height: 1fr;
        margin-bottom: 1;
    }

    #execution-log-panel {
        width: 2fr;
        height: 1fr;
        border: round #45475a;
        margin-right: 1;
    }

    #tool-table-panel {
        width: 1fr;
        height: 1fr;
        border: round #45475a;
    }

    #notes-panel {
        height: 12;
        border: round #45475a;
    }

    .panel-title {
        dock: top;
        height: 1;
        background: #313244;
        color: $primary;
        text-align: center;
        text-style: bold;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        # Agent status bar
        yield Static("", id="agent-status-bar")

        with Horizontal(id="logs-main"):
            # Execution log (rich scrollable)
            with Container(id="execution-log-panel"):
                yield Static("📜 Execution Log", classes="panel-title")
                yield RichLog(id="exec-log", wrap=True, markup=True, highlight=True)

            # Tool execution table
            with Container(id="tool-table-panel"):
                yield Static("🔨 Tools Run", classes="panel-title")
                yield DataTable(
                    id="tool-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )

        # Engagement notes at the bottom
        with Container(id="notes-panel"):
            yield Static("📌 Engagement Notes", classes="panel-title")
            yield RichLog(id="notes-log", wrap=True, markup=True)

    def on_mount(self) -> None:
        self._setup_tool_table()
        self._refresh_all()

        app_state.subscribe("agent_status_changed", lambda _: self._refresh_agent_bar())
        app_state.subscribe("scan_status_changed",  lambda _: self._refresh_all())
        app_state.subscribe("scan_projection_updated", lambda _: self._refresh_all())

    def _setup_tool_table(self) -> None:
        t = self.query_one("#tool-table", DataTable)
        t.add_column("Tool",   key="tool",   width=16)
        t.add_column("Target", key="target", width=20)
        t.add_column("Status", key="status", width=10)
        t.add_column("Time",   key="time",   width=9)

    def _refresh_all(self) -> None:
        self._refresh_agent_bar()
        self._refresh_logs()
        self._refresh_tool_table()
        self._refresh_notes()

    def _refresh_agent_bar(self) -> None:
        w = self.query_one("#agent-status-bar", Static)
        scan = app_state.get_current_scan()

        if not scan or not scan.agents:
            w.update("[dim]No active agent — start a scan to begin[/dim]")
            w.remove_class("running", "idle", "error")
            w.add_class("idle")
            return

        # Single agent
        agent = next(iter(scan.agents.values()))
        status = agent.status

        icons = {
            AgentStatus.THINKING:  "🟢",
            AgentStatus.EXECUTING: "🟢",
            AgentStatus.IDLE:      "🟡",
            AgentStatus.WAITING:   "🟡",
            AgentStatus.COMPLETED: "✅",
            AgentStatus.FAILED:    "🔴",
            AgentStatus.PAUSED:    "⏸",
        }
        icon = icons.get(status, "❓")
        task = agent.current_task or "idle"
        task_str = task[:60] + "…" if len(task) > 60 else task

        last_ts = agent.last_activity
        since = f"  [dim]Last active: {last_ts.strftime('%H:%M:%S')}[/dim]" if last_ts else ""
        finds = f"  ⚑ {agent.findings_count} findings" if agent.findings_count else ""

        w.update(
            f"{icon} [bold]{agent.name}[/bold]  ·  {status.value.upper()}"
            f"  [dim]|[/dim]  {task_str}{finds}{since}"
        )

        w.remove_class("running", "idle", "error")
        if status in (AgentStatus.THINKING, AgentStatus.EXECUTING):
            w.add_class("running")
        elif status == AgentStatus.FAILED:
            w.add_class("error")
        else:
            w.add_class("idle")

    def _refresh_logs(self) -> None:
        log_widget = self.query_one("#exec-log", RichLog)
        # Don't clear — RichLog is append-only; we only add new entries.
        # On full refresh, clear and repopulate from state
        log_widget.clear()

        scan = app_state.get_current_scan()
        if not scan:
            log_widget.write("[dim]No scan running[/dim]")
            return

        for entry in self._entries_from_projection(scan):
            level = entry["level"].upper()
            msg = entry["message"]
            src = entry["source"]
            ts_s = entry["time"]

            mk = _LEVEL_MARKUP.get(level, "")
            end = mk.replace("[", "[/").rstrip("]") + "]" if mk else ""
            src_part = f"[dim]{src}[/dim]  " if src else ""
            log_widget.write(
                f"[dim]{ts_s}[/dim]  {mk}[{level}]{end}  {src_part}{msg}"
            )

    def _refresh_tool_table(self) -> None:
        t = self.query_one("#tool-table", DataTable)
        t.clear()

        scan = app_state.get_current_scan()
        if not scan:
            return

        for rec in reversed(list(getattr(scan, "attempts", []) or [])):  # most recent first
            tool = str(rec.get("tool", "?"))[:14]
            target = str(rec.get("target", "?"))[:18]
            status = str(rec.get("status", "?"))
            ts_s = "—"

            status_icons = {"success": "✅", "failed": "❌", "timeout": "⏱", "error": "🔴"}
            icon = status_icons.get(status, "")
            t.add_row(tool, target, f"{icon}{status}", ts_s)

    def _refresh_notes(self) -> None:
        notes_widget = self.query_one("#notes-log", RichLog)
        notes_widget.clear()

        scan = app_state.get_current_scan()
        if not scan:
            return

        notes = list(getattr(scan, "engagement_notes", []) or [])
        if not notes:
            notes_widget.write("[dim]No engagement notes yet[/dim]")
            return

        for note in notes:
            cat = str(note.get("category", "general"))
            icon = _NOTE_CAT_ICONS.get(cat, "📌")
            content = str(note.get("content", ""))
            target = str(note.get("target", ""))
            target_part = f"[dim]({target})[/dim]  " if target and target != "*" else ""
            notes_widget.write(f"{icon} [bold]{cat.replace('_', ' ').title()}:[/bold]  {target_part}{content}")

    def action_refresh(self) -> None:
        self._refresh_all()

    def action_clear_logs(self) -> None:
        self.query_one("#exec-log", RichLog).clear()
        self.notify("Log cleared", timeout=2)

    def append_log_entry(self, level: str, message: str, source: str = "") -> None:
        """External API: append a single log line without full refresh."""
        from datetime import datetime
        log_widget = self.query_one("#exec-log", RichLog)
        ts_s = datetime.now().strftime("%H:%M:%S")
        mk = _LEVEL_MARKUP.get(level.upper(), "")
        end = mk.replace("[", "[/").rstrip("]") + "]" if mk else ""
        src_part = f"[dim]{source}[/dim]  " if source else ""
        log_widget.write(
            f"[dim]{ts_s}[/dim]  {mk}[{level.upper()}]{end}  {src_part}{message}"
        )

    def _entries_from_projection(self, scan):
        entries = []
        for event in getattr(scan, "recent_events", []) or []:
            payload = event.get("payload", {}) or {}
            msg = payload.get("content") or payload.get("message") or payload.get("summary")
            if not msg:
                msg = f"{event.get('type', 'event').replace('_', ' ')}"
            entries.append({
                "level": "INFO" if "failed" not in event.get("type", "") else "ERROR",
                "message": str(msg),
                "source": str(payload.get("tool") or event.get("entity_type", "scan")),
                "time": "",
            })
        return entries

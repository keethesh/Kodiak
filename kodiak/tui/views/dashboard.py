"""
Dashboard View — Live stats, severity breakdown, activity feed, project selector.
"""

from datetime import datetime
from typing import List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import DataTable, Static

from kodiak.tui.state import app_state, ScanStatus, ScanState


# ── Severity bar helpers ──────────────────────────────────────────────────────

_SEV_COLORS = {
    "critical": "[bold red]",
    "high":     "[orange1]",
    "medium":   "[yellow]",
    "low":      "[blue]",
    "info":     "[dim white]",
}

_SEV_ORDER = ["critical", "high", "medium", "low", "info"]


def _sev_markup(sev: str, count: int) -> str:
    color = _SEV_COLORS.get(sev, "[white]")
    end = color.replace("[", "[/").rstrip("]") + "]"
    # rich markup: colour block with label
    return f"{color}● {sev.upper()} {count}{end}"


def _phase_markup(phase: str) -> str:
    colors = {
        "recon":       "[cyan]",
        "enumeration": "[green]",
        "vuln_scan":   "[yellow]",
        "exploitation":"[red]",
        "reporting":   "[magenta]",
    }
    c = colors.get(phase, "[white]")
    end = c.replace("[", "[/").rstrip("]") + "]"
    return f"{c}◆ {phase.upper()}{end}"


class DashboardView(Static):
    """Main dashboard tab — always-visible overview."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    DashboardView {
        layout: vertical;
        height: 1fr;
    }

    #dash-top {
        height: auto;
    }

    #scan-header {
        height: 3;
        background: $surface;
        border: round #45475a;
        padding: 0 2;
        margin-bottom: 1;
    }

    #stats-row {
        height: 7;
        margin-bottom: 1;
    }

    .stat-card {
        background: $surface;
        border: round #45475a;
        padding: 1 2;
        width: 1fr;
        height: 7;
        content-align: center middle;
        text-align: center;
    }

    #sev-row {
        height: 5;
        background: $surface;
        border: round #45475a;
        padding: 1 2;
        margin-bottom: 1;
        align: left middle;
    }

    #sev-label {
        width: 14;
        color: #a6adc8;
    }

    #dash-bottom {
        height: 1fr;
        margin-bottom: 0;
    }

    #activity-panel {
        width: 1fr;
        height: 1fr;
        border: round #45475a;
        margin-right: 1;
    }

    #projects-panel {
        width: 1fr;
        height: 1fr;
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

    #activity-log-list {
        height: 1fr;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        # Scan header bar
        yield Static("", id="scan-header")

        # Stats row: 4 cards
        with Horizontal(id="stats-row"):
            yield Static("", id="stat-findings", classes="stat-card")
            yield Static("", id="stat-nodes", classes="stat-card")
            yield Static("", id="stat-tools", classes="stat-card")
            yield Static("", id="stat-phase", classes="stat-card")

        # Severity breakdown bar
        with Horizontal(id="sev-row"):
            yield Static("Severity: ", id="sev-label")
            yield Static("", id="sev-breakdown")

        # Bottom: activity feed + project list
        with Horizontal(id="dash-bottom"):
            with Container(id="activity-panel"):
                yield Static("📋 Activity Feed", classes="panel-title")
                yield Static("", id="activity-content")

            with Container(id="projects-panel"):
                yield Static("📁 Projects", classes="panel-title")
                yield DataTable(id="projects-table", cursor_type="row", zebra_stripes=True)

    def on_mount(self) -> None:
        self._setup_projects_table()
        self._refresh_all()

        # Subscribe to state changes
        app_state.subscribe("project_added",      lambda _: self._refresh_all())
        app_state.subscribe("project_updated",    lambda _: self._refresh_all())
        app_state.subscribe("project_removed",    lambda _: self._refresh_all())
        app_state.subscribe("scan_status_changed",lambda _: self._refresh_all())
        app_state.subscribe("finding_added",      lambda _: self._refresh_findings())
        app_state.subscribe("scan_projection_updated", lambda _: self._refresh_all())

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_projects_table(self) -> None:
        t = self.query_one("#projects-table", DataTable)
        t.add_column("Project", key="name",   width=22)
        t.add_column("Target",  key="target", width=24)
        t.add_column("Status",  key="status", width=14)
        t.add_column("Findings",key="finds",  width=9)
        t.add_column("Updated", key="upd",    width=12)

    # ── Refresh helpers ───────────────────────────────────────────────────────

    def _refresh_all(self) -> None:
        self._refresh_scan_header()
        self._refresh_stats()
        self._refresh_findings()
        self._refresh_activity()
        self._refresh_projects_table()

    def _refresh_scan_header(self) -> None:
        w = self.query_one("#scan-header", Static)
        scan   = app_state.get_current_scan()
        project= app_state.get_current_project()

        if not scan or not project:
            w.update("[dim]No active scan — press [bold cyan]n[/bold cyan] to start one[/dim]")
            w.remove_class("running", "paused", "failed", "completed")
            return

        icons = {
            ScanStatus.RUNNING:   ("🟢", "running"),
            ScanStatus.PAUSED:    ("🟡", "paused"),
            ScanStatus.FAILED:    ("🔴", "failed"),
            ScanStatus.COMPLETED: ("✅", "completed"),
            ScanStatus.PENDING:   ("⏳", "pending"),
        }
        icon, css_cls = icons.get(scan.status, ("❓", ""))
        elapsed = ""
        if scan.started_at:
            delta = (datetime.now() - scan.started_at.replace(tzinfo=None)).seconds
            elapsed = f"  ⏱ {delta // 60}m {delta % 60}s"

        agent_info = ""
        if scan.agents:
            a = next(iter(scan.agents.values()))
            agent_info = f"  🤖 {a.name}  {a.current_task or 'idle'}"

        queue = getattr(scan, "work_queue", {}) or {}
        queue_info = ""
        if queue:
            running = queue.get("running", 0) + queue.get("claimed", 0)
            pending = queue.get("pending", 0)
            queue_info = f"  📋 {running} active / {pending} queued"

        w.update(
            f"{icon} [bold]{project.name}[/bold]  →  {scan.name}  "
            f"[dim]|[/dim]  {scan.status.value.title()}{elapsed}{agent_info}{queue_info}"
        )
        w.remove_class("running", "paused", "failed", "completed", "pending")
        if css_cls:
            w.add_class(css_cls)

    def _refresh_stats(self) -> None:
        scan = app_state.get_current_scan()

        findings = len(scan.findings) if scan else 0
        nodes    = (getattr(scan, "node_count", 0) or len(scan.nodes)) if scan else 0
        queue    = getattr(scan, "work_queue", {}) if scan else {}
        tools    = (queue.get("completed", 0) + queue.get("failed", 0)) if scan else 0
        phase    = self._current_phase(scan) if scan else "—"
        degraded = len(getattr(scan, "degraded_components", []) or []) if scan else 0

        self.query_one("#stat-findings", Static).update(
            f"[bold cyan]{findings}[/bold cyan]\n[dim]Findings[/dim]"
        )
        self.query_one("#stat-nodes", Static).update(
            f"[bold cyan]{nodes}[/bold cyan]\n[dim]Nodes[/dim]"
        )
        self.query_one("#stat-tools", Static).update(
            f"[bold cyan]{tools}[/bold cyan]\n[dim]Tools Run[/dim]"
        )
        self.query_one("#stat-phase", Static).update(
            f"[bold magenta]{phase}[/bold magenta]\n[dim]{'Phase' if degraded == 0 else f'Phase • {degraded} degraded'}[/dim]"
        )

    def _refresh_findings(self) -> None:
        scan = app_state.get_current_scan()
        if not scan:
            self.query_one("#sev-breakdown", Static).update("[dim]—[/dim]")
            return

        counts: dict = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in scan.findings:
            sev = getattr(f, "severity", "info")
            if hasattr(sev, "value"):
                sev = sev.value
            counts[sev] = counts.get(sev, 0) + 1

        parts = []
        for sev in _SEV_ORDER:
            n = counts.get(sev, 0)
            parts.append(_sev_markup(sev, n))

        self.query_one("#sev-breakdown", Static).update("    ".join(parts))

    def _refresh_activity(self) -> None:
        w = self.query_one("#activity-content", Static)
        scan = app_state.get_current_scan()
        if scan and getattr(scan, "recent_events", None):
            lines = []
            degraded = list(getattr(scan, "degraded_components", []) or [])
            if degraded:
                names = ", ".join(component.get("component", "?") for component in degraded[:3])
                lines.append(f"⚠️ degraded components: {names}")
            for entry in scan.recent_events[:12]:
                event_type = str(entry.get("type", "")).replace("_", " ")
                payload = entry.get("payload", {}) or {}
                if "technique" in payload:
                    detail = payload["technique"]
                elif "title" in payload:
                    detail = payload["title"]
                elif "tool" in payload:
                    detail = payload["tool"]
                else:
                    detail = entry.get("entity_type") or "event"
                lines.append(f"• {event_type}: {detail}")
            w.update("\n".join(lines))
            return
        all_scans: List[ScanState] = []
        for p in app_state.get_all_projects():
            all_scans.extend(app_state.get_scans_for_project(p.id))

        if not all_scans:
            w.update("[dim]No recent activity. Press [bold cyan]n[/bold cyan] to start a scan.[/dim]")
            return

        lines = []
        all_scans.sort(key=lambda s: s.created_at, reverse=True)
        for historic_scan in all_scans[:15]:
            p = app_state.get_project(historic_scan.project_id)
            pname = p.name if p else "?"
            icon = {
                ScanStatus.RUNNING:   "🟢",
                ScanStatus.COMPLETED: "✅",
                ScanStatus.FAILED:    "🔴",
                ScanStatus.PAUSED:    "🟡",
                ScanStatus.PENDING:   "⏳",
            }.get(historic_scan.status, "  ")
            ts = historic_scan.created_at.strftime("%m-%d %H:%M")
            lines.append(f"{icon} [dim]{ts}[/dim]  [bold]{pname}[/bold] — {historic_scan.name}")

        w.update("\n".join(lines))

    def _refresh_projects_table(self) -> None:
        t = self.query_one("#projects-table", DataTable)
        t.clear()

        projects = app_state.get_all_projects()
        if not projects:
            return

        for p in projects:
            scans  = app_state.get_scans_for_project(p.id)
            latest = scans[-1] if scans else None
            status = "No scans"
            finds  = 0
            if latest:
                status = latest.status.value.title()
                finds  = len(latest.findings)
                status_icons = {
                    "running": "🟢", "completed": "✅",
                    "failed": "🔴", "paused": "🟡", "pending": "⏳",
                }
                status = f"{status_icons.get(latest.status.value, '')} {status}"

            upd = p.updated_at.strftime("%m-%d %H:%M") if hasattr(p, "updated_at") else "—"
            t.add_row(
                p.name,
                getattr(p, "target", "N/A") or "N/A",
                status,
                str(finds),
                upd,
                key=p.id,
            )

    def _current_phase(self, scan: ScanState) -> str:
        """Infer the visible scan phase from recent events."""
        for entry in getattr(scan, "recent_events", []) or []:
            event_type = entry.get("type")
            payload = entry.get("payload", {}) or {}
            if event_type == "directive_added" and payload.get("type") == "DirectiveType.PHASE_ADVANCE":
                content = payload.get("content", {}) or {}
                return content.get("new_phase") or content.get("phase") or "—"
            phase = payload.get("phase")
            if phase:
                return str(phase)
        return getattr(scan, "phase", "—")

    def action_refresh(self) -> None:
        self._refresh_all()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key:
            pid = str(event.row_key.value)
            app_state.set_current_project(pid)
            scans = app_state.get_scans_for_project(pid)
            if scans:
                app_state.set_current_scan(scans[-1].id)
            self._refresh_all()
            self.notify("Project selected — use 🏠 Dashboard to manage, 🔒 Findings to review", timeout=3)

"""
Findings Tab View — Split-pane: findings list (left) + finding detail (right).
"""

from typing import Optional, Any
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Label, Static, Button
from loguru import logger

from kodiak.tui.state import app_state

_SEV_ICONS = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🔵",
    "info":     "⚪",
}

_SEV_MARKUP = {
    "critical": "[bold red]CRITICAL[/bold red]",
    "high":     "[orange1]HIGH[/orange1]",
    "medium":   "[yellow]MEDIUM[/yellow]",
    "low":      "[blue]LOW[/blue]",
    "info":     "[dim]INFO[/dim]",
}


class FindingsView(Static):
    """Findings tab — split-pane findings browser with inline detail."""

    BINDINGS = [
        Binding("r",       "refresh",         "Refresh",  show=False),
        Binding("1",       "filter_all",       "All",      show=False),
        Binding("c",       "filter_critical",  "Critical", show=False),
        Binding("e",       "export_json",      "Export",   show=False),
    ]

    DEFAULT_CSS = """
    FindingsView {
        layout: vertical;
        height: 1fr;
    }

    #sev-summary {
        height: 3;
        background: $surface;
        border-bottom: solid $surface1;
        padding: 0 2;
        align: left middle;
        margin-bottom: 1;
    }

    #findings-layout {
        height: 1fr;
    }

    #findings-list-panel {
        width: 2fr;
        height: 1fr;
        border: round $surface1;
        margin-right: 1;
    }

    #finding-detail-panel {
        width: 3fr;
        height: 1fr;
        border: round $surface1;
    }

    #finding-detail-scroll {
        height: 1fr;
        padding: 1 2;
    }

    #export-bar {
        height: 3;
        align: right middle;
        margin-top: 1;
        padding: 0 1;
    }

    .panel-title {
        dock: top;
        height: 1;
        background: $surface0;
        color: $primary;
        text-align: center;
        text-style: bold;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._filter_sev: Optional[str] = None
        self._selected_finding: Optional[Any] = None

    def compose(self) -> ComposeResult:
        # Severity summary bar
        yield Static("", id="sev-summary")

        # Split pane: list left, detail right
        with Horizontal(id="findings-layout"):
            with Container(id="findings-list-panel"):
                yield Static("🔒 Findings", classes="panel-title")
                yield DataTable(
                    id="findings-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )

            with Container(id="finding-detail-panel"):
                yield Static("📄 Finding Detail", classes="panel-title")
                yield Static(
                    "[dim]Select a finding to see details[/dim]",
                    id="finding-detail-content",
                )

        # Export bar
        with Horizontal(id="export-bar"):
            yield Button("⬇ JSON",     id="btn-export-json",     variant="default")
            yield Button("⬇ Markdown", id="btn-export-md",       variant="default")

    def on_mount(self) -> None:
        self._setup_table()
        self._refresh_all()
        app_state.subscribe("finding_added", lambda _: self._refresh_all())

    def _setup_table(self) -> None:
        t = self.query_one("#findings-table", DataTable)
        t.add_column("Sev",    key="sev",    width=4)
        t.add_column("Title",  key="title",  width=32)
        t.add_column("Target", key="target", width=22)
        t.add_column("Tool",   key="tool",   width=14)
        t.add_column("Time",   key="time",   width=12)

    def _refresh_all(self) -> None:
        self._refresh_summary()
        self._refresh_table()

    def _refresh_summary(self) -> None:
        w = self.query_one("#sev-summary", Static)
        scan = app_state.get_current_scan()
        if not scan:
            w.update("[dim]No scan selected[/dim]")
            return

        counts: dict = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
        for f in scan.findings:
            sev = getattr(f, "severity", "info")
            if hasattr(sev, "value"):
                sev = sev.value
            counts[sev] = counts.get(sev, 0) + 1

        total = sum(counts.values())
        parts = [f"[bold]{total}[/bold] findings:"]
        for sev, n in counts.items():
            if n:
                mk = _SEV_MARKUP.get(sev, sev)
                parts.append(f"{mk} {n}")

        w.update("  ".join(parts))

    def _refresh_table(self) -> None:
        t = self.query_one("#findings-table", DataTable)
        t.clear()

        scan = app_state.get_current_scan()
        if not scan:
            return

        # Sort by severity then time
        _ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        findings = sorted(
            scan.findings,
            key=lambda f: (
                _ORDER.get(getattr(f, "severity", "info") if isinstance(getattr(f, "severity", "info"), str)
                           else getattr(f, "severity", "info").value, 4),
            ),
        )

        for f in findings:
            sev = getattr(f, "severity", "info")
            if hasattr(sev, "value"):
                sev = sev.value

            if self._filter_sev and sev != self._filter_sev:
                continue

            icon  = _SEV_ICONS.get(sev, "⚪")
            title = getattr(f, "title", "?")[:30]
            target= (getattr(f, "target", "") or "")[:20]
            tool  = (getattr(f, "tool",   "") or "")[:12]
            ts    = getattr(f, "created_at", None)
            ts_s  = ts.strftime("%m-%d %H:%M") if ts else "—"
            fid   = str(getattr(f, "id", title))

            t.add_row(icon, title, target, tool, ts_s, key=fid)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if not event.row_key:
            return
        self._show_detail_by_key(str(event.row_key.value))

    def _show_detail_by_key(self, key: str) -> None:
        scan = app_state.get_current_scan()
        if not scan:
            return

        finding = None
        for f in scan.findings:
            if str(getattr(f, "id", "")) == key or getattr(f, "title", "") == key:
                finding = f
                break

        if not finding:
            return

        self._selected_finding = finding
        self._render_detail(finding)

    def _render_detail(self, f: Any) -> None:
        w = self.query_one("#finding-detail-content", Static)

        sev  = getattr(f, "severity", "info")
        if hasattr(sev, "value"):
            sev = sev.value
        sev_mk = _SEV_MARKUP.get(sev, sev.upper())

        lines = []
        lines.append(f"[bold white]{getattr(f, 'title', '?')}[/bold white]")
        lines.append(f"Severity: {sev_mk}")
        target = getattr(f, "target", "") or ""
        if target:
            lines.append(f"Target:   [cyan]{target}[/cyan]")
        tool = getattr(f, "tool", "") or ""
        if tool:
            lines.append(f"Tool:     [dim]{tool}[/dim]")
        ts = getattr(f, "created_at", None)
        if ts:
            lines.append(f"Found:    [dim]{ts.strftime('%Y-%m-%d %H:%M')}[/dim]")

        lines.append("")
        desc = getattr(f, "description", "") or ""
        if desc:
            lines.append("[bold]Description[/bold]")
            lines.append(desc[:800])

        vec = getattr(f, "vector", "") or ""
        if vec:
            lines.append("")
            lines.append(f"[bold]Vector[/bold]  {vec}")

        exp_steps = getattr(f, "exploitation_steps", "") or ""
        if exp_steps:
            lines.append("")
            lines.append("[bold]Exploitation Steps[/bold]")
            lines.append(exp_steps[:600])

        poc = getattr(f, "poc", "") or ""
        if poc:
            lines.append("")
            lines.append("[bold]Proof of Concept[/bold]")
            lines.append(f"[dim]{poc[:800]}[/dim]")

        proof = getattr(f, "proof", "") or ""
        if proof and proof != poc:
            lines.append("")
            lines.append("[bold]Proof[/bold]")
            lines.append(f"[dim]{proof[:600]}[/dim]")

        impact = getattr(f, "impact", "") or ""
        if impact:
            lines.append("")
            lines.append("[bold]Impact[/bold]")
            lines.append(impact[:400])

        rem = getattr(f, "remediation", "") or ""
        if rem:
            lines.append("")
            lines.append("[bold]Remediation[/bold]")
            lines.append(rem[:500])

        raw = getattr(f, "raw_evidence", "") or ""
        if raw:
            lines.append("")
            lines.append("[bold]Raw Evidence[/bold]")
            lines.append(f"[dim]{raw[:800]}[/dim]")

        w.update("\n".join(lines))

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_refresh(self) -> None:
        self._filter_sev = None
        self._refresh_all()

    def action_filter_critical(self) -> None:
        self._filter_sev = "critical" if self._filter_sev != "critical" else None
        self._refresh_table()

    def action_filter_all(self) -> None:
        self._filter_sev = None
        self._refresh_table()

    def action_export_json(self) -> None:
        self._do_export("json")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export-json":
            self._do_export("json")
        elif event.button.id == "btn-export-md":
            self._do_export("markdown")

    def _do_export(self, fmt: str) -> None:
        import json
        from pathlib import Path
        from datetime import datetime

        scan = app_state.get_current_scan()
        if not scan:
            self.notify("No active scan to export", severity="warning")
            return

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"kodiak_findings_{now}"

        if fmt == "json":
            records = []
            for f in scan.findings:
                sev = getattr(f, "severity", "info")
                if hasattr(sev, "value"):
                    sev = sev.value
                records.append({
                    "title":       getattr(f, "title", ""),
                    "severity":    sev,
                    "target":      getattr(f, "target", ""),
                    "description": getattr(f, "description", ""),
                    "poc":         getattr(f, "poc", ""),
                    "remediation": getattr(f, "remediation", ""),
                    "tool":        getattr(f, "tool", ""),
                })
            out = Path(f"{fname}.json")
            out.write_text(json.dumps(records, indent=2, default=str))
            self.notify(f"Exported {len(records)} findings → {out}", timeout=5)

        elif fmt == "markdown":
            lines = [f"# Kodiak Findings — {now}\n"]
            _ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
            sorted_findings = sorted(
                scan.findings,
                key=lambda f: _ORDER.get(
                    (getattr(f, "severity", "info").value
                     if hasattr(getattr(f, "severity", "info"), "value")
                     else getattr(f, "severity", "info")), 4
                )
            )
            for f in sorted_findings:
                sev = getattr(f, "severity", "info")
                if hasattr(sev, "value"):
                    sev = sev.value
                icon = _SEV_ICONS.get(sev, "")
                lines.append(f"## {icon} {getattr(f, 'title', 'Unknown')} — {sev.upper()}")
                t = getattr(f, "target", "")
                if t:
                    lines.append(f"**Target:** `{t}`  ")
                lines.append(f"\n{getattr(f, 'description', '')}\n")
                poc = getattr(f, "poc", "")
                if poc:
                    lines.append(f"**PoC:**\n```\n{poc}\n```\n")
                rem = getattr(f, "remediation", "")
                if rem:
                    lines.append(f"**Remediation:** {rem}\n")
                lines.append("---\n")
            out = Path(f"{fname}.md")
            out.write_text("\n".join(lines))
            self.notify(f"Exported findings → {out}", timeout=5)

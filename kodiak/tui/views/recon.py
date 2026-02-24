"""
Recon & Surface View — Attack surface tree, node details, tool attempts.
"""

from typing import Optional, Any, Dict
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import DataTable, Label, Static, Tree
from textual.widgets.tree import TreeNode
from loguru import logger

from kodiak.tui.state import app_state


class ReconView(Static):
    """Recon & Attack Surface tab — explore discovered assets."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    ReconView {
        layout: vertical;
        height: 1fr;
    }

    #recon-top {
        height: 1fr;
    }

    #surface-tree-panel {
        width: 2fr;
        height: 1fr;
        border: round $surface1;
        margin-right: 1;
    }

    #node-detail-panel {
        width: 1fr;
        height: 1fr;
        border: round $surface1;
    }

    #node-detail-content {
        padding: 1 2;
        height: 1fr;
    }

    #attempts-panel {
        height: 12;
        border: round $surface1;
        margin-top: 1;
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

    # Node type icons
    _TYPE_ICONS = {
        "domain": "🌐",
        "host":   "🖥",
        "ip":     "🖥",
        "port":   "🔌",
        "service":"🔧",
        "url":    "🔗",
        "directory":"📁",
        "file":   "📄",
        "vulnerability":"🔍",
    }

    def compose(self) -> ComposeResult:
        with Horizontal(id="recon-top"):
            with Container(id="surface-tree-panel"):
                yield Static("🌐 Attack Surface", classes="panel-title")
                yield Tree("Target", id="surface-tree")

            with Container(id="node-detail-panel"):
                yield Static("📋 Node Detail", classes="panel-title")
                yield Static(
                    "[dim]Select a node to see details[/dim]",
                    id="node-detail-content",
                )

        with Container(id="attempts-panel"):
            yield Static("🔨 Tool Attempts", classes="panel-title")
            yield DataTable(
                id="attempts-table",
                cursor_type="row",
                zebra_stripes=True,
            )

    def on_mount(self) -> None:
        self._setup_attempts_table()
        self._refresh_all()

        app_state.subscribe("node_added",     lambda _: self._refresh_tree())
        app_state.subscribe("scan_status_changed", lambda _: self._refresh_all())

    def _setup_attempts_table(self) -> None:
        t = self.query_one("#attempts-table", DataTable)
        t.add_column("Tool",    key="tool",   width=18)
        t.add_column("Target",  key="target", width=28)
        t.add_column("Status",  key="status", width=12)
        t.add_column("Reason",  key="reason", width=34)
        t.add_column("Time",    key="time",   width=12)

    def _refresh_all(self) -> None:
        self._refresh_tree()
        self._refresh_attempts()

    def _refresh_tree(self) -> None:
        tree = self.query_one("#surface-tree", Tree)
        tree.clear()

        scan = app_state.get_current_scan()
        if not scan or not scan.nodes:
            tree.root.set_label("[dim]No assets discovered yet[/dim]")
            return

        # Group nodes by type for a hierarchical view
        buckets: Dict[str, list] = {}
        for n in scan.nodes:
            ntype = getattr(n, "type", "unknown")
            buckets.setdefault(ntype, []).append(n)

        # Top-level = domains/hosts, then ports/services nested
        # Build flat tree grouped by type
        for ntype, nodes in sorted(buckets.items()):
            icon = self._TYPE_ICONS.get(ntype, "▸")
            parent = tree.root.add(
                f"{icon} {ntype.upper()} ({len(nodes)})",
                data={"type": "group", "ntype": ntype},
                expand=True,
            )
            for node in nodes:
                name = getattr(node, "name", "?")
                node_id = str(getattr(node, "id", ""))
                leaf = parent.add_leaf(
                    f"  {name}",
                    data={"type": "node", "node": node, "id": node_id},
                )

    def _refresh_attempts(self) -> None:
        t = self.query_one("#attempts-table", DataTable)
        t.clear()

        scan = app_state.get_current_scan()
        if not scan:
            return

        # Attempts are stored in app_state or come from the DB via core_bridge
        # We surface them through the scan's nodes or from a separate attempts list
        attempts = getattr(scan, "attempts", [])
        for a in attempts:
            tool   = getattr(a, "tool",   "?")
            target = getattr(a, "target", "?")
            status = getattr(a, "status", "?")
            reason = getattr(a, "reason", "") or ""
            ts     = getattr(a, "created_at", None)
            ts_str = ts.strftime("%H:%M:%S") if ts else "—"
            reason  = reason[:40] + "…" if len(reason) > 40 else reason

            status_icons = {"success": "✅", "failed": "❌", "timeout": "⏱", "error": "🔴"}
            icon = status_icons.get(status, "")
            t.add_row(tool, target, f"{icon} {status}", reason, ts_str, key=str(getattr(a, "id", tool)))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or data.get("type") != "node":
            return

        node = data.get("node")
        if not node:
            return

        detail = self.query_one("#node-detail-content", Static)
        lines = []
        lines.append(f"[bold cyan]{getattr(node, 'name', '?')}[/bold cyan]")
        lines.append(f"[dim]Type:[/dim]  {getattr(node, 'type', '?')}")
        lines.append(f"[dim]Label:[/dim] {getattr(node, 'label', '?')}")

        props = getattr(node, "properties", {}) or {}
        if props:
            lines.append("")
            lines.append("[bold]Properties:[/bold]")
            for k, v in props.items():
                v_str = str(v)
                if len(v_str) > 60:
                    v_str = v_str[:57] + "…"
                lines.append(f"  [dim]{k}:[/dim] {v_str}")

        ts = getattr(node, "created_at", None)
        if ts:
            lines.append("")
            lines.append(f"[dim]Discovered:[/dim] {ts.strftime('%Y-%m-%d %H:%M')}")

        scanned = getattr(node, "scanned", False)
        lines.append(f"[dim]Scanned:[/dim] {'✅ Yes' if scanned else '❌ No'}")

        detail.update("\n".join(lines))

    def action_refresh(self) -> None:
        self._refresh_all()

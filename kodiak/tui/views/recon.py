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
        border: round #45475a;
        margin-right: 1;
    }

    #node-detail-panel {
        width: 1fr;
        height: 1fr;
        border: round #45475a;
    }

    #node-detail-content {
        padding: 1 2;
        height: 1fr;
    }

    #attempts-panel {
        height: 12;
        border: round #45475a;
        margin-top: 1;
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
        app_state.subscribe("scan_projection_updated", lambda _: self._refresh_all())

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
        if not scan:
            tree.root.set_label("[dim]No scan selected[/dim]")
            return

        if not scan.nodes:
            projection_nodes = self._surface_nodes_from_projection(scan)
            if projection_nodes:
                tree.root.set_label("Target")
                for group_name, nodes in projection_nodes.items():
                    parent = tree.root.add(
                        f"{self._TYPE_ICONS.get(group_name, '▸')} {group_name.upper()} ({len(nodes)})",
                        data={"type": "group", "ntype": group_name},
                        expand=True,
                    )
                    for node in nodes:
                        parent.add_leaf(
                            f"  {node['name']}",
                            data={"type": "projection-node", "node": node},
                        )
                tree.root.expand()
                return
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
        attempts = list(getattr(scan, "attempts", []) or [])
        if not attempts:
            attempts = self._attempts_from_projection(scan)
        for a in attempts:
            tool   = a.get("tool", "?") if isinstance(a, dict) else getattr(a, "tool", "?")
            target = a.get("target", "?") if isinstance(a, dict) else getattr(a, "target", "?")
            status = a.get("status", "?") if isinstance(a, dict) else getattr(a, "status", "?")
            reason = (a.get("reason", "") if isinstance(a, dict) else getattr(a, "reason", "")) or ""
            ts     = a.get("created_at") if isinstance(a, dict) else getattr(a, "created_at", None)
            ts_str = ts.strftime("%H:%M:%S") if ts else "—"
            reason  = reason[:40] + "…" if len(reason) > 40 else reason

            status_icons = {"success": "✅", "failed": "❌", "timeout": "⏱", "error": "🔴"}
            icon = status_icons.get(status, "")
            row_id = a.get("id", tool) if isinstance(a, dict) else getattr(a, "id", tool)
            t.add_row(tool, target, f"{icon} {status}", reason, ts_str, key=str(row_id))

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data or data.get("type") not in {"node", "projection-node"}:
            return

        node = data.get("node")
        if not node:
            return

        detail = self.query_one("#node-detail-content", Static)
        lines = []
        if isinstance(node, dict):
            lines.append(f"[bold cyan]{node.get('name', '?')}[/bold cyan]")
            lines.append(f"[dim]Type:[/dim]  {node.get('type', '?')}")
            lines.append(f"[dim]Label:[/dim] {node.get('label', 'Derived from projection')}")
            props = node.get("properties", {}) or {}
            ts = None
            scanned = bool(node.get("scanned", False))
        else:
            lines.append(f"[bold cyan]{getattr(node, 'name', '?')}[/bold cyan]")
            lines.append(f"[dim]Type:[/dim]  {getattr(node, 'type', '?')}")
            lines.append(f"[dim]Label:[/dim] {getattr(node, 'label', '?')}")
            props = getattr(node, "properties", {}) or {}
            ts = getattr(node, "created_at", None)
            scanned = getattr(node, "scanned", False)

        if props:
            lines.append("")
            lines.append("[bold]Properties:[/bold]")
            for k, v in props.items():
                v_str = str(v)
                if len(v_str) > 60:
                    v_str = v_str[:57] + "…"
                lines.append(f"  [dim]{k}:[/dim] {v_str}")

        if ts:
            lines.append("")
            lines.append(f"[dim]Discovered:[/dim] {ts.strftime('%Y-%m-%d %H:%M')}")

        lines.append(f"[dim]Scanned:[/dim] {'✅ Yes' if scanned else '❌ No'}")

        detail.update("\n".join(lines))

    def action_refresh(self) -> None:
        self._refresh_all()

    def _attempts_from_projection(self, scan):
        rows = []
        for event in getattr(scan, "recent_events", []) or []:
            if event.get("type") != "attempt_recorded":
                continue
            payload = event.get("payload", {}) or {}
            rows.append(
                {
                    "tool": str(payload.get("tool", "?")),
                    "target": str(payload.get("target", "?")),
                    "status": str(payload.get("status", "?")),
                    "reason": str(payload.get("reason", "") or ""),
                    "created_at": None,
                    "id": event.get("entity_id"),
                }
            )
        return rows

    def _surface_nodes_from_projection(self, scan):
        groups: Dict[str, list] = {}
        for capability in getattr(scan, "capabilities", []) or []:
            capability_type = capability.get("type", "capability")
            target = capability.get("target")
            if not target:
                continue
            node_type = "url" if "surface" in capability_type or target.startswith("http") else "service"
            groups.setdefault(node_type, []).append(
                {
                    "name": target,
                    "type": node_type,
                    "label": capability_type.replace("_", " "),
                    "properties": {"key": capability.get("key", "")},
                    "scanned": True,
                }
            )
        return groups

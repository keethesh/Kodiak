"""
Config Tab — System info, health status, scan configuration overview.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static
from loguru import logger

from kodiak.core.config import settings


class ConfigView(Static):
    """Config tab — system health, settings, and diagnostics."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    ConfigView {
        layout: vertical;
        height: 1fr;
        padding: 1 2;
    }

    #config-columns {
        height: 1fr;
    }

    #col-left {
        width: 1fr;
        margin-right: 2;
    }

    #col-right {
        width: 1fr;
    }

    .config-section {
        border: round #45475a;
        padding: 1 2;
        margin-bottom: 1;
        height: auto;
    }

    .config-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }

    .config-row {
        margin-bottom: 0;
    }

    .config-key {
        color: #a6adc8;
        width: 18;
    }

    .config-val {
        color: $text;
    }

    .ok { color: #a6e3a1; }
    .warn { color: #f9e2af; }
    .err { color: #f38ba8; }

    #action-bar {
        height: auto;
        align: left middle;
        margin-top: 1;
        padding: 1 0;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="config-columns"):
            with Vertical(id="col-left"):
                with Container(classes="config-section"):
                    yield Static("⚙️  System Info", classes="config-title")
                    yield Static("", id="sys-info")

                with Container(classes="config-section"):
                    yield Static("🔑  LLM Configuration", classes="config-title")
                    yield Static("", id="llm-info")

            with Vertical(id="col-right"):
                with Container(classes="config-section"):
                    yield Static("🏥  Health Status", classes="config-title")
                    yield Static("", id="health-info")

                with Container(classes="config-section"):
                    yield Static("🐳  Docker Status", classes="config-title")
                    yield Static("", id="docker-info")

        with Horizontal(id="action-bar"):
            yield Button("🔄 Refresh Health", id="btn-refresh", variant="default")
            yield Button("🩺 Run Doctor",     id="btn-doctor",  variant="default")

    def on_mount(self) -> None:
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._render_sys_info()
        self._render_llm_info()
        self._render_health()
        self._render_docker()

    def _kv(self, key: str, val: str, ok: bool = True, warn: bool = False) -> str:
        cls = "err" if not ok else ("warn" if warn else "ok")
        return f"[dim]{key:<18}[/dim] [{cls}]{val}[/{cls}]"

    def _render_sys_info(self) -> None:
        w = self.query_one("#sys-info", Static)
        lines = [
            self._kv("Version",  settings.VERSION),
            self._kv("Database", str(settings.database_url)[:60]),
        ]
        w.update("\n".join(lines))

    def _render_llm_info(self) -> None:
        w = self.query_one("#llm-info", Static)
        model = settings.llm_model
        provider = settings.llm_provider
        api_key = settings.get_resolved_api_key()
        key_status = "Set" if api_key else "Missing"
        key_ok = bool(api_key)

        lines = [
            self._kv("Provider", str(provider), ok=provider == "openrouter"),
            self._kv("Model", str(model)),
            self._kv("API Key", key_status, ok=key_ok),
            self._kv("Planner Model", settings.planner_model),
            self._kv("Analyst Model", settings.analyst_model),
        ]

        max_iter = getattr(settings, "MAX_ITERATIONS", None)
        if max_iter:
            lines.append(self._kv("Max Iterations", str(max_iter)))

        w.update("\n".join(lines))

    def _render_health(self) -> None:
        w = self.query_one("#health-info", Static)

        from kodiak.tui.core_bridge import get_core_bridge
        cb = get_core_bridge()

        if not cb:
            w.update(self._kv("Core Bridge", "Not initialized", ok=False))
            return

        status = cb.get_health_status() if hasattr(cb, "get_health_status") else {}
        lines = []

        db_ok = status.get("database_healthy", False)
        lines.append(self._kv("Database",       "✅ Connected" if db_ok else "❌ Disconnected", ok=db_ok))

        initialized = status.get("initialized", False)
        lines.append(self._kv("Bridge",         "✅ Initialized" if initialized else "⚠ Not initialized", ok=initialized, warn=not initialized))

        db_type = status.get("database_type", "unknown")
        lines.append(self._kv("DB Type",        db_type))

        w.update("\n".join(lines))

    def _render_docker(self) -> None:
        w = self.query_one("#docker-info", Static)
        import shutil
        docker = shutil.which("docker")
        if docker:
            w.update(self._kv("Docker CLI", f"✅ {docker}"))
        else:
            w.update(self._kv("Docker CLI", "❌ Not found in PATH", ok=False))

    def action_refresh(self) -> None:
        self._refresh_all()
        self.notify("Config refreshed", timeout=2)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-refresh":
            self._refresh_all()
            self.notify("Health status refreshed", timeout=2)
        elif event.button.id == "btn-doctor":
            self.notify("Run 'kodiak doctor' in your terminal for full diagnostics", timeout=6)

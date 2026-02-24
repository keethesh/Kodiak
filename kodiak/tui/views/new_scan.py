"""
New Scan — Modal screen overlay for creating a new scan.
"""

import re
from typing import Optional
from datetime import datetime
from uuid import uuid4

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Static
from textual.validation import Validator, ValidationResult
from loguru import logger

from kodiak.tui.state import app_state, ProjectState, ScanState, ScanStatus


class TargetValidator(Validator):
    """Validates target URL/IP/domain input."""

    URL_PATTERN = re.compile(
        r"^https?://"
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
        r"localhost|"
        r"\d{1,3}(?:\.\d{1,3}){3})"
        r"(?::\d+)?(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    DOMAIN_PATTERN = re.compile(
        r"^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}$",
        re.IGNORECASE,
    )
    IP_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

    def validate(self, value: str) -> ValidationResult:
        v = value.strip()
        if not v:
            return self.failure("Target is required")
        if (self.URL_PATTERN.match(v)
                or self.DOMAIN_PATTERN.match(v)
                or self.IP_PATTERN.match(v)):
            return self.success()
        return self.failure("Enter a valid URL, domain, or IP address")


class NewScanModal(ModalScreen):
    """Modal overlay for creating a new scan."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Cancel", priority=True),
        Binding("ctrl+s",  "submit",       "Start Scan"),
    ]

    CSS = """
    NewScanModal {
        align: center middle;
    }

    #modal-box {
        background: $surface;
        border: round $primary;
        padding: 2 3;
        width: 70;
        height: auto;
        max-height: 90%;
    }

    #modal-title {
        color: $primary;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    .field-label {
        color: #a6adc8;
        margin-top: 1;
        margin-bottom: 0;
    }

    #project-mode {
        height: 3;
        margin-bottom: 1;
    }

    #existing-projects {
        border: round #45475a;
        height: 7;
        padding: 0 1;
        margin-bottom: 1;
    }

    #agent-count-row {
        height: 3;
        margin: 1 0;
    }

    .agent-btn {
        min-width: 5;
        margin-right: 1;
    }

    .agent-btn.-primary {
        background: $accent;
        color: #1e1e2e;
    }

    #error-msg {
        color: #f38ba8;
        margin-top: 1;
        height: auto;
    }

    #button-row {
        align: right middle;
        height: 3;
        margin-top: 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._agent_count = 1

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Static("🔍 New Scan", id="modal-title")

            # Project mode toggle
            yield Label("Project", classes="field-label")
            with RadioSet(id="project-mode"):
                yield RadioButton("New project", id="radio-new",      value=True)
                yield RadioButton("Existing project", id="radio-existing")

            # New project name (conditional)
            yield Label("Project Name", classes="field-label", id="label-project-name")
            yield Input(
                placeholder="e.g. HackerOne Target",
                id="input-project-name",
            )

            # Existing project selector (shown when radio-existing active)
            yield Label("Select Project", classes="field-label", id="label-existing")
            from textual.widgets import DataTable as DT
            yield DT(id="existing-projects", cursor_type="row")

            # Target
            yield Label("Target (URL / domain / IP)", classes="field-label")
            yield Input(
                placeholder="e.g. https://target.com or 192.168.1.1",
                id="input-target",
                validators=[TargetValidator()],
            )

            # Instructions
            yield Label("Instructions (optional)", classes="field-label")
            yield Input(
                placeholder="Focus on auth bypass, API endpoints…",
                id="input-instructions",
            )

            # Error message
            yield Static("", id="error-msg")

            with Horizontal(id="button-row"):
                yield Button("Cancel",     id="btn-cancel",  variant="default")
                yield Button("🚀 Start Scan", id="btn-submit", variant="success")

    def on_mount(self) -> None:
        # Hide existing projects panel by default
        self._set_mode("new")
        self.query_one("#input-project-name", Input).focus()

    def _set_mode(self, mode: str) -> None:
        show_new = (mode == "new")
        try:
            self.query_one("#input-project-name", Input).display = show_new
            self.query_one("#label-project-name", Label).display = show_new
            self.query_one("#existing-projects").display = not show_new
            self.query_one("#label-existing", Label).display = not show_new
        except Exception:
            pass

        if mode == "existing":
            self._populate_existing_projects()

    def _populate_existing_projects(self) -> None:
        from textual.widgets import DataTable as DT
        t = self.query_one("#existing-projects", DT)
        if not t.columns:
            t.add_column("Name",   width=24)
            t.add_column("Target", width=26)
        t.clear()
        for p in app_state.get_all_projects():
            t.add_row(p.name, getattr(p, "target", "") or "N/A", key=p.id)

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        mode = "existing" if event.index == 1 else "new"
        self._set_mode(mode)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.action_dismiss_modal()
        elif event.button.id == "btn-submit":
            self.action_submit()

    def action_dismiss_modal(self) -> None:
        self.dismiss()

    def action_submit(self) -> None:
        self._do_submit()

    def _do_submit(self) -> None:
        err = self.query_one("#error-msg", Static)
        err.update("")

        target_input = self.query_one("#input-target", Input)
        target = target_input.value.strip()

        if not target:
            err.update("⚠ Target is required")
            target_input.focus()
            return

        if not target_input.is_valid:
            err.update("⚠ Enter a valid URL, domain, or IP address")
            target_input.focus()
            return

        instructions = self.query_one("#input-instructions", Input).value.strip()

        # Determine project mode
        radio_set = self.query_one("#project-mode", RadioSet)
        use_existing = (radio_set.pressed_index == 1)

        if use_existing:
            from textual.widgets import DataTable as DT
            existing_tbl = self.query_one("#existing-projects", DT)
            if existing_tbl.cursor_row < 0:
                err.update("⚠ Select an existing project")
                return
            row = existing_tbl.get_row_at(existing_tbl.cursor_row)
            project_name = str(row[0])
            project = next(
                (p for p in app_state.get_all_projects() if p.name == project_name), None
            )
            if not project:
                err.update("⚠ Could not find selected project")
                return
            project_id = project.id
        else:
            project_name = self.query_one("#input-project-name", Input).value.strip()
            if not project_name:
                err.update("⚠ Project name is required")
                self.query_one("#input-project-name", Input).focus()
                return
            # Create project in state (core_bridge will persist it)
            from kodiak.database.models import Project
            from datetime import timezone
            new_proj = Project(name=project_name)
            project_id = str(new_proj.id)
            project_state = ProjectState(
                id=project_id,
                name=project_name,
                description="",
                target=target,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            app_state.add_project_state(project_state)

        # Kick off scan via core_bridge
        cb = self.app.core_bridge
        if cb:
            self.app.call_later(
                cb.create_scan,
                project_id,
                f"Scan {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                target,
                1,      # Always 1 agent
                instructions,
            )
        else:
            # Fallback: create scan in state only (no DB)
            scan_id = str(uuid4())
            from kodiak.tui.state import ScanState, ScanStatus, AgentState, AgentStatus
            scan_state = ScanState(
                id=scan_id,
                project_id=str(project_id),
                name=f"Scan {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                target=target,
                status=ScanStatus.PENDING,
                agent_count=1,
                created_at=datetime.now(),
            )
            app_state.add_scan_state(scan_state)
            app_state.set_current_scan(scan_id)

        self.notify("Scan queued — check Dashboard for status", timeout=4)
        self.dismiss()
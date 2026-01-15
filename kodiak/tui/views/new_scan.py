"""
NewScanScreen View

Screen for creating new security scans with custom parameters.
Implements input validation and form submission.
"""

import re
from typing import Optional
from datetime import datetime
from uuid import uuid4
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static, Input, Button, Label
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from textual.validation import Validator, ValidationResult
from loguru import logger

from kodiak.tui.state import app_state, ProjectState, ScanState, ScanStatus


class TargetValidator(Validator):
    """Validator for target URL/IP input"""
    
    # Regex patterns for validation
    URL_PATTERN = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    IP_PATTERN = re.compile(
        r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
        r'(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)'
        r'(?:/(?:3[0-2]|[12]?[0-9]))?$'  # Optional CIDR notation
    )
    
    DOMAIN_PATTERN = re.compile(
        r'^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}$',
        re.IGNORECASE
    )
    
    def validate(self, value: str) -> ValidationResult:
        """Validate the target input"""
        if not value or not value.strip():
            return self.failure("Target cannot be empty")
        
        value = value.strip()
        
        # Check if it's a valid URL
        if self.URL_PATTERN.match(value):
            return self.success()
        
        # Check if it's a valid IP or CIDR
        if self.IP_PATTERN.match(value):
            return self.success()
        
        # Check if it's a valid domain
        if self.DOMAIN_PATTERN.match(value):
            return self.success()
        
        return self.failure("Invalid target. Enter a valid URL, IP address, or domain.")


class NewScanScreen(Screen):
    """
    New scan screen - create new security scans
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "submit", "Submit"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    NewScanScreen {
        layout: vertical;
        align: center middle;
    }
    
    #form-container {
        width: 80;
        height: auto;
        border: solid $primary;
        padding: 2;
        background: $surface;
    }
    
    #form-header {
        height: auto;
        margin-bottom: 2;
    }
    
    #form-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    
    #form-subtitle {
        text-align: center;
        color: $text-muted;
    }
    
    .form-section {
        height: auto;
        margin-bottom: 1;
        border: solid $surface;
        padding: 1;
    }
    
    .section-title {
        color: $primary;
        text-style: bold;
        margin-bottom: 1;
    }
    
    .form-row {
        height: auto;
        margin-bottom: 1;
    }
    
    .form-label {
        height: 1;
        margin-bottom: 0;
        color: $text-muted;
    }
    
    .form-input {
        height: 3;
        margin-bottom: 1;
    }
    
    .form-input.-invalid {
        border: solid $error;
    }
    
    #scan-type-container {
        height: auto;
        margin-bottom: 1;
    }
    
    #scan-type-buttons {
        height: 3;
    }
    
    .scan-type-btn {
        width: 15;
        margin-right: 1;
    }
    
    .scan-type-btn.-selected {
        background: $accent;
        color: $background;
    }
    
    #agent-count-container {
        height: auto;
        margin-bottom: 1;
    }
    
    #agent-count-label {
        height: 1;
        color: $text-muted;
    }
    
    #agent-count-buttons {
        height: 3;
    }
    
    .agent-btn {
        width: 5;
        margin-right: 1;
    }
    
    .agent-btn.-selected {
        background: $primary;
        color: $background;
    }
    
    #button-container {
        height: 3;
        margin-top: 2;
        align: center middle;
    }
    
    #submit-btn {
        margin-right: 2;
        background: $accent;
        color: $background;
        min-width: 16;
    }
    
    #cancel-btn {
        min-width: 12;
    }
    
    #error-message {
        height: 2;
        color: $error;
        text-align: center;
        margin-top: 1;
    }
    
    #instructions-input {
        height: 5;
    }
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_count = 3
        self.error_message = ""
    
    def compose(self) -> ComposeResult:
        """Compose the new scan form"""
        yield Header()
        
        with Container(id="form-container"):
            yield Static("🔍 Create New Scan", id="form-title")
            
            # Project name
            with Vertical(classes="form-row"):
                yield Label("Project Name:", classes="form-label")
                yield Input(
                    placeholder="Enter project name...",
                    id="name-input",
                    classes="form-input"
                )
            
            # Target
            with Vertical(classes="form-row"):
                yield Label("Target (URL, IP, or Domain):", classes="form-label")
                yield Input(
                    placeholder="https://example.com or 192.168.1.1",
                    id="target-input",
                    classes="form-input",
                    validators=[TargetValidator()]
                )
            
            # Instructions
            with Vertical(classes="form-row"):
                yield Label("Instructions (optional):", classes="form-label")
                yield Input(
                    placeholder="Special instructions for the agents...",
                    id="instructions-input",
                    classes="form-input"
                )
            
            # Agent count
            with Vertical(id="agent-count-container"):
                yield Label("Number of Agents:", id="agent-count-label")
                with Horizontal(id="agent-count-buttons"):
                    for i in range(1, 6):
                        btn = Button(str(i), id=f"agent-{i}", classes="agent-btn")
                        if i == self.agent_count:
                            btn.add_class("-selected")
                        yield btn
            
            # Error message
            yield Static("", id="error-message")
            
            # Buttons
            with Horizontal(id="button-container"):
                yield Button("Create Scan", id="submit-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn", variant="default")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Focus the name input on mount"""
        name_input = self.query_one("#name-input", Input)
        name_input.focus()
    
    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        button_id = event.button.id
        
        if button_id == "submit-btn":
            self._submit_form()
        elif button_id == "cancel-btn":
            self.action_cancel()
        elif button_id and button_id.startswith("agent-"):
            # Agent count button
            count = int(button_id.split("-")[1])
            self._set_agent_count(count)
    
    def _set_agent_count(self, count: int):
        """Set the agent count and update button styles"""
        self.agent_count = count
        
        # Update button styles
        for i in range(1, 6):
            btn = self.query_one(f"#agent-{i}", Button)
            if i == count:
                btn.add_class("-selected")
            else:
                btn.remove_class("-selected")
    
    def _submit_form(self):
        """Validate and submit the form"""
        name_input = self.query_one("#name-input", Input)
        target_input = self.query_one("#target-input", Input)
        instructions_input = self.query_one("#instructions-input", Input)
        error_display = self.query_one("#error-message", Static)
        
        # Get values
        name = name_input.value.strip()
        target = target_input.value.strip()
        instructions = instructions_input.value.strip()
        
        # Validate name
        if not name:
            error_display.update("❌ Project name is required")
            name_input.focus()
            return
        
        # Validate target
        if not target:
            error_display.update("❌ Target is required")
            target_input.focus()
            return
        
        # Validate target format
        validator = TargetValidator()
        result = validator.validate(target)
        if not result.is_valid:
            error_display.update(f"❌ {result.failure_descriptions[0]}")
            target_input.focus()
            return
        
        # Clear error
        error_display.update("")
        
        # Create project and scan
        try:
            self._create_scan(name, target, instructions)
        except Exception as e:
            logger.error(f"Failed to create scan: {e}")
            error_display.update(f"❌ Failed to create scan: {str(e)}")
    
    def _create_scan(self, name: str, target: str, instructions: str):
        """Create a new project and scan"""
        now = datetime.now()
        
        # Create project
        project = ProjectState(
            id=str(uuid4()),
            name=name,
            description=instructions or f"Security scan of {target}",
            target=target,
            created_at=now,
            updated_at=now
        )
        
        # Create scan
        scan = ScanState(
            id=str(uuid4()),
            project_id=project.id,
            name=f"Scan of {target}",
            target=target,
            status=ScanStatus.PENDING,
            agent_count=self.agent_count,
            created_at=now
        )
        
        # Add to state
        app_state.projects[project.id] = project
        app_state.scans[scan.id] = scan
        app_state.set_current_project(project.id)
        app_state.set_current_scan(scan.id)
        
        logger.info(f"Created project '{name}' with scan targeting '{target}'")
        
        # Navigate to mission control
        self.notify(f"Created scan for {target}", severity="information")
        
        from kodiak.tui.views.mission_control import MissionControlScreen
        self.app.switch_screen(MissionControlScreen())
    
    def action_quit(self) -> None:
        """Quit the application (Global shortcut)"""
        self.app.exit()
    
    def action_go_home(self) -> None:
        """Go to home screen (Global shortcut)"""
        # Pop all screens and go to home
        while len(self.app.screen_stack) > 1:
            self.app.pop_screen()
        
        # If we're not on home, push home screen
        from kodiak.tui.views.home import HomeScreen
        if not isinstance(self.app.screen, HomeScreen):
            self.app.push_screen(HomeScreen())
    
    def action_show_help(self) -> None:
        """Show help overlay (Global shortcut)"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def action_cancel(self) -> None:
        """Cancel and return to home"""
        self.app.pop_screen()
    
    def action_submit(self) -> None:
        """Submit the form"""
        self._submit_form()
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Clear error message when input changes"""
        error_display = self.query_one("#error-message", Static)
        error_display.update("")
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in inputs"""
        # Move to next input or submit
        if event.input.id == "name-input":
            self.query_one("#target-input", Input).focus()
        elif event.input.id == "target-input":
            self.query_one("#instructions-input", Input).focus()
        elif event.input.id == "instructions-input":
            self._submit_form()
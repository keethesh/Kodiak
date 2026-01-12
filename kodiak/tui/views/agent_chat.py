"""
AgentChatScreen View

Direct communication interface with individual agents.
Supports chat history, message input, and agent switching.
"""

from typing import Optional, List
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Header, Footer, Static
from textual.containers import Vertical, Horizontal, Container
from textual.binding import Binding
from loguru import logger

from kodiak.tui.state import app_state, AgentState, AgentStatus
from kodiak.tui.widgets import ChatHistory


class AgentChatScreen(Screen):
    """
    Agent Chat - direct communication with agents
    
    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8
    """
    
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("h", "go_home", "Home", priority=True),
        Binding("escape", "go_back", "Back"),
        Binding("left", "prev_agent", "Prev Agent"),
        Binding("right", "next_agent", "Next Agent"),
        Binding("question_mark", "show_help", "Help"),
    ]
    
    CSS = """
    AgentChatScreen {
        layout: vertical;
    }
    
    #agent-header {
        dock: top;
        height: 3;
        background: $primary;
        padding: 0 1;
    }
    
    #agent-name {
        text-style: bold;
        height: 1;
    }
    
    #agent-status {
        height: 1;
    }
    
    #agent-task {
        height: 1;
        color: $text-muted;
    }
    
    #chat-container {
        height: 1fr;
        margin: 1;
    }
    
    #agent-nav {
        dock: bottom;
        height: 1;
        background: $surface;
        text-align: center;
    }
    """
    
    def __init__(self, agent_id: str, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.agent_ids: List[str] = []
        self.current_agent_index = 0
    
    def compose(self) -> ComposeResult:
        """Compose the agent chat layout"""
        yield Header()
        
        # Agent header
        with Container(id="agent-header"):
            yield Static("", id="agent-name")
            yield Static("", id="agent-status")
            yield Static("", id="agent-task")
        
        # Chat container
        with Container(id="chat-container"):
            yield ChatHistory(agent_id=self.agent_id, id="chat-history")
        
        # Agent navigation hint
        yield Static("← → to switch agents | ESC to go back", id="agent-nav")
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Initialize the agent chat screen"""
        self._load_agent_list()
        self._update_agent_header()
        
        # Focus the chat input
        chat_history = self.query_one("#chat-history", ChatHistory)
        chat_history.focus_input()
        
        # Subscribe to agent status changes
        app_state.subscribe("agent_status_changed", self._on_agent_status_changed)
    
    def _load_agent_list(self):
        """Load the list of agents for navigation"""
        current_scan = app_state.get_current_scan()
        if current_scan:
            self.agent_ids = list(current_scan.agents.keys())
            
            # Find current agent index
            if self.agent_id in self.agent_ids:
                self.current_agent_index = self.agent_ids.index(self.agent_id)
    
    def _update_agent_header(self):
        """Update the agent header display"""
        agent_name = self.query_one("#agent-name", Static)
        agent_status = self.query_one("#agent-status", Static)
        agent_task = self.query_one("#agent-task", Static)
        
        current_scan = app_state.get_current_scan()
        if not current_scan:
            agent_name.update("No scan selected")
            agent_status.update("")
            agent_task.update("")
            return
        
        agent = current_scan.agents.get(self.agent_id)
        if not agent:
            agent_name.update(f"Agent {self.agent_id} not found")
            agent_status.update("")
            agent_task.update("")
            return
        
        # Update name
        agent_name.update(f"🤖 {agent.name}")
        
        # Update status with icon
        status_icon = self._get_status_icon(agent.status)
        agent_status.update(f"Status: {status_icon} {agent.status.value.title()}")
        
        # Update task
        if agent.current_task:
            agent_task.update(f"Task: {agent.current_task}")
        else:
            agent_task.update("Task: Idle")
    
    def _get_status_icon(self, status: AgentStatus) -> str:
        """Get status icon for agent"""
        status_icons = {
            AgentStatus.IDLE: "⚪",
            AgentStatus.THINKING: "🟡",
            AgentStatus.EXECUTING: "🟢",
            AgentStatus.WAITING: "🔵",
            AgentStatus.COMPLETED: "✅",
            AgentStatus.FAILED: "🔴",
            AgentStatus.PAUSED: "⏸️",
        }
        return status_icons.get(status, "❓")
    
    def _on_agent_status_changed(self, event):
        """Handle agent status changes"""
        data = event.data
        if data.get("agent_id") == self.agent_id:
            self._update_agent_header()
    
    def _switch_to_agent(self, agent_id: str):
        """Switch to a different agent"""
        self.agent_id = agent_id
        
        # Update chat history
        chat_history = self.query_one("#chat-history", ChatHistory)
        chat_history.set_agent(agent_id)
        
        # Update header
        self._update_agent_header()
        
        # Update index
        if agent_id in self.agent_ids:
            self.current_agent_index = self.agent_ids.index(agent_id)
    
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
    
    def action_go_back(self) -> None:
        """Return to mission control"""
        self.app.pop_screen()
    
    def action_prev_agent(self) -> None:
        """Switch to previous agent"""
        if not self.agent_ids:
            return
        
        self.current_agent_index = (self.current_agent_index - 1) % len(self.agent_ids)
        new_agent_id = self.agent_ids[self.current_agent_index]
        self._switch_to_agent(new_agent_id)
        self.notify(f"Switched to Agent {new_agent_id}")
    
    def action_next_agent(self) -> None:
        """Switch to next agent"""
        if not self.agent_ids:
            return
        
        self.current_agent_index = (self.current_agent_index + 1) % len(self.agent_ids)
        new_agent_id = self.agent_ids[self.current_agent_index]
        self._switch_to_agent(new_agent_id)
        self.notify(f"Switched to Agent {new_agent_id}")
    
    def action_show_help(self) -> None:
        """Show help overlay"""
        from kodiak.tui.views.help import HelpScreen
        self.app.push_screen(HelpScreen())
    
    def on_message_sent(self, event) -> None:
        """Handle message sent from chat history"""
        # TODO: Send message to actual agent via core bridge
        logger.info(f"Message sent to agent {event.agent_id}: {event.content}")
        
        # For now, simulate a response
        chat_history = self.query_one("#chat-history", ChatHistory)
        chat_history.simulate_agent_thinking(event.agent_id)
        
        # Simulate delayed response
        self.set_timer(1.0, lambda: self._simulate_response(event.content))
    
    def _simulate_response(self, user_message: str):
        """Simulate an agent response (for demo purposes)"""
        chat_history = self.query_one("#chat-history", ChatHistory)
        
        # Simple response based on message content
        if "scan" in user_message.lower():
            response = "I'm currently scanning the target. I'll report any findings as I discover them."
        elif "status" in user_message.lower():
            response = "I'm actively working on the assigned tasks. Current focus is on reconnaissance."
        elif "help" in user_message.lower():
            response = "I can help with security testing. Ask me about specific vulnerabilities or targets."
        else:
            response = f"Understood. I'll take that into consideration for my analysis."
        
        chat_history.add_agent_response(response, self.agent_id)
"""
ChatHistory Widget

A widget that displays chat messages between user and agents.
Shows messages with timestamps and sender identification, supports scrolling.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass
from textual.widget import Widget
from textual.widgets import RichLog, Static, Input
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.message import Message
from rich.text import Text
from rich.panel import Panel
from rich.console import Console

from kodiak.tui.state import app_state, ScanState, AgentState


@dataclass
class ChatMessage:
    """Represents a single chat message"""
    timestamp: datetime
    sender: str  # "user" or agent_id
    content: str
    agent_id: Optional[str] = None
    message_type: str = "text"  # "text", "system", "error"
    
    def format_timestamp(self) -> str:
        """Format timestamp for display"""
        return self.timestamp.strftime("%H:%M:%S")
    
    def get_sender_display(self) -> str:
        """Get display name for sender"""
        if self.sender == "user":
            return "You"
        elif self.agent_id:
            return f"Agent-{self.agent_id}"
        else:
            return self.sender
    
    def get_sender_color(self) -> str:
        """Get color for sender"""
        if self.sender == "user":
            return "cyan"
        elif self.message_type == "system":
            return "yellow"
        elif self.message_type == "error":
            return "red"
        else:
            return "green"
    
    def to_rich_text(self) -> Text:
        """Convert to Rich Text object for display"""
        text = Text()
        
        # Timestamp
        text.append(f"[{self.format_timestamp()}] ", style="dim white")
        
        # Sender
        sender_display = self.get_sender_display()
        sender_color = self.get_sender_color()
        text.append(f"{sender_display}: ", style=f"bold {sender_color}")
        
        # Content
        if self.message_type == "error":
            text.append(self.content, style="red")
        elif self.message_type == "system":
            text.append(self.content, style="yellow italic")
        else:
            text.append(self.content, style="white")
        
        return text


class MessageSent(Message):
    """Message sent when user sends a chat message"""
    
    def __init__(self, content: str, agent_id: str) -> None:
        super().__init__()
        self.content = content
        self.agent_id = agent_id


class ChatHistory(Widget):
    """
    Widget that displays chat history between user and agents.
    Supports scrolling and message input.
    """
    
    DEFAULT_CSS = """
    ChatHistory {
        border: solid $primary;
        height: 100%;
        min-height: 10;
    }
    
    ChatHistory > Vertical {
        height: 100%;
    }
    
    ChatHistory .title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    
    ChatHistory .agent-info {
        dock: top;
        height: 1;
        background: $surface;
        color: $text;
        text-align: center;
        padding: 0 1;
    }
    
    ChatHistory RichLog {
        height: 1fr;
        border: none;
        scrollbar-gutter: stable;
        margin: 1 0;
    }
    
    ChatHistory .input-container {
        dock: bottom;
        height: 3;
        border: solid $primary;
        padding: 1;
    }
    
    ChatHistory Input {
        height: 1;
        border: none;
    }
    
    ChatHistory .empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """
    
    # Reactive properties
    current_agent: reactive[Optional[AgentState]] = reactive(None)
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    agent_id: reactive[Optional[str]] = reactive(None)
    
    def __init__(self, agent_id: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.agent_id = agent_id
        self.messages: List[ChatMessage] = []
        self.max_messages = 1000
        
        # Subscribe to state changes
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("agent_status_changed", self._on_agent_status_changed)
    
    def compose(self) -> ComposeResult:
        """Compose the chat history layout"""
        with Vertical():
            yield Static("Chat", classes="title", id="title")
            yield Static("", classes="agent-info", id="agent-info")
            yield RichLog(id="chat-display", auto_scroll=True, max_lines=self.max_messages)
            with Vertical(classes="input-container"):
                yield Static("Type your message and press Enter:", id="input-label")
                yield Input(placeholder="Message...", id="message-input")
    
    def on_mount(self) -> None:
        """Initialize chat history when mounted"""
        self.current_scan = app_state.get_current_scan()
        self._update_agent_info()
        self._add_system_message("Chat initialized. Start typing to communicate with the agent.")
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        self.current_scan = app_state.get_current_scan()
        self._update_agent_info()
    
    def _on_agent_status_changed(self, event):
        """Handle agent status change events"""
        data = event.data
        if (self.current_scan and 
            data.get("scan_id") == self.current_scan.id and 
            data.get("agent_id") == self.agent_id):
            self._update_agent_info()
    
    def _update_agent_info(self):
        """Update the agent information display"""
        agent_info = self.query_one("#agent-info", Static)
        title = self.query_one("#title", Static)
        
        if not self.agent_id or not self.current_scan:
            agent_info.update("No agent selected")
            title.update("Chat")
            self.current_agent = None
            return
        
        # Get agent from current scan
        agent = self.current_scan.agents.get(self.agent_id)
        self.current_agent = agent
        
        if not agent:
            agent_info.update(f"Agent-{self.agent_id} not found")
            title.update("Chat")
            return
        
        # Update title and info
        title.update(f"Chat - Agent-{self.agent_id}")
        
        status_icon = self._get_status_icon(agent.status)
        task_text = f" - {agent.current_task}" if agent.current_task else ""
        info_text = f"{status_icon} {agent.status.value.title()}{task_text}"
        
        agent_info.update(info_text)
    
    def _get_status_icon(self, status) -> str:
        """Get status icon for agent"""
        status_icons = {
            "idle": "⚪",
            "thinking": "🟡",
            "executing": "🟢",
            "waiting": "🔵",
            "completed": "✅",
            "failed": "🔴",
            "paused": "⏸️",
        }
        return status_icons.get(status.value if hasattr(status, 'value') else str(status), "❓")
    
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle message input submission"""
        if not self.agent_id:
            self._add_system_message("No agent selected. Cannot send message.")
            return
        
        content = event.value.strip()
        if not content:
            return
        
        # Clear input
        message_input = self.query_one("#message-input", Input)
        message_input.value = ""
        
        # Add user message to history
        self._add_user_message(content)
        
        # Post message sent event
        self.post_message(MessageSent(content, self.agent_id))
    
    def _add_user_message(self, content: str):
        """Add a user message to the chat"""
        message = ChatMessage(
            timestamp=datetime.now(),
            sender="user",
            content=content,
            agent_id=self.agent_id
        )
        self._add_message(message)
    
    def _add_agent_message(self, content: str, agent_id: str):
        """Add an agent message to the chat"""
        message = ChatMessage(
            timestamp=datetime.now(),
            sender=agent_id,
            content=content,
            agent_id=agent_id
        )
        self._add_message(message)
    
    def _add_system_message(self, content: str):
        """Add a system message to the chat"""
        message = ChatMessage(
            timestamp=datetime.now(),
            sender="system",
            content=content,
            message_type="system"
        )
        self._add_message(message)
    
    def _add_error_message(self, content: str):
        """Add an error message to the chat"""
        message = ChatMessage(
            timestamp=datetime.now(),
            sender="system",
            content=content,
            message_type="error"
        )
        self._add_message(message)
    
    def _add_message(self, message: ChatMessage):
        """Add a message to the chat history"""
        self.messages.append(message)
        
        # Trim messages if we exceed max
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
        
        # Update display
        chat_display = self.query_one("#chat-display", RichLog)
        chat_display.write(message.to_rich_text())
    
    def set_agent(self, agent_id: str):
        """Set the current agent for this chat"""
        if self.agent_id != agent_id:
            # Clear chat history when switching agents
            self.clear_chat()
            
        self.agent_id = agent_id
        self._update_agent_info()
        self._add_system_message(f"Now chatting with Agent-{agent_id}")
    
    def add_agent_response(self, content: str, agent_id: Optional[str] = None):
        """Add an agent response to the chat"""
        target_agent_id = agent_id or self.agent_id
        if not target_agent_id:
            self._add_error_message("Cannot add agent response: no agent selected")
            return
        
        if target_agent_id != self.agent_id:
            # Response from different agent, show as system message
            self._add_system_message(f"Agent-{target_agent_id}: {content}")
        else:
            self._add_agent_message(content, target_agent_id)
    
    def clear_chat(self):
        """Clear all chat messages"""
        self.messages.clear()
        chat_display = self.query_one("#chat-display", RichLog)
        chat_display.clear()
    
    def export_chat(self, filename: str) -> bool:
        """Export chat history to a file"""
        try:
            with open(filename, 'w') as f:
                f.write(f"Kodiak Chat Export - Agent-{self.agent_id}\n")
                f.write("=" * 50 + "\n\n")
                
                for message in self.messages:
                    f.write(f"[{message.timestamp.isoformat()}] ")
                    f.write(f"{message.get_sender_display()}: ")
                    f.write(f"{message.content}\n\n")
            
            self._add_system_message(f"Chat exported to {filename}")
            return True
            
        except Exception as e:
            self._add_error_message(f"Failed to export chat: {str(e)}")
            return False
    
    def get_message_count(self) -> int:
        """Get total number of messages"""
        return len(self.messages)
    
    def get_user_message_count(self) -> int:
        """Get number of user messages"""
        return sum(1 for msg in self.messages if msg.sender == "user")
    
    def get_agent_message_count(self) -> int:
        """Get number of agent messages"""
        return sum(1 for msg in self.messages if msg.sender != "user" and msg.message_type == "text")
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the chat"""
        chat_display = self.query_one("#chat-display", RichLog)
        chat_display.scroll_end()
    
    def scroll_to_top(self):
        """Scroll to the top of the chat"""
        chat_display = self.query_one("#chat-display", RichLog)
        chat_display.scroll_home()
    
    def focus_input(self):
        """Focus the message input field"""
        message_input = self.query_one("#message-input", Input)
        message_input.focus()
    
    def watch_agent_id(self, agent_id: Optional[str]) -> None:
        """React to agent ID changes"""
        self._update_agent_info()
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        self._update_agent_info()
    
    def simulate_agent_thinking(self, agent_id: Optional[str] = None):
        """Show that an agent is thinking (for testing/demo)"""
        target_agent_id = agent_id or self.agent_id
        if target_agent_id:
            self._add_system_message(f"Agent-{target_agent_id} is thinking...")
    
    def simulate_agent_response(self, response: str, agent_id: Optional[str] = None):
        """Simulate an agent response (for testing/demo)"""
        target_agent_id = agent_id or self.agent_id
        if target_agent_id:
            self.add_agent_response(response, target_agent_id)
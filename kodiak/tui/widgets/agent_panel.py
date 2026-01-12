"""
AgentPanel Widget

A widget that displays a list of agents with their status icons.
Supports selection and navigation.
"""

from typing import Optional, List, Dict
from textual.widget import Widget
from textual.widgets import ListView, ListItem, Static
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.app import ComposeResult
from textual.message import Message

from kodiak.tui.state import app_state, AgentState, AgentStatus, ScanState


class AgentSelected(Message):
    """Message sent when an agent is selected"""
    
    def __init__(self, agent_id: str, agent: AgentState) -> None:
        super().__init__()
        self.agent_id = agent_id
        self.agent = agent


class AgentItem(ListItem):
    """Individual agent list item"""
    
    def __init__(self, agent: AgentState, **kwargs):
        super().__init__(**kwargs)
        self.agent = agent
        self._update_content()
    
    def _update_content(self):
        """Update the agent item content"""
        status_icon = self._get_status_icon(self.agent.status)
        task_text = f" - {self.agent.current_task}" if self.agent.current_task else ""
        
        content = f"{status_icon} {self.agent.name}{task_text}"
        
        # Clear existing content and add new
        self.remove_children()
        self.mount(Static(content))
    
    def _get_status_icon(self, status: AgentStatus) -> str:
        """Get the appropriate icon for agent status"""
        status_icons = {
            AgentStatus.IDLE: "⚪",           # White circle for idle
            AgentStatus.THINKING: "🟡",       # Yellow circle for thinking
            AgentStatus.EXECUTING: "🟢",     # Green circle for active/executing
            AgentStatus.WAITING: "🔵",       # Blue circle for waiting
            AgentStatus.COMPLETED: "✅",     # Check mark for completed
            AgentStatus.FAILED: "🔴",        # Red circle for error/failed
            AgentStatus.PAUSED: "⏸️",        # Pause symbol for paused
        }
        return status_icons.get(status, "❓")
    
    def update_agent(self, agent: AgentState):
        """Update the agent data and refresh display"""
        self.agent = agent
        self._update_content()


class AgentPanel(Widget):
    """
    Panel that displays a list of agents with their status.
    Supports selection and navigation.
    """
    
    DEFAULT_CSS = """
    AgentPanel {
        border: solid $primary;
        height: 100%;
        min-height: 10;
    }
    
    AgentPanel > Vertical {
        height: 100%;
    }
    
    AgentPanel .title {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        text-align: center;
        text-style: bold;
    }
    
    AgentPanel ListView {
        height: 1fr;
        border: none;
    }
    
    AgentPanel ListItem {
        height: 1;
        padding: 0 1;
    }
    
    AgentPanel ListItem:hover {
        background: $primary 20%;
    }
    
    AgentPanel ListItem.-selected {
        background: $accent;
        color: $text-selected;
    }
    
    AgentPanel .empty {
        height: 100%;
        content-align: center middle;
        color: $text-muted;
        text-style: italic;
    }
    """
    
    # Reactive properties
    current_scan: reactive[Optional[ScanState]] = reactive(None)
    agents: reactive[List[AgentState]] = reactive([])
    selected_agent_id: reactive[Optional[str]] = reactive(None)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_items: Dict[str, AgentItem] = {}
        
        # Subscribe to state changes
        app_state.subscribe("current_scan_changed", self._on_scan_changed)
        app_state.subscribe("agent_added", self._on_agent_added)
        app_state.subscribe("agent_status_changed", self._on_agent_status_changed)
    
    def compose(self) -> ComposeResult:
        """Compose the agent panel layout"""
        with Vertical():
            yield Static("Agents", classes="title", id="title")
            yield ListView(id="agent-list")
    
    def on_mount(self) -> None:
        """Initialize agent panel when mounted"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_agents()
    
    def _on_scan_changed(self, event):
        """Handle scan change events"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_agents()
    
    def _on_agent_added(self, event):
        """Handle agent added events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            self._refresh_agents()
    
    def _on_agent_status_changed(self, event):
        """Handle agent status change events"""
        data = event.data
        if self.current_scan and data.get("scan_id") == self.current_scan.id:
            agent_id = data.get("agent_id")
            agent = data.get("agent")
            
            if agent_id in self.agent_items and agent:
                self.agent_items[agent_id].update_agent(agent)
    
    def _refresh_agents(self):
        """Refresh the agent list"""
        agent_list = self.query_one("#agent-list", ListView)
        
        # Clear existing items
        agent_list.clear()
        self.agent_items.clear()
        
        if not self.current_scan:
            self.agents = []
            agent_list.mount(Static("No scan selected", classes="empty"))
            return
        
        # Get agents from current scan
        agents = list(self.current_scan.agents.values())
        self.agents = agents
        
        if not agents:
            agent_list.mount(Static("No agents in scan", classes="empty"))
            return
        
        # Add agent items
        for agent in agents:
            agent_item = AgentItem(agent)
            self.agent_items[agent.id] = agent_item
            agent_list.append(agent_item)
        
        # Select first agent if none selected
        if agents and not self.selected_agent_id:
            self.selected_agent_id = agents[0].id
            agent_list.index = 0
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Handle agent selection"""
        if event.item and hasattr(event.item, 'agent'):
            agent = event.item.agent
            self.selected_agent_id = agent.id
            
            # Post agent selected message
            self.post_message(AgentSelected(agent.id, agent))
    
    def watch_current_scan(self, scan: Optional[ScanState]) -> None:
        """React to current scan changes"""
        self._refresh_agents()
    
    def watch_selected_agent_id(self, agent_id: Optional[str]) -> None:
        """React to selected agent changes"""
        if agent_id and agent_id in self.agent_items:
            agent_list = self.query_one("#agent-list", ListView)
            # Find the index of the selected agent
            for i, item in enumerate(agent_list.children):
                if hasattr(item, 'agent') and item.agent.id == agent_id:
                    agent_list.index = i
                    break
    
    def get_selected_agent(self) -> Optional[AgentState]:
        """Get the currently selected agent"""
        if self.selected_agent_id and self.current_scan:
            return self.current_scan.agents.get(self.selected_agent_id)
        return None
    
    def select_agent(self, agent_id: str) -> bool:
        """Select an agent by ID"""
        if agent_id in self.agent_items:
            self.selected_agent_id = agent_id
            return True
        return False
    
    def select_next_agent(self) -> bool:
        """Select the next agent in the list"""
        agent_list = self.query_one("#agent-list", ListView)
        if agent_list.index is not None and agent_list.index < len(agent_list.children) - 1:
            agent_list.action_cursor_down()
            return True
        return False
    
    def select_previous_agent(self) -> bool:
        """Select the previous agent in the list"""
        agent_list = self.query_one("#agent-list", ListView)
        if agent_list.index is not None and agent_list.index > 0:
            agent_list.action_cursor_up()
            return True
        return False
    
    def refresh(self):
        """Force refresh the agent panel"""
        self.current_scan = app_state.get_current_scan()
        self._refresh_agents()
    
    def get_agent_count(self) -> int:
        """Get the number of agents"""
        return len(self.agents)
    
    def get_active_agent_count(self) -> int:
        """Get the number of active agents"""
        return sum(1 for agent in self.agents 
                  if agent.status in [AgentStatus.EXECUTING, AgentStatus.THINKING])
    
    def get_status_summary(self) -> Dict[AgentStatus, int]:
        """Get a summary of agent statuses"""
        summary = {}
        for agent in self.agents:
            summary[agent.status] = summary.get(agent.status, 0) + 1
        return summary
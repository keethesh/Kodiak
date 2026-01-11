# Design Document: TUI Architecture Pivot

## Overview

This design document describes the architectural transformation of Kodiak from a frontend-backend (Next.js + FastAPI) architecture to a unified Terminal User Interface (TUI) application. The TUI will be built using Python's Textual framework, providing a modern, async-native terminal experience that directly integrates with the existing core components.

The key architectural change is eliminating the HTTP/WebSocket layer between the UI and core services, replacing it with direct Python function calls within a single process. This simplifies deployment, eliminates networking issues, and provides a more responsive user experience.

## TUI Library Selection: Textual

We will use **Textual** (https://textual.textualize.io/) as the TUI framework.

### Why Textual?

| Criteria | Textual | Rich (alternative) | Curses (alternative) |
|----------|---------|-------------------|---------------------|
| **Async Native** | ✅ Built on asyncio | ❌ Synchronous | ❌ Synchronous |
| **Modern Widgets** | ✅ DataTable, Tree, Input, etc. | ⚠️ Limited widgets | ❌ Manual implementation |
| **CSS Styling** | ✅ Full CSS support | ❌ No CSS | ❌ No CSS |
| **Testing Framework** | ✅ Built-in AppTest | ❌ None | ❌ None |
| **Active Development** | ✅ Very active (Textualize) | ✅ Active | ⚠️ Stable but old |
| **Documentation** | ✅ Excellent | ✅ Good | ⚠️ Sparse |
| **Python Version** | 3.8+ | 3.7+ | 2.x/3.x |

### Key Textual Features We'll Use

1. **Async Event Loop**: Textual runs on asyncio, which matches our existing async database and LLM code perfectly. No need to bridge sync/async boundaries.

2. **Reactive State**: Textual's `reactive` decorator automatically triggers UI updates when state changes - ideal for real-time agent updates.

3. **Built-in Widgets**: DataTable (for project list, findings), Tree (for attack surface graph), Input (for chat), Static (for logs).

4. **CSS Styling**: We can style the entire UI with CSS, making it easy to create a consistent look and support themes.

5. **Screen Stack**: Built-in navigation with push/pop screens - perfect for our view hierarchy.

6. **Testing**: `AppTest` allows us to simulate user input and verify UI state in tests.

### Example Textual Code

```python
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable
from textual.reactive import reactive

class KodiakApp(App):
    CSS = """
    DataTable {
        height: 100%;
    }
    .critical { color: red; }
    .high { color: orange; }
    """
    
    # Reactive state - UI auto-updates when this changes
    projects: reactive[list] = reactive([])
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()
    
    async def on_mount(self) -> None:
        # Load projects from database (async!)
        self.projects = await crud.get_all_projects(session)
        
    def watch_projects(self, projects: list) -> None:
        # Called automatically when projects changes
        table = self.query_one(DataTable)
        table.clear()
        for p in projects:
            table.add_row(p.name, p.target, p.status)
```

### Installation

```bash
pip install textual
# or
poetry add textual
```

Textual has minimal dependencies and works on Linux, macOS, and Windows.

## Architecture

### Current Architecture (To Be Removed)
```
┌─────────────┐     HTTP/WS      ┌─────────────┐     SQL      ┌──────────┐
│   Next.js   │ ◄──────────────► │   FastAPI   │ ◄──────────► │ Postgres │
│  Frontend   │                  │   Backend   │              │    DB    │
└─────────────┘                  └─────────────┘              └──────────┘
     Browser                      Docker Container            Docker Container
```

### New Architecture (TUI)
```
┌─────────────────────────────────────────────────────────────┐
│                     Kodiak TUI Application                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   Textual   │  │    Core     │  │      Services       │  │
│  │    Views    │◄─┤   Engine    │◄─┤  (Agents, Tools,    │  │
│  │             │  │             │  │   LLM, Hive Mind)   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ SQL (asyncpg)
                       ┌──────────┐
                       │ Postgres │
                       │    DB    │
                       └──────────┘
```

### Component Interaction Flow
```
User Input (keyboard)
        │
        ▼
┌───────────────┐
│  Textual App  │ ◄─── Event Loop (asyncio)
└───────┬───────┘
        │
        ▼
┌───────────────┐
│  View Layer   │ ◄─── HomeView, MissionControlView, AgentChatView, etc.
└───────┬───────┘
        │
        ▼
┌───────────────┐
│ State Manager │ ◄─── Reactive state, triggers UI updates
└───────┬───────┘
        │
        ├──────────────────┬──────────────────┐
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│  Orchestrator │  │   Database    │  │  LLM Service  │
│    (Agents)   │  │     CRUD      │  │   (LiteLLM)   │
└───────────────┘  └───────────────┘  └───────────────┘
```

## Components and Interfaces

### 1. TUI Application (`kodiak/tui/app.py`)

The main application class that extends `textual.app.App`.

```python
from textual.app import App, ComposeResult
from textual.binding import Binding

class KodiakApp(App):
    """Main Kodiak TUI Application."""
    
    TITLE = "Kodiak"
    CSS_PATH = "styles.tcss"
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("h", "go_home", "Home"),
        Binding("?", "show_help", "Help"),
    ]
    
    async def on_mount(self) -> None:
        """Initialize database and services on startup."""
        await self.initialize_services()
        await self.push_screen(HomeScreen())
    
    async def initialize_services(self) -> None:
        """Initialize database, orchestrator, and event system."""
        pass
```

### 2. View Classes (`kodiak/tui/views/`)

Each view is a Textual `Screen` that manages its own layout and state.

| View | File | Purpose |
|------|------|---------|
| HomeScreen | `home.py` | Project list, recent activity |
| NewScanScreen | `new_scan.py` | Create new scan form |
| MissionControlScreen | `mission_control.py` | Main dashboard with agents, graph, logs |
| AgentChatScreen | `agent_chat.py` | Direct agent communication |
| GraphScreen | `graph.py` | Expanded attack surface tree |
| FindingsScreen | `findings.py` | Vulnerability report list |
| FindingDetailScreen | `finding_detail.py` | Single finding details |

### 3. Widget Classes (`kodiak/tui/widgets/`)

Reusable UI components.

| Widget | File | Purpose |
|--------|------|---------|
| AgentPanel | `agent_panel.py` | List of agents with status |
| GraphTree | `graph_tree.py` | Attack surface tree rendering |
| ActivityLog | `activity_log.py` | Scrolling log of agent actions |
| ChatHistory | `chat_history.py` | Message display for agent chat |
| FindingsList | `findings_list.py` | Grouped findings by severity |
| StatusBar | `status_bar.py` | Header with context and status |

### 4. State Management (`kodiak/tui/state.py`)

Reactive state container using Textual's reactive system.

```python
from textual.reactive import reactive

class AppState:
    """Global application state."""
    
    current_project: reactive[Project | None] = reactive(None)
    agents: reactive[list[AgentState]] = reactive([])
    findings: reactive[list[Finding]] = reactive([])
    graph_nodes: reactive[list[Node]] = reactive([])
    activity_log: reactive[list[LogEntry]] = reactive([])
    
    def update_agent_status(self, agent_id: str, status: str) -> None:
        """Update agent status and trigger UI refresh."""
        pass
```

### 5. Event System (`kodiak/tui/events.py`)

Internal event system for agent-to-UI communication (replaces WebSocket).

```python
from dataclasses import dataclass
from textual.message import Message

@dataclass
class AgentStatusChanged(Message):
    agent_id: str
    status: str
    task: str | None

@dataclass
class AssetDiscovered(Message):
    node: Node
    parent_id: str | None

@dataclass
class FindingCreated(Message):
    finding: Finding

@dataclass
class AgentLogEntry(Message):
    agent_id: str
    message: str
    timestamp: datetime
```

### 6. Core Integration Layer (`kodiak/tui/core_bridge.py`)

Bridge between TUI and existing core components.

```python
class CoreBridge:
    """Bridge between TUI and core Kodiak services."""
    
    def __init__(self, app: KodiakApp):
        self.app = app
        self.orchestrator: Orchestrator | None = None
        self.tool_inventory: ToolInventory | None = None
    
    async def initialize(self) -> None:
        """Initialize core services."""
        await init_db()
        self.tool_inventory = ToolInventory(event_callback=self._on_event)
        self.tool_inventory.initialize_tools()
        self.orchestrator = Orchestrator(self.tool_inventory)
    
    async def start_scan(self, project_id: UUID, config: ScanConfig) -> None:
        """Start a new scan for a project."""
        pass
    
    async def send_message_to_agent(self, agent_id: str, message: str) -> None:
        """Send a user message to a specific agent."""
        pass
    
    def _on_event(self, event: dict) -> None:
        """Handle events from core services and post to TUI."""
        self.app.post_message(self._convert_event(event))
```

## Data Models

### Existing Models (Preserved)
The following models from `kodiak/database/models.py` remain unchanged:
- `Project` - Project/scan metadata
- `Scan` - Scan configuration and status
- `Node` - Attack surface graph nodes
- `Edge` - Relationships between nodes
- `Finding` - Discovered vulnerabilities
- `AgentLog` - Agent activity history
- `Task` - Orchestrator task queue

### New TUI-Specific Models

```python
@dataclass
class AgentState:
    """Runtime state of an agent (not persisted)."""
    id: str
    name: str
    status: Literal["active", "thinking", "error", "paused", "idle"]
    current_task: str | None
    role: str | None

@dataclass  
class LogEntry:
    """Activity log entry for display."""
    timestamp: datetime
    agent_id: str | None
    message: str
    level: Literal["info", "warning", "error", "success"]

@dataclass
class ChatMessage:
    """Chat message between user and agent."""
    timestamp: datetime
    sender: Literal["user", "agent"]
    agent_id: str
    content: str
```

## Project Structure

### New Directory Layout
```
kodiak/
├── __init__.py
├── __main__.py              # Entry point: python -m kodiak
├── cli.py                   # CLI commands: kodiak init, kodiak config
├── tui/
│   ├── __init__.py
│   ├── app.py               # Main KodiakApp class
│   ├── state.py             # Reactive state management
│   ├── events.py            # Internal event definitions
│   ├── core_bridge.py       # Bridge to core services
│   ├── styles.tcss          # Textual CSS styles
│   ├── views/
│   │   ├── __init__.py
│   │   ├── home.py
│   │   ├── new_scan.py
│   │   ├── mission_control.py
│   │   ├── agent_chat.py
│   │   ├── graph.py
│   │   ├── findings.py
│   │   └── finding_detail.py
│   └── widgets/
│       ├── __init__.py
│       ├── agent_panel.py
│       ├── graph_tree.py
│       ├── activity_log.py
│       ├── chat_history.py
│       ├── findings_list.py
│       └── status_bar.py
├── core/                    # Existing core (moved from backend/)
│   ├── agent.py
│   ├── orchestrator.py
│   ├── hive_mind.py
│   ├── safety.py
│   ├── config.py
│   └── tools/
├── database/                # Existing database (moved from backend/)
│   ├── models.py
│   ├── crud.py
│   └── engine.py
├── services/                # Existing services (moved from backend/)
│   ├── llm.py
│   └── executor.py
└── skills/                  # Existing skills (moved from backend/)
    ├── skill_loader.py
    ├── skill_registry.py
    └── definitions/
```

### Files to Remove
```
frontend/                    # Entire directory
backend/main.py              # FastAPI entry point
backend/kodiak/api/          # All API endpoints
backend/kodiak/services/websocket_manager.py
```

### Files to Update
```
docker-compose.yml           # Remove frontend service
pyproject.toml              # Move to root, add textual dependency
README.md                   # Update for TUI usage
docs/DEPLOYMENT.md          # Update deployment instructions
.kiro/steering/*.md         # Update all steering documents
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*



### Property 1: Core Components Preserved After Cleanup

*For any* core module (agents, tools, database, LLM services, skills, hive mind, orchestrator), after the architecture cleanup, the module SHALL be importable and functional without errors.

**Validates: Requirements 1.7**

### Property 2: Database Operations Work Without HTTP

*For any* database operation (create, read, update, delete) on projects, scans, nodes, or findings, the TUI SHALL execute the operation directly through the database engine without any HTTP intermediary, and the operation SHALL complete successfully.

**Validates: Requirements 2.4, 13.2, 13.3**

### Property 3: Project List Displays All Required Fields

*For any* project in the database, when displayed in the Home_View, the rendered output SHALL contain the project's name, target, status, and finding count.

**Validates: Requirements 3.2**

### Property 4: Navigation State Consistency

*For any* navigation action (Enter to select, Escape to go back, shortcut keys), the application SHALL transition to the correct view and maintain consistent state between the view stack and the displayed content.

**Validates: Requirements 3.4, 4.4, 4.5, 5.6, 7.7, 10.7**

### Property 5: Target Validation Rejects Invalid Inputs

*For any* string that is not a valid URL or IP address/CIDR range, the New_Scan_View validation SHALL reject the input and prevent scan creation.

**Validates: Requirements 4.6, 4.7**

### Property 6: Agent Status Visual Mapping

*For any* agent with a status (active, thinking, error, paused, idle), the Agent_Panel SHALL display the correct visual indicator (🟢, 🟡, 🔴, ⏸, ⚪) corresponding to that status.

**Validates: Requirements 6.2**

### Property 7: Event Propagation Updates UI

*For any* event emitted by an agent (asset discovered, finding created, log entry), the corresponding UI component (graph, findings list, activity log) SHALL update within one render cycle to reflect the new data.

**Validates: Requirements 5.4, 6.4, 8.8, 9.7, 11.2, 11.3, 11.4**

### Property 8: Chat Message Round-Trip

*For any* message sent by the user to an agent, the message SHALL appear in the chat history with correct timestamp and sender identification, and when the agent responds, the response SHALL appear in the same chat history.

**Validates: Requirements 7.1, 7.2, 7.4, 7.5**

### Property 9: Graph Node Icon Mapping

*For any* node in the attack surface graph, the Graph_View SHALL display the correct icon based on node type (🎯 target, 📡 host, 🔌 port, 🌐 endpoint, 🔓 vulnerability).

**Validates: Requirements 8.2**

### Property 10: Severity Color Coding

*For any* vulnerability finding, the display SHALL use the correct color based on severity (🔴 critical, 🟠 high, 🟡 medium, 🟢 low).

**Validates: Requirements 8.3**

### Property 11: Findings Grouped By Severity

*For any* set of findings, the Findings_View SHALL group them by severity level, and the summary count for each severity SHALL equal the number of findings in that group.

**Validates: Requirements 9.1, 9.2**

### Property 12: Finding Detail Contains All Fields

*For any* finding, when displayed in Finding_Detail_View, the view SHALL contain: title, severity, location (URL, parameter, method), evidence, and remediation recommendations.

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

### Property 13: Keyboard Bindings Registered

*For any* global shortcut (q, h, ?) and view-specific shortcut, the binding SHALL be registered with the application and trigger the correct action when pressed.

**Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

### Property 14: Configuration Loading

*For any* configuration value, the system SHALL load it from environment variables first, then fall back to .env file, then use default values.

**Validates: Requirements 15.1, 15.2**

### Property 15: Non-Blocking UI

*For any* async operation (database query, LLM call, agent communication), the UI event loop SHALL continue processing user input and rendering updates without blocking.

**Validates: Requirements 2.3, 11.5**

## Error Handling

### Database Errors
- Connection failures: Display error message and exit with code 1
- Query errors: Log error, display user-friendly message, allow retry
- Transaction failures: Rollback and notify user

### LLM Service Errors
- API key missing: Prompt user to configure via `kodiak config`
- Rate limiting: Implement exponential backoff, notify user of delay
- Model errors: Log full error, display simplified message to user

### Agent Errors
- Agent crash: Mark agent as error state, log details, allow restart
- Tool execution failure: Log error, continue with other tasks
- Timeout: Cancel operation, mark as failed, notify user

### UI Errors
- Render errors: Log and attempt recovery, fall back to safe state
- Input validation: Display inline error messages
- Navigation errors: Return to home view as safe fallback

## Testing Strategy

### Unit Tests
Unit tests will verify individual components in isolation:
- View rendering with mock data
- Widget behavior and state management
- Event handling and message passing
- Validation functions
- Configuration loading

### Property-Based Tests
Property-based tests will use Hypothesis to verify universal properties:
- Navigation consistency across random sequences of actions
- Data rendering completeness for generated test data
- Event propagation for random event sequences
- Keyboard binding coverage

**Testing Framework**: pytest with pytest-asyncio for async tests, Hypothesis for property-based testing

**Minimum iterations**: 100 per property test

**Test file naming**: `test_*.py` in `kodiak/tui/tests/`

### Integration Tests
- Full application startup and shutdown
- Database integration with test database
- End-to-end user flows (create project → start scan → view findings)

### TUI-Specific Testing
Textual provides a testing framework for simulating user interaction:
```python
from textual.testing import AppTest

async def test_home_view_displays_projects():
    async with AppTest(KodiakApp) as pilot:
        # Verify home screen is displayed
        assert pilot.app.screen.name == "home"
        # Verify project list widget exists
        assert pilot.app.query_one(ProjectList)
```

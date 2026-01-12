# Project Structure

## Root Level
- `docker-compose.yml`: Multi-service orchestration (PostgreSQL, Kodiak TUI)
- `README.md`: Project overview and quick start guide
- `docs/`: Architecture, contributing, deployment, and security documentation
- `scripts/`: Deployment and verification utilities
- `.kiro/steering/`: Project steering documents for AI assistant guidance
- `pyproject.toml`: Poetry dependencies and CLI entry points
- `kodiak/`: Main Python package (moved from backend/)

## Main Package (`kodiak/`)
```
kodiak/
├── __init__.py              # Package initialization
├── __main__.py              # Entry point for `python -m kodiak`
├── cli.py                   # CLI commands (init, config, tui)
├── tui/                     # Terminal User Interface
│   ├── __init__.py
│   ├── app.py              # Main TUI application class
│   ├── styles.tcss         # Textual CSS styles
│   ├── views/              # Screen implementations
│   │   ├── __init__.py
│   │   ├── home.py         # Project selection and management
│   │   ├── new_scan.py     # Scan creation form
│   │   ├── mission_control.py # Main dashboard
│   │   ├── agent_chat.py   # Agent communication
│   │   ├── graph.py        # Attack surface visualization
│   │   ├── findings.py     # Vulnerability reports
│   │   ├── finding_detail.py # Individual finding details
│   │   ├── help.py         # Help and shortcuts
│   │   └── error.py        # Error handling screens
│   ├── widgets/            # Reusable UI components
│   │   ├── __init__.py
│   │   ├── status_bar.py   # Header with context and status
│   │   ├── agent_panel.py  # Agent list with status indicators
│   │   ├── graph_tree.py   # Attack surface tree rendering
│   │   ├── activity_log.py # Scrolling log of agent actions
│   │   ├── findings_list.py # Grouped findings display
│   │   ├── chat_history.py # Message display for agent chat
│   │   └── loading_indicator.py # Async operation feedback
│   ├── state.py            # Reactive state management
│   ├── events.py           # TUI event system
│   └── core_bridge.py      # Bridge to core functionality
├── core/                   # Core business logic
│   ├── __init__.py
│   ├── agent.py            # Enhanced LLM agent with skills
│   ├── orchestrator.py     # Task scheduling and coordination
│   ├── hive_mind.py        # Command synchronization
│   ├── safety.py           # Security controls and approval
│   ├── config.py           # Configuration management
│   ├── error_handling.py   # Comprehensive error handling
│   └── tools/              # Tool definitions and inventory
│       ├── __init__.py
│       ├── base.py         # Abstract tool base class
│       ├── inventory.py    # Tool registry and management
│       └── definitions/    # Individual tool implementations
├── skills/                 # Dynamic skills system
│   ├── __init__.py
│   ├── skill_loader.py     # Skill loading and formatting
│   ├── skill_registry.py   # Skill discovery and validation
│   └── definitions/        # YAML skill definitions
│       ├── vulnerabilities/ # Core vulnerability skills
│       ├── frameworks/     # Framework-specific skills
│       └── technologies/   # Technology-specific skills
├── database/               # Data layer
│   ├── __init__.py
│   ├── models.py           # SQLModel definitions
│   ├── crud.py             # Database operations
│   └── engine.py           # Database connection and initialization
├── services/               # External service integrations
│   ├── __init__.py
│   ├── llm.py              # LLM service integration
│   └── executor.py         # Tool execution service
└── api/                    # Event system (adapted for TUI)
    ├── __init__.py
    └── events.py           # Event management system
```

## Key Architecture Patterns

### TUI Patterns
- **Textual Framework**: Modern async TUI with CSS styling support
- **Screen Stack**: Navigation using push/pop screen pattern
- **Reactive State**: Automatic UI updates when state changes
- **Event-Driven**: Message passing between components
- **Keyboard Navigation**: Complete keyboard-driven workflow

### Backend Patterns (Preserved)
- **Async/Await**: All database and external operations use async patterns
- **Dependency Injection**: Database sessions and service dependencies
- **Repository Pattern**: CRUD operations separated from business logic
- **Event-Driven**: Orchestrator polls for tasks and spawns workers
- **Command Pattern**: Tools are encapsulated as executable commands
- **Strategy Pattern**: Skills provide specialized knowledge for different contexts

### Database Schema (Unchanged)
- **Graph Structure**: Nodes and Edges represent the attack surface
- **Audit Trail**: AgentLog captures all agent thoughts and actions
- **Command Caching**: CommandCache prevents duplicate tool execution
- **Task Queue**: Task table drives the orchestrator's work distribution
- **Skills Integration**: Dynamic skill loading with agent specialization

### Skills System Architecture (Unchanged)
- **YAML Definitions**: Human-readable skill specifications
- **Dynamic Loading**: Runtime skill loading based on agent needs
- **Category Organization**: Structured skill taxonomy
- **Template System**: Jinja2-based skill formatting for agents
- **Validation**: Comprehensive skill validation and dependency checking

### Tool System Architecture (Unchanged)
- **Abstract Base**: Common interface for all security tools
- **Schema Generation**: Automatic OpenAI function schema creation
- **Result Standardization**: Consistent ToolResult format
- **Hive Mind Integration**: Automatic command deduplication
- **Safety Integration**: Built-in approval workflow for dangerous operations

### TUI-Specific Patterns
- **View Controllers**: Each screen manages its own state and interactions
- **Widget Composition**: Reusable components with clear responsibilities
- **State Synchronization**: Core bridge keeps TUI and backend in sync
- **Error Boundaries**: Graceful error handling with user-friendly messages
- **Loading States**: Visual feedback for async operations

### Naming Conventions
- **Python**: snake_case for variables/functions, PascalCase for classes
- **TUI Components**: PascalCase for screens and widgets
- **Database**: snake_case table and column names
- **Skills**: snake_case identifiers with descriptive names
- **Tools**: snake_case names matching command-line tool names
- **Events**: PascalCase for TUI messages and events

## Implementation Status

### ✅ Completed Components
- **TUI Architecture**: Complete Textual-based interface with all views and widgets
- **Multi-Agent System**: Complete with role-based specialization and Hive Mind coordination
- **Security Tools**: 20+ core tools + comprehensive toolkit
- **HTTP Proxy System**: Full request/response manipulation and analysis
- **Browser Automation**: Single-page analysis with security vulnerability detection
- **Terminal Environments**: Persistent interactive shells with command history
- **Python Runtime**: Custom exploit development environment with security analysis
- **Skills System**: 8+ skills with dynamic loading capabilities
- **Database Schema**: Complete graph-based persistence layer
- **CLI Interface**: Complete with init, config, and tui commands
- **Error Handling**: Comprehensive error management with user-friendly messages
- **State Management**: Reactive state with real-time UI updates
- **Event System**: TUI-adapted event system for real-time coordination

### ⚠️ Partially Implemented
- **Multi-tab Browser Sessions**: Framework ready, needs persistent session management
- **Database Migrations**: Schema defined, Alembic setup needed
- **Advanced Reporting**: Basic reporting complete, export features needed

### 📋 Development Priorities
1. **Database Migrations**: Alembic setup for schema management
2. **Advanced Reporting**: Enhanced export and reporting features
3. **Multi-tab Browser Sessions**: Complete persistent browser automation
4. **Plugin System**: Extensible architecture for custom tools and skills
5. **Distributed Scanning**: Multi-instance coordination capabilities

## Removed Components (Frontend Architecture)
The following components were removed during the TUI pivot:
- `frontend/` directory (Next.js React application)
- `backend/main.py` (FastAPI application entry point)
- `backend/kodiak/api/endpoints/` (REST API endpoints)
- `backend/kodiak/api/ws.py` (WebSocket handlers)
- `backend/kodiak/services/websocket_manager.py` (WebSocket management)
- CORS configuration and frontend-specific settings

## Migration Notes
- **Backend → Root**: All backend code moved to root `kodiak/` package
- **API Adaptation**: Event system adapted for TUI instead of WebSocket
- **State Management**: Replaced WebSocket state sync with direct function calls
- **Configuration**: Removed frontend-specific settings, added TUI settings
- **Entry Points**: CLI commands replace web server startup
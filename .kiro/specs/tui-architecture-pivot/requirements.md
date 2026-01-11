# Requirements Document

## Introduction

This specification defines the architectural pivot from a frontend-backend (Next.js + FastAPI) architecture to a unified Terminal User Interface (TUI) application. The goal is to simplify deployment, eliminate networking complexity, and provide a native terminal experience for security professionals. The TUI will be built using Python's Textual library and will directly integrate with the existing core components (agents, tools, database, LLM services).

## Glossary

- **TUI**: Terminal User Interface - a text-based interface that runs in a terminal emulator
- **Textual**: A Python framework for building modern TUI applications with async support
- **Kodiak_App**: The main TUI application class that manages all views and state
- **View**: A distinct screen or panel within the TUI (e.g., Home, Mission Control, Agent Chat)
- **Agent**: An LLM-powered security testing worker that executes tasks
- **Hive_Mind**: The coordination system that synchronizes multiple agents
- **Attack_Surface_Graph**: The tree/graph representation of discovered assets and vulnerabilities
- **Finding**: A discovered security vulnerability with evidence and severity

## Requirements

### Requirement 1: Architecture Cleanup

**User Story:** As a developer, I want to remove all frontend-backend separation artifacts, so that the codebase is clean and maintainable.

#### Acceptance Criteria

1. WHEN the TUI branch is created, THE System SHALL remove the entire `frontend/` directory
2. WHEN the TUI branch is created, THE System SHALL remove FastAPI REST API endpoints from `kodiak/api/endpoints/`
3. WHEN the TUI branch is created, THE System SHALL remove WebSocket-related code from `kodiak/api/ws.py` and `kodiak/services/websocket_manager.py`
4. WHEN the TUI branch is created, THE System SHALL remove CORS configuration from `kodiak/core/config.py`
5. WHEN the TUI branch is created, THE System SHALL update `docker-compose.yml` to remove the frontend service
6. WHEN the TUI branch is created, THE System SHALL remove `main.py` FastAPI application entry point
7. THE System SHALL preserve all core components: agents, tools, database, LLM services, skills, hive mind, orchestrator

### Requirement 2: TUI Application Framework

**User Story:** As a user, I want to launch Kodiak as a single terminal application, so that I can run security scans without managing multiple services.

#### Acceptance Criteria

1. THE Kodiak_App SHALL be implemented using the Textual library for Python
2. WHEN a user runs `python -m kodiak` or `kodiak`, THE Kodiak_App SHALL launch in the terminal
3. THE Kodiak_App SHALL support async operations for non-blocking UI updates
4. THE Kodiak_App SHALL integrate directly with the database engine without HTTP intermediaries
5. THE Kodiak_App SHALL integrate directly with the LLM service without HTTP intermediaries
6. THE Kodiak_App SHALL support keyboard navigation and shortcuts
7. THE Kodiak_App SHALL display a consistent header with application name, current context, and status

### Requirement 3: Home View - Project Selection

**User Story:** As a user, I want to see all my projects and their status on startup, so that I can quickly resume or start work.

#### Acceptance Criteria

1. WHEN the Kodiak_App starts, THE Home_View SHALL display a list of all projects from the database
2. THE Home_View SHALL display each project's name, target, status, and finding count
3. WHEN a user presses arrow keys, THE Home_View SHALL navigate between projects
4. WHEN a user presses Enter on a project, THE Kodiak_App SHALL navigate to the Mission_Control_View for that project
5. WHEN a user presses 'n', THE Kodiak_App SHALL navigate to the New_Scan_View
6. WHEN a user presses 'd' on a project, THE System SHALL prompt for confirmation before deleting
7. WHEN a user presses 'r' on a paused project, THE System SHALL resume the scan
8. THE Home_View SHALL display recent activity from all projects

### Requirement 4: New Scan View

**User Story:** As a user, I want to create new security scans with custom parameters, so that I can test different targets.

#### Acceptance Criteria

1. THE New_Scan_View SHALL provide input fields for: project name, target URL/IP, instructions
2. THE New_Scan_View SHALL provide a slider or input for agent count (1-5)
3. WHEN a user presses Enter with valid inputs, THE System SHALL create a new project and scan in the database
4. WHEN a user presses Enter with valid inputs, THE System SHALL navigate to Mission_Control_View and start the scan
5. WHEN a user presses Escape, THE Kodiak_App SHALL return to the Home_View without creating a scan
6. IF the target field is empty, THEN THE System SHALL display an error and prevent submission
7. THE New_Scan_View SHALL validate that the target is a valid URL or IP address/range

### Requirement 5: Mission Control View - Main Dashboard

**User Story:** As a user, I want to monitor all agents and the attack surface in real-time, so that I can understand scan progress.

#### Acceptance Criteria

1. THE Mission_Control_View SHALL display a panel showing all active agents with their status
2. THE Mission_Control_View SHALL display the attack surface graph as a navigable tree structure
3. THE Mission_Control_View SHALL display a scrolling activity log of all agent actions
4. THE Mission_Control_View SHALL update in real-time as agents discover assets and findings
5. WHEN a user presses Tab, THE Mission_Control_View SHALL cycle focus between panels
6. WHEN a user selects an agent and presses Enter, THE Kodiak_App SHALL navigate to Agent_Chat_View
7. WHEN a user presses 'g', THE Kodiak_App SHALL navigate to the expanded Graph_View
8. WHEN a user presses 'f', THE Kodiak_App SHALL navigate to the Findings_View
9. WHEN a user presses 'p', THE System SHALL pause/resume the current scan
10. THE Mission_Control_View SHALL display scan duration and overall status in the header

### Requirement 6: Agent Selection and Status

**User Story:** As a user, I want to see which agents are active and what they're doing, so that I can monitor and direct the scan.

#### Acceptance Criteria

1. THE Agent_Panel SHALL display each agent with a unique identifier (Agent-1, Agent-2, etc.)
2. THE Agent_Panel SHALL display agent status using visual indicators: 🟢 active, 🟡 thinking, 🔴 error, ⏸ paused
3. THE Agent_Panel SHALL display the current task or role for each agent
4. WHEN an agent's status changes, THE Agent_Panel SHALL update immediately
5. WHEN a user navigates to an agent and presses Enter, THE Kodiak_App SHALL open Agent_Chat_View for that agent
6. THE Agent_Panel SHALL highlight the currently selected agent

### Requirement 7: Agent Chat View - Direct Communication

**User Story:** As a user, I want to communicate directly with individual agents, so that I can guide their testing focus.

#### Acceptance Criteria

1. THE Agent_Chat_View SHALL display the conversation history between the user and the selected agent
2. THE Agent_Chat_View SHALL display messages with timestamps and sender identification
3. THE Agent_Chat_View SHALL provide a text input field for sending messages to the agent
4. WHEN a user types a message and presses Enter, THE System SHALL send the message to the agent
5. WHEN the agent responds, THE Agent_Chat_View SHALL display the response in real-time
6. WHEN a user presses left/right arrow keys, THE Kodiak_App SHALL switch to adjacent agents
7. WHEN a user presses Escape, THE Kodiak_App SHALL return to Mission_Control_View
8. THE Agent_Chat_View SHALL display the agent's current status and task in the header

### Requirement 8: Attack Surface Graph View

**User Story:** As a user, I want to visualize the discovered attack surface as a tree, so that I can understand the target's structure.

#### Acceptance Criteria

1. THE Graph_View SHALL render the attack surface as an ASCII tree structure
2. THE Graph_View SHALL display nodes with appropriate icons: 🎯 target, 📡 host, 🔌 port, 🌐 endpoint, 🔓 vulnerability
3. THE Graph_View SHALL color-code vulnerabilities by severity: 🔴 critical, 🟠 high, 🟡 medium, 🟢 low
4. WHEN a user navigates with arrow keys, THE Graph_View SHALL move selection between nodes
5. WHEN a user presses Enter on a vulnerability node, THE Kodiak_App SHALL navigate to Finding_Detail_View
6. WHEN a user presses '/', THE Graph_View SHALL activate search mode to filter nodes
7. THE Graph_View SHALL support collapsing and expanding tree branches
8. THE Graph_View SHALL update in real-time as new assets are discovered

### Requirement 9: Findings View - Vulnerability Report

**User Story:** As a user, I want to see all discovered vulnerabilities organized by severity, so that I can prioritize remediation.

#### Acceptance Criteria

1. THE Findings_View SHALL display a summary count of findings by severity level
2. THE Findings_View SHALL group findings by severity: Critical, High, Medium, Low, Info
3. THE Findings_View SHALL display each finding with: title, location, discovering agent, timestamp
4. WHEN a user navigates to a finding and presses Enter, THE Kodiak_App SHALL navigate to Finding_Detail_View
5. WHEN a user presses 'e', THE System SHALL export findings to a file (JSON, Markdown, or HTML)
6. THE Findings_View SHALL support filtering by severity, type, or agent
7. THE Findings_View SHALL update in real-time as new findings are discovered

### Requirement 10: Finding Detail View

**User Story:** As a user, I want to see complete details of a vulnerability including evidence, so that I can validate and report it.

#### Acceptance Criteria

1. THE Finding_Detail_View SHALL display the vulnerability title and severity prominently
2. THE Finding_Detail_View SHALL display location information: URL, parameter, method
3. THE Finding_Detail_View SHALL display evidence: request/response data, payloads used
4. THE Finding_Detail_View SHALL display remediation recommendations
5. WHEN a user presses 'c', THE System SHALL copy the proof-of-concept to clipboard
6. WHEN a user presses 'r', THE System SHALL trigger a re-test of the vulnerability
7. WHEN a user presses Escape, THE Kodiak_App SHALL return to the previous view

### Requirement 11: Real-time Updates

**User Story:** As a user, I want to see live updates from agents without refreshing, so that I can monitor progress continuously.

#### Acceptance Criteria

1. THE Kodiak_App SHALL use async event handling to receive updates from agents
2. WHEN an agent discovers a new asset, THE Attack_Surface_Graph SHALL update immediately
3. WHEN an agent finds a vulnerability, THE Findings list SHALL update immediately
4. WHEN an agent logs an action, THE Activity_Log SHALL append the entry immediately
5. THE Kodiak_App SHALL NOT block the UI while waiting for agent responses
6. THE Kodiak_App SHALL display a visual indicator when updates are being received

### Requirement 12: Keyboard Navigation

**User Story:** As a user, I want to navigate the entire application using keyboard shortcuts, so that I can work efficiently.

#### Acceptance Criteria

1. THE Kodiak_App SHALL support global shortcuts: 'q' quit, 'h' home, '?' help
2. THE Kodiak_App SHALL support Tab to cycle between panels in split views
3. THE Kodiak_App SHALL support arrow keys for list/tree navigation
4. THE Kodiak_App SHALL support Enter to select/activate items
5. THE Kodiak_App SHALL support Escape to go back or cancel
6. THE Kodiak_App SHALL display available shortcuts in a footer bar on each view
7. WHEN a user presses '?', THE Kodiak_App SHALL display a help overlay with all shortcuts

### Requirement 13: Database Integration

**User Story:** As a developer, I want the TUI to use the existing database layer directly, so that we preserve data persistence.

#### Acceptance Criteria

1. THE Kodiak_App SHALL initialize the database connection on startup
2. THE Kodiak_App SHALL use the existing SQLModel models for all data operations
3. THE Kodiak_App SHALL use the existing CRUD operations from `kodiak/database/crud.py`
4. THE Kodiak_App SHALL handle database errors gracefully with user-friendly messages
5. WHEN the database is unavailable, THE Kodiak_App SHALL display an error and exit cleanly

### Requirement 14: Simplified Deployment

**User Story:** As a user, I want to run Kodiak with minimal setup, so that I can start testing quickly.

#### Acceptance Criteria

1. THE System SHALL be installable via `pip install kodiak` or `poetry install`
2. THE System SHALL require only PostgreSQL as an external dependency
3. THE docker-compose.yml SHALL define only two services: db and kodiak (TUI)
4. THE System SHALL support running without Docker using a local PostgreSQL instance
5. THE System SHALL provide a `kodiak init` command to set up the database schema
6. THE System SHALL provide a `kodiak config` command to configure LLM settings interactively

### Requirement 15: Configuration Management

**User Story:** As a user, I want to configure Kodiak settings easily, so that I can customize my environment.

#### Acceptance Criteria

1. THE System SHALL read configuration from environment variables and `.env` file
2. THE System SHALL preserve existing LLM configuration options (provider, model, API keys)
3. THE System SHALL remove CORS and frontend-related configuration options
4. THE System SHALL add TUI-specific configuration: color theme, refresh rate
5. WHEN required configuration is missing, THE System SHALL prompt the user interactively

### Requirement 16: Documentation Updates

**User Story:** As a developer or user, I want accurate documentation reflecting the TUI architecture, so that I can understand and use the system correctly.

#### Acceptance Criteria

1. THE System SHALL update `docs/DEPLOYMENT.md` to reflect TUI-based deployment
2. THE System SHALL update `README.md` to describe the TUI application and usage
3. THE System SHALL update `.kiro/steering/tech.md` to remove frontend technologies and add Textual
4. THE System SHALL update `.kiro/steering/structure.md` to reflect the new project structure without frontend
5. THE System SHALL update `.kiro/steering/product.md` to describe TUI-based interface instead of web dashboard
6. THE System SHALL update `.kiro/steering/implementation.md` to reflect TUI implementation status
7. THE System SHALL remove or archive frontend-related documentation
8. THE System SHALL add TUI-specific documentation: keyboard shortcuts, views, navigation

### Requirement 17: Project Structure Reorganization

**User Story:** As a developer, I want a clean project structure without the backend subdirectory, so that the codebase is simpler to navigate.

#### Acceptance Criteria

1. THE System SHALL move `backend/kodiak/` contents to the root `kodiak/` directory
2. THE System SHALL move `backend/pyproject.toml` to the root directory
3. THE System SHALL remove the empty `backend/` directory after migration
4. THE System SHALL update all import paths to reflect the new structure
5. THE System SHALL create a new `kodiak/tui/` directory for TUI-specific code
6. THE System SHALL create `kodiak/tui/app.py` as the main TUI application entry point
7. THE System SHALL create `kodiak/tui/views/` directory for individual view implementations
8. THE System SHALL create `kodiak/tui/widgets/` directory for reusable TUI components
9. THE System SHALL update `pyproject.toml` to define `kodiak` as the CLI entry point

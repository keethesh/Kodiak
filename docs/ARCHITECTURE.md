# Kodiak Architecture

## Philosophy
Kodiak is designed to be **persistent, structured, and synchronized**. Unlike traditional monolithic and ephemeral tools, Kodiak focuses on robust state management and coordinated execution to prevent infinite loops and lost context.

## Core Concepts

### 1. The "Hive Mind" (Command Synchronization)
Kodiak solves the "thundering herd" problem of multiple agents running duplicates scans.
- **Global Lock Registry**: Before running `nmap` or `nuclei`, agents check the DB.
- **Output Streaming**: If Agent A is running a scan, Agent B attaches to Agent A's output stream instead of spawning a new process.
- **Result Caching**: Heavy scan results are cached in PostgreSQL.

### 2. State Persistence
We use **PostgreSQL** as the source of truth.
- **Resumability**: You can stop the TUI application at any time. On restart, the Orchestrator rehydrates the state machine and resumes agents from their last valid checkpoint.
- **Audit Trail**: Every tool output, thought process, and finding is committed to the DB.

### 3. The Graph (LangGraph-style)
Agents do not run in an infinite `while True` loop. They follow a strict State Machine:
`Recon` -> `Enumeration` -> `Vulnerability Assessment` -> `Exploitation` -> `Reporting`

Transitions are guarded by "Gates" (e.g., "Has open ports?" -> Yes -> Enum).

## Tech Stack
- **Application**: Python 3.11+, Textual TUI Framework
- **Core Logic**: SQLModel (SQLAlchemy), LiteLLM, asyncio
- **Database**: PostgreSQL (pgvector support planned for embeddings)
- **Security Tools**: nmap, nuclei, sqlmap, commix, subfinder, httpx, Playwright
- **Engine**: Docker (for sandboxed tool execution)

## Data Flow
1. User initiates Scan via TUI interface.
2. Core creates `ScanJob` in database.
3. `Orchestrator` spawns specialized agents.
4. Agents request security tools via `ToolServer`.
5. `ToolServer` checks Hive Mind -> runs tools in Docker.
6. Output piped to DB + TUI event system.
7. Next agents triggered by completion events.

## TUI Architecture

### Terminal User Interface (Textual Framework)
Kodiak uses the modern Textual framework for its terminal interface, providing:
- **Async Native**: Full async/await support for non-blocking operations
- **CSS Styling**: Rich visual design with customizable themes
- **Component Architecture**: Reusable widgets and modular screen design
- **Event-Driven**: Reactive updates based on agent activities

### Screen Stack Navigation
The TUI implements a screen stack pattern:
- **HomeScreen**: Project management and selection
- **NewScanScreen**: Scan creation with validation
- **MissionControlScreen**: Real-time monitoring dashboard
- **AgentChatScreen**: Direct agent communication
- **GraphScreen**: Attack surface visualization
- **FindingsScreen**: Vulnerability reports
- **FindingDetailScreen**: Detailed vulnerability analysis

### State Management
- **Reactive State**: Automatic UI updates when data changes
- **Core Bridge**: Connects TUI to backend functionality
- **Event System**: Message passing between components
- **Real-time Updates**: Live monitoring of agent activities

### Widget System
Reusable components provide consistent functionality:
- **StatusBar**: Application context and status
- **AgentPanel**: Agent list with status indicators
- **GraphTree**: Attack surface tree visualization
- **ActivityLog**: Scrolling log of agent actions
- **FindingsList**: Grouped vulnerability display
- **ChatHistory**: Message display for agent communication

## Security Architecture

### Sandboxed Tool Execution
All security tools run in isolated Docker containers:
- **Network Isolation**: Controlled network access
- **Resource Limits**: CPU and memory constraints
- **File System Isolation**: Temporary file systems
- **Safety Controls**: Built-in approval workflows

### Multi-Agent Coordination
- **Role Specialization**: Agents have specific security focuses
- **Knowledge Sharing**: Shared discovery and findings
- **Conflict Prevention**: Hive Mind prevents duplicate work
- **Persistent Memory**: Database-backed execution state

### Skills System
Dynamic skill loading provides specialized knowledge:
- **Vulnerability Skills**: SQL injection, XSS, command injection
- **Framework Skills**: Django, Express, FastAPI testing
- **Technology Skills**: JWT, OAuth, GraphQL analysis
- **Protocol Skills**: HTTP, WebSocket, API testing

## Database Schema

### Core Entities
- **Project**: Top-level container for security assessments
- **Scan**: Individual security scan within a project
- **Agent**: AI agent instance with role and status
- **Node**: Attack surface element (host, port, service)
- **Edge**: Relationship between attack surface elements
- **Finding**: Security vulnerability or issue
- **AgentLog**: Complete audit trail of agent actions

### Graph Structure
The attack surface is modeled as a directed graph:
- **Nodes**: Represent discoverable assets (domains, hosts, ports, services)
- **Edges**: Represent relationships and attack paths
- **Attributes**: Store metadata, configurations, and findings
- **Traversal**: Enable path analysis and attack chain discovery

## Integration Points

### LLM Providers
Support for multiple AI providers via LiteLLM:
- **Google Gemini**: Primary recommendation for performance
- **OpenAI GPT**: Full GPT-3.5 and GPT-4 support
- **Anthropic Claude**: Claude 3.5 Sonnet support
- **Local Models**: Ollama and other local deployments

### Security Tools
Comprehensive security toolkit integration:
- **Network Discovery**: nmap, subfinder, httpx
- **Vulnerability Scanning**: nuclei with 5000+ templates
- **Web Testing**: Playwright browser automation
- **Injection Testing**: sqlmap, commix with validation
- **Custom Tools**: HTTP proxy, Python runtime

### Export and Reporting
Multiple output formats for findings and reports:
- **JSON**: Structured data for automation
- **CSV**: Spreadsheet-compatible format
- **PDF**: Professional reports (planned)
- **SARIF**: Static analysis results format (planned)

## Performance Considerations

### Async Operations
- **Non-blocking UI**: Interface remains responsive during scans
- **Background Processing**: Long-running operations in background
- **Progress Indicators**: Visual feedback for user awareness
- **Cancellation Support**: Ability to stop operations

### Resource Management
- **Connection Pooling**: Efficient database connections
- **Memory Management**: Controlled memory usage for large scans
- **Disk Usage**: Temporary file cleanup and rotation
- **Network Efficiency**: Optimized tool execution and caching

### Scalability
- **Agent Limits**: Configurable maximum concurrent agents
- **Database Optimization**: Indexed queries and efficient schemas
- **Tool Coordination**: Hive Mind prevents resource conflicts
- **Cleanup Procedures**: Automated cleanup of old data

## Development Architecture

### Code Organization
```
kodiak/
├── cli.py              # Command-line interface
├── tui/                # Terminal user interface
│   ├── app.py         # Main application
│   ├── views/         # Screen implementations
│   ├── widgets/       # Reusable components
│   ├── state.py       # State management
│   └── events.py      # Event system
├── core/              # Business logic
│   ├── agent.py       # AI agent implementation
│   ├── orchestrator.py # Task coordination
│   └── tools/         # Security tool definitions
├── database/          # Data layer
├── services/          # External integrations
└── skills/            # Dynamic skills system
```

### Testing Strategy
- **Unit Tests**: Component-level testing with pytest
- **Integration Tests**: End-to-end workflow validation
- **Property Tests**: Universal correctness validation
- **Manual Testing**: User experience validation

### Deployment Options
- **Local Development**: Poetry-based development environment
- **Docker Compose**: Multi-service development setup
- **Production**: Systemd service with PostgreSQL
- **CI/CD**: Automated testing and deployment pipelines
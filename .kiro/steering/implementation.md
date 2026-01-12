---
inclusion: manual
---

# Kodiak Implementation Specification

## Current Implementation Status

### ✅ Completed Core Features

#### TUI Architecture (NEW)
- **Textual Framework**: Modern async TUI with CSS styling and component architecture
- **Screen Management**: Complete navigation system with screen stack and keyboard shortcuts
- **View Implementation**: 9 complete views (Home, NewScan, MissionControl, AgentChat, Graph, Findings, FindingDetail, Help, Error)
- **Widget System**: 7 reusable widgets (StatusBar, AgentPanel, GraphTree, ActivityLog, FindingsList, ChatHistory, LoadingIndicator)
- **State Management**: Reactive state system with automatic UI updates
- **Event System**: TUI-adapted event system for real-time coordination
- **Error Handling**: Comprehensive error management with user-friendly screens
- **CLI Interface**: Complete CLI with init, config, and tui commands

#### Multi-Agent Architecture
- **Agent System**: Complete implementation with role-based specialization
  - Scout agents for reconnaissance and enumeration
  - Attacker agents for exploitation and validation
  - Manager agents for orchestration and coordination
- **Skills Integration**: Dynamic skill loading with 8+ specialized skills
- **Hive Mind Coordination**: Command synchronization prevents duplicate work
- **Orchestrator**: Task scheduling with database-backed persistence
- **Message Queue**: Priority interrupt system for agent communication

#### Security Tools (20+ Implemented)
1. **nmap**: Network discovery with vulnerability assessment and structured parsing
2. **nuclei**: Fast vulnerability scanner with severity analysis and CVE detection
3. **sqlmap**: SQL injection detection with database-specific techniques
4. **commix**: Command injection testing with multiple techniques
5. **subfinder**: Passive subdomain enumeration with source filtering
6. **httpx**: HTTP probing with security header analysis and technology detection
7. **browser_navigate**: Playwright-based web application testing with XSS detection
8. **web_search**: OSINT capabilities for reconnaissance
9. **terminal_execute**: System command execution with safety controls
10. **proxy_start/request/history/stop**: Full HTTP proxy system for request manipulation
11. **terminal_start/history/stop**: Persistent interactive shell environments
12. **python_start/execute/history/stop**: Python runtime for custom exploit development

#### Skills System (8+ Implemented)
1. **sql_injection**: Advanced SQL injection techniques with database-specific payloads
2. **xss_detection**: Cross-site scripting detection with context-aware payloads
3. **command_injection**: OS command injection with filter bypass techniques
4. **web_application_testing**: Comprehensive web app security methodology
5. **django_testing**: Django framework-specific security testing
6. **nodejs_testing**: Node.js and Express.js security assessment
7. **jwt_testing**: JSON Web Token security testing and exploitation
8. **api_testing**: REST API and GraphQL security testing

#### Database Schema
- **Graph Structure**: Nodes and Edges for attack surface representation
- **Persistence Models**: Project, ScanJob, Task, Finding, AgentLog
- **Command Caching**: Hive Mind deduplication with CommandCache
- **Operational Memory**: Attempt tracking to prevent infinite loops
- **Audit Trail**: Complete logging of agent thoughts and actions

#### Core Bridge System (NEW)
- **Database Integration**: Direct database access without HTTP intermediaries
- **Event Conversion**: Converts core events to TUI messages
- **State Synchronization**: Keeps TUI and backend state in sync
- **Error Handling**: Comprehensive error handling with retry logic and health monitoring
- **Async Operations**: Non-blocking operations with loading indicators

### ⚠️ Partially Implemented

#### Safety & Approval System
- ✅ Safety framework with risk categorization
- ✅ Approval request mechanism with task pausing
- ⚠️ User approval TUI interface (backend ready, TUI implementation needed)
- ✅ Tool safety validation and blocking

#### Advanced Browser Features
- ✅ Single-page browser automation with Playwright
- ⚠️ Multi-tab session management (framework ready, needs implementation)
- ⚠️ Persistent browser sessions across scans

### ❌ Removed Components (Frontend Architecture Pivot)
- **Next.js Frontend**: Removed entire React-based web interface
- **FastAPI REST Endpoints**: Removed HTTP API layer (kept core event system)
- **WebSocket Handlers**: Removed WebSocket communication (replaced with direct calls)
- **CORS Configuration**: Removed frontend-specific settings

### ❌ Not Yet Implemented

#### Infrastructure
- Database migrations with Alembic
- Advanced production deployment configuration
- Comprehensive monitoring and observability

#### Advanced Features
- Advanced reporting and export capabilities
- Plugin system for custom tools and skills
- Distributed scanning capabilities

## Architecture Patterns

### TUI Design Patterns (NEW)
- **Screen Stack Navigation**: Push/pop screen pattern for view management
- **Reactive State**: Automatic UI updates when state changes using Textual's reactive system
- **Event-Driven Architecture**: Message passing between TUI components
- **Widget Composition**: Reusable components with clear responsibilities
- **Async Native**: Built on asyncio with non-blocking operations
- **CSS Styling**: Rich visual design with customizable themes

### Backend Design Patterns (Preserved)
- **Async/Await**: All I/O operations use async patterns for performance
- **Repository Pattern**: CRUD operations separated from business logic
- **Event-Driven Architecture**: Orchestrator polls tasks and spawns workers
- **Command Pattern**: Tools encapsulated as executable commands with schemas
- **Strategy Pattern**: Skills provide specialized knowledge for different contexts
- **Bridge Pattern**: Core bridge connects TUI to backend services

### Database Design Patterns (Unchanged)
- **Graph Database**: Nodes and Edges represent attack surface relationships
- **Event Sourcing**: AgentLog captures all agent decisions and actions
- **Command Query Responsibility Segregation**: Separate read/write operations
- **Audit Trail**: Complete operational history for compliance and analysis

## Security Considerations

### Tool Execution Security
- **Input Validation**: All tool parameters validated against Pydantic schemas
- **Safety Middleware**: Risk assessment before tool execution
- **Approval Workflow**: Human oversight for dangerous operations
- **Operational Memory**: Attempt tracking prevents infinite loops

### Data Security
- **Database Isolation**: Project-based data segregation
- **Audit Logging**: Complete trail of all operations
- **Sensitive Data Handling**: Proper handling of credentials and secrets
- **Local Security**: TUI runs locally, reducing network attack surface

## Performance Optimizations

### TUI Performance (NEW)
- **Async Operations**: Non-blocking UI with loading indicators
- **Reactive Updates**: Efficient state change propagation
- **Background Tasks**: Health monitoring and periodic updates
- **Memory Management**: Efficient widget lifecycle management

### Hive Mind Efficiency (Preserved)
- **Command Deduplication**: Prevents redundant tool execution
- **Result Caching**: Database-backed caching of tool outputs
- **Leader Election**: Single agent executes, others subscribe to results
- **Async Coordination**: Non-blocking agent communication

### Database Performance (Preserved)
- **Indexed Queries**: Strategic indexing on frequently queried fields
- **Connection Pooling**: Efficient database connection management
- **Batch Operations**: Bulk inserts for high-volume data
- **Query Optimization**: Efficient SQLModel queries with proper joins

## Testing Strategy

### TUI Testing (NEW)
- **Textual Testing**: Using Textual's AppTest framework for UI testing
- **Keyboard Navigation**: Automated testing of keyboard shortcuts and navigation
- **Screen Transitions**: Testing view transitions and state management
- **Error Scenarios**: Testing error handling and recovery

### Implementation Testing (Preserved)
- **Unit Tests**: Individual component testing with pytest
- **Integration Tests**: End-to-end workflow testing
- **Tool Testing**: Validation of security tool implementations
- **Skills Testing**: Verification of skill loading and formatting
- **Property-Based Testing**: Using Hypothesis for comprehensive testing

### Security Testing (Preserved)
- **Input Validation**: Fuzzing of tool parameters and inputs
- **Authorization Testing**: Verification of access controls
- **Injection Testing**: SQL injection and XSS prevention
- **Rate Limiting**: DoS protection testing

## Deployment Architecture

### TUI Deployment (NEW)
- **Local Installation**: Poetry/pip installation for development
- **Docker Support**: Containerized deployment with database
- **Remote Access**: SSH-friendly terminal interface
- **Multi-User**: Shared database with multiple TUI instances

### Production Considerations (Updated)
- **Container Orchestration**: Docker Compose for production deployment
- **Database Scaling**: PostgreSQL clustering and read replicas
- **Process Management**: systemd service configuration
- **Monitoring**: Application and database monitoring
- **Backup Strategy**: Automated database backups

## CLI Documentation (NEW)

### Command Interface
```bash
kodiak                    # Launch TUI (default)
kodiak tui               # Explicitly launch TUI
kodiak tui --debug       # Launch with debug mode
kodiak init              # Initialize database
kodiak init --force      # Force reinitialize database
kodiak config           # Interactive LLM configuration
kodiak version          # Show version information
```

### Configuration Management
```bash
# Interactive configuration (recommended)
kodiak config

# Manual configuration via .env file
KODIAK_LLM_PROVIDER=gemini
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_api_key
POSTGRES_SERVER=localhost
POSTGRES_DB=kodiak_db
```

## TUI Navigation Reference (NEW)

### Global Shortcuts
- `q` - Quit application
- `h` - Return to home screen
- `?` - Show help overlay
- `Ctrl+C` - Force quit

### Screen-Specific Shortcuts
- **Home**: `n` (new scan), `d` (delete), `r` (resume), `Enter` (select)
- **Mission Control**: `Tab` (next panel), `g` (graph), `f` (findings), `p` (pause)
- **Agent Chat**: `Left/Right` (switch agents), `Enter` (send message)
- **Graph**: `/` (search), `e` (expand all), `c` (collapse all)
- **Findings**: `1-5` (filter by severity), `e` (export), `a` (agent filter)

## Skills System Specification (Unchanged)

### Skill Definition Format (YAML)
```yaml
name: skill_identifier
description: Brief description of the skill
techniques:
  - List of techniques provided
tools:
  - Recommended tools for this skill
knowledge: |
  Detailed knowledge content in markdown format
examples:
  - title: Example name
    description: Example description
    payload: Example payload or command
    validation: How to validate the result
validation_methods:
  - Methods to confirm findings
references:
  - External references and documentation
```

### Skill Categories
- **vulnerabilities/**: Core vulnerability testing techniques
- **frameworks/**: Framework-specific testing methodologies
- **technologies/**: Technology-specific security testing
- **protocols/**: Protocol-specific testing patterns
- **cloud/**: Cloud provider security testing

## Tool System Specification (Unchanged)

### Tool Implementation Pattern
```python
class ExampleTool(KodiakTool):
    name = "tool_name"
    description = "Tool description"
    args_schema = PydanticArgsModel
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        # OpenAI function schema
        
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        # Tool implementation
        return ToolResult(success=True, output=output, data=data)
```

### Tool Result Format
```python
ToolResult(
    success: bool,           # Execution success status
    output: str,            # Human-readable output
    data: Dict[str, Any],   # Structured data for processing
    error: Optional[str]    # Error message if failed
)
```

## Next Phase Development Plan

### Phase 1: Infrastructure Completion (1-2 weeks)
1. **Database Migrations**: Alembic setup and initial migrations
2. **Advanced Browser Automation**: Multi-tab session management
3. **Production Deployment**: Comprehensive deployment configuration
4. **Advanced Reporting**: Export capabilities and detailed reports

### Phase 2: Advanced Features (2-3 weeks)
1. **Plugin System**: Extensible architecture for custom tools
2. **Advanced Skills**: Cloud-specific and protocol-specific skills
3. **Performance Optimization**: Caching and scaling improvements
4. **Distributed Scanning**: Multi-instance coordination

### Phase 3: Production Readiness (2-3 weeks)
1. **Monitoring**: Performance and security monitoring
2. **Documentation**: Comprehensive user and developer documentation
3. **Testing**: Complete test suite with CI/CD integration
4. **Community**: Open-source preparation and community features

This specification reflects the successful pivot to TUI architecture while preserving all core security testing capabilities and multi-agent coordination features.
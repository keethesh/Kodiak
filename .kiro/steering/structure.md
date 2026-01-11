# Project Structure

## Root Level
- `docker-compose.yml`: Multi-service orchestration (PostgreSQL, backend, frontend)
- `README.md`: Project overview and quick start guide
- `docs/`: Architecture, contributing, deployment, and security documentation
- `scripts/`: Deployment and verification utilities
- `.kiro/steering/`: Project steering documents for AI assistant guidance

## Backend (`backend/`)
```
backend/
├── kodiak/                    # Main Python package
│   ├── api/                   # FastAPI routes and endpoints
│   │   ├── api.py            # Main API router
│   │   └── endpoints/        # Individual endpoint modules
│   │       ├── scans.py      # Scan management endpoints
│   │       ├── projects.py   # Project CRUD operations
│   │       ├── skills.py     # Skills management API
│   │       ├── graph.py      # Knowledge graph endpoints
│   │       ├── approvals.py  # Safety approval workflow
│   │       └── ws.py         # WebSocket connections
│   ├── core/                 # Core business logic
│   │   ├── agent.py          # Enhanced LLM agent with skills
│   │   ├── orchestrator.py   # Task scheduling and coordination
│   │   ├── hive_mind.py      # Command synchronization
│   │   ├── safety.py         # Security controls and approval
│   │   └── tools/            # Tool definitions and inventory
│   │       ├── base.py       # Abstract tool base class
│   │       ├── inventory.py  # Tool registry and management
│   │       └── definitions/  # Individual tool implementations
│   ├── skills/               # Dynamic skills system
│   │   ├── skill_loader.py   # Skill loading and formatting
│   │   ├── skill_registry.py # Skill discovery and validation
│   │   └── definitions/      # YAML skill definitions
│   │       ├── vulnerabilities/ # Core vulnerability skills
│   │       ├── frameworks/   # Framework-specific skills
│   │       └── technologies/ # Technology-specific skills
│   ├── database/             # Data layer
│   │   ├── models.py         # SQLModel definitions
│   │   ├── crud.py           # Database operations
│   │   └── engine.py         # Database connection
│   └── services/             # External service integrations
├── main.py                   # FastAPI application entry point
├── test_implementation.py    # Implementation validation tests
├── pyproject.toml           # Poetry dependencies and config
└── Dockerfile               # Container definition
```

## Frontend (`frontend/`)
```
frontend/
├── app/                     # Next.js App Router
│   ├── layout.tsx          # Root layout component
│   ├── page.tsx            # Home page with project management
│   └── mission/[id]/       # Dynamic mission pages
│       └── page.tsx        # Mission HUD with live updates
├── components/             # Reusable React components
│   ├── HiveGraph.tsx      # Network visualization with vis-network
│   ├── AgentTree.tsx      # Agent hierarchy display
│   └── Terminal.tsx       # Real-time log streaming
├── lib/                   # Utility functions
│   ├── api.ts            # Backend API client
│   └── useWebSocket.ts   # WebSocket hook for real-time updates
├── types/                # TypeScript type definitions
├── package.json          # Node.js dependencies
└── Dockerfile           # Container definition
```

## Steering Documents (`.kiro/steering/`)
- `product.md`: Product overview and core features
- `tech.md`: Technology stack and development commands
- `structure.md`: Project organization and patterns (this file)
- `implementation.md`: Current implementation status and specifications
- `roadmap.md`: Development roadmap and future plans

## Key Architecture Patterns

### Backend Patterns
- **Async/Await**: All database and external operations use async patterns
- **Dependency Injection**: FastAPI's dependency system for database sessions
- **Repository Pattern**: CRUD operations separated from business logic
- **Event-Driven**: Orchestrator polls for tasks and spawns workers
- **Command Pattern**: Tools are encapsulated as executable commands
- **Strategy Pattern**: Skills provide specialized knowledge for different contexts

### Frontend Patterns
- **Server Components**: Next.js App Router with React Server Components
- **Client Components**: Interactive components marked with 'use client'
- **Custom Hooks**: WebSocket and API interactions abstracted into hooks
- **Component Composition**: Small, focused components with clear responsibilities
- **Real-time State**: WebSocket-driven state updates for live dashboard

### Database Schema
- **Graph Structure**: Nodes and Edges represent the attack surface
- **Audit Trail**: AgentLog captures all agent thoughts and actions
- **Command Caching**: CommandCache prevents duplicate tool execution
- **Task Queue**: Task table drives the orchestrator's work distribution
- **Skills Integration**: Dynamic skill loading with agent specialization

### Skills System Architecture
- **YAML Definitions**: Human-readable skill specifications
- **Dynamic Loading**: Runtime skill loading based on agent needs
- **Category Organization**: Structured skill taxonomy
- **Template System**: Jinja2-based skill formatting for agents
- **Validation**: Comprehensive skill validation and dependency checking

### Tool System Architecture
- **Abstract Base**: Common interface for all security tools
- **Schema Generation**: Automatic OpenAI function schema creation
- **Result Standardization**: Consistent ToolResult format
- **Hive Mind Integration**: Automatic command deduplication
- **Safety Integration**: Built-in approval workflow for dangerous operations

### Naming Conventions
- **Python**: snake_case for variables/functions, PascalCase for classes
- **TypeScript**: camelCase for variables/functions, PascalCase for components/types
- **Database**: snake_case table and column names
- **API Endpoints**: kebab-case URLs with RESTful patterns
- **Skills**: snake_case identifiers with descriptive names
- **Tools**: snake_case names matching command-line tool names

## Implementation Status

### ✅ Completed Components
- **Multi-Agent System**: Complete with role-based specialization and Hive Mind coordination
- **Security Tools**: 9 core tools + comprehensive toolkit (20+ tools total)
- **HTTP Proxy System**: Full request/response manipulation and analysis
- **Browser Automation**: Single-page analysis with security vulnerability detection
- **Terminal Environments**: Persistent interactive shells with command history
- **Python Runtime**: Custom exploit development environment with security analysis
- **Skills System**: 8+ skills with dynamic loading capabilities
- **Database Schema**: Complete graph-based persistence layer
- **API Layer**: REST + WebSocket + Skills management
- **Frontend Dashboard**: Core visualization and real-time updates
- **Hive Mind**: Command synchronization and deduplication with real-time updates
- **Safety Framework**: Risk assessment and approval workflow
- **Real-time WebSocket**: Live updates for tools, sessions, and hive mind coordination

### ⚠️ Partially Implemented
- **Multi-tab Browser Sessions**: Framework ready, needs persistent session management
- **Approval Workflow UI**: Backend complete, frontend interface needed
- **Database Migrations**: Schema defined, Alembic setup needed

### 📋 Development Priorities
1. **Multi-tab Browser Sessions**: Complete persistent browser automation
2. **Database Migrations**: Alembic setup for schema management
3. **Approval Workflow UI**: Complete safety system interface
4. **Advanced Reconnaissance**: Enhanced OSINT and attack surface mapping
5. **Production Deployment**: Kubernetes manifests and monitoring
# Technology Stack

## Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI with async/await support
- **Database**: PostgreSQL with SQLModel (SQLAlchemy 2.0)
- **LLM Integration**: LiteLLM for multi-provider support
- **WebSocket**: Real-time communication with frontend
- **Authentication**: python-jose with cryptography (planned)
- **Browser Automation**: Playwright for web application testing
- **HTTP Client**: httpx with async support
- **Configuration**: Pydantic settings with environment variables
- **Task Queue**: Custom orchestrator with database-backed persistence

## Frontend
- **Framework**: Next.js 16+ with React 19
- **Language**: TypeScript 5+
- **Styling**: TailwindCSS 4
- **Visualization**: vis-network for graph rendering
- **Animation**: Framer Motion
- **Icons**: Lucide React
- **Build Tool**: Next.js built-in bundler
- **State Management**: React hooks with WebSocket integration

## Security Tools (Implemented)
- **Network Discovery**: nmap with advanced parsing and vulnerability assessment
- **Vulnerability Scanning**: nuclei with structured JSON output and severity analysis
- **SQL Injection**: sqlmap with comprehensive database testing capabilities
- **Command Injection**: commix for OS command injection detection
- **Subdomain Enumeration**: subfinder for passive reconnaissance
- **HTTP Probing**: httpx with security header analysis and technology detection
- **Browser Automation**: Playwright-based web application testing with vulnerability analysis
- **OSINT**: web search capabilities for reconnaissance
- **System Commands**: terminal execution with safety controls
- **HTTP Proxy System**: Complete request/response manipulation and analysis
- **Terminal Environments**: Persistent interactive shells for command execution
- **Python Runtime**: Custom exploit development and validation environment

## Skills System (Implemented)
- **Dynamic Loading**: YAML-based skill definitions with runtime loading
- **Categories**: Vulnerabilities, frameworks, technologies, protocols, cloud
- **Specializations**: 8+ implemented skills including SQL injection, XSS, command injection
- **Framework Support**: Django, Node.js/Express testing methodologies
- **Technology Focus**: JWT, API testing, web application security

## Infrastructure
- **Database**: PostgreSQL 15 (Alpine)
- **Orchestration**: Docker Compose for development and deployment
- **Development**: Poetry for Python dependency management
- **Code Quality**: Black, isort, mypy, ruff for Python; ESLint for TypeScript
- **Testing**: pytest with async support, custom implementation test suite

## Common Commands

### Development Setup
```bash
# Start full stack
docker-compose up --build

# Backend only (requires PostgreSQL running)
cd backend
poetry install
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend only
cd frontend
npm install
npm run dev

# Run implementation tests
cd backend
python test_implementation.py
```

### Code Quality
```bash
# Backend linting and formatting
cd backend
poetry run black kodiak/
poetry run isort kodiak/
poetry run ruff check kodiak/
poetry run mypy kodiak/

# Frontend linting
cd frontend
npm run lint
```

### Database Operations
```bash
# Access PostgreSQL in Docker
docker-compose exec db psql -U kodiak -d kodiak_db

# Backend database migrations (when implemented)
cd backend
poetry run alembic upgrade head
```

### Skills Management
```bash
# Test skills system
curl http://localhost:8000/api/v1/skills/

# Get skill categories
curl http://localhost:8000/api/v1/skills/categories

# Search skills
curl http://localhost:8000/api/v1/skills/search/sql

# Get skill details
curl http://localhost:8000/api/v1/skills/sql_injection
```

## Environment Variables
- `OPENAI_API_KEY`: Required for LLM functionality
- `KODIAK_MODEL`: LLM model to use (default: gpt-3.5-turbo)
- `POSTGRES_*`: Database connection settings (handled by docker-compose)
- `NEXT_PUBLIC_WS_URL`: WebSocket URL for frontend (defaults to localhost:8000)

## Implementation Status
- **Core Architecture**: ✅ Complete (Multi-agent, Hive Mind, Orchestrator)
- **Security Tools**: ✅ Complete (9 tools fully implemented)
- **Skills System**: ✅ Complete (Dynamic loading, 8+ skills)
- **Database Schema**: ✅ Complete (Full graph-based persistence)
- **API Endpoints**: ✅ Complete (REST + WebSocket + Skills management)
- **Frontend Dashboard**: ✅ Core features (Mission HUD, graph visualization)
- **Authentication**: ⚠️ Planned (Framework ready)
- **Database Migrations**: ⚠️ Needed (Alembic setup required)
- **Production Deployment**: ⚠️ Basic (Docker Compose ready, needs hardening)
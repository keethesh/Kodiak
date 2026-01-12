# Technology Stack

## TUI Application
- **Language**: Python 3.11+
- **TUI Framework**: Textual for modern terminal interfaces with async support
- **Database**: PostgreSQL with SQLModel (SQLAlchemy 2.0)
- **LLM Integration**: LiteLLM for multi-provider support (Gemini, OpenAI, Claude, Ollama, etc.)
- **Browser Automation**: Playwright for web application testing
- **HTTP Client**: httpx with async support
- **Configuration**: Pydantic settings with environment variables
- **Task Queue**: Custom orchestrator with database-backed persistence

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
- **Code Quality**: Black, isort, mypy, ruff for Python
- **Testing**: pytest with async support, Hypothesis for property-based testing

## Common Commands

### Development Setup
```bash
# Configure your LLM (interactive)
kodiak config

# Or manually create .env file
cp .env.example .env
# Edit .env with your API keys and preferences

# Initialize database
kodiak init

# Start TUI application
kodiak

# Or explicitly launch TUI
kodiak tui

# Run with debug mode
kodiak tui --debug
```

### LLM Configuration Examples
```bash
# Gemini 1.5 Pro (Recommended)
export KODIAK_LLM_PROVIDER=gemini
export KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
export GOOGLE_API_KEY=your_google_api_key

# OpenAI GPT-4
export KODIAK_LLM_PROVIDER=openai
export KODIAK_LLM_MODEL=openai/gpt-4
export OPENAI_API_KEY=your_openai_api_key

# Claude 3.5 Sonnet
export KODIAK_LLM_PROVIDER=claude
export KODIAK_LLM_MODEL=claude-3-5-sonnet-20241022
export ANTHROPIC_API_KEY=your_anthropic_api_key
```

### Code Quality
```bash
# Python linting and formatting
poetry run black kodiak/
poetry run isort kodiak/
poetry run ruff check kodiak/
poetry run mypy kodiak/

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=kodiak
```

### Database Operations
```bash
# Initialize database
kodiak init

# Force reinitialize
kodiak init --force

# Access PostgreSQL in Docker
docker-compose exec db psql -U kodiak -d kodiak_db

# Database migrations (when implemented)
poetry run alembic upgrade head
```

### Skills Management
```bash
# Test skills system (via Python)
python -c "
from kodiak.skills.skill_registry import SkillRegistry
registry = SkillRegistry()
registry.load_all_skills()
print('Available skills:', list(registry.skills.keys()))
"
```

## Environment Variables

### LLM Configuration
- `KODIAK_LLM_PROVIDER`: LLM provider (gemini, openai, claude, ollama)
- `KODIAK_LLM_MODEL`: Specific model to use (e.g., gemini/gemini-1.5-pro)
- `GOOGLE_API_KEY`: Google API key for Gemini models
- `OPENAI_API_KEY`: OpenAI API key for GPT models
- `ANTHROPIC_API_KEY`: Anthropic API key for Claude models
- `KODIAK_LLM_TEMPERATURE`: Model temperature (default: 0.1)
- `KODIAK_LLM_MAX_TOKENS`: Maximum tokens per response (default: 4096)

### Database Configuration
- `POSTGRES_SERVER`: Database server hostname (default: localhost)
- `POSTGRES_PORT`: Database port (default: 5432)
- `POSTGRES_DB`: Database name (default: kodiak_db)
- `POSTGRES_USER`: Database user (default: kodiak)
- `POSTGRES_PASSWORD`: Database password (required)

### Application Settings
- `KODIAK_DEBUG`: Enable debug mode (default: false)
- `KODIAK_LOG_LEVEL`: Logging level (default: INFO)
- `KODIAK_ENABLE_SAFETY`: Enable safety checks (default: true)
- `KODIAK_MAX_AGENTS`: Maximum concurrent agents (default: 5)
- `KODIAK_TOOL_TIMEOUT`: Tool execution timeout in seconds (default: 300)
- `KODIAK_ENABLE_HIVE_MIND`: Enable hive mind coordination (default: true)

### TUI Configuration
- `KODIAK_TUI_COLOR_THEME`: Color theme (default: dark)
- `KODIAK_TUI_REFRESH_RATE`: UI refresh rate in Hz (default: 10)

## Implementation Status
- **TUI Architecture**: ✅ Complete (Textual-based terminal interface)
- **Core Architecture**: ✅ Complete (Multi-agent, Hive Mind, Orchestrator)
- **Security Tools**: ✅ Complete (20+ tools fully implemented)
- **Skills System**: ✅ Complete (Dynamic loading, 8+ skills)
- **Database Schema**: ✅ Complete (Full graph-based persistence)
- **CLI Interface**: ✅ Complete (init, config, tui commands)
- **Error Handling**: ✅ Complete (Comprehensive error management)
- **Database Migrations**: ⚠️ Needed (Alembic setup required)
- **Production Deployment**: ✅ Ready (Docker Compose + systemd support)
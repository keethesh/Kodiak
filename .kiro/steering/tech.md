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

## LLM Integration

Kodiak uses [LiteLLM](https://docs.litellm.ai/) for unified access to multiple LLM providers. This allows seamless switching between different models and providers using a consistent interface.

### Supported Providers
- **Google Gemini**: Latest models including Gemini 3 Pro Preview
- **OpenAI**: GPT-5, GPT-4 Turbo, and other GPT models
- **Anthropic**: Claude 4.5 Sonnet, Claude 3.5 Sonnet
- **Ollama**: Local models for privacy and offline usage
- **Azure OpenAI**: Enterprise deployments
- **Many others**: See [LiteLLM providers documentation](https://docs.litellm.ai/docs/providers)

### Model Selection Guidelines
- **Security Analysis**: Gemini 3 Pro Preview, Claude 4.5 Sonnet
- **General Purpose**: GPT-5, Gemini 1.5 Pro
- **Fast Operations**: Gemini 1.5 Flash, GPT-4 Turbo
- **Privacy/Offline**: Ollama models (llama3.1:70b, codellama:34b)
- **Cost Optimization**: Gemini 1.5 Flash, smaller Ollama models

### Configuration Format
Use the LiteLLM format: `provider/model-name`
```bash
# Examples
KODIAK_LLM_MODEL=gemini/gemini-3-pro-preview
KODIAK_LLM_MODEL=openai/gpt-5
KODIAK_LLM_MODEL=anthropic/claude-4.5-sonnet
KODIAK_LLM_MODEL=ollama/llama3.1:70b
```

For complete model lists and configuration options, see the [LiteLLM documentation](https://docs.litellm.ai/docs/providers).

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
# Gemini 3 Pro Preview (Recommended - Latest model with best security analysis)
export KODIAK_LLM_MODEL=gemini/gemini-3-pro-preview
export GOOGLE_API_KEY=your_google_api_key

# Gemini 1.5 Pro (Stable - Excellent for complex reasoning)
export KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
export GOOGLE_API_KEY=your_google_api_key

# GPT-5 (Latest OpenAI - Excellent reasoning capabilities)
export KODIAK_LLM_MODEL=openai/gpt-5
export OPENAI_API_KEY=your_openai_api_key

# Claude 4.5 Sonnet (Latest Anthropic - Best for security analysis)
export KODIAK_LLM_MODEL=anthropic/claude-4.5-sonnet
export ANTHROPIC_API_KEY=your_anthropic_api_key

# Ollama Local (Privacy-focused - No API key required)
export KODIAK_LLM_MODEL=ollama/llama3.1:70b
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
- `KODIAK_LLM_MODEL`: LiteLLM model string (e.g., gemini/gemini-3-pro-preview, openai/gpt-5)
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
# Contributing to Kodiak

We welcome contributions to Kodiak! Since this is a security tool, please follow our guidelines strictly.

## Development Setup

### Prerequisites
- Python 3.11+
- Poetry (Python dependency management)
- Docker and Docker Compose
- PostgreSQL (or use Docker Compose)

### Quick Start
1. **Clone and Setup**:
   ```bash
   git clone https://github.com/your-org/kodiak.git
   cd kodiak
   poetry install
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your LLM API keys
   kodiak config  # Interactive configuration
   ```

3. **Initialize Database**:
   ```bash
   # Option 1: Use Docker Compose (recommended)
   docker-compose up -d db
   
   # Option 2: Local PostgreSQL
   # Ensure PostgreSQL is running locally
   
   # Initialize schema
   kodiak init
   ```

4. **Start Development**:
   ```bash
   # Run the TUI application
   kodiak tui --debug
   
   # Or run tests
   poetry run pytest
   ```

## Development Workflow

### TUI Development
The Terminal User Interface is built with Textual framework:

```bash
# Run with debug mode for development
kodiak tui --debug

# Test specific TUI components
poetry run python -c "from kodiak.tui.widgets.status_bar import StatusBar; print('Widget imports work')"

# Run TUI tests
poetry run pytest tests/tui/ -v
```

### Core Logic Development
```bash
# Test core functionality
poetry run pytest tests/core/ -v

# Test database operations
poetry run pytest tests/database/ -v

# Test security tools
poetry run pytest tests/tools/ -v
```

## Code Standards

### Python Code Quality
- **Formatting**: We use `black` for code formatting
- **Linting**: We use `ruff` for linting and `mypy` for type checking
- **Import Sorting**: We use `isort` for import organization

```bash
# Run all code quality checks
poetry run black kodiak/
poetry run isort kodiak/
poetry run ruff check kodiak/
poetry run mypy kodiak/
```

### Type Hints
- Strict type checking is enforced
- All functions must have type hints
- Pydantic models must be used for all data structures
- Use `from __future__ import annotations` for forward references

### Security Guidelines
- **NEVER commit API keys or secrets**
- Use `.env` files for configuration
- All external tool execution must be sandboxed
- Validate all user inputs
- Follow principle of least privilege

## Adding New Features

### Adding Security Tools
1. Create a tool class in `kodiak/core/tools/definitions/`:
   ```python
   from kodiak.core.tools.base import Tool, ToolResult
   
   class MyTool(Tool):
       name = "mytool"
       description = "Description of what the tool does"
       
       async def execute(self, **kwargs) -> ToolResult:
           # Implementation
           pass
   ```

2. Register it in `kodiak/core/tools/inventory.py`
3. Add tests in `tests/tools/`
4. Update documentation

### Adding TUI Views
1. Create view in `kodiak/tui/views/`:
   ```python
   from textual.screen import Screen
   from kodiak.tui.views.base import BaseView
   
   class MyView(BaseView):
       # Implementation
       pass
   ```

2. Add navigation in `kodiak/tui/app.py`
3. Add keyboard shortcuts
4. Update help documentation

### Adding Skills
1. Create YAML skill definition in `kodiak/skills/definitions/`
2. Follow existing skill format and validation
3. Test skill loading and formatting
4. Update skills documentation

## Testing Guidelines

### Test Structure
```bash
tests/
├── core/           # Core business logic tests
├── tui/            # TUI component tests
├── database/       # Database operation tests
├── tools/          # Security tool tests
├── skills/         # Skills system tests
└── integration/    # End-to-end tests
```

### Running Tests
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=kodiak

# Run specific test categories
poetry run pytest tests/core/ -v
poetry run pytest tests/tui/ -v

# Run integration tests (requires Docker)
poetry run pytest tests/integration/ -v
```

### Test Requirements
- All new features must have tests
- Aim for >90% code coverage
- Use pytest fixtures for common setup
- Mock external dependencies appropriately
- Test both success and failure cases

## Documentation

### Required Documentation
- Update relevant docstrings
- Add examples for new features
- Update keyboard shortcuts if applicable
- Update architecture documentation for significant changes

### Documentation Files
- `README.md`: Project overview and quick start
- `docs/TUI_GUIDE.md`: Comprehensive TUI usage guide
- `docs/KEYBOARD_SHORTCUTS.md`: Quick reference
- `docs/ARCHITECTURE.md`: Technical architecture
- `docs/DEPLOYMENT.md`: Production deployment guide

## Pull Request Process

### Before Submitting
1. **Code Quality**: Ensure all linting and type checking passes
2. **Tests**: All tests must pass, add tests for new features
3. **Documentation**: Update relevant documentation
4. **Security**: Review for security implications

### PR Requirements
- **Descriptive Title**: Clear, concise description of changes
- **Semantic Commits**: Use conventional commit format
  - `feat: add new vulnerability scanner`
  - `fix: resolve agent synchronization issue`
  - `docs: update TUI navigation guide`
  - `refactor: improve database query performance`
- **Description**: Explain what, why, and how
- **Testing**: Describe testing performed
- **Breaking Changes**: Clearly mark any breaking changes

### Review Process
1. Automated checks must pass (CI/CD)
2. Code review by maintainers
3. Security review for tool additions
4. Documentation review
5. Final approval and merge

## Development Environment

### Recommended Tools
- **Editor**: VS Code with Python extension
- **Terminal**: Modern terminal with Unicode support
- **Docker**: For tool sandboxing and database
- **Git**: For version control

### VS Code Configuration
```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "python.linting.enabled": true,
    "python.linting.ruffEnabled": true,
    "python.formatting.provider": "black",
    "python.sortImports.args": ["--profile", "black"]
}
```

### Environment Variables
Key environment variables for development:
```bash
# LLM Configuration
KODIAK_LLM_PROVIDER=gemini
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_api_key

# Database
POSTGRES_SERVER=localhost
POSTGRES_PORT=5432
POSTGRES_DB=kodiak_db
POSTGRES_USER=kodiak
POSTGRES_PASSWORD=kodiak

# Development
KODIAK_DEBUG=true
KODIAK_LOG_LEVEL=DEBUG
```

## Community Guidelines

### Communication
- Be respectful and professional
- Use GitHub Issues for bug reports and feature requests
- Use GitHub Discussions for questions and ideas
- Follow the code of conduct

### Security Reporting
- **DO NOT** open public issues for security vulnerabilities
- Email security issues to: security@kodiak-project.org
- Include detailed reproduction steps
- Allow reasonable time for response before disclosure

### Getting Help
1. Check existing documentation
2. Search GitHub Issues
3. Ask in GitHub Discussions
4. Join community chat (if available)

Thank you for contributing to Kodiak! Your contributions help make security testing more accessible and effective for everyone.

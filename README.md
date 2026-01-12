# Kodiak 🐻

> **Advanced LLM-Powered Penetration Testing Suite with Terminal Interface**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Kodiak is an advanced LLM-powered penetration testing suite that uses AI agents with intelligent coordination to automate security assessments. Built with a modern Terminal User Interface (TUI), Kodiak provides a seamless, keyboard-driven experience for security professionals.

## ✨ Features

### 🖥️ Modern Terminal Interface
- **Rich TUI**: Built with [Textual](https://textual.textualize.io/) for a modern terminal experience
- **Keyboard Navigation**: Complete keyboard-driven workflow for efficiency
- **Real-time Updates**: Live monitoring of agent activities and scan progress
- **Multi-view Dashboard**: Dedicated screens for projects, scans, findings, and agent communication

### 🤖 Intelligent Multi-Agent System
- **Coordinated Agents**: Multiple AI agents work together to perform comprehensive security testing
- **Hive Mind Architecture**: Agents share knowledge and coordinate to prevent duplicate work
- **Persistent State**: Database-backed execution allows pausing, resuming, and replaying scans
- **Real-time Collaboration**: Agents communicate findings and coordinate next steps automatically

### 🛠️ Comprehensive Security Toolkit
- **Network Discovery**: nmap, subfinder, httpx for reconnaissance
- **Vulnerability Scanning**: nuclei, sqlmap, commix for automated testing
- **Web Application Testing**: Browser automation with Playwright
- **Custom Exploitation**: HTTP proxy system and Python runtime for custom payloads
- **OSINT Capabilities**: Web search and information gathering

### 🎯 Advanced Vulnerability Detection
- **Injection Attacks**: SQL, NoSQL, command injection with intelligent validation
- **Web Vulnerabilities**: XSS, CSRF, authentication bypasses, business logic flaws
- **Infrastructure Issues**: Misconfigurations, exposed services, privilege escalation
- **API Security**: REST/GraphQL testing, JWT vulnerabilities, rate limiting bypasses

## 🚀 Quick Start

### Prerequisites
- **Python 3.11+**
- **PostgreSQL** (or Docker for easy setup)
- **LLM API Key** (Gemini, OpenAI, Claude, or others)

### Installation

#### Option 1: Using Poetry (Recommended)
```bash
git clone https://github.com/yourusername/kodiak.git
cd kodiak
poetry install
```

#### Option 2: Using pip
```bash
git clone https://github.com/yourusername/kodiak.git
cd kodiak
pip install -e .
```

### Setup

#### 1. Configure Your LLM Provider
```bash
# Interactive configuration (recommended)
kodiak config

# Or manually create .env file
cp .env.example .env
# Edit .env with your API keys
```

#### 2. Initialize Database
```bash
# Start PostgreSQL (using Docker)
docker-compose up -d db

# Initialize Kodiak database
kodiak init
```

#### 3. Launch Kodiak
```bash
# Start the TUI interface
kodiak

# Or explicitly launch TUI
kodiak tui
```

## 🎮 Usage

### Navigation
- **Global Shortcuts**:
  - `q` - Quit application
  - `h` - Return to home screen
  - `?` - Show help overlay
  - `Ctrl+C` - Force quit

### Home Screen
- **`n`** - Create new scan
- **`Enter`** - Select project/scan
- **`d`** - Delete selected item
- **`r`** - Resume paused scan

### Mission Control
- **`Tab`** - Cycle between panels (agents, graph, logs)
- **`g`** - View full attack surface graph
- **`f`** - View findings report
- **`p`** - Pause/resume current scan

### Agent Chat
- **`Left/Right`** - Switch between agents
- **`Enter`** - Send message to agent
- **`Escape`** - Return to mission control

## 🤖 Supported LLM Providers

Kodiak supports multiple LLM providers through [LiteLLM](https://docs.litellm.ai/):

| Provider | Recommended Models | API Key |
|----------|-------------------|---------|
| **Google Gemini** ⭐ | `gemini-1.5-pro`, `gemini-1.5-flash` | `GOOGLE_API_KEY` |
| **Anthropic Claude** | `claude-3-5-sonnet`, `claude-3-opus` | `ANTHROPIC_API_KEY` |
| **OpenAI** | `gpt-4`, `gpt-4-turbo` | `OPENAI_API_KEY` |
| **Local (Ollama)** | `llama2`, `codellama` | No API key needed |

### Configuration Examples

**Gemini (Recommended)**:
```bash
export KODIAK_LLM_PROVIDER=gemini
export KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
export GOOGLE_API_KEY=your_api_key_here
```

**Claude**:
```bash
export KODIAK_LLM_PROVIDER=claude
export KODIAK_LLM_MODEL=claude-3-5-sonnet-20241022
export ANTHROPIC_API_KEY=your_api_key_here
```

**OpenAI**:
```bash
export KODIAK_LLM_PROVIDER=openai
export KODIAK_LLM_MODEL=openai/gpt-4
export OPENAI_API_KEY=your_api_key_here
```

## 🏗️ Architecture

### TUI Architecture
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

### Key Components
- **TUI Layer**: Modern terminal interface built with Textual
- **Core Engine**: Multi-agent coordination and state management
- **Services Layer**: Security tools, LLM integration, and hive mind
- **Database**: PostgreSQL for persistent state and audit trails

### Multi-Agent Coordination
- **Specialized Agents**: Each agent focuses on specific security domains
- **Hive Mind**: Shared knowledge base prevents duplicate work
- **Real-time Updates**: Agents communicate findings instantly
- **Persistent Sessions**: Resume scans across application restarts

## 🛠️ Development

### Project Structure
```
kodiak/
├── kodiak/
│   ├── tui/                 # Terminal User Interface
│   │   ├── app.py          # Main TUI application
│   │   ├── views/          # Screen implementations
│   │   └── widgets/        # Reusable UI components
│   ├── core/               # Core business logic
│   │   ├── agent.py        # LLM agent implementation
│   │   ├── orchestrator.py # Multi-agent coordination
│   │   └── tools/          # Security tool integrations
│   ├── database/           # Data persistence layer
│   └── services/           # External service integrations
├── tests/                  # Test suite
├── docs/                   # Documentation
└── pyproject.toml         # Project configuration
```

### Running Tests
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=kodiak

# Run specific test file
poetry run pytest tests/test_tui.py
```

### Code Quality
```bash
# Format code
poetry run black kodiak/
poetry run isort kodiak/

# Lint code
poetry run ruff check kodiak/
poetry run mypy kodiak/
```

## 📚 Documentation

- **[Installation Guide](docs/INSTALLATION.md)** - Detailed setup instructions
- **[User Guide](docs/USER_GUIDE.md)** - Complete usage documentation
- **[Architecture Guide](docs/ARCHITECTURE.md)** - Technical architecture overview
- **[API Reference](docs/API.md)** - Core API documentation
- **[Contributing Guide](CONTRIBUTING.md)** - How to contribute to Kodiak
- **[Security Policy](SECURITY.md)** - Security guidelines and reporting

## 🤝 Contributing

We welcome contributions from the security community! Here's how you can help:

### Ways to Contribute
- 🐛 **Bug Reports**: Found an issue? [Open an issue](https://github.com/yourusername/kodiak/issues)
- 💡 **Feature Requests**: Have an idea? [Start a discussion](https://github.com/yourusername/kodiak/discussions)
- 🔧 **Code Contributions**: Submit pull requests for bug fixes or new features
- 📖 **Documentation**: Help improve our docs and guides
- 🧪 **Testing**: Add test cases or test on different environments

### Development Setup
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `poetry run pytest`
5. Submit a pull request

### Code Standards
- Follow [PEP 8](https://pep8.org/) style guidelines
- Add type hints for all functions
- Write comprehensive tests for new features
- Update documentation for user-facing changes

## 🔒 Security

### Responsible Disclosure
If you discover a security vulnerability, please follow our [Security Policy](SECURITY.md):
- **DO NOT** open a public issue
- Email security issues to: security@kodiak-project.org
- Include detailed reproduction steps and impact assessment

### Security Considerations
- Kodiak is designed for authorized security testing only
- Always obtain proper authorization before testing targets
- Use in isolated environments when possible
- Keep LLM API keys secure and rotate regularly

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

### Third-Party Licenses
- [Textual](https://github.com/Textualize/textual) - MIT License
- [LiteLLM](https://github.com/BerriAI/litellm) - MIT License
- [SQLModel](https://github.com/tiangolo/sqlmodel) - MIT License

## 🙏 Acknowledgments

- **[Textual](https://textual.textualize.io/)** - For the amazing TUI framework
- **[LiteLLM](https://docs.litellm.ai/)** - For unified LLM provider support
- **Security Community** - For inspiration and feedback
- **Contributors** - Thank you for making Kodiak better!

## 📊 Project Status

- ✅ **Core TUI Interface** - Complete
- ✅ **Multi-Agent System** - Complete  
- ✅ **Security Tools Integration** - Complete
- ✅ **Database Persistence** - Complete
- 🚧 **Advanced Reporting** - In Progress
- 📋 **Plugin System** - Planned
- 📋 **Distributed Scanning** - Planned

---

**Made with ❤️ by the security community, for the security community.**

[⭐ Star us on GitHub](https://github.com/yourusername/kodiak) | [📖 Read the Docs](https://kodiak-docs.org) | [💬 Join Discussions](https://github.com/yourusername/kodiak/discussions)

# Kodiak

**AI-Powered Penetration Testing Suite with Terminal Interface**

Kodiak is an advanced LLM-powered penetration testing suite that uses AI agents with intelligent coordination to automate security assessments. Built with a modern Terminal User Interface (TUI), Kodiak provides a seamless, keyboard-driven experience for security professionals who prefer working in terminal environments.

[![Python](https://img.shields.io/pypi/pyversions/kodiak-pentest?color=3776AB)](https://pypi.org/project/kodiak-pentest/)
[![PyPI](https://img.shields.io/pypi/v/kodiak-pentest?color=10b981)](https://pypi.org/project/kodiak-pentest/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## 🚀 Quick Start

**Prerequisites:**
- Python 3.11+
- Docker (for security toolbox container)
- An LLM provider API key (OpenAI, Google,Anthropic, or local Ollama)

### One-Command Installation

```bash
# Install Kodiak with zero configuration required
curl -sSL https://raw.githubusercontent.com/keethesh/Kodiak/main/install.sh | bash
```

This installs:
- ✅ `kodiak` CLI tool
- ✅ SQLite database (no external dependencies)
- ✅ Interactive configuration wizard

### First Run

```bash
# Launch interactive configuration wizard
kodiak config
# Choose LLM provider → Enter API key → Select SQLite (default)

# Initialize database
kodiak init
# Creates ~/.kodiak/kodiak.db automatically

# Launch TUI interface
kodiak

# Or scan a target directly
kodiak --target ./my-application
```

## 🎯 Core Features

### 🖥️ Modern Terminal Interface
- **Rich TUI Experience**: Built with Textual for responsive terminal interface
- **Keyboard-Driven Workflow**: Complete navigation via keyboard shortcuts
- **Real-time Updates**: Live monitoring of agent activities and findings
- **Multi-view Dashboard**: Dedicated screens for projects, agents, and reporting

### 🤖 AI Agent Coordination
- **Multi-Agent System**: Specialized AI agents working together
- **Hive Mind Architecture**: Shared knowledge and coordinated execution
- **Persistent State**: SQLite-backed sessions with pause/resume capability
- **Intelligent Reasoning**: LLM-powered decision making and adaptation

### 🛠️ Comprehensive Security Toolkit (Dockerized)
All security tools run in a Kali Linux container - **no local installation needed**:
- **Network Discovery**: nmap, subfinder, httpx reconnaissance
- **Vulnerability Scanning**: nuclei with 5000+ templates
- **Web Application Testing**: Playwright browser automation
- **Injection Testing**: sqlmap, commix with intelligent validation
- **Custom Exploitation**: HTTP proxy system and Python runtime

### 📚 Specialized Skills System
- **Dynamic Loading**: Agents load specialized skills per task
- **Vulnerability-Specific**: Advanced techniques for SQLi, XSS, etc.
- **Framework-Specific**: Django, Express, FastAPI testing
- **Technology-Specific**: Supabase, Firebase, Auth0 integration testing

## 🔧 Installation Options

### Recommended: One-Command Install
```bash
# Installs Kodiak with SQLite database (local mode)
curl -sSL https://raw.githubusercontent.com/keethesh/Kodiak/main/install.sh | bash
```

### Alternative: Python Package Managers
```bash
# UV (recommended)
uv tool install kodiak-pentest[local]

# Or with pip
pip install kodiak-pentest[local]
```

### PostgreSQL Mode (Optional)
For production deployments with multiple users:
```bash
# Install with PostgreSQL support
pip install kodiak-pentest[full]

# Configure PostgreSQL
kodiak config --advanced
```

### Development Installation
```bash
git clone https://github.com/keethesh/Kodiak.git
cd Kodiak
make setup-dev
```

## 📖 Usage

### Command Line Interface

```bash
# Show help
kodiak --help

# Check installation
kodiak doctor

# Interactive configuration
kodiak config

# Initialize database
kodiak init

# Launch TUI
kodiak tui

# Quick scan
kodiak --target https://example.com

# API server mode
kodiak api --port 8000
```

### TUI Navigation

- **Tab/Shift+Tab**: Navigate between panels
- **Enter**: Select/activate items
- **Escape**: Go back/cancel
- **Ctrl+C**: Exit application
- **F1**: Help screen
- **F2**: Agent chat
- **F3**: Findings view
- **F4**: Graph visualization

## 🏗️ Architecture

### Multi-Agent System
- **Reconnaissance Agent**: Network discovery and enumeration
- **Web Agent**: Application testing and browser automation
- **Exploitation Agent**: Vulnerability validation and PoC generation
- **Analysis Agent**: Finding correlation and reporting

### Hive Mind Coordination
- **Shared Knowledge**: Agents share discoveries in real-time
- **Command Deduplication**: Prevents redundant tool execution
- **Intelligent Routing**: Tasks assigned to most suitable agents
- **Persistent Memory**: Complete audit trail and session state

### Database Schema
- **Graph-Based**: Nodes and edges represent attack surface
- **Audit Trail**: Complete logging of agent actions and decisions
- **Findings Management**: Structured vulnerability data with evidence
- **Session Persistence**: Resume scans across application restarts

## 🔒 Security & Safety

- **Sandboxed Execution**: All tools run in isolated environments
- **Approval Workflow**: Built-in safety checks for high-risk operations
- **Configurable Safety**: Adjustable safety levels for different environments
- **Audit Logging**: Complete trail of all actions for compliance

## 🌐 LLM Provider Support

Kodiak uses [LiteLLM](https://docs.litellm.ai/) for unified access to multiple providers:

### Supported Providers
- **Google Gemini**: `gemini/gemini-1.5-pro`, `gemini/gemini-3-pro-preview`
- **OpenAI**: `openai/gpt-4`, `openai/gpt-5`
- **Anthropic**: `anthropic/claude-3-5-sonnet-20241022`, `anthropic/claude-4.5-sonnet`
- **Local Models**: `ollama/llama3.1:70b`, `ollama/codellama:34b`
- **Azure OpenAI**: Enterprise deployments
- **Many others**: See [LiteLLM providers](https://docs.litellm.ai/docs/providers)

### Configuration Examples
```bash
# Gemini (Recommended)
export KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
export GOOGLE_API_KEY=your_api_key

# OpenAI
export KODIAK_LLM_MODEL=openai/gpt-4
export OPENAI_API_KEY=your_api_key

# Local Ollama (Privacy-focused)
export KODIAK_LLM_MODEL=ollama/llama3.1:70b
```

## 🐳 Docker Usage

For containerized deployment (alternative to global installation):

```bash
# Clone repository
git clone https://github.com/keethesh/Kodiak.git
cd Kodiak

# Start services
docker-compose up --build

# Run commands
docker-compose run --rm kodiak kodiak init
docker-compose run --rm kodiak kodiak tui
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines.

### Development Setup
```bash
git clone https://github.com/keethesh/Kodiak.git
cd Kodiak
make setup-dev
make check-all
```

### Code Quality
```bash
make format      # Format code
make lint        # Lint code
make type-check  # Type checking
make test        # Run tests
```

## 📚 Documentation

- [Architecture Guide](docs/ARCHITECTURE.md)
- [TUI User Guide](docs/TUI_GUIDE.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## 📄 License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with [Textual](https://textual.textualize.io/) for the modern TUI
- Powered by [LiteLLM](https://docs.litellm.ai/) for multi-provider LLM access
- Integrates industry-standard security tools (nmap, nuclei, sqlmap, etc.)

---

**Kodiak** - Intelligent AI-powered penetration testing for the modern security professional.
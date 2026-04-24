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
- An OpenRouter API key

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
# Enter OpenRouter API key → Choose model → Select SQLite (default)

# Initialize database
kodiak init
# Creates ~/.kodiak/kodiak.db automatically

# Launch TUI interface
kodiak

# Or scan a target directly
kodiak scan https://example.com
```

## 🎯 Core Features

### 🖥️ Modern Terminal Interface
- **Rich TUI Experience**: Built with Textual for responsive terminal interface
- **Keyboard-Driven Workflow**: Complete navigation via keyboard shortcuts
- **Real-time Updates**: Live monitoring of agent activities and findings
- **Multi-view Dashboard**: Dedicated screens for projects, agents, and reporting

### 🤖 AI-Powered Execution
- **Kernel-First Runtime**: Planner + Analyst + parallel worker pool
- **Structured Scanning**: RECON → ENUMERATION → VULN_SCAN → EXPLOITATION
- **Persistent State**: SQLite-backed shared store with scan projections
- **Intelligent Reasoning**: Planner handles execution strategy, Analyst interprets evidence

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

# Launch TUI
kodiak tui

# Quick scan
kodiak scan https://example.com

# Explicit scan command
kodiak scan https://example.com --instructions "Passive recon only" --workers 6
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

### Multi-Agent Pipeline
- **Planner + Analyst Agents**: Specialized reasoning stages coordinate scan strategy
- **Parallel Workers**: Stateless tool executors run concurrently
- **Phased Execution**: RECON → ENUMERATION → VULN_SCAN → EXPLOITATION
- **Per-Tool Concurrency**: Limits prevent WAF tripping and resource exhaustion

### Execution State
- **Single Runtime Path**: Manager-era runtime has been removed from the active code path
- **Persistent Shared Store**: Planner, workers, and analyst coordinate through DB-backed state
- **Projection-Backed Reads**: CLI/TUI consume derived scan projections

### Database Schema
- **Kernel Work Queue**: Single-scope `WorkUnit` records drive execution
- **Evidence Model**: Observations, capabilities, hypotheses, findings, notes, attempts
- **Audit Trail**: Complete logging through `ScanEvent`
- **Session Persistence**: Resume scan state across application restarts

### Database Compatibility
- Existing old SQLite schemas are not migrated in place.
- If Kodiak detects a legacy database, reset it with:

```bash
kodiak migrate --reset --force
```

## 🔒 Security & Safety

- **Sandboxed Execution**: All tools run in isolated environments
- **Approval Workflow**: Built-in safety checks for high-risk operations
- **Configurable Safety**: Adjustable safety levels for different environments
- **Audit Logging**: Complete trail of all actions for compliance

## 🌐 OpenRouter Model Support

Kodiak's current MVP runtime is OpenRouter-only. Direct Gemini, OpenAI, or Anthropic provider setup is unsupported for this milestone; use their models through OpenRouter model IDs.

### Configuration Examples
```bash
export KODIAK_LLM_PROVIDER=openrouter
export KODIAK_OPENROUTER_API_KEY=your_openrouter_api_key
export KODIAK_PLANNER_MODEL=anthropic/claude-3.5-haiku-20241022
export KODIAK_ANALYST_MODEL=anthropic/claude-3.5-sonnet-20241022
export KODIAK_LLM_MODEL=anthropic/claude-3.5-sonnet-20241022
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
- Powered by OpenRouter-backed LLM integration
- Integrates industry-standard security tools (nmap, nuclei, sqlmap, etc.)

---

**Kodiak** - Intelligent AI-powered penetration testing for the modern security professional.

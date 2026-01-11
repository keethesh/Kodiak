# Kodiak 🐻

> **Advanced LLM-based Penetration Testing Suite with Multi-Agent Coordination**

Kodiak is an advanced LLM-based penetration testing suite that uses AI agents with a "Hive Mind" architecture to intelligently orchestrate security assessments. It features multi-agent coordination, persistent state management, and real-time collaboration capabilities.

## 🎯 Key Features

### 🛠️ Comprehensive Security Toolkit
- **Full HTTP Proxy**: Complete request/response manipulation and analysis
- **Browser Automation**: Multi-tab browser testing for XSS, CSRF, and auth flows  
- **Terminal Environments**: Interactive shells for command execution and testing
- **Python Runtime**: Custom exploit development and validation
- **Reconnaissance**: Automated OSINT and attack surface mapping

### 🧠 Enhanced Multi-Agent Architecture
- **Hive Mind Coordination**: Multiple agents share tool output streams and coordinate execution to prevent duplicate work
- **Persistent State**: Database-backed execution allows pausing, resuming, and replaying scans across sessions
- **Graph-Based Workflow**: Uses deterministic state machines combined with LLM reasoning for structured penetration testing
- **Real-time UI**: Next.js dashboard provides live visualization of the attack surface and agent activities

### 🎯 Advanced Vulnerability Detection
- **Injection Attacks**: SQL, NoSQL, command injection with validation
- **Server-Side**: SSRF, XXE, deserialization flaws
- **Client-Side**: XSS, prototype pollution, DOM vulnerabilities
- **Authentication**: JWT vulnerabilities, session management
- **Infrastructure**: Misconfigurations, exposed services

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- LLM API Key (Gemini, OpenAI, Claude, or others)

### 1. Configure Your LLM
Choose your preferred AI provider:

**Option A: Interactive Configuration (Recommended)**
```bash
git clone https://github.com/yourusername/kodiak.git
cd kodiak
python configure_llm.py
```

**Option B: Manual Configuration**
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your preferred settings
# For Gemini (recommended):
KODIAK_LLM_PROVIDER=gemini
KODIAK_LLM_MODEL=gemini/gemini-1.5-pro
GOOGLE_API_KEY=your_google_api_key_here
```

### 2. Launch Kodiak
```bash
docker-compose up --build
```

### 3. Access the Dashboard
- **Frontend**: http://localhost:3000
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

## 🤖 Supported LLM Providers

Kodiak supports multiple LLM providers through LiteLLM:

| Provider | Models | Configuration |
|----------|--------|---------------|
| **Google Gemini** | `gemini-1.5-pro`, `gemini-1.5-flash` | `GOOGLE_API_KEY` |
| **OpenAI** | `gpt-4`, `gpt-4-turbo`, `gpt-3.5-turbo` | `OPENAI_API_KEY` |
| **Anthropic Claude** | `claude-3-5-sonnet`, `claude-3-opus` | `ANTHROPIC_API_KEY` |
| **Others** | Ollama, Azure, Cohere, HuggingFace | See [LiteLLM docs](https://docs.litellm.ai/) |

### Recommended Models for Security Testing
- **Gemini 1.5 Pro**: Excellent reasoning and code analysis capabilities
- **Claude 3.5 Sonnet**: Outstanding for security analysis and vulnerability assessment
- **GPT-4**: Proven performance for complex security tasks

## 🛠️ Security Tools Included

Kodiak includes 20+ integrated security tools:

- **Network**: nmap, nuclei, subfinder, httpx
- **Web Application**: sqlmap, commix, browser automation
- **Custom Development**: HTTP proxy, terminal environments, Python runtime
- **OSINT**: Web search and reconnaissance capabilities

## 🏗️ Architecture

### Multi-Agent Coordination
- Agents specialize in different aspects of security testing
- Hive Mind prevents duplicate tool execution across agents
- Real-time coordination through WebSocket updates

### Persistent State Management
- Database-backed execution state
- Pause and resume scans across sessions
- Complete audit trail of all agent actions

### Skills System
- Dynamic loading of specialized knowledge
- 8+ pre-built skills for different vulnerability classes
- Framework-specific testing capabilities (Django, Node.js, etc.)

### Security Model
- No authentication required - designed as a security tool
- Configurable access controls for production deployments
- Secure credential storage for LLM API keys and target credentials

## 📚 Documentation

- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Documentation](http://localhost:8000/docs) (when running)
- [Skills System Guide](docs/SKILLS.md)
- [Contributing Guide](docs/CONTRIBUTING.md)

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](docs/CONTRIBUTING.md) for details.

## 📄 License

Apache 2.0 - see [LICENSE](LICENSE) for details.

## 🔒 Security

For security issues, please see our [Security Policy](docs/SECURITY.md).

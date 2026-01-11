# Kodiak 🐻

> **The Advanced LLM-based Penetration Testing Suite.**

Kodiak is an open-source, modern alternative to traditional automated scanners. It uses LLM Agents with a "Hive Mind" architecture to intelligently orchestrate penetration tests, avoiding the pitfalls of redundant scanning and "dumb" brute forcing.

## Features
- **🧠 Hive Mind**: Synchronized tool execution. Multiple agents share the same tool output streams.
- **💾 Persistent State**: Pause, resume, and replay scans. Database-backed execution.
- **🕸️ Graph-Based Workflow**: Deterministic state machines combined with LLM reasoning.
- **🛡️ Sandboxed Execution**: All dangerous tools run in isolated Docker containers.
- **✨ Premium UI**: Real-time Next.js visualization of the attack surface.

## Quick Start

### Prerequisites
- Docker & Docker Compose
- OpenAI API Key (or other LLM provider)

### Run
```bash
git clone https://github.com/yourusername/kodiak.git
cd kodiak
docker-compose up --build
```
Access the dashboard at `http://localhost:3000`.

## Documentation
- [Architecture Overview](docs/ARCHITECTURE.md)
- [Contributing Guide](docs/CONTRIBUTING.md)
- [Security Policy](docs/SECURITY.md)

## License
Apache 2.0

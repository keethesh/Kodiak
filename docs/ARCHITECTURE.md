# Kodiak Architecture

## Philosophy

Kodiak is an AI-powered penetration testing platform built around **persistent state**, **structured coordination**, and **specialized agents**. The system replaces monolithic agent designs with a pipeline of specialized components that communicate through a shared database store.

## Core Architecture

### Multi-Agent Pipeline

Kodiak uses a three-component pipeline architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                     MultiAgentOrchestrator                      │
│                                                                  │
│   ┌────────────┐         ┌────────────┐         ┌───────────┐ │
│   │  Planner   │────────▶│  Workers   │────────▶│  Analyst  │ │
│   │  (Flash)   │         │   (Pool)   │         │   (Pro)   │ │
│   └────────────┘         └────────────┘         └───────────┘ │
│         │                      │                       │       │
│         └──────────────────────┴───────────────────────┘       │
│                                 │                               │
│                    ┌────────────▼────────────┐                  │
│                    │    SharedScanStore     │                  │
│                    │      (DB-backed)       │                  │
│                    └────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Components

| Component | Model | Role |
|-----------|-------|------|
| **Planner** | Gemini Flash | Fast, methodology-driven work unit generation |
| **Workers** | None (stateless) | Execute security tools in Docker containers |
| **Analyst** | Gemini Pro | Deep vulnerability analysis and hypothesis generation |

### Data Flow

1. **Planner** reads scan state → emits WorkUnits to SharedScanStore
2. **Workers** claim WorkUnits → execute in Docker → write results to SharedScanStore
3. **Analyst** reads completed results → produces findings/notes/directives → writes to SharedScanStore
4. **Planner** reads Analyst directives → generates new WorkUnits
5. Repeat until scan complete or max duration reached

### SharedScanStore

The shared database store serves as the sole IPC mechanism:

- **WorkUnits**: Queued tasks for Workers to execute
- **Findings**: Confirmed vulnerabilities with severity and evidence
- **Hypotheses**: Follow-up targets generated from observations
- **Directives**: Strategic instructions from Analyst to Planner
- **ScanEvents**: Append-only audit log for all state changes
- **Observations**: Extracted facts from tool output
- **Capabilities**: Derived asset properties (auth_surface, admin_surface, etc.)

## Scan Phases

The pipeline follows a methodology-driven approach:

```
RECON → ENUMERATION → VULN_SCAN → EXPLOITATION
```

### Triggers

Rules activate based on:
- `ALWAYS` - Run immediately when phase begins
- `HOST_DISCOVERED` - New host/subdomain found
- `HOST_LIVE_HTTP` - HTTP service confirmed live
- `TECH_DETECTED` - Specific technology fingerprint
- `ANALYST_HINT` - Analyst issued attack_hint directive

## State Persistence

PostgreSQL serves as the source of truth:
- **Resumability**: Scans can be stopped and resumed
- **Audit Trail**: Every action committed to ScanEvents table
- **Atomic Dedup**: WorkUnits deduplicated via `IntegrityError` handling

## Tech Stack

- **Application**: Python 3.10+, asyncio
- **Database**: PostgreSQL / SQLite via SQLModel
- **LLM**: Google Gemini (Flash for Planner, Pro for Analyst)
- **Tools**: Docker sandboxed execution (nmap, nuclei, sqlmap, ffuf, etc.)
- **Interface**: Textual TUI + CoreInterface for programmatic access

## Code Organization

```
kodiak/
├── api/
│   └── events.py           # TUI event system
├── core/
│   ├── analyst.py          # Analyst agent (deep thinking)
│   ├── config.py           # Settings management
│   ├── failure_policy.py   # Error handling policies
│   ├── interface.py        # Frontend-agnostic API
│   ├── kernel_result.py    # Runtime result type
│   ├── methodology.py      # Pentesting playbook rules
│   ├── multi_agent_orchestrator.py  # Pipeline orchestration
│   ├── planner.py          # Planner agent (fast planning)
│   ├── reporting.py        # Report generation
│   ├── scan_runner.py      # Scan execution wrapper
│   ├── shared_store.py     # DB-backed state store
│   └── worker.py           # Stateless tool executor
├── database/
│   ├── crud.py            # Database operations
│   ├── engine.py          # SQLModel engine setup
│   └── models.py          # SQLModel entity definitions
├── services/
│   ├── executor.py        # Docker command execution
│   ├── gemini_client.py   # Gemini API client
│   └── llm.py             # LLM utilities
├── tui/                    # Terminal user interface
└── skills/                 # Dynamic skill loading (planned)
```

## Concurrency Control

### Tool Serialization

Heavy tools are serialized to prevent duplicate scans:

```python
_HEAVY_TOOLS = frozenset({
    "nuclei", "ffuf", "katana", "gau", "sqlmap",
    "nmap", "commix", "wpscan", "hydra", "nikto",
})
```

Workers check active locks before claiming WorkUnits. Same-scope heavy tools are never run concurrently.

### Semaphore Limits

- `global_tool_concurrency`: Max parallel tool executions (default: 6)
- `heavy_tool_parallel_limit`: Max parallel heavy tools (default: 2)

## Error Handling

### Component Health

Components track their health state:
- **Healthy**: Normal operation
- **Degraded**: Recoverable failure, continues with warning
- **Paused**: Circuit breaker triggered, awaiting recovery

### Circuit Breaker

If a component fails N consecutive cycles (configurable via `failure_threshold`), it is paused:
- Emits `COMPONENT_PAUSED` event
- Stops generating work until timeout or manual resume
- Prevents cascade failures from repeatedly failing components

## Security Architecture

### Sandboxed Tool Execution

All security tools run in isolated Docker containers:
- Network isolation (controlled access)
- Resource limits (CPU, memory)
- Filesystem isolation (temporary workspaces)
- Safety controls (approval workflows for destructive tools)

## Integration Points

### CoreInterface API

Frontend-agnostic interface for scan orchestration:

```python
interface = CoreInterface()
run_id = await interface.start_scan(target="https://example.com")
async for event in interface.subscribe_events(run_id):
    print(event)
result = await interface.get_scan_result(run_id)
```

### Event Types

- `scan_started`, `scan_completed`, `scan_failed`
- `tool_start`, `tool_complete`
- `finding_discovered`, `finding_saved`
- `agent_thinking`, `agent_thought`
- `phase_advanced`

## Performance Considerations

### Async Operations

- Non-blocking UI during scans
- Background processing for long operations
- Progress indicators for user awareness
- Cancellation support via asyncio.Task

### Resource Management

- Connection pooling for database
- Memory management for large scans
- Tool timeout enforcement
- Cleanup of completed work units

## Development

### Testing

- Unit tests for individual components
- Integration tests for agent coordination
- Mock store for deterministic testing

### Configuration

All settings via environment variables or `.env`:
- `KODIAK_LLM_MODEL`: Gemini model selection
- `KODIAK_MULTI_AGENT_WORKERS`: Worker pool size
- `KODIAK_GLOBAL_CONCURRENCY`: Tool execution limit
- `KODIAK_TOOL_TIMEOUT`: Default tool timeout

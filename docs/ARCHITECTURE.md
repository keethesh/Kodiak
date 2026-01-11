# Kodiak Architecture

## Philosophy
Kodiak is designed to be **persistent, structured, and synchronized**. Unlike traditional monolithic and ephemeral tools, Kodiak focuses on robust state management and coordinated execution to prevent infinite loops and lost context.

## Core Concepts

### 1. The "Hive Mind" (Command Synchronization)
Kodiak solves the "thundering herd" problem of multiple agents running duplicates scans.
- **Global Lock Registry**: Before running `nmap` or `nuclei`, agents check the DB.
- **Output Streaming**: If Agent A is running a scan, Agent B attaches to Agent A's output stream instead of spawning a new process.
- **Result Caching**: Heavy scan results are cached in PostgreSQL.

### 2. State Persistence
We use **PostgreSQL** as the source of truth.
- **Resumability**: You can kill the `uvicorn` server at any time. On restart, the Orchestrator rehydrates the state machine and resumes agents from their last valid checkpoint.
- **Audit Trail**: Every tool output, thought process, and finding is committed to the DB.

### 3. The Graph (LangGraph-style)
Agents do not run in an infinite `while True` loop. They follow a strict State Machine:
`Recon` -> `Enumeration` -> `Vulnerability Assessment` -> `Exploitation` -> `Reporting`

Transitions are guarded by "Gates" (e.g., "Has open ports?" -> Yes -> Enum).

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, SQLModel (SQLAlchemy), LiteLLM
- **Database**: PostgreSQL (pgvector support planned for embeddings)
- **Frontend**: Next.js 14, React, TailwindCSS, WebSocket
- **Engine**: Docker (for sandboxed tool execution)

## Data Flow
1. User initiates Scan via Frontend.
2. Backend creates `ScanJob`.
3. `Orchestrator` spawns `ReconAgent`.
4. `ReconAgent` requests `nmap` tool.
5. `ToolServer` checks Hive Mind -> runs `nmap` in Docker.
6. Output piped to DB + WebSocket.
7. `EnumerationAgent` triggered by `nmap` completion event.

# What Kodiak Can Learn from Strix and Shannon

## Deep Comparative Analysis

---

## Executive Summary

Kodiak is a capable AI pentester with a smart single-brain Manager-Worker architecture, bounded state management, and Docker-based tool execution. But compared to the more mature Strix and Shannon, it has significant gaps in **multi-provider LLM support**, **authenticated scanning**, **white-box analysis**, **scan resume**, **multi-agent specialization**, **memory management**, **vulnerability deduplication**, **audit trails**, and **prompt templating**. Below is the full breakdown.

---

## 1. ARCHITECTURE COMPARISON

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Agent Model** | Single-brain Manager + stateless Workers | Multi-agent with dynamic subagent spawning | Structured 5-phase pipeline with parallel agents |
| **LLM Providers** | Gemini only | OpenAI, Anthropic, Google, Bedrock, Azure, Ollama (via litellm) | Anthropic Claude (+ router for OpenAI/Gemini) |
| **Execution** | Docker containers | Docker sandbox + FastAPI tool server | Temporal.io workflow engine |
| **State** | Bounded ScanState in-memory | AgentState (Pydantic) + agents graph | Temporal workflow state + git checkpoints |
| **UI** | Textual TUI | TUI + CLI with streaming renderers | CLI with Temporal Web UI |
| **Language** | Python | Python | TypeScript |

### What Kodiak Should Learn:

**A. Multi-Provider LLM Support (from Strix)**
Strix uses litellm as a universal LLM adapter, letting it switch between OpenAI, Anthropic, Google, Azure, Bedrock, and local models with zero code changes. Kodiak is locked to Gemini. Adding litellm (or a similar abstraction) would:
- Allow users to choose their preferred/cheapest provider
- Enable model-specific optimizations (Claude for code analysis, Gemini for reasoning, GPT for general tasks)
- Reduce vendor lock-in risk

**B. Workflow Orchestration (from Shannon)**
Shannon's Temporal.io integration provides:
- **Fault-tolerant execution**: Workflow state survives worker crashes
- **Deterministic replay**: Failed workflows resume exactly where they left off
- **Built-in retry policies**: Per-activity configurable retries with exponential backoff
- **Queryable progress**: Non-blocking state queries for monitoring

Kodiak's event-driven scheduler is good but lacks crash recovery and deterministic replay. Even without adopting Temporal, Kodiak could implement checkpoint serialization for resume capability.

**C. Specialized Agent Spawning (from both)**
Both Strix and Shannon spawn specialized agents per vulnerability type. Strix dynamically creates subagents with 1-5 focused skills. Shannon runs 5 parallel vulnerability agents (injection, XSS, auth, SSRF, authz) each with specialized prompts. Kodiak's single-brain approach is token-efficient but misses the depth that specialization provides.

---

## 2. SKILLS & KNOWLEDGE

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Format** | YAML files | Markdown files | Embedded in prompt templates |
| **Count** | ~10 skills | 26+ skills | 13 specialized agent prompts |
| **Depth** | Medium (techniques, payloads, examples) | Deep (190-210 lines each, DB-specific, bypass techniques, Pro Tips) | Deep (methodology, evidence hierarchy, classification) |
| **Dynamic Loading** | Yes (skill_loader.py) | Yes (Jinja2 + max 5 per agent) | No (static per agent) |
| **Categories** | vulnerabilities, frameworks, technologies | vulnerabilities, frameworks, technologies, protocols, scan_modes, coordination | Per vulnerability type (injection, XSS, auth, SSRF, authz) |

### What Kodiak Should Learn:

**A. Richer Skill Content (from Strix)**
Strix's skills are significantly deeper. Compare SQL injection:
- **Kodiak**: Lists techniques and example payloads
- **Strix**: Includes DB-specific primitives (MySQL `LOAD_FILE()`, PostgreSQL `pg_read_file()`, MSSQL `xp_cmdshell`), advanced bypass techniques (whitespace substitution, keyword splitting, CTE tricks), oracle selection methodology, extraction channels, metadata pivots, false positive guidance, and Pro Tips

Kodiak should expand each skill with:
- Database/framework-specific attack primitives
- Bypass technique catalogs (WAF evasion, filter bypass)
- False positive identification guidance
- Methodology flowcharts (when to use which technique)
- Validation requirements (how to confirm exploitation)

**B. Framework & Technology Skills (from Strix)**
Strix has deep guides for FastAPI, Next.js, Firebase, Supabase, and GraphQL. These go beyond generic vulnerability testing into framework-specific attack surfaces (e.g., Pydantic type coercion in FastAPI, Firestore rules gaps, Next.js middleware bypass). Kodiak should add similar framework-specific skills.

**C. Scan Mode Skills (from Strix)**
Strix has scan mode skills (quick, standard, deep) that adjust agent behavior based on time/thoroughness requirements. Kodiak has phases but no configurable depth modes.

---

## 3. PROMPTS

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Templating** | Inline Python string building | Jinja2 templates (431 lines) | Text files with `@include()` + variable interpolation |
| **Per-Agent Prompts** | Single system prompt for Manager | Per-agent directory with system_prompt.jinja | 13 separate prompt files |
| **Shared Components** | None | Dynamic tool/skill injection via Jinja2 | `prompts/shared/` (login instructions, target, rules, scope) |
| **Variable Injection** | Hardcoded in Python | `{{ get_tools_prompt() }}`, `{{ get_skill() }}` | `{{WEB_URL}}`, `{{MCP_SERVER}}`, `{{LOGIN_INSTRUCTIONS}}` |
| **Prompt Caching** | None | Anthropic cache control | Via Claude SDK |

### What Kodiak Should Learn:

**A. Externalized Prompt Templates (from both)**
Kodiak builds its entire system prompt inline in `manager.py` (~160 lines of Python string concatenation). Both Strix and Shannon externalize prompts into separate files. Benefits:
- Easier to iterate on prompts without touching Python code
- Version control for prompt changes
- Non-engineers can edit prompts
- A/B testing different prompt strategies

**Recommendation**: Move prompt sections to Jinja2 templates (like Strix) or text files with `@include()` (like Shannon).

**B. Shared Prompt Components (from Shannon)**
Shannon has a `prompts/shared/` directory with reusable components:
- `login-instructions.txt` — Dynamic authentication flow templates
- `_target.txt` — Target URL injection
- `_rules.txt` — Custom avoid/focus rules
- `_vuln-scope.txt` — Scope boundaries

This prevents prompt duplication and ensures consistency across agents.

**C. Prompt Caching (from Strix)**
Strix implements Anthropic's cache control for system prompts, reducing cost by ~90% on repeated scans. If Kodiak adds multi-provider support, it should implement prompt caching for providers that support it (Anthropic, Google).

---

## 4. AUTHENTICATION & AUTHENTICATED SCANNING

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Auth Support** | ❌ None | ✅ Via browser + proxy | ✅ Rich config-driven |
| **Login Types** | — | Manual browser login | Form, SSO, API, Basic |
| **2FA/TOTP** | — | — | ✅ TOTP secret in config |
| **Session Management** | — | Browser cookies persist | Playwright sessions |
| **Credential Config** | — | Environment-based | YAML config with schema validation |

### What Kodiak Should Learn:

**A. Config-Driven Authentication (from Shannon)**
Shannon's YAML config supports:
```yaml
authentication:
  login_type: form|sso|api|basic
  login_url: "https://app.example.com/login"
  credentials:
    username: "test@example.com"
    password: "password123"
    totp_secret: "JBSWY3DPEHPK3PXP"  # Optional 2FA
  login_flow:
    - "Type $username into email field"
    - "Type $password into password field"
    - "Click Sign In button"
  success_condition:
    type: url_contains
    value: "/dashboard"
```

This is a critical gap for Kodiak — most real-world targets require authentication. Without it, Kodiak can only test public-facing surfaces.

**B. Login Flow Instructions Injected into Prompts (from Shannon)**
Shannon dynamically builds login instructions from config and injects them into agent prompts. The LLM then follows the flow using Playwright. Kodiak could adopt this pattern with its existing Playwright integration.

---

## 5. WHITE-BOX ANALYSIS

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Source Code Analysis** | ❌ None | ⚠️ File edit tool (remediation) | ✅ Deep code analysis + Task tool |
| **Testing Modes** | Black-box only | Black-box, White-box, Combined | White-box + Black-box hybrid |
| **Code-Informed Attacks** | — | White-box mode reads code | AI uses code insights to target attacks |

### What Kodiak Should Learn:

**A. White-Box + Black-Box Hybrid (from Shannon)**
Shannon's most powerful feature is combining source code analysis with dynamic exploitation. The pre-recon agent reads source code, traces data flows, and identifies sink functions. This knowledge is then used by exploitation agents to craft targeted attacks.

For Kodiak, this could mean:
- Adding a "code analysis" phase before RECON when source is available
- Using LLM to identify dangerous patterns (eval, exec, SQL string concat, etc.)
- Feeding code insights into the Manager's system prompt for informed attacks

---

## 6. MEMORY & CONTEXT MANAGEMENT

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Strategy** | Bounded ScanState (~2K tokens) | Token-aware memory compression (100K limit) | Claude SDK context (per-agent) |
| **History Preservation** | Compact serialization, drops old data | LLM summarization of old messages | Per-phase deliverables |
| **Cross-Scan Memory** | ✅ Prior findings/notes injected | — | Git-based workspace + deliverable files |

### What Kodiak Should Learn:

**A. LLM-Powered Memory Compression (from Strix)**
Strix's `MemoryCompressor` is sophisticated:
- Monitors token count (100K limit, 90% threshold)
- Keeps 15+ recent messages intact
- Summarizes older messages in chunks of 10 using LLM
- Preserves critical security context (vulnerabilities, credentials, failed attempts)
- Limits images to 3 most recent

Kodiak's bounded ScanState is efficient but loses details. A hybrid approach — bounded state PLUS LLM-compressed conversation history — would give deeper context without blowing token budgets.

---

## 7. VULNERABILITY DEDUPLICATION

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Approach** | Basic in reporting | ✅ LLM-based with confidence scoring | Implicit (structured pipeline) |
| **Criteria** | Simple matching | Same root cause + component + exploit method + fix | Per-type analysis prevents overlap |
| **Output** | Duplicate count in report | XML with confidence score + reason | — |

### What Kodiak Should Learn:

**A. LLM-Based Deduplication (from Strix)**
Strix uses a dedicated LLM call for deduplication with nuanced rules:
- **SAME** = same root cause + same component + same exploit method + same fix
- **NOT duplicate** even if same vuln type at different endpoints/parameters
- **ARE duplicates** even if different wording, detail levels, or PoC payloads
- Returns confidence score (0-1) and explanation

Kodiak should implement similar LLM-based dedup before reporting, replacing simple string matching.

---

## 8. AUDIT, LOGGING & REPORTING

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Audit Trail** | Basic DB logging | Live streaming UI | ✅ Comprehensive per-agent JSONL + workflow log |
| **Prompt Snapshots** | ❌ | ❌ | ✅ Saved in audit-logs/prompts/ |
| **Metrics** | Token counts + cost | Per-request stats | ✅ Per-agent + per-phase + aggregate |
| **Reporting** | JSON + basic Markdown | ✅ CVSS, PoC, remediation, CVE/CWE | ✅ Structured deliverables per phase |
| **Resume Attempts** | ❌ | ❌ | ✅ Tracked in session.json |

### What Kodiak Should Learn:

**A. Comprehensive Audit Session (from Shannon)**
Shannon's audit system is production-grade:
```
audit-logs/{hostname}_{sessionId}/
├── session.json              # Aggregate metrics, status, resume history
├── agents/                   # Per-agent JSONL event logs
│   ├── pre-recon.jsonl
│   └── ...
├── prompts/                  # Exact prompts used (reproducibility)
└── deliverables/             # Phase outputs
```

Kodiak should adopt:
- Per-iteration JSONL logging (not just DB records)
- Prompt snapshots for debugging/reproducibility
- Phase-level metrics aggregation
- Resume attempt tracking

**B. Richer Reports (from both)**
Strix produces reports with:
- CVSS scoring per finding
- CVE/CWE references
- Remediation steps
- PoC code inclusion
- Multi-target correlation

Shannon produces structured deliverables per phase with evidence hierarchy (Level 1-4).

Kodiak's reports should add CVSS scores, CWE references, remediation guidance, and attack chain documentation.

---

## 9. ERROR HANDLING & RESILIENCE

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Error Classification** | ✅ Error hierarchy with severity | Retry on HTTP 429/5xx | ✅ Typed PentestError with ErrorCode enum |
| **Retry Strategy** | Tool-specific failure policies | Exponential backoff (5 retries) | ✅ Temporal retry (50-100 attempts, 5min-6hr) |
| **Billing Detection** | ❌ | ❌ | ✅ Multi-layer spending cap detection |
| **Scan Resume** | ❌ (PAUSED status defined but not implemented) | ❌ | ✅ Full workspace resume |
| **Graceful Degradation** | ✅ Timeout backoff reduces tool params | ✅ Max iteration warnings | ✅ Skip empty queues, continue on agent failure |

### What Kodiak Should Learn:

**A. Spending Cap Detection (from Shannon)**
Shannon detects billing limits through:
1. SDK error classification (`billing_error` type)
2. Text pattern matching ("spending cap", "usage limit", etc.)
3. Behavioral heuristic (cost=$0, turns≤2)

Then retries with long backoff (5min-30min default, 5min-6hr for subscription). This is critical for production use.

**B. Scan Resume/Checkpoint (from Shannon)**
Shannon's resume system:
- Git checkpoint before each agent execution
- On failure: rollback to clean state
- On resume: skip completed agents, restart from failure point
- Cross-references deliverable files to validate completion

Kodiak defines `PAUSED` status but never implements pause/resume. It should:
- Serialize ScanState to DB at each iteration
- Allow resume from any iteration checkpoint
- Skip completed phases on resume

**C. Typed Error Codes (from Shannon)**
Shannon's `ErrorCode` enum provides reliable error classification:
```typescript
enum ErrorCode {
  SPENDING_CAP_REACHED,    // → retry with long backoff
  CONFIG_NOT_FOUND,        // → fail immediately
  API_RATE_LIMITED,         // → retry with short backoff
  GIT_CHECKPOINT_FAILED,   // → fail immediately
  OUTPUT_VALIDATION_FAILED, // → retry (agent may succeed)
}
```

Kodiak has error severity but could benefit from error codes that drive specific recovery strategies.

---

## 10. CONFIGURATION & RULES

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Config Format** | .env + env vars | .env + JSON | ✅ YAML with JSON schema validation |
| **Schema Validation** | Pydantic Settings | Static class | ✅ AJV schema validation |
| **Scope Rules** | ❌ | ❌ | ✅ avoid/focus rules (path, subdomain, domain, method) |
| **Scan Modes** | Phases (hardcoded) | quick/standard/deep (skill-based) | Configurable pipeline parallelism |

### What Kodiak Should Learn:

**A. Scope Rules (from Shannon)**
Shannon allows users to define avoid/focus rules:
```yaml
rules:
  avoid:
    - description: "Don't touch production DB"
      type: path
      url_path: "/admin/db"
  focus:
    - description: "Focus on API v2"
      type: path
      url_path: "/api/v2"
```

These are injected into prompts as `{{RULES_AVOID}}` and `{{RULES_FOCUS}}`. Kodiak should support similar scope control to prevent unintended testing of sensitive endpoints.

**B. Scan Mode Configuration (from Strix)**
Strix has quick/standard/deep scan modes that adjust agent behavior. Kodiak could add configurable depth levels that control:
- Number of iterations
- Tool thoroughness
- Payload breadth
- Time budgets

---

## 11. BROWSER & TOOL INTEGRATION

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **Browser** | Playwright (headless, disconnected from scan loop) | ✅ Playwright as first-class tool (click, type, JS execution, form fuzzing) | ✅ 5 isolated Playwright instances via MCP |
| **Proxy** | ✅ HTTP/HTTPS proxy with interception | ✅ Caido-based full interception + replay | ❌ |
| **Python REPL** | write_file action (scripts) | ✅ IPython sessions for exploit dev | ❌ |
| **Web Search** | ❌ | ✅ Perplexity API integration | ❌ |

### What Kodiak Should Learn:

**A. Browser as First-Class Scan Tool (from Strix)**
Strix's browser tool supports: launch, goto, click, type, execute_js, get_console_logs, screenshot, and more — all callable by the LLM during scanning. Kodiak has Playwright but it's not integrated into the scan loop as a tool the Manager can invoke.

**B. Web Search for Payload Research (from Strix)**
Strix integrates Perplexity API for real-time payload research. When the LLM encounters an unfamiliar technology or needs specific bypass techniques, it can search the web. This is valuable for zero-day research and uncommon tech stacks.

---

## 12. PROOF-OF-CONCEPT VALIDATION

| Dimension | Kodiak | Strix | Shannon |
|-----------|--------|-------|---------|
| **PoC Requirement** | Prompt says "PoC attempt before REPORTING" | ✅ Mandatory validation agents | ✅ "No Exploit, No Report" policy |
| **Evidence Hierarchy** | ❌ | Confidence scoring | ✅ Level 1-4 (weakness → full takeover) |
| **Classification** | Finding severity (info/low/medium/high/critical) | Deduplicated with confidence | ✅ EXPLOITED / POTENTIAL / FALSE POSITIVE |

### What Kodiak Should Learn:

**A. Structured Exploitation Gating (from Shannon)**
Shannon's queue validation system ensures exploitation only runs when analysis found real vulnerabilities:
1. Vulnerability analysis agent outputs `{type}_exploitation_queue.json`
2. Queue validation checks: file exists, valid JSON, has vulnerabilities
3. Exploitation agent only runs if `shouldExploit: true`
4. Evidence classified as EXPLOITED, POTENTIAL, or FALSE POSITIVE

**B. Evidence Hierarchy (from Shannon)**
Shannon classifies exploitation evidence in levels:
- Level 1: Weakness identified
- Level 2: Vulnerability confirmed
- Level 3: Successful exploitation
- Level 4: Full account takeover / data exfiltration demonstrated

Kodiak should adopt similar classification to distinguish between theoretical vulnerabilities and proven exploits.

---

---

## 13. ARCHITECTURAL PATTERNS

### 13a. Multi-Agent Spawning vs Single-Brain (Strix → Kodiak)

**Strix's Pattern**: The root `StrixAgent` dynamically spawns specialized subagents at runtime. Each subagent:
- Runs in its own **thread** (`threading.Thread`, daemon=True)
- Gets an isolated `AgentState` with `parent_id` linking to parent
- Inherits conversation context from parent via `inherited_messages`
- Has its own LLM instance with 1-5 focused skills
- Is tracked in an **agents graph** (nodes + edges) for visualization

```python
# Strix: agents_graph_actions.py
thread = threading.Thread(
    target=_run_agent_in_thread,
    args=(agent, state, inherited_messages),
    daemon=True,
    name=f"Agent-{name}-{state.agent_id}",
)
thread.start()
_running_agents[state.agent_id] = thread
```

**Kodiak's Pattern**: Single Manager LLM makes ALL decisions. Workers are stateless command executors.

**What Kodiak could adopt**: A hybrid approach — keep the single Manager brain for strategic decisions, but allow it to spawn **specialist sub-managers** for deep-dive on specific vulnerability types. The Manager would hand off a subset of context + a focused skill set, and the sub-manager would run a smaller loop targeting (e.g.) only SQLi on a specific endpoint. Results flow back to the parent Manager.

### 13b. Structured Pipeline with Conditional Gating (Shannon → Kodiak)

**Shannon's Pattern**: A rigid 5-phase pipeline where exploitation is *gated* by queue validation:

```
Pre-Recon → Recon → [5 parallel vuln agents] → [conditional exploit per vuln type] → Report
```

Each vuln agent outputs a `{type}_exploitation_queue.json`. The queue validator checks:
1. File exists and is valid JSON
2. Has a `vulnerabilities` array with entries
3. Only then spawns the corresponding exploit agent

```typescript
// Shannon: queue-validation.ts
if (decision.shouldExploit && !shouldSkip(exploitAgentName)) {
  exploitMetrics = await runExploitAgent();
}
```

**Kodiak's current approach**: The Manager decides what to do next based on scan state — no formal gating.

**What Kodiak could adopt**: Formalize phase transitions with **gate conditions**. Before advancing from VULN_SCAN to EXPLOITATION, validate that findings exist and have sufficient evidence. This prevents wasted iterations where the Manager attempts exploitation without solid leads.

### 13c. Tool Server Architecture (Strix → Kodiak)

**Strix's Pattern**: Tools execute inside Docker via a **FastAPI tool server**:
- Container runs `sleep infinity` + a FastAPI server listening on a dynamic port
- Bearer token authentication per container (`secrets.token_urlsafe(32)`)
- Per-agent task tracking — cancels stale requests before submitting new ones
- Health check polling before declaring container ready
- Tools dispatch via HTTP POST to `{server_url}/execute`

```python
# Strix: tool_server.py
@app.post("/execute", response_model=ToolExecutionResponse)
async def execute_tool(request: ToolExecutionRequest, credentials = security_dependency):
    verify_token(credentials)
    task = asyncio.create_task(asyncio.wait_for(_run_tool(...), timeout=REQUEST_TIMEOUT))
```

**Kodiak's Pattern**: Creates a new container per command (`docker run --rm`), no persistent server.

**What Kodiak could adopt**: A persistent tool server per scan would dramatically reduce container startup overhead. Instead of launching a new Docker container per command (250-500ms startup), keep a long-lived container with a tool server. Multiple commands execute as HTTP requests against the same container. This is especially beneficial for rapid iteration (e.g., spraying payloads).

### 13d. Agent Self-Management Tools (Strix → Kodiak)

**Strix's Pattern**: Agents have **todo** and **notes** tools for self-organization:

```python
# Strix: todo_actions.py — per-agent isolated storage
_todos_storage: dict[str, dict[str, dict[str, Any]]] = {}  # agent_id → todos

@register_tool(sandbox_execution=False)
def create_todo(agent_state, title, ...):
    agent_todos = _get_agent_todos(agent_state.agent_id)
    todo = {"title": ..., "priority": ..., "status": "pending", ...}
    agent_todos[todo_id] = todo
```

The LLM can create, update, and query its own task list during scanning. This provides structured self-planning.

**Kodiak's Pattern**: The Manager tracks its plan in `analysis` text (free-form). No structured self-planning.

**What Kodiak could adopt**: Add todo/notes as structured fields in `KodiakResponse`. The Manager would output planned tasks, mark them done as tools complete, and the system could surface "stalled" tasks that haven't progressed.

### 13e. Result Type Pattern (Shannon → Kodiak)

**Shannon's Pattern**: Functional error handling via discriminated union:

```typescript
type Result<T, E> = { ok: true, value: T } | { ok: false, error: E };

// Usage in agent-execution.ts
const result = await execute(agentName, input);
if (isErr(result)) {
  throw result.error;  // Typed error propagation
}
const value = result.value;  // Type-narrowed success
```

**Kodiak's Pattern**: Try/except with custom exception hierarchy.

**What Kodiak could adopt**: Python equivalent using `Result` type (e.g., `result` library or simple dataclass). This makes error paths explicit in function signatures and prevents silent exception swallowing.

### 13f. Concurrency Safety (Shannon → Kodiak)

**Shannon's Pattern**: `SessionMutex` — Promise-based FIFO lock per session:

```typescript
// concurrency.ts
class SessionMutex {
  private locks: Map<string, Promise<void>> = new Map();
  async lock(sessionId: string): Promise<UnlockFunction> {
    if (this.locks.has(sessionId)) await this.locks.get(sessionId);
    let resolve: () => void;
    const promise = new Promise<void>((r) => (resolve = r));
    this.locks.set(sessionId, promise);
    return () => { this.locks.delete(sessionId); resolve!(); };
  }
}
```

Used for atomic session.json writes during parallel agent execution.

**Kodiak's Pattern**: Uses `asyncio.Semaphore` for task concurrency but no per-resource locks for database writes.

**What Kodiak could adopt**: Per-scan or per-resource async locks to prevent race conditions when parallel workers update shared state (findings, scan status, etc.).

### 13g. Git-Based Checkpoint & Rollback (Shannon → Kodiak)

**Shannon's Pattern**: Every agent execution is bracketed by git operations:
1. **Before**: `git add -A && git commit -m "Checkpoint: {agent} (attempt N)"`
2. **On retry**: `git reset --hard HEAD && git clean -fd` (clean slate)
3. **On success**: Changes committed as proof
4. **On resume**: `git checkout {checkpoint_hash}` to restore exact state

A `GitSemaphore` serializes all git operations to prevent `index.lock` conflicts.

**Kodiak could adopt**: For white-box scanning or when modifying target repos, git checkpoints provide deterministic rollback. Even for pure black-box scanning, checkpointing scan state to a git-like system would enable true resume.

### 13h. MCP Server Integration (Shannon → Kodiak)

**Shannon's Pattern**: Custom MCP (Model Context Protocol) servers extend the Claude SDK:
- `shannon-helper` server: `save_deliverable` + `generate_totp` tools
- `playwright-agentN`: 5 isolated Playwright browser instances
- MCP servers are assigned per-agent via `MCP_AGENT_MAPPING`

```typescript
// claude-executor.ts
const mcpServers = {
  'shannon-helper': createShannonHelperServer(sourceDir),
  'playwright-agent1': { type: 'stdio', command: 'npx', args: ['@playwright/mcp@latest', '--isolated'] },
};
const result = await query({ prompt, options: { mcpServers, maxTurns: 10_000 } });
```

**Kodiak's Pattern**: Tools are shell commands in Docker. No MCP.

**What Kodiak could adopt**: If Kodiak ever supports non-Gemini providers (especially Anthropic), MCP servers would be a clean way to expose tools. Even without MCP, the *pattern* of isolated tool servers per agent is valuable.

### 13i. Streaming Architecture (Strix → Kodiak)

**Strix's Pattern**: Real-time streaming with tool-call detection:

```python
# llm.py — streaming loop
async for chunk in response:
    delta = self._get_chunk_content(chunk)
    accumulated += delta
    if "</function>" in accumulated:
        # Stop streaming, parse tool call immediately
        yield LLMResponse(content=accumulated)
        done_streaming = 1
        continue
    yield LLMResponse(content=accumulated)
```

The TUI renders partial responses in real-time, so users see the agent's thinking as it streams.

**Kodiak's Pattern**: Waits for complete LLM response, then processes.

**What Kodiak could adopt**: Streaming LLM responses would improve TUI responsiveness. Users could see the Manager's analysis forming in real-time rather than waiting for the full response.

### 13j. Docker Image Strategy (Shannon → Kodiak)

**Shannon's Pattern**: Multi-stage Chainguard Wolfi build:
- **Builder stage**: Installs Go, gcc, pip, Ruby → compiles subfinder, WhatWeb, schemathesis
- **Runtime stage**: Minimal base with only runtime dependencies + compiled binaries
- Non-root user (`pentest:pentest`)
- Chromium pre-installed for Playwright
- Git pre-configured for agent use

**Kodiak's Pattern**: Single Dockerfile based on Kali with all tools.

**What Kodiak could adopt**: Multi-stage builds reduce image size and attack surface. Separate build-time dependencies (compilers, package managers) from runtime. Use a security-focused base image.

---

## 14. ADDITIONAL NON-OBVIOUS LESSONS

### 14a. Telemetry & Observability (Strix → Kodiak)
Strix's `Tracer` tracks:
- Agent lifecycle (creation → completion, with timing)
- Every tool execution (start → end, with args & results)
- Vulnerability reports (discovery → dedup → final)
- Saves structured JSON to `strix_runs/` for post-hoc analysis

Kodiak has event emission but no structured post-scan telemetry export. Adding a tracer would enable scan quality analysis over time.

### 14b. Agent-Scoped Storage Isolation (Strix → Kodiak)
Strix isolates todo/notes storage by `agent_id`:
```python
_todos_storage: dict[str, dict[str, dict[str, Any]]] = {}  # agent_id → todos
```
This prevents cross-agent contamination in multi-agent setups. Even in Kodiak's single-manager model, separating per-scan storage (vs global) would improve multi-scan safety.

### 14c. Memory Compression Strategy (Strix → Kodiak)
Strix's compressor is nuanced:
- 100K token budget with 90% threshold trigger
- Keeps 15+ most recent messages intact
- Summarizes older messages in chunks of 10 via LLM
- **Preserves security-critical context**: vulnerabilities, credentials, failed attempts, architecture insights
- Limits images to 3 most recent

Kodiak's bounded ScanState drops detail aggressively (20 hosts, 20 ports). A hybrid: ScanState for structured data + compressed conversation for nuanced context.

### 14d. Prompt Caching Economics (Strix → Kodiak)
Strix uses Anthropic's `cache_control` on system prompts. For a 4K token system prompt repeated 50 times in a scan:
- Without caching: 50 × 4K × $3/1M = $0.60
- With caching: 1 × 4K × $3/1M + 49 × 4K × $0.30/1M = $0.07
- **~88% savings** on input tokens

If Kodiak adds multi-provider support, prompt caching should be a day-1 feature.

### 14e. Exploitation Queue Pattern (Shannon → Kodiak)
Shannon separates *analysis* from *exploitation* with a queue file:
```json
// injection_exploitation_queue.json
{ "vulnerabilities": [
    { "id": "VULN-001", "type": "sql_injection", "endpoint": "/api/users", "parameter": "id", "confidence": "HIGH" }
] }
```
The exploit agent reads this queue and systematically works through it. Kodiak's Manager decides ad-hoc what to exploit — no formal queue ensures coverage.

### 14f. Per-Phase Deliverables (Shannon → Kodiak)
Shannon produces a structured markdown deliverable per phase:
- `code_analysis_deliverable.md` — Source code insights
- `recon_deliverable.md` — Attack surface map with 6 sections
- `{type}_analysis_deliverable.md` — Vulnerability analysis
- `{type}_exploitation_evidence.md` — PoC evidence
- `comprehensive_security_assessment_report.md` — Final report

Each phase builds on previous deliverables. This creates a paper trail and ensures nothing is lost between phases.

Kodiak outputs a single final report. Adding per-phase deliverables would:
- Provide intermediate visibility
- Enable phase-specific review
- Create audit-quality documentation

### 14g. Login Flow Templates (Shannon → Kodiak)
Shannon's prompt manager builds login instructions dynamically:
```typescript
// Sections: COMMON, AUTH_TYPE (FORM/SSO), VERIFICATION
// Variables: $username, $password, $totp
// Result: Full login flow steps injected into agent prompt
```
This is the most practical authenticated scanning implementation — the LLM follows natural language instructions using the browser tool.

### 14h. Scope Boundary Injection (Shannon → Kodiak)
Shannon injects avoid/focus rules directly into prompts:
```yaml
rules:
  avoid:
    - description: "Don't touch admin panel"
      type: path
      url_path: "/admin"
  focus:
    - description: "Focus on API v2"
      type: path
      url_path: "/api/v2"
```
These become `{{RULES_AVOID}}` and `{{RULES_FOCUS}}` in the prompt template. Kodiak has no scope control — the Manager decides what to test based on its own judgment.

---

## PRIORITY RANKING: What to Implement First

| # | Feature | Effort | Impact | Source |
|---|---------|--------|--------|--------|
| 1 | **Externalize prompts to Jinja2 templates** | Medium | High | Both |
| 2 | **Multi-LLM provider support (litellm)** | Medium | High | Strix |
| 3 | **Authenticated scanning config** | Medium | Critical | Shannon |
| 4 | **Scan resume/checkpoint** | Medium | High | Shannon |
| 5 | **Persistent tool server (not container-per-command)** | Medium | High | Strix |
| 6 | **Richer skills (DB-specific, bypass catalogs)** | Low | High | Strix |
| 7 | **Scope rules (avoid/focus)** | Low | Medium | Shannon |
| 8 | **LLM-based vuln deduplication** | Low | Medium | Strix |
| 9 | **Browser as first-class scan tool** | Medium | High | Strix |
| 10 | **Exploitation queue pattern** | Low | Medium | Shannon |
| 11 | **Comprehensive audit trail + telemetry** | Medium | Medium | Both |
| 12 | **Evidence hierarchy & PoC classification** | Low | Medium | Shannon |
| 13 | **LLM streaming responses** | Medium | Medium | Strix |
| 14 | **Memory compression (hybrid)** | Medium | Medium | Strix |
| 15 | **CVSS/CWE in reports + per-phase deliverables** | Low | Medium | Both |
| 16 | **Spending cap detection** | Low | Medium | Shannon |
| 17 | **Phase gate conditions** | Low | Medium | Shannon |
| 18 | **Agent self-management (todo/notes tools)** | Low | Low | Strix |
| 19 | **Multi-stage Docker image** | Medium | Low | Shannon |
| 20 | **White-box code analysis** | High | High | Shannon |
| 21 | **Specialist sub-manager spawning** | High | High | Strix |
| 22 | **Scan depth modes** | Low | Low | Strix |
| 23 | **Web search for payloads** | Low | Low | Strix |

# Requirements Document

## Introduction

This feature establishes the minimal viable end-to-end scan execution flow for Kodiak. The goal is to fix critical blockers and create a working demonstration where a user can initiate a scan through the API, watch an agent execute tools, and see results persisted to the database with real-time updates.

## Glossary

- **Orchestrator**: The core scheduling system that manages agent tasks and execution
- **Agent**: An LLM-powered autonomous entity that executes security testing tasks
- **Scan_Job**: A database record representing a security assessment session
- **Task**: A specific directive assigned to an agent within a scan
- **Tool**: A security testing capability (e.g., nmap, web_search, terminal_execute)
- **WebSocket_Manager**: Real-time communication system for live updates

## Requirements

### Requirement 1: Orchestrator Lifecycle Management

**User Story:** As a system administrator, I want the orchestrator to start automatically when the application launches, so that scans can be processed without manual intervention.

#### Acceptance Criteria

1. WHEN the FastAPI application starts, THE Orchestrator SHALL initialize and begin its scheduler loop
2. WHEN the application shuts down, THE Orchestrator SHALL gracefully stop all running tasks
3. WHEN the orchestrator is running, THE System SHALL accept and process scan requests
4. THE Orchestrator SHALL maintain a registry of active workers and their status
5. WHEN a scan is stopped, THE Orchestrator SHALL cancel associated worker tasks

### Requirement 2: Scan Creation and Execution Flow

**User Story:** As a security tester, I want to create and start a scan through the API, so that I can initiate automated security testing.

#### Acceptance Criteria

1. WHEN a user creates a project via POST /api/v1/projects, THE System SHALL store the project in the database
2. WHEN a user creates a scan job via POST /api/v1/scans, THE System SHALL validate the configuration and store the scan
3. WHEN a user starts a scan via POST /api/v1/scans/{id}/start, THE System SHALL create a root task and update scan status to RUNNING
4. WHEN a scan is started, THE Orchestrator SHALL detect the pending task and spawn an agent worker
5. WHEN a scan is stopped via POST /api/v1/scans/{id}/stop, THE System SHALL cancel the worker and update scan status

### Requirement 3: Agent Task Execution

**User Story:** As an agent, I want to receive and execute tasks with proper tool access, so that I can perform security testing activities.

#### Acceptance Criteria

1. WHEN an agent is spawned for a task, THE Agent SHALL load the task directive and initialize with appropriate tools
2. WHEN an agent executes a tool, THE System SHALL validate the tool exists in the inventory
3. WHEN a tool execution completes, THE Agent SHALL process the result and decide on next actions
4. WHEN an agent completes its mission, THE System SHALL mark the task as completed
5. WHEN an agent encounters an error, THE System SHALL log the error and mark the task as failed

### Requirement 4: Basic Tool Execution

**User Story:** As an agent, I want to execute basic reconnaissance tools, so that I can gather information about targets.

#### Acceptance Criteria

1. WHEN an agent calls terminal_execute, THE System SHALL execute the command and return structured output
2. WHEN an agent calls web_search, THE System SHALL perform a web search and return relevant results
3. WHEN a tool execution fails, THE System SHALL return an error message with details
4. WHEN a tool executes successfully, THE System SHALL return structured data including success status and output
5. THE System SHALL prevent infinite loops by tracking tool execution attempts

### Requirement 5: Database Persistence

**User Story:** As a system, I want to persist scan results and agent activities, so that findings can be reviewed and analyzed.

#### Acceptance Criteria

1. WHEN an agent discovers an asset, THE System SHALL create a Node record in the database
2. WHEN an agent identifies a vulnerability, THE System SHALL create a Finding record linked to the relevant node
3. WHEN an agent executes a tool, THE System SHALL create an Attempt record to prevent duplication
4. WHEN an agent performs any action, THE System SHALL create an AgentLog record for audit trail
5. THE System SHALL maintain referential integrity between projects, scans, tasks, and findings

### Requirement 6: Real-time Progress Updates

**User Story:** As a user monitoring a scan, I want to see real-time progress updates, so that I can track the scan's status and results.

#### Acceptance Criteria

1. WHEN a scan starts, THE System SHALL broadcast a scan_started event via WebSocket
2. WHEN an agent executes a tool, THE System SHALL broadcast tool_execution_start and tool_execution_complete events
3. WHEN an agent discovers a finding, THE System SHALL broadcast a finding_discovered event
4. WHEN a scan completes or fails, THE System SHALL broadcast a scan_completed or scan_failed event
5. THE WebSocket_Manager SHALL maintain connections and deliver events to subscribed clients

### Requirement 7: Error Handling and Recovery

**User Story:** As a system operator, I want robust error handling during scan execution, so that failures are graceful and debuggable.

#### Acceptance Criteria

1. WHEN an LLM API call fails, THE Agent SHALL retry with exponential backoff up to 3 attempts
2. WHEN a tool execution times out, THE System SHALL terminate the process and return a timeout error
3. WHEN database operations fail, THE System SHALL log the error and continue with degraded functionality
4. WHEN an agent crashes, THE Orchestrator SHALL mark the task as failed and clean up resources
5. THE System SHALL provide detailed error messages and stack traces for debugging

### Requirement 8: Configuration Validation

**User Story:** As a system administrator, I want the system to validate configuration on startup, so that missing API keys or settings are detected early.

#### Acceptance Criteria

1. WHEN the application starts, THE System SHALL validate that an LLM provider is configured
2. WHEN the application starts, THE System SHALL verify database connectivity
3. WHEN an LLM API key is missing, THE System SHALL provide clear error messages with setup instructions
4. WHEN configuration is invalid, THE System SHALL prevent startup and display helpful guidance
5. THE System SHALL log successful configuration validation on startup
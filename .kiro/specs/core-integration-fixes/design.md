# Design Document

## Overview

This design addresses the critical integration failures in Kodiak by fixing the broken connections between tools, agents, database operations, and event broadcasting. The focus is on making the existing architecture actually work rather than adding new features.

## Architecture

The core integration follows this flow:
1. **Agent** receives task from **Orchestrator**
2. **Agent** calls **Tool** through **Tool_Inventory**
3. **Tool** executes command and emits events via **Event_Manager**
4. **Tool** returns results to **Agent**
5. **Agent** persists results via **CRUD** operations to **Node** models
6. **Hive_Mind** deduplicates commands and shares results across agents

## Components and Interfaces

### Event Manager
```python
# kodiak/api/events.py
class EventManager:
    def __init__(self, websocket_manager: WebSocketManager):
        self.websocket_manager = websocket_manager
    
    async def emit_tool_start(self, tool_name: str, target: str, agent_id: str):
        """Broadcast tool execution start event"""
    
    async def emit_tool_progress(self, tool_name: str, progress: dict):
        """Broadcast tool execution progress"""
    
    async def emit_tool_complete(self, tool_name: str, result: ToolResult):
        """Broadcast tool execution completion"""
```

### Tool Base Class Updates
```python
# kodiak/core/tools/base.py
class BaseTool:
    def __init__(self, event_manager: EventManager):
        self.event_manager = event_manager
    
    async def execute(self, **kwargs) -> ToolResult:
        """Public interface - handles events and calls _execute"""
        await self.event_manager.emit_tool_start(self.name, kwargs.get('target'), kwargs.get('agent_id'))
        try:
            result = await self._execute(**kwargs)
            await self.event_manager.emit_tool_complete(self.name, result)
            return result
        except Exception as e:
            error_result = ToolResult(success=False, error=str(e))
            await self.event_manager.emit_tool_complete(self.name, error_result)
            return error_result
    
    async def _execute(self, **kwargs) -> ToolResult:
        """Override this in concrete tools"""
        raise NotImplementedError
```

### CRUD Layer Fixes
```python
# kodiak/database/crud.py
# Replace all Asset references with Node
async def create_node(db: AsyncSession, node_data: dict) -> Node:
    """Create a new node (asset) in the database"""

async def get_nodes_by_project(db: AsyncSession, project_id: int) -> List[Node]:
    """Get all nodes for a project"""

async def update_node(db: AsyncSession, node_id: int, updates: dict) -> Node:
    """Update an existing node"""
```

### Agent Tool Integration
```python
# kodiak/core/agent.py
class Agent:
    def __init__(self, tool_inventory: ToolInventory, event_manager: EventManager):
        self.tool_inventory = tool_inventory
        self.event_manager = event_manager
        # Use actual tool names from inventory
        self.available_tools = [tool.name for tool in tool_inventory.get_all_tools()]
    
    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute tool with proper error handling"""
        tool = self.tool_inventory.get_tool(tool_name)
        if not tool:
            return ToolResult(success=False, error=f"Tool {tool_name} not found")
        
        return await tool.execute(agent_id=self.id, **kwargs)
```

### Configuration Consolidation
```python
# kodiak/core/config.py (keep this one, remove old settings.py)
class KodiakConfig(BaseSettings):
    # Database settings
    database_url: str = "postgresql+asyncpg://kodiak:kodiak@localhost/kodiak_db"
    
    # LLM settings
    llm_provider: str = "gemini"
    llm_model: str = "gemini/gemini-1.5-pro"
    llm_temperature: float = 0.1
    
    # Application settings
    debug: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_prefix = "KODIAK_"
        env_file = ".env"

# Single global config instance
config = KodiakConfig()
```

## Data Models

The existing Node model is correct - we just need to fix CRUD operations to use it consistently:

```python
# kodiak/database/models.py (already exists, just reference)
class Node(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id")
    node_type: str  # "ip", "domain", "service", "vulnerability"
    value: str      # The actual IP, domain name, etc.
    metadata: Optional[dict] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Tool execution returns structured results
*For any* registered tool and valid parameters, executing the tool should return a ToolResult object with success status and either data or error information.
**Validates: Requirements 1.1**

### Property 2: Event broadcasting completeness
*For any* tool execution, the Event_Manager should broadcast start, progress, and completion events in the correct sequence to all connected WebSocket clients.
**Validates: Requirements 1.2, 4.1**

### Property 3: Error handling consistency
*For any* tool execution that fails, the system should return a ToolResult with success=False and a descriptive error message without crashing.
**Validates: Requirements 1.3, 2.3**

### Property 4: Tool registration validation
*For any* tool registration attempt, only tools with complete _execute method implementations should be successfully registered in the Tool_Inventory.
**Validates: Requirements 1.4**

### Property 5: Command deduplication
*For any* identical tool execution requests from multiple agents, the Hive_Mind should execute the command only once and share results with all requesting agents.
**Validates: Requirements 1.5**

### Property 6: Database model consistency
*For any* CRUD operation involving assets, the system should use Node models consistently without referencing the deprecated Asset model.
**Validates: Requirements 2.1**

### Property 7: Asset discovery persistence
*For any* asset discovered by an agent, the system should create a Node record with proper foreign key relationships to the project.
**Validates: Requirements 2.2**

### Property 8: Database query correctness
*For any* Node query operation, the system should return current data that matches what was previously stored.
**Validates: Requirements 2.5**

### Property 9: Tool availability consistency
*For any* agent in the system, it should have access to all tools registered in the Tool_Inventory.
**Validates: Requirements 3.1**

### Property 10: Tool naming consistency
*For any* tool in the system, its name should be consistent across the Tool_Inventory, Agent, and Orchestrator components.
**Validates: Requirements 3.2**

### Property 11: State synchronization
*For any* discovery made by one agent, other active agents should be able to access that shared state through the Hive_Mind.
**Validates: Requirements 3.3**

### Property 12: Tool validation before execution
*For any* tool execution attempt by an agent, the system should only allow execution of tools that exist in the Tool_Inventory.
**Validates: Requirements 3.4**

### Property 13: Configuration source consistency
*For any* configuration value, all system components should access it through the single Pydantic-based configuration interface.
**Validates: Requirements 3.5, 5.2**

### Property 14: WebSocket event delivery
*For any* connected WebSocket client, it should receive all tool execution events broadcast by the Event_Manager.
**Validates: Requirements 4.2**

### Property 15: Event content completeness
*For any* event broadcast, it should include all relevant context information (tool name, target, results) required for client understanding.
**Validates: Requirements 4.3**

### Property 16: System resilience to client disconnections
*For any* WebSocket client disconnection during tool execution, the tool should continue running normally without interruption.
**Validates: Requirements 4.4**

### Property 17: Multi-client broadcasting
*For any* event broadcast with multiple connected WebSocket clients, all active clients should receive the same event.
**Validates: Requirements 4.5**

### Property 18: Configuration validation error clarity
*For any* invalid configuration provided to the system, it should return clear, descriptive error messages indicating what is wrong.
**Validates: Requirements 5.3**

### Property 19: Environment variable override support
*For any* configuration setting, providing an environment variable with the KODIAK_ prefix should override the default value.
**Validates: Requirements 5.4**

### Property 20: Startup configuration validation
*For any* application startup attempt with missing required configuration, the system should fail with clear error messages before attempting to run.
**Validates: Requirements 5.5**

## Error Handling

### Tool Execution Errors
- Network timeouts: Return ToolResult with timeout error
- Command not found: Return ToolResult with installation guidance
- Permission denied: Return ToolResult with permission requirements
- Invalid parameters: Return ToolResult with parameter validation errors

### Database Errors
- Connection failures: Retry with exponential backoff, then fail gracefully
- Constraint violations: Return descriptive error about data conflicts
- Migration failures: Log detailed error and prevent startup

### Configuration Errors
- Missing required values: Fail fast with clear error messages
- Invalid formats: Provide examples of correct format
- Environment variable conflicts: Show which values are being used

### WebSocket Errors
- Client disconnections: Clean up resources, continue tool execution
- Broadcast failures: Log error, continue operation
- Connection limits: Reject new connections with clear message

## Testing Strategy

### Unit Tests
- Test each component in isolation with mocked dependencies
- Focus on error conditions and edge cases
- Verify configuration loading and validation
- Test database CRUD operations with test database

### Property-Based Tests
- Use pytest with Hypothesis for property-based testing
- Generate random tool parameters and verify consistent behavior
- Test event broadcasting with multiple simulated clients
- Verify Hive_Mind deduplication across various scenarios
- Each property test should run minimum 100 iterations
- Tag format: **Feature: core-integration-fixes, Property {number}: {property_text}**

### Integration Tests
- Test complete workflow from agent task assignment to result persistence
- Verify WebSocket event delivery end-to-end
- Test tool execution with real security tools in Docker containers
- Validate database schema supports complete workflows

### Testing Configuration
- Use pytest-asyncio for async test support
- Configure test database with SQLite for speed
- Mock external tool execution for unit tests
- Use real tools in integration tests with test targets
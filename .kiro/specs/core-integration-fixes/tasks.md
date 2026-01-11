# Implementation Plan: Core Integration Fixes

## Overview

This implementation plan systematically fixes the broken integration points in Kodiak by addressing missing components, model mismatches, and configuration conflicts. Each task builds incrementally to restore basic functionality.

## Tasks

- [x] 1. Create missing Event Manager
  - Create `kodiak/api/events.py` with EventManager class
  - Implement tool execution event broadcasting (start, progress, complete)
  - Integrate with existing WebSocketManager for client notifications
  - _Requirements: 1.2, 4.1, 4.2, 4.3_

- [x] 1.1 Write property test for event broadcasting
  - **Property 2: Event broadcasting completeness**
  - **Validates: Requirements 1.2, 4.1**

- [x] 2. Fix Tool base class integration
  - Update `kodiak/core/tools/base.py` to accept EventManager in constructor
  - Implement public `execute()` method that handles events and calls `_execute()`
  - Add proper error handling and event emission for failures
  - _Requirements: 1.1, 1.3_

- [x] 2.1 Write property test for tool execution

  - **Property 1: Tool execution returns structured results**
  - **Validates: Requirements 1.1**

- [x] 2.2 Write property test for error handling

  - **Property 3: Error handling consistency**
  - **Validates: Requirements 1.3**

- [x] 3. Implement concrete tool methods
  - Add `_execute()` implementations to all tools in `kodiak/core/tools/definitions/`
  - Start with network.py (nmap), terminal.py, and proxy.py as core tools
  - Ensure all tools return proper ToolResult objects
  - _Requirements: 1.1, 1.4_

- [x] 3.1 Write property test for tool registration validation
  - **Property 4: Tool registration validation**
  - **Validates: Requirements 1.4**

- [x] 4. Fix CRUD model references
  - Update all functions in `kodiak/database/crud.py` to use Node instead of Asset
  - Ensure proper foreign key relationships to Project model
  - Add error handling for database operation failures
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 4.1 Write property test for database model consistency
  - **Property 6: Database model consistency**
  - **Validates: Requirements 2.1**

- [x] 4.2 Write property test for asset discovery persistence
  - **Property 7: Asset discovery persistence**
  - **Validates: Requirements 2.2**

- [ ] 5. Checkpoint - Basic tool execution working
  - Ensure all tests pass, ask the user if questions arise.

- [-] 6. Update Agent tool integration
  - Modify `kodiak/core/agent.py` to use actual tool names from ToolInventory
  - Add EventManager dependency injection
  - Fix tool execution calls to use consistent naming
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 6.1 Write property test for tool availability
  - **Property 9: Tool availability consistency**
  - **Validates: Requirements 3.1**

- [ ]* 6.2 Write property test for tool naming consistency
  - **Property 10: Tool naming consistency**
  - **Validates: Requirements 3.2**

- [-] 7. Fix Orchestrator tool references
  - Update `kodiak/services/executor.py` to use correct tool names
  - Ensure orchestrator can assign tasks with valid tool references
  - Add validation that assigned tools exist in inventory
  - _Requirements: 3.1, 3.4_

- [ ]* 7.1 Write property test for tool validation
  - **Property 12: Tool validation before execution**
  - **Validates: Requirements 3.4**

- [x] 8. Consolidate configuration system
  - Remove old `settings.py` if it exists
  - Ensure all components import config from `kodiak/core/config.py`
  - Add environment variable validation and error messages
  - _Requirements: 3.5, 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 8.1 Write property test for configuration consistency
  - **Property 13: Configuration source consistency**
  - **Validates: Requirements 3.5, 5.2**

- [x] 8.2 Write property test for environment variable overrides
  - **Property 19: Environment variable override support**
  - **Validates: Requirements 5.4**

- [ ] 9. Integrate Hive Mind with tool execution
  - Update Hive Mind to work with new tool execution flow
  - Ensure command deduplication works with EventManager
  - Add state synchronization for agent discoveries
  - _Requirements: 1.5, 3.3_

- [ ] 9.1 Write property test for command deduplication
  - **Property 5: Command deduplication**
  - **Validates: Requirements 1.5**

- [ ]* 9.2 Write property test for state synchronization
  - **Property 11: State synchronization**
  - **Validates: Requirements 3.3**

- [-] 10. Wire EventManager into application startup
  - Update `main.py` to create EventManager instance
  - Inject EventManager into ToolInventory and Agent constructors
  - Ensure WebSocket endpoints have access to EventManager
  - _Requirements: 4.2, 4.4, 4.5_

- [ ]* 10.1 Write property test for WebSocket event delivery
  - **Property 14: WebSocket event delivery**
  - **Validates: Requirements 4.2**

- [ ]* 10.2 Write property test for multi-client broadcasting
  - **Property 17: Multi-client broadcasting**
  - **Validates: Requirements 4.5**

- [x] 11. Add comprehensive error handling
  - Implement graceful error handling for all integration points
  - Add descriptive error messages for common failure scenarios
  - Ensure system resilience to component failures
  - _Requirements: 2.3, 4.4, 5.3_

- [ ]* 11.1 Write property test for system resilience
  - **Property 16: System resilience to client disconnections**
  - **Validates: Requirements 4.4**

- [ ] 12. Final integration testing
  - Test complete workflow: Agent → Tool → EventManager → WebSocket → Database
  - Verify all components work together without crashes
  - Validate that basic security tool execution works end-to-end
  - _Requirements: 2.4_

- [ ]* 12.1 Write integration test for complete workflow
  - **Property 8: Database query correctness**
  - **Validates: Requirements 2.5**

- [ ] 13. Final checkpoint - All integration fixes complete
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Each task references specific requirements for traceability
- Focus on making existing architecture work rather than adding features
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration tests ensure components work together correctly
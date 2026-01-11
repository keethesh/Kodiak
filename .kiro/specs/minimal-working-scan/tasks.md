# Implementation Plan: Minimal Working Scan

## Overview

This implementation plan converts the minimal working scan design into discrete coding tasks that will establish the foundational end-to-end execution flow. The focus is on fixing critical blockers in the orchestrator lifecycle, agent task execution, and real-time progress reporting to achieve a working demonstration scan.

## Tasks

- [X] 1. Fix Orchestrator Lifecycle Management
  - Fix orchestrator startup in FastAPI lifespan to automatically start scheduler loop
  - Add missing stop_scan method to orchestrator class
  - Implement graceful shutdown with worker cleanup
  - _Requirements: 1.1, 1.2, 1.5_

- [ ]* 1.1 Write property test for orchestrator lifecycle
  - **Property 1: Orchestrator Lifecycle Management**
  - **Validates: Requirements 1.1, 1.2**

- [x] 2. Fix Task Directive Access and Processing
  - Fix task.directive field access in orchestrator (remove .properties)
  - Implement proper JSON parsing for task directives
  - Add validation for task directive format
  - _Requirements: 3.1_

- [ ]* 2.1 Write property test for task directive processing
  - **Property 3: Worker Spawning and Management**
  - **Validates: Requirements 2.4, 1.4**

- [x] 3. Implement Basic Tool Execution Framework
  - Ensure terminal_execute tool works with proper command execution
  - Implement web_search tool with basic search functionality
  - Add tool result validation and structured error handling
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ]* 3.1 Write property test for tool execution reliability
  - **Property 4: Tool Execution Reliability**
  - **Validates: Requirements 4.1, 4.2, 4.4**

- [ ]* 3.2 Write property test for tool validation and error handling
  - **Property 5: Tool Validation and Error Handling**
  - **Validates: Requirements 3.2, 4.3**

- [x] 4. Fix Database Models and Persistence
  - Ensure all database tables are created on startup
  - Fix Task model directive field (ensure it's a direct field, not in properties)
  - Implement proper database session handling in agent execution
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ]* 4.1 Write property test for database persistence consistency
  - **Property 6: Database Persistence Consistency**
  - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5**

- [x] 5. Implement Scan Creation and Execution Flow
  - Fix scan creation API to properly store scan configuration
  - Implement start_scan endpoint to create root task and trigger orchestrator
  - Add stop_scan endpoint to cancel workers and update scan status
  - _Requirements: 2.1, 2.2, 2.3, 2.5_

- [ ]* 5.1 Write property test for scan state transitions
  - **Property 2: Scan State Transitions**
  - **Validates: Requirements 2.1, 2.2, 2.3**

- [x] 6. Implement Agent Task Execution Loop
  - Fix agent initialization with proper tool inventory access
  - Implement agent think-act loop with LLM integration
  - Add proper error handling and task completion logic
  - _Requirements: 3.1, 3.4, 3.5_

- [ ]* 6.1 Write property test for task completion and cleanup
  - **Property 8: Task Completion and Cleanup**
  - **Validates: Requirements 3.4, 3.5, 2.5, 1.5**

- [x] 7. Implement Real-time WebSocket Events
  - Fix WebSocket event broadcasting for scan lifecycle events
  - Add tool execution start/complete event emission
  - Implement finding discovery event broadcasting
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ]* 7.1 Write property test for real-time event broadcasting
  - **Property 7: Real-time Event Broadcasting**
  - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.5**

- [x] 8. Implement Attempt Tracking and Deduplication
  - Add attempt record creation during tool execution
  - Implement deduplication logic to prevent infinite loops
  - Add attempt history querying for agent context
  - _Requirements: 4.5_

- [ ]* 8.1 Write property test for attempt deduplication
  - **Property 11: Attempt Deduplication**
  - **Validates: Requirements 4.5**

- [x] 9. Add Comprehensive Error Handling
  - Implement LLM API retry logic with exponential backoff
  - Add tool execution timeout handling
  - Implement database error recovery and graceful degradation
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 9.1 Write property test for system resilience under failure
  - **Property 9: System Resilience Under Failure**
  - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5**

- [x] 10. Implement Configuration Validation
  - Add startup configuration validation for LLM provider
  - Implement database connectivity verification
  - Add helpful error messages for missing configuration
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ]* 10.1 Write property test for configuration validation
  - **Property 10: Configuration Validation**
  - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5**

- [ ] 11. Create End-to-End Integration Test
  - Implement complete scan flow test (create project → create scan → start scan → verify results)
  - Add WebSocket event verification in integration test
  - Test with real LLM provider (if configured) or mock responses
  - _Requirements: All requirements integration_

- [ ] 12. Checkpoint - Verify Complete Scan Flow
  - Test complete end-to-end scan execution
  - Verify all WebSocket events are broadcast correctly
  - Ensure database persistence works for all models
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Focus on getting the basic flow working before adding comprehensive testing
- Property tests validate universal correctness properties
- Integration test validates the complete end-to-end flow
- The checkpoint ensures all components work together correctly
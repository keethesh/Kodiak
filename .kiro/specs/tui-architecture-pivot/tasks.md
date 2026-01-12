# Implementation Plan: TUI Architecture Pivot

## Overview

This implementation plan transforms Kodiak from a frontend-backend architecture to a unified TUI application. The work is organized into phases: cleanup, restructuring, TUI framework setup, view implementation, and documentation updates.

## Tasks

- [x] 1. Create feature branch and initial setup
  - Create `feature/tui-architecture` branch from main
  - Add `textual` dependency to `backend/pyproject.toml`
  - Verify Textual installation works
  - _Requirements: 2.1_

- [x] 2. Project structure reorganization
  - [x] 2.1 Move backend code to root
    - Move `backend/kodiak/` to root `kodiak/`
    - Move `backend/pyproject.toml` to root
    - Move `backend/poetry.lock` to root
    - Update all import paths in moved files
    - _Requirements: 17.1, 17.2, 17.3, 17.4_
  
  - [x] 2.2 Create TUI directory structure
    - Create `kodiak/tui/` directory
    - Create `kodiak/tui/views/` directory
    - Create `kodiak/tui/widgets/` directory
    - Create `kodiak/tui/__init__.py` files
    - _Requirements: 17.5, 17.6, 17.7, 17.8_
  
  - [x] 2.3 Update entry points
    - Create `kodiak/__main__.py` for `python -m kodiak`
    - Create `kodiak/cli.py` for CLI commands
    - Update `pyproject.toml` with `[tool.poetry.scripts]` entry
    - _Requirements: 2.2, 17.9_

- [x] 3. Architecture cleanup - Remove frontend artifacts
  - [x] 3.1 Remove frontend directory
    - Delete entire `frontend/` directory
    - _Requirements: 1.1_
  
  - [x] 3.2 Remove FastAPI API layer
    - Delete `kodiak/api/endpoints/` directory
    - Delete `kodiak/api/api.py`
    - Keep `kodiak/api/events.py` (will be adapted for TUI)
    - _Requirements: 1.2_
  
  - [x] 3.3 Remove WebSocket code
    - Delete `kodiak/api/ws.py`
    - Delete `kodiak/services/websocket_manager.py`
    - _Requirements: 1.3_
  
  - [x] 3.4 Remove FastAPI main entry point
    - Delete `main.py` (FastAPI app)
    - _Requirements: 1.6_
  
  - [x] 3.5 Clean up configuration
    - Remove CORS configuration from `kodiak/core/config.py`
    - Remove `BACKEND_CORS_ORIGINS` setting
    - Add TUI-specific settings (color_theme, refresh_rate)
    - _Requirements: 1.4, 15.3, 15.4_

- [x] 4. Update Docker configuration
  - [x] 4.1 Simplify docker-compose.yml
    - Remove frontend service definition
    - Update backend service to run TUI (or remove if TUI runs locally)
    - Keep only db and kodiak services
    - _Requirements: 1.5, 14.3_
  
  - [x] 4.2 Update backend Dockerfile
    - Remove FastAPI/uvicorn references
    - Update CMD to run TUI or provide shell access
    - _Requirements: 14.2_

- [x] 5. Checkpoint - Verify cleanup
  - Ensure all tests pass after cleanup
  - Verify core imports work: `from kodiak.core import agent, orchestrator`
  - Verify database imports work: `from kodiak.database import models, crud`
  - Ask user if questions arise
  - _Requirements: 1.7_

- [x] 6. TUI Application Framework
  - [x] 6.1 Create main application class
    - Create `kodiak/tui/app.py` with `KodiakApp` class
    - Implement global key bindings (q, h, ?)
    - Implement screen stack navigation
    - Create base CSS styles in `kodiak/tui/styles.tcss`
    - _Requirements: 2.1, 2.6, 2.7, 12.1_
  
  - [x] 6.2 Create state management
    - Create `kodiak/tui/state.py` with `AppState` class
    - Implement reactive state for projects, agents, findings
    - _Requirements: 5.4, 6.4, 11.1_
  
  - [x] 6.3 Create event system
    - Create `kodiak/tui/events.py` with TUI event classes
    - Define `AgentStatusChanged`, `AssetDiscovered`, `FindingCreated` messages
    - _Requirements: 11.2, 11.3, 11.4_
  
  - [x] 6.4 Create core bridge
    - Create `kodiak/tui/core_bridge.py`
    - Implement database initialization
    - Implement orchestrator integration
    - Implement event callback to TUI message conversion
    - _Requirements: 2.4, 2.5, 13.1_

  - [ ]* 6.5 Write property test for database integration
    - **Property 2: Database Operations Work Without HTTP**
    - **Validates: Requirements 2.4, 13.2, 13.3**

- [x] 7. Implement reusable widgets
  - [x] 7.1 Create StatusBar widget
    - Display app name, current context, scan status
    - Update dynamically based on state
    - _Requirements: 2.7, 5.10_
  
  - [x] 7.2 Create AgentPanel widget
    - Display list of agents with status icons
    - Support selection and navigation
    - Implement status icon mapping (🟢, 🟡, 🔴, ⏸)
    - _Requirements: 6.1, 6.2, 6.3, 6.6_
  
  - [ ]* 7.3 Write property test for agent status mapping
    - **Property 6: Agent Status Visual Mapping**
    - **Validates: Requirements 6.2**
  
  - [x] 7.4 Create GraphTree widget
    - Render attack surface as tree with icons
    - Support expand/collapse
    - Support navigation and selection
    - Implement node type icon mapping
    - _Requirements: 8.1, 8.2, 8.7_
  
  - [ ]* 7.5 Write property test for graph node icons
    - **Property 9: Graph Node Icon Mapping**
    - **Validates: Requirements 8.2**
  
  - [x] 7.6 Create ActivityLog widget
    - Scrolling log display
    - Auto-scroll on new entries
    - Timestamp formatting
    - _Requirements: 5.3_
  
  - [x] 7.7 Create FindingsList widget
    - Group findings by severity
    - Display summary counts
    - Support filtering
    - Color-code by severity
    - _Requirements: 9.1, 9.2, 9.3, 9.6_
  
  - [ ]* 7.8 Write property test for findings grouping
    - **Property 11: Findings Grouped By Severity**
    - **Validates: Requirements 9.1, 9.2**
  
  - [x] 7.9 Create ChatHistory widget
    - Display messages with timestamps and sender
    - Support scrolling
    - _Requirements: 7.1, 7.2_

- [x] 8. Checkpoint - Verify widgets
  - Ensure all widget tests pass
  - Verify widgets render correctly in isolation
  - Ask user if questions arise

- [-] 9. Implement views
  - [x] 9.1 Create HomeScreen view
    - Display project list using DataTable
    - Show recent activity
    - Implement keyboard shortcuts (n, d, r, Enter)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  
  - [ ]* 9.2 Write property test for project display
    - **Property 3: Project List Displays All Required Fields**
    - **Validates: Requirements 3.2**
  
  - [x] 9.3 Create NewScanScreen view
    - Input fields for name, target, instructions
    - Agent count selector (1-5)
    - Validation logic
    - Submit and cancel handling
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
  
  - [ ]* 9.4 Write property test for target validation
    - **Property 5: Target Validation Rejects Invalid Inputs**
    - **Validates: Requirements 4.6, 4.7**
  
  - [x] 9.5 Create MissionControlScreen view
    - Split layout: agents panel, graph, activity log
    - Tab navigation between panels
    - Keyboard shortcuts (g, f, p)
    - Real-time updates from agents
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10_
  
  - [ ]* 9.6 Write property test for event propagation
    - **Property 7: Event Propagation Updates UI**
    - **Validates: Requirements 5.4, 6.4, 8.8, 9.7, 11.2, 11.3, 11.4**
  
  - [x] 9.7 Create AgentChatScreen view
    - Chat history display
    - Message input field
    - Agent switching (left/right arrows)
    - Agent status in header
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_
  
  - [ ]* 9.8 Write property test for chat messages
    - **Property 8: Chat Message Round-Trip**
    - **Validates: Requirements 7.1, 7.2, 7.4, 7.5**
  
  - [x] 9.9 Create GraphScreen view (expanded)
    - Full-screen tree view
    - Search functionality
    - Navigation to finding details
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8_
  
  - [ ]* 9.10 Write property test for severity colors
    - **Property 10: Severity Color Coding**
    - **Validates: Requirements 8.3**
  
  - [x] 9.11 Create FindingsScreen view
    - Findings list with grouping
    - Export functionality
    - Navigation to details
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
  
  - [x] 9.12 Create FindingDetailScreen view
    - Display all finding fields
    - Copy PoC functionality
    - Re-test trigger
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  
  - [ ]* 9.13 Write property test for finding details
    - **Property 12: Finding Detail Contains All Fields**
    - **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

- [x] 10. Checkpoint - Verify views
  - Ensure all view tests pass
  - Test navigation flow between views
  - Ask user if questions arise

- [x] 11. Implement keyboard navigation
  - [x] 11.1 Global shortcuts
    - Implement 'q' to quit
    - Implement 'h' to go home
    - Implement '?' to show help overlay
    - _Requirements: 12.1, 12.7_
  
  - [x] 11.2 View-specific shortcuts
    - Implement Tab for panel cycling
    - Implement arrow keys for navigation
    - Implement Enter for selection
    - Implement Escape for back
    - _Requirements: 12.2, 12.3, 12.4, 12.5_
  
  - [x] 11.3 Footer shortcut display
    - Display available shortcuts in footer
    - Update footer based on current view
    - _Requirements: 12.6_
  
  - [ ]* 11.4 Write property test for keyboard bindings
    - **Property 13: Keyboard Bindings Registered**
    - **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5**

- [x] 12. Implement CLI commands
  - [x] 12.1 Create kodiak init command
    - Initialize database schema
    - Create tables if not exist
    - _Requirements: 14.5_
  
  - [x] 12.2 Create kodiak config command
    - Interactive LLM configuration
    - Save to .env file
    - _Requirements: 14.6, 15.5_
  
  - [ ]* 12.3 Write property test for configuration loading
    - **Property 14: Configuration Loading**
    - **Validates: Requirements 15.1, 15.2**

- [x] 13. Error handling implementation
  - [x] 13.1 Database error handling
    - Graceful connection failure handling
    - User-friendly error messages
    - Clean exit on fatal errors
    - _Requirements: 13.4, 13.5_
  
  - [ ]* 13.2 Write property test for database error handling
    - **Property 2: Database Operations Work Without HTTP** (error cases)
    - **Validates: Requirements 13.4**
  
  - [x] 13.3 Async non-blocking verification
    - Ensure UI remains responsive during operations
    - Implement loading indicators
    - _Requirements: 11.5, 11.6_
  
  - [ ]* 13.4 Write property test for non-blocking UI
    - **Property 15: Non-Blocking UI**
    - **Validates: Requirements 2.3, 11.5**

- [x] 14. Checkpoint - Full integration test
  - Run complete user flow: create project → start scan → view findings
  - Verify all keyboard shortcuts work
  - Test error handling scenarios
  - Ask user if questions arise

- [x] 15. Documentation updates
  - [x] 15.1 Update README.md
    - New installation instructions
    - TUI usage guide
    - Screenshot/demo
    - _Requirements: 16.2_
  
  - [x] 15.2 Update docs/DEPLOYMENT.md
    - Remove frontend deployment
    - Add TUI deployment instructions
    - Update Docker instructions
    - _Requirements: 16.1_
  
  - [x] 15.3 Update steering documents
    - Update `.kiro/steering/tech.md` - remove Next.js, add Textual
    - Update `.kiro/steering/structure.md` - new project structure
    - Update `.kiro/steering/product.md` - TUI description
    - Update `.kiro/steering/implementation.md` - TUI status
    - _Requirements: 16.3, 16.4, 16.5, 16.6_
  
  - [x] 15.4 Add TUI documentation
    - Create keyboard shortcuts reference
    - Create view navigation guide
    - _Requirements: 16.8_
  
  - [x] 15.5 Archive frontend documentation
    - Move or delete frontend-specific docs
    - _Requirements: 16.7_

- [x] 16. Final checkpoint
  - All tests pass
  - Documentation complete
  - Ready for merge to main
  - Ask user for final review

## Notes

- Tasks marked with `*` are optional property-based tests that can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases

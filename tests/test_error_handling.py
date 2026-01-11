"""
Property-based tests for error handling consistency.

Feature: core-integration-fixes, Property 3: Error handling consistency
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from kodiak.core.tools.base import BaseTool, ToolResult
from kodiak.api.events import EventManager


class NetworkErrorTool(BaseTool):
    """Mock tool that simulates network errors."""
    
    @property
    def name(self) -> str:
        return "network_error_tool"
    
    @property
    def description(self) -> str:
        return "A tool that simulates network errors"
    
    async def _execute(self, **kwargs) -> ToolResult:
        """Simulate network timeout."""
        raise ConnectionError("Connection timeout after 30 seconds")


class ValidationErrorTool(BaseTool):
    """Mock tool that simulates validation errors."""
    
    @property
    def name(self) -> str:
        return "validation_error_tool"
    
    @property
    def description(self) -> str:
        return "A tool that simulates validation errors"
    
    async def _execute(self, **kwargs) -> ToolResult:
        """Simulate validation error."""
        raise ValueError("Invalid target format: expected IP address")


class PermissionErrorTool(BaseTool):
    """Mock tool that simulates permission errors."""
    
    @property
    def name(self) -> str:
        return "permission_error_tool"
    
    @property
    def description(self) -> str:
        return "A tool that simulates permission errors"
    
    async def _execute(self, **kwargs) -> ToolResult:
        """Simulate permission error."""
        raise PermissionError("Access denied: requires root privileges")


class GenericErrorTool(BaseTool):
    """Mock tool that raises generic exceptions."""
    
    def __init__(self, event_manager=None, error_message="Generic error"):
        super().__init__(event_manager)
        self.error_message = error_message
    
    @property
    def name(self) -> str:
        return "generic_error_tool"
    
    @property
    def description(self) -> str:
        return "A tool that raises generic exceptions"
    
    async def _execute(self, **kwargs) -> ToolResult:
        """Raise a generic exception."""
        raise Exception(self.error_message)


class TestErrorHandlingProperties:
    """Property-based tests for error handling consistency."""

    def create_test_fixtures(self):
        """Create test fixtures for each test run."""
        # Mock WebSocket manager
        mock_websocket_manager = MagicMock()
        mock_websocket_manager.send_tool_update = AsyncMock()
        mock_websocket_manager.send_agent_update = AsyncMock()
        mock_websocket_manager.send_finding_update = AsyncMock()
        
        # Event manager
        event_manager = EventManager(mock_websocket_manager)
        
        return event_manager, mock_websocket_manager

    @pytest.mark.asyncio
    async def test_error_handling_consistency_network_errors(self):
        """
        Property 3: Error handling consistency for network errors
        For any tool execution that fails with network errors, the system should return 
        a ToolResult with success=False and a descriptive error message without crashing.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Create tool that raises network errors
        tool = NetworkErrorTool(event_manager)
        
        # Test data
        kwargs = {
            'target': '192.168.1.1',
            'agent_id': 'agent_001',
            'scan_id': 'scan_123'
        }
        
        # Execute tool (should not crash)
        result = await tool.execute(**kwargs)
        
        # Verify error handling
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert result.output == ""
        assert result.error == "Connection timeout after 30 seconds"
        assert result.data == {}
        
        # Verify error events were emitted
        assert mock_websocket_manager.send_tool_update.call_count == 2  # start and complete (with error)
        
        # Check that the completion event indicates failure
        calls = mock_websocket_manager.send_tool_update.call_args_list
        complete_call = calls[1]
        assert complete_call[1]['status'] == 'failed'

    @pytest.mark.asyncio
    async def test_error_handling_consistency_validation_errors(self):
        """
        Property 3: Error handling consistency for validation errors
        For any tool execution that fails with validation errors, the system should 
        return a ToolResult with success=False and descriptive error without crashing.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Create tool that raises validation errors
        tool = ValidationErrorTool(event_manager)
        
        # Test data
        kwargs = {
            'target': 'invalid_target',
            'agent_id': 'agent_002',
            'scan_id': 'scan_456'
        }
        
        # Execute tool (should not crash)
        result = await tool.execute(**kwargs)
        
        # Verify error handling
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert result.output == ""
        assert result.error == "Invalid target format: expected IP address"
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_error_handling_consistency_permission_errors(self):
        """
        Property 3: Error handling consistency for permission errors
        For any tool execution that fails with permission errors, the system should 
        return a ToolResult with success=False and descriptive error without crashing.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Create tool that raises permission errors
        tool = PermissionErrorTool(event_manager)
        
        # Test data
        kwargs = {
            'target': 'secure.example.com',
            'agent_id': 'agent_003',
            'scan_id': 'scan_789'
        }
        
        # Execute tool (should not crash)
        result = await tool.execute(**kwargs)
        
        # Verify error handling
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert result.output == ""
        assert result.error == "Access denied: requires root privileges"
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_error_handling_consistency_without_event_manager(self):
        """
        Property 3: Error handling consistency without EventManager
        For any tool execution that fails without EventManager, the system should 
        still return a ToolResult with error information without crashing.
        
        **Validates: Requirements 1.3, 2.3**
        """
        # Create tool without event manager
        tool = GenericErrorTool(event_manager=None, error_message="No event manager error")
        
        # Test data
        kwargs = {
            'target': 'test.com',
            'agent_id': 'agent_004'
        }
        
        # Execute tool (should not crash)
        result = await tool.execute(**kwargs)
        
        # Verify error handling
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert result.output == ""
        assert result.error == "No event manager error"
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_error_handling_consistency_multiple_error_types(self):
        """
        Property 3: Error handling consistency across multiple error types
        For any tool execution that fails with different error types, the system 
        should consistently return ToolResult with error information.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Test different error types
        error_tools = [
            (NetworkErrorTool(event_manager), "Connection timeout after 30 seconds"),
            (ValidationErrorTool(event_manager), "Invalid target format: expected IP address"),
            (PermissionErrorTool(event_manager), "Access denied: requires root privileges"),
            (GenericErrorTool(event_manager, "Custom error"), "Custom error")
        ]
        
        for i, (tool, expected_error) in enumerate(error_tools):
            kwargs = {
                'target': f'target_{i}',
                'agent_id': f'agent_{i}',
                'scan_id': f'scan_{i}'
            }
            
            # Execute tool (should not crash)
            result = await tool.execute(**kwargs)
            
            # Verify consistent error handling
            assert isinstance(result, ToolResult)
            assert result.success == False
            assert result.output == ""
            assert result.error == expected_error
            assert result.data == {}

    @pytest.mark.asyncio
    async def test_error_handling_preserves_context(self):
        """
        Property 3: Error handling preserves execution context
        For any tool execution that fails, the error should preserve context information
        like agent_id and scan_id for proper event broadcasting.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Create tool that raises errors
        tool = GenericErrorTool(event_manager, "Context preservation test")
        
        # Test data with specific context
        kwargs = {
            'target': 'context.test.com',
            'agent_id': 'context_agent',
            'scan_id': 'context_scan',
            'additional_param': 'test_value'
        }
        
        # Execute tool (should not crash)
        result = await tool.execute(**kwargs)
        
        # Verify error handling
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert result.error == "Context preservation test"
        
        # Verify events were emitted with correct context
        assert mock_websocket_manager.send_tool_update.call_count == 2
        assert mock_websocket_manager.send_agent_update.call_count == 1
        
        # Check that agent update was called with correct context
        agent_call = mock_websocket_manager.send_agent_update.call_args
        assert agent_call[1]['scan_id'] == 'context_scan'
        assert agent_call[1]['agent_id'] == 'context_agent'

    @pytest.mark.asyncio
    async def test_error_handling_concurrent_failures(self):
        """
        Property 3: Error handling consistency under concurrent failures
        For any concurrent tool executions that fail, each should return consistent
        error information without interfering with each other.
        
        **Validates: Requirements 1.3, 2.3**
        """
        event_manager, mock_websocket_manager = self.create_test_fixtures()
        
        # Create multiple tools with different errors
        tools_and_errors = [
            (GenericErrorTool(event_manager, f"Concurrent error {i}"), f"Concurrent error {i}")
            for i in range(5)
        ]
        
        # Execute all tools concurrently
        tasks = []
        for i, (tool, expected_error) in enumerate(tools_and_errors):
            kwargs = {
                'target': f'concurrent_{i}',
                'agent_id': f'agent_{i}',
                'scan_id': f'scan_{i}'
            }
            tasks.append(tool.execute(**kwargs))
        
        # Wait for all to complete
        results = await asyncio.gather(*tasks)
        
        # Verify all results have consistent error handling
        for i, (result, (tool, expected_error)) in enumerate(zip(results, tools_and_errors)):
            assert isinstance(result, ToolResult)
            assert result.success == False
            assert result.output == ""
            assert result.error == expected_error
            assert result.data == {}
        
        # Verify all events were emitted (2 per tool = 10 total)
        assert mock_websocket_manager.send_tool_update.call_count == 10
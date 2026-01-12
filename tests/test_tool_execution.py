"""
Property-based tests for tool execution functionality.

Feature: core-integration-fixes, Property 1: Tool execution returns structured results
"""

import pytest
import asyncio
from typing import Dict, Any
from unittest.mock import AsyncMock, MagicMock

from kodiak.core.tools.base import BaseTool, ToolResult
from kodiak.api.events import EventManager


class MockTool(BaseTool):
    """Mock tool for testing."""
    
    @property
    def name(self) -> str:
        return "mock_tool"
    
    @property
    def description(self) -> str:
        return "A mock tool for testing"
    
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        """Mock implementation that returns a ToolResult."""
        target = args.get('target', 'unknown')
        return ToolResult(
            success=True,
            output=f"Mock tool executed on {target}",
            data={"target": target, "args": args}
        )


class MockFailingTool(BaseTool):
    """Mock tool that always fails for testing."""
    
    @property
    def name(self) -> str:
        return "failing_tool"
    
    @property
    def description(self) -> str:
        return "A mock tool that always fails"
    
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        """Mock implementation that raises an exception."""
        raise Exception("Mock tool failure")


class MockDictTool(BaseTool):
    """Mock tool that returns a dict instead of ToolResult."""
    
    @property
    def name(self) -> str:
        return "dict_tool"
    
    @property
    def description(self) -> str:
        return "A mock tool that returns a dict"
    
    async def _execute(self, args: Dict[str, Any]) -> dict:
        """Mock implementation that returns a dict."""
        return {"output": "dict result", "data": args}


class TestToolExecutionProperties:
    """Property-based tests for tool execution."""

    def create_test_fixtures(self):
        """Create test fixtures for each test run."""
        # Mock TUI bridge
        mock_tui_bridge = MagicMock()
        mock_tui_bridge.send_tool_update = AsyncMock()
        mock_tui_bridge.send_agent_update = AsyncMock()
        mock_tui_bridge.send_finding_update = AsyncMock()
        
        # Event manager
        event_manager = EventManager(mock_tui_bridge)
        
        return event_manager, mock_tui_bridge

    @pytest.mark.asyncio
    async def test_tool_execution_returns_structured_results(self):
        """
        Property 1: Tool execution returns structured results
        For any registered tool and valid parameters, executing the tool should return 
        a ToolResult object with success status and either data or error information.
        
        **Validates: Requirements 1.1**
        """
        event_manager, mock_tui_bridge = self.create_test_fixtures()
        
        # Create tool with event manager
        tool = MockTool(event_manager)
        
        # Test data
        kwargs = {
            'target': '192.168.1.1',
            'agent_id': 'agent_001',
            'scan_id': 'scan_123'
        }
        
        # Execute tool
        result = await tool.execute(**kwargs)
        
        # Verify result structure
        assert isinstance(result, ToolResult)
        assert hasattr(result, 'success')
        assert hasattr(result, 'output')
        assert hasattr(result, 'data')
        assert hasattr(result, 'error')
        
        # Verify successful execution
        assert result.success == True
        assert result.output == "Mock tool executed on 192.168.1.1"
        assert result.data['target'] == '192.168.1.1'
        assert result.error is None
        
        # Verify events were emitted
        assert mock_tui_bridge.send_tool_update.call_count == 2  # start and complete
        assert mock_tui_bridge.send_agent_update.call_count == 1  # executing status

    @pytest.mark.asyncio
    async def test_tool_execution_without_event_manager(self):
        """
        Property 1 (No EventManager): Tool execution should work without EventManager
        For any tool without EventManager, executing should still return ToolResult.
        
        **Validates: Requirements 1.1**
        """
        # Create tool without event manager
        tool = MockTool(event_manager=None)
        
        # Test data
        kwargs = {
            'target': 'example.com',
            'agent_id': 'agent_002'
        }
        
        # Execute tool
        result = await tool.execute(**kwargs)
        
        # Verify result structure
        assert isinstance(result, ToolResult)
        assert result.success == True
        assert result.output == "Mock tool executed on example.com"
        assert result.data['target'] == 'example.com'
        assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_execution_with_dict_return(self):
        """
        Property 1 (Dict return): Tool execution should handle dict returns
        For any tool that returns a dict, execute should convert it to ToolResult.
        
        **Validates: Requirements 1.1**
        """
        event_manager, mock_tui_bridge = self.create_test_fixtures()
        
        # Create tool that returns dict
        tool = MockDictTool(event_manager)
        
        # Test data
        kwargs = {
            'target': 'test.com',
            'agent_id': 'agent_003',
            'scan_id': 'scan_456'
        }
        
        # Execute tool
        result = await tool.execute(**kwargs)
        
        # Verify result structure
        assert isinstance(result, ToolResult)
        assert result.success == True
        assert result.output == "dict result"
        # The data should contain the converted dict result
        assert result.data == {"output": "dict result", "data": {'target': 'test.com'}}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_tool_execution_error_handling(self):
        """
        Property 1 (Error handling): Tool execution should handle exceptions gracefully
        For any tool that raises an exception, execute should return ToolResult with error.
        
        **Validates: Requirements 1.1**
        """
        event_manager, mock_tui_bridge = self.create_test_fixtures()
        
        # Create failing tool
        tool = MockFailingTool(event_manager)
        
        # Test data
        kwargs = {
            'target': 'failing.com',
            'agent_id': 'agent_004',
            'scan_id': 'scan_789'
        }
        
        # Execute tool
        result = await tool.execute(**kwargs)
        
        # Verify error result structure
        assert isinstance(result, ToolResult)
        assert result.success == False
        assert "Mock tool failure" in result.output  # Error message should be in output
        assert result.error == "Mock tool failure"
        
        # Verify error events were emitted
        assert mock_tui_bridge.send_tool_update.call_count == 2  # start and complete (with error)

    @pytest.mark.asyncio
    async def test_tool_execution_multiple_calls(self):
        """
        Property 1 (Multiple calls): Tool execution should work consistently across multiple calls
        For any tool, multiple executions should return consistent ToolResult structures.
        
        **Validates: Requirements 1.1**
        """
        event_manager, mock_tui_bridge = self.create_test_fixtures()
        
        # Create tool
        tool = MockTool(event_manager)
        
        # Execute tool multiple times
        results = []
        for i in range(3):
            kwargs = {
                'target': f'target_{i}',
                'agent_id': f'agent_{i}',
                'scan_id': f'scan_{i}'
            }
            result = await tool.execute(**kwargs)
            results.append(result)
        
        # Verify all results have consistent structure
        for i, result in enumerate(results):
            assert isinstance(result, ToolResult)
            assert result.success == True
            assert result.output == f"Mock tool executed on target_{i}"
            assert result.data['target'] == f'target_{i}'
            assert result.error is None
        
        # Verify events were emitted for all executions
        assert mock_tui_bridge.send_tool_update.call_count == 6  # 2 events per execution
        assert mock_tui_bridge.send_agent_update.call_count == 3  # 1 per execution

    @pytest.mark.asyncio
    async def test_tool_execution_parameter_validation(self):
        """
        Property 1 (Parameter handling): Tool execution should handle various parameter types
        For any tool with different parameter types, execute should handle them correctly.
        
        **Validates: Requirements 1.1**
        """
        event_manager, mock_tui_bridge = self.create_test_fixtures()
        
        # Create tool
        tool = MockTool(event_manager)
        
        # Test with various parameter types
        test_cases = [
            {'target': 'string_target', 'port': 80, 'enabled': True},
            {'target': '192.168.1.1', 'ports': [80, 443, 8080]},
            {'target': 'complex.com', 'config': {'timeout': 30, 'retries': 3}}
        ]
        
        for kwargs in test_cases:
            kwargs.update({'agent_id': 'test_agent', 'scan_id': 'test_scan'})
            result = await tool.execute(**kwargs)
            
            # Verify result structure
            assert isinstance(result, ToolResult)
            assert result.success == True
            assert isinstance(result.output, str)
            assert isinstance(result.data, dict)
            assert result.error is None
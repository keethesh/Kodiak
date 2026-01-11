"""
Property-based tests for event broadcasting functionality.

Feature: core-integration-fixes, Property 2: Event broadcasting completeness
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call

from kodiak.api.events import EventManager
from kodiak.services.websocket_manager import ConnectionManager


class TestEventBroadcastingProperties:
    """Property-based tests for event broadcasting completeness."""

    def create_test_fixtures(self):
        """Create test fixtures for each test run."""
        # Mock WebSocket manager
        mock_websocket_manager = MagicMock(spec=ConnectionManager)
        mock_websocket_manager.send_tool_update = AsyncMock()
        mock_websocket_manager.send_agent_update = AsyncMock()
        mock_websocket_manager.send_finding_update = AsyncMock()
        mock_websocket_manager.broadcast = AsyncMock()
        mock_websocket_manager.broadcast_global = AsyncMock()
        
        # Event manager
        event_manager = EventManager(mock_websocket_manager)
        
        # Sample tool result class
        class MockToolResult:
            def __init__(self, success=True, output="test output", error=None, data=None):
                self.success = success
                self.output = output
                self.error = error
                self.data = data or {}
        
        return event_manager, mock_websocket_manager, MockToolResult

    @pytest.mark.asyncio
    async def test_event_broadcasting_completeness_basic(self):
        """
        Property 2: Event broadcasting completeness
        For any tool execution, the Event_Manager should broadcast start, progress, 
        and completion events in the correct sequence to all connected WebSocket clients.
        
        **Validates: Requirements 1.2, 4.1**
        """
        event_manager, mock_websocket_manager, MockToolResult = self.create_test_fixtures()
        
        # Test data
        tool_name = "nmap"
        target = "192.168.1.1"
        agent_id = "agent_001"
        scan_id = "scan_123"
        
        # Create a successful tool result
        result = MockToolResult(success=True, output="test output")
        progress_data = {"percent": 50, "message": "Processing"}
        
        # Execute the event sequence
        await event_manager.emit_tool_start(tool_name, target, agent_id, scan_id)
        await event_manager.emit_tool_progress(tool_name, progress_data, scan_id)
        await event_manager.emit_tool_complete(tool_name, result, scan_id)
        
        # Verify all three events were broadcast
        assert mock_websocket_manager.send_tool_update.call_count == 3
        
        # Verify the calls were made in the correct order
        calls = mock_websocket_manager.send_tool_update.call_args_list
        
        # Check start event
        start_call = calls[0]
        assert start_call[1]['scan_id'] == scan_id
        assert start_call[1]['tool_name'] == tool_name
        assert start_call[1]['status'] == "started"
        assert start_call[1]['data']['target'] == target
        assert start_call[1]['data']['agent_id'] == agent_id
        
        # Check progress event
        progress_call = calls[1]
        assert progress_call[1]['scan_id'] == scan_id
        assert progress_call[1]['tool_name'] == tool_name
        assert progress_call[1]['status'] == "progress"
        assert progress_call[1]['data']['progress'] == progress_data
        
        # Check completion event
        complete_call = calls[2]
        assert complete_call[1]['scan_id'] == scan_id
        assert complete_call[1]['tool_name'] == tool_name
        assert complete_call[1]['status'] == "completed"
        assert complete_call[1]['data']['success'] == True
        assert complete_call[1]['data']['output'] == "test output"
        
        # Verify agent update was also sent for tool start
        mock_websocket_manager.send_agent_update.assert_called_once_with(
            scan_id=scan_id,
            agent_id=agent_id,
            status="executing",
            message_text=f"Executing {tool_name} on {target}"
        )

    @pytest.mark.asyncio
    async def test_event_broadcasting_with_failures(self):
        """
        Property 2 (Error case): Event broadcasting completeness for failed tools
        For any tool execution that fails, the Event_Manager should broadcast start 
        and failure events to all connected WebSocket clients.
        
        **Validates: Requirements 1.2, 4.1**
        """
        event_manager, mock_websocket_manager, MockToolResult = self.create_test_fixtures()
        
        # Test data
        tool_name = "sqlmap"
        target = "http://example.com"
        agent_id = "agent_002"
        scan_id = "scan_456"
        error_message = "Connection timeout"
        
        # Create a failed tool result
        result = MockToolResult(success=False, error=error_message, output=None)
        
        # Execute the event sequence for a failed tool
        await event_manager.emit_tool_start(tool_name, target, agent_id, scan_id)
        await event_manager.emit_tool_complete(tool_name, result, scan_id)
        
        # Verify start and failure events were broadcast
        assert mock_websocket_manager.send_tool_update.call_count == 2
        
        calls = mock_websocket_manager.send_tool_update.call_args_list
        
        # Check start event
        start_call = calls[0]
        assert start_call[1]['status'] == "started"
        
        # Check failure event
        failure_call = calls[1]
        assert failure_call[1]['scan_id'] == scan_id
        assert failure_call[1]['tool_name'] == tool_name
        assert failure_call[1]['status'] == "failed"
        assert failure_call[1]['data']['success'] == False
        assert failure_call[1]['data']['error'] == error_message

    @pytest.mark.asyncio
    async def test_event_broadcasting_without_scan_id(self):
        """
        Property 2 (Edge case): Event broadcasting should handle missing scan_id gracefully
        For any tool execution without scan_id, the Event_Manager should not crash
        but should not broadcast events either.
        
        **Validates: Requirements 1.2, 4.1**
        """
        event_manager, mock_websocket_manager, MockToolResult = self.create_test_fixtures()
        
        tool_name = "nuclei"
        target = "example.com"
        agent_id = "agent_003"
        
        result = MockToolResult(success=True)
        
        # Execute events without scan_id (should not crash)
        await event_manager.emit_tool_start(tool_name, target, agent_id, scan_id=None)
        await event_manager.emit_tool_complete(tool_name, result, scan_id=None)
        
        # Verify no WebSocket calls were made (since no scan_id)
        mock_websocket_manager.send_tool_update.assert_not_called()
        mock_websocket_manager.send_agent_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_discovery_event_broadcasting(self):
        """
        Property 2 (Discovery): Discovery events should be broadcast correctly
        For any discovery event, the Event_Manager should broadcast it to WebSocket clients.
        
        **Validates: Requirements 1.2, 4.1**
        """
        event_manager, mock_websocket_manager, MockToolResult = self.create_test_fixtures()
        
        discovery_data = {
            "type": "service",
            "host": "192.168.1.100",
            "port": 80,
            "service": "http"
        }
        scan_id = "scan_789"
        
        await event_manager.emit_discovery(discovery_data, scan_id)
        
        # Verify discovery was broadcast
        mock_websocket_manager.send_finding_update.assert_called_once_with(
            scan_id=scan_id,
            finding=discovery_data
        )

    @pytest.mark.asyncio
    async def test_event_broadcasting_multiple_tools(self):
        """
        Property 2 (Multiple tools): Event broadcasting should work for multiple concurrent tools
        For any multiple tool executions, the Event_Manager should broadcast all events correctly.
        
        **Validates: Requirements 1.2, 4.1**
        """
        event_manager, mock_websocket_manager, MockToolResult = self.create_test_fixtures()
        
        # Test concurrent tool executions
        tools = [
            ("nmap", "192.168.1.1", "agent_001"),
            ("nuclei", "example.com", "agent_002"),
            ("sqlmap", "http://test.com", "agent_003")
        ]
        scan_id = "scan_multi"
        
        # Execute all tools
        for tool_name, target, agent_id in tools:
            result = MockToolResult(success=True, output=f"{tool_name} output")
            await event_manager.emit_tool_start(tool_name, target, agent_id, scan_id)
            await event_manager.emit_tool_complete(tool_name, result, scan_id)
        
        # Verify all events were broadcast (2 events per tool = 6 total)
        assert mock_websocket_manager.send_tool_update.call_count == 6
        
        # Verify all agent updates were sent (1 per tool = 3 total)
        assert mock_websocket_manager.send_agent_update.call_count == 3
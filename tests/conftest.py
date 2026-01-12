"""Pytest configuration and shared fixtures for Kodiak tests."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from kodiak.api.events import EventManager


@pytest.fixture
def mock_tui_bridge():
    """Create a mock TUI bridge for testing."""
    bridge = MagicMock()
    bridge.send_tool_update = AsyncMock()
    bridge.send_agent_update = AsyncMock()
    bridge.send_finding_update = AsyncMock()
    bridge.broadcast = AsyncMock()
    bridge.broadcast_global = AsyncMock()
    return bridge


@pytest.fixture
def event_manager(mock_tui_bridge):
    """Create an EventManager instance with mocked TUI bridge."""
    return EventManager(mock_tui_bridge)


@pytest.fixture
def sample_tool_result():
    """Create a sample tool result for testing."""
    class MockToolResult:
        def __init__(self, success=True, output="test output", error=None, data=None):
            self.success = success
            self.output = output
            self.error = error
            self.data = data or {}
    
    return MockToolResult


@pytest.fixture
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
"""Pytest configuration and shared fixtures for Kodiak tests."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from kodiak.api.events import EventManager
from kodiak.services.websocket_manager import ConnectionManager


@pytest.fixture
def mock_websocket_manager():
    """Create a mock WebSocket manager for testing."""
    manager = MagicMock(spec=ConnectionManager)
    manager.send_tool_update = AsyncMock()
    manager.send_agent_update = AsyncMock()
    manager.send_finding_update = AsyncMock()
    manager.broadcast = AsyncMock()
    manager.broadcast_global = AsyncMock()
    return manager


@pytest.fixture
def event_manager(mock_websocket_manager):
    """Create an EventManager instance with mocked WebSocket manager."""
    return EventManager(mock_websocket_manager)


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
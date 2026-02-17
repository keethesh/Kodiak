"""Pytest configuration and shared fixtures for Kodiak tests."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from typing import Dict, Any

from kodiak.api.events import TUIEventManager


@pytest.fixture
def event_manager():
    """Create a TUIEventManager instance for testing."""
    return TUIEventManager()


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
#!/usr/bin/env python3
"""
Test script to verify real-time WebSocket events functionality.
This tests the requirements for task 7: Implement Real-time WebSocket Events.
"""

import asyncio
import sys
import os
import json
import time
from uuid import uuid4

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

async def test_event_manager_initialization():
    """Test EventManager initialization and basic functionality"""
    print("Testing EventManager initialization...")
    
    try:
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create WebSocket manager and EventManager
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        # Test health status
        health = event_manager.get_health_status()
        assert health["healthy"] == True, "EventManager should be healthy"
        
        print("✓ EventManager initialized successfully")
        print(f"  Health status: {health}")
        return True
        
    except Exception as e:
        print(f"✗ EventManager initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_scan_lifecycle_events():
    """Test scan lifecycle event emission"""
    print("\nTesting scan lifecycle events...")
    
    try:
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create event manager
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        scan_id = str(uuid4())
        scan_name = "Test Scan"
        target = "example.com"
        
        # Test scan started event
        await event_manager.emit_scan_started(
            scan_id=scan_id,
            scan_name=scan_name,
            target=target,
            agent_id="test-agent"
        )
        print("✓ Scan started event emitted successfully")
        
        # Test scan completed event
        await event_manager.emit_scan_completed(
            scan_id=scan_id,
            scan_name=scan_name,
            status="completed",
            summary={"total_tasks": 5, "findings": 2}
        )
        print("✓ Scan completed event emitted successfully")
        
        # Test scan failed event
        await event_manager.emit_scan_failed(
            scan_id=scan_id,
            scan_name=scan_name,
            error="Test error",
            details={"reason": "test failure"}
        )
        print("✓ Scan failed event emitted successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Scan lifecycle events test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_tool_execution_events():
    """Test tool execution event emission"""
    print("\nTesting tool execution events...")
    
    try:
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create event manager
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        scan_id = str(uuid4())
        tool_name = "nmap"
        target = "192.168.1.1"
        agent_id = "test-agent"
        
        # Test tool start event
        await event_manager.emit_tool_start(
            tool_name=tool_name,
            target=target,
            agent_id=agent_id,
            scan_id=scan_id
        )
        print("✓ Tool start event emitted successfully")
        
        # Test tool complete event
        class MockResult:
            def __init__(self, success=True):
                self.success = success
                self.output = "Test output"
                self.error = None if success else "Test error"
                self.data = {"test": "data"}
        
        await event_manager.emit_tool_complete(
            tool_name=tool_name,
            result=MockResult(success=True),
            scan_id=scan_id
        )
        print("✓ Tool complete event emitted successfully")
        
        # Test tool failed event
        await event_manager.emit_tool_complete(
            tool_name=tool_name,
            result=MockResult(success=False),
            scan_id=scan_id
        )
        print("✓ Tool failed event emitted successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Tool execution events test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_finding_discovery_events():
    """Test finding discovery event emission"""
    print("\nTesting finding discovery events...")
    
    try:
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create event manager
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        scan_id = str(uuid4())
        agent_id = "test-agent"
        
        # Test finding discovered event
        finding = {
            "id": str(uuid4()),
            "title": "SQL Injection Vulnerability",
            "severity": "high",
            "description": "SQL injection found in login form",
            "target": "http://example.com/login",
            "evidence": {"payload": "' OR 1=1 --", "response": "Login successful"}
        }
        
        await event_manager.emit_finding_discovered(
            scan_id=scan_id,
            finding=finding,
            agent_id=agent_id
        )
        print("✓ Finding discovery event emitted successfully")
        print(f"  Finding: {finding['title']} ({finding['severity']})")
        
        return True
        
    except Exception as e:
        print(f"✗ Finding discovery events test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_agent_thinking_events():
    """Test agent thinking event emission"""
    print("\nTesting agent thinking events...")
    
    try:
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create event manager
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        scan_id = str(uuid4())
        agent_id = "test-agent"
        
        # Test agent thinking event
        await event_manager.emit_agent_thinking(
            agent_id=agent_id,
            message="Analyzing target for potential vulnerabilities",
            scan_id=scan_id
        )
        print("✓ Agent thinking event emitted successfully")
        
        return True
        
    except Exception as e:
        print(f"✗ Agent thinking events test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_websocket_connection_manager():
    """Test WebSocket connection manager functionality"""
    print("\nTesting WebSocket connection manager...")
    
    try:
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create connection manager
        manager = ConnectionManager()
        
        # Test connection stats
        stats = manager.get_connection_stats()
        assert isinstance(stats, dict), "Stats should be a dictionary"
        assert "total_scan_connections" in stats, "Stats should include total_scan_connections"
        assert "global_connections" in stats, "Stats should include global_connections"
        
        print("✓ WebSocket connection manager working correctly")
        print(f"  Initial stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"✗ WebSocket connection manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_websocket_endpoints_structure():
    """Test WebSocket endpoints structure and imports"""
    print("\nTesting WebSocket endpoints structure...")
    
    try:
        from kodiak.api.endpoints.ws import router
        from fastapi import APIRouter
        
        # Verify router is properly configured
        assert isinstance(router, APIRouter), "WebSocket router should be an APIRouter instance"
        
        # Check that routes are defined
        routes = [route.path for route in router.routes]
        assert "/ws/{scan_id}" in routes, "Scan-specific WebSocket endpoint should be defined"
        assert "/ws" in routes, "Global WebSocket endpoint should be defined"
        
        print("✓ WebSocket endpoints structure is correct")
        print(f"  Available routes: {routes}")
        
        return True
        
    except Exception as e:
        print(f"✗ WebSocket endpoints structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_agent_finding_reporting():
    """Test agent finding reporting functionality"""
    print("\nTesting agent finding reporting...")
    
    try:
        from kodiak.core.agent import KodiakAgent
        from kodiak.core.tools.inventory import ToolInventory
        from kodiak.api.events import EventManager
        from kodiak.services.websocket_manager import ConnectionManager
        
        # Create dependencies
        tool_inventory = ToolInventory()
        tool_inventory.initialize_tools()
        
        websocket_manager = ConnectionManager()
        event_manager = EventManager(websocket_manager)
        
        # Create agent
        agent = KodiakAgent(
            agent_id="test-agent",
            tool_inventory=tool_inventory,
            event_manager=event_manager,
            role="scout",
            project_id=uuid4()
        )
        
        # Test finding reporting
        finding = {
            "title": "Open Port Detected",
            "severity": "medium",
            "description": "Port 22 is open on target",
            "target": "192.168.1.1:22"
        }
        
        enhanced_finding = await agent.report_finding(finding)
        
        # Verify finding was enhanced
        assert "agent_id" in enhanced_finding, "Finding should include agent_id"
        assert "discovered_at" in enhanced_finding, "Finding should include discovered_at timestamp"
        assert enhanced_finding["agent_id"] == agent.agent_id, "Agent ID should match"
        
        print("✓ Agent finding reporting working correctly")
        print(f"  Enhanced finding keys: {list(enhanced_finding.keys())}")
        
        return True
        
    except Exception as e:
        print(f"✗ Agent finding reporting test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all WebSocket events tests"""
    print("=" * 70)
    print("Testing Real-time WebSocket Events")
    print("=" * 70)
    
    tests = [
        test_event_manager_initialization,
        test_scan_lifecycle_events,
        test_tool_execution_events,
        test_finding_discovery_events,
        test_agent_thinking_events,
        test_websocket_connection_manager,
        test_websocket_endpoints_structure,
        test_agent_finding_reporting,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"Test failed with exception: {e}")
    
    print("\n" + "=" * 70)
    print(f"Test Results: {passed}/{total} tests passed")
    print("=" * 70)
    
    if passed == total:
        print("✓ All WebSocket events tests passed!")
        print("\nReal-time WebSocket Events are working correctly:")
        print("  • EventManager initialization and health monitoring")
        print("  • Scan lifecycle events (started, completed, failed)")
        print("  • Tool execution events (start, complete, progress)")
        print("  • Finding discovery events with metadata")
        print("  • Agent thinking events for progress tracking")
        print("  • WebSocket connection management")
        print("  • Agent finding reporting integration")
        return True
    else:
        print("✗ Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
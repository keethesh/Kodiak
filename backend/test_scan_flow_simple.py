#!/usr/bin/env python3
"""
Simple test to verify scan creation and execution flow.
Tests the requirements for task 5: Implement Scan Creation and Execution Flow.
"""

import asyncio
import sys
import os
import json
from uuid import uuid4

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

async def test_scan_creation_basic():
    """Test basic scan creation functionality"""
    print("Testing basic scan creation...")
    
    try:
        from kodiak.database import get_session, init_db
        from kodiak.database.models import Project, ScanJob, ScanStatus
        from kodiak.database.crud import project as crud_project, scan_job as crud_scan
        
        # Initialize database
        await init_db()
        
        async for session in get_session():
            # Create a test project first
            project = Project(name="Test Project for Scan Creation")
            created_project = await crud_project.create(session, project)
            
            # Test valid scan creation
            scan_config = {
                "target": "example.com",
                "instructions": "Perform a basic security scan"
            }
            
            scan = ScanJob(
                project_id=created_project.id,
                name="Test Scan",
                config=scan_config
            )
            
            created_scan = await crud_scan.create(session, scan)
            
            # Verify scan was created correctly
            assert created_scan.id is not None, "Scan should have an ID"
            assert created_scan.project_id == created_project.id, "Scan should be linked to project"
            assert created_scan.name == "Test Scan", "Scan name should be preserved"
            assert created_scan.status == ScanStatus.PENDING, "New scan should have PENDING status"
            assert created_scan.config["target"] == "example.com", "Scan config should be preserved"
            
            print("✓ Basic scan creation works correctly")
            print(f"  Created scan: {created_scan.name} (ID: {created_scan.id})")
            print(f"  Status: {created_scan.status}")
            print(f"  Target: {created_scan.config.get('target')}")
            return True
            
    except Exception as e:
        print(f"✗ Basic scan creation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_orchestrator_start_scan():
    """Test orchestrator start_scan functionality"""
    print("\nTesting orchestrator start_scan...")
    
    try:
        from kodiak.database import get_session
        from kodiak.database.models import Project, ScanJob, Task
        from kodiak.database.crud import project as crud_project, scan_job as crud_scan
        from kodiak.core.orchestrator import Orchestrator
        from kodiak.core.tools.inventory import inventory
        from sqlmodel import select
        
        async for session in get_session():
            # Create test project and scan
            project = Project(name="Test Project for Orchestrator")
            created_project = await crud_project.create(session, project)
            
            scan_config = {
                "target": "testsite.com",
                "instructions": "Conduct a comprehensive security assessment"
            }
            
            scan = ScanJob(
                project_id=created_project.id,
                name="Orchestrator Test Scan",
                config=scan_config
            )
            
            created_scan = await crud_scan.create(session, scan)
            
            # Create orchestrator and start scan
            orchestrator = Orchestrator(inventory)
            
            # Start the scan (this should create a root task)
            await orchestrator.start_scan(created_scan.id)
            
            # Verify root task was created
            statement = select(Task).where(Task.project_id == created_project.id)
            result = await session.execute(statement)
            tasks = result.scalars().all()
            
            assert len(tasks) > 0, "Root task should be created"
            
            root_task = tasks[0]
            assert root_task.name == "Mission Manager", "Root task should be named 'Mission Manager'"
            assert root_task.status == "pending", "Root task should have pending status"
            assert root_task.assigned_agent_id == f"manager-{created_scan.id}", "Root task should have correct agent ID"
            
            # Verify directive is properly formatted
            directive = json.loads(root_task.directive)
            assert directive["goal"] == scan_config["instructions"], "Directive should contain scan instructions"
            assert directive["target"] == scan_config["target"], "Directive should contain scan target"
            assert directive["role"] == "manager", "Directive should specify manager role"
            
            # Verify scan status was updated
            await session.refresh(created_scan)
            assert created_scan.status == "running", "Scan status should be updated to running"
            
            print("✓ Orchestrator start_scan works correctly")
            print(f"  Created task: {root_task.name} (ID: {root_task.id})")
            print(f"  Agent ID: {root_task.assigned_agent_id}")
            print(f"  Scan status: {created_scan.status}")
            return True
            
    except Exception as e:
        print(f"✗ Orchestrator start_scan test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run basic scan flow tests"""
    print("=" * 60)
    print("Testing Basic Scan Creation and Execution Flow")
    print("=" * 60)
    
    tests = [
        test_scan_creation_basic,
        test_orchestrator_start_scan,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if await test():
                passed += 1
        except Exception as e:
            print(f"Test failed with exception: {e}")
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("✓ All basic scan flow tests passed!")
        return True
    else:
        print("✗ Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
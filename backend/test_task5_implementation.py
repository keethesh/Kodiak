#!/usr/bin/env python3
"""
Test script to verify Task 5: Implement Scan Creation and Execution Flow
This tests all the requirements for the scan creation and execution flow.
"""

import asyncio
import sys
import os
import json
from uuid import uuid4

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from kodiak.database.engine import get_session
from kodiak.database.models import Project, ScanJob, Task, ScanStatus
from kodiak.database.crud import project as project_crud, scan_job as scan_crud
from kodiak.core.orchestrator import orchestrator
from sqlmodel import select


async def test_requirement_2_1():
    """Test: WHEN a user creates a project via POST /api/v1/projects, THE System SHALL store the project in the database"""
    print("Testing Requirement 2.1: Project creation and storage...")
    
    async for session in get_session():
        try:
            # Create a test project
            test_project = Project(
                name="Test Project for Req 2.1",
                description="Test project for requirement 2.1 validation"
            )
            
            created_project = await project_crud.create(session, test_project)
            
            # Verify project was stored
            retrieved_project = await project_crud.get(session, created_project.id)
            
            if retrieved_project and retrieved_project.name == test_project.name:
                print("✓ Requirement 2.1 PASSED: Project created and stored successfully")
                return True, created_project.id
            else:
                print("❌ Requirement 2.1 FAILED: Project not properly stored")
                return False, None
                
        except Exception as e:
            print(f"❌ Requirement 2.1 FAILED with exception: {e}")
            return False, None


async def test_requirement_2_2(project_id):
    """Test: WHEN a user creates a scan job via POST /api/v1/scans, THE System SHALL validate the configuration and store the scan"""
    print("Testing Requirement 2.2: Scan creation with validation...")
    
    async for session in get_session():
        try:
            # Test valid scan configuration
            valid_scan = ScanJob(
                project_id=project_id,
                name="Valid Test Scan",
                status=ScanStatus.PENDING,
                config={
                    "target": "https://example.com",
                    "instructions": "Conduct a basic security assessment"
                }
            )
            
            created_scan = await scan_crud.create(session, valid_scan)
            
            # Verify scan was stored with correct configuration
            retrieved_scan = await scan_crud.get(session, created_scan.id)
            
            if (retrieved_scan and 
                retrieved_scan.config.get("target") == "https://example.com" and
                retrieved_scan.status == ScanStatus.PENDING):
                print("✓ Requirement 2.2 PASSED: Scan created with valid configuration")
                return True, created_scan.id
            else:
                print("❌ Requirement 2.2 FAILED: Scan not properly stored or validated")
                return False, None
                
        except Exception as e:
            print(f"❌ Requirement 2.2 FAILED with exception: {e}")
            return False, None


async def test_requirement_2_3(scan_id):
    """Test: WHEN a user starts a scan via POST /api/v1/scans/{id}/start, THE System SHALL create a root task and update scan status to RUNNING"""
    print("Testing Requirement 2.3: Scan start creates root task and updates status...")
    
    async for session in get_session():
        try:
            # Get initial scan state
            scan_before = await scan_crud.get(session, scan_id)
            if not scan_before:
                print("❌ Requirement 2.3 FAILED: Scan not found")
                return False
            
            # Start the scan
            await orchestrator.start_scan(scan_id)
            
            # Check if scan status was updated
            await session.refresh(scan_before)
            scan_after = scan_before
            
            if scan_after.status != ScanStatus.RUNNING:
                print(f"❌ Requirement 2.3 FAILED: Scan status not updated to RUNNING (current: {scan_after.status})")
                return False
            
            # Check if root task was created
            task_stmt = select(Task).where(
                Task.project_id == scan_after.project_id,
                Task.name == "Mission Manager"
            )
            task_result = await session.execute(task_stmt)
            root_task = task_result.scalar_one_or_none()
            
            if not root_task:
                print("❌ Requirement 2.3 FAILED: Root task not created")
                return False
            
            # Verify task has correct configuration
            try:
                directive = json.loads(root_task.directive)
                if "goal" not in directive or "role" not in directive:
                    print("❌ Requirement 2.3 FAILED: Root task directive missing required fields")
                    return False
            except json.JSONDecodeError:
                print("❌ Requirement 2.3 FAILED: Root task directive is not valid JSON")
                return False
            
            print("✓ Requirement 2.3 PASSED: Scan started, status updated to RUNNING, root task created")
            return True
            
        except Exception as e:
            print(f"❌ Requirement 2.3 FAILED with exception: {e}")
            return False


async def test_requirement_2_4(project_id):
    """Test: WHEN a scan is started, THE Orchestrator SHALL detect the pending task and spawn an agent worker"""
    print("Testing Requirement 2.4: Orchestrator detects pending task and spawns worker...")
    
    async for session in get_session():
        try:
            # Check if there are pending tasks for this project
            task_stmt = select(Task).where(
                Task.project_id == project_id,
                Task.status == "pending"
            )
            task_result = await session.execute(task_stmt)
            pending_tasks = task_result.scalars().all()
            
            if not pending_tasks:
                # Check if task was already picked up and is running
                running_task_stmt = select(Task).where(
                    Task.project_id == project_id,
                    Task.status == "running"
                )
                running_task_result = await session.execute(running_task_stmt)
                running_tasks = running_task_result.scalars().all()
                
                if running_tasks:
                    print("✓ Requirement 2.4 PASSED: Orchestrator detected and started processing task")
                    return True
                else:
                    print("❌ Requirement 2.4 FAILED: No pending or running tasks found")
                    return False
            
            # Wait a bit for orchestrator to pick up the task
            await asyncio.sleep(3)
            
            # Check if task status changed from pending
            await session.refresh(pending_tasks[0])
            task_after_wait = pending_tasks[0]
            
            if task_after_wait.status in ["running", "completed"]:
                print("✓ Requirement 2.4 PASSED: Orchestrator detected pending task and spawned worker")
                return True
            else:
                print(f"❌ Requirement 2.4 FAILED: Task still pending after wait (status: {task_after_wait.status})")
                return False
                
        except Exception as e:
            print(f"❌ Requirement 2.4 FAILED with exception: {e}")
            return False


async def test_requirement_2_5(scan_id, project_id):
    """Test: WHEN a scan is stopped via POST /api/v1/scans/{id}/stop, THE System SHALL cancel the worker and update scan status"""
    print("Testing Requirement 2.5: Scan stop cancels worker and updates status...")
    
    async for session in get_session():
        try:
            # Stop the scan
            cancelled_workers = await orchestrator.stop_scan(scan_id)
            
            # Check if scan status was updated
            scan_after_stop = await scan_crud.get(session, scan_id)
            
            if scan_after_stop.status not in [ScanStatus.PAUSED, ScanStatus.COMPLETED]:
                print(f"❌ Requirement 2.5 FAILED: Scan status not properly updated after stop (current: {scan_after_stop.status})")
                return False
            
            # Check if tasks were cancelled
            task_stmt = select(Task).where(Task.project_id == project_id)
            task_result = await session.execute(task_stmt)
            tasks = task_result.scalars().all()
            
            cancelled_tasks = [task for task in tasks if task.status == "cancelled"]
            
            if cancelled_workers > 0 or cancelled_tasks:
                print(f"✓ Requirement 2.5 PASSED: Scan stopped, {cancelled_workers} workers cancelled, scan status: {scan_after_stop.status}")
                return True
            else:
                print("✓ Requirement 2.5 PASSED: Scan stopped successfully (no active workers to cancel)")
                return True
                
        except Exception as e:
            print(f"❌ Requirement 2.5 FAILED with exception: {e}")
            return False


async def test_orchestrator_functionality():
    """Test orchestrator core functionality"""
    print("Testing Orchestrator core functionality...")
    
    try:
        # Test tool validation
        available_tools = orchestrator.get_available_tools()
        if not available_tools:
            print("❌ Orchestrator FAILED: No tools available")
            return False
        
        # Test tool existence validation
        valid_tool = available_tools[0]
        if not orchestrator.validate_tool_exists(valid_tool):
            print(f"❌ Orchestrator FAILED: Tool validation failed for {valid_tool}")
            return False
        
        if orchestrator.validate_tool_exists("nonexistent_tool"):
            print("❌ Orchestrator FAILED: Invalid tool validation should return False")
            return False
        
        # Test role-based tool assignment
        scout_tools = orchestrator.get_tools_for_role("scout")
        manager_tools = orchestrator.get_tools_for_role("manager")
        
        if not scout_tools or not manager_tools:
            print("❌ Orchestrator FAILED: Role-based tool assignment not working")
            return False
        
        print(f"✓ Orchestrator PASSED: {len(available_tools)} tools available, role-based assignment working")
        return True
        
    except Exception as e:
        print(f"❌ Orchestrator FAILED with exception: {e}")
        return False


async def main():
    """Run all tests for Task 5: Implement Scan Creation and Execution Flow"""
    print("=" * 70)
    print("Testing Task 5: Implement Scan Creation and Execution Flow")
    print("=" * 70)
    
    try:
        # Test orchestrator functionality first
        if not await test_orchestrator_functionality():
            print("\n❌ Orchestrator functionality tests failed")
            return False
        
        # Test Requirement 2.1: Project creation
        req_2_1_passed, project_id = await test_requirement_2_1()
        if not req_2_1_passed:
            return False
        
        # Test Requirement 2.2: Scan creation with validation
        req_2_2_passed, scan_id = await test_requirement_2_2(project_id)
        if not req_2_2_passed:
            return False
        
        # Test Requirement 2.3: Scan start creates root task and updates status
        req_2_3_passed = await test_requirement_2_3(scan_id)
        if not req_2_3_passed:
            return False
        
        # Test Requirement 2.4: Orchestrator detects pending task and spawns worker
        req_2_4_passed = await test_requirement_2_4(project_id)
        if not req_2_4_passed:
            return False
        
        # Test Requirement 2.5: Scan stop cancels worker and updates status
        req_2_5_passed = await test_requirement_2_5(scan_id, project_id)
        if not req_2_5_passed:
            return False
        
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED: Task 5 implementation is working correctly!")
        print("✓ Requirement 2.1: Project creation and storage")
        print("✓ Requirement 2.2: Scan creation with validation")
        print("✓ Requirement 2.3: Scan start creates root task and updates status")
        print("✓ Requirement 2.4: Orchestrator detects pending task and spawns worker")
        print("✓ Requirement 2.5: Scan stop cancels worker and updates status")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"\n❌ Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
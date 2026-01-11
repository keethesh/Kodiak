#!/usr/bin/env python3
"""
Test script for scan creation and execution flow.
"""

import asyncio
import sys
import os
from uuid import uuid4

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from kodiak.database.engine import get_session
from kodiak.database.models import Project, ScanJob, Task, ScanStatus
from kodiak.database.crud import project as project_crud, scan_job as scan_crud
from kodiak.core.orchestrator import orchestrator
from sqlmodel import select


async def test_scan_creation_flow():
    """Test the scan creation and execution flow."""
    print("🧪 Testing Scan Creation and Execution Flow")
    print("=" * 50)
    
    # Get database session
    async for session in get_session():
        try:
            # 1. Create a test project
            test_project = Project(
                name="Test Scan Flow",
                description="Test project for scan creation and execution flow"
            )
            
            created_project = await project_crud.create(session, test_project)
            project_id = created_project.id
            print(f"✓ Created test project: {project_id}")
            
            # 2. Create a scan job
            print("\n📝 Testing scan creation...")
            
            scan_job = ScanJob(
                project_id=project_id,
                name="Test Security Scan",
                status=ScanStatus.PENDING,
                config={
                    "target": "https://example.com",
                    "instructions": "Conduct a basic security assessment of the target website."
                }
            )
            
            created_scan = await scan_crud.create(session, scan_job)
            scan_id = created_scan.id
            print(f"✓ Created scan job: {scan_id}")
            print(f"  - Target: {created_scan.config['target']}")
            print(f"  - Status: {created_scan.status}")
            
            # 3. Test scan start (create root task)
            print("\n🚀 Testing scan start...")
            
            await orchestrator.start_scan(scan_id)
            
            # Check if root task was created
            await session.refresh(created_scan)
            print(f"✓ Scan status after start: {created_scan.status}")
            
            # Check for root task
            task_stmt = select(Task).where(
                Task.project_id == project_id,
                Task.name == "Mission Manager"
            )
            task_result = await session.execute(task_stmt)
            root_task = task_result.scalar_one_or_none()
            
            if root_task:
                print(f"✓ Root task created: {root_task.id}")
                print(f"  - Agent ID: {root_task.assigned_agent_id}")
                print(f"  - Status: {root_task.status}")
                print(f"  - Directive: {root_task.directive}")
            else:
                print("❌ Root task was not created")
                return False
            
            # 4. Test scan stop
            print("\n🛑 Testing scan stop...")
            
            cancelled_workers = await orchestrator.stop_scan(scan_id)
            
            # Check scan status after stop
            await session.refresh(created_scan)
            print(f"✓ Scan status after stop: {created_scan.status}")
            print(f"✓ Cancelled workers: {cancelled_workers}")
            
            # Check task status after stop
            await session.refresh(root_task)
            print(f"✓ Root task status after stop: {root_task.status}")
            
            # 5. Test scan configuration validation
            print("\n🔍 Testing scan configuration validation...")
            
            # Test scan without target (should fail)
            invalid_scan = ScanJob(
                project_id=project_id,
                name="Invalid Scan",
                status=ScanStatus.PENDING,
                config={"instructions": "Test without target"}
            )
            
            try:
                created_invalid_scan = await scan_crud.create(session, invalid_scan)
                await orchestrator.start_scan(created_invalid_scan.id)
                
                # Check if scan was marked as failed
                await session.refresh(created_invalid_scan)
                if created_invalid_scan.status == ScanStatus.FAILED:
                    print("✓ Invalid scan configuration properly rejected")
                else:
                    print(f"❌ Invalid scan not properly handled, status: {created_invalid_scan.status}")
                    
            except Exception as e:
                print(f"✓ Invalid scan configuration properly rejected with error: {e}")
            
            # 6. Test orchestrator tool validation
            print("\n🔧 Testing orchestrator tool validation...")
            
            available_tools = orchestrator.get_available_tools()
            print(f"✓ Available tools: {len(available_tools)} tools")
            print(f"  - Sample tools: {available_tools[:5]}")
            
            # Test tool validation
            valid_tool = available_tools[0] if available_tools else "nmap"
            invalid_tool = "nonexistent_tool"
            
            print(f"✓ Tool '{valid_tool}' exists: {orchestrator.validate_tool_exists(valid_tool)}")
            print(f"✓ Tool '{invalid_tool}' exists: {orchestrator.validate_tool_exists(invalid_tool)}")
            
            # Test role-based tool assignment
            scout_tools = orchestrator.get_tools_for_role("scout")
            manager_tools = orchestrator.get_tools_for_role("manager")
            print(f"✓ Scout tools: {len(scout_tools)} tools")
            print(f"✓ Manager tools: {len(manager_tools)} tools")
            
            print("\n✅ All scan creation and execution flow tests passed!")
            return True
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        finally:
            # Clean up - in a real scenario, you might want to keep test data
            try:
                await session.rollback()
            except:
                pass


async def main():
    """Main test function."""
    success = await test_scan_creation_flow()
    if success:
        print("\n🎉 Scan creation and execution flow is working correctly!")
        sys.exit(0)
    else:
        print("\n💥 Scan creation and execution flow tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
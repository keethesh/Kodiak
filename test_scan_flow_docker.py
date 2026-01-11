#!/usr/bin/env python3
"""
Docker-compatible test script to verify scan creation and execution flow.
This tests the requirements for task 5: Implement Scan Creation and Execution Flow.

Run this from the host machine after starting docker-compose:
python test_scan_flow_docker.py
"""

import asyncio
import httpx
import json
import time
import sys
from uuid import uuid4

# Test configuration
BASE_URL = "http://localhost:8000/api/v1"
TEST_PROJECT_NAME = f"Docker Test Project {uuid4().hex[:8]}"
TEST_SCAN_NAME = f"Docker Test Scan {uuid4().hex[:8]}"

async def wait_for_backend():
    """Wait for backend to be ready"""
    print("Waiting for backend to be ready...")
    
    for attempt in range(30):  # Wait up to 30 seconds
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("http://localhost:8000/health")
                if response.status_code == 200:
                    print("✓ Backend is ready")
                    return True
        except Exception as e:
            print(f"Attempt {attempt + 1}/30: Backend not ready yet ({e})")
            await asyncio.sleep(1)
    
    print("✗ Backend failed to become ready")
    return False

async def test_project_creation():
    """Test project creation via API"""
    print("\nTesting project creation...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create project
            project_data = {
                "name": TEST_PROJECT_NAME,
                "description": "Docker test project for scan flow validation"
            }
            
            response = await client.post(f"{BASE_URL}/projects/", json=project_data)
            
            if response.status_code != 200:
                print(f"✗ Project creation failed: {response.status_code} - {response.text}")
                return None
            
            project = response.json()
            print(f"✓ Project created successfully: {project['name']} (ID: {project['id']})")
            return project
    except Exception as e:
        print(f"✗ Project creation failed with exception: {e}")
        return None

async def test_scan_creation(project_id: str):
    """Test scan creation via API"""
    print("\nTesting scan creation...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Create scan
            scan_data = {
                "project_id": project_id,
                "name": TEST_SCAN_NAME,
                "config": {
                    "target": "example.com",
                    "instructions": "Perform a comprehensive security assessment"
                }
            }
            
            response = await client.post(f"{BASE_URL}/scans/", json=scan_data)
            
            if response.status_code != 200:
                print(f"✗ Scan creation failed: {response.status_code} - {response.text}")
                return None
            
            scan = response.json()
            print(f"✓ Scan created successfully: {scan['name']} (ID: {scan['id']})")
            print(f"  Status: {scan['status']}")
            print(f"  Target: {scan['config']['target']}")
            return scan
    except Exception as e:
        print(f"✗ Scan creation failed with exception: {e}")
        return None

async def test_scan_start(scan_id: str):
    """Test scan start via API"""
    print("\nTesting scan start...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{BASE_URL}/scans/{scan_id}/start")
            
            if response.status_code != 200:
                print(f"✗ Scan start failed: {response.status_code} - {response.text}")
                return False
            
            result = response.json()
            print(f"✓ Scan started successfully")
            print(f"  Message: {result['message']}")
            print(f"  Status: {result['status']}")
            print(f"  Root task created: {result['root_task_created']}")
            return True
    except Exception as e:
        print(f"✗ Scan start failed with exception: {e}")
        return False

async def test_scan_status(scan_id: str):
    """Test scan status retrieval"""
    print("\nTesting scan status retrieval...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{BASE_URL}/scans/{scan_id}/status")
            
            if response.status_code != 200:
                print(f"✗ Scan status retrieval failed: {response.status_code} - {response.text}")
                return None
            
            status = response.json()
            print(f"✓ Scan status retrieved successfully")
            print(f"  Scan status: {status['scan_status']}")
            print(f"  Target: {status['target']}")
            print(f"  Total tasks: {status['task_summary']['total_tasks']}")
            print(f"  Tasks by status: {status['task_summary']['by_status']}")
            return status
    except Exception as e:
        print(f"✗ Scan status retrieval failed with exception: {e}")
        return None

async def test_scan_stop(scan_id: str):
    """Test scan stop via API"""
    print("\nTesting scan stop...")
    
    try:
        # Wait a bit to let the scan start processing
        await asyncio.sleep(3)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{BASE_URL}/scans/{scan_id}/stop")
            
            if response.status_code != 200:
                print(f"✗ Scan stop failed: {response.status_code} - {response.text}")
                return False
            
            result = response.json()
            print(f"✓ Scan stopped successfully")
            print(f"  Message: {result['message']}")
            print(f"  Status: {result['status']}")
            print(f"  Cancelled workers: {result['cancelled_workers']}")
            return True
    except Exception as e:
        print(f"✗ Scan stop failed with exception: {e}")
        return False

async def test_system_health():
    """Test system health endpoints"""
    print("\nTesting system health...")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test health endpoint
            response = await client.get("http://localhost:8000/health")
            if response.status_code != 200:
                print(f"✗ Health check failed: {response.status_code}")
                return False
            
            health = response.json()
            print(f"✓ Health check passed: {health}")
            
            # Test system status endpoint
            response = await client.get(f"{BASE_URL}/system/status")
            if response.status_code == 200:
                system_status = response.json()
                print(f"✓ System status: {system_status}")
            else:
                print(f"⚠ System status endpoint not available: {response.status_code}")
            
            return True
    except Exception as e:
        print(f"✗ System health test failed with exception: {e}")
        return False

async def test_configuration_validation():
    """Test scan configuration validation"""
    print("\nTesting scan configuration validation...")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First create a project
            project_data = {
                "name": f"Config Test Project {uuid4().hex[:8]}",
                "description": "Test project for config validation"
            }
            
            project_response = await client.post(f"{BASE_URL}/projects/", json=project_data)
            if project_response.status_code != 200:
                print("✗ Failed to create test project for config validation")
                return False
            
            project = project_response.json()
            
            # Test scan with valid configuration
            valid_scan_data = {
                "project_id": project["id"],
                "name": "Valid Config Scan",
                "config": {
                    "target": "valid.example.com",
                    "instructions": "Valid scan instructions"
                }
            }
            
            response = await client.post(f"{BASE_URL}/scans/", json=valid_scan_data)
            if response.status_code != 200:
                print(f"✗ Valid scan creation failed: {response.status_code} - {response.text}")
                return False
            
            valid_scan = response.json()
            print(f"✓ Valid scan created: {valid_scan['name']}")
            
            # Test scan without target (should fail at start)
            invalid_scan_data = {
                "project_id": project["id"],
                "name": "Invalid Scan",
                "config": {
                    "instructions": "This scan has no target"
                }
            }
            
            response = await client.post(f"{BASE_URL}/scans/", json=invalid_scan_data)
            
            # This should succeed at creation but fail at start
            if response.status_code == 200:
                scan = response.json()
                # Try to start the scan - this should fail
                start_response = await client.post(f"{BASE_URL}/scans/{scan['id']}/start")
                if start_response.status_code == 400:
                    print("✓ Configuration validation works correctly - scan without target rejected at start")
                    return True
                else:
                    print(f"✗ Configuration validation failed - scan without target was allowed to start: {start_response.status_code}")
                    return False
            else:
                print(f"✗ Unexpected response for invalid scan creation: {response.status_code}")
                return False
                
    except Exception as e:
        print(f"✗ Configuration validation test failed with exception: {e}")
        return False

async def main():
    """Run all scan endpoint tests in Docker environment"""
    print("=" * 70)
    print("Testing Scan Creation and Execution Flow in Docker Environment")
    print("=" * 70)
    
    # Wait for backend to be ready
    if not await wait_for_backend():
        print("✗ Backend is not ready, cannot run tests")
        return False
    
    try:
        # Test system health first
        if not await test_system_health():
            print("✗ System health check failed")
            return False
        
        # Test project creation
        project = await test_project_creation()
        if not project:
            print("✗ Cannot continue without project")
            return False
        
        # Test scan creation
        scan = await test_scan_creation(project["id"])
        if not scan:
            print("✗ Cannot continue without scan")
            return False
        
        # Test scan start
        if not await test_scan_start(scan["id"]):
            print("✗ Cannot continue without successful scan start")
            return False
        
        # Test scan status
        status = await test_scan_status(scan["id"])
        if not status:
            print("✗ Failed to get scan status")
            return False
        
        # Test scan stop
        if not await test_scan_stop(scan["id"]):
            print("✗ Failed to stop scan")
            return False
        
        # Test configuration validation
        if not await test_configuration_validation():
            print("✗ Configuration validation test failed")
            return False
        
        print("\n" + "=" * 70)
        print("✓ All scan endpoint tests passed in Docker environment!")
        print("=" * 70)
        print("\nScan Creation and Execution Flow is working correctly:")
        print("  ✓ Project creation via API")
        print("  ✓ Scan creation with proper validation")
        print("  ✓ Scan start with root task creation")
        print("  ✓ Scan status monitoring")
        print("  ✓ Scan stop with worker cancellation")
        print("  ✓ Configuration validation")
        print("  ✓ System health monitoring")
        return True
        
    except Exception as e:
        print(f"\n✗ Test suite failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
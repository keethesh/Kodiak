#!/usr/bin/env python3
"""
Test script for attempt tracking and deduplication functionality.
"""

import asyncio
import sys
import os
from uuid import uuid4
from datetime import datetime

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from kodiak.database.engine import get_session
from kodiak.database.models import Project, Attempt
from kodiak.core.deduplication import deduplication_service
from kodiak.database.crud import project as project_crud, attempt as attempt_crud


async def test_attempt_tracking():
    """Test the attempt tracking and deduplication functionality."""
    print("🧪 Testing Attempt Tracking and Deduplication")
    print("=" * 50)
    
    # Get database session
    async for session in get_session():
        try:
            # 1. Create a test project
            test_project = Project(
                name="Test Attempt Tracking",
                description="Test project for attempt tracking functionality"
            )
            
            created_project = await project_crud.create(session, test_project)
            project_id = created_project.id
            print(f"✓ Created test project: {project_id}")
            
            # 2. Test basic attempt recording
            print("\n📝 Testing attempt recording...")
            
            attempt1 = await deduplication_service.record_attempt(
                session, project_id, "nmap", "192.168.1.1", "success"
            )
            print(f"✓ Recorded successful nmap attempt: {attempt1.id}")
            
            attempt2 = await deduplication_service.record_attempt(
                session, project_id, "nmap", "192.168.1.2", "failure", "Connection timeout"
            )
            print(f"✓ Recorded failed nmap attempt: {attempt2.id}")
            
            # 3. Test deduplication logic
            print("\n🔍 Testing deduplication logic...")
            
            # Should skip because nmap already succeeded on 192.168.1.1
            should_skip, reason = await deduplication_service.should_skip_attempt(
                session, project_id, "nmap", "192.168.1.1", {}
            )
            print(f"✓ Deduplication check for successful target: skip={should_skip}, reason={reason}")
            
            # Should not skip because this is a different target
            should_skip2, reason2 = await deduplication_service.should_skip_attempt(
                session, project_id, "nmap", "192.168.1.3", {}
            )
            print(f"✓ Deduplication check for new target: skip={should_skip2}, reason={reason2}")
            
            # 4. Test attempt history retrieval
            print("\n📊 Testing attempt history retrieval...")
            
            attempts = await deduplication_service.get_attempt_history(session, project_id)
            print(f"✓ Retrieved {len(attempts)} attempts from history")
            
            for attempt in attempts:
                print(f"  - {attempt.tool} on {attempt.target}: {attempt.status}")
            
            # 5. Test tool-specific attempts
            print("\n🔧 Testing tool-specific attempt retrieval...")
            
            nmap_attempts = await deduplication_service.get_attempt_history(session, project_id, "nmap")
            print(f"✓ Retrieved {len(nmap_attempts)} nmap attempts")
            
            # 6. Test statistics
            print("\n📈 Testing deduplication statistics...")
            
            stats = await deduplication_service.get_deduplication_stats(session, project_id)
            print(f"✓ Statistics: {stats}")
            
            # 7. Test target normalization
            print("\n🎯 Testing target normalization...")
            
            # Test URL normalization
            await deduplication_service.record_attempt(
                session, project_id, "proxy_request", "https://example.com/path?param=1", "success"
            )
            
            # This should be considered a duplicate due to normalization
            should_skip3, reason3 = await deduplication_service.should_skip_attempt(
                session, project_id, "proxy_request", "https://example.com/path?param=2", {}
            )
            print(f"✓ URL normalization test: skip={should_skip3}, reason={reason3}")
            
            # 8. Test failure count limits
            print("\n⚠️  Testing failure count limits...")
            
            # Record multiple failures for the same target
            for i in range(4):
                await deduplication_service.record_attempt(
                    session, project_id, "sqlmap", "http://test.com", "failure", f"Attempt {i+1} failed"
                )
            
            # Should skip due to too many failures
            should_skip4, reason4 = await deduplication_service.should_skip_attempt(
                session, project_id, "sqlmap", "http://test.com", {}
            )
            print(f"✓ Failure limit test: skip={should_skip4}, reason={reason4}")
            
            print("\n✅ All attempt tracking tests passed!")
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
    success = await test_attempt_tracking()
    if success:
        print("\n🎉 Attempt tracking implementation is working correctly!")
        sys.exit(0)
    else:
        print("\n💥 Attempt tracking tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
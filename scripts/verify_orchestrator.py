import asyncio
import os
import sys

# Ensure backend definitions are loaded
# sys.path hacking removed - run via poetry run python ...

from kodiak.database import init_db, get_session
from kodiak.database.models import Project, ScanJob, ScanStatus
from kodiak.core.orchestrator import orchestrator
from kodiak.core.tools.inventory import inventory
from kodiak.core.tools.definitions.network import NmapTool

# Register Nmap manually if not imported by default logic yet
inventory.register(NmapTool())

async def main():
    print("--- Starting Orchestrator Verification ---")
    
    # 1. Initialize DB
    await init_db()
    
    # 2. Create Data
    async for session in get_session():
        # Create Project
        project = Project(name="Verification Project")
        session.add(project)
        await session.commit()
        await session.refresh(project)
        
        # Create ScanJob
        scan = ScanJob(
            project_id=project.id,
            name="Orchestrator Test Scan",
            status=ScanStatus.PENDING,
            config={"target": "scanme.nmap.org"}
        )
        session.add(scan)
        await session.commit()
        await session.refresh(scan)
        
        scan_id = scan.id
        print(f"Created ScanJob {scan_id} for target 'scanme.nmap.org'")
        break

    # 3. Start Orchestrator
    await orchestrator.start_scan(scan_id)
    
    # 4. Monitor Loop
    # The orchestrator loop currently sets status to COMPLETED after one run
    print("Monitoring scan status...")
    for _ in range(20): # Wait up to 20s
        await asyncio.sleep(1)
        async for session in get_session():
            scan = await session.get(ScanJob, scan_id)
            print(f"Current Status: {scan.status}")
            if scan.status == ScanStatus.COMPLETED:
                print("Scan completed successfully!")
                return
            if scan.status == ScanStatus.FAILED:
                print("Scan failed!")
                return
                
    print("Timed out waiting for scan completion.")

if __name__ == "__main__":
    # Ensure Nmap is in path for this test
    os.environ["PATH"] += r";C:\Program Files (x86)\Nmap"
    
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main())

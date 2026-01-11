from typing import List, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel.ext.asyncio.session import AsyncSession
from pydantic import BaseModel, Field

from kodiak.database import get_session
from kodiak.database.crud import scan_job as crud_scan, project as crud_project
from kodiak.database.models import ScanJob, ScanStatus

router = APIRouter()


class ScanCreateRequest(BaseModel):
    """Request model for creating a new scan"""
    project_id: UUID = Field(..., description="ID of the project this scan belongs to")
    name: str = Field(..., description="Name of the scan")
    config: Dict[str, Any] = Field(default_factory=dict, description="Scan configuration including target, instructions, etc.")


class ScanResponse(BaseModel):
    """Response model for scan operations"""
    id: UUID
    project_id: UUID
    name: str
    status: str
    config: Dict[str, Any]
    created_at: str
    updated_at: str


class ScanStartResponse(BaseModel):
    """Response model for scan start operation"""
    message: str
    scan_id: UUID
    status: str
    root_task_created: bool


class ScanStopResponse(BaseModel):
    """Response model for scan stop operation"""
    message: str
    scan_id: UUID
    status: str
    cancelled_workers: int


@router.post("/", response_model=ScanResponse)
async def create_scan(
    scan_request: ScanCreateRequest, 
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new scan job with proper validation.
    """
    # Validate that the project exists
    project = await crud_project.get(session, scan_request.project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Validate scan configuration
    config = scan_request.config
    if not config.get("target"):
        raise HTTPException(status_code=400, detail="Scan configuration must include a 'target'")
    
    # Set default values for missing configuration
    if "instructions" not in config:
        config["instructions"] = "Conduct a comprehensive security assessment of the target."
    
    # Create the scan job
    scan = ScanJob(
        project_id=scan_request.project_id,
        name=scan_request.name,
        status=ScanStatus.PENDING,
        config=config
    )
    
    created_scan = await crud_scan.create(session, scan)
    
    return ScanResponse(
        id=created_scan.id,
        project_id=created_scan.project_id,
        name=created_scan.name,
        status=created_scan.status,
        config=created_scan.config,
        created_at=created_scan.created_at.isoformat(),
        updated_at=created_scan.updated_at.isoformat()
    )


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: UUID, 
    session: AsyncSession = Depends(get_session)
):
    """
    Get scan details by ID.
    """
    scan = await crud_scan.get(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    return ScanResponse(
        id=scan.id,
        project_id=scan.project_id,
        name=scan.name,
        status=scan.status,
        config=scan.config,
        created_at=scan.created_at.isoformat(),
        updated_at=scan.updated_at.isoformat()
    )


@router.post("/{scan_id}/start", response_model=ScanStartResponse)
async def start_scan(
    scan_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Start or Resume a scan by creating a root task and triggering the orchestrator.
    """
    # Validate scan exists
    scan = await crud_scan.get(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Check if scan is already running
    if scan.status == ScanStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Scan is already running")
    
    # Validate scan configuration
    if not scan.config.get("target"):
        raise HTTPException(status_code=400, detail="Scan configuration missing required 'target' field")
    
    # Get orchestrator from app state
    orchestrator = getattr(request.app.state, 'orchestrator', None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not available")
    
    # Get event manager for broadcasting
    event_manager = getattr(request.app.state, 'event_manager', None)
    
    try:
        # Trigger Orchestrator to start the scan
        await orchestrator.start_scan(scan_id)
        
        # Refresh scan to get updated status
        await session.refresh(scan)
        
        # Emit scan started event
        if event_manager:
            await event_manager.emit_scan_started(
                scan_id=str(scan_id),
                scan_name=scan.name,
                target=scan.config.get("target"),
                agent_id=f"manager-{scan_id}"
            )
        
        return ScanStartResponse(
            message="Scan started successfully",
            scan_id=scan_id,
            status=scan.status,
            root_task_created=True
        )
        
    except Exception as e:
        # If scan start fails, ensure scan status is not left in running state
        await crud_scan.update_status(session, scan_id, ScanStatus.FAILED)
        
        # Emit scan failed event
        if event_manager:
            await event_manager.emit_scan_failed(
                scan_id=str(scan_id),
                scan_name=scan.name,
                error=str(e),
                details={"operation": "start_scan", "target": scan.config.get("target")}
            )
        
        raise HTTPException(status_code=500, detail=f"Failed to start scan: {str(e)}")


@router.post("/{scan_id}/stop", response_model=ScanStopResponse)
async def stop_scan(
    scan_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """
    Stop/Pause a scan by cancelling workers and updating scan status.
    """
    # Validate scan exists
    scan = await crud_scan.get(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Check if scan is actually running
    if scan.status not in [ScanStatus.RUNNING, ScanStatus.PENDING]:
        raise HTTPException(status_code=400, detail=f"Cannot stop scan with status: {scan.status}")
    
    # Get orchestrator from app state
    orchestrator = getattr(request.app.state, 'orchestrator', None)
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator not available")
    
    # Get event manager for broadcasting
    event_manager = getattr(request.app.state, 'event_manager', None)
    
    try:
        # Stop the scan through orchestrator
        cancelled_count = await orchestrator.stop_scan(scan_id)
        
        # Refresh scan to get updated status
        await session.refresh(scan)
        
        # Emit scan completed event (stopped by user)
        if event_manager:
            await event_manager.emit_scan_completed(
                scan_id=str(scan_id),
                scan_name=scan.name,
                status="stopped",
                summary={
                    "cancelled_workers": cancelled_count or 0,
                    "stopped_by": "user",
                    "reason": "Manual stop requested"
                }
            )
        
        return ScanStopResponse(
            message="Scan stopped successfully",
            scan_id=scan_id,
            status=scan.status,
            cancelled_workers=cancelled_count or 0
        )
        
    except Exception as e:
        # Emit scan failed event if stop operation fails
        if event_manager:
            await event_manager.emit_scan_failed(
                scan_id=str(scan_id),
                scan_name=scan.name,
                error=f"Failed to stop scan: {str(e)}",
                details={"operation": "stop_scan", "cancelled_workers": 0}
            )
        
        raise HTTPException(status_code=500, detail=f"Failed to stop scan: {str(e)}")


@router.get("/{scan_id}/status")
async def get_scan_status(
    scan_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Get detailed scan status including associated tasks.
    """
    from kodiak.database.models import Task
    from sqlmodel import select
    
    # Get scan
    scan = await crud_scan.get(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Get associated tasks
    statement = select(Task).where(Task.project_id == scan.project_id)
    result = await session.execute(statement)
    tasks = result.scalars().all()
    
    # Count tasks by status
    task_counts = {}
    for task in tasks:
        task_counts[task.status] = task_counts.get(task.status, 0) + 1
    
    return {
        "scan_id": scan.id,
        "scan_name": scan.name,
        "scan_status": scan.status,
        "project_id": scan.project_id,
        "target": scan.config.get("target"),
        "created_at": scan.created_at.isoformat(),
        "updated_at": scan.updated_at.isoformat(),
        "task_summary": {
            "total_tasks": len(tasks),
            "by_status": task_counts
        },
        "tasks": [
            {
                "id": str(task.id),
                "name": task.name,
                "status": task.status,
                "assigned_agent_id": task.assigned_agent_id,
                "created_at": task.created_at.isoformat()
            }
            for task in tasks
        ]
    }


@router.get("/", response_model=List[ScanResponse])
async def list_scans(
    project_id: UUID = None,
    session: AsyncSession = Depends(get_session)
):
    """
    List all scans, optionally filtered by project.
    """
    from sqlmodel import select
    
    if project_id:
        # Validate project exists
        project = await crud_project.get(session, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Get scans for specific project
        statement = select(ScanJob).where(ScanJob.project_id == project_id)
    else:
        # Get all scans
        statement = select(ScanJob)
    
    result = await session.execute(statement)
    scans = result.scalars().all()
    
    return [
        ScanResponse(
            id=scan.id,
            project_id=scan.project_id,
            name=scan.name,
            status=scan.status,
            config=scan.config,
            created_at=scan.created_at.isoformat(),
            updated_at=scan.updated_at.isoformat()
        )
        for scan in scans
    ]

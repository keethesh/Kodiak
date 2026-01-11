from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from kodiak.core.orchestrator import orchestrator
from kodiak.database import get_session
from kodiak.database.crud import scan_job as crud_scan
from kodiak.database.models import ScanJob

router = APIRouter()

@router.post("/", response_model=ScanJob)
async def create_scan(
    scan: ScanJob, 
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new scan job.
    """
    return await crud_scan.create(session, scan)

@router.get("/{scan_id}", response_model=ScanJob)
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
    return scan

@router.post("/{scan_id}/start")
async def start_scan(
    scan_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Start or Resume a scan.
    """
    scan = await crud_scan.get(session, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    
    # Trigger Orchestrator
    await orchestrator.start_scan(scan_id)
    return {"message": "Scan started", "scan_id": scan_id}

@router.post("/{scan_id}/stop")
async def stop_scan(
    scan_id: UUID,
):
    """
    Pause/Stop a scan.
    """
    await orchestrator.stop_scan(scan_id)
    return {"message": "Scan stopped", "scan_id": scan_id}

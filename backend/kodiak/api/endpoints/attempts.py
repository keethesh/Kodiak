"""
API endpoints for attempt tracking and deduplication management.
"""

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from kodiak.database.engine import get_session
from kodiak.database.models import Attempt
from kodiak.core.deduplication import deduplication_service

router = APIRouter()


@router.get("/projects/{project_id}/attempts", response_model=List[dict])
async def get_project_attempts(
    project_id: UUID,
    tool: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """
    Get attempt history for a project.
    
    Args:
        project_id: Project UUID
        tool: Optional tool filter
        limit: Maximum number of attempts to return (default: 50, max: 200)
        
    Returns:
        List of attempt records with metadata
    """
    try:
        # Limit the maximum number of attempts that can be requested
        limit = min(limit, 200)
        
        attempts = await deduplication_service.get_attempt_history(
            session, project_id, tool, limit
        )
        
        # Convert to dict format for API response
        attempt_dicts = []
        for attempt in attempts:
            attempt_dict = {
                "id": str(attempt.id),
                "project_id": str(attempt.project_id),
                "tool": attempt.tool,
                "target": attempt.target,
                "status": attempt.status,
                "reason": attempt.reason,
                "timestamp": attempt.timestamp.isoformat()
            }
            attempt_dicts.append(attempt_dict)
        
        return attempt_dicts
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get attempts: {str(e)}")


@router.get("/projects/{project_id}/attempts/stats")
async def get_deduplication_stats(
    project_id: UUID,
    session: AsyncSession = Depends(get_session)
):
    """
    Get deduplication statistics for a project.
    
    Args:
        project_id: Project UUID
        
    Returns:
        Dictionary with deduplication statistics and metrics
    """
    try:
        stats = await deduplication_service.get_deduplication_stats(session, project_id)
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.post("/projects/{project_id}/attempts/check-duplicate")
async def check_duplicate_attempt(
    project_id: UUID,
    tool: str,
    target: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Check if an attempt would be considered a duplicate.
    
    Args:
        project_id: Project UUID
        tool: Tool name
        target: Target identifier
        
    Returns:
        Dictionary indicating if the attempt should be skipped and why
    """
    try:
        should_skip, reason = await deduplication_service.should_skip_attempt(
            session, project_id, tool, target, {}
        )
        
        return {
            "should_skip": should_skip,
            "reason": reason,
            "tool": tool,
            "target": target
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check duplicate: {str(e)}")


@router.get("/projects/{project_id}/attempts/tools/{tool}")
async def get_tool_attempts(
    project_id: UUID,
    tool: str,
    limit: int = 20,
    session: AsyncSession = Depends(get_session)
):
    """
    Get attempt history for a specific tool within a project.
    
    Args:
        project_id: Project UUID
        tool: Tool name
        limit: Maximum number of attempts to return (default: 20, max: 100)
        
    Returns:
        List of attempt records for the specified tool
    """
    try:
        # Limit the maximum number of attempts that can be requested
        limit = min(limit, 100)
        
        attempts = await deduplication_service.get_attempt_history(
            session, project_id, tool, limit
        )
        
        # Convert to dict format for API response
        attempt_dicts = []
        for attempt in attempts:
            attempt_dict = {
                "id": str(attempt.id),
                "project_id": str(attempt.project_id),
                "tool": attempt.tool,
                "target": attempt.target,
                "status": attempt.status,
                "reason": attempt.reason,
                "timestamp": attempt.timestamp.isoformat()
            }
            attempt_dicts.append(attempt_dict)
        
        return attempt_dicts
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get tool attempts: {str(e)}")
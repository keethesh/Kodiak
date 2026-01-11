from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from pydantic import BaseModel, Field

from kodiak.database import get_session
from kodiak.database.models import Project
from kodiak.database.crud import project as crud_project

router = APIRouter()


class ProjectCreateRequest(BaseModel):
    """Request model for creating a new project"""
    name: str = Field(..., description="Name of the project")
    description: str = Field(None, description="Optional description of the project")


class ProjectResponse(BaseModel):
    """Response model for project operations"""
    id: UUID
    name: str
    description: str = None
    created_at: str


@router.get("/", response_model=List[ProjectResponse])
async def list_projects(session: AsyncSession = Depends(get_session)):
    """
    List all active projects.
    """
    projects = await crud_project.get_all(session)
    return [
        ProjectResponse(
            id=project.id,
            name=project.name,
            description=project.description,
            created_at=project.created_at.isoformat()
        )
        for project in projects
    ]


@router.post("/", response_model=ProjectResponse)
async def create_project(
    project_request: ProjectCreateRequest, 
    session: AsyncSession = Depends(get_session)
):
    """
    Create a new project with proper validation.
    """
    # Validate project name is not empty
    if not project_request.name.strip():
        raise HTTPException(status_code=400, detail="Project name cannot be empty")
    
    # Create the project
    project = Project(
        name=project_request.name.strip(),
        description=project_request.description
    )
    
    created_project = await crud_project.create(session, project)
    
    return ProjectResponse(
        id=created_project.id,
        name=created_project.name,
        description=created_project.description,
        created_at=created_project.created_at.isoformat()
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: UUID, session: AsyncSession = Depends(get_session)):
    """
    Get project details by ID.
    """
    project = await crud_project.get(session, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat()
    )

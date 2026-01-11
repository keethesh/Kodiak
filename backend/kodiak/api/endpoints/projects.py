from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select

from kodiak.database import get_session
from kodiak.database.models import Project

router = APIRouter()

@router.get("/", response_model=List[Project])
async def list_projects(session: AsyncSession = Depends(get_session)):
    """
    List all active projects.
    """
    stmt = select(Project)
    projects = (await session.execute(stmt)).scalars().all()
    return projects

@router.post("/", response_model=Project)
async def create_project(project: Project, session: AsyncSession = Depends(get_session)):
    """
    Create a new engagement.
    If description is not provided, it defaults to None.
    """
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project

@router.get("/{project_id}", response_model=Project)
async def get_project(project_id: UUID, session: AsyncSession = Depends(get_session)):
    stmt = select(Project).where(Project.id == project_id)
    project = (await session.execute(stmt)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project

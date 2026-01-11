from uuid import UUID
from typing import Optional, List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from kodiak.database.models import Project, ScanJob, Asset, Finding, ScanStatus


class CRUDProject:
    async def create(self, session: AsyncSession, project: Project) -> Project:
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def get(self, session: AsyncSession, project_id: UUID) -> Optional[Project]:
        statement = select(Project).where(Project.id == project_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()
    
    async def get_all(self, session: AsyncSession) -> Sequence[Project]:
        statement = select(Project)
        result = await session.execute(statement)
        return result.scalars().all()


class CRUDScanJob:
    async def create(self, session: AsyncSession, scan: ScanJob) -> ScanJob:
        session.add(scan)
        await session.commit()
        await session.refresh(scan)
        return scan

    async def get(self, session: AsyncSession, scan_id: UUID) -> Optional[ScanJob]:
        statement = select(ScanJob).where(ScanJob.id == scan_id)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def update_status(self, session: AsyncSession, scan_id: UUID, status: str) -> Optional[ScanJob]:
        scan = await self.get(session, scan_id)
        if not scan:
            return None
        scan.status = status
        session.add(scan)
        await session.commit()
        await session.refresh(scan)
        return scan

class CRUDAsset:
    async def create(self, session: AsyncSession, asset: Asset) -> Asset:
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        return asset

project = CRUDProject()
scan_job = CRUDScanJob()
asset = CRUDAsset()

from uuid import UUID
from typing import Optional, List, Sequence, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from kodiak.database.models import Project, ScanJob, Node, Finding, ScanStatus
from kodiak.core.error_handling import (
    ErrorHandler, DatabaseError, handle_errors, ErrorCategory
)


class CRUDProject:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, project: Project) -> Project:
        try:
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return project
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_project", e, {
                "project_name": getattr(project, 'name', 'unknown')
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get(self, session: AsyncSession, project_id: UUID) -> Optional[Project]:
        try:
            statement = select(Project).where(Project.id == project_id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_project", e, {
                "project_id": str(project_id)
            })
    
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_all(self, session: AsyncSession) -> Sequence[Project]:
        try:
            statement = select(Project)
            result = await session.execute(statement)
            return result.scalars().all()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_all_projects", e)


class CRUDScanJob:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, scan: ScanJob) -> ScanJob:
        try:
            session.add(scan)
            await session.commit()
            await session.refresh(scan)
            return scan
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_scan_job", e, {
                "scan_name": getattr(scan, 'name', 'unknown'),
                "project_id": str(getattr(scan, 'project_id', 'unknown'))
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get(self, session: AsyncSession, scan_id: UUID) -> Optional[ScanJob]:
        try:
            statement = select(ScanJob).where(ScanJob.id == scan_id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_scan_job", e, {
                "scan_id": str(scan_id)
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def update_status(self, session: AsyncSession, scan_id: UUID, status: str) -> Optional[ScanJob]:
        try:
            scan = await self.get(session, scan_id)
            if not scan:
                return None
            scan.status = status
            session.add(scan)
            await session.commit()
            await session.refresh(scan)
            return scan
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("update_scan_status", e, {
                "scan_id": str(scan_id),
                "new_status": status
            })


class CRUDNode:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, node: Node) -> Node:
        """Create a new node (asset) in the database"""
        try:
            session.add(node)
            await session.commit()
            await session.refresh(node)
            return node
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_node", e, {
                "node_name": getattr(node, 'name', 'unknown'),
                "node_type": getattr(node, 'type', 'unknown'),
                "project_id": str(getattr(node, 'project_id', 'unknown'))
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get(self, session: AsyncSession, node_id: UUID) -> Optional[Node]:
        """Get a node by ID"""
        try:
            statement = select(Node).where(Node.id == node_id)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_node", e, {
                "node_id": str(node_id)
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_nodes_by_project(self, session: AsyncSession, project_id: UUID) -> List[Node]:
        """Get all nodes for a project"""
        try:
            statement = select(Node).where(Node.project_id == project_id)
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_nodes_by_project", e, {
                "project_id": str(project_id)
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_name_and_type(self, session: AsyncSession, project_id: UUID, name: str, node_type: str) -> Optional[Node]:
        """Get a node by name and type within a project"""
        try:
            statement = select(Node).where(
                Node.project_id == project_id,
                Node.name == name,
                Node.type == node_type
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_node_by_name_and_type", e, {
                "project_id": str(project_id),
                "name": name,
                "type": node_type
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def update_node(self, session: AsyncSession, node_id: UUID, updates: Dict[str, Any]) -> Optional[Node]:
        """Update an existing node"""
        try:
            node = await self.get(session, node_id)
            if not node:
                return None
            
            for key, value in updates.items():
                if hasattr(node, key):
                    setattr(node, key, value)
            
            session.add(node)
            await session.commit()
            await session.refresh(node)
            return node
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("update_node", e, {
                "node_id": str(node_id),
                "updates": updates
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def mark_scanned(self, session: AsyncSession, node_id: UUID) -> Optional[Node]:
        """Mark a node as scanned"""
        return await self.update_node(session, node_id, {"scanned": True})

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_unscanned_nodes(self, session: AsyncSession, project_id: UUID) -> List[Node]:
        """Get all unscanned nodes for a project"""
        try:
            statement = select(Node).where(
                Node.project_id == project_id,
                Node.scanned == False
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_unscanned_nodes", e, {
                "project_id": str(project_id)
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def delete(self, session: AsyncSession, node_id: UUID) -> bool:
        """Delete a node"""
        try:
            node = await self.get(session, node_id)
            if not node:
                return False
            
            await session.delete(node)
            await session.commit()
            return True
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("delete_node", e, {
                "node_id": str(node_id)
            })


project = CRUDProject()
scan_job = CRUDScanJob()
node = CRUDNode()

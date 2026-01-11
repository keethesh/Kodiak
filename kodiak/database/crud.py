from uuid import UUID
from typing import Optional, List, Sequence, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from kodiak.database.models import Project, ScanJob, Node, Finding, ScanStatus, Attempt
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


class CRUDAttempt:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, attempt: Attempt) -> Attempt:
        """Create a new attempt record"""
        try:
            session.add(attempt)
            await session.commit()
            await session.refresh(attempt)
            return attempt
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_attempt", e, {
                "tool": getattr(attempt, 'tool', 'unknown'),
                "target": getattr(attempt, 'target', 'unknown'),
                "project_id": str(getattr(attempt, 'project_id', 'unknown'))
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_tool_and_target(self, session: AsyncSession, project_id: UUID, tool: str, target: str) -> Optional[Attempt]:
        """Get an attempt by tool and target within a project"""
        try:
            statement = select(Attempt).where(
                Attempt.project_id == project_id,
                Attempt.tool == tool,
                Attempt.target == target
            ).order_by(Attempt.timestamp.desc())
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_attempt_by_tool_and_target", e, {
                "project_id": str(project_id),
                "tool": tool,
                "target": target
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_attempts_by_project(self, session: AsyncSession, project_id: UUID, limit: int = 50) -> List[Attempt]:
        """Get recent attempts for a project"""
        try:
            statement = select(Attempt).where(
                Attempt.project_id == project_id
            ).order_by(Attempt.timestamp.desc()).limit(limit)
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_attempts_by_project", e, {
                "project_id": str(project_id),
                "limit": limit
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_attempts_by_tool(self, session: AsyncSession, project_id: UUID, tool: str, limit: int = 20) -> List[Attempt]:
        """Get recent attempts for a specific tool within a project"""
        try:
            statement = select(Attempt).where(
                Attempt.project_id == project_id,
                Attempt.tool == tool
            ).order_by(Attempt.timestamp.desc()).limit(limit)
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_attempts_by_tool", e, {
                "project_id": str(project_id),
                "tool": tool,
                "limit": limit
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def check_duplicate_attempt(self, session: AsyncSession, project_id: UUID, tool: str, target: str) -> bool:
        """Check if a successful attempt already exists for this tool and target"""
        try:
            statement = select(Attempt).where(
                Attempt.project_id == project_id,
                Attempt.tool == tool,
                Attempt.target == target,
                Attempt.status == "success"
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none() is not None
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("check_duplicate_attempt", e, {
                "project_id": str(project_id),
                "tool": tool,
                "target": target
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def count_failed_attempts(self, session: AsyncSession, project_id: UUID, tool: str, target: str) -> int:
        """Count failed attempts for a specific tool and target"""
        try:
            from sqlalchemy import func
            statement = select(func.count(Attempt.id)).where(
                Attempt.project_id == project_id,
                Attempt.tool == tool,
                Attempt.target == target,
                Attempt.status == "failure"
            )
            result = await session.execute(statement)
            return result.scalar() or 0
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("count_failed_attempts", e, {
                "project_id": str(project_id),
                "tool": tool,
                "target": target
            })


project = CRUDProject()
scan_job = CRUDScanJob()
node = CRUDNode()
attempt = CRUDAttempt()

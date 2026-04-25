from uuid import UUID
from typing import Optional, List, Sequence, Dict, Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from kodiak.database.models import (
    Project,
    ScanJob,
    Node,
    Finding,
    Attempt,
    InsightMemory,
    VerificationQueue,
    VerificationQueueStatus,
    EngagementNote,
)
from kodiak.core.error_handling import (
    ErrorHandler, handle_errors, ErrorCategory
)


async def _safe_rollback(session: AsyncSession) -> None:
    """Attempt a session rollback, silently swallowing any error.

    When a commit() is interrupted mid-flight (e.g. SQLite busy or an
    async-cancellation), SQLAlchemy leaves the session in _prepare_impl()
    or a CLOSED transaction state.  Calling rollback() in that state raises
    another exception which (a) masks the original error and (b) prevents
    the subsequent `raise` from executing, leaving callers without the real
    error message and the session permanently broken.  Wrapping every
    rollback call with this helper ensures the original exception always
    propagates cleanly.
    """
    try:
        await session.rollback()
    except Exception:
        pass


class CRUDProject:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, project: Project) -> Project:
        try:
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return project
        except SQLAlchemyError as e:
            await _safe_rollback(session)
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

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_name(self, session: AsyncSession, name: str) -> Optional[Project]:
        try:
            statement = select(Project).where(Project.name == name)
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_project_by_name", e, {
                "project_name": name
            })


class CRUDScanJob:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, scan: ScanJob) -> ScanJob:
        try:
            session.add(scan)
            await session.commit()
            await session.refresh(scan)
            return scan
        except SQLAlchemyError as e:
            await _safe_rollback(session)
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
    async def get_all(self, session: AsyncSession) -> Sequence[ScanJob]:
        try:
            statement = select(ScanJob).order_by(ScanJob.created_at.desc())
            result = await session.execute(statement)
            return result.scalars().all()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_all_scan_jobs", e)

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_project_id(self, session: AsyncSession, project_id: UUID) -> Sequence[ScanJob]:
        try:
            statement = (
                select(ScanJob)
                .where(ScanJob.project_id == project_id)
                .order_by(ScanJob.created_at.desc())
            )
            result = await session.execute(statement)
            return result.scalars().all()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_scan_jobs_by_project_id", e, {
                "project_id": str(project_id),
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
            await _safe_rollback(session)
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
            await _safe_rollback(session)
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
            await _safe_rollback(session)
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
                Node.scanned.is_(False)
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
            await _safe_rollback(session)
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
            await _safe_rollback(session)
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
            ).order_by(Attempt.created_at.desc())
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
            ).order_by(Attempt.created_at.desc()).limit(limit)
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_attempts_by_project", e, {
                "project_id": str(project_id),
                "limit": limit
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_attempts_by_scan(self, session: AsyncSession, scan_id: UUID, limit: int = 200) -> List[Attempt]:
        """Get recent attempts for a scan across all agents."""
        try:
            statement = (
                select(Attempt)
                .where(Attempt.scan_id == scan_id)
                .order_by(Attempt.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_attempts_by_scan", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_attempts_by_tool(self, session: AsyncSession, project_id: UUID, tool: str, limit: int = 20) -> List[Attempt]:
        """Get recent attempts for a specific tool within a project"""
        try:
            statement = select(Attempt).where(
                Attempt.project_id == project_id,
                Attempt.tool == tool
            ).order_by(Attempt.created_at.desc()).limit(limit)
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


class CRUDInsightMemory:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, memory: InsightMemory) -> InsightMemory:
        try:
            session.add(memory)
            await session.commit()
            await session.refresh(memory)
            return memory
        except SQLAlchemyError as e:
            await _safe_rollback(session)
            raise ErrorHandler.handle_database_error("create_insight_memory", e, {
                "project_id": str(getattr(memory, "project_id", "unknown")),
                "scan_id": str(getattr(memory, "scan_id", "unknown")),
                "tool": getattr(memory, "tool", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_by_scan(self, session: AsyncSession, scan_id: UUID, limit: int = 50) -> List[InsightMemory]:
        try:
            statement = (
                select(InsightMemory)
                .where(InsightMemory.scan_id == scan_id)
                .order_by(InsightMemory.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_insight_memory_by_scan", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def find_by_fingerprint(self, session: AsyncSession, scan_id: UUID, fingerprint: str) -> Optional[InsightMemory]:
        try:
            statement = (
                select(InsightMemory)
                .where(
                    InsightMemory.scan_id == scan_id,
                    InsightMemory.fingerprint == fingerprint
                )
                .order_by(InsightMemory.created_at.desc())
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("find_insight_memory_by_fingerprint", e, {
                "scan_id": str(scan_id),
                "fingerprint": fingerprint,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_do_not_repeat(self, session: AsyncSession, scan_id: UUID, limit: int = 50) -> List[InsightMemory]:
        try:
            statement = (
                select(InsightMemory)
                .where(InsightMemory.scan_id == scan_id)
                .order_by(InsightMemory.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            records = list(result.scalars().all())
            return [r for r in records if (r.insight or {}).get("do_not_repeat")]
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_insight_memory_do_not_repeat", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })



class CRUDVerificationQueue:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, item: VerificationQueue) -> VerificationQueue:
        try:
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return item
        except SQLAlchemyError as e:
            await _safe_rollback(session)
            raise ErrorHandler.handle_database_error("create_verification_queue_item", e, {
                "scan_id": str(getattr(item, "scan_id", "unknown")),
                "entity_type": getattr(item, "entity_type", "unknown"),
                "entity_key": getattr(item, "entity_key", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def find_pending(
        self,
        session: AsyncSession,
        scan_id: UUID,
        entity_type: str,
        entity_key: str,
    ) -> Optional[VerificationQueue]:
        try:
            statement = (
                select(VerificationQueue)
                .where(
                    VerificationQueue.scan_id == scan_id,
                    VerificationQueue.entity_type == entity_type,
                    VerificationQueue.entity_key == entity_key,
                    VerificationQueue.status == VerificationQueueStatus.PENDING,
                )
                .order_by(VerificationQueue.created_at.desc())
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("find_pending_verification_item", e, {
                "scan_id": str(scan_id),
                "entity_type": entity_type,
                "entity_key": entity_key,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_pending_by_scan(
        self,
        session: AsyncSession,
        scan_id: UUID,
        limit: int = 50,
    ) -> List[VerificationQueue]:
        try:
            statement = (
                select(VerificationQueue)
                .where(
                    VerificationQueue.scan_id == scan_id,
                    VerificationQueue.status == VerificationQueueStatus.PENDING,
                )
                .order_by(VerificationQueue.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_pending_verification_items", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def resolve(
        self,
        session: AsyncSession,
        item_id: UUID,
        status: VerificationQueueStatus = VerificationQueueStatus.RESOLVED,
    ) -> Optional[VerificationQueue]:
        try:
            statement = select(VerificationQueue).where(VerificationQueue.id == item_id)
            result = await session.execute(statement)
            item = result.scalar_one_or_none()
            if not item:
                return None
            item.status = status
            item.resolved_at = datetime.now(timezone.utc)
            session.add(item)
            await session.commit()
            await session.refresh(item)
            return item
        except SQLAlchemyError as e:
            await _safe_rollback(session)
            raise ErrorHandler.handle_database_error("resolve_verification_item", e, {
                "item_id": str(item_id),
                "status": str(status),
            })


class CRUDEngagementNote:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, note: EngagementNote) -> EngagementNote:
        try:
            session.add(note)
            await session.commit()
            await session.refresh(note)
            return note
        except SQLAlchemyError as e:
            await _safe_rollback(session)
            raise ErrorHandler.handle_database_error("create_engagement_note", e, {
                "project_id": str(getattr(note, "project_id", "unknown")),
                "category": str(getattr(note, "category", "unknown")),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_for_project(
        self, session: AsyncSession, project_id: UUID, limit: int = 100
    ) -> List[EngagementNote]:
        try:
            statement = (
                select(EngagementNote)
                .where(EngagementNote.project_id == project_id)
                .order_by(EngagementNote.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_engagement_notes", e, {
                "project_id": str(project_id),
                "limit": limit,
            })


class CRUDFinding:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, finding: Finding) -> Finding:
        try:
            session.add(finding)
            await session.commit()
            await session.refresh(finding)
            return finding
        except SQLAlchemyError as e:
            await _safe_rollback(session)
            raise ErrorHandler.handle_database_error("create_finding", e, {
                "project_id": str(getattr(finding, "project_id", "unknown")),
                "title": getattr(finding, "title", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_for_project(
        self, session: AsyncSession, project_id: UUID, limit: int = 50
    ) -> List[Finding]:
        try:
            statement = (
                select(Finding)
                .where(Finding.project_id == project_id)
                .order_by(Finding.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_findings", e, {
                "project_id": str(project_id),
                "limit": limit,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def find_by_title_and_target(
        self,
        session: AsyncSession,
        project_id: UUID,
        title: str,
        target: str,
    ) -> Optional[Finding]:
        try:
            statement = (
                select(Finding)
                .where(
                    Finding.project_id == project_id,
                    Finding.title == title,
                    Finding.target == target,
                )
                .order_by(Finding.created_at.desc())
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("find_finding_by_title_target", e, {
                "project_id": str(project_id),
                "title": title,
                "target": target,
            })


project = CRUDProject()
scan_job = CRUDScanJob()
node = CRUDNode()
attempt = CRUDAttempt()
insight_memory = CRUDInsightMemory()
verification_queue = CRUDVerificationQueue()
note = CRUDEngagementNote()
finding = CRUDFinding()

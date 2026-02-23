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
    ScanStatus,
    Attempt,
    InsightMemory,
    BlackboardEvent,
    BlackboardFact,
    BlackboardEdge,
    VerificationQueue,
    VerificationQueueStatus,
)
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
            await session.rollback()
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


class CRUDBlackboardEvent:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, event: BlackboardEvent) -> BlackboardEvent:
        try:
            session.add(event)
            await session.commit()
            await session.refresh(event)
            return event
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_blackboard_event", e, {
                "project_id": str(getattr(event, "project_id", "unknown")),
                "scan_id": str(getattr(event, "scan_id", "unknown")),
                "entity_type": getattr(event, "entity_type", "unknown"),
                "entity_key": getattr(event, "entity_key", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_by_scan(self, session: AsyncSession, scan_id: UUID, limit: int = 100) -> List[BlackboardEvent]:
        try:
            statement = (
                select(BlackboardEvent)
                .where(BlackboardEvent.scan_id == scan_id)
                .order_by(BlackboardEvent.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_blackboard_events_by_scan", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_by_entity(
        self,
        session: AsyncSession,
        scan_id: UUID,
        entity_type: str,
        entity_key: str,
        limit: int = 50,
    ) -> List[BlackboardEvent]:
        try:
            statement = (
                select(BlackboardEvent)
                .where(
                    BlackboardEvent.scan_id == scan_id,
                    BlackboardEvent.entity_type == entity_type,
                    BlackboardEvent.entity_key == entity_key,
                )
                .order_by(BlackboardEvent.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_blackboard_events_by_entity", e, {
                "scan_id": str(scan_id),
                "entity_type": entity_type,
                "entity_key": entity_key,
                "limit": limit,
            })


class CRUDBlackboardFact:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, fact: BlackboardFact) -> BlackboardFact:
        try:
            session.add(fact)
            await session.commit()
            await session.refresh(fact)
            return fact
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_blackboard_fact", e, {
                "project_id": str(getattr(fact, "project_id", "unknown")),
                "scan_id": str(getattr(fact, "scan_id", "unknown")),
                "entity_type": getattr(fact, "entity_type", "unknown"),
                "entity_key": getattr(fact, "entity_key", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_entity(
        self,
        session: AsyncSession,
        scan_id: UUID,
        entity_type: str,
        entity_key: str,
    ) -> Optional[BlackboardFact]:
        try:
            statement = (
                select(BlackboardFact)
                .where(
                    BlackboardFact.scan_id == scan_id,
                    BlackboardFact.entity_type == entity_type,
                    BlackboardFact.entity_key == entity_key,
                )
                .order_by(BlackboardFact.updated_at.desc())
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_blackboard_fact_by_entity", e, {
                "scan_id": str(scan_id),
                "entity_type": entity_type,
                "entity_key": entity_key,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def save(self, session: AsyncSession, fact: BlackboardFact) -> BlackboardFact:
        try:
            session.add(fact)
            await session.commit()
            await session.refresh(fact)
            return fact
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("save_blackboard_fact", e, {
                "fact_id": str(getattr(fact, "id", "unknown")),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_by_scan(
        self,
        session: AsyncSession,
        scan_id: UUID,
        limit: int = 200,
        entity_types: Optional[List[str]] = None,
        verification_statuses: Optional[List[str]] = None,
    ) -> List[BlackboardFact]:
        try:
            statement = select(BlackboardFact).where(BlackboardFact.scan_id == scan_id)
            if entity_types:
                statement = statement.where(BlackboardFact.entity_type.in_(entity_types))
            if verification_statuses:
                statement = statement.where(BlackboardFact.verification_status.in_(verification_statuses))
            statement = statement.order_by(BlackboardFact.updated_at.desc()).limit(limit)
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_blackboard_facts_by_scan", e, {
                "scan_id": str(scan_id),
                "limit": limit,
            })


class CRUDBlackboardEdge:
    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def get_by_relation(
        self,
        session: AsyncSession,
        scan_id: UUID,
        src_type: str,
        src_key: str,
        relation: str,
        dst_type: str,
        dst_key: str,
    ) -> Optional[BlackboardEdge]:
        try:
            statement = (
                select(BlackboardEdge)
                .where(
                    BlackboardEdge.scan_id == scan_id,
                    BlackboardEdge.src_type == src_type,
                    BlackboardEdge.src_key == src_key,
                    BlackboardEdge.relation == relation,
                    BlackboardEdge.dst_type == dst_type,
                    BlackboardEdge.dst_key == dst_key,
                )
            )
            result = await session.execute(statement)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("get_blackboard_edge", e, {
                "scan_id": str(scan_id),
                "relation": relation,
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def create(self, session: AsyncSession, edge: BlackboardEdge) -> BlackboardEdge:
        try:
            session.add(edge)
            await session.commit()
            await session.refresh(edge)
            return edge
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("create_blackboard_edge", e, {
                "scan_id": str(getattr(edge, "scan_id", "unknown")),
                "relation": getattr(edge, "relation", "unknown"),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def save(self, session: AsyncSession, edge: BlackboardEdge) -> BlackboardEdge:
        try:
            session.add(edge)
            await session.commit()
            await session.refresh(edge)
            return edge
        except SQLAlchemyError as e:
            await session.rollback()
            raise ErrorHandler.handle_database_error("save_blackboard_edge", e, {
                "edge_id": str(getattr(edge, "id", "unknown")),
            })

    @handle_errors(ErrorCategory.DATABASE, reraise=True)
    async def list_by_scan(self, session: AsyncSession, scan_id: UUID, limit: int = 200) -> List[BlackboardEdge]:
        try:
            statement = (
                select(BlackboardEdge)
                .where(BlackboardEdge.scan_id == scan_id)
                .order_by(BlackboardEdge.updated_at.desc())
                .limit(limit)
            )
            result = await session.execute(statement)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            raise ErrorHandler.handle_database_error("list_blackboard_edges_by_scan", e, {
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
            await session.rollback()
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
            await session.rollback()
            raise ErrorHandler.handle_database_error("resolve_verification_item", e, {
                "item_id": str(item_id),
                "status": str(status),
            })


project = CRUDProject()
scan_job = CRUDScanJob()
node = CRUDNode()
attempt = CRUDAttempt()
insight_memory = CRUDInsightMemory()
blackboard_event = CRUDBlackboardEvent()
blackboard_fact = CRUDBlackboardFact()
blackboard_edge = CRUDBlackboardEdge()
verification_queue = CRUDVerificationQueue()

"""
Shared Scan Store — DB-backed state for cross-agent IPC.

All agents (Planner, Analyst, Workers) read and write through this store.
It wraps the existing DB models with atomic dedup and query helpers.
"""

from __future__ import annotations

import hashlib
import json
import shlex
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, update

from kodiak.core.config import settings
from kodiak.database.models import (
    Attempt,
    Capability,
    CapabilityType,
    Directive,
    DirectiveType,
    EngagementNote,
    Finding,
    FindingSeverity,
    Hypothesis,
    HypothesisStatus,
    HypothesisType,
    Node,
    NoteCategory,
    Observation,
    ObservationType,
    ScanEvent,
    ScanEventType,
    WorkUnit,
    WorkUnitStatus,
)


def _target_kind(target: str) -> str:
    if "://" in target:
        parsed_path = target.split("://", 1)[-1]
        return "url" if "/" in parsed_path or "?" in parsed_path else "origin"
    return "host"


def _unit_targets(unit: WorkUnit) -> List[str]:
    """Get the single target from a WorkUnit as a list (for compatibility)."""
    if unit.target:
        return [unit.target]
    return []


_SERIALIZED_TOOL_FAMILIES = settings.HEAVY_TOOLS


def _tool_family(technique: str, command_template: str = "") -> str:
    """Best-effort tool family used for concurrency-aware claiming."""
    if command_template:
        segment = command_template.rsplit("|", 1)[-1].strip()
        try:
            parts = shlex.split(segment, posix=True)
        except ValueError:
            parts = segment.split()
        if parts:
            return parts[0].lower()
    return technique.split("_", 1)[0].lower()


class DBMetrics:
    """Track database operation metrics for monitoring."""
    
    _error_counts: dict[str, int] = {}
    _operation_counts: dict[str, int] = {}
    
    @classmethod
    def record_operation(cls, operation: str) -> None:
        cls._operation_counts[operation] = cls._operation_counts.get(operation, 0) + 1
    
    @classmethod
    def record_error(cls, operation: str, error_type: str) -> None:
        cls._error_counts[f"{operation}:{error_type}"] = (
            cls._error_counts.get(f"{operation}:{error_type}", 0) + 1
        )
        if cls._error_counts.get(f"{operation}:{error_type}", 0) >= 10:
            logger.warning(
                f"DB error rate elevated for {operation}: "
                f"{cls._error_counts[f'{operation}:{error_type}']} errors"
            )
    
    @classmethod
    def get_stats(cls) -> dict:
        return {
            "operations": dict(cls._operation_counts),
            "errors": dict(cls._error_counts),
            "error_rate": (
                sum(cls._error_counts.values()) / max(sum(cls._operation_counts.values()), 1)
            ),
        }
    
    @classmethod
    def reset(cls) -> None:
        cls._error_counts.clear()
        cls._operation_counts.clear()


def _handle_db_error(operation: str, error: SQLAlchemyError, default_return: Any = None) -> Any:
    """Log and record database errors, return default value."""
    error_type = type(error).__name__
    DBMetrics.record_error(operation, error_type)
    logger.debug(f"DB error in {operation}: {error_type} - {error}")
    return default_return


async def _flush_if_available(session: AsyncSession) -> None:
    flush = getattr(session, "flush", None)
    if flush is not None:
        await flush()


class SharedScanStore:
    """
    Thread-safe, DB-backed store shared by Planner, Analyst, and Workers.

    Every method takes an AsyncSession so callers control transaction scope.
    Methods that create records handle IntegrityError silently for idempotency.
    """

    def __init__(self, project_id: UUID, scan_id: UUID):
        self.project_id = project_id
        self.scan_id = scan_id

    # ------------------------------------------------------------------
    # Scan Events
    # ------------------------------------------------------------------

    async def append_event(
        self,
        session: AsyncSession,
        *,
        event_type: ScanEventType,
        payload: Dict[str, Any],
        entity_type: str | None = None,
        entity_id: str | None = None,
        auto_commit: bool = True,
    ) -> Optional[ScanEvent]:
        """Append a normalized scan event to the event log."""
        event = ScanEvent(
            scan_id=self.scan_id,
            project_id=self.project_id,
            type=event_type,
            payload=payload,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        try:
            session.add(event)
            if auto_commit:
                await session.commit()
                await session.refresh(event)
            else:
                await _flush_if_available(session)
            DBMetrics.record_operation("append_event")
            return event
        except SQLAlchemyError as e:
            if auto_commit:
                await session.rollback()
                return _handle_db_error("append_event", e)
            raise

    async def get_events(
        self,
        session: AsyncSession,
        *,
        event_type: ScanEventType | None = None,
        limit: int = 100,
    ) -> List[ScanEvent]:
        """Fetch recent scan events."""
        try:
            stmt = select(ScanEvent).where(ScanEvent.scan_id == self.scan_id)
            if event_type is not None:
                stmt = stmt.where(ScanEvent.type == event_type)
            stmt = stmt.order_by(ScanEvent.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Failed to fetch scan events: {e}")
            return []

    # ------------------------------------------------------------------
    # Work Units
    # ------------------------------------------------------------------

    async def enqueue_work_unit(
        self,
        session: AsyncSession,
        *,
        technique: str,
        targets: List[str],
        command_template: str = "",
        context: str = "",
        priority: int = 50,
        phase: str = "recon",
    ) -> Optional[WorkUnit]:
        """Add a single-scope work unit. Returns None if duplicate.

        Empty targets preserve the legacy no-op behavior. Multiple targets are
        rejected so callers do not accidentally enqueue only one target.
        """
        if not targets:
            logger.warning("enqueue_work_unit called with empty targets list")
            return None
        if len(targets) > 1:
            raise ValueError("enqueue_work_unit accepts exactly one target; enqueue one work unit per target")
        
        primary_target = targets[0]
        unit = WorkUnit(
            scan_id=self.scan_id,
            project_id=self.project_id,
            technique=technique,
            target=primary_target,
            target_kind=_target_kind(primary_target),
            tool_family=_tool_family(technique, command_template),
            scope_key=primary_target,
            command_template=command_template,
            context=context,
            priority=priority,
            phase=phase,
        )
        try:
            session.add(unit)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.WORK_UNIT_QUEUED,
                entity_type="work_unit",
                entity_id=str(unit.id),
                payload={
                    "technique": technique,
                    "target": primary_target,
                    "priority": priority,
                    "phase": phase,
                },
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(unit)
            logger.debug(f"📋 WorkUnit queued: {technique} → {primary_target}")
            return unit
        except IntegrityError:
            await session.rollback()
            logger.debug(f"📋 WorkUnit dedup: {technique} already queued for {primary_target}")
            return None
        except SQLAlchemyError as e:
            await session.rollback()
            return _handle_db_error("enqueue_work_unit", e)

    async def claim_work_unit(
        self, session: AsyncSession, worker_id: str
    ) -> Optional[WorkUnit]:
        """Atomically claim the highest-priority pending work unit."""
        try:
            active_stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status.in_([
                        WorkUnitStatus.CLAIMED,
                        WorkUnitStatus.RUNNING,
                    ]),
                )
            )
            active_result = await session.execute(active_stmt)
            active_locks = {
                (
                    unit.tool_family or _tool_family(unit.technique, unit.command_template or ""),
                    unit.scope_key or unit.target,
                )
                for unit in active_result.scalars().all()
            }

            stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status == WorkUnitStatus.PENDING,
                )
                .order_by(WorkUnit.priority.asc(), WorkUnit.created_at.asc())
                .limit(50)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            unit = None
            claimed_id: Optional[UUID] = None
            claimed_targets: List[str] = []
            claimed_technique = ""
            claim_started_at = datetime.now(timezone.utc)
            for candidate in result.scalars().all():
                family = _tool_family(candidate.technique, candidate.command_template or "")
                scope_key = candidate.scope_key or candidate.target
                if (
                    family in _SERIALIZED_TOOL_FAMILIES
                    and (family, scope_key) in active_locks
                ):
                    continue
                claim_stmt = (
                    update(WorkUnit)
                    .where(
                        WorkUnit.id == candidate.id,
                        WorkUnit.status == WorkUnitStatus.PENDING,
                    )
                    .values(
                        status=WorkUnitStatus.CLAIMED,
                        claimed_by=worker_id,
                        started_at=claim_started_at,
                    )
                )
                claim_result = await session.execute(claim_stmt)
                if (claim_result.rowcount or 0) == 1:
                    unit = candidate
                    claimed_id = candidate.id
                    claimed_technique = candidate.technique
                    claimed_targets = _unit_targets(candidate)
                    break
                await session.rollback()
            if unit is None:
                return None

            await self.append_event(
                session,
                event_type=ScanEventType.WORK_UNIT_CLAIMED,
                entity_type="work_unit",
                entity_id=str(claimed_id),
                payload={
                    "technique": claimed_technique,
                    "worker_id": worker_id,
                    "targets": claimed_targets,
                },
                auto_commit=False,
            )
            await session.commit()
            refresh_stmt = select(WorkUnit).where(WorkUnit.id == claimed_id)
            refreshed = await session.execute(refresh_stmt)
            unit = refreshed.scalar_one_or_none()
            if unit is None:
                return None
            return unit
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to claim work unit: {e}")
            return None

    async def complete_work_unit(
        self,
        session: AsyncSession,
        unit_id: UUID,
        *,
        stdout: str = "",
        stderr: str = "",
        exit_code: int = 0,
        status: WorkUnitStatus = WorkUnitStatus.COMPLETED,
    ) -> None:
        """Mark a work unit as completed with results."""
        try:
            stmt = select(WorkUnit).where(WorkUnit.id == unit_id)
            result = await session.execute(stmt)
            unit = result.scalar_one_or_none()
            if unit is None:
                return
            unit.status = status
            unit.result_stdout = stdout
            unit.result_stderr = stderr
            unit.exit_code = exit_code
            unit.completed_at = datetime.now(timezone.utc)
            completed_targets = _unit_targets(unit)
            completed_technique = unit.technique
            session.add(unit)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=(
                    ScanEventType.WORK_UNIT_COMPLETED
                    if status == WorkUnitStatus.COMPLETED
                    else ScanEventType.WORK_UNIT_FAILED
                ),
                entity_type="work_unit",
                entity_id=str(unit.id),
                payload={
                    "technique": completed_technique,
                    "status": str(status),
                    "exit_code": exit_code,
                    "targets": completed_targets,
                },
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(unit)
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to complete work unit {unit_id}: {e}")

    async def get_unanalyzed_results(
        self, session: AsyncSession, limit: int = 10
    ) -> List[WorkUnit]:
        """Get completed work units the Analyst hasn't reviewed yet."""
        try:
            stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status == WorkUnitStatus.COMPLETED,
                    WorkUnit.analyzed == False,
                )
                .order_by(WorkUnit.completed_at.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Failed to get unanalyzed results: {e}")
            return []

    async def mark_analyzed(
        self, session: AsyncSession, unit_ids: List[UUID]
    ) -> None:
        """Mark work units as analyzed by the Analyst."""
        if not unit_ids:
            return
        try:
            stmt = select(WorkUnit).where(WorkUnit.id.in_(unit_ids))
            result = await session.execute(stmt)
            for unit in result.scalars().all():
                unit.analyzed = True
                session.add(unit)
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to mark units analyzed: {e}")

    async def get_completed_techniques(
        self, session: AsyncSession
    ) -> List[str]:
        """Get list of techniques that have been completed (for dedup)."""
        try:
            from sqlalchemy import distinct
            stmt = (
                select(distinct(WorkUnit.technique))
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status.in_([
                        WorkUnitStatus.COMPLETED,
                        WorkUnitStatus.RUNNING,
                        WorkUnitStatus.CLAIMED,
                        WorkUnitStatus.PENDING,
                    ]),
                )
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
        except SQLAlchemyError as e:
            logger.error(f"Failed to get completed techniques: {e}")
            return []

    async def get_pending_count(self, session: AsyncSession) -> int:
        """Count pending work units."""
        try:
            from sqlalchemy import func
            stmt = (
                select(func.count(WorkUnit.id))
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status.in_([
                        WorkUnitStatus.PENDING,
                        WorkUnitStatus.CLAIMED,
                        WorkUnitStatus.RUNNING,
                    ]),
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError:
            return 0

    async def get_unanalyzed_count(self, session: AsyncSession) -> int:
        """Count completed work units the Analyst has not reviewed yet."""
        try:
            from sqlalchemy import func
            stmt = (
                select(func.count(WorkUnit.id))
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status == WorkUnitStatus.COMPLETED,
                    WorkUnit.analyzed == False,
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError:
            return 0

    # ------------------------------------------------------------------
    # Directives (Analyst → Planner)
    # ------------------------------------------------------------------

    async def add_directive(
        self,
        session: AsyncSession,
        *,
        directive_type: DirectiveType,
        content: Dict[str, Any],
    ) -> Optional[Directive]:
        """Analyst writes a directive for the Planner."""
        directive = Directive(
            scan_id=self.scan_id,
            type=directive_type,
            content=content,
        )
        try:
            session.add(directive)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.DIRECTIVE_ADDED,
                entity_type="directive",
                entity_id=str(directive.id),
                payload={"type": str(directive_type), "content": content},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(directive)
            logger.debug(f"📜 Directive added: {directive_type} → {content}")
            return directive
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add directive: {e}")
            return None

    async def consume_directives(
        self, session: AsyncSession
    ) -> List[Directive]:
        """Planner reads and marks unconsumed directives."""
        try:
            stmt = (
                select(Directive)
                .where(
                    Directive.scan_id == self.scan_id,
                    Directive.consumed == False,
                )
                .order_by(Directive.created_at.asc())
            )
            result = await session.execute(stmt)
            directives = list(result.scalars().all())
            for d in directives:
                d.consumed = True
                session.add(d)
            if directives:
                await session.commit()
            return directives
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to consume directives: {e}")
            return []

    async def get_unconsumed_directive_count(self, session: AsyncSession) -> int:
        """Count unconsumed directives waiting for the Planner."""
        try:
            from sqlalchemy import func
            stmt = (
                select(func.count(Directive.id))
                .where(
                    Directive.scan_id == self.scan_id,
                    Directive.consumed == False,
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
        except SQLAlchemyError:
            return 0

    # ------------------------------------------------------------------
    # Observations / Capabilities / Hypotheses
    # ------------------------------------------------------------------

    async def add_observation(
        self,
        session: AsyncSession,
        *,
        observation_type: ObservationType,
        target: str,
        key: str,
        value: Dict[str, Any],
    ) -> Optional[Observation]:
        """Persist a typed observation if it does not already exist."""
        observation = Observation(
            scan_id=self.scan_id,
            project_id=self.project_id,
            type=observation_type,
            target=target,
            key=key,
            value=value,
        )
        try:
            session.add(observation)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.OBSERVATION_ADDED,
                entity_type="observation",
                entity_id=str(observation.id),
                payload={"type": str(observation_type), "target": target, "key": key},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(observation)
            return observation
        except IntegrityError:
            await session.rollback()
            existing = (
                await session.execute(
                    select(Observation).where(
                        Observation.scan_id == self.scan_id,
                        Observation.type == observation_type,
                        Observation.target == target,
                        Observation.key == key,
                    )
                )
            ).scalar_one_or_none()
            return existing
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add observation: {e}")
            return None

    async def get_observations(
        self,
        session: AsyncSession,
        *,
        observation_type: ObservationType | None = None,
        limit: int = 100,
    ) -> List[Observation]:
        try:
            stmt = select(Observation).where(Observation.scan_id == self.scan_id)
            if observation_type is not None:
                stmt = stmt.where(Observation.type == observation_type)
            stmt = stmt.order_by(Observation.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

    async def add_capability(
        self,
        session: AsyncSession,
        *,
        capability_type: CapabilityType,
        target: str,
        key: str,
        details: Dict[str, Any],
    ) -> Optional[Capability]:
        """Persist or update a capability."""
        try:
            existing = (
                await session.execute(
                    select(Capability).where(
                        Capability.scan_id == self.scan_id,
                        Capability.type == capability_type,
                        Capability.target == target,
                        Capability.key == key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.details = details
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
                await _flush_if_available(session)
                await self.append_event(
                    session,
                    event_type=ScanEventType.CAPABILITY_ADDED,
                    entity_type="capability",
                    entity_id=str(existing.id),
                    payload={"type": str(capability_type), "target": target, "key": key},
                    auto_commit=False,
                )
                await session.commit()
                await session.refresh(existing)
                return existing
        except SQLAlchemyError:
            await session.rollback()

        capability = Capability(
            scan_id=self.scan_id,
            project_id=self.project_id,
            type=capability_type,
            target=target,
            key=key,
            details=details,
        )
        try:
            session.add(capability)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.CAPABILITY_ADDED,
                entity_type="capability",
                entity_id=str(capability.id),
                payload={"type": str(capability_type), "target": target, "key": key},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(capability)
            return capability
        except IntegrityError:
            await session.rollback()
            return (
                await session.execute(
                    select(Capability).where(
                        Capability.scan_id == self.scan_id,
                        Capability.type == capability_type,
                        Capability.target == target,
                        Capability.key == key,
                    )
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add capability: {e}")
            return None

    async def get_capabilities(
        self,
        session: AsyncSession,
        *,
        capability_type: CapabilityType | None = None,
        limit: int = 100,
    ) -> List[Capability]:
        try:
            stmt = select(Capability).where(Capability.scan_id == self.scan_id)
            if capability_type is not None:
                stmt = stmt.where(Capability.type == capability_type)
            stmt = stmt.order_by(Capability.updated_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

    async def add_hypothesis(
        self,
        session: AsyncSession,
        *,
        hypothesis_type: HypothesisType,
        target: str,
        key: str,
        rationale: str,
        confidence: float = 0.5,
        evidence: Dict[str, Any] | None = None,
        status: HypothesisStatus = HypothesisStatus.PENDING,
    ) -> Optional[Hypothesis]:
        """Persist or update a hypothesis."""
        try:
            existing = (
                await session.execute(
                    select(Hypothesis).where(
                        Hypothesis.scan_id == self.scan_id,
                        Hypothesis.type == hypothesis_type,
                        Hypothesis.target == target,
                        Hypothesis.key == key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                if existing.status in {HypothesisStatus.RESOLVED, HypothesisStatus.DISMISSED}:
                    return existing
                existing.rationale = rationale
                existing.confidence = confidence
                existing.evidence = evidence or {}
                existing.updated_at = datetime.now(timezone.utc)
                session.add(existing)
                await _flush_if_available(session)
                await self.append_event(
                    session,
                    event_type=ScanEventType.HYPOTHESIS_UPDATED,
                    entity_type="hypothesis",
                    entity_id=str(existing.id),
                    payload={
                        "type": str(hypothesis_type),
                        "target": target,
                        "key": key,
                        "status": str(existing.status),
                    },
                    auto_commit=False,
                )
                await session.commit()
                await session.refresh(existing)
                return existing
        except SQLAlchemyError:
            await session.rollback()

        hypothesis = Hypothesis(
            scan_id=self.scan_id,
            project_id=self.project_id,
            type=hypothesis_type,
            target=target,
            key=key,
            rationale=rationale,
            confidence=confidence,
            evidence=evidence or {},
            status=status,
        )
        try:
            session.add(hypothesis)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.HYPOTHESIS_ADDED,
                entity_type="hypothesis",
                entity_id=str(hypothesis.id),
                payload={
                    "type": str(hypothesis_type),
                    "target": target,
                    "key": key,
                    "status": str(status),
                },
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(hypothesis)
            return hypothesis
        except IntegrityError:
            await session.rollback()
            return (
                await session.execute(
                    select(Hypothesis).where(
                        Hypothesis.scan_id == self.scan_id,
                        Hypothesis.type == hypothesis_type,
                        Hypothesis.target == target,
                        Hypothesis.key == key,
                    )
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add hypothesis: {e}")
            return None

    async def get_hypotheses(
        self,
        session: AsyncSession,
        *,
        statuses: Sequence[HypothesisStatus] | None = None,
        limit: int = 100,
    ) -> List[Hypothesis]:
        try:
            stmt = select(Hypothesis).where(Hypothesis.scan_id == self.scan_id)
            if statuses:
                stmt = stmt.where(Hypothesis.status.in_(list(statuses)))
            stmt = stmt.order_by(Hypothesis.confidence.desc(), Hypothesis.updated_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

    async def mark_hypothesis_status(
        self,
        session: AsyncSession,
        hypothesis_ids: List[UUID],
        status: HypothesisStatus,
    ) -> None:
        if not hypothesis_ids:
            return
        try:
            stmt = select(Hypothesis).where(Hypothesis.id.in_(hypothesis_ids))
            result = await session.execute(stmt)
            hypotheses = list(result.scalars().all())
            for hypothesis in hypotheses:
                hypothesis.status = status
                hypothesis.updated_at = datetime.now(timezone.utc)
                session.add(hypothesis)
            for hypothesis in hypotheses:
                await self.append_event(
                    session,
                    event_type=ScanEventType.HYPOTHESIS_UPDATED,
                    entity_type="hypothesis",
                    entity_id=str(hypothesis.id),
                    payload={
                        "type": str(hypothesis.type),
                        "target": hypothesis.target,
                        "key": hypothesis.key,
                        "status": str(status),
                    },
                    auto_commit=False,
                )
            await session.commit()
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to update hypothesis status: {e}")

    # ------------------------------------------------------------------
    # Findings (both Analyst and legacy Manager can write)
    # ------------------------------------------------------------------

    async def add_finding(
        self,
        session: AsyncSession,
        *,
        title: str,
        description: str,
        severity: FindingSeverity = FindingSeverity.INFO,
        target: str = "",
        tool: str = "",
        vector: str = "",
        proof: str = "",
        remediation: str = "",
    ) -> Optional[Finding]:
        """Add a finding, dedup by title+target."""
        # Check for existing
        try:
            existing = (
                await session.execute(
                    select(Finding).where(
                        Finding.project_id == self.project_id,
                        Finding.title == title,
                        Finding.target == target,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                logger.debug(f"Finding dedup: '{title}' on {target}")
                return existing
        except SQLAlchemyError:
            pass

        finding = Finding(
            project_id=self.project_id,
            scan_id=self.scan_id,
            title=title,
            description=description,
            severity=severity,
            target=target,
            tool=tool,
            vector=vector,
            proof=proof,
            remediation=remediation,
        )
        try:
            session.add(finding)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.FINDING_ADDED,
                entity_type="finding",
                entity_id=str(finding.id),
                payload={"title": title, "severity": str(severity), "target": target},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(finding)
            return finding
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add finding: {e}")
            return None

    async def get_findings(
        self, session: AsyncSession, limit: int = 100
    ) -> List[Finding]:
        """Get all findings for this scan."""
        try:
            stmt = (
                select(Finding)
                .where(Finding.scan_id == self.scan_id)
                .order_by(Finding.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            DBMetrics.record_operation("get_findings")
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            return _handle_db_error("get_findings", e, default_return=[])

    # ------------------------------------------------------------------
    # Notes (shared intelligence)
    # ------------------------------------------------------------------

    async def add_note(
        self,
        session: AsyncSession,
        *,
        category: NoteCategory,
        target: str = "*",
        content: str,
    ) -> Optional[EngagementNote]:
        """Add a note to shared intelligence."""
        note = EngagementNote(
            project_id=self.project_id,
            scan_id=self.scan_id,
            category=category,
            target=target,
            content=content,
        )
        try:
            session.add(note)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.NOTE_ADDED,
                entity_type="note",
                entity_id=str(note.id),
                payload={"category": str(category), "target": target},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(note)
            return note
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to add note: {e}")
            return None

    async def get_notes(
        self, session: AsyncSession, limit: int = 100
    ) -> List[EngagementNote]:
        """Get all notes for this scan."""
        try:
            stmt = (
                select(EngagementNote)
                .where(EngagementNote.scan_id == self.scan_id)
                .order_by(EngagementNote.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            DBMetrics.record_operation("get_notes")
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            return _handle_db_error("get_notes", e, default_return=[])

    async def get_attack_hints(
        self, session: AsyncSession
    ) -> List[EngagementNote]:
        """Get attack hints from Analyst."""
        try:
            stmt = (
                select(EngagementNote)
                .where(
                    EngagementNote.scan_id == self.scan_id,
                    EngagementNote.category == NoteCategory.ATTACK_HINT,
                )
                .order_by(EngagementNote.created_at.desc())
            )
            result = await session.execute(stmt)
            DBMetrics.record_operation("get_attack_hints")
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            return _handle_db_error("get_attack_hints", e, default_return=[])

    # ------------------------------------------------------------------
    # Attempts (tool execution history)
    # ------------------------------------------------------------------

    async def record_attempt(
        self,
        session: AsyncSession,
        *,
        tool: str,
        target: str,
        status: str,
        reason: str = "",
        properties: Dict[str, Any] | None = None,
    ) -> Optional[Attempt]:
        """Record a tool execution attempt."""
        attempt = Attempt(
            project_id=self.project_id,
            scan_id=self.scan_id,
            tool=tool,
            target=target,
            status=status,
            reason=reason,
            properties=properties or {},
        )
        try:
            session.add(attempt)
            await _flush_if_available(session)
            await self.append_event(
                session,
                event_type=ScanEventType.ATTEMPT_RECORDED,
                entity_type="attempt",
                entity_id=str(attempt.id),
                payload={"tool": tool, "target": target, "status": status},
                auto_commit=False,
            )
            await session.commit()
            await session.refresh(attempt)
            DBMetrics.record_operation("record_attempt")
            return attempt
        except SQLAlchemyError as e:
            await session.rollback()
            return _handle_db_error("record_attempt", e)

    async def build_projection(self, session: AsyncSession) -> Dict[str, Any]:
        """Build a compact, event-first projection for UI/CLI consumers."""
        findings = await self.get_findings(session, limit=100)
        observations = await self.get_observations(session, limit=200)
        capabilities = await self.get_capabilities(session, limit=100)
        hypotheses = await self.get_hypotheses(session, limit=100)
        notes = await self.get_notes(session, limit=50)
        attempts = await self.get_attempts(session, limit=100)
        recent_events = await self.get_events(session, limit=25)
        nodes = await self._get_nodes(session, limit=100)
        assets = self._build_assets_projection(observations, capabilities)
        degraded_components = self._build_degraded_components_projection(recent_events)
        asset_count = len(assets)

        try:
            from sqlalchemy import func
            stmt = (
                select(WorkUnit.status, func.count(WorkUnit.id))
                .where(WorkUnit.scan_id == self.scan_id)
                .group_by(WorkUnit.status)
            )
            result = await session.execute(stmt)
            work_queue = {str(row[0]): row[1] for row in result.all()}
        except SQLAlchemyError:
            work_queue = {}

        return {
            "scan_id": str(self.scan_id),
            "project_id": str(self.project_id),
            "work_queue": work_queue,
            "assets": assets,
            "asset_count": asset_count,
            "degraded_components": degraded_components,
            "node_count": len(nodes),  # Deprecated: use asset_count
            "nodes": [
                {
                    "id": str(node.id),
                    "name": node.name,
                    "type": node.type,
                    "label": node.label,
                    "properties": node.properties or {},
                    "scanned": node.scanned,
                }
                for node in nodes
            ],
            "findings": [
                {"title": finding.title, "severity": str(finding.severity), "target": finding.target}
                for finding in findings
            ],
            "attempts": [
                {
                    "id": str(attempt.id),
                    "tool": attempt.tool,
                    "target": attempt.target,
                    "status": attempt.status,
                    "reason": attempt.reason,
                }
                for attempt in attempts
            ],
            "notes": [
                {
                    "id": str(note.id),
                    "category": str(note.category),
                    "target": note.target,
                    "content": note.content,
                }
                for note in notes
            ],
            "capabilities": [
                {"type": str(capability.type), "target": capability.target, "key": capability.key}
                for capability in capabilities
            ],
            "hypotheses": [
                {
                    "type": str(hypothesis.type),
                    "target": hypothesis.target,
                    "status": str(hypothesis.status),
                    "confidence": hypothesis.confidence,
                }
                for hypothesis in hypotheses
            ],
            "recent_events": [
                {
                    "type": str(event.type),
                    "entity_type": event.entity_type,
                    "entity_id": event.entity_id,
                    "payload": event.payload,
                }
                for event in recent_events
            ],
        }

    def _build_assets_projection(
        self,
        observations: List[Observation],
        capabilities: List[Capability],
    ) -> List[Dict[str, Any]]:
        """Derive a lightweight asset read model from kernel evidence tables."""
        assets: Dict[str, Dict[str, Any]] = {}

        def ensure_asset(target: str) -> Dict[str, Any]:
            asset = assets.get(target)
            if asset is None:
                asset = {
                    "target": target,
                    "host": target.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0].lower(),
                    "observation_types": [],
                    "capability_types": [],
                }
                assets[target] = asset
            return asset

        for observation in observations:
            asset = ensure_asset(observation.target)
            obs_type = str(observation.type)
            if obs_type not in asset["observation_types"]:
                asset["observation_types"].append(obs_type)

        for capability in capabilities:
            asset = ensure_asset(capability.target)
            capability_type = str(capability.type)
            if capability_type not in asset["capability_types"]:
                asset["capability_types"].append(capability_type)

        return sorted(assets.values(), key=lambda item: (item["host"], item["target"]))

    def _build_degraded_components_projection(
        self,
        recent_events: List[ScanEvent],
    ) -> List[Dict[str, Any]]:
        """Reduce recent component health events into current degraded state."""
        state_by_component: Dict[str, Dict[str, Any]] = {}
        for event in reversed(recent_events):
            event_type = str(event.type)
            if event_type not in {
                str(ScanEventType.COMPONENT_DEGRADED),
                str(ScanEventType.COMPONENT_RECOVERED),
            }:
                continue
            payload = event.payload or {}
            component = str(payload.get("component", "")).strip()
            if not component or component in state_by_component:
                continue
            state_by_component[component] = {
                "component": component,
                "status": "degraded" if event_type == str(ScanEventType.COMPONENT_DEGRADED) else "healthy",
                "reason": payload.get("reason", ""),
                "details": payload.get("details", {}),
            }
        return [
            state for state in state_by_component.values()
            if state["status"] == "degraded"
        ]

    async def get_attempts(
        self, session: AsyncSession, limit: int = 100
    ) -> List[Attempt]:
        """Get recent attempts for this scan."""
        try:
            stmt = (
                select(Attempt)
                .where(Attempt.scan_id == self.scan_id)
                .order_by(Attempt.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

    async def _get_nodes(
        self, session: AsyncSession, limit: int = 100
    ) -> List[Node]:
        """Get nodes for this scan's project as a UI projection helper."""
        try:
            stmt = (
                select(Node)
                .where(Node.project_id == self.project_id)
                .order_by(Node.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

    # ------------------------------------------------------------------
    # State summary (for LLM prompts)
    # ------------------------------------------------------------------

    async def build_state_summary(
        self, session: AsyncSession
    ) -> str:
        """Build a compact summary of scan state for LLM prompts."""
        findings = await self.get_findings(session, limit=50)
        notes = await self.get_notes(session, limit=50)
        capabilities = await self.get_capabilities(session, limit=25)
        hypotheses = await self.get_hypotheses(
            session,
            statuses=[HypothesisStatus.PENDING, HypothesisStatus.QUEUED],
            limit=25,
        )

        # Count work units by status
        try:
            from sqlalchemy import func
            stmt = (
                select(WorkUnit.status, func.count(WorkUnit.id))
                .where(WorkUnit.scan_id == self.scan_id)
                .group_by(WorkUnit.status)
            )
            result = await session.execute(stmt)
            status_counts = {row[0]: row[1] for row in result.all()}
        except SQLAlchemyError:
            status_counts = {}

        lines = ["<scan_state>"]

        # Work queue status
        pending = status_counts.get(WorkUnitStatus.PENDING, 0)
        running = status_counts.get(WorkUnitStatus.RUNNING, 0) + status_counts.get(WorkUnitStatus.CLAIMED, 0)
        completed = status_counts.get(WorkUnitStatus.COMPLETED, 0)
        failed = status_counts.get(WorkUnitStatus.FAILED, 0)
        lines.append(
            f"  Work queue: {pending} pending, {running} running, "
            f"{completed} completed, {failed} failed"
        )

        # Findings summary
        if findings:
            by_severity: Dict[str, int] = {}
            for f in findings:
                by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            lines.append(f"  Findings: {dict(by_severity)}")

        # Recent notes
        if notes:
            lines.append("  Recent intelligence:")
            for n in notes[:15]:
                lines.append(f"    [{n.category}] ({n.target}) {n.content[:120]}")

        if capabilities:
            lines.append("  Capabilities:")
            for capability in capabilities[:10]:
                lines.append(
                    f"    [{capability.type}] ({capability.target}) {capability.key}"
                )

        if hypotheses:
            lines.append("  Active hypotheses:")
            for hypothesis in hypotheses[:10]:
                lines.append(
                    f"    [{hypothesis.status}] {hypothesis.type} -> {hypothesis.target} "
                    f"(confidence={hypothesis.confidence:.2f})"
                )

        lines.append("</scan_state>")
        return "\n".join(lines)

"""
Shared Scan Store — DB-backed state for cross-agent IPC.

All agents (Planner, Analyst, Workers) read and write through this store.
It wraps the existing DB models with atomic dedup and query helpers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID, uuid4

from loguru import logger
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from kodiak.database.models import (
    Attempt,
    Directive,
    DirectiveType,
    EngagementNote,
    Finding,
    FindingSeverity,
    NoteCategory,
    WorkUnit,
    WorkUnitStatus,
)


def _targets_hash(targets: List[str]) -> str:
    """Deterministic hash for a set of targets (order-independent)."""
    canonical = json.dumps(sorted(targets), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


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
        """Add a work unit. Returns None if duplicate (dedup by technique+targets)."""
        unit = WorkUnit(
            scan_id=self.scan_id,
            project_id=self.project_id,
            technique=technique,
            targets_json=json.dumps(sorted(targets)),
            targets_hash=_targets_hash(targets),
            command_template=command_template,
            context=context,
            priority=priority,
            phase=phase,
        )
        try:
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
            logger.debug(f"📋 WorkUnit queued: {technique} → {targets[:3]}")
            return unit
        except IntegrityError:
            await session.rollback()
            logger.debug(f"📋 WorkUnit dedup: {technique} already queued for these targets")
            return None
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to enqueue work unit: {e}")
            return None

    async def claim_work_unit(
        self, session: AsyncSession, worker_id: str
    ) -> Optional[WorkUnit]:
        """Atomically claim the highest-priority pending work unit."""
        try:
            stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.scan_id,
                    WorkUnit.status == WorkUnitStatus.PENDING,
                )
                .order_by(WorkUnit.priority.asc(), WorkUnit.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            unit = result.scalar_one_or_none()
            if unit is None:
                return None

            unit.status = WorkUnitStatus.CLAIMED
            unit.claimed_by = worker_id
            unit.started_at = datetime.now(timezone.utc)
            session.add(unit)
            await session.commit()
            await session.refresh(unit)
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
            session.add(unit)
            await session.commit()
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
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

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
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

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
            return list(result.scalars().all())
        except SQLAlchemyError:
            return []

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
            await session.commit()
            await session.refresh(attempt)
            return attempt
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Failed to record attempt: {e}")
            return None

    # ------------------------------------------------------------------
    # State summary (for LLM prompts)
    # ------------------------------------------------------------------

    async def build_state_summary(
        self, session: AsyncSession
    ) -> str:
        """Build a compact summary of scan state for LLM prompts."""
        findings = await self.get_findings(session, limit=50)
        notes = await self.get_notes(session, limit=50)

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

        lines.append("</scan_state>")
        return "\n".join(lines)

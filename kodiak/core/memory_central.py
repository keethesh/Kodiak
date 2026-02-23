"""
DB-backed cross-agent memory service for per-scan attempt history.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger

from kodiak.core.config import settings
from kodiak.database.crud import attempt as attempt_crud
from kodiak.database.models import Attempt


class CentralMemoryService:
    _ACTIVE_STATUSES = {"planned", "running"}
    _TERMINAL_STATUSES = {"success", "failure", "timeout", "skipped", "coalesced"}

    async def record_attempt(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
        status_override: Optional[str] = None,
        reason_override: Optional[str] = None,
        extra_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not settings.memory_central_enabled or not session or not project_id or not scan_id:
            return

        status = status_override or self._infer_status(result)
        reason = reason_override or str(result.get("error") or "")[:280] or None
        properties: Dict[str, Any] = {
            "fingerprint": fingerprint,
            "args": args,
            "agent_id": agent_id,
            "timed_out": bool(self._is_timeout_result(result)),
            "output_preview": str(result.get("output", ""))[:300],
        }
        if extra_properties:
            properties.update(extra_properties)

        record = Attempt(
            project_id=project_id,
            scan_id=scan_id,
            tool=tool_name,
            target=(target or "unknown").strip().lower(),
            status=status,
            reason=reason,
            properties=properties,
        )

        try:
            await attempt_crud.create(session, record)
        except Exception as e:
            text = str(e).lower()
            if "no such table" in text and "attempt" in text:
                try:
                    from kodiak.database.engine import init_db

                    await init_db()
                    await attempt_crud.create(session, record)
                except Exception as retry_error:
                    logger.warning(f"Failed to persist central memory after init_db retry: {retry_error}")
            else:
                logger.warning(f"Failed to persist central memory: {e}")

    async def record_state(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        agent_id: str,
        tool_name: str,
        target: str,
        fingerprint: str,
        args: Dict[str, Any],
        status: str,
        reason: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist a lifecycle state such as planned/running before terminal result.
        """
        await self.record_attempt(
            session=session,
            project_id=project_id,
            scan_id=scan_id,
            agent_id=agent_id,
            tool_name=tool_name,
            target=target,
            fingerprint=fingerprint,
            args=args,
            result={"success": status == "success", "error": reason or "", "output": ""},
            status_override=status,
            reason_override=(reason or "")[:280] or None,
            extra_properties=properties or {},
        )

    async def build_prompt_context(
        self,
        session: Any,
        scan_id: UUID,
        limit: int | None = None,
        agent_id: Optional[str] = None,
    ) -> str:
        if not settings.memory_central_enabled or not session or not scan_id:
            return ""

        safe_limit = max(1, limit or settings.memory_recent_in_prompt)
        try:
            attempts = await attempt_crud.get_attempts_by_scan(
                session,
                scan_id,
                limit=max(40, safe_limit * 6),
            )
        except Exception as e:
            logger.warning(f"Failed loading central memory context for scan {scan_id}: {e}")
            return ""

        if not attempts:
            return ""

        lines = ["CENTRAL SCAN MEMORY (across all agents):"]
        latest_by_fingerprint: Dict[str, Any] = {}
        ordered_latest: List[Any] = []
        for attempt in attempts:
            props = attempt.properties or {}
            fingerprint = str(props.get("fingerprint") or f"{attempt.tool}:{attempt.target}")
            if fingerprint in latest_by_fingerprint:
                continue
            latest_by_fingerprint[fingerprint] = attempt
            ordered_latest.append(attempt)

        active_lines: List[str] = []
        completed_lines: List[str] = []

        for attempt in ordered_latest:
            props = attempt.properties or {}
            owner_id = str(props.get("agent_id", "unknown"))
            summary = str(props.get("output_preview", "")).replace("\n", " ").strip()
            if len(summary) > 130:
                summary = summary[:127] + "..."
            strategy = str(props.get("strategy") or props.get("thought") or "").replace("\n", " ").strip()
            if len(strategy) > 110:
                strategy = strategy[:107] + "..."
            outcome = str(props.get("outcome") or "").strip()
            next_step = str(props.get("next_step") or "").replace("\n", " ").strip()
            if len(next_step) > 95:
                next_step = next_step[:92] + "..."
            status = str(attempt.status or "unknown").upper()

            if str(attempt.status or "").lower() in self._ACTIVE_STATUSES:
                if agent_id and owner_id == str(agent_id):
                    continue
                line = (
                    f"- {attempt.tool} target={attempt.target} by={owner_id} "
                    f"status={status} why={strategy or attempt.reason or '-'}"
                )
                active_lines.append(line)
                continue

            line = (
                f"- [{status}] {attempt.tool} target={attempt.target} by={owner_id} "
                f"reason={attempt.reason or '-'}"
            )
            if outcome:
                line += f" outcome={outcome}"
            if next_step:
                line += f" next={next_step}"
            if strategy:
                line += f" why={strategy}"
            if summary:
                line += f" obs={summary}"
            completed_lines.append(line)

        if active_lines:
            lines.append("PEER ACTIVE WORK (avoid concurrent duplicates):")
            for line in active_lines[:safe_limit]:
                lines.append(line)
        if completed_lines:
            lines.append("RECENT EXECUTIONS (reuse before retrying):")
            for line in completed_lines[:safe_limit]:
                lines.append(line)
        return "\n".join(lines)

    async def find_active_peer_execution(
        self,
        session: Any,
        scan_id: UUID,
        fingerprint: str,
        requesting_agent_id: str,
        max_age_seconds: int = 180,
    ) -> Optional[Dict[str, Any]]:
        """
        Return an active in-flight peer execution for a fingerprint, if present and recent.
        """
        if not settings.memory_central_enabled or not session or not scan_id or not fingerprint:
            return None
        try:
            attempts = await attempt_crud.get_attempts_by_scan(session, scan_id, limit=120)
        except Exception:
            return None

        now = datetime.now(timezone.utc)
        for attempt in attempts:
            props = attempt.properties or {}
            if str(props.get("fingerprint") or "") != fingerprint:
                continue
            owner = str(props.get("agent_id") or "")
            if owner == requesting_agent_id:
                continue
            status = str(attempt.status or "").lower()
            if status in self._TERMINAL_STATUSES:
                return None
            if status not in self._ACTIVE_STATUSES:
                continue
            created = attempt.created_at
            if isinstance(created, datetime):
                created_utc = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                if now - created_utc > timedelta(seconds=max(10, max_age_seconds)):
                    return None
            return {
                "agent_id": owner or "unknown",
                "status": status,
                "tool": attempt.tool,
                "target": attempt.target,
                "reason": attempt.reason or "",
                "strategy": str(props.get("strategy") or props.get("thought") or ""),
                "created_at": attempt.created_at,
            }
        return None

    async def timeout_count_for_target(
        self,
        session: Any,
        scan_id: UUID,
        tool_name: str,
        target_key: str,
        limit: int = 50,
    ) -> int:
        if not settings.memory_central_enabled or not session or not scan_id or not target_key:
            return 0
        try:
            attempts = await attempt_crud.get_attempts_by_scan(session, scan_id, limit=limit)
            return sum(
                1
                for a in attempts
                if a.tool == tool_name and (a.target or "") == target_key and a.status == "timeout"
            )
        except Exception:
            return 0

    def _is_timeout_result(self, result: Dict[str, Any]) -> bool:
        text = f"{result.get('error', '')} {result.get('output', '')}".lower()
        return "timeout" in text or "timed out" in text

    def _infer_status(self, result: Dict[str, Any]) -> str:
        status = "success" if result.get("success") else "failure"
        if self._is_timeout_result(result):
            status = "timeout"
        error_text = str(result.get("error") or "")
        if status == "failure" and error_text.startswith("Skipping "):
            status = "skipped"
        return status

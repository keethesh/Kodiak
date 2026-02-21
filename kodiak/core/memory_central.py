"""
DB-backed cross-agent memory service for per-scan attempt history.
"""

from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from loguru import logger

from kodiak.core.config import settings
from kodiak.database.crud import attempt as attempt_crud
from kodiak.database.models import Attempt


class CentralMemoryService:
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
    ) -> None:
        if not settings.memory_central_enabled or not session or not project_id or not scan_id:
            return

        status = "success" if result.get("success") else "failure"
        if self._is_timeout_result(result):
            status = "timeout"
        if status == "failure" and result.get("error", "").startswith("Skipping "):
            status = "skipped"

        record = Attempt(
            project_id=project_id,
            scan_id=scan_id,
            tool=tool_name,
            target=(target or "unknown").strip().lower(),
            status=status,
            reason=str(result.get("error") or "")[:280] or None,
            properties={
                "fingerprint": fingerprint,
                "args": args,
                "agent_id": agent_id,
                "timed_out": bool(self._is_timeout_result(result)),
                "output_preview": str(result.get("output", ""))[:300],
            },
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

    async def build_prompt_context(
        self,
        session: Any,
        scan_id: UUID,
        limit: int | None = None,
    ) -> str:
        if not settings.memory_central_enabled or not session or not scan_id:
            return ""

        safe_limit = max(1, limit or settings.memory_recent_in_prompt)
        try:
            attempts = await attempt_crud.get_attempts_by_scan(session, scan_id, limit=safe_limit)
        except Exception as e:
            logger.warning(f"Failed loading central memory context for scan {scan_id}: {e}")
            return ""

        if not attempts:
            return ""

        lines = ["CENTRAL SCAN MEMORY (across all agents):"]
        for attempt in reversed(attempts[-safe_limit:]):
            props = attempt.properties or {}
            agent_id = str(props.get("agent_id", "unknown"))
            summary = str(props.get("output_preview", "")).replace("\n", " ").strip()
            if len(summary) > 130:
                summary = summary[:127] + "..."
            status = str(attempt.status or "unknown").upper()
            lines.append(
                f"- [{status}] {attempt.tool} target={attempt.target} by={agent_id} "
                f"reason={attempt.reason or '-'} obs={summary or '-'}"
            )
        return "\n".join(lines)

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

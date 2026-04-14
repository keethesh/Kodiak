from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Protocol


class RuntimeEventPublisher(Protocol):
    """Transport-agnostic event publisher used by the core runtime."""

    def subscribe(self, event_type: str, handler: Callable) -> None: ...

    def subscribe_scan(self, scan_id: str, handler: Callable) -> None: ...

    def unsubscribe_scan(self, scan_id: str, handler: Callable) -> None: ...

    async def emit_tool_start(
        self,
        tool_name: str,
        target: str,
        agent_id: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_tool_complete(
        self,
        tool_name: str,
        result: Any,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_agent_thinking(
        self,
        agent_id: str,
        message: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_agent_thought(
        self,
        agent_id: str,
        thought: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_scan_started(
        self,
        scan_id: str,
        scan_name: str,
        target: str,
        agent_id: Optional[str] = None,
    ) -> None: ...

    async def emit_scan_completed(
        self,
        scan_id: str,
        scan_name: str,
        status: str,
        summary: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    async def emit_scan_failed(
        self,
        scan_id: str,
        scan_name: str,
        error: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None: ...

    async def emit_note_saved(
        self,
        category: str,
        target: str,
        preview: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_finding_saved(
        self,
        title: str,
        severity: str,
        target: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_phase_advanced(
        self,
        old_phase: str,
        new_phase: str,
        scan_id: Optional[str] = None,
    ) -> None: ...

    async def emit_prior_knowledge_loaded(
        self,
        notes_count: int,
        findings_count: int,
        scan_id: Optional[str] = None,
    ) -> None: ...

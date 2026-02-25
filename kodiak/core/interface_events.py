from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import time


@dataclass
class CoreEvent:
    """Frontend-agnostic event emitted by the core interface."""

    type: str
    run_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    scan_id: Optional[str] = None


def map_tui_event_payload(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize TUI event payload to a stable frontend-facing shape."""
    if event_type == "tool_start":
        return {
            "tool_name": data.get("tool_name"),
            "target": data.get("target"),
            "status": data.get("status", "started"),
            "agent_id": data.get("agent_id"),
        }
    if event_type == "tool_complete":
        return {
            "tool_name": data.get("tool_name"),
            "status": data.get("status"),
            "success": data.get("success"),
            "output": data.get("output"),
            "error": data.get("error"),
            "data": data.get("data"),
        }
    if event_type in {"scan_started", "scan_completed", "scan_failed"}:
        return {
            "scan_id": data.get("scan_id"),
            "scan_name": data.get("scan_name"),
            "status": data.get("status"),
            "target": data.get("target"),
            "summary": data.get("summary"),
            "error": data.get("error"),
            "details": data.get("details"),
        }
    if event_type == "finding_discovered":
        return {
            "scan_id": data.get("scan_id"),
            "agent_id": data.get("agent_id"),
            "finding": data.get("finding"),
        }
    if event_type in {"agent_thinking", "agent_thought"}:
        return {
            "agent_id": data.get("agent_id"),
            "message": data.get("message"),
            "thought": data.get("thought"),
            "status": data.get("status"),
        }
    if event_type in {"note_saved", "finding_saved"}:
        return {
            "category": data.get("category"),
            "target": data.get("target"),
            "preview": data.get("preview"),
            "title": data.get("title"),
            "severity": data.get("severity"),
        }
    if event_type == "phase_advanced":
        return {
            "old_phase": data.get("old_phase"),
            "new_phase": data.get("new_phase"),
        }
    if event_type == "prior_knowledge_loaded":
        return {
            "notes_count": data.get("notes_count", 0),
            "findings_count": data.get("findings_count", 0),
        }
    if event_type == "llm_response":
        return {
            "iteration": data.get("iteration"),
            "raw_json": data.get("raw_json"),
            "input_tokens": data.get("input_tokens", 0),
            "output_tokens": data.get("output_tokens", 0),
            "thinking_tokens": data.get("thinking_tokens", 0),
            "cached_tokens": data.get("cached_tokens", 0),
            "cost_usd": data.get("cost_usd", 0.0),
        }
    return data or {}

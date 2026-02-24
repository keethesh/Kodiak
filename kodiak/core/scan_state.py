"""
Scan State — structured state object for the Manager agent.

Replaces blackboard + central memory + conversation history as the Manager's
working memory.  Serialises to a compact prompt context (~2K tokens) regardless
of how many tools have run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class ScanPhase(str, Enum):
    RECON = "recon"
    ENUMERATION = "enumeration"
    VULN_SCAN = "vuln_scan"
    EXPLOITATION = "exploitation"
    REPORTING = "reporting"

    @property
    def next(self) -> Optional[ScanPhase]:
        order = list(ScanPhase)
        idx = order.index(self)
        return order[idx + 1] if idx + 1 < len(order) else None


# ---------------------------------------------------------------------------
# Per-target state
# ---------------------------------------------------------------------------

@dataclass
class TargetState:
    """Accumulated knowledge about a single host / URL."""
    hostname: str
    ip: Optional[str] = None
    ports: List[int] = field(default_factory=list)
    services: Dict[int, str] = field(default_factory=dict)  # port → service banner
    technologies: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    status: str = "discovered"  # discovered | enumerated | scanned | exploited

    def to_compact(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"host": self.hostname, "status": self.status}
        if self.ip:
            d["ip"] = self.ip
        if self.ports:
            d["ports"] = self.ports[:20]
        if self.services:
            d["services"] = dict(list(self.services.items())[:10])
        if self.technologies:
            d["technologies"] = self.technologies[:10]
        if self.urls:
            d["urls"] = self.urls[:15]
        return d


# ---------------------------------------------------------------------------
# Completed-tool record
# ---------------------------------------------------------------------------

@dataclass
class ToolRecord:
    """One completed tool execution."""
    tool: str
    target: str
    summary: str
    status: str  # success | timeout | error | no_signal
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_compact(self) -> str:
        return f"{self.tool}({self.target}) → {self.status}: {self.summary[:120]}"


# ---------------------------------------------------------------------------
# Task record (event-driven scheduler)
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    """State for one scheduled command task."""
    task_id: str
    tool: str
    command: str
    status: str  # queued | running | success | failed | timeout | cancelled
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_compact(self) -> str:
        return f"{self.task_id}:{self.tool}:{self.status}:{self.command[:80]}"


# ---------------------------------------------------------------------------
# Finding record
# ---------------------------------------------------------------------------

@dataclass
class FindingRecord:
    """A confirmed or suspected security finding."""
    title: str
    severity: str  # critical | high | medium | low | info
    target: str
    evidence: str = ""
    tool: str = ""

    def to_compact(self) -> str:
        parts = [f"[{self.severity.upper()}] {self.title} @ {self.target}"]
        if self.evidence:
            parts.append(f"  evidence: {self.evidence[:100]}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main scan state
# ---------------------------------------------------------------------------

@dataclass
class ScanState:
    """
    Complete structured state for a Manager-driven scan.

    The Manager serialises this into every LLM prompt via ``to_prompt_context()``.
    It is also the single source of truth that replaces the blackboard,
    central memory, and growing conversation history.
    """

    target: str
    phase: ScanPhase = ScanPhase.RECON
    targets: Dict[str, TargetState] = field(default_factory=dict)
    findings: List[FindingRecord] = field(default_factory=list)
    completed_tools: List[ToolRecord] = field(default_factory=list)
    phase_history: List[str] = field(default_factory=list)  # short decision log
    waf_detected: bool = False  # True when a WAF/CDN (e.g. Cloudflare) is confirmed
    active_tasks: Dict[str, TaskRecord] = field(default_factory=dict)
    pending_tasks: Dict[str, TaskRecord] = field(default_factory=dict)
    last_replan_at: Optional[str] = None

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def ensure_target(self, hostname: str) -> TargetState:
        """Return existing target state or create a new one."""
        if hostname not in self.targets:
            self.targets[hostname] = TargetState(hostname=hostname)
        return self.targets[hostname]

    def record_tool_result(
        self,
        tool: str,
        target: str,
        status: str,
        summary: str,
    ) -> None:
        """Append a tool result to the completed-tools ledger."""
        self.completed_tools.append(
            ToolRecord(tool=tool, target=target, summary=summary, status=status)
        )

    def add_finding(
        self,
        title: str,
        severity: str,
        target: str,
        evidence: str = "",
        tool: str = "",
    ) -> None:
        self.findings.append(
            FindingRecord(
                title=title,
                severity=severity,
                target=target,
                evidence=evidence,
                tool=tool,
            )
        )

    def queue_task(self, task_id: str, tool: str, command: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        record = TaskRecord(
            task_id=task_id,
            tool=tool,
            command=command,
            status="queued",
            created_at=now,
            updated_at=now,
        )
        self.pending_tasks[task_id] = record
        self.active_tasks[task_id] = record

    def start_task(self, task_id: str) -> None:
        record = self.active_tasks.get(task_id)
        if not record:
            return
        record.status = "running"
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self.pending_tasks.pop(task_id, None)

    def finish_task(self, task_id: str, status: str) -> None:
        record = self.active_tasks.pop(task_id, None)
        if not record:
            self.pending_tasks.pop(task_id, None)
            return
        record.status = status
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self.pending_tasks.pop(task_id, None)

    def mark_replan(self) -> None:
        self.last_replan_at = datetime.now(timezone.utc).isoformat()

    def advance_phase(self) -> bool:
        """Move to the next phase.  Returns False if already at REPORTING."""
        nxt = self.phase.next
        if nxt is None:
            return False
        self.phase_history.append(
            f"{self.phase.value} → {nxt.value} "
            f"(tools={len(self.completed_tools)}, findings={len(self.findings)})"
        )
        self.phase = nxt
        return True

    # ------------------------------------------------------------------
    # Prompt serialisation
    # ------------------------------------------------------------------

    def to_prompt_context(self, max_tool_records: int = 30) -> str:
        """
        Compact textual representation for injection into the Manager's
        system prompt.  Stays under ~2K tokens regardless of scan size.
        """
        sections: List[str] = []

        # Phase
        sections.append(f"phase: {self.phase.value}")

        # Targets summary
        if self.targets:
            target_lines = [t.to_compact() for t in self.targets.values()]
            sections.append(
                "targets:\n" + json.dumps(target_lines, separators=(",", ":"))
            )
        else:
            sections.append("targets: none discovered yet")

        # Findings summary
        if self.findings:
            by_sev: Dict[str, int] = {}
            for f in self.findings:
                by_sev[f.severity] = by_sev.get(f.severity, 0) + 1
            sections.append(f"findings_summary: {json.dumps(by_sev, separators=(',', ':'))}")
            recent = self.findings[-5:]
            sections.append(
                "recent_findings:\n"
                + "\n".join(f.to_compact() for f in recent)
            )
        else:
            sections.append("findings: none yet")

        # Tool history (last N)
        if self.completed_tools:
            recent_tools = self.completed_tools[-max_tool_records:]
            sections.append(
                f"completed_tools ({len(self.completed_tools)} total, showing last {len(recent_tools)}):\n"
                + "\n".join(r.to_compact() for r in recent_tools)
            )
        else:
            sections.append("completed_tools: none yet")

        if self.active_tasks:
            active_lines = [task.to_compact() for task in list(self.active_tasks.values())[:10]]
            sections.append(
                f"active_tasks ({len(self.active_tasks)}):\n" + "\n".join(active_lines)
            )
        else:
            sections.append("active_tasks: none")

        if self.pending_tasks:
            pending_lines = [task.to_compact() for task in list(self.pending_tasks.values())[:10]]
            sections.append(
                f"pending_tasks ({len(self.pending_tasks)}):\n" + "\n".join(pending_lines)
            )
        else:
            sections.append("pending_tasks: none")

        # Phase transitions
        if self.phase_history:
            sections.append(
                "phase_transitions:\n" + "\n".join(self.phase_history)
            )

        if self.last_replan_at:
            sections.append(f"last_replan_at: {self.last_replan_at}")

        # WAF/CDN flag — visible to manager so it can tune tool parameters
        if self.waf_detected:
            sections.append("waf_detected: true")

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def findings_count(self) -> int:
        return len(self.findings)

    @property
    def tools_run_count(self) -> int:
        return len(self.completed_tools)

    def has_tool_been_run(self, tool: str, target: str) -> bool:
        """Check if an exact (tool, target) pair already completed."""
        return any(
            r.tool == tool and r.target == target
            for r in self.completed_tools
        )

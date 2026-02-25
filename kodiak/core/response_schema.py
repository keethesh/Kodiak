"""
Structured output schema for the Kodiak agent.

Instead of function calling, the LLM returns a single JSON object
matching `KodiakResponse`.  The orchestrator then:
  1. Executes actions[]/commands[] in parallel via Docker
  2. Persists findings[] and notes[] to the database
  3. Updates ScanState from discoveries
  4. Handles phase_action (advance / complete)

IMPORTANT: Gemini API does not support `additionalProperties` in JSON schemas.
All fields must use concrete types — no Dict[str, Any] or Dict[str, List[...]].
Use typed list-of-objects instead of maps.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PhaseAction(str, Enum):
    CONTINUE = "continue"
    ADVANCE = "advance"
    COMPLETE = "complete"


class ActionType(str, Enum):
    LAUNCH = "launch"
    CANCEL = "cancel"
    WAIT = "wait"
    ADVANCE = "advance"
    COMPLETE = "complete"
    WRITE_FILE = "write_file"


class NoteCategoryEnum(str, Enum):
    RECON_INTEL = "recon_intel"
    BEHAVIORAL = "behavioral"
    ATTACK_HINT = "attack_hint"
    DEAD_END = "dead_end"
    GENERAL = "general"


class SeverityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


# ---------------------------------------------------------------------------
# Component models
# ---------------------------------------------------------------------------

class Command(BaseModel):
    """A shell command to execute in the Docker sandbox."""

    command: str = Field(
        description=(
            "The exact shell command to run, e.g. "
            "'nmap -sV -p- target.com' or 'curl -s -I https://target.com'"
        )
    )
    rationale: str = Field(
        description=(
            "Why this command is being run and what you expect to learn from it"
        )
    )
    timeout: int = Field(
        default=300,
        description="Max seconds before the command is killed (default 300)",
    )


class Action(BaseModel):
    """Explicit manager action for event-driven orchestration."""

    type: ActionType = Field(
        description="Action type: launch, cancel, wait, advance, complete"
    )
    command: str = Field(
        default="",
        description="Required for launch. Shell command to execute in the sandbox.",
    )
    rationale: str = Field(
        default="",
        description="Reason for this action (especially important for launch/cancel).",
    )
    timeout: int = Field(
        default=300,
        description="Timeout seconds for launch actions.",
    )
    task_id: str = Field(
        default="",
        description="Task ID to cancel (for cancel action).",
    )
    reason: str = Field(
        default="",
        description="Optional cancellation/wait/phase reason.",
    )
    target_path: str = Field(
        default="",
        description="Required for write_file. The absolute path to write the file to within the sandbox.",
    )
    content: str = Field(
        default="",
        description="Required for write_file. The exact string/code content to write.",
    )


class Finding(BaseModel):
    """A confirmed vulnerability discovered during the scan."""

    title: str = Field(
        description="Short descriptive title, e.g. 'SQL Injection — POST /login'"
    )
    severity: SeverityEnum = Field(
        description="Severity: critical, high, medium, or low"
    )
    target: str = Field(
        description="The affected host or URL"
    )
    description: str = Field(
        description="What the vulnerability is and how it was confirmed"
    )
    evidence: str = Field(
        default="",
        description="Raw output or proof-of-concept demonstrating the vulnerability",
    )
    remediation: str = Field(
        default="",
        description="Suggested fix for the vulnerability",
    )


class Note(BaseModel):
    """An observation to persist for future scans."""

    category: NoteCategoryEnum = Field(
        description="Category: recon_intel, behavioral, attack_hint, dead_end, or general"
    )
    target: str = Field(description="The host or domain this note relates to")
    content: str = Field(description="The observation to record")


class HostPorts(BaseModel):
    """Open ports discovered on a single host."""
    host: str = Field(description="Hostname or IP address")
    ports: List[int] = Field(default_factory=list, description="List of open TCP ports")


class HostTechs(BaseModel):
    """Technologies detected on a single host."""
    host: str = Field(description="Hostname or IP address")
    technologies: List[str] = Field(default_factory=list, description="Detected technologies, e.g. ['Apache 2.4', 'PHP 7.4']")


class Discovery(BaseModel):
    """Structured state updates extracted from command results."""

    hosts: List[str] = Field(
        default_factory=list,
        description="Newly discovered hostnames or IPs",
    )
    ports: List[HostPorts] = Field(
        default_factory=list,
        description="Open ports per host",
    )
    technologies: List[HostTechs] = Field(
        default_factory=list,
        description="Detected technologies per host",
    )
    urls: List[str] = Field(
        default_factory=list,
        description="Interesting URLs discovered (login pages, admin panels, API endpoints)",
    )


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class KodiakResponse(BaseModel):
    """Complete structured response from Kodiak for one iteration."""

    analysis: str = Field(
        description=(
            "Assessment of current scan state: what is known, what is unknown, "
            "and your strategy for this iteration"
        )
    )
    commands: List[Command] = Field(
        default_factory=list,
        description="Shell commands to execute in parallel in the Docker sandbox",
    )
    actions: List[Action] = Field(
        default_factory=list,
        description=(
            "Event-driven manager actions. Preferred over commands[] when provided. "
            "Supported: launch, cancel, wait, advance, complete."
        ),
    )
    discoveries: Discovery = Field(
        default_factory=Discovery,
        description="Structured updates to scan state from previous command results",
    )
    findings: List[Finding] = Field(
        default_factory=list,
        description="Confirmed vulnerabilities to record immediately",
    )
    notes: List[Note] = Field(
        default_factory=list,
        description="Observations to persist for future scans",
    )
    phase_action: PhaseAction = Field(
        default=PhaseAction.CONTINUE,
        description=(
            "continue = stay in current phase, "
            "advance = move to next phase, "
            "complete = finish scan (requires scan_summary)"
        ),
    )
    scan_summary: Optional[str] = Field(
        default=None,
        description="Final scan summary — required when phase_action is 'complete'",
    )

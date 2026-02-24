"""
Structured output schema for the Kodiak agent.

Instead of function calling, the LLM returns a single JSON object
matching `KodiakResponse`.  The orchestrator then:
  1. Executes commands[] in parallel via Docker
  2. Persists findings[] and notes[] to the database
  3. Updates ScanState from discoveries
  4. Handles phase_action (advance / complete)
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PhaseAction(str, Enum):
    CONTINUE = "continue"
    ADVANCE = "advance"
    COMPLETE = "complete"


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


class Discovery(BaseModel):
    """Structured state updates extracted from command results."""

    hosts: List[str] = Field(
        default_factory=list,
        description="Newly discovered hostnames or IPs",
    )
    ports: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="Map of host → open ports, e.g. {'target.com': [80, 443]}",
    )
    technologies: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Map of host → detected tech, e.g. {'target.com': ['Apache 2.4']}",
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

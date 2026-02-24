"""
Engagement Memory Tools — save_note and save_finding.

These are in-process tools intercepted by the Manager loop (not dispatched to
Docker workers). The ``_execute()`` methods return a confirmation ToolResult;
actual DB persistence is handled in ``manager.py``.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field

from kodiak.core.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------

class SaveNoteArgs(BaseModel):
    target: str = Field(
        ...,
        description="Host, URL, or '*' for project-wide observations",
    )
    category: str = Field(
        ...,
        description="One of: recon_intel, behavioral, attack_hint, dead_end, general",
    )
    content: str = Field(
        ...,
        description="The observation or insight to record for future scans",
    )


class SaveNoteTool(BaseTool):
    """Record an observation or insight that should persist across scans."""

    @property
    def name(self) -> str:
        return "save_note"

    @property
    def description(self) -> str:
        return (
            "Save an engagement note (observation, attack hint, dead end, behavioral "
            "pattern) so it is available in future scans of this project. Use this "
            "whenever you notice something worth remembering."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "The host, URL, or domain this note relates to. "
                        "Use '*' for project-wide observations."
                    ),
                },
                "category": {
                    "type": "string",
                    "enum": [
                        "recon_intel",
                        "behavioral",
                        "attack_hint",
                        "dead_end",
                        "general",
                    ],
                    "description": (
                        "recon_intel = discovered infrastructure detail. "
                        "behavioral = WAF/rate-limit/server behavior. "
                        "attack_hint = promising attack surface to explore. "
                        "dead_end = path that should be skipped in future scans. "
                        "general = any other observation."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "The observation or insight to record.",
                },
            },
            "required": ["target", "category", "content"],
        }

    args_schema = SaveNoteArgs

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            output=f"Note saved: [{args.get('category')}] {args.get('content', '')[:120]}",
            data={
                "saved": True,
                "target": args.get("target", "*"),
                "category": args.get("category", "general"),
                "content": args.get("content", ""),
            },
        )


# ---------------------------------------------------------------------------
# save_finding
# ---------------------------------------------------------------------------

class SaveFindingArgs(BaseModel):
    target: str = Field(..., description="Affected host, URL, or endpoint")
    title: str = Field(..., description="Short title, e.g. 'SQL Injection — POST /login'")
    severity: str = Field(
        ...,
        description="One of: critical, high, medium, low, info",
    )
    description: str = Field(
        ...,
        description="Detailed description of the vulnerability",
    )
    vulnerability_type: str = Field(
        default="unknown",
        description="Category: sqli, xss, rce, lfi, ssrf, idor, etc.",
    )
    exploitation_steps: str = Field(
        default="",
        description="Step-by-step reproduction instructions",
    )
    impact: str = Field(
        default="",
        description="Business/technical impact if exploited",
    )
    poc: str = Field(
        default="",
        description="Proof-of-concept: payload, curl command, or screenshot description",
    )
    remediation: str = Field(
        default="",
        description="How to fix or mitigate the vulnerability",
    )


class SaveFindingTool(BaseTool):
    """Record a confirmed security finding with full detail."""

    @property
    def name(self) -> str:
        return "save_finding"

    @property
    def description(self) -> str:
        return (
            "Save a confirmed security vulnerability with evidence, impact, POC, and "
            "remediation. Call this as soon as a vulnerability is confirmed — do not "
            "wait for the REPORTING phase."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Affected host, URL, or endpoint",
                },
                "title": {
                    "type": "string",
                    "description": "Short title, e.g. 'SQL Injection — POST /login'",
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                    "description": "Severity level of the finding",
                },
                "description": {
                    "type": "string",
                    "description": "Detailed description of the vulnerability",
                },
                "vulnerability_type": {
                    "type": "string",
                    "description": "Category: sqli, xss, rce, lfi, ssrf, idor, etc.",
                },
                "exploitation_steps": {
                    "type": "string",
                    "description": "Step-by-step reproduction instructions",
                },
                "impact": {
                    "type": "string",
                    "description": "Business/technical impact if exploited",
                },
                "poc": {
                    "type": "string",
                    "description": "Proof-of-concept: payload, curl command, or evidence",
                },
                "remediation": {
                    "type": "string",
                    "description": "How to fix or mitigate the vulnerability",
                },
            },
            "required": ["target", "title", "severity", "description"],
        }

    args_schema = SaveFindingArgs

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        severity = args.get("severity", "info").upper()
        title = args.get("title", "Untitled")
        return ToolResult(
            success=True,
            output=f"Finding saved: [{severity}] {title}",
            data={
                "saved": True,
                "target": args.get("target", ""),
                "title": title,
                "severity": args.get("severity", "info"),
                "description": args.get("description", ""),
                "vulnerability_type": args.get("vulnerability_type", "unknown"),
                "exploitation_steps": args.get("exploitation_steps", ""),
                "impact": args.get("impact", ""),
                "poc": args.get("poc", ""),
                "remediation": args.get("remediation", ""),
            },
        )

"""
Analyst Agent — deep security brain for the multi-agent pipeline.

The Analyst does NOT dispatch tools. It receives completed work unit results,
performs deep vulnerability analysis, and outputs:
  - Findings (confirmed vulnerabilities)
  - Notes (intelligence for other agents)
  - Directives (strategic instructions for the Planner)

Uses the powerful model (Gemini Pro) with high thinking for thorough analysis.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from loguru import logger
from pydantic import BaseModel, Field

from kodiak.api.events import TUIEventManager
from kodiak.core.config import settings
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.engine import get_session
from kodiak.database.models import (
    DirectiveType,
    FindingSeverity,
    NoteCategory,
    WorkUnit,
)
from kodiak.services import llm
from kodiak.services.gemini_client import GeminiClient


# ---------------------------------------------------------------------------
# Analyst-specific response schema
# ---------------------------------------------------------------------------

class AnalystFinding(BaseModel):
    title: str = Field(description="Short title, e.g. 'SQL Injection — POST /login'")
    severity: str = Field(description="critical, high, medium, low, or info")
    target: str = Field(description="Affected host or URL")
    description: str = Field(description="What the vulnerability is")
    evidence: str = Field(default="", description="Raw proof-of-concept output")
    remediation: str = Field(default="", description="Suggested fix")


class AnalystNote(BaseModel):
    category: str = Field(description="recon_intel, behavioral, attack_hint, dead_end, general")
    target: str = Field(description="Host this note relates to")
    content: str = Field(description="The observation")


class AnalystDirective(BaseModel):
    type: str = Field(description="rate_limit, skip_target, prioritize_target, attack_hint, escalate, phase_advance")
    content: str = Field(description="JSON string with directive details")


class AnalystResponse(BaseModel):
    """Structured response from the Analyst agent."""
    analysis: str = Field(description="Deep analysis of the tool results")
    findings: List[AnalystFinding] = Field(default_factory=list)
    notes: List[AnalystNote] = Field(default_factory=list)
    directives: List[AnalystDirective] = Field(default_factory=list)
    phase_recommendation: str = Field(
        default="continue",
        description="continue, advance, or complete"
    )
    scan_summary: Optional[str] = Field(
        default=None,
        description="Required when phase_recommendation is 'complete'"
    )


# ---------------------------------------------------------------------------
# Analyst Agent
# ---------------------------------------------------------------------------

@dataclass
class AnalystResult:
    """Outcome of an Analyst cycle."""
    findings_count: int
    notes_count: int
    directives_count: int
    phase_recommendation: str
    scan_summary: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cached_tokens: int = 0


class AnalystAgent:
    """
    Deep security analysis brain. Runs on its own async loop.

    Flow per cycle:
      1. Reads unanalyzed work unit results from SharedScanStore
      2. Builds a focused prompt with results + accumulated intelligence
      3. Calls Pro model for deep analysis
      4. Writes findings, notes, and directives back to store
      5. Marks work units as analyzed
    """

    def __init__(
        self,
        store: SharedScanStore,
        event_manager: Optional[TUIEventManager] = None,
    ):
        self.store = store
        self.event_manager = event_manager
        self._gemini = GeminiClient()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_thinking_tokens = 0
        self._total_cached_tokens = 0
        self._cycle_count = 0
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        poll_interval: float = 10.0,
        max_cycles: int = 100,
        min_results_per_batch: int = 1,
        planner_done_event: Optional[asyncio.Event] = None,
        settle_cycles: int = 2,
    ) -> AnalystResult:
        """
        Main Analyst loop. Polls for unanalyzed results and processes them.
        Returns when scan is complete or max_cycles reached.
        """
        last_recommendation = "continue"
        scan_summary = None
        idle_cycles = 0

        while self._cycle_count < max_cycles and not self._stop_requested:
            async for session in get_session():
                unanalyzed = await self.store.get_unanalyzed_results(
                    session, limit=15
                )
                pending = await self.store.get_pending_count(session)

            if len(unanalyzed) < min_results_per_batch and pending > 0:
                # Wait for more results to accumulate
                idle_cycles = 0
                await self._sleep(poll_interval)
                continue

            if not unanalyzed and pending == 0:
                planner_done = planner_done_event.is_set() if planner_done_event else True
                if planner_done:
                    idle_cycles += 1
                else:
                    idle_cycles = 0

                # Nothing to analyze and no work in flight. Wait for the
                # Planner to finish and for the system to stay idle across
                # multiple polls before declaring completion.
                if planner_done and idle_cycles >= settle_cycles:
                    logger.info("🧠 Analyst: no more work — signaling completion")
                    last_recommendation = "complete"
                    break
                await self._sleep(poll_interval)
                continue

            if not unanalyzed:
                idle_cycles = 0
                await self._sleep(poll_interval)
                continue

            # Process batch
            result = await self._analyze_batch(unanalyzed)
            self._cycle_count += 1
            idle_cycles = 0

            if result:
                last_recommendation = result.phase_recommendation
                scan_summary = result.scan_summary

            if last_recommendation == "complete" and (
                planner_done_event is None or planner_done_event.is_set()
            ):
                break

        return AnalystResult(
            findings_count=0,  # Accumulated in store
            notes_count=0,
            directives_count=0,
            phase_recommendation=last_recommendation,
            scan_summary=scan_summary,
            input_tokens=self._total_input_tokens,
            output_tokens=self._total_output_tokens,
            thinking_tokens=self._total_thinking_tokens,
            cached_tokens=self._total_cached_tokens,
        )

    async def _sleep(self, seconds: float) -> None:
        """Interruptible sleep."""
        import asyncio
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            self._stop_requested = True

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    async def _analyze_batch(
        self, work_units: List[WorkUnit]
    ) -> Optional[AnalystResult]:
        """Analyze a batch of completed work units."""
        logger.info(
            f"🧠 Analyst cycle {self._cycle_count + 1}: "
            f"analyzing {len(work_units)} results"
        )

        if self.event_manager:
            try:
                await self.event_manager.emit_agent_thinking(
                    agent_id="analyst",
                    message=f"Analyzing {len(work_units)} results (cycle {self._cycle_count + 1})",
                    scan_id=str(self.store.scan_id),
                )
            except Exception:
                pass

        # Build prompt
        system_prompt = self._build_system_prompt()
        user_content = self._build_results_prompt(work_units)

        # Get accumulated context
        async for session in get_session():
            state_summary = await self.store.build_state_summary(session)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{state_summary}\n\n{user_content}"},
        ]

        # Call LLM
        try:
            model = llm.normalize_model_name(settings.llm_model)
            thinking_level = llm.resolve_gemini_thinking_level(
                model, settings.gemini_thinking_level
            )
            api_key = llm.get_google_api_key()

            response = await self._gemini.generate(
                model=model,
                api_key=api_key,
                system_prompt=system_prompt,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                thinking_level=thinking_level,
                response_schema=AnalystResponse,
            )
        except Exception as exc:
            logger.error(f"Analyst LLM call failed: {exc}")
            return None

        if not response or not response.content:
            return None

        # Track tokens
        self._total_input_tokens += response.input_tokens
        self._total_output_tokens += response.output_tokens
        self._total_thinking_tokens += response.thinking_tokens
        self._total_cached_tokens += response.cached_tokens

        # Parse response
        try:
            parsed = AnalystResponse.model_validate_json(response.content)
        except Exception:
            try:
                data = json.loads(response.content)
                parsed = AnalystResponse.model_validate(data)
            except Exception as exc:
                logger.error(f"Analyst response parse failed: {exc}")
                # Mark as analyzed to avoid infinite retry
                async for session in get_session():
                    await self.store.mark_analyzed(
                        session, [u.id for u in work_units]
                    )
                return None

        logger.info(f"🧠 Analyst: {parsed.analysis[:200]}")

        if self.event_manager:
            try:
                await self.event_manager.emit_agent_thought(
                    agent_id="analyst",
                    thought=parsed.analysis,
                    scan_id=str(self.store.scan_id),
                )
            except Exception:
                pass

        # Persist results
        await self._persist_analysis(parsed, work_units)

        return AnalystResult(
            findings_count=len(parsed.findings),
            notes_count=len(parsed.notes),
            directives_count=len(parsed.directives),
            phase_recommendation=parsed.phase_recommendation,
            scan_summary=parsed.scan_summary,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            thinking_tokens=response.thinking_tokens,
            cached_tokens=response.cached_tokens,
        )

    async def _persist_analysis(
        self,
        parsed: AnalystResponse,
        work_units: List[WorkUnit],
    ) -> None:
        """Write findings, notes, directives to shared store and mark analyzed."""
        async for session in get_session():
            # Findings
            for f in parsed.findings:
                severity_map = {
                    "critical": FindingSeverity.CRITICAL,
                    "high": FindingSeverity.HIGH,
                    "medium": FindingSeverity.MEDIUM,
                    "low": FindingSeverity.LOW,
                    "info": FindingSeverity.INFO,
                }
                await self.store.add_finding(
                    session,
                    title=f.title,
                    description=f.description,
                    severity=severity_map.get(f.severity, FindingSeverity.INFO),
                    target=f.target,
                    proof=f.evidence,
                    remediation=f.remediation,
                )

            # Notes
            for n in parsed.notes:
                cat_map = {
                    "recon_intel": NoteCategory.RECON_INTEL,
                    "behavioral": NoteCategory.BEHAVIORAL,
                    "attack_hint": NoteCategory.ATTACK_HINT,
                    "dead_end": NoteCategory.DEAD_END,
                    "general": NoteCategory.GENERAL,
                }
                await self.store.add_note(
                    session,
                    category=cat_map.get(n.category, NoteCategory.GENERAL),
                    target=n.target,
                    content=n.content,
                )

            # Directives
            for d in parsed.directives:
                type_map = {
                    "rate_limit": DirectiveType.RATE_LIMIT,
                    "skip_target": DirectiveType.SKIP_TARGET,
                    "prioritize_target": DirectiveType.PRIORITIZE_TARGET,
                    "attack_hint": DirectiveType.ATTACK_HINT,
                    "escalate": DirectiveType.ESCALATE,
                    "phase_advance": DirectiveType.PHASE_ADVANCE,
                }
                try:
                    content = json.loads(d.content) if d.content else {}
                except (json.JSONDecodeError, TypeError):
                    content = {"raw": d.content}

                await self.store.add_directive(
                    session,
                    directive_type=type_map.get(d.type, DirectiveType.ATTACK_HINT),
                    content=content,
                )

            # Mark work units as analyzed
            await self.store.mark_analyzed(
                session, [u.id for u in work_units]
            )

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """Analyst-specific system prompt: analysis only, no tool dispatch."""
        return "\n".join([
            "<role>",
            "You are the ANALYST in Kodiak's multi-agent penetration testing pipeline.",
            "Your job is DEEP SECURITY ANALYSIS — you do NOT dispatch tools or commands.",
            "You receive raw tool output from Workers and produce:",
            "  1. FINDINGS: confirmed vulnerabilities with severity, evidence, and remediation",
            "  2. NOTES: intelligence observations (technologies, behaviors, attack hints)",
            "  3. DIRECTIVES: strategic instructions for the Planner agent",
            "",
            "Think like a senior penetration tester reviewing junior testers' output.",
            "Look for what the tools MISSED. Correlate across results.",
            "A version string + an exposed endpoint = a specific CVE to test.",
            "An error message + a login page = a credential attack vector.",
            "</role>",
            "",
            "<analysis_focus>",
            "For each batch of tool results, evaluate:",
            "- What vulnerabilities are confirmed or strongly indicated?",
            "- What technologies, frameworks, or versions are revealed?",
            "- What new attack vectors should the Planner pursue?",
            "- Are there cross-target patterns (same tech stack, shared creds, related infra)?",
            "- Should the scan change strategy (more stealth, different phase, skip targets)?",
            "",
            "BUSINESS LOGIC analysis is critical:",
            "- Look for APIs, multi-step flows, auth endpoints, pricing/payment logic",
            "- Identify IDOR patterns, privilege boundaries, workflow bypass opportunities",
            "- Flag any endpoint that handles money, permissions, or state transitions",
            "",
            "CORRELATION is your superpower:",
            "- Credential found on host A → test on all login endpoints",
            "- Technology X on host B → check specific CVEs on all hosts with same tech",
            "- WAF bypass found → apply technique to all blocked targets",
            "</analysis_focus>",
            "",
            "<directives_guide>",
            "Issue DIRECTIVES to control the Planner's behavior:",
            "- rate_limit: {\"max_threads\": N, \"reason\": \"WAF detected\"} — throttle all scans",
            "- skip_target: {\"target\": \"host\", \"reason\": \"decommissioned\"} — stop testing a host",
            "- prioritize_target: {\"target\": \"host\", \"reason\": \"admin panel found\"} — test first",
            "- attack_hint: {\"targets\": [...], \"technique\": \"...\", \"context\": \"...\"} — suggest new test",
            "- escalate: {\"target\": \"host\", \"finding\": \"...\", \"action\": \"...\"} — urgent exploitation",
            "- phase_advance: {\"to_phase\": \"...\", \"reason\": \"...\"} — recommend phase change",
            "",
            "Use attack_hint directives generously — they drive the Planner to run targeted tests.",
            "Example: if you see Laravel cookies, emit: attack_hint with technique='laravel_env_check'",
            "and targets=['all_live_hosts'] so the Planner probes .env on every host.",
            "</directives_guide>",
            "",
            "<output_format>",
            "Respond with JSON matching the AnalystResponse schema.",
            "Every finding needs evidence. Every directive needs a reason.",
            "Set phase_recommendation to 'advance' when the current phase's goals are met.",
            "Set phase_recommendation to 'complete' only when ALL phases are exhausted.",
            "</output_format>",
        ])

    def _build_results_prompt(self, work_units: List[WorkUnit]) -> str:
        """Format work unit results for the Analyst to review."""
        lines = ["<tool_results>"]
        for unit in work_units:
            targets = json.loads(unit.targets_json) if unit.targets_json else []
            lines.append(f"\n<result technique=\"{unit.technique}\" targets=\"{','.join(targets[:5])}\">")

            stdout = (unit.result_stdout or "").strip()
            stderr = (unit.result_stderr or "").strip()

            # Truncate very long outputs
            MAX = 8000
            if len(stdout) > MAX:
                stdout = stdout[:MAX] + f"\n... (truncated, {len(stdout)} chars total)"
            if stderr:
                if len(stderr) > 2000:
                    stderr = stderr[:2000] + "\n... (truncated)"
                lines.append(f"[stdout]\n{stdout}\n[stderr]\n{stderr}")
            else:
                lines.append(stdout)

            lines.append(f"Exit code: {unit.exit_code or 0}")
            if unit.context:
                lines.append(f"Context: {unit.context}")
            lines.append("</result>")

        lines.append("</tool_results>")
        return "\n".join(lines)

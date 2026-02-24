"""
Manager Agent — single LLM brain for Phased Manager-Worker scans.

Replaces N autonomous ``KodiakAgent`` instances with one Manager that:

1. Maintains a ``ScanState`` (structured, bounded context).
2. Calls the LLM once per iteration to decide the next batch of tool calls.
3. Dispatches tools via ``dispatch_batch()`` (parallel, stateless workers).
4. Persists attempts to the database after each batch.
5. Advances through phases: RECON → ENUM → VULN_SCAN → EXPLOIT → REPORT.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.config import settings
from kodiak.core.scan_state import ScanPhase, ScanState
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.worker import WorkerResult, WorkerTask, dispatch_batch
from kodiak.database import crud
from kodiak.database.models import Attempt, EngagementNote, Finding, NoteCategory, FindingSeverity
from kodiak.services import llm
from kodiak.services.gemini_client import GeminiClient, GeminiResponse


# ---------------------------------------------------------------------------
# Phase-aware tool blocking
# ---------------------------------------------------------------------------
# Some tools should not be dispatched until the scan has advanced to the
# appropriate phase.  This is a hard guard — the LLM prompt soft-guidance
# alone is not sufficient to prevent premature heavy scanner invocations.
#
# Key:   minimum phase required before the tool may run.
# Tools not listed here are allowed in any phase.
_TOOL_MIN_PHASE: dict[str, ScanPhase] = {
    # Vulnerability scanners — need enumerated targets first
    "nuclei":       ScanPhase.VULN_SCAN,
    "nikto":        ScanPhase.VULN_SCAN,
    "wpscan":       ScanPhase.VULN_SCAN,
    # Active exploitation — need confirmed vulns first
    "sqlmap":       ScanPhase.EXPLOITATION,
    "commix":       ScanPhase.EXPLOITATION,
    "searchsploit": ScanPhase.EXPLOITATION,
}

# Ordered list so we can compare phases numerically
_PHASE_ORDER: list[ScanPhase] = [
    ScanPhase.RECON,
    ScanPhase.ENUMERATION,
    ScanPhase.VULN_SCAN,
    ScanPhase.EXPLOITATION,
    ScanPhase.REPORTING,
]


def _phase_allowed(tool_name: str, current_phase: ScanPhase) -> bool:
    """Return True if *tool_name* may run in *current_phase*."""
    min_phase = _TOOL_MIN_PHASE.get(tool_name)
    if min_phase is None:
        return True
    return _PHASE_ORDER.index(current_phase) >= _PHASE_ORDER.index(min_phase)


# ---------------------------------------------------------------------------
# Result container (mirrors the old AgentResult)
# ---------------------------------------------------------------------------

@dataclass
class ManagerResult:
    """Outcome of a Manager-driven scan."""
    status: str  # completed | max_iterations | failed | cancelled
    summary: str
    findings_count: int
    iterations: int


# ---------------------------------------------------------------------------
# Manager Agent
# ---------------------------------------------------------------------------

class ManagerAgent:
    """
    Single-brain orchestrator for a penetration-testing scan.

    The Manager owns the full lifecycle:
      think  → decide which tools to run next (LLM call)
      dispatch → run those tools in parallel (no LLM)
      observe → update ScanState with results
      persist → write attempt records to DB
      repeat  → until complete_scan is called or budget exhausted
    """

    def __init__(
        self,
        event_manager: TUIEventManager,
        tool_inventory: ToolInventory,
    ):
        self.event_manager = event_manager
        self.tool_inventory = tool_inventory
        self._gemini = GeminiClient()
        self.scan_state: Optional[ScanState] = None
        self._prior_knowledge: str = ""

        # Built once during run()
        self._tools_for_llm: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self,
        target: str,
        instructions: str,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        max_iterations: int = 30,
        allowed_tools: Optional[List[str]] = None,
    ) -> ManagerResult:
        """Execute the full scan lifecycle."""

        logger.info(f"🚀 Manager starting scan against {target}")
        self.scan_state = ScanState(target=target)

        # Prepare tool definitions for the LLM
        self._tools_for_llm = self._prepare_tools(allowed_tools)

        # Seed the target in state
        self.scan_state.ensure_target(target)

        # scan_id string needed for events (before prior knowledge load)
        scan_id_str = str(scan_id)

        # Load prior engagement knowledge for this project
        self._prior_knowledge, _pk_notes, _pk_findings = await self._load_prior_knowledge(
            session, project_id
        )
        if (_pk_notes > 0 or _pk_findings > 0) and self.event_manager:
            try:
                await self.event_manager.emit_prior_knowledge_loaded(
                    notes_count=_pk_notes,
                    findings_count=_pk_findings,
                    scan_id=scan_id_str,
                )
            except Exception:
                pass

        history: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "<scan_request>\n"
                    f"<target>{target}</target>\n"
                    f"<instructions>{instructions or 'Conduct a comprehensive security assessment.'}</instructions>\n"
                    "</scan_request>"
                ),
            }
        ]

        # Loop-detection state: track tool names mentioned in consecutive text-only responses
        _loop_last_text_tools: set[str] = set()
        _loop_consecutive_count: int = 0

        for iteration in range(1, max_iterations + 1):
            logger.debug(f"🔄 Manager iteration {iteration}/{max_iterations}")

            # --- Iteration warnings ---
            if max_iterations > 10 and iteration == int(max_iterations * 0.85):
                remaining = max_iterations - iteration
                history.append({
                    "role": "user",
                    "content": (
                        f"<iteration_warning>Iteration {iteration}/{max_iterations}. "
                        f"{remaining} remaining. Prioritise completion.</iteration_warning>"
                    ),
                })
            elif iteration == max_iterations - 2:
                history.append({
                    "role": "user",
                    "content": (
                        "<final_warning>Only 2 iterations remain. "
                        "Produce final findings and call complete_scan NOW.</final_warning>"
                    ),
                })

            # 1. THINK -------------------------------------------------------
            response = await self._think(history, iteration, scan_id_str)

            if response is None:
                history.append({"role": "assistant", "content": "Error: LLM returned empty response"})
                history.append({
                    "role": "user",
                    "content": "<retry>Previous call failed. Try again with a tool call.</retry>",
                })
                continue

            # Emit thought for TUI
            if response.content and self.event_manager:
                try:
                    await self.event_manager.emit_agent_thought(
                        agent_id="manager",
                        thought=response.content,
                        scan_id=scan_id_str,
                    )
                except Exception:
                    pass

            # Check for explicit phase advancement
            await self._check_phase_advance(response.content or "", scan_id_str)

            # 2. DISPATCH -----------------------------------------------------
            if response.tool_calls:
                tool_calls = [self._tool_call_to_dict(tc) for tc in response.tool_calls]

                # Record assistant message with tool calls
                history.append({
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": tool_calls,
                })

                # Check for complete_scan first (no need to dispatch workers)
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    if fn.get("name") == "complete_scan":
                        if self.scan_state.phase != ScanPhase.REPORTING:
                            logger.warning(
                                f"complete_scan rejected in phase '{self.scan_state.phase.value}' — "
                                "manager must advance through all phases first"
                            )
                            history.append({
                                "role": "user",
                                "content": (
                                    f"<rejection>complete_scan rejected: current phase is "
                                    f"'{self.scan_state.phase.value}'. You must advance through all "
                                    "phases (recon → enumeration → vuln_scan → exploitation → reporting) "
                                    "by saying 'ADVANCE_PHASE' in each phase before calling complete_scan.</rejection>"
                                ),
                            })
                            break  # reject, fall through to dispatch remaining tool calls

                        args = self._parse_args(fn.get("arguments"))
                        summary = args.get("summary", "Scan completed")

                        # Persist any findings from final state
                        await self._persist_final_findings(session, project_id, scan_id)

                        logger.info(f"✅ Manager scan complete: {summary}")
                        return ManagerResult(
                            status="completed",
                            summary=summary,
                            findings_count=self.scan_state.findings_count,
                            iterations=iteration,
                        )

                # Handle in-process tools (save_note, save_finding) before dispatch
                in_process_tools = {"save_note", "save_finding"}
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    tool_name = fn.get("name", "").strip()
                    if tool_name in in_process_tools:
                        args = self._parse_args(fn.get("arguments"))
                        result_text = await self._handle_in_process_tool(
                            tool_name, args, session, project_id, scan_id,
                        )
                        history.append({
                            "role": "tool",
                            "name": tool_name,
                            "tool_call_id": tc.get("id", f"call_{uuid4().hex[:12]}"),
                            "content": result_text,
                        })

                # Build worker tasks for non-complete, non-in-process tools
                skip_tools = {"complete_scan"} | in_process_tools
                tasks: List[WorkerTask] = []
                for tc in tool_calls:
                    fn = tc.get("function", {})
                    name = fn.get("name", "").strip()
                    if not name or name in skip_tools:
                        continue
                    args = self._parse_args(fn.get("arguments"))

                    # Hard phase guard — reject heavy scanners run too early
                    if not _phase_allowed(name, self.scan_state.phase):
                        min_phase = _TOOL_MIN_PHASE[name]
                        rejection = (
                            f"<phase_rejection tool='{name}'>"
                            f"'{name}' requires phase '{min_phase.value}' but current phase is "
                            f"'{self.scan_state.phase.value}'. "
                            f"Complete the current phase objectives and say ADVANCE_PHASE before "
                            f"dispatching this tool."
                            f"</phase_rejection>"
                        )
                        logger.warning(
                            f"⛔ Phase guard: '{name}' blocked in phase "
                            f"'{self.scan_state.phase.value}' (requires '{min_phase.value}')"
                        )
                        history.append({
                            "role": "tool",
                            "name": name,
                            "tool_call_id": tc.get("id", f"call_{uuid4().hex[:12]}"),
                            "content": rejection,
                        })
                        continue

                    tasks.append(WorkerTask(tool_name=name, args=args))

                if tasks:
                    results = await dispatch_batch(
                        tasks=tasks,
                        tool_inventory=self.tool_inventory,
                        event_manager=self.event_manager,
                        scan_id=scan_id_str,
                        global_concurrency=settings.global_tool_concurrency,
                    )

                    # Reset loop-detection counter on any successful dispatch
                    _loop_last_text_tools = set()
                    _loop_consecutive_count = 0

                    # 3. OBSERVE — update state and build tool-result messages
                    for wr in results:
                        self._observe(wr)

                        # Persist attempt to DB
                        await self._persist_attempt(
                            session, project_id, scan_id, wr
                        )

                        # Add tool result to history
                        tc_id = next(
                            (tc.get("id") for tc in tool_calls
                             if tc.get("function", {}).get("name") == wr.tool_name),
                            f"call_{uuid4().hex[:12]}",
                        )
                        history.append({
                            "role": "tool",
                            "name": wr.tool_name,
                            "tool_call_id": str(tc_id),
                            "content": self._build_tool_history(wr),
                        })
            else:
                # No tool calls — text-only response.
                # Detect if the LLM is looping (writing tool calls as text instead of function calls).
                content = response.content or ""
                mentioned_tools = {
                    name for name in self.tool_inventory.get_all_tools()
                    if re.search(rf'\b{re.escape(name)}\b', content)
                }
                if mentioned_tools:
                    if mentioned_tools == _loop_last_text_tools:
                        _loop_consecutive_count += 1
                    else:
                        _loop_last_text_tools = mentioned_tools
                        _loop_consecutive_count = 1

                history.append({"role": "assistant", "content": content})

                if _loop_consecutive_count >= 2:
                    # LLM is stuck — inject a targeted loop-break nudge
                    stuck_tools = ", ".join(sorted(_loop_last_text_tools))
                    logger.warning(
                        f"⚠️  Loop detected: same tool set mentioned {_loop_consecutive_count}x "
                        f"without dispatch — {stuck_tools}"
                    )
                    history.append({
                        "role": "user",
                        "content": (
                            f"<loop_detected>You have mentioned [{stuck_tools}] {_loop_consecutive_count} times "
                            "without dispatching them. Text tool references are NEVER executed. "
                            "You MUST invoke tools via the function-calling interface right now — "
                            "not as text in your response. Dispatch the tools as function calls immediately, "
                            "or call save_note(category='dead_end') and move on.</loop_detected>"
                        ),
                    })
                    # Reset so we don't spam the nudge every iteration
                    _loop_consecutive_count = 0
                else:
                    history.append({
                        "role": "user",
                        "content": (
                            "<next_step>Continue scan. If objective is met, "
                            "call complete_scan now.</next_step>"
                        ),
                    })

            # Trim history to avoid unbounded growth
            history = self._trim_history(history, max_turns=40)

        # Budget exhausted
        await self._persist_final_findings(session, project_id, scan_id)
        return ManagerResult(
            status="max_iterations",
            summary=f"Reached iteration budget ({max_iterations})",
            findings_count=self.scan_state.findings_count,
            iterations=max_iterations,
        )

    # ------------------------------------------------------------------
    # LLM interaction
    # ------------------------------------------------------------------

    async def _think(
        self,
        history: List[Dict[str, Any]],
        iteration: int,
        scan_id: str,
    ) -> Optional[GeminiResponse]:
        """Single LLM call: system prompt + scan state + history → tool calls."""

        system_prompt = self._build_system_prompt()
        messages = [{"role": "system", "content": system_prompt}]

        # Ensure first non-system message is user (Gemini requirement)
        trimmed = [m for m in history if m.get("role") != "system"]
        if trimmed and trimmed[0].get("role") != "user":
            trimmed.insert(0, {"role": "user", "content": "Begin scan."})
        messages.extend(trimmed)

        try:
            normalized_model = llm.normalize_model_name(settings.llm_model)
            thinking_level = llm.resolve_gemini_thinking_level(
                normalized_model, settings.gemini_thinking_level
            )
            api_key = llm.get_google_api_key()

            if self.event_manager:
                try:
                    await self.event_manager.emit_agent_thinking(
                        agent_id="manager",
                        message=f"Iteration {iteration}",
                        scan_id=scan_id,
                    )
                except Exception:
                    pass

            response = await self._gemini.generate(
                model=normalized_model,
                api_key=api_key,
                system_prompt=system_prompt,
                messages=messages,
                tools=self._tools_for_llm or None,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                thinking_level=thinking_level,
            )
            return response if response else None
        except Exception as exc:
            logger.error(f"Manager think() failed: {exc}")
            return None

    def _build_system_prompt(self) -> str:
        """
        Construct the Manager's system prompt following Gemini 3 agentic best practices:
        - Role + knowledge cutoff at top
        - Plan/Select/Validate/Advance reasoning framework
        - Explicit constraints with risk tiers
        - Large context (scan state) placed before the task
        - Task/question anchored at the very end
        """
        assert self.scan_state is not None

        phase = self.scan_state.phase

        phase_objectives = {
            ScanPhase.RECON: (
                "Discover the full attack surface. Run subdomain enumeration (subfinder), "
                "port scanning (nmap), and technology fingerprinting (whatweb/httpx) against all targets. "
                "Dispatch these tools in parallel where possible."
            ),
            ScanPhase.ENUMERATION: (
                "Map services on live hosts. Probe all HTTP/HTTPS services (httpx), "
                "crawl for endpoints (katana), and fuzz for directories/files (ffuf). "
                "Prioritise hosts with the most exposed ports and services. "
                "Do NOT advance to VULN_SCAN until at least 3 of the most interesting subdomains "
                "(prelive, staging, dev, gitlab, db, shop — in that priority order) have been "
                "enumerated with ffuf or katana. "
                "For GitLab instances: prefer system_execute to probe structured API paths over katana crawl — "
                "check /api/v4/version (returns version unauthenticated), "
                "/users/sign_in (open registration?), and /-/health. "
                "These yield more signal per second than a crawler on a structured platform."
            ),
            ScanPhase.VULN_SCAN: (
                "Identify exploitable vulnerabilities. Run nuclei against live hosts, "
                "sqlmap on discovered forms and parameters, wpscan on WordPress targets, and commix on input fields. "
                "Target scans to the specific technologies found in ENUMERATION."
            ),
            ScanPhase.EXPLOITATION: (
                "Confirm and deepen vulnerability findings. Run targeted sqlmap/wpscan/commix with "
                "full exploitation flags on confirmed injection points. Gather proof-of-concept "
                "evidence: payloads, responses, extracted data."
            ),
            ScanPhase.REPORTING: (
                "Compile the full engagement report. Review every finding in the scan state. "
                "Call complete_scan with a comprehensive summary: severity, evidence, "
                "CVSS context, and remediation guidance for each finding."
            ),
        }

        sections = [
            "<role>",
            "You are KODIAK, an expert autonomous penetration testing AI.",
            f"Current date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Your knowledge cutoff is January 2025.",
            "You are the sole decision-maker for this security engagement.",
            "</role>",
            "",
            "<instructions>",
            "Before dispatching any tools, reason through these steps:",
            "1. PLAN: Review the scan state. Identify what phase objectives remain incomplete.",
            "2. SELECT: Choose the highest-value tools to run. Prefer parallel dispatch over sequential.",
            "3. VALIDATE: After results arrive, extract findings. Confirm whether the phase objective is satisfied.",
            "4. ADVANCE: If the phase is complete, say \"ADVANCE_PHASE\" in your reasoning to transition.",
            "5. PRIOR KNOWLEDGE: If <prior_knowledge> is present, treat attack_hint targets as the HIGHEST",
            "   priority. Investigate them in the current phase before moving to fresh discovery targets.",
            "   Known hosts with attack_hints often have sibling vulnerabilities — do not skip them.",
            "</instructions>",
            "",
            "<constraints>",
            "- Dispatch MULTIPLE tools in a single response — they execute concurrently.",
            "- Never repeat a tool on the same target with identical parameters.",
            "- Risk tiers (low → high): subdomain/port discovery → web probing/crawling → vulnerability scanning → sqlmap/wpscan/commix/exploitation.",
            "  Only escalate to the next risk tier after confirming findings at the current tier.",
            "- Timed-out tools: retry once with reduced scope (fewer ports, smaller wordlist). If it times out again, skip it.",
            "- Reasoning: 3–4 lines maximum. State which tools you are dispatching and why.",
            "- Do NOT call complete_scan until you are in the REPORTING phase.",
            "- CRITICAL: Tool invocations MUST use the function-calling interface ONLY.",
            "  NEVER write tool calls as text (e.g. \"[tool_call] ffuf args=...\"). Text patterns are NOT executed.",
            "  If you find yourself writing tool names in your reasoning, STOP and use function calls instead.",
            "</constraints>",
            "",
            "<phase_rules>",
            f"Current phase: {phase.value.upper()}",
            f"Objective: {phase_objectives.get(phase, '')}",
            "",
            "Phase order (strictly enforced): RECON → ENUMERATION → VULN_SCAN → EXPLOITATION → REPORTING",
            "To advance to the next phase: include \"ADVANCE_PHASE\" in your reasoning text.",
            "Phase transitions are manual — the system does NOT advance automatically.",
            "",
            "Hard phase guards (system-enforced — do NOT attempt before the required phase):",
            "  nuclei, nikto, wpscan → require VULN_SCAN phase",
            "  sqlmap, commix, searchsploit → require EXPLOITATION phase",
            "Calling these tools in an earlier phase returns a rejection message. Complete phase objectives first.",
            "If you want to run nuclei/wpscan/nikto but are NOT yet in VULN_SCAN:",
            "  Do NOT write them as text or attempt function calls. Instead:",
            "  - Complete remaining enumeration (ffuf unprobed subdomains, system_execute API checks on GitLab)",
            "  - Then say ADVANCE_PHASE when enumeration objectives are met.",
            "",
            "EXPLOITATION phase requirement: Do NOT say ADVANCE_PHASE until at least one of sqlmap, commix,",
            "or wpscan has returned a result against a confirmed injection point. If the target is not",
            "susceptible to exploitation, call save_note(category='dead_end') documenting why, then advance.",
            "</phase_rules>",
            "",
            "<scan_state>",
            self.scan_state.to_prompt_context(),
            "</scan_state>",
            "",
        ]

        # WAF/CDN context block — injected when a WAF is detected in scan state
        if self.scan_state.waf_detected:
            sections.extend([
                "<waf_context>",
                "WAF/CDN DETECTED. The adjustments below apply to HTTP-based tools ONLY (ffuf, katana, nuclei).",
                "nmap is TCP-level and is NOT affected by WAFs — scan with your normal full port range.",
                "",
                "HTTP tool adjustments:",
                "- ffuf: Do NOT run broad directory fuzzing against the primary CDN-fronted domain.",
                "  Cloudflare returns 503 for all requests and the result is instant/empty (wasted tool slot).",
                "  Only fuzz subdomains that bypass the CDN (staging, prelive, dev, test, db).",
                "  Use threads=5 and -mc 200,201,204,301,302 to match only success/redirect codes.",
                "- katana: use rate_limit=10. Use depth=1 on large platforms (GitLab, PrestaShop)",
                "  to avoid timeouts — these have deep link trees that exhaust the crawl budget.",
                "- nuclei: use rate_limit=20.",
                "</waf_context>",
                "",
            ])

        # Prior engagement knowledge (from previous scans of this project)
        if self._prior_knowledge:
            sections.append(self._prior_knowledge)
            sections.append("")

        sections.extend([
            "<recording_tools>",
            "You have two tools for persisting knowledge across scans:",
            "",
            "save_note — Record observations that help in future scans:",
            "  - recon_intel: discovered infrastructure (staging servers, CDNs, internal hostnames)",
            "  - behavioral: WAF/rate-limit behavior, server quirks, timing patterns",
            "  - attack_hint: promising attack surface worth deeper investigation next time",
            "  - dead_end: paths that wasted time (skip these in future scans)",
            "  - general: any other observation worth remembering",
            "",
            "save_finding — Record confirmed vulnerabilities with full detail:",
            "  - Call as SOON as a vulnerability is confirmed — do not wait for REPORTING",
            "  - Include: exploitation_steps, impact, poc (proof-of-concept), remediation",
            "  - Duplicate findings (same title + target) are automatically skipped",
            "  Severity anchors:",
            "    critical — RCE, authentication bypass, full DB dump, direct code execution evidence",
            "    high     — Exposed credentials (ANY password, even 'password'), LFI, confirmed SQLi, open admin panel",
            "    medium   — phpinfo() exposure, .git exposed, SSRF potential, partial information disclosure",
            "    low      — Version disclosure only, minor info leak with no direct attack path",
            "",
            "Use these tools proactively throughout the scan, not just at the end.",
            "</recording_tools>",
            "",
            "<task>",
            f"Based on the scan state above, dispatch the most impactful tools for the {phase.value.upper()} phase.",
            "Prioritise breadth in RECON and ENUMERATION. Prioritise precision and depth in VULN_SCAN and EXPLOITATION.",
            "</task>",
        ])

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Tool preparation
    # ------------------------------------------------------------------

    def _prepare_tools(self, allowed_tools: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Build OpenAI-format tool definitions for the LLM."""
        all_tools = self.tool_inventory.get_all_tools()
        tools_for_llm: List[Dict[str, Any]] = []

        for name, tool in all_tools.items():
            # Skip blackboard and orchestration tools — Manager doesn't need them
            if name.startswith("blackboard_") or name.startswith("orchestrate_"):
                continue
            if allowed_tools and name not in allowed_tools:
                continue
            tools_for_llm.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.description,
                    "parameters": tool.parameters_schema,
                },
            })

        return tools_for_llm

    # ------------------------------------------------------------------
    # Observation — update scan state from worker results
    # ------------------------------------------------------------------

    def _observe(self, result: WorkerResult) -> None:
        """Ingest a WorkerResult into the ScanState."""
        status = "success" if result.success else ("timeout" if "timed out" in (result.error or "") else "error")

        self.scan_state.record_tool_result(
            tool=result.tool_name,
            target=result.target,
            status=status,
            summary=result.summary,
        )

        # Extract structured intel from tool output
        self._extract_intel(result)

        # Check for phase advancement signal in accumulated data
        # (Phase is advanced when Manager says ADVANCE_PHASE in its reasoning)

    def _extract_intel(self, result: WorkerResult) -> None:
        """Parse tool output to enrich ScanState targets and findings."""
        if not result.success:
            return

        output = result.output
        data = result.data or {}

        # -- Port / service discovery (nmap) --
        if result.tool_name == "nmap":
            ts = self.scan_state.ensure_target(result.target)
            for line in output.splitlines():
                port_match = re.match(r"(\d+)/tcp\s+open\s+(.*)", line)
                if port_match:
                    port = int(port_match.group(1))
                    service = port_match.group(2).strip()
                    if port not in ts.ports:
                        ts.ports.append(port)
                    ts.services[port] = service

        # -- Subdomain discovery (subfinder) --
        elif result.tool_name == "subfinder":
            for line in output.splitlines():
                host = line.strip()
                if host and "." in host:
                    self.scan_state.ensure_target(host)

        # -- HTTP probing (httpx) --
        elif result.tool_name == "httpx":
            for line in output.splitlines():
                url = line.strip()
                if url.startswith("http"):
                    # Extract hostname
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    if parsed.hostname:
                        ts = self.scan_state.ensure_target(parsed.hostname)
                        if url not in ts.urls:
                            ts.urls.append(url)

        # -- Technology fingerprinting (whatweb) --
        elif result.tool_name == "whatweb":
            ts = self.scan_state.ensure_target(result.target)
            tech_pattern = re.compile(r"\[([^\]]+)\]")
            for match in tech_pattern.finditer(output[:2000]):
                tech = match.group(1).strip()
                if tech and tech not in ts.technologies and len(tech) < 60:
                    ts.technologies.append(tech)
            # Detect WAF/CDN presence
            if not self.scan_state.waf_detected and re.search(
                r'\bcloudflare\b|\bcloud ?flare\b|\bwaf\b|\bakamai\b|\bfastly\b|\bimperva\b',
                output, re.IGNORECASE
            ):
                self.scan_state.waf_detected = True

        # -- Vulnerability findings (nuclei, sqlmap, wpscan, commix) --
        elif result.tool_name in ("nuclei", "sqlmap", "wpscan", "commix"):
            self._extract_findings(result)

    def _extract_findings(self, result: WorkerResult) -> None:
        """Extract security findings from scanner output."""
        output = result.output
        data = result.data or {}

        if result.tool_name == "nuclei":
            for line in output.splitlines():
                if any(sev in line.lower() for sev in ("critical", "high", "medium", "low", "info")):
                    severity = "info"
                    for s in ("critical", "high", "medium", "low"):
                        if s in line.lower():
                            severity = s
                            break
                    self.scan_state.add_finding(
                        title=line.strip()[:200],
                        severity=severity,
                        target=result.target,
                        evidence=line.strip()[:300],
                        tool="nuclei",
                    )

        elif result.tool_name == "sqlmap":
            if data.get("vulnerable") or "injectable" in output.lower() or "parameter" in output.lower():
                self.scan_state.add_finding(
                    title=f"SQL Injection on {result.target}",
                    severity="high",
                    target=result.target,
                    evidence=output[:300],
                    tool="sqlmap",
                )

        elif result.tool_name == "wpscan":
            vulnerabilities = data.get("vulnerabilities") or []
            if vulnerabilities:
                for vuln in vulnerabilities[:8]:
                    location = vuln.get("location", "WordPress component")
                    title = vuln.get("title", "WordPress vulnerability")
                    self.scan_state.add_finding(
                        title=f"{title} ({location})",
                        severity="high",
                        target=result.target,
                        evidence=str(vuln.get("evidence", ""))[:300],
                        tool="wpscan",
                    )

        elif result.tool_name == "commix":
            if "injectable" in output.lower() or "command injection" in output.lower():
                self.scan_state.add_finding(
                    title=f"Command Injection on {result.target}",
                    severity="critical",
                    target=result.target,
                    evidence=output[:300],
                    tool="commix",
                )

    # ------------------------------------------------------------------
    # In-process tool handlers (save_note, save_finding)
    # ------------------------------------------------------------------

    async def _handle_in_process_tool(
        self,
        tool_name: str,
        args: Dict[str, Any],
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> str:
        """Handle save_note / save_finding: persist to DB, return confirmation text."""
        try:
            if tool_name == "save_note":
                return await self._handle_save_note(args, session, project_id, scan_id)
            elif tool_name == "save_finding":
                return await self._handle_save_finding(args, session, project_id, scan_id)
            return f"Unknown in-process tool: {tool_name}"
        except Exception as exc:
            logger.warning(f"Failed to handle {tool_name}: {exc}")
            return f"Error saving {tool_name}: {exc}"

    async def _handle_save_note(
        self,
        args: Dict[str, Any],
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> str:
        target = str(args.get("target", "*")).strip()
        raw_category = str(args.get("category", "general")).strip().lower()
        content = str(args.get("content", "")).strip()

        try:
            category = NoteCategory(raw_category)
        except ValueError:
            category = NoteCategory.GENERAL

        note = EngagementNote(
            project_id=project_id,
            scan_id=scan_id,
            category=category,
            target=target,
            content=content[:2000],
        )
        await crud.note.create(session, note)
        logger.info(f"📝 Note saved [{category.value}]: {content[:80]}")

        if self.event_manager:
            try:
                await self.event_manager.emit_note_saved(
                    category=category.value,
                    target=target,
                    preview=content[:100],
                    scan_id=str(scan_id),
                )
            except Exception:
                pass

        return f"Note saved: [{category.value}] {content[:120]}"

    async def _handle_save_finding(
        self,
        args: Dict[str, Any],
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> str:
        target = str(args.get("target", "")).strip()
        title = str(args.get("title", "Untitled")).strip()
        raw_severity = str(args.get("severity", "info")).strip().lower()

        try:
            severity = FindingSeverity(raw_severity)
        except ValueError:
            severity = FindingSeverity.INFO

        # Dedup: check if this finding already exists for this project
        existing = await crud.finding.find_by_title_and_target(
            session, project_id, title, target,
        )
        if existing:
            logger.info(f"🔄 Finding already exists, skipping: {title}")
            return f"Finding already recorded: {title} (skipped duplicate)"

        finding = Finding(
            project_id=project_id,
            scan_id=scan_id,
            target=target,
            title=title,
            description=str(args.get("description", "")).strip()[:4000],
            severity=severity,
            tool=str(args.get("tool", "")).strip() or None,
            vulnerability_type=str(args.get("vulnerability_type", "")).strip() or None,
            exploitation_steps=str(args.get("exploitation_steps", "")).strip()[:4000] or None,
            impact=str(args.get("impact", "")).strip()[:2000] or None,
            poc=str(args.get("poc", "")).strip()[:4000] or None,
            remediation=str(args.get("remediation", "")).strip()[:2000] or None,
        )
        await crud.finding.create(session, finding)

        # Also record in scan state for prompt context
        self.scan_state.add_finding(
            title=title,
            severity=raw_severity,
            target=target,
            evidence=str(args.get("poc", ""))[:300],
            tool=str(args.get("tool", "")),
        )

        logger.info(f"🎯 Finding saved [{severity.value}]: {title}")

        if self.event_manager:
            try:
                await self.event_manager.emit_finding_saved(
                    title=title,
                    severity=severity.value,
                    target=target,
                    scan_id=str(scan_id),
                )
            except Exception:
                pass

        return f"Finding saved: [{severity.value.upper()}] {title}"

    # ------------------------------------------------------------------
    # Prior knowledge loading
    # ------------------------------------------------------------------

    async def _load_prior_knowledge(
        self,
        session: Any,
        project_id: UUID,
    ) -> tuple[str, int, int]:
        """Load prior notes and findings for this project.

        Returns (xml_block, notes_count, findings_count).
        """
        try:
            notes = await crud.note.list_for_project(session, project_id, limit=30)
            findings = await crud.finding.list_for_project(session, project_id, limit=20)
        except Exception as exc:
            logger.warning(f"Failed to load prior knowledge: {exc}")
            return "", 0, 0

        if not notes and not findings:
            return "", 0, 0

        lines: List[str] = ["<prior_knowledge>"]

        if notes:
            lines.append(f"<prior_notes count=\"{len(notes)}\">")
            for n in reversed(notes):  # oldest first
                date = n.created_at.strftime("%Y-%m-%d") if n.created_at else "?"
                lines.append(f"  [{date} {n.category.value}] ({n.target}) {n.content[:200]}")
            lines.append("</prior_notes>")

        if findings:
            lines.append(f"<prior_findings count=\"{len(findings)}\">")
            for f in reversed(findings):  # oldest first
                sev = f.severity.value.upper() if f.severity else "INFO"
                target = f.target or "?"
                desc = (f.description or "")[:100]
                remediation = f"  Remediation: {f.remediation[:80]}" if f.remediation else ""
                lines.append(f"  [{sev}] {f.title} — {target}")
                if desc:
                    lines.append(f"    {desc}")
                if remediation:
                    lines.append(f"    {remediation}")
            lines.append("</prior_findings>")

        lines.append("</prior_knowledge>")

        block = "\n".join(lines)
        # Hard cap at ~12K chars (~3000 tokens)
        if len(block) > 12000:
            block = block[:11997] + "..."
        return block, len(notes), len(findings)

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def _build_tool_history(self, result: WorkerResult) -> str:
        """Compact tool output for conversation history."""
        parts: List[str] = []

        # Truncated raw output
        output = result.output
        if len(output) > 3500:
            output = output[:3497] + "..."
        if output:
            parts.append(output)

        # Key evidence lines
        evidence = self._extract_key_evidence(output)
        if evidence:
            evidence_block = "\n".join(f"- {line}" for line in evidence[:6])
            parts.append(f"[tool_evidence]\n{evidence_block}\n[/tool_evidence]")

        # Compact data
        data = result.data
        if data:
            preferred_keys = ("exit_code", "vulnerable", "total_found", "summary", "url", "status", "command")
            compact = {k: data[k] for k in preferred_keys if k in data}
            if not compact:
                compact = {k: v for k, v in list(data.items())[:3] if isinstance(v, (str, int, float, bool))}
            if compact:
                cj = json.dumps(compact, sort_keys=True, default=str, separators=(",", ":"))
                if len(cj) > 700:
                    cj = cj[:697] + "..."
                parts.append(f"[tool_data]{cj}[/tool_data]")

        # Status / error
        if result.error:
            parts.append(f"[error]{result.error[:200]}[/error]")

        parts.append(f"[duration]{result.duration_seconds:.1f}s[/duration]")

        return "\n\n".join(parts).strip()

    @staticmethod
    def _extract_key_evidence(output: str) -> List[str]:
        """Pull the most informative lines from raw tool output."""
        if not output:
            return []

        important = re.compile(
            r"\b(vulnerab|cve-|open|found|severity|critical|high|timeout|error|failed|"
            r"status|database|privilege|payload|login|rce|sqli|xss|200|301|302|403)\b",
            re.IGNORECASE,
        )
        seen: set[str] = set()
        evidence: List[str] = []

        for raw in output.splitlines():
            line = " ".join(raw.split()).strip()
            if not line:
                continue
            if len(line) > 180:
                line = line[:177] + "..."
            if important.search(line) and line.lower() not in seen:
                evidence.append(line)
                seen.add(line.lower())
            if len(evidence) >= 6:
                break

        if not evidence:
            for raw in output.splitlines():
                line = " ".join(raw.split()).strip()
                if not line or line.lower() in seen:
                    continue
                if len(line) > 180:
                    line = line[:177] + "..."
                evidence.append(line)
                seen.add(line.lower())
                if len(evidence) >= 3:
                    break

        return evidence

    def _trim_history(self, history: List[Dict[str, Any]], max_turns: int = 40) -> List[Dict[str, Any]]:
        """Keep the first user message and the most recent turns."""
        if len(history) <= max_turns:
            return history
        # Always keep the initial scan_request
        head = history[:1]
        tail = history[-(max_turns - 1):]
        return head + tail

    # ------------------------------------------------------------------
    # Phase advancement
    # ------------------------------------------------------------------

    async def _check_phase_advance(self, assistant_text: str, scan_id: str) -> bool:
        """Check if the Manager explicitly requested a phase advance."""
        if not assistant_text:
            return False
        if "ADVANCE_PHASE" in assistant_text.upper():
            old_phase = self.scan_state.phase.value
            advanced = self.scan_state.advance_phase()
            if advanced:
                new_phase = self.scan_state.phase.value
                logger.info(f"📍 Phase advanced to: {new_phase}")
                if self.event_manager:
                    try:
                        await self.event_manager.emit_phase_advanced(
                            old_phase=old_phase,
                            new_phase=new_phase,
                            scan_id=scan_id,
                        )
                    except Exception:
                        pass
            return advanced
        return False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    async def _persist_attempt(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        result: WorkerResult,
    ) -> None:
        """Write an attempt record to the database."""
        try:
            status = "success" if result.success else "failed"
            if result.error and "timed out" in result.error.lower():
                status = "timeout"

            await crud.attempt.create(
                session=session,
                attempt=Attempt(
                    project_id=project_id,
                    scan_id=scan_id,
                    tool=result.tool_name,
                    target=result.target,
                    status=status,
                    reason=result.error,
                    properties={
                        "agent_id": "manager",
                        "duration_seconds": result.duration_seconds,
                        "task_id": result.task_id,
                    },
                ),
            )
        except Exception as exc:
            logger.warning(f"Failed to persist attempt for {result.tool_name}: {exc}")

    async def _persist_final_findings(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Emit finding events and persist auto-extracted findings to DB."""
        if not self.scan_state:
            return
        for finding in self.scan_state.findings:
            try:
                await self.event_manager.emit_finding_discovered(
                    finding={
                        "title": finding.title,
                        "severity": finding.severity,
                        "target": finding.target,
                        "evidence": finding.evidence,
                        "tool": finding.tool,
                    },
                    agent_id="manager",
                    scan_id=str(scan_id),
                )
            except Exception as exc:
                logger.warning(f"Failed to emit finding event: {exc}")

            # Persist auto-extracted finding to DB with dedup check
            try:
                existing = await crud.finding.find_by_title_and_target(
                    session, project_id, finding.title, finding.target
                )
                if not existing:
                    try:
                        sev_enum = FindingSeverity(finding.severity.lower())
                    except ValueError:
                        sev_enum = FindingSeverity.INFO
                    db_finding = Finding(
                        project_id=project_id,
                        scan_id=scan_id,
                        target=finding.target,
                        title=finding.title,
                        description=finding.evidence[:4000] if finding.evidence else "",
                        severity=sev_enum,
                        tool=finding.tool or None,
                        raw_evidence=finding.evidence[:2000] if finding.evidence else None,
                    )
                    await crud.finding.create(session, db_finding)
            except Exception as exc:
                logger.warning(f"Failed to persist auto-extracted finding '{finding.title}': {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_call_to_dict(tool_call: Any) -> Dict[str, Any]:
        """Normalise a GeminiToolCall into a plain dict."""
        if isinstance(tool_call, dict):
            return tool_call
        if hasattr(tool_call, "model_dump"):
            return tool_call.model_dump()
        function = getattr(tool_call, "function", None)
        return {
            "id": str(getattr(tool_call, "id", f"call_{uuid4().hex[:12]}")),
            "type": "function",
            "function": {
                "name": str(getattr(function, "name", "")),
                "arguments": str(getattr(function, "arguments", "{}")),
            },
        }

    @staticmethod
    def _parse_args(raw: Any) -> Dict[str, Any]:
        """Parse tool arguments from string or dict."""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

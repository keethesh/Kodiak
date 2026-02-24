"""
Manager Agent — single LLM brain using structured output for Kodiak scans.

Architecture (structured output, no function calling):
  1. LLM returns a JSON `KodiakResponse` with commands[], findings[], notes[], etc.
  2. Commands are executed in parallel via Docker (bash -c).
  3. Findings and notes are persisted to the database by the orchestrator.
  4. Scan state is updated from the LLM's `discoveries` field.
  5. Phase advancement and scan completion are driven by `phase_action`.
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
from kodiak.core.response_schema import (
    Command,
    KodiakResponse,
    PhaseAction,
)
from kodiak.core.scan_state import ScanPhase, ScanState
from kodiak.core.tools.inventory import ToolInventory
from kodiak.core.worker import CommandResult, CommandTask, dispatch_commands
from kodiak.database import crud
from kodiak.database.models import Attempt, EngagementNote, Finding, NoteCategory, FindingSeverity
from kodiak.services import llm
from kodiak.services.gemini_client import GeminiClient, GeminiResponse


# ---------------------------------------------------------------------------
# Result container
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

    Uses structured output (no function calling):
      think    → LLM returns KodiakResponse JSON (commands, findings, notes, phase_action)
      execute  → run commands in parallel via Docker
      observe  → update ScanState from discoveries + command results
      persist  → write findings/notes/attempts to DB
      repeat   → until phase_action=complete or budget exhausted
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
        self.scan_state.ensure_target(target)

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
                        "Set phase_action to 'complete' with a scan_summary NOW.</final_warning>"
                    ),
                })

            # 1. THINK -------------------------------------------------------
            response = await self._think(history, iteration, scan_id_str)

            if response is None:
                history.append({"role": "assistant", "content": '{"analysis":"Error: empty response","commands":[],"phase_action":"continue"}'})
                history.append({
                    "role": "user",
                    "content": "<retry>Previous call failed. Output valid JSON with commands.</retry>",
                })
                continue

            # Emit thought for TUI
            if response.content and self.event_manager:
                try:
                    await self.event_manager.emit_agent_thought(
                        agent_id="manager",
                        thought=response.content[:500],
                        scan_id=scan_id_str,
                    )
                except Exception:
                    pass

            # 2. PARSE STRUCTURED RESPONSE ------------------------------------
            kodiak_resp = self._parse_kodiak_response(response.content)

            if kodiak_resp is None:
                history.append({"role": "assistant", "content": response.content or ""})
                history.append({
                    "role": "user",
                    "content": (
                        "<retry>Your response was not valid JSON matching the schema. "
                        "Output a JSON object with: analysis, commands[], discoveries, "
                        "findings[], notes[], phase_action.</retry>"
                    ),
                })
                continue

            # Record assistant response in history
            history.append({"role": "assistant", "content": response.content})

            # 3. PROCESS DISCOVERIES ------------------------------------------
            self._apply_discoveries(kodiak_resp)

            # 4. PERSIST FINDINGS & NOTES -------------------------------------
            for finding in kodiak_resp.findings:
                await self._persist_finding(finding, session, project_id, scan_id)

            for note in kodiak_resp.notes:
                await self._persist_note(note, session, project_id, scan_id)

            # 5. HANDLE PHASE ACTION ------------------------------------------
            if kodiak_resp.phase_action == PhaseAction.COMPLETE:
                summary = kodiak_resp.scan_summary or "Scan completed"
                if self.scan_state.phase != ScanPhase.REPORTING:
                    # Force advance through remaining phases
                    while self.scan_state.phase != ScanPhase.REPORTING:
                        self.scan_state.advance_phase()

                await self._persist_final_findings(session, project_id, scan_id)

                logger.info(f"✅ Manager scan complete: {summary}")
                return ManagerResult(
                    status="completed",
                    summary=summary,
                    findings_count=self.scan_state.findings_count,
                    iterations=iteration,
                )

            if kodiak_resp.phase_action == PhaseAction.ADVANCE:
                old_phase = self.scan_state.phase.value
                advanced = self.scan_state.advance_phase()
                if advanced:
                    new_phase = self.scan_state.phase.value
                    logger.info(f"📍 Phase advanced: {old_phase} → {new_phase}")
                    if self.event_manager:
                        try:
                            await self.event_manager.emit_phase_advanced(
                                old_phase=old_phase,
                                new_phase=new_phase,
                                scan_id=scan_id_str,
                            )
                        except Exception:
                            pass

            # 6. EXECUTE COMMANDS ---------------------------------------------
            if kodiak_resp.commands:
                tasks = [
                    CommandTask(
                        command=cmd.command,
                        rationale=cmd.rationale,
                        timeout=cmd.timeout,
                    )
                    for cmd in kodiak_resp.commands
                ]

                results = await dispatch_commands(
                    commands=tasks,
                    event_manager=self.event_manager,
                    scan_id=scan_id_str,
                    global_concurrency=settings.global_tool_concurrency,
                )

                # Persist attempts to DB
                for cr in results:
                    await self._persist_command_attempt(
                        session, project_id, scan_id, cr
                    )

                # Build command results message for next iteration
                results_text = self._format_command_results(results)
                history.append({
                    "role": "user",
                    "content": results_text,
                })
            else:
                # No commands — nudge the LLM to act
                history.append({
                    "role": "user",
                    "content": (
                        "<next_step>No commands were dispatched. "
                        "Output commands to continue the scan, or set phase_action "
                        "to 'complete' with a scan_summary.</next_step>"
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
        """Single LLM call: system prompt + history → structured KodiakResponse JSON."""

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
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                thinking_level=thinking_level,
                response_schema=KodiakResponse,
            )
            return response if response else None
        except Exception as exc:
            logger.error(f"Manager think() failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _build_system_prompt(self) -> str:
        """
        Construct the Manager's system prompt optimized for Gemini 3:
        - Concise, direct instructions (Gemini 3 over-analyses verbose prompts)
        - XML-tagged sections for clear structure
        - Tool catalog described as text (no function declarations)
        - Context (scan state) placed before the task
        - Task anchored at the very end
        """
        assert self.scan_state is not None

        phase = self.scan_state.phase

        phase_objectives = {
            ScanPhase.RECON: (
                "Discover the full attack surface: subdomains, open ports, "
                "and technology fingerprints. Dispatch multiple recon commands in parallel."
            ),
            ScanPhase.ENUMERATION: (
                "Map services on live hosts: probe HTTP endpoints, crawl for URLs, "
                "fuzz for hidden directories. Prioritize hosts with exposed web services. "
                "Focus on subdomains that suggest dev/staging/admin environments."
            ),
            ScanPhase.VULN_SCAN: (
                "Identify exploitable vulnerabilities: run nuclei templates, "
                "test for injection points, check for known CVEs matching discovered versions."
            ),
            ScanPhase.EXPLOITATION: (
                "Confirm and exploit vulnerabilities: run sqlmap/commix on injection points, "
                "gather proof-of-concept evidence, extract data where possible."
            ),
            ScanPhase.REPORTING: (
                "Compile all findings. Set phase_action='complete' with a comprehensive "
                "scan_summary covering all discovered vulnerabilities."
            ),
        }

        sections = [
            "<role>",
            "You are KODIAK, an expert autonomous penetration tester.",
            f"Current date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}. Knowledge cutoff: January 2025.",
            "</role>",
            "",
            "<instructions>",
            "For each iteration, reason through these steps:",
            "1. ANALYZE: Review scan state and previous command results. What is known? What is unknown?",
            "2. CORRELATE: Connect findings across commands — a version string suggests specific CVEs,",
            "   an exposed .git means source code review, an error message leaks internal paths.",
            "3. PRIORITIZE: Rank targets by attack surface. Focus on what's most likely exploitable.",
            "4. ACT: Output shell commands to run in the Docker sandbox (they execute in parallel).",
            "   For every command, explain your rationale.",
            "5. ADAPT: If a command fails or a WAF blocks you, change approach.",
            "   Try different encoding, flags, alternative tools, or creative workarounds.",
            "   Do not repeat the same failed command.",
            "",
            "If <prior_knowledge> is present, treat attack_hint targets as highest priority.",
            "Known hosts with attack_hints often have sibling vulnerabilities.",
            "</instructions>",
            "",
            "<constraints>",
            "- Output MULTIPLE commands per iteration — they run concurrently.",
            "- Never repeat a command with identical arguments.",
            "- Risk tiers (escalate only after findings at current tier):",
            "  low: subdomain/port discovery → medium: web probing/crawling/vuln scanning → high: exploitation.",
            "- Timed-out commands: retry once with reduced scope. If it times out again, record a dead_end note.",
            "- Phase order: RECON → ENUMERATION → VULN_SCAN → EXPLOITATION → REPORTING.",
            "  Set phase_action='advance' when the current phase objective is met.",
            "  Set phase_action='complete' with scan_summary when all testing is done.",
            "</constraints>",
            "",
            "<tool_catalog>",
            "All tools are pre-installed in a Kali-based Docker sandbox. Use any bash command.",
            "",
            "## Reconnaissance",
            "- `subfinder -d <domain> -silent` — Passive subdomain enumeration",
            "- `nmap -sV -sC -p <ports> <target>` — Port scan + service detection. Use -p- for all ports, -T4 for speed.",
            "- `httpx -l <file> -sc -title -tech-detect` — HTTP probe with status codes and tech detection",
            "- `whatweb <url>` — Web technology fingerprinting (CMS, frameworks, server)",
            "- `dig <domain> ANY`, `host <domain>`, `whois <domain>` — DNS and WHOIS recon",
            "",
            "## Web Crawling & Fuzzing",
            "- `katana -u <url> -d <depth> -silent` — Crawl websites for endpoints. Use -jc for JS, -rl <n> for rate limit.",
            "- `ffuf -u <url>/FUZZ -w <wordlist> -mc 200,301,302 -t <threads>` — Directory/file fuzzing",
            "  Wordlists: /usr/share/seclists/Discovery/Web-Content/common.txt (fast), big.txt (thorough)",
            "",
            "## Vulnerability Scanning",
            "- `nuclei -u <url> -rl <rate> -silent` — Template-based vuln scanner. Tags: -tags cve,sqli,xss,lfi,rce. Severity: -s critical,high,medium",
            "- `nikto -h <url>` — Web server misconfiguration scanner",
            "- `wpscan --url <url> -e vp,vt,u --api-token $WPSCAN_API_TOKEN` — WordPress vuln scanner",
            "",
            "## Exploitation",
            "- `sqlmap -u <url> --data=<post> --batch --level=3 --risk=2` — SQL injection. Use --dump, --os-shell, --technique=BEUSTQ",
            "- `commix --url=<url> --data=<post> --batch` — OS command injection",
            "- `searchsploit <query>` — Offline Exploit-DB search. Use after identifying service versions.",
            "",
            "## General Purpose",
            "- `curl -s -I <url>` — HTTP requests with full header control. Use for WAF bypass, path traversal, custom headers.",
            "- Any standard Linux command: grep, awk, sed, wget, python3, etc.",
            "</tool_catalog>",
            "",
        ]

        # WAF/CDN context
        if self.scan_state.waf_detected:
            sections.extend([
                "<waf_context>",
                "WAF/CDN detected. Adapt your approach — do not abandon testing.",
                "- Discover origin IPs: check DNS history, try direct IP access, check non-HTTP ports.",
                "- Target bypass subdomains: staging/dev/prelive servers often skip WAF.",
                "- Rate-limit HTTP tools: ffuf -t 5, katana -rl 10, nuclei -rl 20.",
                "- nmap is TCP-level — NOT affected by WAFs. Scan full port range.",
                "- Use curl for manual probing with encoding tricks, path normalization, custom headers.",
                "- Try HTTP/1.0, unusual methods (HEAD, OPTIONS), or chunk transfer encoding.",
                "- Do NOT waste commands on broad fuzzing against CDN-fronted domains (returns 503).",
                "</waf_context>",
                "",
            ])

        # Skills injection
        skills_text = self._load_skills()
        if skills_text:
            sections.append(skills_text)
            sections.append("")

        # Prior engagement knowledge
        if self._prior_knowledge:
            sections.append(self._prior_knowledge)
            sections.append("")

        # Recording guidance
        sections.extend([
            "<recording>",
            "Use the `findings` array to record confirmed vulnerabilities with evidence and remediation.",
            "Use the `notes` array to record observations for future scans:",
            "  - recon_intel: infrastructure details (staging servers, CDNs, internal hostnames)",
            "  - behavioral: WAF behavior, rate limits, server quirks",
            "  - attack_hint: promising attack surface for deeper testing",
            "  - dead_end: paths that wasted time — skip these next time",
            "Severity anchors:",
            "  critical — RCE, auth bypass, full DB dump, direct code execution",
            "  high — Exposed credentials, LFI, confirmed SQLi, open admin panel",
            "  medium — phpinfo(), .git exposed, SSRF potential",
            "  low — Version disclosure, minor info leak",
            "</recording>",
            "",
        ])

        # Scan state (context before task — Gemini 3 best practice)
        sections.extend([
            "<scan_state>",
            self.scan_state.to_prompt_context(),
            "</scan_state>",
            "",
        ])

        # Task at the very end (context-before-task pattern)
        sections.extend([
            "<task>",
            f"Current phase: {phase.value.upper()}. Objective: {phase_objectives.get(phase, '')}",
            "Based on the scan state above, output the most impactful commands for this phase.",
            "Prioritise breadth in RECON/ENUMERATION. Prioritise depth in VULN_SCAN/EXPLOITATION.",
            "For each command, explain your rationale.",
            "</task>",
        ])

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Skills injection
    # ------------------------------------------------------------------

    def _load_skills(self) -> str:
        """Load relevant skills based on detected technologies in scan state."""
        try:
            from kodiak.skills.skill_loader import skill_loader

            target_info: Dict[str, Any] = {
                "technologies": [],
                "services": [],
                "ports": [],
            }

            if self.scan_state:
                for ts in self.scan_state.targets.values():
                    target_info["technologies"].extend(ts.technologies)
                    target_info["ports"].extend(ts.ports)
                    target_info["services"].extend(list(ts.services.values()))

            suggested = skill_loader.suggest_skills_for_target(target_info)
            if suggested:
                # Limit to 3 skills to keep prompt concise (Gemini 3 best practice)
                return skill_loader.load_skills_for_agent(suggested, max_skills=3)
            return ""
        except Exception as exc:
            logger.debug(f"Skills loading skipped: {exc}")
            return ""

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_kodiak_response(self, content: str) -> Optional[KodiakResponse]:
        """Parse the LLM's JSON response into a KodiakResponse."""
        if not content:
            return None

        try:
            data = json.loads(content)
            return KodiakResponse.model_validate(data)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning(f"Failed to parse KodiakResponse: {exc}")
            # Try to extract JSON from markdown code block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                    return KodiakResponse.model_validate(data)
                except Exception:
                    pass
            return None

    # ------------------------------------------------------------------
    # Discovery processing
    # ------------------------------------------------------------------

    def _apply_discoveries(self, resp: KodiakResponse) -> None:
        """Update ScanState from the LLM's structured discoveries."""
        disc = resp.discoveries
        if not disc:
            return

        for host in disc.hosts:
            if host and "." in host:
                self.scan_state.ensure_target(host)

        for host, ports in disc.ports.items():
            ts = self.scan_state.ensure_target(host)
            for port in ports:
                if port not in ts.ports:
                    ts.ports.append(port)

        for host, techs in disc.technologies.items():
            ts = self.scan_state.ensure_target(host)
            for tech in techs:
                if tech and tech not in ts.technologies and len(tech) < 60:
                    ts.technologies.append(tech)
            # Detect WAF/CDN presence
            if not self.scan_state.waf_detected:
                for tech in techs:
                    if re.search(
                        r'\bcloudflare\b|\bwaf\b|\bakamai\b|\bfastly\b|\bimperva\b',
                        tech, re.IGNORECASE
                    ):
                        self.scan_state.waf_detected = True
                        break

        for url in disc.urls:
            if url.startswith("http"):
                from urllib.parse import urlparse
                parsed = urlparse(url)
                if parsed.hostname:
                    ts = self.scan_state.ensure_target(parsed.hostname)
                    if url not in ts.urls:
                        ts.urls.append(url)

    # ------------------------------------------------------------------
    # Command results formatting
    # ------------------------------------------------------------------

    def _format_command_results(self, results: List[CommandResult]) -> str:
        """Format command results as context for the next LLM iteration."""
        parts = ["<command_results>"]
        for cr in results:
            parts.append(cr.to_prompt_text())
            parts.append("")  # blank line separator
        parts.append("</command_results>")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Persistence — findings and notes
    # ------------------------------------------------------------------

    async def _persist_finding(
        self,
        finding,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Persist a structured finding from KodiakResponse to the database."""
        try:
            title = finding.title
            target = finding.target

            # Dedup check
            existing = await crud.finding.find_by_title_and_target(
                session, project_id, title, target,
            )
            if existing:
                logger.info(f"🔄 Finding already exists, skipping: {title}")
                return

            try:
                sev = FindingSeverity(finding.severity.value)
            except (ValueError, AttributeError):
                sev = FindingSeverity.INFO

            db_finding = Finding(
                project_id=project_id,
                scan_id=scan_id,
                target=target,
                title=title,
                description=finding.description[:4000],
                severity=sev,
                remediation=finding.remediation[:2000] if finding.remediation else None,
                raw_evidence=finding.evidence[:2000] if finding.evidence else None,
            )
            await crud.finding.create(session, db_finding)

            # Also record in scan state for prompt context
            self.scan_state.add_finding(
                title=title,
                severity=finding.severity.value,
                target=target,
                evidence=finding.evidence[:300] if finding.evidence else "",
            )

            logger.info(f"🎯 Finding saved [{finding.severity.value}]: {title}")

            if self.event_manager:
                try:
                    await self.event_manager.emit_finding_saved(
                        title=title,
                        severity=finding.severity.value,
                        target=target,
                        scan_id=str(scan_id),
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(f"Failed to persist finding '{finding.title}': {exc}")

    async def _persist_note(
        self,
        note,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
    ) -> None:
        """Persist a structured note from KodiakResponse to the database."""
        try:
            try:
                category = NoteCategory(note.category.value)
            except (ValueError, AttributeError):
                category = NoteCategory.GENERAL

            db_note = EngagementNote(
                project_id=project_id,
                scan_id=scan_id,
                category=category,
                target=note.target,
                content=note.content[:2000],
            )
            await crud.note.create(session, db_note)
            logger.info(f"📝 Note saved [{category.value}]: {note.content[:80]}")

            if self.event_manager:
                try:
                    await self.event_manager.emit_note_saved(
                        category=category.value,
                        target=note.target,
                        preview=note.content[:100],
                        scan_id=str(scan_id),
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(f"Failed to persist note: {exc}")

    async def _persist_command_attempt(
        self,
        session: Any,
        project_id: UUID,
        scan_id: UUID,
        result: CommandResult,
    ) -> None:
        """Write a command execution record to the database."""
        try:
            if result.timed_out:
                status = "timeout"
            elif result.exit_code == 0:
                status = "success"
            else:
                status = "failed"

            # Extract tool name from command (first word)
            tool_name = result.command.split()[0] if result.command.strip() else "cmd"

            # Extract target from command if possible
            target = "unknown"
            url_match = re.search(r'https?://[^\s\'"]+', result.command)
            domain_match = re.search(r'-[duh]\s+([^\s]+)', result.command) if not url_match else None
            if url_match:
                target = url_match.group(0)
            elif domain_match:
                target = domain_match.group(1)

            await crud.attempt.create(
                session=session,
                attempt=Attempt(
                    project_id=project_id,
                    scan_id=scan_id,
                    tool=tool_name,
                    target=target,
                    status=status,
                    reason=result.stderr[:300] if result.stderr else None,
                    properties={
                        "agent_id": "manager",
                        "duration_seconds": result.duration_seconds,
                        "command": result.command[:500],
                        "rationale": result.rationale[:300],
                        "exit_code": result.exit_code,
                    },
                ),
            )
        except Exception as exc:
            logger.warning(f"Failed to persist attempt: {exc}")

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
            lines.append(f'<prior_notes count="{len(notes)}">')
            for n in reversed(notes):  # oldest first
                date = n.created_at.strftime("%Y-%m-%d") if n.created_at else "?"
                lines.append(f"  [{date} {n.category.value}] ({n.target}) {n.content[:200]}")
            lines.append("</prior_notes>")

        if findings:
            lines.append(f'<prior_findings count="{len(findings)}">')
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

    def _trim_history(self, history: List[Dict[str, Any]], max_turns: int = 40) -> List[Dict[str, Any]]:
        """Keep the first user message and the most recent turns."""
        if len(history) <= max_turns:
            return history
        # Always keep the initial scan_request
        head = history[:1]
        tail = history[-(max_turns - 1):]
        return head + tail

    # ------------------------------------------------------------------
    # Final findings persistence
    # ------------------------------------------------------------------

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
    # Legacy helpers (kept for test compatibility)
    # ------------------------------------------------------------------

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

    def _check_phase_advance(self, assistant_text: str, scan_id: str = "") -> bool:
        """Check if the Manager explicitly requested a phase advance.
        
        Kept for backward compatibility with tests, but phase advancement
        is now driven by the structured phase_action field.
        """
        if not assistant_text:
            return False
        if "ADVANCE_PHASE" in assistant_text.upper():
            old_phase = self.scan_state.phase.value
            advanced = self.scan_state.advance_phase()
            if advanced:
                logger.info(f"📍 Phase advanced to: {self.scan_state.phase.value}")
            return advanced
        return False

"""
Analyst Agent — deep security brain for the multi-agent pipeline.

The Analyst does NOT dispatch tools. It receives completed work unit results,
performs deep vulnerability analysis, and outputs:
  - Findings (confirmed vulnerabilities)
  - Notes (intelligence for other agents)
  - Directives (strategic instructions for the Planner)

Uses the powerful model (Claude Sonnet) for thorough analysis.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urlparse

from loguru import logger
from pydantic import BaseModel, Field

from kodiak.core.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from kodiak.core.config import settings
from kodiak.core.event_publisher import RuntimeEventPublisher
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.engine import get_session
from kodiak.database.models import (
    Capability,
    CapabilityType,
    DirectiveType,
    FindingSeverity,
    HypothesisType,
    NoteCategory,
    ObservationType,
    ScanEventType,
    WorkUnit,
)
from kodiak.services.litellm_client import LiteLLMClient

_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


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
    total_cost: float = 0.0


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
        instructions: str = "",
        event_manager: Optional[RuntimeEventPublisher] = None,
    ):
        self.store = store
        self._instructions = (instructions or "").strip()
        self.event_manager = event_manager
        self._llm = LiteLLMClient()
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost = 0.0
        self._cycle_count = 0
        self._stop_requested = False
        self._circuit_breaker = CircuitBreaker(
            name="analyst",
            config=CircuitBreakerConfig(
                failure_threshold=settings.failure_threshold,
            ),
        )

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

            # Process batch. Keep the Analyst alive if one batch hits an
            # unexpected persistence/parsing edge case.
            try:
                if self._circuit_breaker.is_open:
                    logger.warning("🧠 Analyst: circuit breaker open, skipping cycle")
                    await self._sleep(poll_interval)
                    continue

                if self._circuit_breaker.state == CircuitState.HALF_OPEN:
                    await self._record_component_recovered("Analyst recovered, testing with half-open circuit")

                result = await self._analyze_batch(unanalyzed)
                self._circuit_breaker.record_success()
            except Exception:
                self._cycle_count += 1
                logger.exception("Analyst batch processing failed")
                circuit_opened = self._circuit_breaker.record_failure()
                if circuit_opened:
                    await self._record_component_paused(
                        f"Analyst circuit breaker opened after {settings.failure_threshold} consecutive failures"
                    )
                idle_cycles = 0
                await self._sleep(poll_interval)
                continue

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

    async def _record_component_degraded(self, reason: str) -> None:
        async for session in get_session():
            await self.store.append_event(
                session,
                event_type=ScanEventType.COMPONENT_DEGRADED,
                entity_type="component",
                entity_id="analyst",
                payload={"component": "analyst", "reason": reason},
            )

    async def _record_component_recovered(self, reason: str = "Analyst resumed successful batch processing") -> None:
        async for session in get_session():
            await self.store.append_event(
                session,
                event_type=ScanEventType.COMPONENT_RECOVERED,
                entity_type="component",
                entity_id="analyst",
                payload={"component": "analyst", "reason": reason},
            )

    async def _record_component_paused(self, reason: str) -> None:
        async for session in get_session():
            await self.store.append_event(
                session,
                event_type=ScanEventType.COMPONENT_PAUSED,
                entity_type="component",
                entity_id="analyst",
                payload={"component": "analyst", "reason": reason},
            )

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

        instruction_context = self._instruction_context_block()
        user_segments = [segment for segment in [instruction_context, state_summary, user_content] if segment]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n\n".join(user_segments)},
        ]

        # Call LLM
        try:
            model = settings.get_analyst_model()
            api_key = settings.get_resolved_api_key()

            response = await self._llm.generate(
                model=model,
                system_prompt=system_prompt,
                messages=messages,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.error(f"Analyst LLM call failed: {exc}")
            return None

        if not response or not response.content:
            return None

        # Track tokens and cost
        self._total_input_tokens += response.input_tokens
        self._total_output_tokens += response.output_tokens
        self._total_cost += response.response_cost

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
            total_cost=response.response_cost,
        )

    async def _persist_analysis(
        self,
        parsed: AnalystResponse,
        work_units: List[WorkUnit],
    ) -> None:
        """Write findings, notes, directives to shared store and mark analyzed."""
        async for session in get_session():
            await self._persist_structured_state(session, parsed, work_units)

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

    async def _persist_structured_state(
        self,
        session,
        parsed: AnalystResponse,
        work_units: List[WorkUnit],
    ) -> None:
        """Persist deterministic observations, capabilities, and hypotheses."""
        for unit in work_units:
            target = unit.target if unit.target else ""
            primary_target = self._normalize_target(target) if target else ""
            combined_output = self._clean_text("\n".join(
                part for part in [unit.result_stdout or "", unit.result_stderr or ""] if part
            ))

            if target:
                if "://" in primary_target:
                    await self.store.add_observation(
                        session,
                        observation_type=ObservationType.LIVE_HTTP,
                        target=primary_target,
                        key=primary_target,
                        value={"source": unit.technique},
                    )
                    await self.store.add_capability(
                        session,
                        capability_type=CapabilityType.WEB_SURFACE,
                        target=primary_target,
                        key=primary_target,
                        details={"source": unit.technique},
                    )

            for url in self._extract_urls(combined_output):
                await self._persist_url_state(session, url, unit.technique)

            await self._persist_service_state(session, combined_output, primary_target, unit.technique)
            await self._persist_tls_name_state(session, combined_output, primary_target, unit.technique)
            for tech in self._extract_technologies(combined_output):
                tech_target = primary_target or self._extract_host(primary_target)
                if not tech_target:
                    continue
                await self.store.add_observation(
                    session,
                    observation_type=ObservationType.TECHNOLOGY,
                    target=tech_target,
                    key=tech,
                    value={"tech": tech, "source": unit.technique},
                )
                await self.store.add_capability(
                    session,
                    capability_type=CapabilityType.TECH_STACK,
                    target=tech_target,
                    key=tech,
                    details={"tech": tech, "source": unit.technique},
                )
                followup = self._technology_followup(tech, tech_target)
                if followup:
                    await self.store.add_hypothesis(
                        session,
                        hypothesis_type=HypothesisType.TECH_FOLLOWUP,
                        target=followup["target"],
                        key=followup["key"],
                        rationale=followup["rationale"],
                        confidence=0.78,
                        evidence={"tech": tech, "source": unit.technique},
                    )
            await self._persist_legacy_stack_hypotheses(session, combined_output, primary_target, unit.technique)

        for finding in parsed.findings:
            finding_target = self._normalize_target(finding.target)
            lower = " ".join(
                [finding.title.lower(), finding.description.lower(), finding.evidence.lower()]
            )
            if "login" in lower or "auth" in lower:
                await self.store.add_capability(
                    session,
                    capability_type=CapabilityType.AUTH_SURFACE,
                    target=finding_target,
                    key=finding_target,
                    details={"source": "finding", "title": finding.title},
                )
            if "admin" in lower:
                await self.store.add_capability(
                    session,
                    capability_type=CapabilityType.ADMIN_SURFACE,
                    target=finding_target,
                    key=finding_target,
                    details={"source": "finding", "title": finding.title},
                )

        await self._derive_waf_followup_directives(session, parsed.analysis, work_units)
        await self._derive_chain_hypotheses(session)

    async def _persist_url_state(self, session, url: str, source: str) -> None:
        normalized_url = self._normalize_target(url)
        parsed = urlparse(normalized_url)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()

        if parsed.scheme and parsed.netloc:
            await self.store.add_observation(
                session,
                observation_type=ObservationType.LIVE_HTTP,
                target=normalized_url,
                key=normalized_url,
                value={"source": source},
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.WEB_SURFACE,
                target=normalized_url,
                key=normalized_url,
                details={"source": source},
            )

        if parsed.query and "=" in parsed.query:
            await self.store.add_observation(
                session,
                observation_type=ObservationType.PARAMETERIZED_URL,
                target=normalized_url,
                key=normalized_url,
                value={"source": source, "query": parsed.query},
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.INPUT_SURFACE,
                target=normalized_url,
                key=normalized_url,
                details={"source": source},
            )
            await self.store.add_hypothesis(
                session,
                hypothesis_type=HypothesisType.INJECTION_FOLLOWUP,
                target=normalized_url,
                key=normalized_url,
                rationale="Discovered parameterized URL worth injection follow-up",
                confidence=0.82,
                evidence={"source": source},
            )

        if any(marker in path for marker in ("/login", "/signin", "/auth", "/session")):
            await self.store.add_observation(
                session,
                observation_type=ObservationType.LOGIN_SURFACE,
                target=normalized_url,
                key=normalized_url,
                value={"source": source},
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.AUTH_SURFACE,
                target=normalized_url,
                key=normalized_url,
                details={"source": source},
            )
            await self.store.add_hypothesis(
                session,
                hypothesis_type=HypothesisType.AUTH_FOLLOWUP,
                target=normalized_url,
                key=normalized_url,
                rationale="Discovered authentication surface worth default-login and auth-bypass testing",
                confidence=0.74,
                evidence={"source": source},
            )

        if any(marker in path for marker in ("/admin", "/wp-admin", "/administrator", "/console", "/manage")):
            await self.store.add_observation(
                session,
                observation_type=ObservationType.ADMIN_SURFACE,
                target=normalized_url,
                key=normalized_url,
                value={"source": source},
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.ADMIN_SURFACE,
                target=normalized_url,
                key=normalized_url,
                details={"source": source},
            )
            await self.store.add_hypothesis(
                session,
                hypothesis_type=HypothesisType.ADMIN_FOLLOWUP,
                target=normalized_url,
                key=normalized_url,
                rationale="Admin surface discovered and should be checked for exposed panels and auth bypass",
                confidence=0.86,
                evidence={"source": source},
            )

        if "/api" in path or any(marker in normalized_url.lower() for marker in ("swagger", "graphql", "openapi")):
            api_target = normalized_url if parsed.scheme and parsed.netloc else host
            await self.store.add_observation(
                session,
                observation_type=ObservationType.API_SURFACE,
                target=api_target,
                key=api_target,
                value={"source": source},
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.API_SURFACE,
                target=api_target,
                key=api_target,
                details={"source": source},
            )
            await self.store.add_hypothesis(
                session,
                hypothesis_type=HypothesisType.API_LOGIC_FOLLOWUP,
                target=api_target,
                key=api_target,
                rationale="API-like surface discovered and should receive targeted API/business-logic follow-up",
                confidence=0.72,
                evidence={"source": source},
            )

    async def _persist_service_state(self, session, output: str, target: str, source: str) -> None:
        """Extract simple network service facts from tool output."""
        host = self._extract_host(target)
        if not host:
            return

        for match in re.finditer(r"(?mi)^(\d+)/(tcp|udp)\s+open\s+([a-z0-9._-]+)", output):
            port, proto, service = match.groups()
            key = f"{proto}/{port}/{service}"
            details = {"source": source, "port": port, "protocol": proto, "service": service}
            await self.store.add_observation(
                session,
                observation_type=ObservationType.NETWORK_SERVICE,
                target=host,
                key=key,
                value=details,
            )
            await self.store.add_capability(
                session,
                capability_type=CapabilityType.NETWORK_SERVICE,
                target=host,
                key=key,
                details=details,
            )

    async def _persist_tls_name_state(self, session, output: str, target: str, source: str) -> None:
        """Extract TLS certificate SAN/CN hostnames as hidden-host evidence."""
        parent_host = self._extract_host(target)
        if not parent_host:
            return

        tls_names = set()
        for match in re.finditer(r"DNS:([A-Za-z0-9._-]+)", output):
            tls_names.add(match.group(1).lower())
        for match in re.finditer(r"Subject:.*?CN=([A-Za-z0-9._-]+)", output):
            tls_names.add(match.group(1).lower())

        for name in sorted(tls_names):
            if name == parent_host:
                continue
            await self.store.add_observation(
                session,
                observation_type=ObservationType.TLS_NAME,
                target=name,
                key=name,
                value={"source": source, "discovered_from": parent_host},
            )
            await self.store.add_hypothesis(
                session,
                hypothesis_type=HypothesisType.HIDDEN_HOST_FOLLOWUP,
                target=name,
                key=f"{parent_host}:tls-name:{name}",
                rationale="TLS certificate metadata exposed an additional host that should receive DNS, port, and web discovery",
                confidence=0.89,
                evidence={"source": source, "discovered_from": parent_host, "tls_name": name},
            )

    async def _persist_legacy_stack_hypotheses(self, session, output: str, target: str, source: str) -> None:
        """Create focused follow-up for obviously legacy/EOL web stacks."""
        lowered = output.lower()
        indicators = []
        if "apache/2.2" in lowered or "apache 2.2" in lowered:
            indicators.append("apache-2.2")
        if "php/5.3" in lowered or "php 5.3" in lowered:
            indicators.append("php-5.3")
        if "centos 6" in lowered:
            indicators.append("centos-6")
        if not indicators:
            return

        followup_target = self._normalize_target(target)
        if not followup_target:
            return
        await self.store.add_hypothesis(
            session,
            hypothesis_type=HypothesisType.LEGACY_STACK_RCE_FOLLOWUP,
            target=followup_target,
            key=f"{followup_target}:legacy-stack",
            rationale="Legacy stack indicators suggest targeted CVE and RCE follow-up, including Shellshock-era exposure checks",
            confidence=0.9,
            evidence={"source": source, "indicators": indicators},
        )

    async def _derive_chain_hypotheses(self, session) -> None:
        """Create higher-value follow-up hypotheses from capability combinations."""
        if not hasattr(self.store, "get_capabilities"):
            return
        capabilities = await self.store.get_capabilities(session, limit=250)
        by_host: Dict[str, Dict[str, List[Capability]]] = {}

        for capability in capabilities:
            host = self._extract_host(capability.target)
            if not host:
                continue
            bucket = by_host.setdefault(host, {})
            bucket.setdefault(str(capability.type), []).append(capability)

        for host, grouped in by_host.items():
            auth_surfaces = grouped.get(str(CapabilityType.AUTH_SURFACE), [])
            admin_surfaces = grouped.get(str(CapabilityType.ADMIN_SURFACE), [])
            api_surfaces = grouped.get(str(CapabilityType.API_SURFACE), [])
            input_surfaces = grouped.get(str(CapabilityType.INPUT_SURFACE), [])
            tech_stack = grouped.get(str(CapabilityType.TECH_STACK), [])

            if auth_surfaces and admin_surfaces:
                admin_target = admin_surfaces[0].target
                auth_target = auth_surfaces[0].target
                await self.store.add_hypothesis(
                    session,
                    hypothesis_type=HypothesisType.ADMIN_FOLLOWUP,
                    target=admin_target,
                    key=f"{host}:auth-admin-chain",
                    rationale="Authentication and admin surfaces coexist on the same host; test for default-login, panel exposure, and auth-bypass paths into admin functionality",
                    confidence=0.91,
                    evidence={
                        "host": host,
                        "auth_target": auth_target,
                        "admin_target": admin_target,
                        "chain": "auth_to_admin",
                    },
                )

            if api_surfaces and input_surfaces:
                api_target = api_surfaces[0].target
                input_target = input_surfaces[0].target
                await self.store.add_hypothesis(
                    session,
                    hypothesis_type=HypothesisType.API_LOGIC_FOLLOWUP,
                    target=input_target,
                    key=f"{host}:api-input-chain",
                    rationale="API-like surface and parameterized input coexist on the same host; prioritize API-specific input abuse and business-logic checks on discovered endpoints",
                    confidence=0.88,
                    evidence={
                        "host": host,
                        "api_target": api_target,
                        "input_target": input_target,
                        "chain": "api_input_abuse",
                    },
                )

            wordpress_targets = [
                capability for capability in tech_stack
                if "wordpress" in str(capability.key).lower()
                or "wordpress" in str((capability.details or {}).get("tech", "")).lower()
            ]
            if wordpress_targets and admin_surfaces:
                admin_target = admin_surfaces[0].target
                await self.store.add_hypothesis(
                    session,
                    hypothesis_type=HypothesisType.TECH_FOLLOWUP,
                    target=admin_target,
                    key=f"{host}:wordpress-admin-chain",
                    rationale="WordPress indicators and an admin surface coexist; prioritize targeted WordPress admin enumeration and known panel abuse checks",
                    confidence=0.93,
                    evidence={
                        "host": host,
                        "tech": "wordpress",
                        "admin_target": admin_target,
                        "chain": "wordpress_admin",
                    },
                )

    async def _derive_waf_followup_directives(
        self,
        session,
        analysis: str,
        work_units: List[WorkUnit],
    ) -> None:
        """Turn WAF/browser-origin conclusions into concrete follow-up directives."""
        analysis_lower = (analysis or "").lower()
        waf_markers = (
            "cloudflare",
            "just a moment",
            "bot management",
            "waf",
            "akamai",
        )
        if not any(marker in analysis_lower for marker in waf_markers):
            return

        targets: List[str] = []
        for unit in work_units:
            target = unit.target if unit.target else ""
            if target:
                normalized = self._normalize_target(target)
                if "://" in normalized:
                    targets.append(normalized)

        unique_targets: List[str] = []
        seen = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            unique_targets.append(target)

        for target in unique_targets[:8]:
            await self.store.add_directive(
                session,
                directive_type=DirectiveType.ATTACK_HINT,
                content={
                    "technique": "waf_detection_followup",
                    "targets": [target],
                    "context": "WAF/CDN pressure detected; confirm the protection and adapt follow-up accordingly",
                },
            )
            await self.store.add_directive(
                session,
                directive_type=DirectiveType.ATTACK_HINT,
                content={
                    "technique": "browser_like_probe_followup",
                    "targets": [target],
                    "context": "CLI probes were blocked; retry with a realistic browser user-agent and follow redirects for better surface visibility",
                },
            )

    @staticmethod
    def _extract_urls(text: str) -> List[str]:
        cleaned_text = AnalystAgent._clean_text(text)
        urls = [match.group(0).rstrip(").,;") for match in re.finditer(r'https?://[^\s"\'<>]+', cleaned_text)]
        seen = set()
        ordered: List[str] = []
        for url in urls:
            if url in seen:
                continue
            seen.add(url)
            ordered.append(url)
        return ordered

    @staticmethod
    def _extract_technologies(text: str) -> List[str]:
        corpus = text.lower()
        known = [
            "wordpress", "drupal", "joomla", "laravel", "django", "rails",
            "nginx", "apache", "iis", "tomcat", "php", "react", "vue", "angular",
        ]
        detected = [tech for tech in known if tech in corpus]
        seen = set()
        ordered: List[str] = []
        for tech in detected:
            if tech in seen:
                continue
            seen.add(tech)
            ordered.append(tech)
        return ordered

    @staticmethod
    def _technology_followup(tech: str, target: str) -> Optional[Dict[str, str]]:
        tech_lower = tech.lower()
        if "wordpress" in tech_lower:
            return {
                "target": target,
                "key": f"{target}:wordpress",
                "rationale": "WordPress technology detected; run targeted WordPress follow-up",
            }
        if any(name in tech_lower for name in ("laravel", "django", "drupal", "joomla")):
            return {
                "target": target,
                "key": f"{target}:{tech_lower}",
                "rationale": f"{tech} detected; run targeted tech-specific CVE follow-up",
            }
        return None

    @staticmethod
    def _normalize_target(target: str) -> str:
        if not target:
            return target
        cleaned = AnalystAgent._clean_text(target).strip().strip("'\"")
        return cleaned.rstrip("/")

    @staticmethod
    def _clean_text(value: str) -> str:
        if not value:
            return value
        without_ansi = _ANSI_ESCAPE_RE.sub("", value)
        return _CONTROL_CHAR_RE.sub("", without_ansi)

    @staticmethod
    def _extract_host(target: str) -> str:
        if not target:
            return ""
        if "://" in target:
            parsed = urlparse(target)
            return (parsed.hostname or "").lower()
        return target.split("/")[0].split(":")[0].lower()

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

    def _instruction_context_block(self) -> str:
        if not self._instructions:
            return ""
        excerpt = self._instructions[:600]
        return "\n".join([
            "<operator_instructions>",
            excerpt,
            "Treat these instructions as scan-level policy constraints unless they conflict with legality/safety.",
            "</operator_instructions>",
        ])

    def _build_results_prompt(self, work_units: List[WorkUnit]) -> str:
        """Format work unit results for the Analyst to review."""
        lines = ["<tool_results>"]
        for unit in work_units:
            target = unit.target if unit.target else ""
            lines.append(f"\n<result technique=\"{unit.technique}\" target=\"{target}\">")

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

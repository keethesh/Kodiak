"""
Planner Agent — methodology-driven work unit generator for the multi-agent pipeline.

The Planner uses a fast model (Gemini Flash) to:
  1. Read shared scan state
  2. Apply methodology rules to generate work units
  3. Consume Analyst directives to adjust strategy
  4. Enqueue deduplicated work units for Workers

The Planner does NOT do deep analysis — it follows the playbook and responds
to Analyst directives. It runs on a fast cycle (~10s) to keep Workers busy.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from uuid import UUID

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.config import settings
from kodiak.core.methodology import (
    ALL_RULES,
    MethodologyRule,
    TriggerType,
    get_rules_for_phase,
)
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.engine import get_session
from kodiak.database.models import (
    Directive,
    DirectiveType,
    EngagementNote,
    NoteCategory,
    WorkUnit,
    WorkUnitStatus,
)
from kodiak.services import llm
from kodiak.services.gemini_client import GeminiClient


class PlannerAgent:
    """
    Methodology-driven work unit generator.

    Runs on a fast cycle, reading shared state and emitting work units
    based on structured rules + Analyst directives.
    """

    def __init__(
        self,
        store: SharedScanStore,
        target: str,
        event_manager: Optional[TUIEventManager] = None,
    ):
        self.store = store
        self.target = target
        self.event_manager = event_manager
        self._gemini = GeminiClient()

        # Track state for rule triggering
        self._known_hosts: Set[str] = {target}
        self._live_http_hosts: Set[str] = set()
        self._detected_techs: Dict[str, Set[str]] = {}  # host → {tech, ...}
        self._parameterized_urls: List[str] = []
        self._completed_techniques: Set[str] = set()
        self._skip_targets: Set[str] = set()
        self._rate_limit: Optional[Dict[str, Any]] = None
        self._current_phase: str = "recon"
        self._cycle_count: int = 0
        self._stop_requested: bool = False
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_thinking_tokens: int = 0
        self._total_cached_tokens: int = 0

    def request_stop(self) -> None:
        self._stop_requested = True

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        cycle_interval: float = 8.0,
        max_cycles: int = 200,
    ) -> Dict[str, Any]:
        """
        Main Planner loop. Generates work units on a fast cycle.
        Returns stats when stopped or max_cycles reached.
        """
        # Seed initial RECON work units
        await self._seed_initial_work()

        while self._cycle_count < max_cycles and not self._stop_requested:
            self._cycle_count += 1

            # Consume Analyst directives
            await self._process_directives()

            # Scan for new intelligence in completed results
            await self._update_state_from_results()

            # Generate new work units from methodology
            generated = await self._generate_work_units()

            # Check if work queue is empty and no more rules apply
            async for session in get_session():
                pending = await self.store.get_pending_count(session)

            if pending == 0 and generated == 0 and self._cycle_count > 3:
                # Try to advance phase
                advanced = self._try_advance_phase()
                if not advanced:
                    logger.info("📋 Planner: no more work — all phases exhausted")
                    break
                # Generate work for new phase
                generated = await self._generate_work_units()
                if generated == 0:
                    break

            if self.event_manager and generated > 0:
                try:
                    await self.event_manager.emit_agent_thinking(
                        agent_id="planner",
                        message=f"Cycle {self._cycle_count}: queued {generated} work units (phase={self._current_phase})",
                        scan_id=str(self.store.scan_id),
                    )
                except Exception:
                    pass

            await self._sleep(cycle_interval)

        return {
            "cycles": self._cycle_count,
            "phase": self._current_phase,
            "hosts_discovered": len(self._known_hosts),
            "techniques_completed": len(self._completed_techniques),
            "input_tokens": self._total_input_tokens,
            "output_tokens": self._total_output_tokens,
        }

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            self._stop_requested = True

    # ------------------------------------------------------------------
    # Initial seeding
    # ------------------------------------------------------------------

    async def _seed_initial_work(self) -> None:
        """Seed the work queue with RECON phase rules that trigger on ALWAYS."""
        domain = self._extract_domain(self.target)
        rules = get_rules_for_phase("recon")
        count = 0

        async for session in get_session():
            for rule in rules:
                if rule.trigger != TriggerType.ALWAYS:
                    continue

                targets = self._resolve_targets(rule, domain)
                if not targets:
                    continue

                cmd = rule.command_template.format(
                    target=targets[0],
                    domain=domain,
                )

                unit = await self.store.enqueue_work_unit(
                    session,
                    technique=rule.technique,
                    targets=targets,
                    command_template=cmd,
                    priority=rule.priority,
                    phase=rule.phase,
                )
                if unit:
                    count += 1

        logger.info(f"📋 Planner: seeded {count} initial RECON work units")

    # ------------------------------------------------------------------
    # Directive processing
    # ------------------------------------------------------------------

    async def _process_directives(self) -> None:
        """Consume Analyst directives and update Planner state."""
        async for session in get_session():
            directives = await self.store.consume_directives(session)

        for d in directives:
            content = d.content or {}
            if d.type == DirectiveType.SKIP_TARGET:
                target = content.get("target", "")
                if target:
                    self._skip_targets.add(target)
                    logger.info(f"📋 Planner: skipping target {target}")

            elif d.type == DirectiveType.PRIORITIZE_TARGET:
                target = content.get("target", "")
                if target:
                    self._known_hosts.add(target)
                    self._live_http_hosts.add(target)
                    logger.info(f"📋 Planner: prioritizing target {target}")

            elif d.type == DirectiveType.RATE_LIMIT:
                self._rate_limit = content
                logger.info(f"📋 Planner: rate limit set: {content}")

            elif d.type == DirectiveType.ATTACK_HINT:
                # Create a work unit from the hint
                await self._process_attack_hint(content)

            elif d.type == DirectiveType.ESCALATE:
                # Create high-priority work unit
                await self._process_escalation(content)

            elif d.type == DirectiveType.PHASE_ADVANCE:
                to_phase = content.get("to_phase", "")
                if to_phase:
                    self._current_phase = to_phase
                    logger.info(f"📋 Planner: phase advanced to {to_phase}")

    async def _process_attack_hint(self, content: Dict[str, Any]) -> None:
        """Convert an Analyst attack_hint into work units."""
        technique = content.get("technique", "analyst_hint")
        targets = content.get("targets", [])
        context = content.get("context", "")
        command = content.get("command", "")

        if not targets:
            targets = list(self._live_http_hosts - self._skip_targets)
        if not targets:
            targets = list(self._known_hosts - self._skip_targets)

        if not targets or not command:
            return

        async for session in get_session():
            await self.store.enqueue_work_unit(
                session,
                technique=f"hint_{technique}",
                targets=targets[:20],
                command_template=command,
                context=context,
                priority=15,  # High priority
                phase=self._current_phase,
            )

    async def _process_escalation(self, content: Dict[str, Any]) -> None:
        """Convert an Analyst escalation into an urgent work unit."""
        target = content.get("target", "")
        action = content.get("action", "")

        if not target or not action:
            return

        async for session in get_session():
            await self.store.enqueue_work_unit(
                session,
                technique=f"escalate_{target[:20]}",
                targets=[target],
                command_template=action,
                context=f"URGENT: {content.get('finding', '')}",
                priority=5,  # Highest priority
                phase="exploitation",
            )

    # ------------------------------------------------------------------
    # State updates from completed results
    # ------------------------------------------------------------------

    async def _update_state_from_results(self) -> None:
        """
        Scan recent completed results to extract new hosts, technologies, etc.
        Uses Flash model for quick extraction when output is complex.
        """
        async for session in get_session():
            # Get recently completed but check their technique for state updates
            from sqlmodel import select
            stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.store.scan_id,
                    WorkUnit.status == WorkUnitStatus.COMPLETED,
                )
                .order_by(WorkUnit.completed_at.desc())
                .limit(20)
            )
            result = await session.execute(stmt)
            recent = list(result.scalars().all())

        for unit in recent:
            self._completed_techniques.add(unit.technique)
            stdout = unit.result_stdout or ""

            # Extract hosts from subdomain tools
            if unit.technique in ("subfinder", "httpx_subdomains", "dnsx_subdomains"):
                self._extract_hosts_from_output(stdout)

            # Extract live HTTP hosts from httpx output
            if "httpx" in unit.technique:
                self._extract_live_hosts_from_httpx(stdout)

            # Extract technologies from whatweb/httpx output
            if unit.technique in ("whatweb_primary", "httpx_primary"):
                self._extract_techs_from_output(stdout, unit.targets_json)

    def _extract_hosts_from_output(self, stdout: str) -> None:
        """Extract hostnames from tool output."""
        import re
        pattern = re.compile(r'([a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}')
        for match in pattern.finditer(stdout):
            host = match.group(0).lower()
            domain = self._extract_domain(self.target)
            if domain in host:
                self._known_hosts.add(host)

    def _extract_live_hosts_from_httpx(self, stdout: str) -> None:
        """Extract hosts that returned HTTP responses."""
        for line in stdout.split("\n"):
            line = line.strip()
            if not line:
                continue
            # httpx output format: https://host [status] [title]
            if "://" in line:
                import re
                match = re.search(r'https?://([^\s/\[\]]+)', line)
                if match:
                    host = match.group(1).lower()
                    self._live_http_hosts.add(host)
            elif "." in line and " " not in line:
                self._live_http_hosts.add(line.lower())

    def _extract_techs_from_output(self, stdout: str, targets_json: str) -> None:
        """Extract technology names from whatweb/httpx output."""
        targets = json.loads(targets_json) if targets_json else []
        host = targets[0] if targets else self.target

        tech_keywords = [
            "wordpress", "drupal", "joomla", "laravel", "django", "rails",
            "nginx", "apache", "iis", "tomcat", "cloudflare", "php",
            "node.js", "react", "angular", "vue", "next.js",
        ]
        stdout_lower = stdout.lower()
        detected = set()
        for tech in tech_keywords:
            if tech in stdout_lower:
                detected.add(tech)

        if detected:
            self._detected_techs.setdefault(host, set()).update(detected)

    # ------------------------------------------------------------------
    # Work unit generation
    # ------------------------------------------------------------------

    async def _generate_work_units(self) -> int:
        """Apply methodology rules to generate new work units."""
        rules = get_rules_for_phase(self._current_phase)
        domain = self._extract_domain(self.target)
        count = 0

        async for session in get_session():
            # Get already-queued techniques for dedup
            existing = await self.store.get_completed_techniques(session)
            existing_set = set(existing)

            for rule in rules:
                if rule.technique in existing_set:
                    continue

                if not self._trigger_satisfied(rule):
                    continue

                targets = self._resolve_targets(rule, domain)
                targets = [t for t in targets if t not in self._skip_targets]
                if not targets:
                    continue

                # Build command from template
                if len(targets) == 1:
                    cmd = rule.command_template.format(
                        target=targets[0], domain=domain,
                    )
                else:
                    # For multi-target rules, use the first target in template
                    cmd = rule.command_template.format(
                        target=targets[0], domain=domain,
                    )

                # Apply rate limiting from Analyst directives
                if self._rate_limit:
                    cmd = self._apply_rate_limit(cmd, rule)

                unit = await self.store.enqueue_work_unit(
                    session,
                    technique=rule.technique,
                    targets=targets[:rule.max_targets],
                    command_template=cmd,
                    priority=rule.priority,
                    phase=rule.phase,
                )
                if unit:
                    count += 1

        return count

    def _trigger_satisfied(self, rule: MethodologyRule) -> bool:
        """Check if a rule's trigger condition is met."""
        if rule.trigger == TriggerType.ALWAYS:
            return True
        if rule.trigger == TriggerType.HOST_DISCOVERED:
            return len(self._known_hosts) > 1
        if rule.trigger == TriggerType.HOST_LIVE_HTTP:
            return len(self._live_http_hosts) > 0
        if rule.trigger == TriggerType.TECH_DETECTED:
            if not rule.tech_filter:
                return bool(self._detected_techs)
            return any(
                rule.tech_filter.lower() in tech.lower()
                for techs in self._detected_techs.values()
                for tech in techs
            )
        if rule.trigger == TriggerType.PARAMS_FOUND:
            return len(self._parameterized_urls) > 0
        if rule.trigger == TriggerType.ANALYST_HINT:
            return False  # Handled via directives, not methodology rules
        return False

    def _resolve_targets(
        self, rule: MethodologyRule, domain: str
    ) -> List[str]:
        """Determine which targets a rule should run against."""
        selector = rule.target_selector

        if selector == "primary":
            return [self.target]
        if selector == "primary_domain":
            return [domain]
        if selector == "all_hosts":
            return sorted(self._known_hosts - self._skip_targets)[:rule.max_targets]
        if selector == "live_http":
            hosts = self._live_http_hosts - self._skip_targets
            if not hosts:
                hosts = {self.target}
            return sorted(hosts)[:rule.max_targets]
        if selector == "with_tech":
            if not rule.tech_filter:
                return []
            result = []
            for host, techs in self._detected_techs.items():
                if host in self._skip_targets:
                    continue
                if any(rule.tech_filter.lower() in t.lower() for t in techs):
                    result.append(host)
            return result[:rule.max_targets]
        if selector == "parameterized_urls":
            return self._parameterized_urls[:rule.max_targets]

        return [self.target]

    def _apply_rate_limit(self, cmd: str, rule: MethodologyRule) -> str:
        """Apply Analyst-directed rate limiting to a command."""
        if not self._rate_limit:
            return cmd
        max_threads = self._rate_limit.get("max_threads")
        if max_threads and "-t " in cmd:
            import re
            cmd = re.sub(r'-t\s+\d+', f'-t {max_threads}', cmd)
        return cmd

    def _try_advance_phase(self) -> bool:
        """Try to advance to the next phase. Returns True if advanced."""
        phase_order = ["recon", "enumeration", "vuln_scan", "exploitation", "reporting"]
        try:
            idx = phase_order.index(self._current_phase)
        except ValueError:
            return False

        if idx + 1 >= len(phase_order):
            return False

        next_phase = phase_order[idx + 1]
        self._current_phase = next_phase
        logger.info(f"📋 Planner: auto-advanced to phase {next_phase}")
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_domain(target: str) -> str:
        """Extract the base domain from a URL or hostname."""
        import re
        target = re.sub(r'^https?://', '', target)
        target = target.split('/')[0].split(':')[0]
        return target

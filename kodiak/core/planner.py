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
import re
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from loguru import logger

from kodiak.api.events import TUIEventManager
from kodiak.core.methodology import (
    MethodologyRule,
    TriggerType,
    get_rules_for_phase,
    get_rule_by_technique,
)
from kodiak.core.shared_store import SharedScanStore
from kodiak.database.engine import get_session
from kodiak.database.models import (
    DirectiveType,
    Hypothesis,
    HypothesisStatus,
    HypothesisType,
    ObservationType,
    ScanEventType,
    WorkUnit,
    WorkUnitStatus,
)


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

        # Track state for rule triggering
        self._known_hosts: Set[str] = {self._extract_host(target)}
        self._live_http_hosts: Set[str] = set()
        self._live_http_origins: Dict[str, str] = {}
        self._detected_techs: Dict[str, Set[str]] = {}
        self._parameterized_urls: List[str] = []
        self._completed_techniques: Set[str] = set()
        self._processed_result_ids: Set[str] = set()
        self._skip_targets: Set[str] = set()
        self._rate_limit: Optional[Dict[str, Any]] = None
        self._current_phase: str = "recon"
        self._cycle_count: int = 0
        self._idle_cycles: int = 0
        self._stop_requested: bool = False
        self._total_input_tokens: int = 0
        self._total_output_tokens: int = 0
        self._total_thinking_tokens: int = 0
        self._total_cached_tokens: int = 0
        self._degraded = False

        if "://" in target:
            self._remember_live_http_target(target)

    @staticmethod
    def _unit_targets(unit: WorkUnit) -> List[str]:
        """Compatibility accessor while WorkUnit keeps targets_json."""
        if unit.target:
            return [unit.target]
        if unit.targets_json:
            try:
                parsed = json.loads(unit.targets_json)
            except json.JSONDecodeError:
                return []
            return [str(item) for item in parsed]
        return []

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

            try:
                if self._degraded:
                    await self._record_component_recovered()
                    self._degraded = False

                # Consume Analyst directives
                await self._process_directives()

                # Scan for new intelligence in completed results
                await self._update_state_from_results()
                await self._refresh_state_from_store()

                # Expand structured hypotheses into concrete follow-up work.
                await self._process_hypotheses()

                # Generate new work units from methodology
                generated = await self._generate_work_units()

                # Check if the system has actually settled before auto-advancing.
                async for session in get_session():
                    pending = await self.store.get_pending_count(session)
                    unanalyzed = await self.store.get_unanalyzed_count(session)
                    waiting_directives = await self.store.get_unconsumed_directive_count(session)

                if pending == 0 and generated == 0:
                    if unanalyzed == 0 and waiting_directives == 0:
                        self._idle_cycles += 1
                    else:
                        self._idle_cycles = 0
                else:
                    self._idle_cycles = 0

                if pending == 0 and generated == 0 and self._cycle_count > 3:
                    if unanalyzed > 0 or waiting_directives > 0 or self._idle_cycles < 2:
                        await self._sleep(cycle_interval)
                        continue

                    # Try to advance phase once we've been idle across multiple cycles.
                    advanced = self._try_advance_phase()
                    self._idle_cycles = 0
                    if not advanced:
                        logger.info("📋 Planner: no more work — all phases exhausted")
                        break
                    # Generate work for new phase immediately.
                    generated = await self._generate_work_units()

                if self.event_manager and generated > 0:
                    try:
                        await self.event_manager.emit_agent_thinking(
                            agent_id="planner",
                            message=f"Cycle {self._cycle_count}: queued {generated} work units (phase={self._current_phase})",
                            scan_id=str(self.store.scan_id),
                        )
                    except Exception:
                        pass
            except Exception:
                logger.exception("Planner cycle failed")
                if not self._degraded:
                    await self._record_component_degraded("Planner cycle failed")
                    self._degraded = True
                self._idle_cycles = 0

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

    async def _record_component_degraded(self, reason: str) -> None:
        async for session in get_session():
            await self.store.append_event(
                session,
                event_type=ScanEventType.COMPONENT_DEGRADED,
                entity_type="component",
                entity_id="planner",
                payload={"component": "planner", "reason": reason},
            )

    async def _record_component_recovered(self) -> None:
        async for session in get_session():
            await self.store.append_event(
                session,
                event_type=ScanEventType.COMPONENT_RECOVERED,
                entity_type="component",
                entity_id="planner",
                payload={"component": "planner", "reason": "Planner resumed successful cycles"},
            )

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
                count += await self._enqueue_rule_targets(session, rule, targets, domain)

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
                    self._skip_targets.add(self._extract_host(target))
                    logger.info(f"📋 Planner: skipping target {target}")

            elif d.type == DirectiveType.PRIORITIZE_TARGET:
                target = content.get("target", "")
                if target:
                    self._remember_target(target, assume_live_http=True)
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

        if not targets:
            targets = list(self._live_http_hosts - self._skip_targets)
        if not targets:
            targets = list(self._known_hosts - self._skip_targets)

        work_specs = self._expand_attack_hint_specs(technique, targets, content)
        if not work_specs:
            return

        async for session in get_session():
            for spec in work_specs:
                resolved_target = spec["target"]
                command = spec["command"].format(
                    target=resolved_target,
                    domain=self._extract_domain(resolved_target),
                )
                await self.store.enqueue_work_unit(
                    session,
                    technique=spec["technique"],
                    targets=[resolved_target],
                    command_template=command,
                    context=spec["context"],
                    priority=spec["priority"],
                    phase=spec["phase"],
                )

    def _expand_attack_hint_specs(
        self,
        technique: str,
        targets: List[str],
        content: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Resolve analyst hint techniques into concrete executable work.

        Raw ``command`` payloads are a compatibility fallback only.
        """
        command = content.get("command", "")
        context = content.get("context", "")
        ordered_targets = self._dedupe_preserve_order(targets)[:20]

        alias_map = {
            "nikto_scan": ["nikto"],
            "nuclei_cves": ["nuclei_cves"],
            "vulnerability_scanning": ["nuclei_cves", "nikto"],
            "directory_bruteforce": ["ffuf_common"],
            "active_crawling": ["katana_crawl"],
            "active_web_discovery": ["katana_crawl", "ffuf_common"],
            "web_discovery": ["dnsx_subdomains", "httpx_subdomains", "whatweb_primary"],
            "subdomain_recon_and_probing": ["dnsx_subdomains", "httpx_subdomains", "whatweb_primary"],
            "port_scan_and_web_discovery": ["nmap_initial", "httpx_subdomains", "whatweb_primary"],
            "waf_detection_followup": ["hint_waf_detection_followup"],
            "browser_like_probe_followup": ["hint_browser_like_probe_followup"],
        }
        resolved_techniques = alias_map.get(technique, [technique])
        specs: List[Dict[str, Any]] = []

        for target in ordered_targets:
            for resolved in resolved_techniques:
                spec = self._work_spec_for_hint_technique(
                    resolved,
                    target,
                    context,
                )
                if spec:
                    specs.append(spec)

        if not specs:
            if command:
                logger.warning(
                    "Planner executed deprecated raw-command attack_hint for technique "
                    f"{technique}; migrate this hint to structured technique mapping."
                )
                return [
                    {
                        "technique": f"hint_{technique}",
                        "target": self._canonical_hint_target(target),
                        "command": command,
                        "context": context,
                        "priority": 15,
                        "phase": self._current_phase,
                    }
                    for target in ordered_targets
                ]
            logger.debug(f"Planner ignored unsupported attack_hint technique: {technique}")
        return specs

    def _work_spec_for_hint_technique(
        self,
        technique: str,
        target: str,
        context: str,
    ) -> Optional[Dict[str, Any]]:
        if technique == "hint_waf_detection_followup":
            resolved_target = self._canonical_hint_target(target)
            return {
                "technique": "hint_waf_detection_followup",
                "target": resolved_target,
                "command": "wafw00f {target} -a",
                "context": context,
                "priority": 15,
                "phase": self._current_phase,
            }

        if technique == "hint_browser_like_probe_followup":
            resolved_target = self._canonical_hint_target(target)
            return {
                "technique": "hint_browser_like_probe_followup",
                "target": resolved_target,
                "command": "curl -skL -A 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36' {target} | head -200",
                "context": context,
                "priority": 15,
                "phase": self._current_phase,
            }

        rule = get_rule_by_technique(technique)
        if not rule:
            return None

        normalized_target = self._normalize_target_for_rule(
            rule,
            self._canonical_hint_target(target),
            self._extract_domain(target),
        )
        return {
            "technique": f"hint_{technique}",
            "target": normalized_target,
            "command": self._apply_rate_limit(rule.command_template.format(
                target=normalized_target,
                domain=self._extract_domain(normalized_target),
            ), rule) if self._rate_limit else rule.command_template.format(
                target=normalized_target,
                domain=self._extract_domain(normalized_target),
            ),
            "context": context,
            "priority": min(rule.priority, 15),
            "phase": rule.phase or self._current_phase,
        }

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

    async def _process_hypotheses(self) -> None:
        """Convert structured hypotheses into high-priority work units."""
        async for session in get_session():
            hypotheses = await self.store.get_hypotheses(
                session,
                statuses=[HypothesisStatus.PENDING],
                limit=25,
            )
            queued_ids: List[Any] = []

            for hypothesis in hypotheses:
                work_item = self._work_item_for_hypothesis(hypothesis)
                if work_item is None:
                    continue

                unit = await self.store.enqueue_work_unit(
                    session,
                    technique=work_item["technique"],
                    targets=[work_item["target"]],
                    command_template=work_item["command"],
                    context=work_item["context"],
                    priority=work_item["priority"],
                    phase=work_item["phase"],
                )
                if unit:
                    queued_ids.append(hypothesis.id)

            await self.store.mark_hypothesis_status(session, queued_ids, HypothesisStatus.QUEUED)

    # ------------------------------------------------------------------
    # State updates from completed results
    # ------------------------------------------------------------------

    async def _update_state_from_results(self) -> None:
        """
        Scan completed results to extract new hosts, URLs, technologies, etc.
        State extraction is deterministic so repeated runs behave consistently.
        """
        async for session in get_session():
            from sqlmodel import select
            stmt = (
                select(WorkUnit)
                .where(
                    WorkUnit.scan_id == self.store.scan_id,
                    WorkUnit.status == WorkUnitStatus.COMPLETED,
                )
                .order_by(WorkUnit.completed_at.asc(), WorkUnit.created_at.asc())
            )
            result = await session.execute(stmt)
            completed_units = list(result.scalars().all())

        for unit in completed_units:
            unit_id = str(unit.id)
            if unit_id in self._processed_result_ids:
                continue
            self._processed_result_ids.add(unit_id)
            self._completed_techniques.add(unit.technique)

            targets = self._unit_targets(unit)
            for target in targets:
                self._remember_target(target)

            stdout = unit.result_stdout or ""
            stderr = unit.result_stderr or ""
            combined_output = f"{stdout}\n{stderr}".strip()

            # Extract hosts from subdomain tools
            if unit.technique in ("subfinder", "httpx_subdomains", "dnsx_subdomains"):
                self._extract_hosts_from_output(stdout)

            # Extract live HTTP hosts from httpx output
            if "httpx" in unit.technique:
                self._extract_live_hosts_from_httpx(stdout)

            # Extract technologies from whatweb/httpx output
            if unit.technique in ("whatweb_primary", "httpx_primary", "httpx_subdomains"):
                self._extract_techs_from_output(stdout, targets)

            self._extract_parameterized_urls(combined_output)

    async def _refresh_state_from_store(self) -> None:
        """Hydrate planner state from persisted observations for resumability."""
        async for session in get_session():
            observations = await self.store.get_observations(session, limit=250)

        for observation in observations:
            if observation.type == ObservationType.LIVE_HTTP:
                self._remember_live_http_target(observation.target)
            elif observation.type == ObservationType.PARAMETERIZED_URL:
                self._parameterized_urls = self._dedupe_preserve_order(
                    self._parameterized_urls + [observation.target]
                )
            elif observation.type == ObservationType.TECHNOLOGY:
                self._detected_techs.setdefault(observation.target, set()).add(observation.key)

    def _extract_hosts_from_output(self, stdout: str) -> None:
        """Extract hostnames from tool output."""
        pattern = re.compile(r'([a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}')
        for match in pattern.finditer(stdout):
            host = match.group(0).lower()
            domain = self._extract_domain(self.target)
            if domain in host:
                self._known_hosts.add(host)

    def _extract_live_hosts_from_httpx(self, stdout: str) -> None:
        """Extract live origins and hostnames from httpx output."""
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.search(r'https?://[^\s\[\]]+', line)
            if match:
                self._remember_live_http_target(match.group(0))
                continue

            token = line.split()[0]
            if "." in token:
                self._remember_live_http_target(token.lower())

    def _extract_techs_from_output(self, stdout: str, targets: List[str]) -> None:
        """Extract technology names from whatweb/httpx output."""
        host = self._canonical_hint_target(targets[0]) if targets else self._canonical_hint_target(self.target)

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

    def _extract_parameterized_urls(self, output: str) -> None:
        """Persist discovered parameterized URLs in stable order."""
        urls: List[str] = []
        for match in re.finditer(r'https?://[^\s"\'<>]+', output):
            url = match.group(0).rstrip(").,;")
            parsed = urlparse(url)
            if parsed.query and "=" in parsed.query:
                urls.append(url)

        if not urls:
            return

        merged = self._parameterized_urls + urls
        self._parameterized_urls = self._dedupe_preserve_order(merged)

    # ------------------------------------------------------------------
    # Work unit generation
    # ------------------------------------------------------------------

    async def _generate_work_units(self) -> int:
        """Apply methodology rules to generate new work units."""
        rules = get_rules_for_phase(self._current_phase)
        domain = self._extract_domain(self.target)
        count = 0

        async for session in get_session():
            for rule in rules:
                if not self._trigger_satisfied(rule):
                    continue

                targets = self._resolve_targets(rule, domain)
                if not targets:
                    continue

                count += await self._enqueue_rule_targets(session, rule, targets, domain)

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

    def _work_item_for_hypothesis(self, hypothesis: Hypothesis) -> Optional[Dict[str, Any]]:
        """Translate a hypothesis into one concrete follow-up command."""
        target = hypothesis.target

        if hypothesis.type == HypothesisType.INJECTION_FOLLOWUP:
            if "?" not in target or "=" not in target:
                return None
            return {
                "technique": "hypothesis_sqlmap_followup",
                "target": target,
                "command": f"sqlmap -u '{target}' --batch --random-agent --level 2 --risk 2 --threads 3",
                "context": hypothesis.rationale,
                "priority": 18,
                "phase": "vuln_scan",
            }

        if hypothesis.type == HypothesisType.AUTH_FOLLOWUP:
            return {
                "technique": "hypothesis_auth_panel_followup",
                "target": target,
                "command": f"nuclei -u {target} -tags default-login,auth-bypass,exposed-panels -rl 10 -silent",
                "context": hypothesis.rationale,
                "priority": 16,
                "phase": "vuln_scan",
            }

        if hypothesis.type == HypothesisType.ADMIN_FOLLOWUP:
            return {
                "technique": "hypothesis_admin_surface_followup",
                "target": target,
                "command": f"nuclei -u {target} -tags exposed-panels,default-login,auth-bypass -rl 10 -silent",
                "context": hypothesis.rationale,
                "priority": 14,
                "phase": "vuln_scan",
            }

        if hypothesis.type == HypothesisType.API_LOGIC_FOLLOWUP:
            return {
                "technique": "hypothesis_api_surface_followup",
                "target": target,
                "command": f"nuclei -u {target} -tags api,swagger,graphql,cors -rl 10 -silent",
                "context": hypothesis.rationale,
                "priority": 17,
                "phase": "vuln_scan",
            }

        if hypothesis.type == HypothesisType.TECH_FOLLOWUP:
            tech = str((hypothesis.evidence or {}).get("tech", "")).lower()
            if "wordpress" in tech:
                return {
                    "technique": "hypothesis_wordpress_followup",
                    "target": self._canonical_hint_target(target),
                    "command": f"wpscan --url {self._canonical_hint_target(target)} --enumerate vp,vt,u --random-user-agent --throttle 500",
                    "context": hypothesis.rationale,
                    "priority": 20,
                    "phase": "enumeration",
                }
            if tech:
                web_target = self._canonical_hint_target(target)
                return {
                    "technique": f"hypothesis_{tech}_followup",
                    "target": web_target,
                    "command": f"nuclei -u {web_target} -tags cve,{tech} -rl 10 -silent",
                    "context": hypothesis.rationale,
                    "priority": 19,
                    "phase": "vuln_scan",
                }

        if hypothesis.type == HypothesisType.HIDDEN_HOST_FOLLOWUP:
            host = self._extract_host(target)
            if not host:
                return None
            return {
                "technique": "hypothesis_hidden_host_followup",
                "target": host,
                "command": f"nmap -sV -sC -T3 -p 80,443,8080,8443 {host}",
                "context": hypothesis.rationale,
                "priority": 12,
                "phase": "recon",
            }

        if hypothesis.type == HypothesisType.LEGACY_STACK_RCE_FOLLOWUP:
            web_target = self._canonical_hint_target(target)
            return {
                "technique": "hypothesis_legacy_stack_rce_followup",
                "target": web_target,
                "command": f"nuclei -u {web_target} -tags cve,shellshock,apache,php -rl 10 -silent",
                "context": hypothesis.rationale,
                "priority": 13,
                "phase": "vuln_scan",
            }

        return None

    def _resolve_targets(
        self, rule: MethodologyRule, domain: str
    ) -> List[str]:
        """Determine which targets a rule should run against."""
        selector = rule.target_selector

        if selector == "primary":
            return [self._canonical_hint_target(self.target)]
        if selector == "primary_domain":
            return [domain]
        if selector == "all_hosts":
            hosts = [
                host for host in sorted(self._known_hosts)
                if not self._is_target_skipped(host)
            ]
            return hosts[:rule.max_targets]
        if selector == "live_http":
            hosts = [
                host for host in sorted(self._live_http_hosts)
                if not self._is_target_skipped(host)
            ]
            if not hosts:
                fallback = self._extract_host(self.target)
                hosts = [fallback] if fallback else []
            return [
                self._format_live_http_target(rule, host)
                for host in hosts[:rule.max_targets]
            ]
        if selector == "with_tech":
            if not rule.tech_filter:
                return []
            result = []
            for host, techs in self._detected_techs.items():
                if self._is_target_skipped(host):
                    continue
                if any(rule.tech_filter.lower() in t.lower() for t in techs):
                    result.append(host)
            return self._dedupe_preserve_order(result)[:rule.max_targets]
        if selector == "parameterized_urls":
            urls = [
                url for url in self._parameterized_urls
                if not self._is_target_skipped(url)
            ]
            return urls[:rule.max_targets]

        return [self._canonical_hint_target(self.target)]

    async def _enqueue_rule_targets(
        self,
        session,
        rule: MethodologyRule,
        targets: List[str],
        domain: str,
    ) -> int:
        """Enqueue one concrete work unit per target scope."""
        count = 0
        for target in self._dedupe_preserve_order(targets)[:rule.max_targets]:
            normalized_target = self._normalize_target_for_rule(rule, target, domain)
            cmd = rule.command_template.format(target=normalized_target, domain=domain)
            if self._rate_limit:
                cmd = self._apply_rate_limit(cmd, rule)

            unit = await self.store.enqueue_work_unit(
                session,
                technique=rule.technique,
                targets=[normalized_target],
                command_template=cmd,
                priority=rule.priority,
                phase=rule.phase,
            )
            if unit:
                count += 1
        return count

    def _normalize_target_for_rule(
        self,
        rule: MethodologyRule,
        target: str,
        domain: str,
    ) -> str:
        """Match target shape to the tool family behind a methodology rule."""
        command_head = rule.command_template.strip().split()[0].lower() if rule.command_template.strip() else ""

        if command_head in {"nmap", "dnsx"} or rule.technique in {"nmap_initial", "ssl_check", "dnsx_subdomains"}:
            host = self._extract_host(target)
            return host or domain

        if command_head in {"httpx", "whatweb", "ffuf", "katana", "nuclei", "wpscan", "nikto", "sqlmap", "curl", "wafw00f"}:
            return self._canonical_hint_target(target)

        return target

    def _apply_rate_limit(self, cmd: str, rule: MethodologyRule) -> str:
        """Apply Analyst-directed rate limiting to a command."""
        if not self._rate_limit:
            return cmd
        max_threads = self._rate_limit.get("max_threads")
        if max_threads and "-t " in cmd:
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
        target = re.sub(r'^https?://', '', target)
        target = target.split('/')[0].split(':')[0]
        return target.lower()

    @staticmethod
    def _extract_host(target: str) -> str:
        """Extract a hostname from a URL, host, or host:port string."""
        if "://" in target:
            parsed = urlparse(target)
            return (parsed.hostname or "").lower()
        return target.split("/")[0].split(":")[0].lower()

    def _canonical_hint_target(self, target: str) -> str:
        """Prefer a full origin for known web targets; otherwise keep the raw scope."""
        host = self._extract_host(target)
        if not host:
            return target
        if "://" in target:
            parsed = urlparse(target)
            if parsed.scheme and parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}"
        return self._live_http_origins.get(host, target)

    def _remember_target(self, target: str, assume_live_http: bool = False) -> None:
        """Track a discovered target in host and origin form."""
        host = self._extract_host(target)
        if host:
            self._known_hosts.add(host)
        if assume_live_http or "://" in target:
            self._remember_live_http_target(target)

    def _remember_live_http_target(self, target: str) -> None:
        """Track a live HTTP origin plus its hostname."""
        normalized = target.strip().rstrip("/")
        if not normalized:
            return
        if "://" not in normalized:
            normalized = f"https://{normalized}"
        parsed = urlparse(normalized)
        host = (parsed.hostname or "").lower()
        if not host:
            return
        origin = f"{parsed.scheme}://{parsed.netloc}"
        self._known_hosts.add(host)
        self._live_http_hosts.add(host)
        self._live_http_origins[host] = origin

    def _format_live_http_target(self, rule: MethodologyRule, host: str) -> str:
        """Return the right target shape for a live HTTP rule."""
        if rule.technique == "ssl_check":
            return host
        return self._live_http_origins.get(host, f"https://{host}")

    def _is_target_skipped(self, target: str) -> bool:
        host = self._extract_host(target)
        return target in self._skip_targets or host in self._skip_targets

    @staticmethod
    def _dedupe_preserve_order(values: List[str]) -> List[str]:
        seen: Set[str] = set()
        result: List[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

"""
Pentesting Methodology — structured playbook for the Planner agent.

Each MethodologyRule defines:
  - trigger: condition on scan state that activates this rule
  - technique: unique name for dedup
  - phase: which scan phase this belongs to
  - command_template: shell command with {target} placeholder
  - priority: 0=highest, 100=lowest (controls execution order)
  - target_selector: how to pick targets ("all_hosts", "live_http", "with_tech:X", etc.)

The Planner iterates rules against current state and emits WorkUnits for
rules whose triggers are satisfied and whose technique hasn't been run yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import List, Optional


class TriggerType(StrEnum):
    """Conditions that activate a methodology rule."""
    ALWAYS = "always"              # Run as soon as phase starts
    HOST_DISCOVERED = "host_discovered"  # New host/subdomain found
    HOST_LIVE_HTTP = "host_live_http"    # Host confirmed serving HTTP
    TECH_DETECTED = "tech_detected"      # Specific technology detected
    PARAMS_FOUND = "params_found"        # URL parameters discovered
    PORTS_FOUND = "ports_found"          # Open ports discovered
    LOGIN_FOUND = "login_found"          # Login page/auth endpoint found
    API_FOUND = "api_found"              # API endpoint discovered
    ANALYST_HINT = "analyst_hint"        # Analyst issued an attack_hint directive


@dataclass
class MethodologyRule:
    """A single pentesting playbook rule."""
    technique: str                    # Unique name (dedup key)
    phase: str                        # recon, enumeration, vuln_scan, exploitation
    trigger: TriggerType              # When to activate
    command_template: str             # Shell command ({target} = placeholder)
    priority: int = 50                # 0=highest
    description: str = ""             # Human-readable purpose
    target_selector: str = "primary"  # How to select targets
    tech_filter: Optional[str] = None # For TECH_DETECTED trigger: match this tech
    timeout: int = 600                # Suggested timeout for this command
    max_targets: int = 20             # Max targets to include in one work unit


# ---------------------------------------------------------------------------
# Playbook: Ordered rules for each phase
# ---------------------------------------------------------------------------

RECON_RULES: List[MethodologyRule] = [
    # Passive discovery — zero noise
    MethodologyRule(
        technique="subfinder",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="subfinder -d {domain} -silent",
        priority=10,
        description="Passive subdomain enumeration",
        target_selector="primary_domain",
        timeout=300,
    ),
    MethodologyRule(
        technique="waybackurls",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="echo {domain} | waybackurls",
        priority=10,
        description="Historical URL harvesting from Wayback Machine",
        target_selector="primary_domain",
        timeout=600,
    ),
    MethodologyRule(
        technique="gau",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="gau {domain} --subs",
        priority=10,
        description="Passive URL harvesting from multiple archives",
        target_selector="primary_domain",
        timeout=600,
    ),
    # Technology fingerprinting
    MethodologyRule(
        technique="whatweb_primary",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="whatweb {target}",
        priority=15,
        description="Technology fingerprinting on primary target",
        target_selector="primary",
        timeout=120,
    ),
    MethodologyRule(
        technique="httpx_primary",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="echo '{target}' | httpx -sc -title -tech-detect -silent",
        priority=15,
        description="HTTP probe with tech detection",
        target_selector="primary",
        timeout=120,
    ),
    # Targeted port scan (common ports only for stealth)
    MethodologyRule(
        technique="nmap_initial",
        phase="recon",
        trigger=TriggerType.ALWAYS,
        command_template="nmap -sV -sC -T3 -p 21,22,25,80,443,3306,5432,8080,8443,27017,6379 {target}",
        priority=20,
        description="Initial targeted port scan with service detection",
        target_selector="primary",
        timeout=300,
    ),
    # Subdomain probing (after subfinder results)
    MethodologyRule(
        technique="httpx_subdomains",
        phase="recon",
        trigger=TriggerType.HOST_DISCOVERED,
        command_template="echo '{target}' | httpx -sc -title -tech-detect -silent",
        priority=25,
        description="Probe discovered subdomains for live HTTP services",
        target_selector="all_hosts",
        timeout=300,
        max_targets=50,
    ),
    MethodologyRule(
        technique="dnsx_subdomains",
        phase="recon",
        trigger=TriggerType.HOST_DISCOVERED,
        command_template="echo '{target}' | dnsx -a -cname -resp -silent",
        priority=25,
        description="DNS resolution for origin IP discovery",
        target_selector="all_hosts",
        timeout=120,
        max_targets=50,
    ),
]

ENUMERATION_RULES: List[MethodologyRule] = [
    # Directory brute-force (low rate for stealth)
    MethodologyRule(
        technique="ffuf_common",
        phase="enumeration",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="ffuf -u {target}/FUZZ -w /usr/share/seclists/Discovery/Web-Content/common.txt -mc 200,301,302,403 -t 5 -rate 10 -s",
        priority=30,
        description="Directory brute-force with common wordlist",
        target_selector="live_http",
        timeout=600,
    ),
    # URL crawling
    MethodologyRule(
        technique="katana_crawl",
        phase="enumeration",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="katana -u {target} -d 3 -rl 10 -silent",
        priority=35,
        description="JavaScript-aware web crawling",
        target_selector="live_http",
        timeout=600,
    ),
    # Robots/sitemap
    MethodologyRule(
        technique="robots_sitemap",
        phase="enumeration",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="curl -sL {target}/robots.txt && curl -sL {target}/sitemap.xml | head -100",
        priority=20,
        description="Extract hidden paths from robots.txt and sitemap",
        target_selector="live_http",
        timeout=60,
    ),
    # Technology-specific enumeration
    MethodologyRule(
        technique="wpscan",
        phase="enumeration",
        trigger=TriggerType.TECH_DETECTED,
        tech_filter="wordpress",
        command_template="wpscan --url {target} --enumerate vp,vt,u --random-user-agent --throttle 500",
        priority=25,
        description="WordPress-specific enumeration",
        target_selector="with_tech",
        timeout=900,
    ),
]

VULN_SCAN_RULES: List[MethodologyRule] = [
    # Nuclei — targeted first, broad later
    MethodologyRule(
        technique="nuclei_critical",
        phase="vuln_scan",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nuclei -u {target} -severity critical,high -rl 15 -silent",
        priority=20,
        description="High/critical vulnerability scan with nuclei",
        target_selector="live_http",
        timeout=900,
    ),
    MethodologyRule(
        technique="nuclei_config",
        phase="vuln_scan",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nuclei -u {target} -tags exposed-panels,config,misconfiguration -rl 10 -silent",
        priority=25,
        description="Configuration and exposed panel detection",
        target_selector="live_http",
        timeout=600,
    ),
    MethodologyRule(
        technique="nuclei_cves",
        phase="vuln_scan",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nuclei -u {target} -tags cve -rl 10 -silent",
        priority=30,
        description="Known CVE scanning",
        target_selector="live_http",
        timeout=900,
    ),
    # SSL/TLS
    MethodologyRule(
        technique="ssl_check",
        phase="vuln_scan",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nmap --script ssl-enum-ciphers -p 443 {target}",
        priority=40,
        description="SSL/TLS configuration audit",
        target_selector="live_http",
        timeout=300,
    ),
    # Security headers
    MethodologyRule(
        technique="security_headers",
        phase="vuln_scan",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="curl -sI {target} | grep -iE '(x-frame|x-content|strict-transport|content-security|x-xss|referrer-policy|permissions-policy)'",
        priority=35,
        description="Security header analysis",
        target_selector="live_http",
        timeout=60,
    ),
    # Parameter testing
    MethodologyRule(
        technique="sqlmap_params",
        phase="vuln_scan",
        trigger=TriggerType.PARAMS_FOUND,
        command_template="sqlmap -u '{target}' --batch --random-agent --level 2 --risk 2 --threads 3",
        priority=30,
        description="SQL injection testing on discovered parameters",
        target_selector="parameterized_urls",
        timeout=1800,
    ),
]

EXPLOITATION_RULES: List[MethodologyRule] = [
    # Exploitation is primarily Analyst-driven via directives,
    # but these are baseline rules for common confirmations
    MethodologyRule(
        technique="nuclei_full",
        phase="exploitation",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nuclei -u {target} -rl 10 -silent",
        priority=40,
        description="Full nuclei template scan for comprehensive coverage",
        target_selector="live_http",
        timeout=1200,
    ),
    MethodologyRule(
        technique="nikto",
        phase="exploitation",
        trigger=TriggerType.HOST_LIVE_HTTP,
        command_template="nikto -h {target} -Tuning 1234567890abcde",
        priority=45,
        description="Nikto web server scanner",
        target_selector="live_http",
        timeout=900,
    ),
]


# All rules in phase order
ALL_RULES: List[MethodologyRule] = (
    RECON_RULES + ENUMERATION_RULES + VULN_SCAN_RULES + EXPLOITATION_RULES
)


def get_rules_for_phase(phase: str) -> List[MethodologyRule]:
    """Get methodology rules for a given scan phase."""
    return [r for r in ALL_RULES if r.phase == phase]


def get_rule_by_technique(technique: str) -> Optional[MethodologyRule]:
    """Look up a rule by its technique name."""
    for r in ALL_RULES:
        if r.technique == technique:
            return r
    return None

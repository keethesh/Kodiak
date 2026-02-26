"""
Kodiak Canonical Tool Registry
===============================
Single source of truth for ALL tools and commands available in the Kodiak
Docker sandbox. Every consumer (manager prompt, preflight, doctor, gating)
derives from this module.

Tool Tiers
----------
CORE     — Primary pentest tools. Full prompt examples. Preflight-probed. Gated by allowed_tools.
EXTENDED — Important tools the LLM should know exist. Brief prompt mention. Preflight-probed. Not gated.
UTILITY  — Standard Kali utilities. No explicit prompt entry (LLM infers from Kali baseline). Not probed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class ToolTier(str, Enum):
    # Detailed examples in prompt, preflight-probed, blocked unless in allowed_tools
    CORE = "core"
    # Brief mention in prompt, preflight-probed, always allowed
    EXTENDED = "extended"
    # Not in prompt at all, always allowed (standard Linux/Kali builtins)
    UTILITY = "utility"


@dataclass
class ToolEntry:
    name: str
    binary: str           # Binary name to probe with `command -v`
    tier: ToolTier
    description: str      # Short description used in AVAILABLE_TOOLS & brief prompt entries
    prompt_usage: str = ""  # Example command(s) for the <tool_catalog>; CORE only
    prompt_category: str = ""  # Section header in <tool_catalog>; CORE only

    @property
    def is_gated(self) -> bool:
        return self.tier == ToolTier.CORE

    @property
    def requires_preflight(self) -> bool:
        return self.tier in (ToolTier.CORE, ToolTier.EXTENDED)


# =============================================================================
# CANONICAL TOOL REGISTRY
# =============================================================================
TOOL_REGISTRY: List[ToolEntry] = [

    # -------------------------------------------------------------------------
    # CORE — Reconnaissance
    # -------------------------------------------------------------------------
    ToolEntry(
        name="subfinder",
        binary="subfinder",
        tier=ToolTier.CORE,
        description="Passive subdomain enumeration",
        prompt_usage="`subfinder -d <domain> -silent` — Passive subdomain enumeration",
        prompt_category="Reconnaissance",
    ),
    ToolEntry(
        name="gau",
        binary="gau",
        tier=ToolTier.CORE,
        description="GetAllUrls — fetch known URLs from AlienVault, Wayback, Common Crawl",
        prompt_usage=(
            "`gau <domain> --subs` — Passive URL harvesting from public archives. "
            "Run early in RECON to seed targeted scanning. Pipe to `grep -iE '\\.(js|json|xml|config|env|bak|sql)'` for high-value files."
        ),
        prompt_category="Reconnaissance",
    ),
    ToolEntry(
        name="waybackurls",
        binary="waybackurls",
        tier=ToolTier.CORE,
        description="Fetch URLs from the Wayback Machine for a domain",
        prompt_usage=(
            "`echo <domain> | waybackurls` — Fetch historical URLs from the Wayback Machine. "
            "Reveals forgotten endpoints, old API routes, admin panels. Combine with gau for full coverage."
        ),
        prompt_category="Reconnaissance",
    ),
    ToolEntry(
        name="nmap",
        binary="nmap",
        tier=ToolTier.CORE,
        description="Network discovery and security auditing",
        prompt_usage=(
            "`nmap -sV -sC -p <ports> <target>` — Port scan + service detection. "
            "Use -p- for all ports, -T4 for speed."
        ),
        prompt_category="Reconnaissance",
    ),
    ToolEntry(
        name="httpx",
        binary="httpx",
        tier=ToolTier.CORE,
        description="HTTP toolkit for probing web services",
        prompt_usage="`httpx -l <file> -sc -title -tech-detect` — HTTP probe with status codes and tech detection",
        prompt_category="Reconnaissance",
    ),
    ToolEntry(
        name="whatweb",
        binary="whatweb",
        tier=ToolTier.CORE,
        description="Web technology fingerprinting tool",
        prompt_usage="`whatweb <url>` — Web technology fingerprinting (CMS, frameworks, server)",
        prompt_category="Reconnaissance",
    ),

    # -------------------------------------------------------------------------
    # CORE — Web Crawling & Fuzzing
    # -------------------------------------------------------------------------
    ToolEntry(
        name="katana",
        binary="katana",
        tier=ToolTier.CORE,
        description="Web crawler for discovering URLs and API endpoints",
        prompt_usage=(
            "`katana -u <url> -d <depth> -silent` — Crawl websites for endpoints. "
            "Use -jc for JS, -rl <n> for rate limit."
        ),
        prompt_category="Web Crawling & Fuzzing",
    ),
    ToolEntry(
        name="ffuf",
        binary="ffuf",
        tier=ToolTier.CORE,
        description="Fast web fuzzer for discovering hidden directories and files",
        prompt_usage=(
            "`ffuf -u <url>/FUZZ -w <wordlist> -mc 200,301,302 -t <threads>` — Directory/file fuzzing\n"
            "  Wordlists: /usr/share/seclists/Discovery/Web-Content/common.txt (fast), big.txt (thorough)"
        ),
        prompt_category="Web Crawling & Fuzzing",
    ),

    # -------------------------------------------------------------------------
    # CORE — Vulnerability Scanning
    # -------------------------------------------------------------------------
    ToolEntry(
        name="nuclei",
        binary="nuclei",
        tier=ToolTier.CORE,
        description="Fast vulnerability scanner with YAML templates",
        prompt_usage=(
            "`nuclei -u <url> -rl <rate> -silent` — Template-based vuln scanner. "
            "Tags: -tags cve,sqli,xss,lfi,rce. Severity: -s critical,high,medium,low. "
            "Use -as for auto-template selection."
        ),
        prompt_category="Vulnerability Scanning",
    ),
    ToolEntry(
        name="wpscan",
        binary="wpscan",
        tier=ToolTier.CORE,
        description="WordPress security scanner for core, plugin, theme, and config issues",
        prompt_usage="`wpscan --url <url> -e vp,vt,u --api-token $WPSCAN_API_TOKEN` — WordPress vuln scanner",
        prompt_category="Vulnerability Scanning",
    ),

    # -------------------------------------------------------------------------
    # CORE — Exploitation
    # -------------------------------------------------------------------------
    ToolEntry(
        name="sqlmap",
        binary="sqlmap",
        tier=ToolTier.CORE,
        description="Automatic SQL injection detection and exploitation",
        prompt_usage=(
            "`sqlmap -u <url> --data=<post> --batch --level=3 --risk=2` — SQL injection. "
            "Use --dump, --os-shell, --technique=BEUSTQ"
        ),
        prompt_category="Exploitation",
    ),
    ToolEntry(
        name="commix",
        binary="commix",
        tier=ToolTier.CORE,
        description="Command injection detection and exploitation",
        prompt_usage="`commix --url=<url> --data=<post> --batch` — OS command injection",
        prompt_category="Exploitation",
    ),
    ToolEntry(
        name="searchsploit",
        binary="searchsploit",
        tier=ToolTier.CORE,
        description="Offline Exploit-DB search and exploit export",
        prompt_usage="`searchsploit <query>` — Offline Exploit-DB search. Use after identifying service versions.",
        prompt_category="Exploitation",
    ),
    ToolEntry(
        name="hydra",
        binary="hydra",
        tier=ToolTier.CORE,
        description="Online login brute-force attack tool",
        prompt_usage=(
            "`hydra -l <user> -P <wordlist> <target> http-post-form '<path>:<params>:F=<fail_string>'` — HTTP brute-force.\n"
            "  Supports ftp, ssh, smtp, http-get, http-post-form, rdp, mysql and many more."
        ),
        prompt_category="Exploitation",
    ),

    # -------------------------------------------------------------------------
    # EXTENDED — Reconnaissance
    # -------------------------------------------------------------------------
    ToolEntry(
        name="dnsx",
        binary="dnsx",
        tier=ToolTier.EXTENDED,
        description="Fast DNS resolver and toolkit for bulk DNS queries",
    ),
    ToolEntry(
        name="gospider",
        binary="gospider",
        tier=ToolTier.EXTENDED,
        description="Fast web spider for crawling and link extraction",
    ),
    # gau and waybackurls promoted to CORE — see Reconnaissance section above
    ToolEntry(
        name="masscan",
        binary="masscan",
        tier=ToolTier.EXTENDED,
        description="Extremely fast Internet port scanner",
    ),
    ToolEntry(
        name="naabu",
        binary="naabu",
        tier=ToolTier.EXTENDED,
        description="Fast port scanner written in Go",
    ),
    ToolEntry(
        name="arjun",
        binary="arjun",
        tier=ToolTier.EXTENDED,
        description="HTTP parameter discovery suite",
    ),
    ToolEntry(
        name="wafw00f",
        binary="wafw00f",
        tier=ToolTier.EXTENDED,
        description="WAF fingerprinting and detection tool",
    ),

    # -------------------------------------------------------------------------
    # EXTENDED — Vulnerability Scanning
    # -------------------------------------------------------------------------
    ToolEntry(
        name="nikto",
        binary="nikto",
        tier=ToolTier.EXTENDED,
        description="Web server misconfiguration and vulnerability scanner",
    ),
    ToolEntry(
        name="dirsearch",
        binary="dirsearch",
        tier=ToolTier.EXTENDED,
        description="Web path discovery tool",
    ),
    ToolEntry(
        name="trufflehog",
        binary="trufflehog",
        tier=ToolTier.EXTENDED,
        description="Secret scanning for credentials and API keys in code/repos",
    ),
    ToolEntry(
        name="trivy",
        binary="trivy",
        tier=ToolTier.EXTENDED,
        description="Container and code vulnerability scanner (CVEs, IaC, secrets)",
    ),
    ToolEntry(
        name="semgrep",
        binary="semgrep",
        tier=ToolTier.EXTENDED,
        description="Static analysis tool for finding security issues in source code",
    ),
    ToolEntry(
        name="interactsh-client",
        binary="interactsh-client",
        tier=ToolTier.EXTENDED,
        description="Out-of-band interaction server client for blind injection testing",
    ),

    # -------------------------------------------------------------------------
    # EXTENDED — Web Application
    # -------------------------------------------------------------------------
    ToolEntry(
        name="jwt-tool",
        binary="jwt_tool",
        tier=ToolTier.EXTENDED,
        description="JWT manipulation and attack tool (alg confusion, none attack, brute)",
    ),
    ToolEntry(
        name="xsstrike",
        binary="xsstrike",
        tier=ToolTier.EXTENDED,
        description="Advanced XSS scanner with fuzzing, crawling, and DOM XSS detection",
    ),

    # -------------------------------------------------------------------------
    # UTILITY — Standard Linux / Kali builtins
    # These are NOT mentioned explicitly in the prompt — the LLM knows them as
    # standard system tools on any Kali box.
    # -------------------------------------------------------------------------
    ToolEntry(name="curl",        binary="curl",        tier=ToolTier.UTILITY, description="HTTP client"),
    ToolEntry(name="dig",         binary="dig",         tier=ToolTier.UTILITY, description="DNS lookup"),
    ToolEntry(name="whois",       binary="whois",       tier=ToolTier.UTILITY, description="WHOIS lookup"),
    ToolEntry(name="host",        binary="host",        tier=ToolTier.UTILITY, description="DNS lookup utility"),
    ToolEntry(name="ncat",        binary="ncat",        tier=ToolTier.UTILITY, description="Netcat networking utility"),
    ToolEntry(name="mysql",       binary="mysql",       tier=ToolTier.UTILITY, description="MySQL client"),
    ToolEntry(name="jq",          binary="jq",          tier=ToolTier.UTILITY, description="JSON processor"),
    ToolEntry(name="ripgrep",     binary="rg",          tier=ToolTier.UTILITY, description="Fast grep"),
    ToolEntry(name="gf",          binary="gf",          tier=ToolTier.UTILITY, description="Pattern matching for gau/waybackurls output"),
    ToolEntry(name="bandit",      binary="bandit",      tier=ToolTier.UTILITY, description="Python SAST tool"),
    ToolEntry(name="retire",      binary="retire",      tier=ToolTier.UTILITY, description="JavaScript vulnerability scanner"),
]


# =============================================================================
# DERIVED VIEWS  — used by all consumers
# =============================================================================

def get_gated_tool_names() -> set[str]:
    """Names of tools blocked by the manager unless in the allowed_tools list."""
    return {e.name for e in TOOL_REGISTRY if e.is_gated}


def get_docker_tool_map() -> dict[str, str]:
    """Tool name -> binary name, for preflight probing in Docker. Core + Extended tools only."""
    return {e.name: e.binary for e in TOOL_REGISTRY if e.requires_preflight}


def get_available_tools() -> dict[str, str]:
    """Tool name -> description for AVAILABLE_TOOLS and list_tools() output.
    Covers Core + Extended (not Utility — those are implicit).
    """
    return {e.name: e.description for e in TOOL_REGISTRY if e.tier != ToolTier.UTILITY}


def get_prompt_catalog() -> list[str]:
    """
    Build the <tool_catalog> XML section injected into the manager's system prompt.

    Layout:
    - Core tools: grouped by category with full usage examples
    - Extended tools: a single compact block — one line per tool
    - Footer: blanket Kali utilities notice
    """
    lines: list[str] = [
        "<tool_catalog>",
        "All tools are pre-installed in a Kali-based Docker sandbox. Use any bash command.",
        "",
    ]

    # ---- Core tools grouped by category ----
    categories: dict[str, list[ToolEntry]] = {}
    for entry in TOOL_REGISTRY:
        if entry.tier == ToolTier.CORE:
            categories.setdefault(entry.prompt_category, []).append(entry)

    # Maintain a sensible ordering
    ordered_categories = [
        "Reconnaissance",
        "Web Crawling & Fuzzing",
        "Vulnerability Scanning",
        "Exploitation",
    ]
    for category in ordered_categories:
        entries = categories.get(category, [])
        if not entries:
            continue
        lines.append(f"## {category}")
        for entry in entries:
            for line in entry.prompt_usage.splitlines():
                lines.append(f"- {line}" if not line.startswith("- ") and not line.startswith(" ") else line)
        lines.append("")

    # ---- Extended tools — brief compact block ----
    extended = [e for e in TOOL_REGISTRY if e.tier == ToolTier.EXTENDED]
    if extended:
        lines.append("## Additional Tools Available")
        for entry in extended:
            lines.append(f"- `{entry.name}` — {entry.description}")
        lines.append("")

    # ---- Utility footer ----
    lines.extend([
        "## General Purpose",
        "- `curl -s -I <url>` — HTTP requests with full header control. Use for WAF bypass, path traversal, custom headers.",
        "- Standard Kali utilities: dig, whois, ncat, mysql, jq, ripgrep, gf, bandit, retire, and all standard Linux commands.",
        "</tool_catalog>",
    ])

    return lines

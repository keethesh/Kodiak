import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor


class SubfinderArgs(BaseModel):
    domain: str = Field(..., description="Target domain for subdomain enumeration")
    sources: Optional[str] = Field(None, description="Comma-separated list of sources to use")
    recursive: bool = Field(False, description="Enable recursive subdomain enumeration")
    timeout: int = Field(30, description="Timeout in seconds")


class SubfinderTool(KodiakTool):
    name = "subfinder"
    description = "Fast passive subdomain enumeration tool. Discovers subdomains using multiple sources like certificate transparency, search engines, and APIs."
    args_schema = SubfinderArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Target domain (e.g., example.com, google.com)"
                },
                "sources": {
                    "type": "string",
                    "description": "Comma-separated sources (certspotter,crtsh,hackertarget,virustotal)"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "Enable recursive enumeration for deeper discovery"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default: 30)"
                }
            },
            "required": ["domain"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        domain_str = args["domain"]
        domains = [d.strip() for d in domain_str.split(",") if d.strip()]
        
        # Build subfinder command
        command = [
            "subfinder",
            "-json",
            "-silent",
            "-timeout", str(args.get("timeout", 30))
        ]
        
        for d in domains:
            command.extend(["-d", d])
            
        if args.get("sources"):
            command.extend(["-sources", args["sources"]])
        
        if args.get("recursive"):
            command.append("-recursive")
        
        cmd_str = " ".join(command)

        try:
            # Docker is the PRIMARY execution path for security tools
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor
            
            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="projectdiscovery/subfinder:latest",
                fallback_entrypoint=""
            )
            
            result = await executor.run_command(command)
            
            if result.exit_code != 0:
                return ToolResult(
                    success=False,
                    output=f"Subfinder failed: {result.stderr}",
                    error=f"Command failed with exit code {result.exit_code}"
                )
            
            # Parse JSON output
            subdomains = self._parse_subfinder_output(result.stdout)
            
            # Generate summary
            summary = self._generate_subfinder_summary(domain_str, subdomains)
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "domain": domain_str,
                    "subdomains": subdomains,
                    "total_found": len(subdomains),
                    "unique_subdomains": list(set(subdomains))
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Subfinder execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_subfinder_output(self, output: str) -> List[str]:
        """Parse subfinder JSON output to extract subdomains"""
        subdomains = []
        
        if not output.strip():
            return subdomains
        
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    host = data.get('host')
                    if host:
                        subdomains.append(host)
                except json.JSONDecodeError:
                    # If not JSON, might be plain text output
                    if '.' in line.strip():
                        subdomains.append(line.strip())
        
        return subdomains

    def _generate_subfinder_summary(self, domain: str, subdomains: List[str]) -> str:
        """Generate human-readable summary"""
        unique_subdomains = list(set(subdomains))
        
        summary = f"Subfinder Subdomain Enumeration Results for {domain}\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Total Subdomains Found: {len(unique_subdomains)}\n\n"
        
        if unique_subdomains:
            summary += "Discovered Subdomains:\n"
            for subdomain in sorted(unique_subdomains)[:20]:  # Show first 20
                summary += f"  - {subdomain}\n"
            
            if len(unique_subdomains) > 20:
                summary += f"  ... and {len(unique_subdomains) - 20} more\n"
        else:
            summary += "No subdomains discovered.\n"
        
        return summary


class HttpxArgs(BaseModel):
    target: str = Field(..., description="Target URL, domain, or comma-separated list")
    ports: Optional[str] = Field(None, description="Ports to probe (e.g., '80,443,8080')")
    follow_redirects: bool = Field(True, description="Follow HTTP redirects")
    timeout: int = Field(10, description="HTTP request timeout in seconds")
    threads: int = Field(50, description="Number of concurrent threads")
    status_code: bool = Field(True, description="Display HTTP status codes")
    title: bool = Field(True, description="Display page titles")
    tech_detect: bool = Field(True, description="Enable technology detection")


class HttpxTool(KodiakTool):
    name = "httpx"
    description = "Fast and multi-purpose HTTP toolkit. Probes for live web servers, extracts titles, detects technologies, and gathers HTTP information."
    args_schema = HttpxArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target URL, domain, or comma-separated list (e.g., 'example.com', 'https://example.com', 'sub1.example.com,sub2.example.com')"
                },
                "ports": {
                    "type": "string",
                    "description": "Ports to probe (e.g., '80,443,8080,8443')"
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "Follow HTTP redirects (default: true)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "HTTP request timeout in seconds (default: 10)"
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of concurrent threads (default: 50)"
                },
                "status_code": {
                    "type": "boolean",
                    "description": "Display HTTP status codes (default: true)"
                },
                "title": {
                    "type": "boolean",
                    "description": "Extract and display page titles (default: true)"
                },
                "tech_detect": {
                    "type": "boolean",
                    "description": "Enable technology detection (default: true)"
                }
            },
            "required": ["target"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        target = args["target"]
        
        # Build httpx command
        command = [
            "httpx",
            "-json",
            "-silent",
            "-timeout", str(args.get("timeout", 10)),
            "-threads", str(args.get("threads", 50))
        ]
        
        # Add target(s)
        if ',' in target:
            # Multiple targets - use stdin
            command.append("-l")
            command.append("/dev/stdin")
            stdin_data = '\n'.join(target.split(','))
        else:
            # Single target
            command.extend(["-u", target])
            stdin_data = None
        
        # Add optional flags
        if args.get("ports"):
            command.extend(["-ports", args["ports"]])
        
        if args.get("follow_redirects", True):
            command.append("-fr")
        
        if args.get("status_code", True):
            command.append("-sc")
        
        if args.get("title", True):
            command.append("-title")
        
        if args.get("tech_detect", True):
            command.append("-tech-detect")
        
        cmd_str = " ".join(command)

        try:
            # Docker is the PRIMARY execution path for security tools
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor
            
            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="projectdiscovery/httpx:latest",
                fallback_entrypoint=""
            )
            
            result = await executor.run_command(command, stdin=stdin_data)
            
            if result.exit_code != 0:
                return ToolResult(
                    success=False,
                    output=f"Httpx failed: {result.stderr}",
                    error=f"Command failed with exit code {result.exit_code}"
                )
            
            # Parse JSON output
            results = self._parse_httpx_output(result.stdout)
            
            # Generate summary
            summary = self._generate_httpx_summary(target, results)
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "target": target,
                    "results": results,
                    "live_hosts": len(results),
                    "technologies": self._extract_technologies(results),
                    "status_codes": self._extract_status_codes(results)
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Httpx execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_httpx_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse httpx JSON output"""
        results = []
        
        if not output.strip():
            return results
        
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    data = json.loads(line)
                    # Enhance with additional analysis
                    enhanced_data = self._enhance_httpx_result(data)
                    results.append(enhanced_data)
                except json.JSONDecodeError:
                    continue
        
        return results

    def _enhance_httpx_result(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance httpx result with additional analysis"""
        enhanced = data.copy()
        
        # Assess security posture
        enhanced["security_assessment"] = self._assess_security(data)
        
        # Extract interesting headers
        headers = data.get("header", {})
        enhanced["security_headers"] = {
            "x-frame-options": headers.get("x-frame-options"),
            "content-security-policy": headers.get("content-security-policy"),
            "strict-transport-security": headers.get("strict-transport-security"),
            "x-content-type-options": headers.get("x-content-type-options"),
            "x-xss-protection": headers.get("x-xss-protection")
        }
        
        return enhanced

    def _assess_security(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Assess security posture of the HTTP service"""
        assessment = {
            "https_enabled": data.get("url", "").startswith("https://"),
            "security_score": 0,
            "issues": []
        }
        
        headers = data.get("header", {})
        
        # Check for security headers
        if headers.get("strict-transport-security"):
            assessment["security_score"] += 20
        else:
            assessment["issues"].append("Missing HSTS header")
        
        if headers.get("x-frame-options") or headers.get("content-security-policy"):
            assessment["security_score"] += 15
        else:
            assessment["issues"].append("Missing clickjacking protection")
        
        if headers.get("x-content-type-options") == "nosniff":
            assessment["security_score"] += 10
        else:
            assessment["issues"].append("Missing X-Content-Type-Options header")
        
        if headers.get("x-xss-protection"):
            assessment["security_score"] += 10
        else:
            assessment["issues"].append("Missing X-XSS-Protection header")
        
        # Check for information disclosure
        server_header = headers.get("server", "")
        if server_header and any(version in server_header.lower() for version in ["apache/", "nginx/", "iis/"]):
            assessment["issues"].append(f"Server version disclosed: {server_header}")
        
        return assessment

    def _extract_technologies(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Extract and count technologies found"""
        tech_count = {}
        
        for result in results:
            technologies = result.get("tech", [])
            for tech in technologies:
                tech_count[tech] = tech_count.get(tech, 0) + 1
        
        return tech_count

    def _extract_status_codes(self, results: List[Dict[str, Any]]) -> Dict[str, int]:
        """Extract and count HTTP status codes"""
        status_count = {}
        
        for result in results:
            status = str(result.get("status_code", "unknown"))
            status_count[status] = status_count.get(status, 0) + 1
        
        return status_count

    def _generate_httpx_summary(self, target: str, results: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary"""
        summary = f"Httpx HTTP Probing Results for {target}\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Live Hosts Found: {len(results)}\n\n"
        
        if not results:
            summary += "No live HTTP services discovered.\n"
            return summary
        
        # Status code breakdown
        status_codes = self._extract_status_codes(results)
        summary += "Status Code Breakdown:\n"
        for status, count in sorted(status_codes.items()):
            summary += f"  {status}: {count}\n"
        summary += "\n"
        
        # Technology breakdown
        technologies = self._extract_technologies(results)
        if technologies:
            summary += "Technologies Detected:\n"
            for tech, count in sorted(technologies.items(), key=lambda x: x[1], reverse=True)[:10]:
                summary += f"  {tech}: {count}\n"
            summary += "\n"
        
        # Live hosts details
        summary += "Live Hosts:\n"
        for i, result in enumerate(results[:10], 1):  # Show first 10
            url = result.get("url", "N/A")
            status = result.get("status_code", "N/A")
            title = result.get("title", "N/A")
            
            summary += f"{i:2d}. {url} [{status}]\n"
            if title and title != "N/A":
                summary += f"     Title: {title[:60]}{'...' if len(title) > 60 else ''}\n"
            
            # Security assessment
            security = result.get("security_assessment", {})
            if security.get("issues"):
                summary += f"     Security Issues: {len(security['issues'])}\n"
        
        if len(results) > 10:
            summary += f"... and {len(results) - 10} more hosts\n"
        
        return summary


class KatanaArgs(BaseModel):
    url: str = Field(..., description="Target URL to crawl")
    depth: int = Field(2, description="Crawl depth (default: 2)")
    js_crawl: bool = Field(True, description="Enable JavaScript crawling for SPAs and dynamic content")
    headless: bool = Field(False, description="Use headless browser for JavaScript rendering")
    timeout: int = Field(30, description="Request timeout in seconds")
    rate_limit: int = Field(150, description="Maximum requests per second")
    scope: Optional[str] = Field(None, description="Scope regex to restrict crawling (e.g., 'example\\.com')") 


class KatanaTool(KodiakTool):
    name = "katana"
    description = "Fast, configurable web crawler for discovering URLs, endpoints, JavaScript files, and API routes. Ideal for mapping the full attack surface of a web application."
    args_schema = KatanaArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL to start crawling from (e.g., https://example.com)"
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum crawl depth (default: 2, higher means deeper but slower)"
                },
                "js_crawl": {
                    "type": "boolean",
                    "description": "Parse JavaScript files to find additional endpoints (default: true)"
                },
                "headless": {
                    "type": "boolean",
                    "description": "Use headless browser for JS-rendered content (slower but more thorough)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 30)"
                },
                "rate_limit": {
                    "type": "integer",
                    "description": "Max requests per second to avoid detection (default: 150)"
                },
                "scope": {
                    "type": "string",
                    "description": "Regex pattern to limit crawling scope (e.g., 'example\\.com')"
                }
            },
            "required": ["url"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        url = args["url"]

        command = [
            "katana",
            "-u", url,
            "-d", str(args.get("depth", 2)),
            "-rl", str(args.get("rate_limit", 150)),
            "-timeout", str(args.get("timeout", 30)),
            "-silent",
            "-jc" if args.get("js_crawl", True) else "",
        ]
        command = [c for c in command if c]

        if args.get("headless"):
            command.append("-headless")
        if args.get("scope"):
            command.extend(["-fs", args["scope"]])

        cmd_str = " ".join(command)

        try:
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor

            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="projectdiscovery/katana:latest",
                fallback_entrypoint=""
            )
            result = await executor.run_command(command)

            if result.exit_code != 0:
                return ToolResult(
                    success=False,
                    output=f"Katana failed: {result.stderr}",
                    error=f"Command failed with exit code {result.exit_code}"
                )

            urls = self._parse_urls(result.stdout)
            summary = self._generate_summary(url, urls)

            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "target": url,
                    "urls": urls,
                    "total_found": len(urls),
                    "endpoints": [u for u in urls if any(p in u for p in ["api", "graphql", "v1", "v2", "rest"])],
                    "js_files": [u for u in urls if u.endswith(".js")],
                    "forms": [u for u in urls if "?" in u],
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Katana execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_urls(self, output: str) -> List[str]:
        """Parse katana's line-separated URL output"""
        urls = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if line and (line.startswith("http://") or line.startswith("https://")):
                urls.append(line)
        return list(dict.fromkeys(urls))  # Deduplicate preserving order

    def _generate_summary(self, target: str, urls: List[str]) -> str:
        summary = f"Katana Web Crawl Results for {target}\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Total URLs Discovered: {len(urls)}\n"
        summary += f"  API/Endpoint Paths: {len([u for u in urls if any(p in u for p in ['api', 'graphql', 'v1', 'v2', 'rest'])])}\n"
        summary += f"  JavaScript Files:   {len([u for u in urls if u.endswith('.js')])}\n"
        summary += f"  URLs with Params:   {len([u for u in urls if '?' in u])}\n\n"

        if urls:
            summary += "Sample Discovered URLs (first 20):\n"
            for u in urls[:20]:
                summary += f"  - {u}\n"
            if len(urls) > 20:
                summary += f"  ... and {len(urls) - 20} more\n"
        else:
            summary += "No URLs discovered.\n"

        return summary


class FfufArgs(BaseModel):
    url: str = Field(..., description="Target URL with FUZZ keyword as placeholder (e.g., https://example.com/FUZZ)")
    wordlist: str = Field(
        "/usr/share/seclists/Discovery/Web-Content/common.txt",
        description="Path to wordlist file inside the Docker container"
    )
    extensions: Optional[str] = Field(None, description="File extensions to append to each word (e.g., 'php,html,asp')")
    filter_status: Optional[str] = Field("404", description="HTTP status codes to filter OUT of results (comma-separated, e.g., '404,403')")
    threads: int = Field(40, description="Number of concurrent threads")
    timeout: int = Field(10, description="Request timeout in seconds")
    method: str = Field("GET", description="HTTP method (GET, POST, etc.)")
    headers: Optional[str] = Field(None, description="Additional HTTP headers (e.g., 'Authorization: Bearer token')")
    cookies: Optional[str] = Field(None, description="Cookie string to include with requests")


class FfufTool(KodiakTool):
    name = "ffuf"
    description = "Fast web fuzzer for discovering hidden directories, files, virtual hosts, and parameters. Use the FUZZ keyword in the URL to specify the injection point."
    args_schema = FfufArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL with FUZZ placeholder (e.g., https://example.com/FUZZ or https://example.com/api/FUZZ.php)"
                },
                "wordlist": {
                    "type": "string",
                    "description": "Wordlist file path (default: /usr/share/seclists/Discovery/Web-Content/common.txt). Other options: /usr/share/seclists/Discovery/Web-Content/big.txt"
                },
                "extensions": {
                    "type": "string",
                    "description": "Comma-separated file extensions to try (e.g., 'php,html,txt,bak')"
                },
                "filter_status": {
                    "type": "string",
                    "description": "HTTP status codes to HIDE from results (e.g., '404' or '404,403,400')"
                },
                "threads": {
                    "type": "integer",
                    "description": "Number of concurrent threads (default: 40)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds (default: 10)"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method to use (default: GET)"
                },
                "headers": {
                    "type": "string",
                    "description": "Additional HTTP headers to include"
                },
                "cookies": {
                    "type": "string",
                    "description": "Cookie header value to include with requests"
                }
            },
            "required": ["url"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        url = args["url"]
        # HARDCODED: Default wordlist path inside the Kodiak Docker container (from seclists)
        wordlist = args.get("wordlist", "/usr/share/seclists/Discovery/Web-Content/common.txt")

        command = [
            "ffuf",
            "-u", url,
            "-w", wordlist,
            "-t", str(args.get("threads", 40)),
            "-timeout", str(args.get("timeout", 10)),
            "-X", args.get("method", "GET"),
            "-json",
            "-s",  # Silent mode
        ]

        if args.get("extensions"):
            command.extend(["-e", args["extensions"]])
        if args.get("filter_status"):
            command.extend(["-fc", args["filter_status"]])
        if args.get("headers"):
            command.extend(["-H", args["headers"]])
        if args.get("cookies"):
            command.extend(["-b", args["cookies"]])

        cmd_str = " ".join(command)

        try:
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor

            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="ghcr.io/ffuf/ffuf:latest",
                fallback_entrypoint=""
            )
            result = await executor.run_command(command)

            # ffuf exits non-zero when no results are found; that's not a failure
            results = self._parse_ffuf_output(result.stdout)
            summary = self._generate_ffuf_summary(url, wordlist, results)

            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "target_url": url,
                    "wordlist": wordlist,
                    "results": results,
                    "total_found": len(results),
                    "interesting": [r for r in results if r.get("status") in [200, 201, 301, 302, 403]],
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=f"FFUF execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_ffuf_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse ffuf's JSONL output (one JSON object per line)"""
        results = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # ffuf JSON output has a top-level 'results' array when using -json flag
                if "results" in data:
                    for r in data["results"]:
                        results.append({
                            "url": r.get("url", ""),
                            "status": r.get("status", 0),
                            "length": r.get("length", 0),
                            "words": r.get("words", 0),
                            "lines": r.get("lines", 0),
                            "input": r.get("input", {}).get("FUZZ", ""),
                        })
                elif "url" in data:
                    results.append({
                        "url": data.get("url", ""),
                        "status": data.get("status", 0),
                        "length": data.get("length", 0),
                        "words": data.get("words", 0),
                        "lines": data.get("lines", 0),
                        "input": data.get("input", {}).get("FUZZ", ""),
                    })
            except json.JSONDecodeError:
                continue
        return results

    def _generate_ffuf_summary(self, url: str, wordlist: str, results: List[Dict[str, Any]]) -> str:
        summary = f"FFUF Directory/File Fuzzing Results\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Target:   {url}\n"
        summary += f"Wordlist: {wordlist}\n"
        summary += f"Found:    {len(results)} result(s)\n\n"

        if results:
            summary += "Discovered Paths:\n"
            for r in results[:30]:
                status = r.get("status", "?")
                path = r.get("input", r.get("url", "?"))
                length = r.get("length", 0)
                summary += f"  [{status}] /{path:<35} (size: {length})\n"
            if len(results) > 30:
                summary += f"  ... and {len(results) - 30} more\n"
        else:
            summary += "No results found.\n"

        return summary


class WhatWebArgs(BaseModel):
    url: str = Field(..., description="Target URL or comma-separated list of URLs")
    aggression: int = Field(1, description="Aggression level (1=stealthy, 3=aggressive, 4=heavy)")


class WhatWebTool(KodiakTool):
    name = "whatweb"
    description = "Web technology fingerprinting tool. Identifies web frameworks, CMS platforms, server software, JavaScript libraries, and other technologies used by a target."
    args_schema = WhatWebArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL(s) to fingerprint (e.g., 'https://example.com' or comma-separated)"
                },
                "aggression": {
                    "type": "integer",
                    "description": "Aggression level: 1=stealthy (quiet, one request), 3=aggressive (more requests), 4=heavy"
                }
            },
            "required": ["url"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        url = args["url"]
        aggression = args.get("aggression", 1)

        targets = [t.strip() for t in url.split(",") if t.strip()]
        command = [
            "whatweb",
            f"--aggression={aggression}",
            "--log-json=-",  # Output JSON to stdout
            "--no-errors",
        ] + targets

        cmd_str = " ".join(command)

        try:
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor

            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="kalilinux/kali-rolling",
                fallback_entrypoint=""
            )
            result = await executor.run_command(command)

            parsed = self._parse_whatweb_output(result.stdout)
            summary = self._generate_whatweb_summary(url, parsed)

            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "target": url,
                    "results": parsed,
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                output=f"WhatWeb execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_whatweb_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse WhatWeb JSON log output"""
        results = []
        for line in output.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, list):
                    for entry in data:
                        results.append(self._normalise_entry(entry))
                elif isinstance(data, dict):
                    results.append(self._normalise_entry(data))
            except json.JSONDecodeError:
                continue
        return results

    def _normalise_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Flatten a WhatWeb result entry into a simpler structure"""
        plugins = entry.get("plugins", {})
        technologies = []
        for name, details in plugins.items():
            tech = {"name": name}
            if details.get("version"):
                tech["version"] = details["version"][0] if isinstance(details["version"], list) else details["version"]
            if details.get("string"):
                tech["string"] = details["string"][0] if isinstance(details["string"], list) else details["string"]
            technologies.append(tech)
        return {
            "target": entry.get("target", ""),
            "http_status": entry.get("http_status", 0),
            "technologies": technologies,
            "technology_names": [t["name"] for t in technologies],
        }

    def _generate_whatweb_summary(self, url: str, results: List[Dict[str, Any]]) -> str:
        summary = f"WhatWeb Technology Fingerprint for {url}\n"
        summary += "=" * 50 + "\n\n"

        if not results:
            summary += "No results returned.\n"
            return summary

        for entry in results:
            summary += f"Target: {entry.get('target', url)}  [HTTP {entry.get('http_status', '?')}]\n"
            techs = entry.get("technologies", [])
            if techs:
                summary += "Detected Technologies:\n"
                for t in techs:
                    line = f"  - {t['name']}"
                    if t.get("version"):
                        line += f" {t['version']}"
                    if t.get("string"):
                        line += f" [{t['string'][:60]}]"
                    summary += line + "\n"
            else:
                summary += "  No technologies identified.\n"
            summary += "\n"

        return summary

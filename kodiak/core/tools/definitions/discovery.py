import json
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
        domain = args["domain"]
        
        # Build subfinder command
        command = [
            "subfinder",
            "-d", domain,
            "-json",
            "-silent",
            "-timeout", str(args.get("timeout", 30))
        ]
        
        if args.get("sources"):
            command.extend(["-sources", args["sources"]])
        
        if args.get("recursive"):
            command.append("-recursive")
        
        cmd_str = " ".join(command)

        try:
            # Docker is the PRIMARY execution path for security tools
            from kodiak.core.config import settings
            
            try:
                executor = get_executor("docker")
                executor.image = settings.toolbox_image
            except Exception:
                # Fallback: Local execution only if Docker unavailable
                # HARDCODED: This should rarely be used in production
                executor = get_executor()
            
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
            summary = self._generate_subfinder_summary(domain, subdomains)
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "domain": domain,
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
            
            try:
                executor = get_executor("docker")
                executor.image = settings.toolbox_image
            except Exception:
                # Fallback: Local execution only if Docker unavailable
                # HARDCODED: This should rarely be used in production
                executor = get_executor()
            
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

import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor


class NucleiArgs(BaseModel):
    target: str = Field(..., description="Target URL or hostname")
    tags: Optional[str] = Field(None, description="Comma-separated tags to filter templates (e.g., cve,exposed-panels,sqli)")
    severity: Optional[str] = Field(None, description="Severity levels to scan for (e.g., critical,high,medium,low)")
    templates: Optional[str] = Field(None, description="Specific template path or directory")
    rate_limit: int = Field(150, description="Rate limit for requests per second")
    timeout: int = Field(10, description="Timeout for HTTP requests in seconds")
    retries: int = Field(1, description="Number of retries for failed requests")


class NucleiTool(KodiakTool):
    name = "nuclei"
    description = "Fast and customizable vulnerability scanner based on simple YAML templates. Detects CVEs, misconfigurations, and security issues."
    args_schema = NucleiArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target URL or hostname (e.g., https://example.com, example.com)"
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated template tags (cve,exposed-panels,sqli,xss,rce,lfi,ssrf,config-audit)"
                },
                "severity": {
                    "type": "string",
                    "description": "Severity filter: critical,high,medium,low,info"
                },
                "templates": {
                    "type": "string",
                    "description": "Specific template file or directory path"
                },
                "rate_limit": {
                    "type": "integer",
                    "description": "Requests per second (default: 150)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "HTTP request timeout in seconds (default: 10)"
                },
                "retries": {
                    "type": "integer",
                    "description": "Number of retries for failed requests (default: 1)"
                }
            },
            "required": ["target"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        target = args["target"]
        
        # Ensure target has protocol
        if not target.startswith(('http://', 'https://')):
            target = f"https://{target}"
        
        # Build nuclei command
        command = [
            "nuclei",
            "-target", target,
            "-json",  # JSON output for parsing
            "-nc",    # No color
            "-silent", # Reduce noise
            "-rate-limit", str(args.get("rate_limit", 150)),
            "-timeout", str(args.get("timeout", 10)),
            "-retries", str(args.get("retries", 1))
        ]
        
        # Add filters
        if args.get("tags"):
            command.extend(["-tags", args["tags"]])
        if args.get("severity"):
            command.extend(["-severity", args["severity"]])
        if args.get("templates"):
            command.extend(["-templates", args["templates"]])
        
        cmd_str = " ".join(command)

        try:
            executor = get_executor()
            result = await executor.run_command(command)
            
            # Nuclei returns 0 even when vulnerabilities are found
            # Only consider it an error if there's a genuine failure
            if result.exit_code != 0 and "No results found" not in result.stderr:
                return ToolResult(
                    success=False,
                    output=f"Nuclei scan failed: {result.stderr}",
                    error=f"Command failed with exit code {result.exit_code}"
                )
            
            # Parse JSON output
            findings = self._parse_nuclei_output(result.stdout)
            
            # Generate summary
            summary = self._generate_summary(target, findings)
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "command": cmd_str,
                    "target": target,
                    "findings": findings,
                    "total_findings": len(findings),
                    "severity_breakdown": self._get_severity_breakdown(findings),
                    "template_matches": [f.get("template-id", "unknown") for f in findings]
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Nuclei execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_nuclei_output(self, output: str) -> List[Dict[str, Any]]:
        """Parse nuclei JSON output into structured findings"""
        findings = []
        
        if not output.strip():
            return findings
        
        # Nuclei outputs one JSON object per line
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    finding = json.loads(line)
                    # Enhance finding with additional metadata
                    enhanced_finding = self._enhance_finding(finding)
                    findings.append(enhanced_finding)
                except json.JSONDecodeError:
                    # Skip non-JSON lines
                    continue
        
        return findings

    def _enhance_finding(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance nuclei finding with additional metadata"""
        info = finding.get("info", {})
        
        enhanced = {
            "template_id": finding.get("template-id", "unknown"),
            "template_path": finding.get("template-path", ""),
            "name": info.get("name", "Unknown Vulnerability"),
            "severity": info.get("severity", "info").upper(),
            "description": info.get("description", ""),
            "reference": info.get("reference", []),
            "tags": info.get("tags", []),
            "classification": info.get("classification", {}),
            "matched_at": finding.get("matched-at", ""),
            "extracted_results": finding.get("extracted-results", []),
            "curl_command": finding.get("curl-command", ""),
            "matcher_status": finding.get("matcher-status", False),
            "timestamp": finding.get("timestamp", ""),
            "raw_finding": finding
        }
        
        # Extract CVE information if available
        if "cve" in enhanced["tags"]:
            cve_match = re.search(r'CVE-\d{4}-\d{4,}', enhanced["name"] + " " + enhanced["description"])
            if cve_match:
                enhanced["cve_id"] = cve_match.group(0)
        
        # Assess risk level
        enhanced["risk_level"] = self._assess_risk_level(enhanced)
        
        return enhanced

    def _assess_risk_level(self, finding: Dict[str, Any]) -> str:
        """Assess the risk level of a finding"""
        severity = finding.get("severity", "INFO").lower()
        tags = [tag.lower() for tag in finding.get("tags", [])]
        
        # High-risk indicators
        high_risk_tags = ["rce", "sqli", "lfi", "rfi", "xxe", "ssti", "deserialization"]
        medium_risk_tags = ["xss", "ssrf", "redirect", "disclosure", "bypass"]
        
        if severity == "critical" or any(tag in high_risk_tags for tag in tags):
            return "HIGH"
        elif severity == "high" or any(tag in medium_risk_tags for tag in tags):
            return "MEDIUM"
        elif severity in ["medium", "low"]:
            return "LOW"
        else:
            return "INFO"

    def _get_severity_breakdown(self, findings: List[Dict[str, Any]]) -> Dict[str, int]:
        """Get breakdown of findings by severity"""
        breakdown = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
        
        for finding in findings:
            severity = finding.get("severity", "INFO").upper()
            if severity in breakdown:
                breakdown[severity] += 1
        
        return breakdown

    def _generate_summary(self, target: str, findings: List[Dict[str, Any]]) -> str:
        """Generate human-readable summary of scan results"""
        if not findings:
            return f"Nuclei scan completed for {target}. No vulnerabilities found."
        
        severity_breakdown = self._get_severity_breakdown(findings)
        
        summary = f"Nuclei Vulnerability Scan Results for {target}\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Total Findings: {len(findings)}\n\n"
        
        # Severity breakdown
        summary += "Severity Breakdown:\n"
        for severity, count in severity_breakdown.items():
            if count > 0:
                summary += f"  {severity}: {count}\n"
        summary += "\n"
        
        # Top findings
        summary += "Key Findings:\n"
        for i, finding in enumerate(findings[:10], 1):  # Show top 10
            name = finding.get("name", "Unknown")
            severity = finding.get("severity", "INFO")
            matched_at = finding.get("matched_at", "")
            
            summary += f"{i:2d}. [{severity}] {name}\n"
            if matched_at:
                summary += f"     URL: {matched_at}\n"
            summary += "\n"
        
        if len(findings) > 10:
            summary += f"... and {len(findings) - 10} more findings\n"
        
        return summary

from typing import Dict, Any, List
import asyncio
import json
import os
from kodiak.core.tools.base import KodiakTool

class NucleiTool(KodiakTool):
    """
    Wrapper for Nuclei Vulnerability Scanner.
    """
    @property
    def name(self) -> str:
        return "nuclei_scan"

    @property
    def description(self) -> str:
        return "Scans a target (URL or Host) for vulnerabilities using Nuclei templates."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Target URL or Hostname (e.g., http://example.com)"},
                "tags": {"type": "string", "description": "Comma-separated tags to filter templates (e.g., cve,exposed-panels)"},
                "severity": {"type": "string", "description": "Severity levels (e.g., critical,high,medium)"}
            },
            "required": ["target"]
        }

    async def _execute(self, args: Dict[str, Any]) -> Any:
        target = args["target"]
        tags = args.get("tags")
        severity = args.get("severity")
        
        # Build command
        # -json for machine readable output
        # -nc (no color)
        cmd = ["nuclei", "-target", target, "-json", "-nc"]
        
        if tags:
            cmd.extend(["-tags", tags])
        if severity:
            cmd.extend(["-severity", severity])
            
        # Run command
        # In a real implementation, we might stream this output back to the websocket
        # For now, we capture it all.
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return f"Nuclei scan failed: {stderr.decode()}"
            
        # Parse JSON output (multiline json objects)
        findings = []
        raw_output = stdout.decode()
        for line in raw_output.splitlines():
            if line.strip():
                try:
                    findings.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        
        # Summarize findings
        summary = f"Nuclei Scan Completed for {target}.\n"
        if not findings:
            summary += "No vulnerabilities found."
        else:
            summary += f"Found {len(findings)} issues:\n"
            for finding in findings:
                name = finding.get('info', {}).get('name', 'Unknown')
                severity = finding.get('info', {}).get('severity', 'info')
                summary += f"- [{severity.upper()}] {name}\n"
                
        return {
            "summary": summary,
            "findings": findings
        }

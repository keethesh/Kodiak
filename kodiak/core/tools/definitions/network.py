import re
import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor


class NmapArgs(BaseModel):
    target: str = Field(..., description="Target IP or Domain")
    ports: Optional[str] = Field(None, description="Port range (e.g., '80,443', '1-1000')")
    fast_mode: bool = Field(False, description="Use -F for fast scan")
    script_scan: bool = Field(False, description="Use -sC for script scan")
    version_detect: bool = Field(True, description="Use -sV for version detection")
    stealth_scan: bool = Field(False, description="Use -sS for stealth SYN scan")
    udp_scan: bool = Field(False, description="Use -sU for UDP scan")
    os_detection: bool = Field(False, description="Use -O for OS detection")
    aggressive: bool = Field(False, description="Use -A for aggressive scan")


class NmapTool(KodiakTool):
    name = "nmap"
    description = "Network discovery and security auditing tool. Scans for open ports, services, and vulnerabilities."
    args_schema = NmapArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Target IP address, hostname, or CIDR range"
                },
                "ports": {
                    "type": "string",
                    "description": "Port specification (e.g., '80,443', '1-1000', 'top-ports 100')"
                },
                "fast_mode": {
                    "type": "boolean",
                    "description": "Fast scan mode - scans fewer ports"
                },
                "script_scan": {
                    "type": "boolean", 
                    "description": "Enable default NSE scripts for vulnerability detection"
                },
                "version_detect": {
                    "type": "boolean",
                    "description": "Probe open ports to determine service/version info"
                },
                "stealth_scan": {
                    "type": "boolean",
                    "description": "Stealth SYN scan (requires root privileges)"
                },
                "udp_scan": {
                    "type": "boolean",
                    "description": "UDP port scan (slower but finds UDP services)"
                },
                "os_detection": {
                    "type": "boolean",
                    "description": "Enable OS detection (requires root privileges)"
                },
                "aggressive": {
                    "type": "boolean",
                    "description": "Aggressive scan - enables OS detection, version detection, script scanning, and traceroute"
                }
            },
            "required": ["target"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        # Construct nmap command
        command = ["nmap", "-oN", "-"]  # Normal output to stdout
        
        # Scan type options
        if args.get("stealth_scan"):
            command.append("-sS")
        if args.get("udp_scan"):
            command.append("-sU")
            
        # Port specification
        if args.get("fast_mode") and not args.get("ports"):
            command.append("-F")
        elif args.get("ports"):
            command.extend(["-p", args["ports"]])
            
        # Detection options
        if args.get("aggressive"):
            command.append("-A")
        else:
            if args.get("version_detect"):
                command.append("-sV")
            if args.get("script_scan"):
                command.append("-sC")
            if args.get("os_detection"):
                command.append("-O")
        
        # Add target
        command.append(args["target"])
        
        cmd_str = " ".join(command)

        try:
            # Docker is the PRIMARY execution path for security tools
            # This ensures tools run in the Kali container without local installation
            from kodiak.core.config import settings
            
            try:
                # Primary: Use Docker executor with Kali toolbox
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
                    output=f"Nmap scan failed: {result.stderr}",
                    error=f"Command failed with exit code {result.exit_code}"
                )
            
            # Parse nmap output
            parsed_data = self._parse_nmap_output(result.stdout)
            
            return ToolResult(
                success=True,
                output=result.stdout,
                data={
                    "command": cmd_str,
                    "target": args["target"],
                    "parsed": parsed_data,
                    "open_ports": parsed_data.get("open_ports", []),
                    "services": parsed_data.get("services", {}),
                    "os_info": parsed_data.get("os_info", {}),
                    "vulnerabilities": parsed_data.get("vulnerabilities", [])
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Nmap execution failed: {str(e)}",
                error=str(e)
            )

    def _parse_nmap_output(self, output: str) -> Dict[str, Any]:
        """Parse nmap output and extract structured data"""
        parsed = {
            "open_ports": [],
            "services": {},
            "os_info": {},
            "vulnerabilities": [],
            "host_info": {}
        }
        
        lines = output.split('\n')
        
        # Extract host information
        for line in lines:
            if "Nmap scan report for" in line:
                host_match = re.search(r'Nmap scan report for (.+)', line)
                if host_match:
                    parsed["host_info"]["target"] = host_match.group(1)
            
            elif "Host is up" in line:
                latency_match = re.search(r'latency: ([\d.]+)s', line)
                if latency_match:
                    parsed["host_info"]["latency"] = float(latency_match.group(1))
        
        # Extract open ports and services
        port_section = False
        for line in lines:
            if "PORT" in line and "STATE" in line and "SERVICE" in line:
                port_section = True
                continue
            elif port_section and line.strip() == "":
                port_section = False
                continue
                
            if port_section and line.strip():
                # Parse port line: 80/tcp open http nginx 1.18.0
                port_match = re.match(r'(\d+)/(tcp|udp)\s+(\w+)\s+(\S+)(?:\s+(.+))?', line.strip())
                if port_match:
                    port_num = int(port_match.group(1))
                    protocol = port_match.group(2)
                    state = port_match.group(3)
                    service = port_match.group(4)
                    version = port_match.group(5) if port_match.group(5) else ""
                    
                    if state == "open":
                        port_info = {
                            "port": port_num,
                            "protocol": protocol,
                            "state": state,
                            "service": service,
                            "version": version.strip() if version else ""
                        }
                        parsed["open_ports"].append(port_info)
                        parsed["services"][f"{port_num}/{protocol}"] = {
                            "service": service,
                            "version": version.strip() if version else ""
                        }
        
        # Extract OS information
        os_section = False
        for line in lines:
            if "OS details:" in line:
                os_info = line.replace("OS details:", "").strip()
                parsed["os_info"]["details"] = os_info
            elif "Aggressive OS guesses:" in line:
                os_section = True
                continue
            elif os_section and line.strip().startswith("No exact OS matches"):
                os_section = False
                continue
            elif os_section and line.strip():
                if "%" in line:
                    os_guess = line.strip()
                    if "os_guesses" not in parsed["os_info"]:
                        parsed["os_info"]["os_guesses"] = []
                    parsed["os_info"]["os_guesses"].append(os_guess)
        
        # Extract script results (potential vulnerabilities)
        script_section = False
        current_script = None
        for line in lines:
            if line.startswith("|"):
                script_section = True
                if line.startswith("|_"):
                    # Script result
                    script_result = line[2:].strip()
                    if current_script:
                        parsed["vulnerabilities"].append({
                            "script": current_script,
                            "result": script_result,
                            "severity": self._assess_vulnerability_severity(script_result)
                        })
                elif line.startswith("| "):
                    # Script name
                    current_script = line[2:].strip().rstrip(":")
            else:
                script_section = False
                current_script = None
        
        return parsed

    def _assess_vulnerability_severity(self, script_result: str) -> str:
        """Assess vulnerability severity based on script output"""
        result_lower = script_result.lower()
        
        if any(keyword in result_lower for keyword in ["critical", "exploit", "backdoor", "shell"]):
            return "critical"
        elif any(keyword in result_lower for keyword in ["high", "dangerous", "vulnerable", "weak"]):
            return "high"
        elif any(keyword in result_lower for keyword in ["medium", "warning", "insecure"]):
            return "medium"
        elif any(keyword in result_lower for keyword in ["low", "info", "disclosure"]):
            return "low"
        else:
            return "info"

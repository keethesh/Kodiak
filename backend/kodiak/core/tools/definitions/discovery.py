from typing import Dict, Any, List
import asyncio
import json
from kodiak.core.tools.base import KodiakTool

class SubfinderTool(KodiakTool):
    """
    Wrapper for ProjectDiscovery's Subfinder.
    Finds valid subdomains for websites.
    """
    @property
    def name(self) -> str:
        return "subfinder_enumerate"

    @property
    def description(self) -> str:
        return "Passive subdomain enumeration tool. Use this to find subdomains of a target domain."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Target domain (e.g., example.com)"}
            },
            "required": ["domain"]
        }

    async def _execute(self, args: Dict[str, Any]) -> Any:
        domain = args["domain"]
        
        # -d domain -json -silent
        cmd = ["subfinder", "-d", domain, "-json", "-silent"]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return f"Subfinder failed: {stderr.decode()}"
            
        # Parse JSON output (multiline json objects)
        subdomains = []
        raw_output = stdout.decode()
        for line in raw_output.splitlines():
            if line.strip():
                try:
                    data = json.loads(line)
                    subdomains.append(data.get('host'))
                except json.JSONDecodeError:
                    pass
        
        return {
            "domain": domain,
            "subdomains_found": len(subdomains),
            "subdomains": subdomains
        }

class HttpxTool(KodiakTool):
    """
    Wrapper for ProjectDiscovery's Httpx.
    Probes for running HTTP services on a list of hosts/domains.
    """
    @property
    def name(self) -> str:
        return "httpx_probe"

    @property
    def description(self) -> str:
        return "HTTP probing tool. Use this to check which subdomains/hosts have active web servers."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Single target or comma-separated list of targets"}
            },
            "required": ["target"]
        }

    async def _execute(self, args: Dict[str, Any]) -> Any:
        target = args["target"]
        
        # We can pass targets via stdin or command line. 
        # For simplicity, if it's a single target, we use -u.
        # If comma separated, we might need a different approach, but let's assume single or small list for now.
        
        cmd = ["httpx", "-u", target, "-json", "-silent", "-sc", "-title"]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            return f"Httpx failed: {stderr.decode()}"
            
        results = []
        raw_output = stdout.decode()
        for line in raw_output.splitlines():
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
                    
        return {
            "scan_target": target,
            "live_hosts": len(results),
            "details": results
        }

from typing import List, Optional
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor
from kodiak.core.hive_mind import hive_mind


class NmapArgs(BaseModel):
    target: str = Field(..., description="Target IP or Domain")
    ports: Optional[str] = Field(None, description="Port range (e.g., '80,443', '1-1000')")
    fast_mode: bool = Field(False, description="Use -F for fast scan")
    script_scan: bool = Field(False, description="Use -sC for script scan")
    version_detect: bool = Field(True, description="Use -sV for version detection")


class NmapTool(KodiakTool):
    name = "nmap"
    description = "Run Nmap network scan"
    args_schema = NmapArgs

    async def _execute(self, args: Dict[str, Any]) -> Any:
        # Construct command
        command = ["nmap"]
        if args.get("fast_mode") and not args.get("ports"):
            command.append("-F")
        if args.get("ports"):
            command.extend(["-p", args["ports"]])
        if args.get("version_detect"):
            command.append("-sV")
        if args.get("script_scan"):
            command.append("-sC")
        
        command.append(args["target"])
        
        cmd_str = " ".join(command)

        cmd_str = " ".join(command)

        # Execute
        try:
            executor = get_executor() 
            result = await executor.run_command(command)
            
            output = result.stdout
            if result.exit_code != 0:
                output += f"\nSTDERR: {result.stderr}"
            
            return {
                "success": result.exit_code == 0,
                "output": output,
                "command": cmd_str
            }
        except Exception as e:
            raise e

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

    async def run(self, args: NmapArgs) -> ToolResult:
        # Construct command
        command = ["nmap"]
        if args.fast_mode and not args.ports:
            command.append("-F")
        if args.ports:
            command.extend(["-p", args.ports])
        if args.version_detect:
            command.append("-sV")
        if args.script_scan:
            command.append("-sC")
        
        command.append(args.target)
        
        cmd_str = " ".join(command)

        # 0. Check Cache First
        cached_output = hive_mind.get_cached_result(cmd_str)
        if cached_output:
            return ToolResult(success=True, output=cached_output, data={"cached": True})
        
        # Hive Mind Synchronization
        # 1. Check if running
        if hive_mind.is_running(cmd_str):
            # 2. If running, wait for result (Follower)
            try:
                output = await hive_mind.wait_for_result(cmd_str)
                return ToolResult(success=True, output=output, data={"cached": True})
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")

        # 3. If not running, acquire lock (Leader)
        # Note: In a race condition, acquire might return False, handled by re-check logic usually, 
        # but for simplicity we rely on is_running + acquire pattern or just acquire.
        # Let's use acquire's return to be safe.
        
        is_leader = await hive_mind.acquire(cmd_str, "agent_placeholder_id") # TODO: Pass actual agent ID
        if not is_leader:
             # Lost the race, wait for result
            try:
                output = await hive_mind.wait_for_result(cmd_str)
                return ToolResult(success=True, output=output, data={"cached": True})
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")

        # I am the Leader
        try:
            executor = get_executor() # Defaults to local for now
            result = await executor.run_command(command)
            
            output = result.stdout
            if result.exit_code != 0:
                output += f"\nSTDERR: {result.stderr}"
            
            # Notify followers
            await hive_mind.release(cmd_str, output)
            
            return ToolResult(
                success=result.exit_code == 0, 
                output=output, 
                error=result.stderr if result.exit_code != 0 else None
            )
        except Exception as e:
            await hive_mind.release(cmd_str, f"Error: {str(e)}")
            return ToolResult(success=False, output="", error=str(e))

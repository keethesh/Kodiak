from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor
from kodiak.core.hive_mind import hive_mind

class PingArgs(BaseModel):
    hostname: str = Field(..., description="Hostname to ping")
    count: int = Field(4, description="Number of packets")

class PingTool(KodiakTool):
    name = "ping"
    description = "Send ICMP Echo Request"
    args_schema = PingArgs

    async def run(self, args: PingArgs) -> ToolResult:
        # Windows-specific ping command
        command = ["ping", "-n", str(args.count), args.hostname]
        cmd_str = " ".join(command)
        
        # Hive Mind Synchronization
        if hive_mind.is_running(cmd_str):
            try:
                output = await hive_mind.wait_for_result(cmd_str)
                return ToolResult(success=True, output=output, data={"cached": True})
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error waiting: {str(e)}")

        is_leader = await hive_mind.acquire(cmd_str, "agent_placeholder_id")
        if not is_leader:
            try:
                output = await hive_mind.wait_for_result(cmd_str)
                return ToolResult(success=True, output=output, data={"cached": True})
            except Exception as e:
                return ToolResult(success=False, output="", error=f"Error waiting: {str(e)}")

        try:
            # REAL Executor (Local)
            executor = get_executor("local") 
            result = await executor.run_command(command)
            
            output = result.stdout
            if result.exit_code != 0:
                output += f"\nSTDERR: {result.stderr}"
            
            await hive_mind.release(cmd_str, output)
            
            return ToolResult(
                success=result.exit_code == 0, 
                output=output, 
                error=result.stderr if result.exit_code != 0 else None
            )
        except Exception as e:
            await hive_mind.release(cmd_str, f"Error: {str(e)}")
            return ToolResult(success=False, output="", error=str(e))

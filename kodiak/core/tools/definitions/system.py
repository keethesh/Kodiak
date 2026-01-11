from typing import Dict, Any
import asyncio
from pydantic import BaseModel, Field
from kodiak.core.tools.base import KodiakTool, ToolResult


class TerminalArgs(BaseModel):
    command: str = Field(..., description="Shell command to execute")
    timeout: int = Field(60, description="Timeout in seconds")


class TerminalTool(KodiakTool):
    """
    Execute arbitrary shell commands.
    This provides the 'Hybrid' capability: giving the LLM raw access when structured tools aren't enough.
    """
    name = "terminal_execute"
    description = "Executes a shell command on the system. Use this for tools that don't have dedicated wrappers or for file system exploration."
    args_schema = TerminalArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string", 
                    "description": "The command line to execute (e.g., 'ls -la', 'cat /etc/passwd')"
                },
                "timeout": {
                    "type": "integer", 
                    "description": "Timeout in seconds (default: 60)"
                }
            },
            "required": ["command"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        command = args["command"]
        timeout = args.get("timeout", 60)
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
                output = stdout.decode() + stderr.decode()
                
                success = process.returncode == 0
                
                summary = f"Terminal Command Execution\n"
                summary += "=" * 30 + "\n\n"
                summary += f"Command: {command}\n"
                summary += f"Exit Code: {process.returncode}\n"
                summary += f"Success: {'✓' if success else '✗'}\n\n"
                
                if output:
                    output_preview = output[:1000]
                    if len(output) > 1000:
                        output_preview += "\n... (truncated)"
                    summary += f"Output:\n{output_preview}\n"
                else:
                    summary += "No output produced.\n"
                
                return ToolResult(
                    success=success,
                    output=summary,
                    data={
                        "command": command,
                        "exit_code": process.returncode,
                        "stdout": stdout.decode(),
                        "stderr": stderr.decode(),
                        "full_output": output
                    },
                    error=stderr.decode() if not success and stderr else None
                )
                
            except asyncio.TimeoutError:
                process.kill()
                return ToolResult(
                    success=False,
                    output=f"Command timed out after {timeout} seconds",
                    error=f"Command timed out after {timeout} seconds"
                )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Command execution failed: {str(e)}",
                error=str(e)
            )

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
    name = "system_execute"
    description = "Executes a simple shell command locally on the host system. Use this for basic file system exploration. For advanced multi-step commands or docker container isolation, use terminal_start."
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
            from kodiak.core.config import settings
            from kodiak.services.executor import get_docker_executor

            executor = await get_docker_executor(
                settings.toolbox_image,
                fallback_image="kalilinux/kali-rolling:latest",
                fallback_entrypoint=""
            )
            
            # Run the command through bash inside the container
            docker_cmd = ["/bin/bash", "-c", command]
            
            # executor.run_command inherently respects some timeouts but let's pass it if supported, 
            # otherwise we just rely on its internal execution
            result = await executor.run_command(docker_cmd)
            
            success = result.exit_code == 0
            
            summary = f"Terminal Command Execution (Sandbox)\n"
            summary += "=" * 30 + "\n\n"
            summary += f"Command: {command}\n"
            summary += f"Exit Code: {result.exit_code}\n"
            summary += f"Success: {'✓' if success else '✗'}\n\n"
            
            output = result.stdout + result.stderr

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
                    "exit_code": result.exit_code,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "full_output": output
                },
                error=result.stderr if not success and result.stderr else None
            )
                
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Command execution failed: {str(e)}",
                error=str(e)
            )

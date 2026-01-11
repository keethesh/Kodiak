from typing import Dict, Any
import asyncio
from kodiak.core.tools.base import KodiakTool

class TerminalTool(KodiakTool):
    """
    Execute arbitrary shell commands.
    This provides the 'Hybrid' capability: giving the LLM raw access when structured tools aren't enough.
    """
    @property
    def name(self) -> str:
        return "terminal_execute"

    @property
    def description(self) -> str:
        return "Executes a shell command on the system. Use this for tools that don't have dedicated wrappers or for file system exploration."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command line to execute (e.g., 'ls -la', 'cat /etc/passwd')"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 60}
            },
            "required": ["command"]
        }

    async def _execute(self, args: Dict[str, Any]) -> Any:
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
                return {
                    "command": command,
                    "exit_code": process.returncode,
                    "output": output
                }
            except asyncio.TimeoutError:
                process.kill()
                return {"error": f"Command timed out after {timeout} seconds"}
                
        except Exception as e:
            return {"error": str(e)}

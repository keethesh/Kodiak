"""
Terminal Environment Tools for Kodiak

Provides interactive shell environments for command execution, exploit development,
and custom security testing workflows.
"""

import asyncio
import json
import time
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor


class TerminalSession:
    """Manages persistent terminal session state"""
    
    def __init__(self, session_id: str, shell_type: str = "bash"):
        self.session_id = session_id
        self.shell_type = shell_type
        self.history: List[Dict[str, Any]] = []
        self.environment: Dict[str, str] = {}
        self.working_directory = "/tmp"
        self.created_at = time.time()
        self.last_activity = time.time()
        self.is_active = True
    
    def add_command(self, command: str, output: str, exit_code: int):
        """Add command execution to session history"""
        self.history.append({
            "command": command,
            "output": output,
            "exit_code": exit_code,
            "timestamp": time.time(),
            "working_directory": self.working_directory
        })
        self.last_activity = time.time()
    
    def set_environment(self, env_vars: Dict[str, str]):
        """Update environment variables"""
        self.environment.update(env_vars)
        self.last_activity = time.time()
    
    def change_directory(self, new_dir: str):
        """Change working directory"""
        self.working_directory = new_dir
        self.last_activity = time.time()


# Global terminal sessions
_terminal_sessions: Dict[str, TerminalSession] = {}


class TerminalStartArgs(BaseModel):
    shell_type: str = Field("bash", description="Shell type (bash, sh, zsh, python)")
    environment: Optional[Dict[str, str]] = Field(None, description="Environment variables")
    working_directory: str = Field("/tmp", description="Initial working directory")
    docker_image: Optional[str] = Field(None, description="Docker image for sandboxed execution")


class TerminalExecuteArgs(BaseModel):
    session_id: str = Field(..., description="Terminal session ID")
    command: str = Field(..., description="Command to execute")
    timeout: int = Field(30, description="Command timeout in seconds")
    capture_output: bool = Field(True, description="Capture command output")


class TerminalStartTool(KodiakTool):
    name = "terminal_start"
    description = "Start a persistent terminal session for interactive command execution and exploit development. Essential for custom security testing workflows."
    args_schema = TerminalStartArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "shell_type": {
                    "type": "string",
                    "description": "Shell type: bash, sh, zsh, python, powershell"
                },
                "environment": {
                    "type": "object",
                    "description": "Environment variables as key-value pairs"
                },
                "working_directory": {
                    "type": "string",
                    "description": "Initial working directory (default: /tmp)"
                },
                "docker_image": {
                    "type": "string",
                    "description": "Docker image for sandboxed execution (e.g., kalilinux/kali-rolling)"
                }
            }
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _terminal_sessions
        
        # Generate unique session ID
        session_id = f"term_{uuid.uuid4().hex[:8]}"
        
        shell_type = args.get("shell_type", "bash")
        environment = args.get("environment", {})
        working_directory = args.get("working_directory", "/tmp")
        docker_image = args.get("docker_image")
        
        # Create terminal session
        session = TerminalSession(session_id, shell_type)
        session.environment.update(environment)
        session.working_directory = working_directory
        
        # Store session
        _terminal_sessions[session_id] = session
        
        # Test initial connection
        try:
            test_command = "pwd" if shell_type != "python" else "import os; print(os.getcwd())"
            
            if docker_image:
                executor = get_executor("docker")
                executor.image = docker_image
            else:
                executor = get_executor("local")
            
            # Test the session
            if shell_type == "python":
                result = await executor.run_command(
                    ["python3", "-c", test_command],
                    cwd=working_directory,
                    env=session.environment
                )
            else:
                result = await executor.run_command(
                    [shell_type, "-c", test_command],
                    cwd=working_directory,
                    env=session.environment
                )
            
            session.add_command(test_command, result.stdout, result.exit_code)
            
            # Send WebSocket update for session start
            from kodiak.services.websocket_manager import manager
            await manager.send_session_update(
                session_type="terminal",
                session_id=session_id,
                status="started",
                data={
                    "shell_type": shell_type,
                    "working_directory": working_directory,
                    "docker_image": docker_image,
                    "test_result": result.stdout.strip()
                }
            )
            
            summary = f"Terminal session started successfully\n"
            summary += f"Session ID: {session_id}\n"
            summary += f"Shell: {shell_type}\n"
            summary += f"Working Directory: {working_directory}\n"
            summary += f"Environment Variables: {len(environment)}\n"
            summary += f"Execution Mode: {'Docker (' + docker_image + ')' if docker_image else 'Local'}\n"
            summary += f"Initial Test: {result.stdout.strip()}\n"
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "session_id": session_id,
                    "shell_type": shell_type,
                    "working_directory": working_directory,
                    "environment": session.environment,
                    "docker_image": docker_image,
                    "test_result": result.stdout.strip()
                }
            )
            
        except Exception as e:
            # Clean up failed session
            if session_id in _terminal_sessions:
                del _terminal_sessions[session_id]
            
            return ToolResult(
                success=False,
                output=f"Failed to start terminal session: {str(e)}",
                error=str(e)
            )


class TerminalExecuteTool(KodiakTool):
    name = "terminal_execute"
    description = "Execute command in persistent terminal session. Maintains state, environment, and working directory across commands. Perfect for multi-step exploits and interactive testing."
    args_schema = TerminalExecuteArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Terminal session ID from terminal_start"
                },
                "command": {
                    "type": "string",
                    "description": "Command to execute (e.g., 'ls -la', 'python exploit.py', 'curl -X POST ...')"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Command timeout in seconds (default: 30)"
                },
                "capture_output": {
                    "type": "boolean",
                    "description": "Whether to capture and return output (default: true)"
                }
            },
            "required": ["session_id", "command"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _terminal_sessions
        
        session_id = args["session_id"]
        command = args["command"]
        timeout = args.get("timeout", 30)
        capture_output = args.get("capture_output", True)
        
        # Get session
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Terminal session {session_id} not found. Start a session first with terminal_start.",
                error="Session not found"
            )
        
        if not session.is_active:
            return ToolResult(
                success=False,
                output=f"Terminal session {session_id} is not active.",
                error="Session inactive"
            )
        
        try:
            # Determine executor
            executor = get_executor("local")  # Default to local, Docker sessions would be handled differently
            
            # Handle special commands
            if command.startswith("cd "):
                # Change directory command
                new_dir = command[3:].strip()
                if not new_dir.startswith("/"):
                    # Relative path
                    new_dir = f"{session.working_directory}/{new_dir}"
                
                # Test if directory exists
                test_result = await executor.run_command(
                    ["test", "-d", new_dir],
                    cwd=session.working_directory,
                    env=session.environment
                )
                
                if test_result.exit_code == 0:
                    session.change_directory(new_dir)
                    output = f"Changed directory to: {new_dir}"
                    session.add_command(command, output, 0)
                    
                    return ToolResult(
                        success=True,
                        output=output,
                        data={
                            "session_id": session_id,
                            "command": command,
                            "working_directory": session.working_directory,
                            "exit_code": 0
                        }
                    )
                else:
                    error_msg = f"Directory not found: {new_dir}"
                    session.add_command(command, error_msg, 1)
                    return ToolResult(
                        success=False,
                        output=error_msg,
                        error="Directory not found"
                    )
            
            elif command.startswith("export ") or "=" in command and not command.startswith(("echo", "printf")):
                # Environment variable setting
                if command.startswith("export "):
                    env_part = command[7:]
                else:
                    env_part = command
                
                if "=" in env_part:
                    key, value = env_part.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    
                    session.set_environment({key: value})
                    output = f"Set environment variable: {key}={value}"
                    session.add_command(command, output, 0)
                    
                    return ToolResult(
                        success=True,
                        output=output,
                        data={
                            "session_id": session_id,
                            "command": command,
                            "environment_updated": {key: value},
                            "exit_code": 0
                        }
                    )
            
            # Execute regular command
            if session.shell_type == "python" and not command.startswith(("python", "python3")):
                # Python session - execute as Python code
                full_command = ["python3", "-c", command]
            else:
                # Shell command
                full_command = [session.shell_type, "-c", command]
            
            result = await executor.run_command(
                full_command,
                cwd=session.working_directory,
                env=session.environment
            )
            
            # Store in session history
            session.add_command(command, result.stdout + result.stderr, result.exit_code)
            
            # Analyze output for security-relevant information
            analysis = self._analyze_command_output(command, result.stdout, result.stderr)
            
            # Generate summary
            summary = self._generate_execution_summary(command, result, analysis)
            
            return ToolResult(
                success=result.exit_code == 0,
                output=summary if capture_output else f"Command executed (exit code: {result.exit_code})",
                data={
                    "session_id": session_id,
                    "command": command,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.exit_code,
                    "working_directory": session.working_directory,
                    "analysis": analysis,
                    "execution_time": time.time()
                }
            )
            
        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            session.add_command(command, error_msg, 1)
            
            return ToolResult(
                success=False,
                output=error_msg,
                error=str(e)
            )

    def _analyze_command_output(self, command: str, stdout: str, stderr: str) -> Dict[str, Any]:
        """Analyze command output for security-relevant information"""
        analysis = {
            "command_type": self._classify_command(command),
            "sensitive_data": [],
            "network_activity": [],
            "file_operations": [],
            "potential_vulnerabilities": []
        }
        
        output = stdout + stderr
        
        # Look for sensitive data patterns
        import re
        
        # API keys, tokens, passwords
        sensitive_patterns = [
            (r'[A-Za-z0-9]{32,}', "Potential API Key/Token"),
            (r'password[:\s=]+[^\s\n]+', "Password Reference"),
            (r'secret[:\s=]+[^\s\n]+', "Secret Reference"),
            (r'token[:\s=]+[^\s\n]+', "Token Reference"),
            (r'key[:\s=]+[^\s\n]+', "Key Reference")
        ]
        
        for pattern, description in sensitive_patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            if matches:
                analysis["sensitive_data"].append({
                    "type": description,
                    "matches": len(matches),
                    "sample": matches[0][:20] + "..." if len(matches[0]) > 20 else matches[0]
                })
        
        # Network activity indicators
        network_patterns = [
            (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', "IP Address"),
            (r'https?://[^\s]+', "URL"),
            (r':\d{2,5}\b', "Port Number"),
            (r'listening on', "Service Listening"),
            (r'connected to', "Network Connection")
        ]
        
        for pattern, description in network_patterns:
            matches = re.findall(pattern, output, re.IGNORECASE)
            if matches:
                analysis["network_activity"].append({
                    "type": description,
                    "matches": len(matches),
                    "samples": matches[:3]  # First 3 matches
                })
        
        # File operations
        if any(keyword in command.lower() for keyword in ["ls", "find", "cat", "grep", "tail", "head"]):
            analysis["file_operations"].append({
                "type": "File System Access",
                "command": command,
                "files_found": len(re.findall(r'\S+\.\w+', output))
            })
        
        # Potential vulnerabilities in output
        vuln_indicators = [
            ("error", "Error Message"),
            ("exception", "Exception"),
            ("stack trace", "Stack Trace"),
            ("sql", "SQL Reference"),
            ("admin", "Admin Reference"),
            ("root", "Root Access"),
            ("privilege", "Privilege Reference")
        ]
        
        for indicator, vuln_type in vuln_indicators:
            if indicator in output.lower():
                analysis["potential_vulnerabilities"].append({
                    "type": vuln_type,
                    "indicator": indicator,
                    "context": "Found in command output"
                })
        
        return analysis

    def _classify_command(self, command: str) -> str:
        """Classify the type of command being executed"""
        command_lower = command.lower()
        
        if any(cmd in command_lower for cmd in ["nmap", "masscan", "zmap"]):
            return "Network Scanning"
        elif any(cmd in command_lower for cmd in ["curl", "wget", "http"]):
            return "HTTP Request"
        elif any(cmd in command_lower for cmd in ["sqlmap", "sql"]):
            return "SQL Testing"
        elif any(cmd in command_lower for cmd in ["python", "ruby", "perl", "php"]):
            return "Script Execution"
        elif any(cmd in command_lower for cmd in ["ls", "find", "cat", "grep"]):
            return "File System"
        elif any(cmd in command_lower for cmd in ["ps", "netstat", "ss", "lsof"]):
            return "System Information"
        elif any(cmd in command_lower for cmd in ["nc", "netcat", "socat"]):
            return "Network Tool"
        else:
            return "General Command"

    def _generate_execution_summary(self, command: str, result, analysis: Dict[str, Any]) -> str:
        """Generate human-readable summary of command execution"""
        summary = f"Terminal Command Execution\n"
        summary += "=" * 30 + "\n\n"
        
        summary += f"Command: {command}\n"
        summary += f"Type: {analysis.get('command_type', 'Unknown')}\n"
        summary += f"Exit Code: {result.exit_code}\n"
        summary += f"Output Length: {len(result.stdout)} chars\n\n"
        
        # Show output (truncated if too long)
        if result.stdout:
            output_preview = result.stdout[:500]
            if len(result.stdout) > 500:
                output_preview += "\n... (truncated)"
            summary += f"Output:\n{output_preview}\n\n"
        
        if result.stderr:
            error_preview = result.stderr[:200]
            if len(result.stderr) > 200:
                error_preview += "\n... (truncated)"
            summary += f"Errors:\n{error_preview}\n\n"
        
        # Analysis results
        if analysis.get("sensitive_data"):
            summary += f"⚠️  Sensitive Data Detected: {len(analysis['sensitive_data'])} types\n"
        
        if analysis.get("network_activity"):
            summary += f"🌐 Network Activity: {len(analysis['network_activity'])} types\n"
        
        if analysis.get("potential_vulnerabilities"):
            summary += f"🔍 Potential Issues: {len(analysis['potential_vulnerabilities'])} indicators\n"
        
        return summary


class TerminalHistoryTool(KodiakTool):
    name = "terminal_history"
    description = "View command history for a terminal session. Analyze execution patterns and review previous commands."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Terminal session ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of commands to return (default: 20)"
                },
                "filter_command": {
                    "type": "string",
                    "description": "Filter by command pattern (regex)"
                }
            },
            "required": ["session_id"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _terminal_sessions
        
        session_id = args["session_id"]
        limit = args.get("limit", 20)
        filter_command = args.get("filter_command")
        
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Terminal session {session_id} not found.",
                error="Session not found"
            )
        
        history = session.history
        
        # Apply filter if specified
        if filter_command:
            import re
            filtered_history = []
            for entry in history:
                if re.search(filter_command, entry["command"], re.IGNORECASE):
                    filtered_history.append(entry)
            history = filtered_history
        
        # Limit results
        history = history[-limit:] if len(history) > limit else history
        
        # Generate summary
        summary = f"Terminal History for Session {session_id}\n"
        summary += "=" * 40 + "\n\n"
        summary += f"Total Commands: {len(session.history)}\n"
        summary += f"Showing: {len(history)} commands\n"
        summary += f"Session Age: {int((time.time() - session.created_at) / 60)} minutes\n\n"
        
        if not history:
            summary += "No commands match the specified criteria.\n"
        else:
            summary += "Command History:\n"
            summary += "-" * 15 + "\n"
            
            for i, entry in enumerate(history, 1):
                timestamp = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
                command = entry["command"]
                exit_code = entry["exit_code"]
                
                # Truncate long commands
                if len(command) > 50:
                    command = command[:47] + "..."
                
                status = "✓" if exit_code == 0 else "✗"
                summary += f"{i:2d}. [{timestamp}] {status} {command}\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": session_id,
                "total_commands": len(session.history),
                "filtered_commands": len(history),
                "history": history,
                "session_info": {
                    "shell_type": session.shell_type,
                    "working_directory": session.working_directory,
                    "environment_vars": len(session.environment),
                    "created_at": session.created_at,
                    "last_activity": session.last_activity
                }
            }
        )


class TerminalStopTool(KodiakTool):
    name = "terminal_stop"
    description = "Stop and clean up a terminal session."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Terminal session ID to stop"
                }
            },
            "required": ["session_id"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _terminal_sessions
        
        session_id = args["session_id"]
        
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Terminal session {session_id} not found.",
                error="Session not found"
            )
        
        # Mark session as inactive
        session.is_active = False
        
        # Send WebSocket update for session stop
        from kodiak.services.websocket_manager import manager
        await manager.send_session_update(
            session_type="terminal",
            session_id=session_id,
            status="stopped",
            data={
                "duration_minutes": duration,
                "total_commands": len(session.history)
            }
        )
        
        # Generate session summary
        duration = int((time.time() - session.created_at) / 60)
        
        summary = f"Terminal session {session_id} stopped.\n"
        summary += f"Session Duration: {duration} minutes\n"
        summary += f"Commands Executed: {len(session.history)}\n"
        summary += f"Final Working Directory: {session.working_directory}\n"
        summary += f"Environment Variables: {len(session.environment)}\n"
        summary += f"Session data preserved for analysis.\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": session_id,
                "duration_minutes": duration,
                "total_commands": len(session.history),
                "final_state": {
                    "working_directory": session.working_directory,
                    "environment": session.environment,
                    "shell_type": session.shell_type
                }
            }
        )
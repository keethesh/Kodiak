"""
Terminal Environment Tools for Kodiak

Provides interactive shell environments for command execution, exploit development,
and custom security testing workflows.
"""

import asyncio
import json
import re
import shlex
import time
import uuid
from typing import Dict, Any, List, Optional, AsyncGenerator
from pydantic import BaseModel, Field

from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.services.executor import get_executor


class TerminalSession:
    """Manages persistent terminal session state"""
    
    def __init__(self, session_id: str, shell_type: str = "bash", docker_image: Optional[str] = None):
        self.session_id = session_id
        self.shell_type = shell_type
        self.docker_image = docker_image
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
_SUPPORTED_SHELLS = {"bash", "sh", "zsh", "python"}
_SHELL_ALIASES = {"py": "python", "python3": "python"}
_STALE_INACTIVE_SECONDS = 900  # 15 minutes
_MAX_SESSION_AGE_SECONDS = 86400  # 24 hours


def _cleanup_stale_terminal_sessions() -> int:
    """Drop very old or inactive sessions to avoid stale state buildup."""
    now = time.time()
    stale_ids = []
    for session_id, session in _terminal_sessions.items():
        age = now - session.created_at
        inactive_for = now - session.last_activity
        if age > _MAX_SESSION_AGE_SECONDS or (not session.is_active and inactive_for > _STALE_INACTIVE_SECONDS):
            stale_ids.append(session_id)

    for session_id in stale_ids:
        _terminal_sessions.pop(session_id, None)
    return len(stale_ids)


def _format_session_not_found_output(session_id: str) -> str:
    active = [
        sid
        for sid, s in _terminal_sessions.items()
        if s.is_active
    ]
    sample = ", ".join(sorted(active)[:3]) if active else "none"
    return (
        f"Terminal session {session_id} not found. Start a session first with terminal_start. "
        f"Active sessions: {len(active)} ({sample})."
    )


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
        _cleanup_stale_terminal_sessions()
        
        # Generate unique session ID
        session_id = f"term_{uuid.uuid4().hex[:8]}"
        
        raw_shell = str(args.get("shell_type", "bash")).strip().lower()
        shell_type = _SHELL_ALIASES.get(raw_shell, raw_shell)
        if shell_type not in _SUPPORTED_SHELLS:
            return ToolResult(
                success=False,
                output=(
                    f"Unsupported shell type: {raw_shell}. "
                    f"Supported shells: {', '.join(sorted(_SUPPORTED_SHELLS))}."
                ),
                error="Unsupported shell type"
            )

        environment = args.get("environment") or {}
        working_directory = args.get("working_directory", "/tmp")
        
        # Default to Docker toolbox for security workflows.
        from kodiak.core.config import settings
        docker_image = args.get("docker_image") or settings.toolbox_image
        
        # Create terminal session
        session = TerminalSession(session_id, shell_type, docker_image=docker_image)
        session.environment.update(environment)
        session.working_directory = working_directory
        
        # Store session
        _terminal_sessions[session_id] = session
        
        # Test initial connection
        try:
            test_command = "pwd" if shell_type != "python" else "import os; print(os.getcwd())"
            
            executor = get_executor("docker")
            executor.image = docker_image
            
            # Test the session
            if shell_type == "python":
                result = await asyncio.wait_for(
                    executor.run_command(
                        ["python3", "-c", test_command],
                        cwd=working_directory,
                        env=session.environment
                    ),
                    timeout=30
                )
            else:
                shell_probe = await asyncio.wait_for(
                    executor.run_command(
                        ["/bin/sh", "-c", f"command -v {shell_type} >/dev/null 2>&1"],
                        cwd=working_directory,
                        env=session.environment
                    ),
                    timeout=30
                )
                if shell_probe.exit_code != 0:
                    raise RuntimeError(
                        f"Requested shell '{shell_type}' is not available in container {docker_image}"
                    )
                result = await asyncio.wait_for(
                    executor.run_command(
                        [shell_type, "-c", test_command],
                        cwd=working_directory,
                        env=session.environment
                    ),
                    timeout=30
                )

            if result.exit_code != 0:
                raise RuntimeError(result.stderr or result.stdout or f"Terminal bootstrap failed with exit code {result.exit_code}")
            
            session.add_command(test_command, result.stdout, result.exit_code)
            
            # Notify WebSocket clients if available (no-op in CLI mode)
            try:
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
            except Exception:
                pass  # WebSocket not available in CLI mode
            
            summary = f"Terminal session started successfully\n"
            summary += f"Session ID: {session_id}\n"
            summary += f"Shell: {shell_type}\n"
            summary += f"Working Directory: {working_directory}\n"
            summary += f"Environment Variables: {len(environment)}\n"
            summary += f"Execution Mode: Docker ({docker_image})\n"
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
            
            if isinstance(e, asyncio.TimeoutError):
                message = "Terminal startup timed out after 30 seconds"
            else:
                message = str(e)

            return ToolResult(
                success=False,
                output=f"Failed to start terminal session: {message}",
                error=message
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
        _cleanup_stale_terminal_sessions()
        
        session_id = args["session_id"]
        command = args["command"]
        timeout = args.get("timeout", 30)
        capture_output = args.get("capture_output", True)
        
        # Get session
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=_format_session_not_found_output(session_id),
                error="Session not found"
            )
        
        if not session.is_active:
            return ToolResult(
                success=False,
                output=(
                    f"Terminal session {session_id} is not active. "
                    "Start a new one with terminal_start."
                ),
                error="Session inactive"
            )
        
        try:
            # Determine executor
            if session.docker_image:
                executor = get_executor("docker")
                executor.image = session.docker_image
            else:
                executor = get_executor("local")
            
            # Handle special commands
            if command.startswith("cd "):
                # Change directory command
                new_dir = command[3:].strip()
                if not new_dir.startswith("/"):
                    # Relative path
                    new_dir = f"{session.working_directory}/{new_dir}"
                
                # Test if directory exists
                test_result = await asyncio.wait_for(
                    executor.run_command(
                        ["test", "-d", new_dir],
                        cwd=session.working_directory,
                        env=session.environment
                    ),
                    timeout=timeout
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
                            "docker_image": session.docker_image,
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
            
            elif command.startswith("export "):
                # Only intercept explicit, assignment-only export commands.
                # Commands containing '=' (curl/sqlmap/etc.) must execute normally.
                env_updates, parse_error = self._parse_export_command(command)
                if parse_error:
                    session.add_command(command, parse_error, 1)
                    return ToolResult(
                        success=False,
                        output=parse_error,
                        error="Invalid export syntax"
                    )
                if env_updates is not None:
                    session.set_environment(env_updates)
                    updates_text = ", ".join(f"{k}={v}" for k, v in env_updates.items())
                    output = f"Set environment variable(s): {updates_text}"
                    session.add_command(command, output, 0)

                    return ToolResult(
                        success=True,
                        output=output,
                        data={
                            "session_id": session_id,
                            "command": command,
                            "environment_updated": env_updates,
                            "docker_image": session.docker_image,
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
            
            run_kwargs = {
                "cwd": session.working_directory,
                "env": session.environment,
            }
            cap_add = self._caps_for_command(command)
            if cap_add:
                run_kwargs["cap_add"] = cap_add

            result = await asyncio.wait_for(
                executor.run_command(full_command, **run_kwargs),
                timeout=timeout
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
                    "docker_image": session.docker_image,
                    "analysis": analysis,
                    "execution_time": time.time()
                }
            )
            
        except asyncio.TimeoutError:
            error_msg = f"Command execution timed out after {timeout} seconds"
            session.add_command(command, error_msg, 1)
            return ToolResult(
                success=False,
                output=error_msg,
                error="Command timeout"
            )

        except Exception as e:
            error_msg = f"Command execution failed: {str(e)}"
            session.add_command(command, error_msg, 1)
            
            return ToolResult(
                success=False,
                output=error_msg,
                error=str(e)
            )

    def _parse_export_command(self, command: str) -> tuple[Optional[Dict[str, str]], Optional[str]]:
        """
        Parse explicit `export KEY=VALUE` updates for persistent session env.

        Returns:
          - (dict, None) when it is a supported export assignment command
          - (None, None) when command should be executed normally by the shell
          - (None, error_message) when command is an explicit export but malformed
        """
        payload = command[len("export "):].strip()
        if not payload:
            return None, "Invalid export syntax: expected at least one KEY=VALUE assignment."

        # If export is chained with shell operators, don't intercept; let shell execute it.
        if any(op in payload for op in ("&&", "||", ";", "|", "$(", "`")):
            return None, None

        try:
            tokens = shlex.split(payload)
        except ValueError as e:
            return None, f"Invalid export syntax: {e}"

        if not tokens:
            return None, "Invalid export syntax: expected KEY=VALUE assignment."

        updates: Dict[str, str] = {}
        for token in tokens:
            if "=" not in token:
                # Non-assignment export forms (e.g. `export VAR`) should be executed by shell.
                return None, None

            key, value = token.split("=", 1)
            key = key.strip()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):
                return None, f"Invalid environment variable name: {key}"
            updates[key] = value

        return updates, None

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

    _RAW_SOCKET_PATTERNS = [
        "masscan", "zmap",
        "nmap -ss", "nmap -su", "nmap -o", "nmap -a",
        "-ss ", "-su ", " -o ", " -a ",
    ]

    def _caps_for_command(self, command: str) -> list[str] | None:
        """Return Docker capabilities required by *command*, or None if none needed.

        Tools that use raw sockets (masscan, nmap SYN/UDP/OS-detection) require
        NET_RAW and NET_ADMIN.  Everything else runs without extra capabilities.
        """
        cmd_lower = command.lower()
        if any(pat in cmd_lower for pat in self._RAW_SOCKET_PATTERNS):
            return ["NET_RAW", "NET_ADMIN"]
        return None

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
        
        stdout_preview_chars = 2000
        stderr_preview_chars = 500

        # Show output (truncated if too long)
        if result.stdout:
            output_preview = result.stdout[:stdout_preview_chars]
            if len(result.stdout) > stdout_preview_chars:
                output_preview += "\n... (truncated)"
            summary += f"Output:\n{output_preview}\n\n"
        
        if result.stderr:
            error_preview = result.stderr[:stderr_preview_chars]
            if len(result.stderr) > stderr_preview_chars:
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
        _cleanup_stale_terminal_sessions()
        
        session_id = args["session_id"]
        limit = args.get("limit", 20)
        filter_command = args.get("filter_command")
        
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=_format_session_not_found_output(session_id),
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
                    "docker_image": session.docker_image,
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
        _cleanup_stale_terminal_sessions()
        
        session_id = args["session_id"]
        
        session = _terminal_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=_format_session_not_found_output(session_id),
                error="Session not found"
            )
        
        # Mark session as inactive
        session.is_active = False
        duration = int((time.time() - session.created_at) / 60)
        
        # Notify WebSocket clients if available (no-op in CLI mode)
        try:
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
        except Exception:
            pass  # WebSocket not available in CLI mode
        
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
                    "shell_type": session.shell_type,
                    "docker_image": session.docker_image,
                }
            }
        )

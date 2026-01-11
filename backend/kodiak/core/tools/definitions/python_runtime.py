"""
Python Runtime Tools for Kodiak

Provides Python code execution capabilities for custom exploit development,
proof-of-concept creation, and advanced security testing workflows.
"""

import asyncio
import json
import sys
import traceback
import time
import uuid
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from io import StringIO
import contextlib

from kodiak.core.tools.base import KodiakTool, ToolResult


class PythonSession:
    """Manages persistent Python execution session"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.globals_dict = {
            '__builtins__': __builtins__,
            '__name__': '__kodiak_session__',
            '__doc__': None,
        }
        self.execution_history: List[Dict[str, Any]] = []
        self.created_at = time.time()
        self.last_activity = time.time()
        self.is_active = True
        
        # Pre-import common security testing libraries
        self._setup_security_imports()
    
    def _setup_security_imports(self):
        """Pre-import common libraries for security testing"""
        try:
            # Import common libraries into session globals
            imports = [
                "import requests",
                "import json",
                "import base64",
                "import hashlib",
                "import urllib.parse",
                "import re",
                "import time",
                "import random",
                "import string",
                "from urllib.parse import urlencode, quote, unquote",
                "import socket",
                "import subprocess",
                "import os",
                "import sys"
            ]
            
            for import_stmt in imports:
                try:
                    exec(import_stmt, self.globals_dict)
                except ImportError:
                    pass  # Skip if library not available
                    
        except Exception as e:
            pass  # Continue even if some imports fail
    
    def execute_code(self, code: str) -> Dict[str, Any]:
        """Execute Python code in the session context"""
        self.last_activity = time.time()
        
        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        result = {
            "code": code,
            "success": False,
            "output": "",
            "error": "",
            "result": None,
            "timestamp": time.time()
        }
        
        try:
            # Redirect output
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            
            # Try to evaluate as expression first (for single expressions)
            try:
                compiled = compile(code, '<kodiak>', 'eval')
                result["result"] = eval(compiled, self.globals_dict)
                result["success"] = True
            except SyntaxError:
                # If not an expression, execute as statement
                compiled = compile(code, '<kodiak>', 'exec')
                exec(compiled, self.globals_dict)
                result["success"] = True
            
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {str(e)}"
            result["traceback"] = traceback.format_exc()
        
        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            
            # Capture output
            result["output"] = stdout_capture.getvalue()
            if stderr_capture.getvalue():
                result["error"] += "\n" + stderr_capture.getvalue()
        
        # Store in history
        self.execution_history.append(result)
        
        return result


# Global Python sessions
_python_sessions: Dict[str, PythonSession] = {}


class PythonStartArgs(BaseModel):
    session_name: Optional[str] = Field(None, description="Optional session name for identification")
    preload_libraries: bool = Field(True, description="Preload common security testing libraries")


class PythonExecuteArgs(BaseModel):
    session_id: str = Field(..., description="Python session ID")
    code: str = Field(..., description="Python code to execute")
    timeout: int = Field(30, description="Execution timeout in seconds")


class PythonStartTool(KodiakTool):
    name = "python_start"
    description = "Start a persistent Python session for custom exploit development and security testing. Pre-loads common libraries like requests, json, base64, etc."
    args_schema = PythonStartArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_name": {
                    "type": "string",
                    "description": "Optional descriptive name for the session"
                },
                "preload_libraries": {
                    "type": "boolean",
                    "description": "Preload common security testing libraries (default: true)"
                }
            }
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _python_sessions
        
        # Generate unique session ID
        session_id = f"py_{uuid.uuid4().hex[:8]}"
        session_name = args.get("session_name", f"Python Session {session_id}")
        
        # Create Python session
        session = PythonSession(session_id)
        _python_sessions[session_id] = session
        
        # Test session with a simple command
        test_result = session.execute_code("print('Python session initialized')")
        
        # Send WebSocket update for session start
        from kodiak.services.websocket_manager import manager
        await manager.send_session_update(
            session_type="python",
            session_id=session_id,
            status="started",
            data={
                "session_name": session_name,
                "available_libraries": available_libs,
                "test_successful": test_result["success"]
            }
        )
        
        summary = f"Python Runtime Session Started\n"
        summary += "=" * 35 + "\n\n"
        summary += f"Session ID: {session_id}\n"
        summary += f"Session Name: {session_name}\n"
        summary += f"Pre-loaded Libraries: {'Yes' if args.get('preload_libraries', True) else 'No'}\n"
        summary += f"Available Globals: {len(session.globals_dict)} items\n"
        summary += f"Test Output: {test_result['output'].strip()}\n\n"
        
        # Show available libraries
        available_libs = []
        for name, obj in session.globals_dict.items():
            if hasattr(obj, '__name__') and not name.startswith('_'):
                available_libs.append(name)
        
        if available_libs:
            summary += f"Pre-loaded Libraries: {', '.join(sorted(available_libs))}\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": session_id,
                "session_name": session_name,
                "available_libraries": available_libs,
                "globals_count": len(session.globals_dict),
                "test_successful": test_result["success"]
            }
        )


class PythonExecuteTool(KodiakTool):
    name = "python_execute"
    description = "Execute Python code in a persistent session. Perfect for developing exploits, testing payloads, parsing responses, and creating proof-of-concepts."
    args_schema = PythonExecuteArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Python session ID from python_start"
                },
                "code": {
                    "type": "string",
                    "description": "Python code to execute (can be expressions or statements)"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (default: 30)"
                }
            },
            "required": ["session_id", "code"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _python_sessions
        
        session_id = args["session_id"]
        code = args["code"]
        timeout = args.get("timeout", 30)
        
        # Get session
        session = _python_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Python session {session_id} not found. Start a session first with python_start.",
                error="Session not found"
            )
        
        if not session.is_active:
            return ToolResult(
                success=False,
                output=f"Python session {session_id} is not active.",
                error="Session inactive"
            )
        
        try:
            # Execute code with timeout
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, session.execute_code, code
                ),
                timeout=timeout
            )
            
            # Analyze the code and result for security relevance
            analysis = self._analyze_python_execution(code, result)
            
            # Generate summary
            summary = self._generate_execution_summary(code, result, analysis)
            
            return ToolResult(
                success=result["success"],
                output=summary,
                data={
                    "session_id": session_id,
                    "code": code,
                    "result": result["result"],
                    "output": result["output"],
                    "error": result["error"],
                    "success": result["success"],
                    "analysis": analysis,
                    "execution_time": result["timestamp"]
                }
            )
            
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                output=f"Python code execution timed out after {timeout} seconds.",
                error="Execution timeout"
            )
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Python execution failed: {str(e)}",
                error=str(e)
            )

    def _analyze_python_execution(self, code: str, result: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze Python code execution for security testing patterns"""
        analysis = {
            "code_type": self._classify_code(code),
            "security_functions": [],
            "network_operations": [],
            "data_processing": [],
            "potential_exploits": []
        }
        
        code_lower = code.lower()
        output = result.get("output", "")
        
        # Identify security-related functions
        security_patterns = [
            ("requests.", "HTTP Request"),
            ("urllib", "URL Processing"),
            ("base64.", "Base64 Encoding/Decoding"),
            ("hashlib.", "Cryptographic Hashing"),
            ("socket.", "Network Socket"),
            ("subprocess.", "System Command"),
            ("os.system", "System Command"),
            ("eval(", "Code Evaluation"),
            ("exec(", "Code Execution"),
            ("__import__", "Dynamic Import")
        ]
        
        for pattern, description in security_patterns:
            if pattern in code_lower:
                analysis["security_functions"].append({
                    "type": description,
                    "pattern": pattern,
                    "context": "Found in code"
                })
        
        # Network operations
        if any(keyword in code_lower for keyword in ["requests.get", "requests.post", "urllib.request", "socket.connect"]):
            analysis["network_operations"].append({
                "type": "Network Request",
                "detected": True,
                "methods": [method for method in ["get", "post", "put", "delete"] if method in code_lower]
            })
        
        # Data processing patterns
        if any(keyword in code_lower for keyword in ["json.loads", "json.dumps", "parse", "decode", "encode"]):
            analysis["data_processing"].append({
                "type": "Data Parsing/Encoding",
                "detected": True
            })
        
        # Potential exploit patterns
        exploit_indicators = [
            ("payload", "Payload Construction"),
            ("injection", "Injection Attack"),
            ("xss", "Cross-Site Scripting"),
            ("sql", "SQL Related"),
            ("shell", "Shell Command"),
            ("reverse", "Reverse Shell"),
            ("bind", "Bind Shell"),
            ("exploit", "Exploit Code")
        ]
        
        for indicator, exploit_type in exploit_indicators:
            if indicator in code_lower:
                analysis["potential_exploits"].append({
                    "type": exploit_type,
                    "indicator": indicator,
                    "confidence": "medium"
                })
        
        # Analyze output for interesting results
        if output:
            if any(keyword in output.lower() for keyword in ["error", "exception", "traceback"]):
                analysis["potential_exploits"].append({
                    "type": "Error/Exception Output",
                    "indicator": "error_output",
                    "confidence": "low"
                })
            
            # Look for HTTP status codes
            import re
            status_codes = re.findall(r'\b[1-5]\d{2}\b', output)
            if status_codes:
                analysis["network_operations"].append({
                    "type": "HTTP Status Codes",
                    "codes": status_codes[:5]  # First 5 codes
                })
        
        return analysis

    def _classify_code(self, code: str) -> str:
        """Classify the type of Python code being executed"""
        code_lower = code.lower()
        
        if any(keyword in code_lower for keyword in ["requests.", "urllib", "http"]):
            return "HTTP/Network Request"
        elif any(keyword in code_lower for keyword in ["base64", "encode", "decode", "hash"]):
            return "Data Encoding/Cryptography"
        elif any(keyword in code_lower for keyword in ["json", "parse", "loads", "dumps"]):
            return "Data Processing"
        elif any(keyword in code_lower for keyword in ["socket", "connect", "bind", "listen"]):
            return "Network Programming"
        elif any(keyword in code_lower for keyword in ["subprocess", "os.system", "popen"]):
            return "System Command"
        elif any(keyword in code_lower for keyword in ["payload", "exploit", "injection"]):
            return "Exploit Development"
        elif "def " in code_lower or "class " in code_lower:
            return "Function/Class Definition"
        elif any(keyword in code_lower for keyword in ["for ", "while ", "if "]):
            return "Control Flow"
        else:
            return "General Python Code"

    def _generate_execution_summary(self, code: str, result: Dict[str, Any], analysis: Dict[str, Any]) -> str:
        """Generate human-readable summary of Python execution"""
        summary = f"Python Code Execution\n"
        summary += "=" * 25 + "\n\n"
        
        summary += f"Code Type: {analysis.get('code_type', 'Unknown')}\n"
        summary += f"Success: {'✓' if result['success'] else '✗'}\n"
        
        # Show code (truncated if long)
        code_preview = code[:200]
        if len(code) > 200:
            code_preview += "\n... (truncated)"
        summary += f"Code:\n{code_preview}\n\n"
        
        # Show result if available
        if result.get("result") is not None:
            result_str = str(result["result"])
            if len(result_str) > 300:
                result_str = result_str[:297] + "..."
            summary += f"Result: {result_str}\n\n"
        
        # Show output if available
        if result.get("output"):
            output_preview = result["output"][:300]
            if len(result["output"]) > 300:
                output_preview += "\n... (truncated)"
            summary += f"Output:\n{output_preview}\n\n"
        
        # Show errors if any
        if result.get("error"):
            error_preview = result["error"][:200]
            if len(result["error"]) > 200:
                error_preview += "\n... (truncated)"
            summary += f"Error:\n{error_preview}\n\n"
        
        # Analysis summary
        if analysis.get("security_functions"):
            summary += f"🔧 Security Functions: {len(analysis['security_functions'])}\n"
        
        if analysis.get("network_operations"):
            summary += f"🌐 Network Operations: {len(analysis['network_operations'])}\n"
        
        if analysis.get("potential_exploits"):
            summary += f"⚠️  Exploit Indicators: {len(analysis['potential_exploits'])}\n"
        
        return summary


class PythonHistoryTool(KodiakTool):
    name = "python_history"
    description = "View execution history for a Python session. Review previous code executions and results."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Python session ID"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of executions to return (default: 10)"
                },
                "filter_success": {
                    "type": "boolean",
                    "description": "Filter by successful executions only"
                }
            },
            "required": ["session_id"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _python_sessions
        
        session_id = args["session_id"]
        limit = args.get("limit", 10)
        filter_success = args.get("filter_success")
        
        session = _python_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Python session {session_id} not found.",
                error="Session not found"
            )
        
        history = session.execution_history
        
        # Apply filter if specified
        if filter_success is not None:
            history = [entry for entry in history if entry["success"] == filter_success]
        
        # Limit results
        history = history[-limit:] if len(history) > limit else history
        
        # Generate summary
        summary = f"Python Execution History for Session {session_id}\n"
        summary += "=" * 50 + "\n\n"
        summary += f"Total Executions: {len(session.execution_history)}\n"
        summary += f"Showing: {len(history)} executions\n"
        summary += f"Session Age: {int((time.time() - session.created_at) / 60)} minutes\n\n"
        
        if not history:
            summary += "No executions match the specified criteria.\n"
        else:
            summary += "Execution History:\n"
            summary += "-" * 18 + "\n"
            
            for i, entry in enumerate(history, 1):
                timestamp = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
                code = entry["code"].replace("\n", " ")
                success = "✓" if entry["success"] else "✗"
                
                # Truncate long code
                if len(code) > 60:
                    code = code[:57] + "..."
                
                summary += f"{i:2d}. [{timestamp}] {success} {code}\n"
                
                # Show result/error preview
                if entry.get("result") is not None:
                    result_str = str(entry["result"])[:40]
                    summary += f"     → {result_str}\n"
                elif entry.get("error"):
                    error_str = entry["error"].split("\n")[0][:40]
                    summary += f"     ✗ {error_str}\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": session_id,
                "total_executions": len(session.execution_history),
                "filtered_executions": len(history),
                "history": history,
                "session_info": {
                    "created_at": session.created_at,
                    "last_activity": session.last_activity,
                    "globals_count": len(session.globals_dict)
                }
            }
        )


class PythonStopTool(KodiakTool):
    name = "python_stop"
    description = "Stop and clean up a Python session."
    args_schema = BaseModel

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Python session ID to stop"
                }
            },
            "required": ["session_id"]
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        global _python_sessions
        
        session_id = args["session_id"]
        
        session = _python_sessions.get(session_id)
        if not session:
            return ToolResult(
                success=False,
                output=f"Python session {session_id} not found.",
                error="Session not found"
            )
        
        # Mark session as inactive
        session.is_active = False
        
        # Send WebSocket update for session stop
        from kodiak.services.websocket_manager import manager
        await manager.send_session_update(
            session_type="python",
            session_id=session_id,
            status="stopped",
            data={
                "duration_minutes": duration,
                "total_executions": len(session.execution_history)
            }
        )
        
        # Generate session summary
        duration = int((time.time() - session.created_at) / 60)
        
        summary = f"Python session {session_id} stopped.\n"
        summary += f"Session Duration: {duration} minutes\n"
        summary += f"Code Executions: {len(session.execution_history)}\n"
        summary += f"Global Variables: {len(session.globals_dict)}\n"
        summary += f"Session data preserved for analysis.\n"
        
        return ToolResult(
            success=True,
            output=summary,
            data={
                "session_id": session_id,
                "duration_minutes": duration,
                "total_executions": len(session.execution_history),
                "globals_count": len(session.globals_dict)
            }
        )
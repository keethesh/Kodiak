from typing import Dict, Type
from kodiak.core.tools.base import KodiakTool

class ToolInventory:
    _tools: Dict[str, KodiakTool] = {}

    @classmethod
    def register(cls, tool: KodiakTool):
        cls._tools[tool.name] = tool

    @classmethod
    def get(cls, name: str) -> KodiakTool | None:
        return cls._tools.get(name)

    @classmethod
    def list_tools(cls) -> Dict[str, str]:
        return {name: tool.description for name, tool in cls._tools.items()}

# Import and register all tools
from kodiak.core.tools.definitions.network import NmapTool
from kodiak.core.tools.definitions.web import NucleiTool
from kodiak.core.tools.definitions.system import TerminalTool
from kodiak.core.tools.definitions.discovery import SubfinderTool, HttpxTool
from kodiak.core.tools.definitions.browser import BrowserNavigateTool
from kodiak.core.tools.definitions.osint import WebSearchTool
from kodiak.core.tools.definitions.exploitation import SQLMapTool, CommixTool
from kodiak.core.tools.definitions.proxy import (
    ProxyStartTool, ProxyRequestTool, ProxyHistoryTool, ProxyStopTool
)
from kodiak.core.tools.definitions.terminal import (
    TerminalStartTool, TerminalExecuteTool, TerminalHistoryTool, TerminalStopTool
)
from kodiak.core.tools.definitions.python_runtime import (
    PythonStartTool, PythonExecuteTool, PythonHistoryTool, PythonStopTool
)

# Create inventory instance
inventory = ToolInventory()

# Register all tools
inventory.register(NmapTool())
inventory.register(NucleiTool())
inventory.register(TerminalTool())
inventory.register(SubfinderTool())
inventory.register(HttpxTool())
inventory.register(BrowserNavigateTool())
inventory.register(WebSearchTool())
inventory.register(SQLMapTool())
inventory.register(CommixTool())

# Register new comprehensive tools
inventory.register(ProxyStartTool())
inventory.register(ProxyRequestTool())
inventory.register(ProxyHistoryTool())
inventory.register(ProxyStopTool())

inventory.register(TerminalStartTool())
inventory.register(TerminalExecuteTool())
inventory.register(TerminalHistoryTool())
inventory.register(TerminalStopTool())

inventory.register(PythonStartTool())
inventory.register(PythonExecuteTool())
inventory.register(PythonHistoryTool())
inventory.register(PythonStopTool())

# Export available tools for easy access
AVAILABLE_TOOLS = {
    # Network & Infrastructure
    "nmap": "Network discovery and security auditing",
    "nuclei": "Fast vulnerability scanner with YAML templates",
    
    # Discovery & Reconnaissance  
    "subfinder": "Passive subdomain enumeration",
    "httpx": "HTTP toolkit for probing web services",
    
    # Web Application Testing
    "browser_navigate": "Browser automation for web app testing",
    "sqlmap": "Automatic SQL injection detection and exploitation",
    "commix": "Command injection detection and exploitation",
    
    # HTTP Proxy System
    "proxy_start": "Start HTTP proxy server for request interception",
    "proxy_request": "Send HTTP requests through proxy with full control",
    "proxy_history": "View proxy request/response history",
    "proxy_stop": "Stop HTTP proxy server",
    
    # Terminal Environment
    "terminal_start": "Start persistent terminal session",
    "terminal_execute": "Execute commands in terminal session",
    "terminal_history": "View terminal command history",
    "terminal_stop": "Stop terminal session",
    
    # Python Runtime
    "python_start": "Start Python session for exploit development",
    "python_execute": "Execute Python code in persistent session",
    "python_history": "View Python execution history",
    "python_stop": "Stop Python session",
    
    # OSINT & Information Gathering
    "web_search": "Web search for reconnaissance",
    
    # System & Utilities
    "terminal_execute": "Execute system commands"
}

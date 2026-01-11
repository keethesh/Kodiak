from typing import Dict, Type, Optional
from kodiak.core.tools.base import KodiakTool

class ToolInventory:
    def __init__(self, event_manager=None):
        """Initialize ToolInventory with optional EventManager"""
        self._tools: Dict[str, KodiakTool] = {}
        self._event_manager = event_manager

    def register(self, tool: KodiakTool):
        """Register a tool with the inventory"""
        # Inject EventManager into the tool if available
        if self._event_manager and hasattr(tool, 'event_manager'):
            tool.event_manager = self._event_manager
        
        self._tools[tool.name] = tool

    def get(self, name: str) -> KodiakTool | None:
        """Get a tool by name"""
        return self._tools.get(name)

    def list_tools(self) -> Dict[str, str]:
        """List all registered tools"""
        return {name: tool.description for name, tool in self._tools.items()}
    
    def get_all_tools(self) -> Dict[str, KodiakTool]:
        """Get all registered tool instances"""
        return self._tools.copy()
    
    def initialize_tools(self):
        """Initialize and register all available tools"""
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

        # Register all tools
        self.register(NmapTool())
        self.register(NucleiTool())
        self.register(TerminalTool())
        self.register(SubfinderTool())
        self.register(HttpxTool())
        self.register(BrowserNavigateTool())
        self.register(WebSearchTool())
        self.register(SQLMapTool())
        self.register(CommixTool())

        # Register new comprehensive tools
        self.register(ProxyStartTool())
        self.register(ProxyRequestTool())
        self.register(ProxyHistoryTool())
        self.register(ProxyStopTool())

        self.register(TerminalStartTool())
        self.register(TerminalExecuteTool())
        self.register(TerminalHistoryTool())
        self.register(TerminalStopTool())

        self.register(PythonStartTool())
        self.register(PythonExecuteTool())
        self.register(PythonHistoryTool())
        self.register(PythonStopTool())


# Legacy global instance for backward compatibility
# This will be replaced by the instance created in main.py
_legacy_inventory = None

def get_legacy_inventory():
    """Get the legacy global inventory instance"""
    global _legacy_inventory
    if _legacy_inventory is None:
        _legacy_inventory = ToolInventory()
        _legacy_inventory.initialize_tools()
    return _legacy_inventory

# For backward compatibility
inventory = get_legacy_inventory()

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

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
    
    # OSINT & Information Gathering
    "web_search": "Web search for reconnaissance",
    
    # System & Utilities
    "terminal_execute": "Execute system commands"
}

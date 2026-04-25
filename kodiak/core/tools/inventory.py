from typing import Dict, Optional

from kodiak.core.tools.base import KodiakTool
from kodiak.core.tools.registry import get_available_tools as _get_available_tools


class ToolInventory:
    _tools: Dict[str, KodiakTool] = {}

    def __init__(self):
        """Initialize ToolInventory"""
        self._tools = type(self)._tools

    def register(self, tool: KodiakTool):
        """Register a tool with the inventory"""
        type(self)._tools[tool.name] = tool
        self._tools = type(self)._tools

    def get(self, name: str) -> Optional[KodiakTool]:
        """Get a tool by name"""
        return type(self)._tools.get(name)

    def list_tools(self) -> Dict[str, str]:
        """List all registered tools"""
        return {name: tool.description for name, tool in type(self)._tools.items()}

    def get_all_tools(self) -> Dict[str, KodiakTool]:
        """Get all registered tool instances"""
        return type(self)._tools.copy()

    def initialize_tools(self):
        """Initialize and register all available tools"""
        from kodiak.core.tools.definitions.network import NmapTool
        from kodiak.core.tools.definitions.web import NucleiTool
        from kodiak.core.tools.definitions.discovery import (
            SubfinderTool, HttpxTool, KatanaTool, FfufTool, WhatWebTool,
        )
        from kodiak.core.tools.definitions.osint import WebSearchTool
        from kodiak.core.tools.definitions.exploitation import (
            SQLMapTool, CommixTool, SearchsploitTool, WPScanTool,
        )
        from kodiak.core.tools.definitions.proxy import (
            ProxyStartTool, ProxyRequestTool, ProxyHistoryTool, ProxyStopTool,
        )
        from kodiak.core.tools.definitions.terminal import (
            TerminalStartTool, TerminalExecuteTool, TerminalHistoryTool, TerminalStopTool,
        )
        from kodiak.core.tools.definitions.python_runtime import (
            PythonStartTool, PythonExecuteTool, PythonHistoryTool, PythonStopTool,
        )
        from kodiak.core.tools.definitions.engagement_memory import (
            SaveFindingTool, SaveNoteTool,
        )
        from kodiak.core.tools.definitions.complete_scan import CompleteScanTool

        # Network & vulnerability scanning
        self.register(NmapTool())
        self.register(NucleiTool())

        # Discovery & reconnaissance
        self.register(SubfinderTool())
        self.register(HttpxTool())
        self.register(KatanaTool())
        self.register(FfufTool())
        self.register(WhatWebTool())

        # OSINT
        self.register(WebSearchTool())

        # Web application exploitation
        self.register(SQLMapTool())
        self.register(WPScanTool())
        self.register(CommixTool())
        self.register(SearchsploitTool())

        # HTTP proxy
        self.register(ProxyStartTool())
        self.register(ProxyRequestTool())
        self.register(ProxyHistoryTool())
        self.register(ProxyStopTool())

        # Persistent terminal
        self.register(TerminalStartTool())
        self.register(TerminalExecuteTool())
        self.register(TerminalHistoryTool())
        self.register(TerminalStopTool())

        # Python runtime
        self.register(PythonStartTool())
        self.register(PythonExecuteTool())
        self.register(PythonHistoryTool())
        self.register(PythonStopTool())

        # Engagement memory
        self.register(SaveNoteTool())
        self.register(SaveFindingTool())

        # Scan control
        self.register(CompleteScanTool())


# Legacy global instance for backward compatibility
_legacy_inventory = None


def get_legacy_inventory() -> ToolInventory:
    """Get the legacy global inventory instance"""
    global _legacy_inventory
    if _legacy_inventory is None:
        _legacy_inventory = ToolInventory()
        _legacy_inventory.initialize_tools()
    return _legacy_inventory


# For backward compatibility
inventory = get_legacy_inventory()
# Derived from the single source of truth in registry.py.
# Covers Core + Extended tools (not Utility — those are implicit Kali builtins).
AVAILABLE_TOOLS = _get_available_tools()




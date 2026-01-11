from typing import Dict, Type
from kodiak.core.tools.base import KodiakTool
from kodiak.core.tools.definitions.network import NmapTool

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

from kodiak.core.tools.definitions.web import NucleiTool

inventory = ToolInventory()
inventory.register(NmapTool())
inventory.register(NucleiTool())

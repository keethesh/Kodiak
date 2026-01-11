from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str
    data: Dict[str, Any] = {}  # Structured data (parsed JSON, etc.)
    error: str | None = None


class KodiakTool(ABC):
    name: str
    description: str
    args_schema: Type[BaseModel]

    @abstractmethod
    async def run(self, args: BaseModel) -> ToolResult:
        """
        Execute the tool with the given arguments.
        """
        pass

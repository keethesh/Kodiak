from abc import ABC, abstractmethod
from typing import Any, Dict, Type

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str
    data: Dict[str, Any] = {}  # Structured data (parsed JSON, etc.)
    error: str | None = None


class KodiakTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for the tool parameters."""
        return {}
    
    def to_openai_schema(self) -> Dict[str, Any]:
        """Converts the tool definition to OpenAI function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema
            }
        }
    
    # Optional Pydantic support
    args_schema: Type[BaseModel] | None = None

    async def run(self, args: BaseModel | Dict[str, Any]) -> ToolResult:
        """
        Execute the tool. Accepts either Pydantic model or Dict.
        """
        try:
            if isinstance(args, BaseModel):
                data = args.dict()
            else:
                data = args
            
            # Call internal execute
            result_data = await self._execute(data)
            
            # Allow _execute to return a dict or a ToolResult
            if isinstance(result_data, ToolResult):
                return result_data
                
            return ToolResult(
                success=True, 
                output=str(result_data.get("output", "")) if isinstance(result_data, dict) else str(result_data),
                data=result_data if isinstance(result_data, dict) else {"raw": result_data}
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @abstractmethod
    async def _execute(self, args: Dict[str, Any]) -> Any:
        pass

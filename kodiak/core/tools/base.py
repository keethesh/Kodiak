import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Type, Optional

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    success: bool
    output: str
    data: Dict[str, Any] = Field(default_factory=dict)  # Structured data (parsed JSON, etc.)
    error: str | None = None


class BaseTool(ABC):
    """
    Base class for all Kodiak tools with EventManager integration.
    """
    
    def __init__(self):
        """Initialize tool."""
        pass
    
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
        schema = self.parameters_schema.copy()

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }
    
    # Optional Pydantic support
    args_schema: Type[BaseModel] | None = None
    execution_timeout: int | None = None

    async def execute(self, **kwargs) -> ToolResult:
        """
        Public interface - handles logic and calls _execute.
        This is the main entry point for tool execution.
        """
        # Extract context information
        target = kwargs.get('target', 'unknown')
        
        try:
            # Validate required parameters if args_schema is defined
            if self.args_schema:
                try:
                    # Validate arguments against schema
                    validated_args = self.args_schema(**kwargs)
                    # Update kwargs with validated data
                    kwargs.update(validated_args.dict())
                except Exception as validation_error:
                    return ToolResult(
                        success=False,
                        output=f"Parameter validation failed: {str(validation_error)}",
                        error=f"Invalid parameters: {str(validation_error)}"
                    )
            
            # Execute the actual tool logic with timeout
            try:
                from kodiak.core.config import settings
                configured_timeout = getattr(self, "execution_timeout", None)
                tool_timeout = configured_timeout if configured_timeout and configured_timeout > 0 else settings.tool_timeout
                # Convert kwargs to args dict for tool execution.
                # Keep full runtime context (agent_id/scan_id/project_id) for stateful tools.
                args_dict = dict(kwargs)
                result = await asyncio.wait_for(self._execute(args_dict), timeout=tool_timeout)
            except asyncio.TimeoutError:
                return ToolResult(
                    success=False,
                    output=f"Tool execution timed out after {tool_timeout} seconds",
                    error="Tool execution timeout"
                )
            
            # Ensure we have a ToolResult
            if not isinstance(result, ToolResult):
                # Convert other return types to ToolResult
                if isinstance(result, dict):
                    result = ToolResult(
                        success=True,
                        output=result.get('output', str(result)),
                        data=result
                    )
                else:
                    result = ToolResult(
                        success=True,
                        output=str(result),
                        data={'raw': result}
                    )
            
            # Validate ToolResult structure
            if not hasattr(result, 'success') or not hasattr(result, 'output'):
                result = ToolResult(
                    success=False,
                    output="Tool returned invalid result structure",
                    error="Invalid ToolResult structure"
                )
            
            return result
            
        except Exception as e:
            return ToolResult(
                success=False, 
                output=f"Tool execution failed: {str(e)}", 
                error=str(e)
            )

    @abstractmethod
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        Override this in concrete tools.
        This method should contain the actual tool implementation.
        
        Args:
            args: Dictionary containing tool arguments
            
        Returns:
            ToolResult with success status, output, and optional data/error
        """
        pass


# Backward compatibility alias
KodiakTool = BaseTool

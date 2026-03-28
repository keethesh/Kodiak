import asyncio
import inspect
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
    
    def __init__(self, event_manager: Any = None):
        """Initialize tool."""
        self.event_manager = event_manager
    
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
        agent_id = kwargs.get("agent_id", "unknown")
        scan_id = kwargs.get("scan_id")
        
        try:
            if self.event_manager:
                await self._emit_agent_update(agent_id, "executing", scan_id)
                await self._emit_tool_start(target, agent_id, scan_id)

            # Validate required parameters if args_schema is defined
            if self.args_schema:
                try:
                    # Validate arguments against schema
                    validated_args = self.args_schema(**kwargs)
                    # Update kwargs with validated data
                    kwargs.update(validated_args.model_dump())
                except Exception as validation_error:
                    result = ToolResult(
                        success=False,
                        output="",
                        error=f"Invalid parameters: {str(validation_error)}"
                    )
                    await self._emit_tool_complete(result, scan_id)
                    return result
            
            # Execute the actual tool logic with timeout
            try:
                from kodiak.core.config import settings
                configured_timeout = getattr(self, "execution_timeout", None)
                tool_timeout = configured_timeout if configured_timeout and configured_timeout > 0 else settings.tool_timeout
                # Convert kwargs to args dict for tool execution.
                # Keep full runtime context (agent_id/scan_id/project_id) for stateful tools.
                args_dict = dict(kwargs)
                result = await asyncio.wait_for(self._invoke_execute(args_dict), timeout=tool_timeout)
            except asyncio.TimeoutError:
                result = ToolResult(
                    success=False,
                    output="",
                    error="Tool execution timeout"
                )
                await self._emit_tool_complete(result, scan_id)
                return result
            
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
            
            await self._emit_tool_complete(result, scan_id)
            return result
            
        except Exception as e:
            result = ToolResult(
                success=False, 
                output="",
                error=str(e)
            )
            await self._emit_tool_complete(result, scan_id)
            return result

    async def _invoke_execute(self, args_dict: Dict[str, Any]) -> Any:
        """Invoke `_execute` while supporting both args-dict and kwargs legacy signatures."""
        method = self._execute
        signature = inspect.signature(method)
        params = list(signature.parameters.values())

        accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
        if accepts_kwargs:
            result = method(**args_dict)
        else:
            result = method(args_dict)

        if inspect.isawaitable(result):
            return await result
        return result

    async def _emit_tool_start(self, target: str, agent_id: str, scan_id: Optional[str]) -> None:
        if not self.event_manager:
            return
        emitter = getattr(self.event_manager, "emit_tool_start", None)
        if emitter:
            await emitter(self.name, target, agent_id, scan_id)

    async def _emit_tool_complete(self, result: ToolResult, scan_id: Optional[str]) -> None:
        if not self.event_manager:
            return
        emitter = getattr(self.event_manager, "emit_tool_complete", None)
        if emitter:
            await emitter(self.name, result, scan_id)

    async def _emit_agent_update(self, agent_id: str, message: str, scan_id: Optional[str]) -> None:
        if not self.event_manager:
            return
        emitter = getattr(self.event_manager, "emit_agent_thinking", None)
        if emitter:
            await emitter(agent_id, message, scan_id)

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

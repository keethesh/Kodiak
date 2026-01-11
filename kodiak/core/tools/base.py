import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, Type, Optional

from pydantic import BaseModel


class ToolResult(BaseModel):
    success: bool
    output: str
    data: Dict[str, Any] = {}  # Structured data (parsed JSON, etc.)
    error: str | None = None


class BaseTool(ABC):
    """
    Base class for all Kodiak tools with EventManager integration.
    """
    
    def __init__(self, event_manager=None):
        """Initialize tool with optional EventManager for event broadcasting."""
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

    async def execute(self, **kwargs) -> ToolResult:
        """
        Public interface - handles events and calls _execute.
        This is the main entry point for tool execution.
        """
        # Extract context information
        target = kwargs.get('target', 'unknown')
        agent_id = kwargs.get('agent_id', 'unknown_agent')
        scan_id = kwargs.get('scan_id')
        
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
            
            # Emit tool start event
            if self.event_manager and scan_id:
                await self.event_manager.emit_tool_start(self.name, target, agent_id, scan_id)
            
            # Execute the actual tool logic with timeout
            try:
                # Convert kwargs to args dict for tool execution
                # Only exclude internal framework parameters, keep tool parameters
                args_dict = {k: v for k, v in kwargs.items() if k not in ['agent_id', 'scan_id']}
                result = await asyncio.wait_for(self._execute(args_dict), timeout=300)  # 5 minute timeout
            except asyncio.TimeoutError:
                return ToolResult(
                    success=False,
                    output=f"Tool execution timed out after 300 seconds",
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
            
            # Emit tool complete event
            if self.event_manager and scan_id:
                await self.event_manager.emit_tool_complete(self.name, result, scan_id)
            
            return result
            
        except Exception as e:
            error_result = ToolResult(
                success=False, 
                output=f"Tool execution failed: {str(e)}", 
                error=str(e)
            )
            
            # Emit tool complete event with error
            if self.event_manager and scan_id:
                await self.event_manager.emit_tool_complete(self.name, error_result, scan_id)
            
            return error_result

    async def run(self, args: BaseModel | Dict[str, Any], context: Dict[str, Any] = None) -> ToolResult:
        """
        Legacy interface for backward compatibility.
        Includes automatic Hive Mind synchronization (Caching & Deduplication).
        """
        from kodiak.core.hive_mind import hive_mind
        from kodiak.services.websocket_manager import manager
        import json
        
        context = context or {}
        scan_id = context.get("scan_id")
        agent_id = context.get("agent_id", "unknown_agent")
        project_id = context.get("project_id")
        
        try:
            # 1. Normalize Args
            if isinstance(args, BaseModel):
                data = args.dict()
            else:
                data = args

            # Add context to data for execute method
            data.update({
                'scan_id': scan_id,
                'agent_id': agent_id,
                'target': data.get('target', 'unknown')
            })

            # 2. Generate Cache Key (Deterministic)
            # Sort keys to ensure {"a": 1, "b": 2} == {"b": 2, "a": 1}
            args_str = json.dumps({k: v for k, v in data.items() if k not in ['scan_id', 'agent_id']}, sort_keys=True)
            cmd_key = f"{self.name}:{args_str}"
            
            # Send WebSocket update: Tool started
            if scan_id:
                await manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=self.name,
                    status="started",
                    data={"args": data, "agent_id": agent_id}
                )

            # 3. Check Cache
            cached_output = await hive_mind.get_cached_result(cmd_key, scan_id)
            if cached_output:
                result = ToolResult(success=True, output=cached_output, data={"cached": True})
                
                # Send WebSocket update: Tool completed (cached)
                if scan_id:
                    await manager.send_tool_update(
                        scan_id=scan_id,
                        tool_name=self.name,
                        status="completed",
                        data={"cached": True, "result": result.dict()}
                    )
                return result

            # 4. Synchronization (The Hive Mind)
            if hive_mind.is_running(cmd_key):
                # Send WebSocket update: Waiting for hive mind
                if scan_id:
                    await manager.send_hive_mind_update(
                        command=cmd_key,
                        status="waiting",
                        agent_id=agent_id
                    )
                
                # Follower: Wait for result
                try:
                    output = await hive_mind.wait_for_result(cmd_key, agent_id, scan_id)
                    result = ToolResult(success=True, output=output, data={"cached": True, "source": "hive_wait"})
                    
                    # Send WebSocket update: Tool completed (hive mind)
                    if scan_id:
                        await manager.send_tool_update(
                            scan_id=scan_id,
                            tool_name=self.name,
                            status="completed",
                            data={"hive_mind": True, "result": result.dict()}
                        )
                    
                    return result
                except Exception as e:
                    error_result = ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")
                    
                    # Send WebSocket update: Tool failed
                    if scan_id:
                        await manager.send_tool_update(
                            scan_id=scan_id,
                            tool_name=self.name,
                            status="failed",
                            data={"error": str(e)}
                        )
                    
                    return error_result
            
            # Leader: Acquire Lock
            is_leader = await hive_mind.acquire(cmd_key, agent_id, scan_id)
            if not is_leader:
                # Send WebSocket update: Waiting for hive mind
                if scan_id:
                    await manager.send_hive_mind_update(
                        command=cmd_key,
                        status="waiting",
                        agent_id=agent_id
                    )
                
                 # Lost the race, wait
                try:
                    output = await hive_mind.wait_for_result(cmd_key, agent_id, scan_id)
                    result = ToolResult(success=True, output=output, data={"cached": True, "source": "hive_wait"})
                    
                    # Send WebSocket update: Tool completed (hive mind)
                    if scan_id:
                        await manager.send_tool_update(
                            scan_id=scan_id,
                            tool_name=self.name,
                            status="completed",
                            data={"hive_mind": True, "result": result.dict()}
                        )
                    
                    return result
                except Exception as e:
                    error_result = ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")
                    
                    # Send WebSocket update: Tool failed
                    if scan_id:
                        await manager.send_tool_update(
                            scan_id=scan_id,
                            tool_name=self.name,
                            status="failed",
                            data={"error": str(e)}
                        )
                    
                    return error_result

            # Send WebSocket update: Hive mind acquired, executing
            if scan_id:
                await manager.send_hive_mind_update(
                    command=cmd_key,
                    status="executing",
                    agent_id=agent_id
                )

            # I am the Leader - Execute using the new execute method
            try:
                result = await self.execute(**data)
                
                # Get output for hive mind
                final_output = result.output
                
                # Release Lock & Notify Followers
                await hive_mind.release(cmd_key, final_output, agent_id, scan_id)
                
                # Send WebSocket updates: Tool completed and hive mind released
                if scan_id:
                    await manager.send_tool_update(
                        scan_id=scan_id,
                        tool_name=self.name,
                        status="completed",
                        data={"result": result.dict()}
                    )
                    await manager.send_hive_mind_update(
                        command=cmd_key,
                        status="completed",
                        agent_id=agent_id
                    )
                    
                return result

            except Exception as e:
                error_msg = str(e)
                await hive_mind.release(cmd_key, f"Error: {error_msg}", agent_id, scan_id)
                
                error_result = ToolResult(success=False, output="", error=error_msg)
                
                # Send WebSocket update: Tool failed
                if scan_id:
                    await manager.send_tool_update(
                        scan_id=scan_id,
                        tool_name=self.name,
                        status="failed",
                        data={"error": error_msg}
                    )
                
                return error_result

        except Exception as e:
            error_result = ToolResult(success=False, output="", error=str(e))
            
            # Send WebSocket update: Tool failed
            if scan_id:
                await manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=self.name,
                    status="failed",
                    data={"error": str(e)}
                )
            
            return error_result

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

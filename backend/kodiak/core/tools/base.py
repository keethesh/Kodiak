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

    async def run(self, args: BaseModel | Dict[str, Any], context: Dict[str, Any] = None) -> ToolResult:
        """
        Execute the tool. Accepts either Pydantic model or Dict.
        Includes automatic Hive Mind synchronization (Caching & Deduplication).
        """
        from kodiak.core.hive_mind import hive_mind
        from kodiak.api.events import event_manager, ExternalEvent
        from kodiak.services.websocket_manager import manager
        import json
        
        context = context or {}
        scan_id = context.get("scan_id")
        agent_id = context.get("agent_id", "unknown_agent")
        
        try:
            # 1. Normalize Args
            if isinstance(args, BaseModel):
                data = args.dict()
            else:
                data = args

            # 2. Generate Cache Key (Deterministic)
            # Sort keys to ensure {"a": 1, "b": 2} == {"b": 2, "a": 1}
            args_str = json.dumps(data, sort_keys=True)
            cmd_key = f"{self.name}:{args_str}"
            
            # Send WebSocket update: Tool started
            if scan_id:
                await manager.send_tool_update(
                    scan_id=scan_id,
                    tool_name=self.name,
                    status="started",
                    data={"args": data, "agent_id": agent_id}
                )
            
            # Emit Start Event
            if scan_id:
                await event_manager.emit(ExternalEvent(
                    type="tool_start", 
                    data={"tool": self.name, "args": data}, 
                    project_id=str(context.get("project_id", ""))
                ), str(scan_id))

            # 3. Check Cache
            cached_output = await hive_mind.get_cached_result(cmd_key)
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
                    await event_manager.emit(ExternalEvent(
                        type="tool_complete", 
                        data={"tool": self.name, "result": result.dict()}, 
                        project_id=str(context.get("project_id", ""))
                    ), str(scan_id))
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
                    output = await hive_mind.wait_for_result(cmd_key)
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
            is_leader = await hive_mind.acquire(cmd_key, agent_id)
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
                    output = await hive_mind.wait_for_result(cmd_key)
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

            # I am the Leader - Execute
            try:
                result_data = await self._execute(data)
                
                # Normalize Result
                if isinstance(result_data, ToolResult):
                    # If tool returns comprehensive result, use it
                    final_output = result_data.output
                    final_result = result_data
                else:
                    # If tool returns dict/str
                    final_output = str(result_data.get("output", "")) if isinstance(result_data, dict) else str(result_data)
                    final_result = ToolResult(
                        success=True, 
                        output=final_output,
                        data=result_data if isinstance(result_data, dict) else {"raw": result_data}
                    )
                
                # Release Lock & Notify Followers
                await hive_mind.release(cmd_key, final_output)
                
                # Send WebSocket updates: Tool completed and hive mind released
                if scan_id:
                    await manager.send_tool_update(
                        scan_id=scan_id,
                        tool_name=self.name,
                        status="completed",
                        data={"result": final_result.dict()}
                    )
                    await manager.send_hive_mind_update(
                        command=cmd_key,
                        status="completed",
                        agent_id=agent_id
                    )
                
                # Emit Complete Event
                if scan_id:
                    await event_manager.emit(ExternalEvent(
                        type="tool_complete", 
                        data={"tool": self.name, "result": final_result.dict()}, 
                        project_id=str(context.get("project_id", ""))
                    ), str(scan_id))
                    
                return final_result

            except Exception as e:
                error_msg = str(e)
                await hive_mind.release(cmd_key, f"Error: {error_msg}")
                
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
    async def _execute(self, args: Dict[str, Any]) -> Any:
        pass

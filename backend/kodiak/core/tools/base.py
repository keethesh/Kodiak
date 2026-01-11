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
        Includes automatic Hive Mind synchronization (Caching & Deduplication).
        """
        from kodiak.core.hive_mind import hive_mind
        import json
        
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

            # 3. Check Cache
            cached_output = hive_mind.get_cached_result(cmd_key)
            if cached_output:
                return ToolResult(success=True, output=cached_output, data={"cached": True})

            # 4. Synchronization (The Hive Mind)
            if hive_mind.is_running(cmd_key):
                # Follower: Wait for result
                try:
                    output = await hive_mind.wait_for_result(cmd_key)
                    # Try to parse cached output as JSON if possible for 'data' field, 
                    # but for now we just return the raw string output.
                    return ToolResult(success=True, output=output, data={"cached": True, "source": "hive_wait"})
                except Exception as e:
                    return ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")
            
            # Leader: Acquire Lock
            is_leader = await hive_mind.acquire(cmd_key, "agent_placeholder") # TODO: Pass real Agent ID
            if not is_leader:
                 # Lost the race, wait
                try:
                    output = await hive_mind.wait_for_result(cmd_key)
                    return ToolResult(success=True, output=output, data={"cached": True, "source": "hive_wait"})
                except Exception as e:
                    return ToolResult(success=False, output="", error=f"Error waiting for shared command: {str(e)}")

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
                return final_result

            except Exception as e:
                error_msg = str(e)
                await hive_mind.release(cmd_key, f"Error: {error_msg}")
                return ToolResult(success=False, output="", error=error_msg)

        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    @abstractmethod
    async def _execute(self, args: Dict[str, Any]) -> Any:
        pass

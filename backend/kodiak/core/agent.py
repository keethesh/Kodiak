from typing import Any, Dict, List
from kodiak.core.config import settings

class KodiakAgent:
    """
    The Brain. 
    Decoupled from the loop. It just takes state in, and outputs actions.
    """
    def __init__(self, agent_id: str, model_name: str = settings.KODIAK_MODEL):
        self.agent_id = agent_id
        self.model_name = model_name
        
    async def think(self, context: Dict[str, Any]) -> List[Any]:
        # TODO: Implement LiteLLM call here
        pass

    async def act(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """
        Execute a tool by name with the given arguments.
        """
        from kodiak.core.tools.inventory import inventory
        
        tool = inventory.get(tool_name)
        if not tool:
            return {"error": f"Tool '{tool_name}' not found."}
            
        try:
            # Validate args against tool schema
            if tool.args_schema:
                validated_args = tool.args_schema(**args)
                result = await tool.run(validated_args)
            else:
                # Pass dict directly
                result = await tool.run(args)
            
            # Return dict representation of result
            return {
                "success": result.success,
                "output": result.output,
                "data": result.data,
                "error": result.error
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

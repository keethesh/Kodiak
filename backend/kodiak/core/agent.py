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
        
    async def think(self, history: List[Dict[str, Any]]) -> Any:
        """
        Ask the LLM what to do next given the conversation history.
        Returns the full response object from LiteLLM (which contains tool_calls).
        """
        from litellm import acompletion
        from kodiak.core.tools.inventory import inventory
        import os

        # Get all available tools
        tools = [t.to_openai_schema() for t in inventory._tools.values()]
        
        # System Prompt
        system_msg = {
            "role": "system",
            "content": (
                "You are KODIAK, an advanced autonomous penetration testing agent. "
                "Your goal is to scan, enumerate, and identify vulnerabilities in the target scope. "
                "You have access to a suite of security tools. Use them ethically and effectively. "
                "Always start with Recon (Subfinder/Httpx) before Active Scanning (Nmap/Nuclei). "
                "Use the 'terminal_execute' tool only when necessary for tasks not covered by other tools. "
                "Result format: Always call a tool or provide a final summary."
            )
        }
        
        # Prepare messages
        messages = [system_msg] + history
        
        # Call LLM
        # We use a default generic model if not specified, but settings.KODIAK_MODEL should be set.
        model = self.model_name or "gpt-3.5-turbo" 
        
        # Using OpenAI-compatible tool calling
        response = await acompletion(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        
        return response.choices[0].message

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

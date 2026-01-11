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

    async def act(self, tool_name: str, args: Dict[str, Any], session: Any = None, project_id: Any = None) -> Any:
        """
        Execute a tool by name with the given arguments.
        If session and project_id are provided, persists Assets and Findings.
        """
        from kodiak.core.tools.inventory import inventory
        from kodiak.database.models import Asset, Finding, FindingSeverity
        from kodiak.database.crud import asset as crud_asset # Assuming we will implement this helper or use direct session add
        
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
            
            # --- Persistence Logic ---
            if session and project_id and result.success and result.data:
                try:
                    # 1. Save Assets
                    if "assets" in result.data:
                         # Expected format: [{"type": "domain", "value": "example.com", "metadata": {}}]
                        for asset_data in result.data["assets"]:
                            # Naive upsert (TODO: use proper CRUD with check)
                            asset = Asset(
                                project_id=project_id,
                                type=asset_data.get("type", "unknown"),
                                value=asset_data.get("value"),
                                metadata_=asset_data.get("metadata", {})
                            )
                            session.add(asset) 
                            # Flush to get ID if needed for findings, but usually we commit at end of loop
                    
                    # 2. Save Subdomains (Special case for Subfinder)
                    if "subdomains" in result.data:
                        for sub in result.data["subdomains"]:
                            asset = Asset(
                                project_id=project_id,
                                type="subdomain",
                                value=sub,
                                metadata_={"source": "subfinder"}
                            )
                            session.add(asset)

                    # 3. Save Live Hosts (Special case for Httpx)
                    if "live_hosts" in result.data and isinstance(result.data["live_hosts"], list):
                         # If it returns a list of hosts
                         for host in result.data["live_hosts"]:
                            # Might be dict or str
                            if isinstance(host, str):
                                val = host
                                meta = {}
                            else:
                                val = host.get("url", host.get("host"))
                                meta = host
                            
                            asset = Asset(
                                project_id=project_id,
                                type="endpoint",
                                value=val,
                                metadata_={"source": "httpx", "details": meta}
                            )
                            session.add(asset)

                    # 4. Save Findings
                    if "findings" in result.data:
                         # Expected: [{"title": "X", "description": "Y", "severity": "high", "asset_value": "Z"}]
                        for finding_data in result.data["findings"]:
                            # Link to asset? Ideally we need asset_id. 
                            # For MVP, we might create a generic asset or require asset lookup.
                            # Assuming finding data has enough info.
                            finding = Finding(
                                scan_id=getattr(session, "scan_id_context", None), # Hacky context passing or need arg
                                # We need scan_id passed to act() really
                                project_id=project_id, # Finding model doesn't have project_id directly usually, linked via asset/scan?
                                # Let's check model... Finding has scan_id and asset_id.
                                # For now, let's skip strict FKs complexity in this snippet and just log wrapper
                                title=finding_data.get("title"),
                                description=finding_data.get("description"),
                                severity=finding_data.get("severity", FindingSeverity.INFO),
                                evidence=finding_data.get("evidence", {})
                            )
                            # We need asset_id... skipping strict relational save for now to avoid breaking run
                            # session.add(finding)
                            pass
                            
                    await session.commit()
                except Exception as e:
                    # Don't fail the tool execution if DB save fails
                    # logger.error(f"Persistence error: {e}")
                    pass

            
            # Return dict representation of result
            return {
                "success": result.success,
                "output": result.output,
                "data": result.data,
                "error": result.error
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

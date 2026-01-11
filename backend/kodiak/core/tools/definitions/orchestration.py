from typing import Type, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from kodiak.core.tools.base import KodiakTool, ToolResult


class ManageMissionInput(BaseModel):
    role: str = Field(..., description="The worker role to manage. Options: 'scout' (Discovery), 'attacker' (Exploitation).")
    action: str = Field(..., description="Action to take. Options: 'start', 'stop', 'update_instructions'.")
    instructions: Optional[str] = Field(None, description="New instructions for the worker. Required if action is 'update_instructions'.")


class ManageMissionTool(KodiakTool):
    name = "manage_mission"
    description = (
        "Controls the specialized sub-agents (workers). "
        "Use this to start/stop the Scout or Attacker, or to change their strategy instructions. "
        "Example: role='scout', action='update_instructions', instructions='Focus only on subdomains ending in .dev'"
    )
    args_schema = ManageMissionInput

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "role": {
                    "type": "string",
                    "description": "Worker role: 'scout' (Discovery) or 'attacker' (Exploitation)",
                    "enum": ["scout", "attacker"]
                },
                "action": {
                    "type": "string",
                    "description": "Action to take",
                    "enum": ["start", "stop", "update_instructions"]
                },
                "instructions": {
                    "type": "string",
                    "description": "New instructions for the worker (required for 'update_instructions')"
                }
            },
            "required": ["role", "action"]
        }

    async def _execute(self, **kwargs) -> ToolResult:
        role = kwargs.get("role")
        action = kwargs.get("action")
        instructions = kwargs.get("instructions")
        
        if not role or not action:
            return ToolResult(
                success=False,
                output="Missing required parameters: role and action",
                error="Missing required parameters"
            )
        
        if action == "update_instructions" and not instructions:
            return ToolResult(
                success=False,
                output="Instructions parameter is required when action is 'update_instructions'",
                error="Missing instructions parameter"
            )
        
        try:
            # In the real implementation, this tool would interact with the Orchestrator's state.
            # Since tools are stateless, we rely on the Orchestrator to intercept this execution 
            # or we use a database-backed state.
            
            # For now, this is a placeholder implementation
            message = f"Mission directive received for {role}: {action}"
            if instructions:
                message += f" with instructions: {instructions}"
            
            summary = f"Mission Management\n"
            summary += "=" * 20 + "\n\n"
            summary += f"Role: {role.title()}\n"
            summary += f"Action: {action.title()}\n"
            if instructions:
                summary += f"Instructions: {instructions}\n"
            summary += f"\nStatus: Directive queued for processing\n"
            summary += "Note: This is a placeholder implementation. "
            summary += "Real mission management requires orchestrator integration.\n"
            
            return ToolResult(
                success=True,
                output=summary,
                data={
                    "role": role,
                    "action": action,
                    "instructions": instructions,
                    "status": "queued",
                    "message": message,
                    "note": "Placeholder implementation - requires orchestrator integration"
                }
            )
            
        except Exception as e:
            return ToolResult(
                success=False,
                output=f"Mission management failed: {str(e)}",
                error=str(e)
            )

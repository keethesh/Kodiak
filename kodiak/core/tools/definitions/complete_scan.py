"""
Complete Scan Tool

Agents call this tool to signal that a scan has been completed.
This replaces the legacy magic string detection ("TASK_COMPLETE", "MISSION COMPLETE").
"""

from typing import Dict, Any
from kodiak.core.tools.base import BaseTool, ToolResult
from pydantic import BaseModel, Field


class CompleteScanArgs(BaseModel):
    """Arguments for the complete_scan tool"""
    summary: str = Field(..., description="Brief summary of what was discovered during the scan")
    findings_count: int = Field(default=0, description="Number of findings discovered")
    nodes_discovered: int = Field(default=0, description="Number of assets/nodes discovered")


class CompleteScanTool(BaseTool):
    """
    Signals scan completion with a structured summary.
    
    This tool should be called by the agent when it has finished its scan objective.
    The ScanRunner watches for this tool call to terminate the think-act loop gracefully.
    """
    
    @property
    def name(self) -> str:
        return "complete_scan"
    
    @property
    def description(self) -> str:
        return (
            "Call this tool when you have completed the security scan. "
            "Provide a summary of discoveries, findings, and nodes identified."
        )
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "Brief summary of what was discovered during the scan"
                },
                "findings_count": {
                    "type": "integer",
                    "description": "Number of security findings discovered",
                    "default": 0
                },
                "nodes_discovered": {
                    "type": "integer",
                    "description": "Number of assets/nodes discovered",
                    "default": 0
                }
            },
            "required": ["summary"]
        }
    
    # Use Pydantic validation
    args_schema = CompleteScanArgs
    
    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        """
        Mark the scan as complete and return summary data.
        
        The ScanRunner monitors for this tool's execution to terminate the agent loop.
        """
        summary = args.get("summary", "")
        findings_count = args.get("findings_count", 0)
        nodes_discovered = args.get("nodes_discovered", 0)
        
        return ToolResult(
            success=True,
            output=f"✅ Scan complete: {summary}",
            data={
                "complete": True,  # Critical flag for ScanRunner
                "summary": summary,
                "findings_count": findings_count,
                "nodes_discovered": nodes_discovered
            }
        )

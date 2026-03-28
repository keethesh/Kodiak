from typing import Dict, Any

from pydantic import BaseModel, Field

from kodiak.core.tools.base import BaseTool, ToolResult


class SaveNoteArgs(BaseModel):
    target: str = Field(..., description="Host, URL, or asset this note relates to")
    category: str = Field(..., description="recon_intel, behavioral, attack_hint, dead_end, or general")
    content: str = Field(..., description="Observation to record")


class SaveFindingArgs(BaseModel):
    target: str = Field(..., description="Affected host or URL")
    title: str = Field(..., description="Short finding title")
    severity: str = Field(..., description="critical, high, medium, low, or info")
    description: str = Field(..., description="Finding description")
    exploitation_steps: str = Field(default="", description="Optional exploitation steps")
    poc: str = Field(default="", description="Optional proof of concept")
    remediation: str = Field(default="", description="Suggested remediation")


class SaveNoteTool(BaseTool):
    args_schema = SaveNoteArgs

    @property
    def name(self) -> str:
        return "save_note"

    @property
    def description(self) -> str:
        return "Persist a note or piece of scan intelligence for later review."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Host, URL, or asset this note relates to"},
                "category": {
                    "type": "string",
                    "description": "Note category",
                    "enum": ["recon_intel", "behavioral", "attack_hint", "dead_end", "general"],
                },
                "content": {"type": "string", "description": "Observation to record"},
            },
            "required": ["target", "category", "content"],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        target = args["target"]
        category = args["category"]
        content = args["content"]
        return ToolResult(
            success=True,
            output=f"Saved note [{category}] for {target}: {content}",
            data={
                "saved": True,
                "target": target,
                "category": category,
                "content": content,
            },
        )


class SaveFindingTool(BaseTool):
    args_schema = SaveFindingArgs

    @property
    def name(self) -> str:
        return "save_finding"

    @property
    def description(self) -> str:
        return "Persist a structured security finding for later review."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Affected host or URL"},
                "title": {"type": "string", "description": "Short finding title"},
                "severity": {
                    "type": "string",
                    "description": "Finding severity",
                    "enum": ["critical", "high", "medium", "low", "info"],
                },
                "description": {"type": "string", "description": "Finding description"},
                "exploitation_steps": {"type": "string", "description": "Optional exploitation steps"},
                "poc": {"type": "string", "description": "Optional proof of concept"},
                "remediation": {"type": "string", "description": "Suggested remediation"},
            },
            "required": ["target", "title", "severity", "description"],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        severity = str(args["severity"]).upper()
        return ToolResult(
            success=True,
            output=f"Saved finding [{severity}] {args['title']} on {args['target']}",
            data={
                "saved": True,
                "target": args["target"],
                "title": args["title"],
                "severity": args["severity"],
                "description": args["description"],
                "exploitation_steps": args.get("exploitation_steps", ""),
                "poc": args.get("poc", ""),
                "remediation": args.get("remediation", ""),
            },
        )

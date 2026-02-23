from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from kodiak.core.blackboard import BlackboardService
from kodiak.core.tools.base import KodiakTool, ToolResult
from kodiak.database import crud
from kodiak.database.engine import get_session


def _parse_uuid(value: Any) -> Optional[UUID]:
    try:
        text = str(value or "").strip()
        if not text:
            return None
        return UUID(text)
    except Exception:
        return None


class BlackboardQueryFactsArgs(BaseModel):
    entity_type: Optional[str] = Field(default=None, description="Optional entity type filter")
    keyword: Optional[str] = Field(default=None, description="Keyword filter for entity key/payload")
    target: Optional[str] = Field(default=None, description="Target-focused filter")
    limit: int = Field(default=10, description="Maximum facts to return")


class BlackboardQueryFactsTool(KodiakTool):
    name = "blackboard_query_facts"
    description = "Query canonical blackboard facts for the active scan."
    args_schema = BlackboardQueryFactsArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": "Optional entity type filter"},
                "keyword": {"type": "string", "description": "Keyword filter for facts"},
                "target": {"type": "string", "description": "Target filter"},
                "limit": {"type": "integer", "description": "Max facts to return", "default": 10},
            },
            "required": [],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(success=False, output="blackboard_query_facts requires active scan_id", error="missing scan_id")
        role = str(args.get("role") or "generalist").strip().lower()
        service = BlackboardService()
        async for session in get_session():
            facts = await service.query_facts(
                session=session,
                scan_id=scan_id,
                role=role,
                entity_type=args.get("entity_type"),
                keyword=args.get("keyword"),
                target=args.get("target"),
                limit=max(1, int(args.get("limit", 10))),
            )
            return ToolResult(
                success=True,
                output=f"Blackboard facts returned: {len(facts)}",
                data={"facts": facts, "total": len(facts)},
            )
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


class BlackboardQueryEdgesArgs(BaseModel):
    entity_key: Optional[str] = Field(default=None, description="Optional source/destination key filter")
    relation: Optional[str] = Field(default=None, description="Optional relation filter")
    limit: int = Field(default=20, description="Maximum edges to return")


class BlackboardQueryEdgesTool(KodiakTool):
    name = "blackboard_query_edges"
    description = "Query blackboard attack-path edges for the active scan."
    args_schema = BlackboardQueryEdgesArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_key": {"type": "string", "description": "Filter by source/destination entity key"},
                "relation": {"type": "string", "description": "Filter by relation"},
                "limit": {"type": "integer", "description": "Max edges to return", "default": 20},
            },
            "required": [],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(success=False, output="blackboard_query_edges requires active scan_id", error="missing scan_id")
        service = BlackboardService()
        async for session in get_session():
            rows = await service.query_edges(
                session=session,
                scan_id=scan_id,
                entity_key=args.get("entity_key"),
                relation=args.get("relation"),
                limit=max(1, int(args.get("limit", 20))),
            )
            return ToolResult(
                success=True,
                output=f"Blackboard edges returned: {len(rows)}",
                data={"edges": rows, "total": len(rows)},
            )
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


class BlackboardQueryEventsArgs(BaseModel):
    entity_type: Optional[str] = Field(default=None, description="Optional entity type filter")
    entity_key: Optional[str] = Field(default=None, description="Optional entity key filter")
    limit: int = Field(default=20, description="Maximum events to return")


class BlackboardQueryEventsTool(KodiakTool):
    name = "blackboard_query_events"
    description = "Query raw blackboard events for provenance and auditing."
    args_schema = BlackboardQueryEventsArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": "Entity type filter"},
                "entity_key": {"type": "string", "description": "Entity key filter"},
                "limit": {"type": "integer", "description": "Max events to return", "default": 20},
            },
            "required": [],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(success=False, output="blackboard_query_events requires active scan_id", error="missing scan_id")
        service = BlackboardService()
        async for session in get_session():
            rows = await service.query_events(
                session=session,
                scan_id=scan_id,
                entity_type=args.get("entity_type"),
                entity_key=args.get("entity_key"),
                limit=max(1, int(args.get("limit", 20))),
            )
            return ToolResult(
                success=True,
                output=f"Blackboard events returned: {len(rows)}",
                data={"events": rows, "total": len(rows)},
            )
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


class BlackboardQueryVerificationQueueArgs(BaseModel):
    limit: int = Field(default=10, description="Maximum pending verification items to return")


class BlackboardQueryVerificationQueueTool(KodiakTool):
    name = "blackboard_query_verification_queue"
    description = "List pending blackboard verification/conflict queue entries."
    args_schema = BlackboardQueryVerificationQueueArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max queue items to return", "default": 10},
            },
            "required": [],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(
                success=False,
                output="blackboard_query_verification_queue requires active scan_id",
                error="missing scan_id",
            )
        service = BlackboardService()
        async for session in get_session():
            rows = await service.query_verification_queue(
                session=session,
                scan_id=scan_id,
                limit=max(1, int(args.get("limit", 10))),
            )
            return ToolResult(
                success=True,
                output=f"Verification queue items returned: {len(rows)}",
                data={"items": rows, "total": len(rows)},
            )
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


class BlackboardPublishFactArgs(BaseModel):
    entity_type: str = Field(..., description="Entity type for the fact")
    entity_key: str = Field(..., description="Stable entity key")
    payload: Dict[str, Any] = Field(..., description="Structured fact payload (must include source_tool/source)")
    confidence: str = Field(default="medium", description="low|medium|high confidence")
    status: str = Field(default="observed", description="observed|verified|conflicted")


class BlackboardPublishFactTool(KodiakTool):
    name = "blackboard_publish_fact"
    description = "Publish a manual blackboard fact from analyzed tool evidence."
    args_schema = BlackboardPublishFactArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "entity_type": {"type": "string", "description": "Fact entity type"},
                "entity_key": {"type": "string", "description": "Stable entity key"},
                "payload": {"type": "object", "description": "Structured payload with source_tool/source"},
                "confidence": {"type": "string", "description": "low|medium|high", "default": "medium"},
                "status": {"type": "string", "description": "observed|verified|conflicted", "default": "observed"},
            },
            "required": ["entity_type", "entity_key", "payload"],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(success=False, output="blackboard_publish_fact requires active scan_id", error="missing scan_id")
        project_id = _parse_uuid(args.get("project_id"))
        service = BlackboardService()
        async for session in get_session():
            if not project_id:
                scan = await crud.scan_job.get(session, scan_id)
                if not scan:
                    return ToolResult(success=False, output="Scan not found for provided scan_id", error="scan_not_found")
                project_id = scan.project_id
            try:
                response = await service.publish_fact(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    agent_id=str(args.get("agent_id") or "unknown"),
                    entity_type=str(args.get("entity_type")),
                    entity_key=str(args.get("entity_key")),
                    payload=args.get("payload") or {},
                    confidence=str(args.get("confidence") or "medium"),
                    status=str(args.get("status") or "observed"),
                )
            except Exception as e:
                return ToolResult(success=False, output=f"Failed to publish blackboard fact: {e}", error=str(e))
            return ToolResult(success=True, output="Blackboard fact published", data={"result": response})
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


class BlackboardPublishEdgeArgs(BaseModel):
    src_type: str = Field(..., description="Source entity type")
    src_key: str = Field(..., description="Source entity key")
    relation: str = Field(..., description="Edge relation label")
    dst_type: str = Field(..., description="Destination entity type")
    dst_key: str = Field(..., description="Destination entity key")
    confidence: str = Field(default="medium", description="low|medium|high confidence")
    status: str = Field(default="observed", description="observed|verified|conflicted")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Optional extra payload; include source_tool/source")


class BlackboardPublishEdgeTool(KodiakTool):
    name = "blackboard_publish_edge"
    description = "Publish a manual attack-path edge to the blackboard graph."
    args_schema = BlackboardPublishEdgeArgs

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "src_type": {"type": "string", "description": "Source entity type"},
                "src_key": {"type": "string", "description": "Source entity key"},
                "relation": {"type": "string", "description": "Edge relation"},
                "dst_type": {"type": "string", "description": "Destination entity type"},
                "dst_key": {"type": "string", "description": "Destination entity key"},
                "confidence": {"type": "string", "description": "low|medium|high", "default": "medium"},
                "status": {"type": "string", "description": "observed|verified|conflicted", "default": "observed"},
                "payload": {"type": "object", "description": "Optional extra edge payload"},
            },
            "required": ["src_type", "src_key", "relation", "dst_type", "dst_key"],
        }

    async def _execute(self, args: Dict[str, Any]) -> ToolResult:
        scan_id = _parse_uuid(args.get("scan_id"))
        if not scan_id:
            return ToolResult(success=False, output="blackboard_publish_edge requires active scan_id", error="missing scan_id")
        project_id = _parse_uuid(args.get("project_id"))
        service = BlackboardService()
        async for session in get_session():
            if not project_id:
                scan = await crud.scan_job.get(session, scan_id)
                if not scan:
                    return ToolResult(success=False, output="Scan not found for provided scan_id", error="scan_not_found")
                project_id = scan.project_id
            payload = args.get("payload") or {}
            if "source_tool" not in payload and "source" not in payload:
                payload = {**payload, "source_tool": str(args.get("source_tool") or "manual")}
            try:
                response = await service.publish_edge(
                    session=session,
                    project_id=project_id,
                    scan_id=scan_id,
                    agent_id=str(args.get("agent_id") or "unknown"),
                    src_type=str(args.get("src_type")),
                    src_key=str(args.get("src_key")),
                    relation=str(args.get("relation")),
                    dst_type=str(args.get("dst_type")),
                    dst_key=str(args.get("dst_key")),
                    confidence=str(args.get("confidence") or "medium"),
                    status=str(args.get("status") or "observed"),
                    payload=payload,
                )
            except Exception as e:
                return ToolResult(success=False, output=f"Failed to publish blackboard edge: {e}", error=str(e))
            return ToolResult(success=True, output="Blackboard edge published", data={"result": response})
        return ToolResult(success=False, output="Failed to open database session", error="session_unavailable")


from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from uuid import UUID, uuid4
from enum import StrEnum

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel, Relationship, Column, JSON

if TYPE_CHECKING:
    from sqlalchemy.sql.schema import ForeignKey


# --- Enums & Helpers ---

class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class NoteCategory(StrEnum):
    RECON_INTEL = "recon_intel"
    BEHAVIORAL = "behavioral"
    ATTACK_HINT = "attack_hint"
    DEAD_END = "dead_end"
    GENERAL = "general"


class ScanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class VerificationQueueStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class WorkUnitStatus(StrEnum):
    PENDING = "pending"
    CLAIMED = "claimed"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DirectiveType(StrEnum):
    RATE_LIMIT = "rate_limit"
    SKIP_TARGET = "skip_target"
    PRIORITIZE_TARGET = "prioritize_target"
    ATTACK_HINT = "attack_hint"
    ESCALATE = "escalate"
    PHASE_ADVANCE = "phase_advance"


class ObservationType(StrEnum):
    LIVE_HTTP = "live_http"
    TECHNOLOGY = "technology"
    PARAMETERIZED_URL = "parameterized_url"
    LOGIN_SURFACE = "login_surface"
    ADMIN_SURFACE = "admin_surface"
    API_SURFACE = "api_surface"
    TLS_NAME = "tls_name"
    NETWORK_SERVICE = "network_service"
    ORIGIN_CANDIDATE = "origin_candidate"


class CapabilityType(StrEnum):
    WEB_SURFACE = "web_surface"
    INPUT_SURFACE = "input_surface"
    AUTH_SURFACE = "auth_surface"
    ADMIN_SURFACE = "admin_surface"
    API_SURFACE = "api_surface"
    TECH_STACK = "tech_stack"
    NETWORK_SERVICE = "network_service"
    ORIGIN_REACHABLE = "origin_reachable"


class HypothesisType(StrEnum):
    INJECTION_FOLLOWUP = "injection_followup"
    AUTH_FOLLOWUP = "auth_followup"
    ADMIN_FOLLOWUP = "admin_followup"
    API_LOGIC_FOLLOWUP = "api_logic_followup"
    TECH_FOLLOWUP = "tech_followup"
    HIDDEN_HOST_FOLLOWUP = "hidden_host_followup"
    LEGACY_STACK_RCE_FOLLOWUP = "legacy_stack_rce_followup"


class HypothesisStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ScanEventType(StrEnum):
    WORK_UNIT_QUEUED = "work_unit_queued"
    WORK_UNIT_CLAIMED = "work_unit_claimed"
    WORK_UNIT_COMPLETED = "work_unit_completed"
    WORK_UNIT_FAILED = "work_unit_failed"
    DIRECTIVE_ADDED = "directive_added"
    OBSERVATION_ADDED = "observation_added"
    CAPABILITY_ADDED = "capability_added"
    HYPOTHESIS_ADDED = "hypothesis_added"
    HYPOTHESIS_UPDATED = "hypothesis_updated"
    FINDING_ADDED = "finding_added"
    NOTE_ADDED = "note_added"
    ATTEMPT_RECORDED = "attempt_recorded"
    COMPONENT_DEGRADED = "component_degraded"
    COMPONENT_RECOVERED = "component_recovered"
    COMPONENT_PAUSED = "component_paused"


def utc_now():
    return datetime.now(timezone.utc)


# --- Core Models ---

class Project(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)
    
    scans: List["ScanJob"] = Relationship(back_populates="project")
    nodes: List["Node"] = Relationship(back_populates="project")
    tasks: List["Task"] = Relationship(back_populates="project")
    attempts: List["Attempt"] = Relationship(back_populates="project")
    insights: List["InsightMemory"] = Relationship(back_populates="project")
    verification_items: List["VerificationQueue"] = Relationship(back_populates="project")
    notes: List["EngagementNote"] = Relationship(back_populates="project")
    findings: List["Finding"] = Relationship(back_populates="project")


class ScanJob(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    name: str
    status: ScanStatus = Field(default=ScanStatus.PENDING)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    
    config: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    project: Project = Relationship(back_populates="scans")
    logs: List["AgentLog"] = Relationship(back_populates="scan")


class Node(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    label: str # e.g. "Asset"
    type: str  # domain, ip, url, etc.
    name: str = Field(index=True)
    
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    scanned: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utc_now)
    
    project: Project = Relationship(back_populates="nodes")
    findings: List["Finding"] = Relationship(back_populates="node")


class Edge(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(foreign_key="node.id")
    target_id: UUID = Field(foreign_key="node.id")
    relation: str = Field(index=True)
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)


class Attempt(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = None
    
    tool: str
    target: str
    status: str
    reason: Optional[str] = None
    
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    
    project: Project = Relationship(back_populates="attempts")


class InsightMemory(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    tool: str
    target: str
    fingerprint: str = Field(index=True)
    status: str
    insight: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=utc_now)

    project: Project = Relationship(back_populates="insights")


class VerificationQueue(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    entity_type: str = Field(index=True)
    entity_key: str = Field(index=True)
    reason: str
    requested_by_agent: str = Field(index=True)
    status: VerificationQueueStatus = Field(default=VerificationQueueStatus.PENDING, index=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)
    resolved_at: Optional[datetime] = None

    project: Project = Relationship(back_populates="verification_items")


class Task(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    name: str
    directive: str
    status: str
    assigned_agent_id: Optional[str] = None
    result: Optional[str] = None
    
    created_at: datetime = Field(default_factory=utc_now)
    project: Project = Relationship(back_populates="tasks")


class Finding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    node_id: Optional[UUID] = Field(default=None, foreign_key="node.id")
    project_id: Optional[UUID] = Field(default=None, foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")
    
    title: str
    description: str
    severity: FindingSeverity = Field(default=FindingSeverity.INFO)
    target: Optional[str] = Field(default=None, index=True)
    vector: Optional[str] = None
    proof: Optional[str] = None
    tool: Optional[str] = None
    vulnerability_type: Optional[str] = None
    exploitation_steps: Optional[str] = None
    impact: Optional[str] = None
    poc: Optional[str] = None
    remediation: Optional[str] = None
    raw_evidence: Optional[str] = None
    
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    
    node: Optional[Node] = Relationship(back_populates="findings")
    project: Optional[Project] = Relationship(back_populates="findings")


class AgentLog(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id")
    
    agent_id: str
    message: str
    level: str = Field(default="INFO")
    timestamp: datetime = Field(default_factory=utc_now)
    
    scan: ScanJob = Relationship(back_populates="logs")


class EngagementNote(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    category: NoteCategory = Field(default=NoteCategory.GENERAL, index=True)
    target: str = Field(default="*", index=True)
    content: str

    created_at: datetime = Field(default_factory=utc_now)

    project: Project = Relationship(back_populates="notes")


class WorkUnit(SQLModel, table=True):
    """A discrete unit of work for the multi-agent pipeline."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)
    project_id: UUID = Field(foreign_key="project.id")

    technique: str = Field(index=True)  # e.g. "nuclei_drupal", "ffuf_dirbrute"
    target: str = Field(default="", index=True)  # Canonical single scope for this work unit
    target_kind: str = Field(default="scope", index=True)  # host, origin, url, or scope
    tool_family: str = Field(default="", index=True)
    scope_key: str = Field(default="", index=True)
    targets_json: str  # JSON array of target hostnames/URLs
    targets_hash: str = Field(index=True)  # SHA256 of sorted targets for dedup
    context: str = ""  # Extra context for the worker (e.g. "Laravel detected")
    command_template: str = ""  # Shell command template with {target} placeholder
    priority: int = Field(default=50)  # 0=highest, 100=lowest
    phase: str = Field(default="recon")  # recon, enumeration, vuln_scan, exploitation

    status: WorkUnitStatus = Field(default=WorkUnitStatus.PENDING, index=True)
    claimed_by: Optional[str] = None  # Worker ID that claimed this unit
    result_stdout: Optional[str] = None  # Raw stdout from execution
    result_stderr: Optional[str] = None  # Raw stderr from execution
    exit_code: Optional[int] = None
    analyzed: bool = Field(default=False, index=True)  # Has the Analyst reviewed this?

    created_at: datetime = Field(default_factory=utc_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    __table_args__ = (
        UniqueConstraint("scan_id", "technique", "targets_hash", name="uq_work_unit_dedup"),
    )


class Directive(SQLModel, table=True):
    """Analyst-to-Planner communication: strategic instructions."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)

    type: DirectiveType = Field(index=True)
    content: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    consumed: bool = Field(default=False, index=True)

    created_at: datetime = Field(default_factory=utc_now)


class Observation(SQLModel, table=True):
    """Typed facts extracted from tool output or analysis."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)
    project_id: UUID = Field(foreign_key="project.id")

    type: ObservationType = Field(index=True)
    target: str = Field(index=True)
    key: str = Field(index=True)
    value: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("scan_id", "type", "target", "key", name="uq_observation_dedup"),
    )


class Capability(SQLModel, table=True):
    """Reusable offensive assets or attack surfaces inferred from observations."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)
    project_id: UUID = Field(foreign_key="project.id")

    type: CapabilityType = Field(index=True)
    target: str = Field(index=True)
    key: str = Field(index=True)
    details: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("scan_id", "type", "target", "key", name="uq_capability_dedup"),
    )


class Hypothesis(SQLModel, table=True):
    """Concrete follow-up ideas generated from evidence and capabilities."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)
    project_id: UUID = Field(foreign_key="project.id")

    type: HypothesisType = Field(index=True)
    target: str = Field(index=True)
    key: str = Field(index=True)
    rationale: str
    confidence: float = Field(default=0.5)
    evidence: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    status: HypothesisStatus = Field(default=HypothesisStatus.PENDING, index=True)

    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        UniqueConstraint("scan_id", "type", "target", "key", name="uq_hypothesis_dedup"),
    )


class ScanEvent(SQLModel, table=True):
    """Append-only event log for scan execution and reasoning state."""
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id", index=True)
    project_id: UUID = Field(foreign_key="project.id")

    type: ScanEventType = Field(index=True)
    payload: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    entity_type: Optional[str] = Field(default=None, index=True)
    entity_id: Optional[str] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)

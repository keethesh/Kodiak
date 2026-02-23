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


class ScanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class ConfidenceLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"


class VerificationQueueStatus(StrEnum):
    PENDING = "pending"
    RESOLVED = "resolved"
    IGNORED = "ignored"


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
    blackboard_events: List["BlackboardEvent"] = Relationship(back_populates="project")
    blackboard_facts: List["BlackboardFact"] = Relationship(back_populates="project")
    blackboard_edges: List["BlackboardEdge"] = Relationship(back_populates="project")
    verification_items: List["VerificationQueue"] = Relationship(back_populates="project")


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


class BlackboardEvent(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    agent_id: str = Field(index=True)
    event_type: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_key: str = Field(index=True)
    payload: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM)
    status: str = Field(default="observed", index=True)

    created_at: datetime = Field(default_factory=utc_now, index=True)

    project: Project = Relationship(back_populates="blackboard_events")


class BlackboardFact(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("scan_id", "entity_type", "entity_key", name="uq_blackboard_fact_scan_entity"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    entity_type: str = Field(index=True)
    entity_key: str = Field(index=True)
    canonical: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM)
    verification_status: VerificationStatus = Field(default=VerificationStatus.UNVERIFIED, index=True)
    last_event_id: Optional[UUID] = Field(default=None, foreign_key="blackboardevent.id")

    updated_at: datetime = Field(default_factory=utc_now, index=True)

    project: Project = Relationship(back_populates="blackboard_facts")


class BlackboardEdge(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "scan_id",
            "src_type",
            "src_key",
            "relation",
            "dst_type",
            "dst_key",
            name="uq_blackboard_edge_scan_rel",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")

    src_type: str = Field(index=True)
    src_key: str = Field(index=True)
    relation: str = Field(index=True)
    dst_type: str = Field(index=True)
    dst_key: str = Field(index=True)
    confidence: ConfidenceLevel = Field(default=ConfidenceLevel.MEDIUM)
    last_event_id: Optional[UUID] = Field(default=None, foreign_key="blackboardevent.id")

    updated_at: datetime = Field(default_factory=utc_now, index=True)

    project: Project = Relationship(back_populates="blackboard_edges")


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
    node_id: UUID = Field(foreign_key="node.id")
    
    title: str
    description: str
    severity: FindingSeverity = Field(default=FindingSeverity.INFO)
    vector: Optional[str] = None
    proof: Optional[str] = None
    
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=utc_now)
    
    node: Node = Relationship(back_populates="findings")


class AgentLog(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id")
    
    agent_id: str
    message: str
    level: str = Field(default="INFO")
    timestamp: datetime = Field(default_factory=utc_now)
    
    scan: ScanJob = Relationship(back_populates="logs")

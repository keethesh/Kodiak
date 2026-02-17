from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from uuid import UUID, uuid4
from enum import StrEnum

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

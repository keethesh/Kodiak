from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, Relationship, Column, JSON


# --- Enums & Helpers ---
# Keeping it simple with strings for now to avoid alembic enum complexities early on
class FindingSeverity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ScanStatus:
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# --- Core Models ---

class Project(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    scans: List["ScanJob"] = Relationship(back_populates="project")
    scans: List["ScanJob"] = Relationship(back_populates="project")
    nodes: List["Node"] = Relationship(back_populates="project")


class ScanJob(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    name: str
    status: str = Field(default=ScanStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Configuration for this scan (scope, agent directives, etc.)
    config: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    project: Project = Relationship(back_populates="scans")
    logs: List["AgentLog"] = Relationship(back_populates="scan")


class Node(SQLModel, table=True):
    """
    The fundamental unit of the Knowledge Graph.
    Replaces 'Asset' to be more generic.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    label: str # e.g. "Asset", "User", "Technology"
    type: str  # domain, ip, url, service, file, technology
    name: str = Field(index=True) # example.com, 80/tcp, admin 
    
    # Flexible metadata (e.g., {'version': '1.2', 'headers': {...}})
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    # Workflow Status
    scanned: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    project: Project = Relationship(back_populates="nodes")
    findings: List["Finding"] = Relationship(back_populates="node")


class Edge(SQLModel, table=True):
    """
    Relationships between Nodes.
    e.g. Domain --resolves_to--> IP
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    source_id: UUID = Field(foreign_key="node.id")
    target_id: UUID = Field(foreign_key="node.id")
    
    # "resolves_to", "runs_on", "has_vulnerability"
    relation: str = Field(index=True)
    
    # Metadata for the edge (e.g. "first_seen", "confidence")
    properties: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Attempt(SQLModel, table=True):
    """
    Operational Memory.
    Prevents the agent from trying the same tool on the same target infinitely.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    # What was attempted?
    tool: str = Field(index=True) # "sqlmap"
    target: str = Field(index=True) # "http://example.com/id=1"
    
    # Outcome
    status: str # "success", "failure", "skipped"
    reason: Optional[str] = None # "Connection timeout"
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Task(SQLModel, table=True):
    """
    Directives for Agents.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    name: str # "Scan Port 80"
    status: str = Field(default="pending") # pending, running, completed, failed
    
    assigned_agent_id: str # "Scout_1"
    parent_task_id: Optional[UUID] = Field(foreign_key="task.id", default=None)
    
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Finding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    node_id: UUID = Field(foreign_key="node.id")
    # scan_id is optional as findings might be general project knowledge
    scan_id: Optional[UUID] = Field(default=None, foreign_key="scanjob.id")
    
    title: str
    description: str
    severity: str = Field(default=FindingSeverity.INFO)
    cve_id: Optional[str] = None
    
    # Evidence: screenshot paths, raw request/response, etc.
    evidence: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    remediation: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    node: Node = Relationship(back_populates="findings")


class AgentLog(SQLModel, table=True):
    """
    The 'Hive Mind' audit trail. Every thought and action is recorded here.
    """
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    scan_id: UUID = Field(foreign_key="scanjob.id")
    agent_name: str
    
    step: str # "thinking", "executing_tool", "processing_result"
    content: str # The thought or tool output
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    scan: ScanJob = Relationship(back_populates="logs")

# --- CVE Knowledge Base ---

class VulnerabilityDefinition(SQLModel, table=True):
    """
    Local copy of NVD data for quick lookup.
    """
    cve_id: str = Field(primary_key=True)
    description: str
    cvss_score: Optional[float] = None
    affected_products: List[str] = Field(default=[], sa_column=Column(JSON)) 
    # We will use Postgres Full Text Search on this field later

class CommandCache(SQLModel, table=True):
    """
    Cache for tool outputs to prevent redundant execution.
    Part of "The Hive Mind".
    """
    command_hash: str = Field(primary_key=True) # e.g. "nmap:192.168.1.1" (hashed or normalized)
    tool_name: str = Field(index=True)
    args_json: str # Normalized JSON of args
    
    output: str # The raw or compressed output
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

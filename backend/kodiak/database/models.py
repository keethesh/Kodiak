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
    assets: List["Asset"] = Relationship(back_populates="project")


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


class Asset(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    project_id: UUID = Field(foreign_key="project.id")
    
    type: str  # domain, ip, url, service, file
    value: str = Field(index=True) # example.com, 192.168.1.1
    metadata_: Dict[str, Any] = Field(default={}, sa_column=Column("metadata", JSON))
    
    # Workflow Status
    scanned: bool = Field(default=False)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    project: Project = Relationship(back_populates="assets")
    findings: List["Finding"] = Relationship(back_populates="asset")


class Finding(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    asset_id: UUID = Field(foreign_key="asset.id")
    scan_id: UUID = Field(foreign_key="scanjob.id")
    
    title: str
    description: str
    severity: str = Field(default=FindingSeverity.INFO)
    cve_id: Optional[str] = None
    
    # Evidence: screenshot paths, raw request/response, etc.
    evidence: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    remediation: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    asset: Asset = Relationship(back_populates="findings")


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

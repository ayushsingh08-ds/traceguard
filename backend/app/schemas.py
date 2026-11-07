import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import settings
from app.models import IncidentStatus, SeverityLevel


class IncidentEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    fingerprint: str = Field(..., min_length=64, max_length=64)
    title: str = Field(..., min_length=3, max_length=255)
    service: str = Field(..., min_length=2, max_length=100)
    environment: str = Field(default="production", min_length=2, max_length=50)
    severity: SeverityLevel
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("fingerprint")
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        if not all(c in "0123456789abcdefABCDEF" for c in v):
            raise ValueError("Fingerprint must be a valid hexadecimal SHA-256 string")
        return v.lower()

    @staticmethod
    def compute_fingerprint(service: str, title: str, environment: str = "production") -> str:
        # Normalization via lowercase stripping guarantees alert identity invariance
        # across heterogeneous monitoring agents emitting minor whitespace variations.
        normalized = f"{service.strip().lower()}:{title.strip().lower()}:{environment.strip().lower()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def calculate_sla_deadline(severity: SeverityLevel, base_time: Optional[datetime] = None) -> datetime:
        ref_time = base_time or datetime.now(timezone.utc)
        if severity == SeverityLevel.SEV1:
            return ref_time + timedelta(minutes=settings.SLA_MINUTES_SEV1)
        if severity == SeverityLevel.SEV2:
            return ref_time + timedelta(minutes=settings.SLA_MINUTES_SEV2)
        return ref_time + timedelta(minutes=settings.SLA_MINUTES_SEV3)


class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    service: str = Field(..., min_length=2, max_length=100)
    environment: str = Field(default="production", min_length=2, max_length=50)
    severity: SeverityLevel
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class IncidentUpdateStatus(BaseModel):
    status: IncidentStatus
    actor: str = Field(..., min_length=2, max_length=100)
    note: Optional[str] = None


class IncidentAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    action: str
    actor: str
    previous_status: Optional[str]
    new_status: Optional[str]
    note: Optional[str]
    created_at: datetime


class ToolExecutionRecord(BaseModel):
    tool_name: str
    parameters: Dict[str, Any]
    result: Dict[str, Any]
    execution_time_ms: int


class RunbookCitation(BaseModel):
    runbook_id: str
    chunk_index: int
    title: str
    similarity_score: float


class RootCauseReport(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hypothesis: str = Field(..., min_length=10)
    supporting_evidence: List[str] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    recommended_runbook_steps: List[str] = Field(..., min_length=1)
    tools_executed: List[ToolExecutionRecord] = Field(default_factory=list)
    retrieved_chunks: List[RunbookCitation] = Field(default_factory=list)
    model_name: str = Field(default="gemini-1.5-pro")
    tokens_used: int = Field(default=0, ge=0)
    execution_time_ms: int = Field(default=0, ge=0)


class RCAReportResponse(RootCauseReport):
    id: UUID
    incident_id: UUID
    created_at: datetime


class IncidentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fingerprint: str
    title: str
    service: str
    environment: str
    severity: SeverityLevel
    status: IncidentStatus
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    sla_deadline_at: datetime
    acknowledged_at: Optional[datetime]
    resolved_at: Optional[datetime]
    acknowledged_by: Optional[str]
    resolved_by: Optional[str]


class IncidentDetailResponse(IncidentListItem):
    raw_payload: Dict[str, Any]
    audit_logs: List[IncidentAuditLogResponse] = Field(default_factory=list)
    rca_reports: List[RCAReportResponse] = Field(default_factory=list)


class RunbookChunkCreate(BaseModel):
    runbook_id: str = Field(..., min_length=2, max_length=100)
    title: str = Field(..., min_length=3, max_length=255)
    service: str = Field(..., min_length=2, max_length=100)
    chunk_index: int = Field(..., ge=0)
    content: str = Field(..., min_length=10)
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class RunbookChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    runbook_id: str
    title: str
    service: str
    chunk_index: int
    content: str
    created_at: datetime


class RunbookSearchResult(BaseModel):
    id: UUID
    runbook_id: str
    title: str
    service: str
    chunk_index: int
    content: str
    similarity: float


class SLAMetricsResponse(BaseModel):
    mean_time_to_acknowledge_seconds: float
    mean_time_to_resolve_seconds: float
    active_sev1_breach_count: int
    active_sev2_breach_count: int
    active_sev3_breach_count: int
    total_active_incidents: int
    sla_compliance_rate: float


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    role: Optional[str] = None
    exp: Optional[int] = None


class UserLogin(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    role: str
    created_at: datetime


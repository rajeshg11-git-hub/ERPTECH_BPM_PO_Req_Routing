from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict


class RequisitionStatus(str, Enum):
    PENDING = "PENDING"
    PENDING_LINE_MANAGER = "PENDING_LINE_MANAGER"
    PENDING_DEPT_HEAD = "PENDING_DEPT_HEAD"
    PENDING_FINANCE_VP = "PENDING_FINANCE_VP"
    PENDING_PROCUREMENT_DIR = "PENDING_PROCUREMENT_DIR"
    PENDING_SECURITY_OFFICER = "PENDING_SECURITY_OFFICER"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ESCALATED = "ESCALATED"
    ESCALATED_TO_DELEGATE = "ESCALATED_TO_DELEGATE"


class ItemCategory(str, Enum):
    HARDWARE = "Hardware"
    SOFTWARE = "Software"
    CONSULTING = "Consulting"
    OFFICE_SUPPLIES = "Office Supplies"
    MARKETING = "Marketing"
    OTHER = "Other"


class ApprovalAuditEntry(BaseModel):
    actor: str = Field(..., description="ID or name of user or agent taking action")
    previous_status: RequisitionStatus
    new_status: RequisitionStatus
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    comments: Optional[str] = None


class PolicyEvaluationResult(BaseModel):
    is_compliant: bool
    recommended_status: RequisitionStatus
    required_approvers: List[str]
    auto_approval_eligible: bool
    policy_notes: List[str]
    risk_level: str


class BPMRoutingDecision(BaseModel):

    requisition_id: str
    amount: float
    item_category: str
    rule_applied: str
    current_step: str
    current_approver: str
    required_approvers: List[str]
    next_status: RequisitionStatus
    reasoning: str
    rag_policies_retrieved: List[str] = Field(default_factory=list)
    compliance_flags: List[str] = Field(default_factory=list)
    additional_approvers: List[str] = Field(default_factory=list)
    diagram_url: Optional[str] = None
    landed_cost_summary: Optional[str] = None


class RequisitionCreate(BaseModel):
    requester_name: str = Field(..., json_schema_extra={"example": "Jane Doe"})
    cost_center: str = Field(..., json_schema_extra={"example": "CC-1024"})
    amount: float = Field(..., gt=0, json_schema_extra={"example": 4500.00})
    currency: str = Field("USD", json_schema_extra={"example": "USD"})
    tax_rate: float = Field(0.0, json_schema_extra={"example": 0.08})
    item_category: str = Field(..., json_schema_extra={"example": "Hardware"})
    line_manager_id: str = Field(..., json_schema_extra={"example": "mgr-882"})
    department_head_id: str = Field(..., json_schema_extra={"example": "dh-401"})
    fallback_approver_id: Optional[str] = Field("DELEGATE_VP", json_schema_extra={"example": "DELEGATE_VP"})


class RequisitionUpdateStatus(BaseModel):
    status: RequisitionStatus
    actor: str = Field(..., json_schema_extra={"example": "mgr-882"})
    comments: Optional[str] = Field(None, json_schema_extra={"example": "Approved based on budget."})


class Requisition(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    requisition_id: str
    requester_name: str
    cost_center: str
    amount: float
    currency: str = "USD"
    tax_rate: float = 0.0
    landed_cost_usd: Optional[float] = None
    item_category: str
    line_manager_id: str
    department_head_id: str
    fallback_approver_id: str = "DELEGATE_VP"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: RequisitionStatus = RequisitionStatus.PENDING
    current_approver: Optional[str] = None
    diagram_url: Optional[str] = None
    history: List[ApprovalAuditEntry] = []
    bpm_routing: Optional[BPMRoutingDecision] = None


class ChatMessage(BaseModel):
    role: str = Field(..., json_schema_extra={"example": "user"})
    content: str = Field(...)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Optional[dict] = None


class ChatRequest(BaseModel):
    session_id: str = Field(..., json_schema_extra={"example": "session-123"})
    message: str = Field(..., json_schema_extra={"example": "What is the status of requisition REQ-1001?"})
    requisition_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    response: str
    requisition: Optional[Requisition] = None
    routing_decision: Optional[BPMRoutingDecision] = None
    a2ui_components: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_action: Optional[dict] = None

import os
import logging
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query, Path, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from schemas import (
    Requisition,
    RequisitionCreate,
    RequisitionUpdateStatus,
    RequisitionStatus,
    BPMRoutingDecision,
    PolicyEvaluationResult,
    ChatRequest,
    ChatResponse,
    ChatMessage
)
from firestore_db import db_service
from bpm_engine import BPMRoutingEngine
from policy_engine import ApprovalPolicyEngine
from agent import agent_instance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("po_fastapi")

app = FastAPI(
    title="POApprovalAgent API",
    description="Python FastAPI Agent for Dynamic Purchase Order & Requisition Approvals with BPM Routing Engine",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "agent": agent_instance.name,
        "firestore_mode": "mock" if db_service.use_mock else "live",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# --- Requisition CRUD & BPM Endpoints ---

@app.post(
    "/api/requisitions",
    response_model=Requisition,
    status_code=status.HTTP_201_CREATED,
    tags=["Requisitions"]
)
def create_requisition(req_in: RequisitionCreate):
    """
    Submit a new Purchase Order Requisition.
    Evaluates BPM rules (Rules 1, 2, 3) to assign required approvers and initial routing status.
    """
    now_str = datetime.now(timezone.utc).isoformat()
    req_id = f"REQ-{int(datetime.now().timestamp() * 1000) % 100000:04d}"
    
    new_req = Requisition(
        requisition_id=req_id,
        requester_name=req_in.requester_name,
        cost_center=req_in.cost_center,
        amount=req_in.amount,
        item_category=req_in.item_category,
        line_manager_id=req_in.line_manager_id,
        department_head_id=req_in.department_head_id,
        fallback_approver_id=req_in.fallback_approver_id or "DELEGATE_VP",
        created_at=now_str,
        last_updated_at=now_str,
        status=RequisitionStatus.PENDING
    )
    
    # Determine initial route via BPM Engine
    decision = BPMRoutingEngine.determine_initial_route(new_req)
    new_req.status = decision.next_status
    new_req.current_approver = decision.current_approver
    new_req.bpm_routing = decision

    created_req = db_service.create_requisition(new_req)
    logger.info(f"Created Requisition {created_req.requisition_id} with initial status {created_req.status}")
    return created_req


@app.get(
    "/api/requisitions",
    response_model=List[Requisition],
    tags=["Requisitions"]
)
def list_requisitions(
    status: Optional[str] = Query(None, description="Filter by status e.g. 'PENDING_LINE_MANAGER', 'APPROVED', etc."),
    category: Optional[str] = Query(None, description="Filter by item category")
):
    """
    List all PO Requisitions with optional status or category filtering.
    """
    return db_service.list_requisitions(status=status, category=category)


@app.get(
    "/api/requisitions/{requisition_id}",
    response_model=Requisition,
    tags=["Requisitions"]
)
def get_requisition(requisition_id: str = Path(..., description="Unique requisition ID")):
    """
    Fetch a single requisition state and audit log.
    """
    req = db_service.get_requisition(requisition_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisition '{requisition_id}' not found"
        )
    return req


@app.post(
    "/api/requisitions/{requisition_id}/route",
    response_model=BPMRoutingDecision,
    tags=["BPM Routing Engine"]
)
def route_and_advance_requisition(
    requisition_id: str,
    actor: str = Query("Manager", description="Actor advancing the approval step"),
    comments: Optional[str] = Query(None, description="Approval step comments")
):
    """
    Advance a requisition through its BPM multi-step approval flow.
    Returns structured JSON detailing rule applied, required approvers, step, and reasoning.
    """
    req = db_service.get_requisition(requisition_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisition '{requisition_id}' not found"
        )
    
    updated_req, decision = BPMRoutingEngine.advance_approval_step(req, actor=actor, comments=comments)
    return decision


@app.post(
    "/api/requisitions/check-stale",
    response_model=List[Requisition],
    tags=["BPM Routing Engine"]
)
def check_and_escalate_stale_requests(cutoff_hours: float = Query(48.0, description="Inactivity threshold in hours")):
    """
    Edge Case Escalation Logic:
    Scans for requests in pending approval states for > 48 hours and updates status to 'ESCALATED_TO_DELEGATE',
    reassigning to user preference fallback approvers.
    """
    return BPMRoutingEngine.check_and_escalate_stale_requests(cutoff_hours=cutoff_hours)


@app.patch(
    "/api/requisitions/{requisition_id}/status",
    response_model=Requisition,
    tags=["Requisitions"]
)
def update_requisition_status(
    requisition_id: str,
    update_data: RequisitionUpdateStatus
):
    """
    Directly update requisition status and record audit entry.
    """
    updated_req = db_service.update_requisition_status(
        requisition_id=requisition_id,
        new_status=update_data.status,
        actor=update_data.actor,
        comments=update_data.comments
    )
    if not updated_req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisition '{requisition_id}' not found"
        )
    return updated_req


@app.delete(
    "/api/requisitions/{requisition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Requisitions"]
)
def delete_requisition(requisition_id: str):
    """
    Delete a requisition from database.
    """
    success = db_service.delete_requisition(requisition_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requisition '{requisition_id}' not found"
        )
    return None


# --- Agent Chat Endpoints ---

@app.post(
    "/api/agent/chat",
    response_model=ChatResponse,
    tags=["Agent"]
)
def agent_chat(chat_request: ChatRequest):
    """
    Interact with POApprovalAgent via natural language to query status, evaluate BPM rules,
    or advance approval workflow steps.
    """
    return agent_instance.process_chat(chat_request)


@app.get(
    "/api/agent/sessions/{session_id}/history",
    response_model=List[ChatMessage],
    tags=["Agent"]
)
def get_session_history(session_id: str):
    """
    Retrieve stored chat session history from Firestore.
    """
    return db_service.get_session_history(session_id)


# Mount Static UI Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def read_root():
        return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)


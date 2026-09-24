import re
import json
import logging
from typing import Optional, Tuple, Dict, Any, List
from datetime import datetime, timezone
from schemas import (
    Requisition,
    RequisitionStatus,
    RequisitionCreate,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ApprovalAuditEntry,
    BPMRoutingDecision
)
from firestore_db import db_service
from bpm_engine import BPMRoutingEngine
from rag_service import rag_service
from sandbox_runner import sandbox_runner

logger = logging.getLogger("po_agent")


class POApprovalAgent:
    """
    Intelligent PO Approval Agent with A2UI Rich Components, Sandbox Calculations, & Diagram Generation.
    """

    def __init__(self, name: str = "POApprovalAgent"):
        self.name = name

    def process_chat(self, request: ChatRequest) -> ChatResponse:
        session_id = request.session_id
        user_msg_str = request.message.strip()

        # Log incoming user message
        user_message = ChatMessage(
            role="user",
            content=user_msg_str,
            metadata={"requisition_id": request.requisition_id}
        )
        db_service.save_session_message(session_id, user_message)

        req_id_match = re.search(r"REQ-\d+", user_msg_str, re.IGNORECASE)
        target_req_id = request.requisition_id or (req_id_match.group(0).upper() if req_id_match else None)

        response_text = ""
        target_req: Optional[Requisition] = None
        routing_decision: Optional[BPMRoutingDecision] = None
        a2ui_components: List[Dict[str, Any]] = []

        lower_msg = user_msg_str.lower()

        if "create" in lower_msg or "submit" in lower_msg or "new requisition" in lower_msg or "form" in lower_msg:
            response_text, target_req, routing_decision, a2ui_components = self._handle_creation_intent(user_msg_str)
        
        elif ("approve" in lower_msg or "advance" in lower_msg) and target_req_id:
            response_text, target_req, routing_decision, a2ui_components = self._handle_advance_approval_intent(target_req_id, actor="ChatUser")

        elif ("reject" in lower_msg) and target_req_id:
            db_service.update_requisition_status(target_req_id, RequisitionStatus.REJECTED, actor="ChatUser", comments="Rejected via chat action.")
            target_req = db_service.get_requisition(target_req_id)
            response_text = f"❌ **Requisition {target_req_id} REJECTED** by ChatUser."
            if target_req:
                a2ui_components.append(self._build_status_card_a2ui(target_req))

        elif ("escalate" in lower_msg) and target_req_id:
            db_service.update_requisition_status(target_req_id, RequisitionStatus.ESCALATED_TO_DELEGATE, actor="ChatUser", comments="Escalated via chat action.")
            target_req = db_service.get_requisition(target_req_id)
            response_text = f"🚨 **Requisition {target_req_id} ESCALATED** to fallback delegate."
            if target_req:
                a2ui_components.append(self._build_status_card_a2ui(target_req))

        elif "escalated" in lower_msg or "stale" in lower_msg or "sweep" in lower_msg:
            stale_list = BPMRoutingEngine.check_and_escalate_stale_requests(cutoff_hours=48.0)
            if stale_list:
                req_ids = [r.requisition_id for r in stale_list]
                response_text = f"🚨 **48-Hour Inactivity Escalation Completed**\nEscalated {len(stale_list)} request(s): {', '.join(req_ids)}."
            else:
                response_text = "✅ **48-Hour Inactivity Check**: No stale pending requests found."

        elif "status" in lower_msg or "check" in lower_msg or "summary" in lower_msg or "route" in lower_msg or "policy" in lower_msg:
            if target_req_id:
                target_req = db_service.get_requisition(target_req_id)
                if target_req:
                    routing_decision = target_req.bpm_routing or BPMRoutingEngine.determine_initial_route(target_req)
                    st_val = target_req.status.value if hasattr(target_req.status, "value") else target_req.status
                    
                    rag_notes = "\n".join([f"• {p}" for p in routing_decision.rag_policies_retrieved]) if routing_decision.rag_policies_retrieved else "• Standard compliance check passed."

                    response_text = (
                        f"📋 **BPM & RAG Routing for {target_req.requisition_id}**\n"
                        f"- Requester: **{target_req.requester_name}** | Cost Center: **{target_req.cost_center}**\n"
                        f"- Amount: **${target_req.amount:,.2f} {target_req.currency}** (Landed Cost: **${target_req.landed_cost_usd or target_req.amount:,.2f} USD**)\n"
                        f"- Status: `{st_val}` | Pending Approver: `{routing_decision.current_approver}`\n\n"
                        f"📚 **RAG Grounded Policies:**\n{rag_notes}"
                    )

                    a2ui_components.append(self._build_status_card_a2ui(target_req))
                    if target_req.diagram_url:
                        a2ui_components.append({"type": "workflow_diagram", "diagram_url": target_req.diagram_url})
                    a2ui_components.append(self._build_action_buttons_a2ui(target_req.requisition_id))
                else:
                    response_text = f"❌ Could not find requisition with ID `{target_req_id}`."
            else:
                reqs = db_service.list_requisitions()
                response_text = f"📊 Total Requisitions in Register: **{len(reqs)}**. You can ask to view, approve, or submit a requisition."
                a2ui_components.append(self._build_approval_form_a2ui())

        else:
            if target_req_id:
                target_req = db_service.get_requisition(target_req_id)
                if target_req:
                    response_text = f"Inquiring about **{target_req.requisition_id}** (${target_req.amount:,.2f} {target_req.currency}). Use buttons below to take action."
                    a2ui_components.append(self._build_status_card_a2ui(target_req))
                    a2ui_components.append(self._build_action_buttons_a2ui(target_req.requisition_id))
                else:
                    response_text = f"Requisition `{target_req_id}` was not found."
            else:
                response_text = (
                    f"Hello! I am **{self.name}** featuring **A2UI Rich Components**, **Python Sandbox Landed Cost Calculations**, and **Visual Workflow Hierarchy Diagrams**.\n\n"
                    f"Use the form below or chat e.g. `Approve REQ-1002` or `Check status REQ-1003`."
                )
                a2ui_components.append(self._build_approval_form_a2ui())

        # Save assistant message
        assistant_msg = ChatMessage(
            role="assistant",
            content=response_text,
            metadata={"requisition_id": target_req.requisition_id if target_req else None}
        )
        db_service.save_session_message(session_id, assistant_msg)

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            requisition=target_req,
            routing_decision=routing_decision,
            a2ui_components=a2ui_components
        )

    def _handle_creation_intent(self, text: str) -> Tuple[str, Optional[Requisition], Optional[BPMRoutingDecision], List[Dict[str, Any]]]:
        amount_match = re.search(r"\$(\d+(?:\.\d{2})?)|\b(\d+)\s*(?:dollars|usd|eur|gbp)?", text, re.IGNORECASE)
        amount = float(amount_match.group(1) or amount_match.group(2)) if amount_match else 30000.00
        
        currency = "USD"
        if "eur" in text.lower():
            currency = "EUR"
        elif "gbp" in text.lower():
            currency = "GBP"

        category = "Hardware"
        if "consulting" in text.lower():
            category = "Consulting"
        elif "software" in text.lower():
            category = "Software"

        new_id = f"REQ-{int(datetime.now().timestamp() * 10) % 100000:04d}"
        now_str = datetime.now(timezone.utc).isoformat()

        req_create = Requisition(
            requisition_id=new_id,
            requester_name="Chat User",
            cost_center="CC-ENG-101",
            amount=amount,
            currency=currency,
            tax_rate=0.08,
            item_category=category,
            line_manager_id="MGR-101",
            department_head_id="DH-201",
            fallback_approver_id="DELEGATE_VP",
            created_at=now_str,
            last_updated_at=now_str,
            status=RequisitionStatus.PENDING
        )

        decision = BPMRoutingEngine.determine_initial_route(req_create)
        req_create.status = decision.next_status
        req_create.current_approver = decision.current_approver
        req_create.bpm_routing = decision

        saved_req = db_service.create_requisition(req_create)

        st_val = saved_req.status.value if hasattr(saved_req.status, "value") else saved_req.status
        reply = (
            f"✅ **Created Requisition {saved_req.requisition_id}**\n"
            f"- Category: **{saved_req.item_category}** | Amount: **{saved_req.amount:,.2f} {saved_req.currency}**\n"
            f"- Sandbox Landed Cost USD: **${saved_req.landed_cost_usd:,.2f}**\n"
            f"- Assigned Status: `{st_val}` | Pending Approver: `{decision.current_approver}`"
        )

        components = [
            self._build_status_card_a2ui(saved_req),
            {"type": "workflow_diagram", "diagram_url": saved_req.diagram_url},
            self._build_action_buttons_a2ui(saved_req.requisition_id)
        ]

        return reply, saved_req, decision, components

    def _handle_advance_approval_intent(self, requisition_id: str, actor: str) -> Tuple[str, Optional[Requisition], Optional[BPMRoutingDecision], List[Dict[str, Any]]]:
        req = db_service.get_requisition(requisition_id)
        if not req:
            return f"❌ Requisition `{requisition_id}` was not found.", None, None, []

        prev_st = req.status.value if hasattr(req.status, "value") else req.status
        updated_req, decision = BPMRoutingEngine.advance_approval_step(req, actor=actor, comments="Advanced via conversational agent.")
        new_st = updated_req.status.value if hasattr(updated_req.status, "value") else updated_req.status

        msg = (
            f"⚡ **BPM Approval Advanced for {requisition_id}**\n"
            f"- Transition: `{prev_st}` ➔ `{new_st}`\n"
            f"- Current Step: **{decision.current_step}** | Pending Approver: `{decision.current_approver}`"
        )

        components = [
            self._build_status_card_a2ui(updated_req),
            {"type": "workflow_diagram", "diagram_url": updated_req.diagram_url},
            self._build_action_buttons_a2ui(updated_req.requisition_id)
        ]

        return msg, updated_req, decision, components

    # --- A2UI Helper Builders ---

    def _build_status_card_a2ui(self, req: Requisition) -> Dict[str, Any]:
        st = req.status.value if hasattr(req.status, "value") else req.status
        if st == "APPROVED":
            color = "green"
        elif "ESCALATED" in st or st == "REJECTED":
            color = "red"
        else:
            color = "yellow"

        return {
            "type": "status_card",
            "requisition_id": req.requisition_id,
            "status": st,
            "status_color": color,
            "amount_display": f"${req.amount:,.2f} {req.currency} (Landed: ${req.landed_cost_usd or req.amount:,.2f} USD)",
            "category": req.item_category,
            "approver": req.current_approver or "N/A"
        }

    def _build_action_buttons_a2ui(self, requisition_id: str) -> Dict[str, Any]:
        return {
            "type": "action_buttons",
            "requisition_id": requisition_id,
            "buttons": [
                {"label": "Approve", "action": "approve", "style": "btn-success"},
                {"label": "Reject", "action": "reject", "style": "btn-danger"},
                {"label": "Escalate", "action": "escalate", "style": "btn-warning"}
            ]
        }

    def _build_approval_form_a2ui(self) -> Dict[str, Any]:
        return {
            "type": "approval_form",
            "title": "Interactive Requisition Approval Form",
            "fields": [
                {"name": "requester_name", "label": "Requester Name", "type": "text", "default": "Jane Doe"},
                {"name": "cost_center", "label": "Cost Center", "type": "text", "default": "CC-ENG-101"},
                {"name": "amount", "label": "Amount", "type": "number", "default": 25000},
                {"name": "currency", "label": "Currency", "type": "select", "options": ["USD", "EUR", "GBP", "JPY"]},
                {"name": "item_category", "label": "Category", "type": "select", "options": ["Hardware", "Software", "Consulting", "Office Supplies"]}
            ]
        }


agent_instance = POApprovalAgent()

import logging
from typing import List, Tuple, Optional
from datetime import datetime, timezone, timedelta
from schemas import (
    Requisition,
    RequisitionStatus,
    BPMRoutingDecision,
    ApprovalAuditEntry
)
from firestore_db import db_service
from rag_service import rag_service
from sandbox_runner import sandbox_runner
from diagram_generator import generate_workflow_diagram

logger = logging.getLogger("bpm_engine")


class BPMRoutingEngine:
    """
    BPM Approval Routing Engine with Sandbox Calculation & Diagram Generation:
    - Calculates total landed cost in USD via sandbox code execution tool.
    - Evaluates BPM threshold rules and Vertex AI RAG grounded compliance policies.
    - Generates visual flowchart diagrams for the approval hierarchy.
    """

    @classmethod
    def determine_initial_route(cls, req: Requisition) -> BPMRoutingDecision:
        # 1. Run Landed Cost Sandbox Calculation
        calc = sandbox_runner.execute_landed_cost_calc(
            amount=req.amount,
            currency=req.currency,
            tax_rate=req.tax_rate
        )
        req.landed_cost_usd = calc.total_landed_cost_usd
        eval_amount = calc.total_landed_cost_usd
        category = req.item_category

        # 2. Query Vertex AI RAG knowledge base using total landed cost USD
        rag_res = rag_service.query_compliance_policies(category, eval_amount)

        # 3. Determine base BPM route
        if eval_amount < 10000.00:
            if category.lower() != "consulting":
                rule = "Rule 1: Landed Cost < $10,000 & Category != Consulting"
                step = "Auto-Approved"
                approver = "SYSTEM_AUTO"
                next_st = RequisitionStatus.APPROVED
                req_approvers = []
                reason = f"Landed cost (${eval_amount:,.2f} USD) is below $10,000 and non-consulting. Auto-approved by BPM Rule 1."
            else:
                rule = "Rule 1: Landed Cost < $10,000 & Category == Consulting"
                step = "Line Manager Review"
                approver = req.line_manager_id
                next_st = RequisitionStatus.PENDING_LINE_MANAGER
                req_approvers = [req.line_manager_id]
                reason = f"Consulting requisitions below $10,000 (${eval_amount:,.2f} USD) require single-step Line Manager approval by BPM Rule 1."

        elif 10000.00 <= eval_amount <= 50000.00:
            rule = "Rule 2: $10,000 <= Landed Cost <= $50,000"
            step = "Line Manager Review (Step 1/2)"
            approver = req.line_manager_id
            next_st = RequisitionStatus.PENDING_LINE_MANAGER
            req_approvers = [req.line_manager_id, req.department_head_id]
            reason = f"Landed cost (${eval_amount:,.2f} USD) requires multi-step approval (Line Manager -> Department Head) by BPM Rule 2."

        else:  # eval_amount > 50000.00
            rule = "Rule 3: Landed Cost > $50,000"
            step = "Line Manager Review (Step 1/3)"
            approver = req.line_manager_id
            next_st = RequisitionStatus.PENDING_LINE_MANAGER
            req_approvers = [req.line_manager_id, "FINANCE_VP", "PROCUREMENT_DIR"]
            reason = f"Landed cost (${eval_amount:,.2f} USD) requires multi-step approval (Line Manager -> Finance VP -> Procurement Director) by BPM Rule 3."

        # 4. Dynamic RAG Compliance Adjustment
        if "SECURITY_OFFICER" in rag_res.additional_approvers:
            if "SECURITY_OFFICER" not in req_approvers:
                req_approvers.append("SECURITY_OFFICER")
            reason += " [Vertex AI RAG Grounded: Additional Security Officer approval required for IT Hardware > $25,000]."

        if rag_res.compliance_flags:
            reason += f" [RAG Flags: {', '.join(rag_res.compliance_flags)}]."

        # 5. Generate Visual Workflow Diagram PNG
        diagram_path = generate_workflow_diagram(
            requisition_id=req.requisition_id,
            requester_name=req.requester_name,
            required_approvers=req_approvers,
            current_approver=approver,
            status=next_st.value if hasattr(next_st, "value") else str(next_st)
        )
        req.diagram_url = diagram_path

        return BPMRoutingDecision(
            requisition_id=req.requisition_id,
            amount=req.amount,
            item_category=req.item_category,
            rule_applied=rule,
            current_step=step,
            current_approver=approver,
            required_approvers=req_approvers,
            next_status=next_st,
            reasoning=reason,
            rag_policies_retrieved=rag_res.retrieved_policies,
            compliance_flags=rag_res.compliance_flags,
            additional_approvers=rag_res.additional_approvers,
            diagram_url=diagram_path,
            landed_cost_summary=f"{req.amount} {req.currency} -> ${calc.total_landed_cost_usd:,.2f} USD (Tax: {req.tax_rate*100:.1f}%)"
        )

    @classmethod
    def advance_approval_step(
        cls,
        req: Requisition,
        actor: str,
        comments: Optional[str] = None
    ) -> Tuple[Requisition, BPMRoutingDecision]:
        # Calculate sandbox landed cost
        calc = sandbox_runner.execute_landed_cost_calc(req.amount, req.currency, req.tax_rate)
        eval_amount = calc.total_landed_cost_usd
        category = req.item_category
        current_st = req.status
        now_str = datetime.now(timezone.utc).isoformat()

        rag_res = rag_service.query_compliance_policies(category, eval_amount)
        requires_security = "SECURITY_OFFICER" in rag_res.additional_approvers

        if current_st in (RequisitionStatus.APPROVED, RequisitionStatus.REJECTED):
            decision = cls.determine_initial_route(req)
            decision.reasoning = f"Requisition is already in terminal status '{current_st.value}'."
            return req, decision

        if eval_amount < 10000.00:
            next_st = RequisitionStatus.APPROVED
            next_approver = "COMPLETED"
            step = "Approved (Final)"
            rule = "Rule 1: Consulting Approval"
            reason = f"Line Manager '{actor}' approved consulting requisition."
            req_approvers = [req.line_manager_id]

        elif 10000.00 <= eval_amount <= 50000.00:
            if current_st in (RequisitionStatus.PENDING_LINE_MANAGER, RequisitionStatus.PENDING):
                next_st = RequisitionStatus.PENDING_DEPT_HEAD
                next_approver = req.department_head_id
                step = "Department Head Review"
                rule = "Rule 2: Line Manager Approved"
                reason = f"Line Manager '{actor}' approved. Routed to Department Head '{req.department_head_id}'."
            elif current_st == RequisitionStatus.PENDING_DEPT_HEAD:
                if requires_security:
                    next_st = RequisitionStatus.PENDING_SECURITY_OFFICER
                    next_approver = "SECURITY_OFFICER"
                    step = "Security Officer Compliance Review"
                    rule = "Vertex AI RAG: Security Compliance Requirement"
                    reason = f"Department Head '{actor}' approved. Routed to Security Officer per Corporate Procurement RAG policy for Hardware > $25,000."
                else:
                    next_st = RequisitionStatus.APPROVED
                    next_approver = "COMPLETED"
                    step = "Approved (Final)"
                    rule = "Rule 2: Department Head Approved"
                    reason = f"Department Head '{actor}' approved. Workflow completed."
            else:
                next_st = RequisitionStatus.APPROVED
                next_approver = "COMPLETED"
                step = "Approved (Final)"
                rule = "RAG Compliance: Security Officer Approved"
                reason = f"Security Officer '{actor}' approved compliance check. Workflow completed."

            req_approvers = [req.line_manager_id, req.department_head_id]
            if requires_security:
                req_approvers.append("SECURITY_OFFICER")

        else:
            if current_st in (RequisitionStatus.PENDING_LINE_MANAGER, RequisitionStatus.PENDING):
                next_st = RequisitionStatus.PENDING_FINANCE_VP
                next_approver = "FINANCE_VP"
                step = "Finance VP Review"
                rule = "Rule 3: Line Manager Approved"
                reason = f"Line Manager '{actor}' approved. Routed to Finance VP."
            elif current_st == RequisitionStatus.PENDING_FINANCE_VP:
                next_st = RequisitionStatus.PENDING_PROCUREMENT_DIR
                next_approver = "PROCUREMENT_DIR"
                step = "Procurement Director Review"
                rule = "Rule 3: Finance VP Approved"
                reason = f"Finance VP '{actor}' approved. Routed to Procurement Director."
            elif current_st == RequisitionStatus.PENDING_PROCUREMENT_DIR:
                if requires_security:
                    next_st = RequisitionStatus.PENDING_SECURITY_OFFICER
                    next_approver = "SECURITY_OFFICER"
                    step = "Security Officer Compliance Review"
                    rule = "Vertex AI RAG: Security Compliance Requirement"
                    reason = f"Procurement Director '{actor}' approved. Routed to Security Officer per Corporate Procurement RAG policy for IT Hardware > $25,000."
                else:
                    next_st = RequisitionStatus.APPROVED
                    next_approver = "COMPLETED"
                    step = "Approved (Final)"
                    rule = "Rule 3: Procurement Director Approved"
                    reason = f"Procurement Director '{actor}' approved. Workflow completed."
            else:
                next_st = RequisitionStatus.APPROVED
                next_approver = "COMPLETED"
                step = "Approved (Final)"
                rule = "RAG Compliance: Security Officer Approved"
                reason = f"Security Officer '{actor}' approved compliance check. Workflow completed."

            req_approvers = [req.line_manager_id, "FINANCE_VP", "PROCUREMENT_DIR"]
            if requires_security:
                req_approvers.append("SECURITY_OFFICER")

        previous_status = req.status
        req.status = next_st
        req.current_approver = next_approver
        req.last_updated_at = now_str
        
        audit = ApprovalAuditEntry(
            actor=actor,
            previous_status=previous_status,
            new_status=next_st,
            timestamp=now_str,
            comments=comments or f"Advanced step via {rule}"
        )
        req.history.append(audit)

        diagram_path = generate_workflow_diagram(
            requisition_id=req.requisition_id,
            requester_name=req.requester_name,
            required_approvers=req_approvers,
            current_approver=next_approver,
            status=next_st.value if hasattr(next_st, "value") else str(next_st)
        )
        req.diagram_url = diagram_path

        decision = BPMRoutingDecision(
            requisition_id=req.requisition_id,
            amount=req.amount,
            item_category=req.item_category,
            rule_applied=rule,
            current_step=step,
            current_approver=next_approver,
            required_approvers=req_approvers,
            next_status=next_st,
            reasoning=reason,
            rag_policies_retrieved=rag_res.retrieved_policies,
            compliance_flags=rag_res.compliance_flags,
            additional_approvers=rag_res.additional_approvers,
            diagram_url=diagram_path,
            landed_cost_summary=f"{req.amount} {req.currency} -> ${calc.total_landed_cost_usd:,.2f} USD"
        )
        req.bpm_routing = decision

        db_service.create_requisition(req)
        return req, decision

    @classmethod
    def check_and_escalate_stale_requests(cls, cutoff_hours: float = 48.0) -> List[Requisition]:
        all_reqs = db_service.list_requisitions()
        stale_reqs: List[Requisition] = []
        now = datetime.now(timezone.utc)
        cutoff_delta = timedelta(hours=cutoff_hours)

        pending_statuses = {
            RequisitionStatus.PENDING,
            RequisitionStatus.PENDING_LINE_MANAGER,
            RequisitionStatus.PENDING_DEPT_HEAD,
            RequisitionStatus.PENDING_FINANCE_VP,
            RequisitionStatus.PENDING_PROCUREMENT_DIR,
            RequisitionStatus.PENDING_SECURITY_OFFICER,
            RequisitionStatus.ESCALATED
        }

        for req in all_reqs:
            if req.status in pending_statuses:
                ref_time_str = req.last_updated_at or req.created_at
                try:
                    ref_dt = datetime.fromisoformat(ref_time_str)
                    if ref_dt.tzinfo is None:
                        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
                except Exception:
                    ref_dt = now

                elapsed = now - ref_dt
                if elapsed >= cutoff_delta:
                    fallback = req.fallback_approver_id or "DELEGATE_VP"
                    prev_status = req.status
                    req.status = RequisitionStatus.ESCALATED_TO_DELEGATE
                    req.current_approver = fallback
                    req.last_updated_at = now.isoformat()

                    audit = ApprovalAuditEntry(
                        actor="BPMEngine_48Hr_Watcher",
                        previous_status=prev_status,
                        new_status=RequisitionStatus.ESCALATED_TO_DELEGATE,
                        timestamp=now.isoformat(),
                        comments=f"Inactivity timeout (> {cutoff_hours} hours). Escalated to fallback delegate '{fallback}'."
                    )
                    req.history.append(audit)

                    diagram_path = generate_workflow_diagram(
                        requisition_id=req.requisition_id,
                        requester_name=req.requester_name,
                        required_approvers=[fallback],
                        current_approver=fallback,
                        status="ESCALATED_TO_DELEGATE"
                    )
                    req.diagram_url = diagram_path

                    req.bpm_routing = BPMRoutingDecision(
                        requisition_id=req.requisition_id,
                        amount=req.amount,
                        item_category=req.item_category,
                        rule_applied="Edge Case: 48-Hour Inactivity Escalation",
                        current_step="Escalated to Fallback Delegate",
                        current_approver=fallback,
                        required_approvers=[fallback],
                        next_status=RequisitionStatus.ESCALATED_TO_DELEGATE,
                        reasoning=f"Inactive in '{prev_status.value}' for over {cutoff_hours} hours. Reassigned to delegate ({fallback}).",
                        diagram_url=diagram_path
                    )

                    db_service.create_requisition(req)
                    stale_reqs.append(req)

        return stale_reqs

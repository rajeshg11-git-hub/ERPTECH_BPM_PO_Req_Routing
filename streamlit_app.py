import os
import streamlit as st
from datetime import datetime, timezone
from schemas import Requisition, RequisitionStatus
from firestore_db import db_service
from bpm_engine import BPMRoutingEngine
from agent import agent_instance

st.set_page_config(
    page_title="POApprovalAgent - Procurement Dashboard",
    page_icon="📋",
    layout="wide"
)

st.title("📋 POApprovalAgent - Intelligent Procurement & Approval Engine")
st.caption("BPM Routing Engine | Vertex AI RAG Policy Grounding | Python Sandbox Calculations | A2UI Components")

tab1, tab2, tab3 = st.tabs(["Submit New Requisition", "Requisition Management & Approval Simulator", "48-Hour Escalation Simulator"])

# --- TAB 1: Submit Requisition ---
with tab1:
    st.subheader("Submit Test PO Requisition")
    with st.form("create_req_form"):
        col1, col2 = st.columns(2)
        with col1:
            requester_name = st.text_input("Requester Name", "Jane Doe")
            cost_center = st.text_input("Cost Center", "CC-ENG-102")
            amount = st.number_input("Amount", min_value=1.0, value=25000.0, step=500.0)
            currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "JPY", "CAD"])
        with col2:
            item_category = st.selectbox("Category", ["Hardware", "Software", "Consulting", "Office Supplies", "Marketing"])
            line_manager_id = st.text_input("Line Manager ID", "MGR-882")
            department_head_id = st.text_input("Department Head ID", "DH-401")
            fallback_approver_id = st.text_input("Fallback Delegate ID", "DELEGATE_VP")

        submit_btn = st.form_submit_button("Submit Requisition")

    if submit_btn:
        new_id = f"REQ-{int(datetime.now().timestamp() * 10) % 100000:04d}"
        now_str = datetime.now(timezone.utc).isoformat()
        req = Requisition(
            requisition_id=new_id,
            requester_name=requester_name,
            cost_center=cost_center,
            amount=amount,
            currency=currency,
            tax_rate=0.08,
            item_category=item_category,
            line_manager_id=line_manager_id,
            department_head_id=department_head_id,
            fallback_approver_id=fallback_approver_id,
            created_at=now_str,
            last_updated_at=now_str
        )
        decision = BPMRoutingEngine.determine_initial_route(req)
        req.status = decision.next_status
        req.current_approver = decision.current_approver
        req.bpm_routing = decision
        saved = db_service.create_requisition(req)

        st.success(f"Successfully Created Requisition **{saved.requisition_id}**!")
        st.json(decision.model_dump())

        if saved.diagram_url:
            diagram_file = os.path.join(os.path.dirname(__file__), saved.diagram_url.lstrip('/'))
            if os.path.exists(diagram_file):
                st.image(diagram_file, caption=f"Approval Workflow Diagram for {saved.requisition_id}")

# --- TAB 2: Requisition Register & Approval Simulator ---
with tab2:
    st.subheader("Active Requisitions Register")
    reqs = db_service.list_requisitions()
    
    if not reqs:
        st.info("No requisitions found in database.")
    else:
        for r in reqs:
            st_val = r.status.value if hasattr(r.status, "value") else r.status
            with st.expander(f"{r.requisition_id} | {r.item_category} | ${r.amount:,.2f} {r.currency} | Status: {st_val}"):
                c1, col_diagram = st.columns([1, 1])
                with c1:
                    st.write(f"**Requester**: {r.requester_name}")
                    st.write(f"**Cost Center**: {r.cost_center}")
                    st.write(f"**Pending Approver**: `{r.current_approver}`")
                    st.write(f"**Landed Cost USD**: `${r.landed_cost_usd or r.amount:,.2f}`")
                    
                    if r.bpm_routing:
                        st.markdown(f"**Applied Rule**: {r.bpm_routing.rule_applied}")
                        st.markdown(f"**Active Step**: {r.bpm_routing.current_step}")
                        st.markdown(f"**Required Approvers**: `{' ➔ '.join(r.bpm_routing.required_approvers)}`")
                        if r.bpm_routing.rag_policies_retrieved:
                            st.info(f"**RAG Policy**: {r.bpm_routing.rag_policies_retrieved[0]}")

                    # Simulator Approval Buttons
                    if st_val not in ("APPROVED", "REJECTED"):
                        b_col1, b_col2 = st.columns(2)
                        with b_col1:
                            if st.button(f"Approve Step for {r.requisition_id}", key=f"appr_{r.requisition_id}"):
                                updated, dec = BPMRoutingEngine.advance_approval_step(r, actor=r.current_approver or "Manager")
                                st.success(f"Advanced {r.requisition_id} to {updated.status}!")
                                st.rerun()
                        with b_col2:
                            if st.button(f"Reject {r.requisition_id}", key=f"rej_{r.requisition_id}"):
                                db_service.update_requisition_status(r.requisition_id, RequisitionStatus.REJECTED, actor="Manager")
                                st.warning(f"Rejected {r.requisition_id}")
                                st.rerun()

                with col_diagram:
                    if r.diagram_url:
                        d_path = os.path.join(os.path.dirname(__file__), r.diagram_url.lstrip('/'))
                        if os.path.exists(d_path):
                            st.image(d_path, caption="Visual Approval Workflow Flowchart")

# --- TAB 3: 48-Hour Inactivity Escalation Simulator ---
with tab3:
    st.subheader("48-Hour Inactivity Escalation Simulator")
    st.write("Scans all pending requisitions and escalates any inactive for > 48 hours to their fallback delegate.")
    cutoff = st.slider("Cutoff Inactivity Hours", min_value=1.0, max_value=72.0, value=48.0)
    
    if st.button("Run Escalation Sweep"):
        stale_reqs = BPMRoutingEngine.check_and_escalate_stale_requests(cutoff_hours=cutoff)
        if stale_reqs:
            st.warning(f"Escalated {len(stale_reqs)} stale request(s) to user fallback delegates!")
            for sr in stale_reqs:
                st.write(f"- **{sr.requisition_id}** -> Escalated to delegate `{sr.current_approver}`")
        else:
            st.success("No stale pending requests found matching cutoff criteria.")

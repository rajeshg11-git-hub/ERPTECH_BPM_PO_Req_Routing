import os
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from main import app
from schemas import RequisitionStatus
from firestore_db import db_service
from bpm_engine import BPMRoutingEngine
from sandbox_runner import sandbox_runner
from diagram_generator import generate_workflow_diagram

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["agent"] == "POApprovalAgent"


def test_sandbox_landed_cost_calculation():
    """
    Test safe Python sandbox calculation tool for multi-currency EUR & tax.
    """
    calc = sandbox_runner.execute_landed_cost_calc(
        amount=10000.0,
        currency="EUR",
        tax_rate=0.10
    )
    # 10,000 EUR @ 1.08 = $10,800 USD base + $1,080 tax = $11,880 USD total
    assert calc.amount_usd == 10800.0
    assert calc.tax_amount_usd == 1080.0
    assert calc.total_landed_cost_usd == 11880.0
    assert "Original: 10000.0 EUR" in calc.execution_logs


def test_workflow_diagram_generation():
    """
    Test Matplotlib diagram PNG workflow flowchart generation.
    """
    diagram_url = generate_workflow_diagram(
        requisition_id="REQ-TEST-DIAGRAM",
        requester_name="Test Requester",
        required_approvers=["MGR-101", "DH-101"],
        current_approver="MGR-101",
        status="PENDING_LINE_MANAGER"
    )
    assert diagram_url == "/static/diagrams/REQ-TEST-DIAGRAM.png"
    
    local_path = os.path.join(os.path.dirname(__file__), "..", "static", "diagrams", "REQ-TEST-DIAGRAM.png")
    assert os.path.exists(os.path.abspath(local_path))



def test_bpm_rule_1_auto_approval_non_consulting():
    payload = {
        "requester_name": "Alice Office",
        "cost_center": "CC-101",
        "amount": 2500.00,
        "currency": "USD",
        "item_category": "Office Supplies",
        "line_manager_id": "MGR-101",
        "department_head_id": "DH-101"
    }
    res = client.post("/api/requisitions", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["status"] == RequisitionStatus.APPROVED.value
    assert data["bpm_routing"]["rule_applied"].startswith("Rule 1")


def test_rag_policy_hardware_over_25k_appends_security_officer():
    payload = {
        "requester_name": "Eve Hardware High",
        "cost_center": "CC-SEC-105",
        "amount": 35000.00,
        "currency": "USD",
        "item_category": "Hardware",
        "line_manager_id": "MGR-105",
        "department_head_id": "DH-105"
    }
    res = client.post("/api/requisitions", json=payload)
    assert res.status_code == 201
    data = res.json()
    bpm = data["bpm_routing"]

    assert "SECURITY_OFFICER" in bpm["required_approvers"]
    assert data["diagram_url"] is not None


def test_agent_chat_a2ui_components():
    payload = {
        "session_id": "a2ui-chat-session",
        "message": "Create new requisition for $30000 EUR in Hardware for cost center CC-TEST"
    }
    res = client.post("/api/agent/chat", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "a2ui_components" in data
    assert len(data["a2ui_components"]) > 0

    types = [c["type"] for c in data["a2ui_components"]]
    assert "status_card" in types
    assert "action_buttons" in types
    assert "workflow_diagram" in types

# POApprovalAgent - Intelligent Purchase Order & Requisition Routing Agent

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110.0-009688.svg?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg?style=flat&logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-Cloud%20Run%20Ready-2496ED.svg?style=flat&logo=docker)](https://cloud.google.com/run)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

An agentic AI Purchase Order (PO) and Requisition approval system built with **FastAPI**, **BPM Routing Rules**, **Vertex AI RAG Policy Grounding**, **Python Code Execution Sandbox**, **Matplotlib Media Flowchart Generation**, and **A2UI Rich Interface Components**.

Deployed live on Google Cloud Run: [https://po-approval-agent-247623479081.us-central1.run.app](https://po-approval-agent-247623479081.us-central1.run.app)

---

## 🌟 Key Capabilities

### 1. BPM Approval Routing Engine
Executes configurable multi-step approval routing based on requisition landed cost thresholds and item category:
- **Rule 1 (Landed Cost < $10,000 USD)**:
  - Automatically marks as `APPROVED` if item category is not `Consulting`.
  - Routes to **Line Manager** for single-step approval if category is `Consulting`.
- **Rule 2 (Landed Cost $10,000 - $50,000 USD)**:
  - Multi-step approval: **Line Manager** ➔ **Department Head**.
- **Rule 3 (Landed Cost > $50,000 USD)**:
  - Multi-step approval: **Line Manager** ➔ **Finance VP** ➔ **Procurement Director**.
- **48-Hour Inactivity Auto-Escalation**:
  - `check_and_escalate_stale_requests()` scans for requests inactive for > 48 hours in `PENDING` status and escalates them to the user's fallback delegate (`ESCALATED_TO_DELEGATE`).

### 2. Vertex AI RAG Policy Grounding
Querying a vector knowledge base containing corporate procurement compliance policies:
- **IT Hardware > $25,000**: Automatically appends `"Security Officer"` (`SECURITY_OFFICER`) to the required approver sequence.
- **Consulting Engagements**: Flags vendor tax validation requirements.

### 3. Financial Sandbox Calculation Tool
Runs safe Python code execution in an isolated environment to compute total USD landed cost:
$$\text{Landed Cost USD} = (\text{Amount} \times \text{FX Rate}) \times (1 + \text{Tax Rate}) + \text{Duties}$$
Supported currencies: `USD`, `EUR`, `GBP`, `JPY`, `CAD`.

### 4. Media Workflow Flowchart Generator
Generates custom visual flowchart PNG diagrams (`Requester ➔ Approver 1 ➔ Approver 2 ...`) highlighting active steps, approved steps, and escalations. Images are served dynamically at `/static/diagrams/{requisition_id}.png`.

### 5. A2UI Interactive Interface
- **Modern Web Dashboard**: Glassmorphism UI with status filter dropdowns, RAG citation modals, and 48-hour escalation sweep trigger.
- **Streamlit Interface Option**: Multi-tab Streamlit interface in `streamlit_app.py`.
- **Interactive Chat A2UI Components**: Embedded requisition forms, dynamic status cards, and 1-click `Approve`, `Reject`, and `Escalate` action buttons directly in chat bubbles.

---

## 📁 Repository Structure

```
.
├── main.py                 # FastAPI application, REST endpoints, static routes
├── agent.py                # POApprovalAgent assistant logic & A2UI component builder
├── bpm_engine.py           # BPM multi-step routing rules & 48-hr escalation logic
├── rag_service.py          # Vertex AI RAG policy grounding vector service
├── sandbox_runner.py       # Safe Python sandbox financial landed cost calculator
├── diagram_generator.py    # Matplotlib workflow hierarchy PNG flowchart generator
├── firestore_db.py         # Firestore state and session persistence service
├── schemas.py              # Pydantic V2 data models & A2UI component schemas
├── streamlit_app.py        # Streamlit dashboard interface
├── Dockerfile              # Cloud Run production container specification
├── requirements.txt        # Python dependency manifest
├── pyproject.toml          # Project configuration & test dependencies
├── static/                 # A2UI Web Dashboard (HTML/CSS/JS) & flowchart diagrams
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── diagrams/
└── tests/
    └── test_api.py         # Pytest test suite
```

---

## 🚀 Local Quickstart

### Prerequisites
- Python 3.10+
- [`uv`](https://github.com/astral-sh/uv) (recommended) or standard `pip`

### 1. Installation
```bash
git clone https://github.com/rajeshg11-git-hub/ERPTECH_BPM_PO_Req_Routing.git
cd ERPTECH_BPM_PO_Req_Routing

# Install dependencies using uv
uv sync --extra dev
```

### 2. Run FastAPI Backend & Web Dashboard
```bash
uv run uvicorn main:app --reload --port 8000
```
Open your browser at `http://localhost:8000` to access the interactive web dashboard.

### 3. Run Streamlit Dashboard Option
```bash
uv run streamlit run streamlit_app.py
```

---

## 🧪 Running Automated Tests

Run the complete pytest suite:
```bash
uv run --extra dev pytest
```

---

## ☁️ Deploying to Google Cloud Run

### 1. Configure GCP Project
```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"

gcloud config set project $PROJECT_ID
```

### 2. Build Container Image with Cloud Build
```bash
gcloud builds submit --tag gcr.io/$PROJECT_ID/po-approval-agent:latest .
```

### 3. Deploy to Cloud Run
```bash
gcloud run deploy po-approval-agent \
  --image gcr.io/$PROJECT_ID/po-approval-agent:latest \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID
```

---

## 📡 API Reference

### `POST /api/requisitions`
Submit new PO requisition.
```json
{
  "requester_name": "Jane Doe",
  "cost_center": "CC-ENG-101",
  "amount": 25000.0,
  "currency": "EUR",
  "tax_rate": 0.08,
  "item_category": "Hardware",
  "line_manager_id": "MGR-101",
  "department_head_id": "DH-201",
  "fallback_approver_id": "DELEGATE_VP"
}
```

### `POST /api/agent/chat`
Interact with POApprovalAgent in natural language with A2UI rich component responses.
```json
{
  "session_id": "user-session-1",
  "message": "Approve REQ-1002"
}
```

### `POST /api/requisitions/check-stale`
Trigger 48-hour inactivity escalation sweep.

---

## 📄 License
MIT License.

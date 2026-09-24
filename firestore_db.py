import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from schemas import Requisition, RequisitionStatus, ApprovalAuditEntry, ChatMessage

logger = logging.getLogger("firestore_db")

# Try importing Firestore SDK and exceptions
try:
    from google.cloud import firestore
    from google.api_core.exceptions import GoogleAPICallError, PermissionDenied
    FIRESTORE_SDK_AVAILABLE = True
except ImportError:
    FIRESTORE_SDK_AVAILABLE = False
    GoogleAPICallError = Exception
    PermissionDenied = Exception
    logger.warning("google-cloud-firestore SDK not installed or unavailable.")


class FirestoreService:
    def __init__(self, project_id: Optional[str] = None, collection_prefix: str = "po_agent_"):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "po-approval-demo")
        self.collection_prefix = collection_prefix
        self.client = None
        self.use_mock = True
        
        # In-memory storage with seed data
        self._mock_requisitions: Dict[str, dict] = {}
        self._mock_sessions: Dict[str, List[dict]] = {}

        self._load_seed_data()
        self._initialize_client()

    def _initialize_client(self):
        if FIRESTORE_SDK_AVAILABLE:
            try:
                # If emulator host is defined or explicit credentials exist
                if os.getenv("FIRESTORE_EMULATOR_HOST") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
                    self.client = firestore.Client(project=self.project_id)
                    self.use_mock = False
                    logger.info("Connected to Firestore client via environment config.")
                else:
                    # Attempt default initialization and probe connection
                    test_client = firestore.Client(project=self.project_id)
                    test_client.collection(f"{self.collection_prefix}health").limit(1).get()
                    self.client = test_client
                    self.use_mock = False
                    logger.info("Connected to Firestore using Default Application Credentials.")
            except Exception as e:
                logger.warning(f"Could not connect to live Firestore ({e}). Using mock in-memory database.")
                self.use_mock = True
                self.client = None
        else:
            self.use_mock = True

    def _load_seed_data(self):
        """Seed sample requisitions if mock store is empty."""
        now_str = datetime.now(timezone.utc).isoformat()
        if not self._mock_requisitions:
            sample_reqs = [
                {
                    "requisition_id": "REQ-1001",
                    "requester_name": "Alice Smith",
                    "cost_center": "CC-FIN-101",
                    "amount": 450.00,
                    "item_category": "Office Supplies",
                    "line_manager_id": "MGR-201",
                    "department_head_id": "DH-301",
                    "fallback_approver_id": "DELEGATE_VP",
                    "created_at": now_str,
                    "last_updated_at": now_str,
                    "status": "APPROVED",
                    "current_approver": "COMPLETED",
                    "history": [
                        {
                            "actor": "SYSTEM_AUTO",
                            "previous_status": "PENDING",
                            "new_status": "APPROVED",
                            "timestamp": now_str,
                            "comments": "Auto-approved by BPM Rule 1 (Amount < $10,000 non-consulting)."
                        }
                    ],
                    "bpm_routing": {
                        "requisition_id": "REQ-1001",
                        "amount": 450.00,
                        "item_category": "Office Supplies",
                        "rule_applied": "Rule 1: Amount < $10,000 & Category != Consulting",
                        "current_step": "Auto-Approved",
                        "current_approver": "SYSTEM_AUTO",
                        "required_approvers": [],
                        "next_status": "APPROVED",
                        "reasoning": "Amount is below $10,000 and non-consulting. Automatically approved by BPM Rule 1."
                    }
                },
                {
                    "requisition_id": "REQ-1002",
                    "requester_name": "Bob Jones",
                    "cost_center": "CC-ENG-202",
                    "amount": 25000.00,
                    "item_category": "Hardware",
                    "line_manager_id": "MGR-202",
                    "department_head_id": "DH-302",
                    "fallback_approver_id": "DELEGATE_VP",
                    "created_at": now_str,
                    "last_updated_at": now_str,
                    "status": "PENDING_LINE_MANAGER",
                    "current_approver": "MGR-202",
                    "history": [],
                    "bpm_routing": {
                        "requisition_id": "REQ-1002",
                        "amount": 25000.00,
                        "item_category": "Hardware",
                        "rule_applied": "Rule 2: $10,000 <= Amount <= $50,000",
                        "current_step": "Line Manager Review (Step 1/2)",
                        "current_approver": "MGR-202",
                        "required_approvers": ["MGR-202", "DH-302"],
                        "next_status": "PENDING_LINE_MANAGER",
                        "reasoning": "Requisitions between $10,000 and $50,000 require multi-step approval (Line Manager -> Department Head) by BPM Rule 2."
                    }
                },
                {
                    "requisition_id": "REQ-1003",
                    "requester_name": "Carol Danvers",
                    "cost_center": "CC-EXEC-303",
                    "amount": 75000.00,
                    "item_category": "Software",
                    "line_manager_id": "MGR-203",
                    "department_head_id": "DH-303",
                    "fallback_approver_id": "DELEGATE_VP",
                    "created_at": now_str,
                    "last_updated_at": now_str,
                    "status": "PENDING_FINANCE_VP",
                    "current_approver": "FINANCE_VP",
                    "history": [
                        {
                            "actor": "MGR-203",
                            "previous_status": "PENDING_LINE_MANAGER",
                            "new_status": "PENDING_FINANCE_VP",
                            "timestamp": now_str,
                            "comments": "Line Manager approved. Advanced to Finance VP per BPM Rule 3."
                        }
                    ],
                    "bpm_routing": {
                        "requisition_id": "REQ-1003",
                        "amount": 75000.00,
                        "item_category": "Software",
                        "rule_applied": "Rule 3: Amount > $50,000",
                        "current_step": "Finance VP Review (Step 2/3)",
                        "current_approver": "FINANCE_VP",
                        "required_approvers": ["MGR-203", "FINANCE_VP", "PROCUREMENT_DIR"],
                        "next_status": "PENDING_FINANCE_VP",
                        "reasoning": "Requisitions above $50,000 require multi-step approval (Line Manager -> Finance VP -> Procurement Director) by BPM Rule 3."
                    }
                }
            ]
            for req in sample_reqs:
                self._mock_requisitions[req["requisition_id"]] = req

    # --- Requisition CRUD Functions ---

    def create_requisition(self, req: Requisition) -> Requisition:
        if not req.last_updated_at:
            req.last_updated_at = datetime.now(timezone.utc).isoformat()
        req_dict = req.model_dump()

        if not self.use_mock and self.client:
            try:
                doc_ref = self.client.collection(f"{self.collection_prefix}requisitions").document(req.requisition_id)
                doc_ref.set(req_dict)
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore write error ({e}). Fallback to mock store.")
                self.use_mock = True
                self._mock_requisitions[req.requisition_id] = req_dict
        else:
            self._mock_requisitions[req.requisition_id] = req_dict

        return req

    def get_requisition(self, requisition_id: str) -> Optional[Requisition]:
        if not self.use_mock and self.client:
            try:
                doc_ref = self.client.collection(f"{self.collection_prefix}requisitions").document(requisition_id)
                doc = doc_ref.get()
                if doc.exists:
                    return Requisition(**doc.to_dict())
                return None
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore read error ({e}). Fallback to mock store.")
                self.use_mock = True
                data = self._mock_requisitions.get(requisition_id)
                return Requisition(**data) if data else None
        else:
            data = self._mock_requisitions.get(requisition_id)
            return Requisition(**data) if data else None

    def list_requisitions(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[Requisition]:
        results = []
        if not self.use_mock and self.client:
            try:
                query = self.client.collection(f"{self.collection_prefix}requisitions")
                if status:
                    query = query.where(filter=firestore.FieldFilter("status", "==", status))
                if category:
                    query = query.where(filter=firestore.FieldFilter("item_category", "==", category))
                docs = query.stream()
                for doc in docs:
                    results.append(Requisition(**doc.to_dict()))
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore query error ({e}). Fallback to mock store.")
                self.use_mock = True
                for item in self._mock_requisitions.values():
                    if status and item.get("status") != status:
                        continue
                    if category and item.get("item_category") != category:
                        continue
                    results.append(Requisition(**item))
        else:
            for item in self._mock_requisitions.values():
                if status and item.get("status") != status:
                    continue
                if category and item.get("item_category") != category:
                    continue
                results.append(Requisition(**item))

        # Sort by creation timestamp descending
        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def update_requisition_status(
        self,
        requisition_id: str,
        new_status: RequisitionStatus,
        actor: str,
        comments: Optional[str] = None
    ) -> Optional[Requisition]:
        req = self.get_requisition(requisition_id)
        if not req:
            return None

        previous_status = req.status
        now_str = datetime.now(timezone.utc).isoformat()
        req.status = new_status
        req.last_updated_at = now_str

        audit_entry = ApprovalAuditEntry(
            actor=actor,
            previous_status=previous_status,
            new_status=new_status,
            timestamp=now_str,
            comments=comments
        )
        req.history.append(audit_entry)

        req_dict = req.model_dump()
        if not self.use_mock and self.client:
            try:
                doc_ref = self.client.collection(f"{self.collection_prefix}requisitions").document(requisition_id)
                doc_ref.set(req_dict)
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore update error ({e}). Fallback to mock store.")
                self.use_mock = True
                self._mock_requisitions[requisition_id] = req_dict
        else:
            self._mock_requisitions[requisition_id] = req_dict

        return req

    def delete_requisition(self, requisition_id: str) -> bool:
        if not self.use_mock and self.client:
            try:
                doc_ref = self.client.collection(f"{self.collection_prefix}requisitions").document(requisition_id)
                doc_ref.delete()
                return True
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore delete error ({e}). Fallback to mock store.")
                self.use_mock = True
                if requisition_id in self._mock_requisitions:
                    del self._mock_requisitions[requisition_id]
                    return True
                return False
        else:
            if requisition_id in self._mock_requisitions:
                del self._mock_requisitions[requisition_id]
                return True
            return False

    # --- Session History Functions ---

    def save_session_message(self, session_id: str, message: ChatMessage):
        msg_dict = message.model_dump()
        if not self.use_mock and self.client:
            try:
                session_ref = self.client.collection(f"{self.collection_prefix}sessions").document(session_id)
                session_ref.collection("messages").add(msg_dict)
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore session save error ({e}). Fallback to mock store.")
                self.use_mock = True
                if session_id not in self._mock_sessions:
                    self._mock_sessions[session_id] = []
                self._mock_sessions[session_id].append(msg_dict)
        else:
            if session_id not in self._mock_sessions:
                self._mock_sessions[session_id] = []
            self._mock_sessions[session_id].append(msg_dict)

    def get_session_history(self, session_id: str) -> List[ChatMessage]:
        messages = []
        if not self.use_mock and self.client:
            try:
                msgs_stream = (
                    self.client.collection(f"{self.collection_prefix}sessions")
                    .document(session_id)
                    .collection("messages")
                    .order_by("timestamp")
                    .stream()
                )
                for m in msgs_stream:
                    messages.append(ChatMessage(**m.to_dict()))
            except (GoogleAPICallError, PermissionDenied) as e:
                logger.warning(f"Firestore session read error ({e}). Fallback to mock store.")
                self.use_mock = True
                raw_list = self._mock_sessions.get(session_id, [])
                messages = [ChatMessage(**m) for m in raw_list]
        else:
            raw_list = self._mock_sessions.get(session_id, [])
            messages = [ChatMessage(**m) for m in raw_list]
        return messages


# Global database service singleton
db_service = FirestoreService()

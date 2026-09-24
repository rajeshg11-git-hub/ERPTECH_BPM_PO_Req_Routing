from typing import List, Tuple
from schemas import Requisition, RequisitionStatus, PolicyEvaluationResult


class ApprovalPolicyEngine:
    """
    Evaluates dynamic business rules and compliance thresholds for PO Requisitions.
    """

    AUTO_APPROVAL_LIMIT = 1000.00  # < $1,000 can be auto-approved for low risk
    STANDARD_APPROVAL_LIMIT = 10000.00  # $1,000 - $10,000 requires Line Manager + Dept Head
    HIGH_VALUE_THRESHOLD = 10000.00  # > $10,000 requires VP/CFO escalation

    HIGH_RISK_CATEGORIES = ["Consulting"]
    LOW_RISK_CATEGORIES = ["Office Supplies"]

    @classmethod
    def evaluate(cls, req: Requisition) -> PolicyEvaluationResult:
        notes: List[str] = []
        required_approvers: List[str] = []
        is_compliant = True
        risk_level = "LOW"
        auto_eligible = False
        recommended_status = RequisitionStatus.PENDING

        amount = req.amount
        category = req.item_category

        # 1. Evaluate Category Risk
        if category in cls.HIGH_RISK_CATEGORIES:
            risk_level = "HIGH"
            notes.append(f"Category '{category}' is designated high-risk requiring executive review.")
        elif category in cls.LOW_RISK_CATEGORIES and amount < cls.AUTO_APPROVAL_LIMIT:
            risk_level = "LOW"
        else:
            risk_level = "MEDIUM"

        # 2. Evaluate Amount Thresholds & Approval Pathway
        if amount < cls.AUTO_APPROVAL_LIMIT and category != "Consulting":
            auto_eligible = True
            recommended_status = RequisitionStatus.APPROVED
            required_approvers.append(req.line_manager_id)
            notes.append(f"Amount (${amount:,.2f}) is below ${cls.AUTO_APPROVAL_LIMIT:,.2f} threshold. Eligible for automatic approval.")
        elif amount <= cls.STANDARD_APPROVAL_LIMIT:
            recommended_status = RequisitionStatus.PENDING
            required_approvers.extend([req.line_manager_id, req.department_head_id])
            notes.append(f"Amount (${amount:,.2f}) requires Line Manager ({req.line_manager_id}) and Department Head ({req.department_head_id}) sign-off.")
        else:
            # Over $10,000 or high risk consulting
            recommended_status = RequisitionStatus.ESCALATED
            risk_level = "HIGH"
            required_approvers.extend([req.department_head_id, "VP-FINANCE", "CFO-DESK"])
            notes.append(f"High-value amount (${amount:,.2f}) exceeds standard approval limits (${cls.STANDARD_APPROVAL_LIMIT:,.2f}). Escalated to Executive Finance.")

        # 3. Cost Center Validation
        if not req.cost_center or not req.cost_center.startswith("CC-"):
            is_compliant = False
            notes.append("Warning: Invalid or missing Cost Center format. Expected format 'CC-XXX'.")

        return PolicyEvaluationResult(
            is_compliant=is_compliant,
            recommended_status=recommended_status,
            required_approvers=required_approvers,
            auto_approval_eligible=auto_eligible,
            policy_notes=notes,
            risk_level=risk_level
        )

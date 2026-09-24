import os
import logging
from typing import List, Optional
import matplotlib
matplotlib.use('Agg')  # Headless backend
import matplotlib.pyplot as plt
import matplotlib.patches as patches

logger = logging.getLogger("diagram_generator")

DIAGRAMS_DIR = os.path.join(os.path.dirname(__file__), "static", "diagrams")
os.makedirs(DIAGRAMS_DIR, exist_ok=True)


def generate_workflow_diagram(
    requisition_id: str,
    requester_name: str,
    required_approvers: List[str],
    current_approver: Optional[str] = None,
    status: str = "PENDING"
) -> str:
    """
    Generates a PNG workflow hierarchy flowchart (Requester -> Approver 1 -> Approver 2 -> ...)
    and saves it to static/diagrams/{requisition_id}.png.
    Returns the relative image URL path '/static/diagrams/{requisition_id}.png'.
    """
    try:
        nodes = [f"Requester:\n{requester_name}"] + [f"Approver:\n{app}" for app in required_approvers]
        if not required_approvers:

            nodes.append("Auto-Approved\n(SYSTEM)")

        num_nodes = len(nodes)
        fig, ax = plt.subplots(figsize=(max(7, num_nodes * 2.8), 2.8), dpi=150)
        ax.set_facecolor('#0f172a')
        fig.patch.set_facecolor('#0f172a')

        y_pos = 0.5
        x_positions = [0.1 + i * (0.8 / max(1, num_nodes - 1)) for i in range(num_nodes)] if num_nodes > 1 else [0.5]

        for i, (node_text, x) in enumerate(zip(nodes, x_positions)):
            # Colors based on node step and current status
            if "Requester" in node_text:
                box_color = '#38bdf8'  # Accent blue
                edge_color = '#0284c7'
            elif current_approver and current_approver in node_text:
                box_color = '#f59e0b'  # Pending yellow
                edge_color = '#d97706'
            elif status == "APPROVED":
                box_color = '#10b981'  # Green
                edge_color = '#059669'
            elif "ESCALATED" in status:
                box_color = '#ef4444'  # Red
                edge_color = '#dc2626'
            else:
                box_color = '#6366f1'  # Indigo
                edge_color = '#4f46e5'

            box = patches.FancyBboxPatch(
                (x - 0.08, y_pos - 0.22),
                0.16, 0.44,
                boxstyle="round,pad=0.03,rounding_size=0.05",
                facecolor=box_color,
                edgecolor=edge_color,
                linewidth=2,
                alpha=0.9
            )
            ax.add_patch(box)

            ax.text(
                x, y_pos, node_text,
                color='#ffffff',
                fontsize=9,
                fontweight='bold',
                ha='center', va='center',
                wrap=True
            )

            # Draw arrow to next node
            if i < num_nodes - 1:
                next_x = x_positions[i + 1]
                ax.annotate(
                    '',
                    xy=(next_x - 0.09, y_pos),
                    xytext=(x + 0.09, y_pos),
                    arrowprops=dict(
                        arrowstyle='->',
                        lw=2.5,
                        color='#94a3b8',
                        mutation_scale=15
                    )
                )

        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis('off')
        plt.title(f"BPM Approval Hierarchy Diagram: {requisition_id}", color='#f8fafc', fontsize=11, fontweight='bold', pad=12)

        file_path = os.path.join(DIAGRAMS_DIR, f"{requisition_id}.png")
        plt.tight_layout()
        plt.savefig(file_path, facecolor=fig.get_facecolor(), edgecolor='none')
        plt.close(fig)

        logger.info(f"Generated workflow diagram for {requisition_id} at {file_path}")
        return f"/static/diagrams/{requisition_id}.png"

    except Exception as e:
        logger.error(f"Error generating diagram for {requisition_id}: {e}")
        return f"/static/diagrams/default.png"

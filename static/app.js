document.addEventListener('DOMContentLoaded', () => {
    const API_BASE = '/api';
    let currentSessionId = 'session-' + Math.floor(Math.random() * 10000);

    // DOM Elements
    const requisitionsTbody = document.getElementById('requisitions-tbody');
    const filterStatus = document.getElementById('filter-status');
    const filterCategory = document.getElementById('filter-category');
    const refreshBtn = document.getElementById('refresh-btn');
    const staleCheckBtn = document.getElementById('stale-check-btn');
    
    const metricTotal = document.getElementById('metric-total');
    const metricPending = document.getElementById('metric-pending');
    const metricApproved = document.getElementById('metric-approved');
    const metricEscalated = document.getElementById('metric-escalated');

    const openNewModalBtn = document.getElementById('open-new-modal-btn');
    const createModal = document.getElementById('create-modal');
    const createReqForm = document.getElementById('create-req-form');
    
    const detailModal = document.getElementById('detail-modal');
    const modalReqTitle = document.getElementById('modal-req-title');
    const modalReqBody = document.getElementById('modal-req-body');
    const modalReqFooter = document.getElementById('modal-req-footer');

    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');

    const navItems = document.querySelectorAll('.nav-item');
    const tabPanes = document.querySelectorAll('.tab-pane');

    // --- Tab Switching ---
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            navItems.forEach(n => n.classList.remove('active'));
            tabPanes.forEach(p => p.classList.remove('active'));

            item.classList.add('active');
            const targetTab = item.getAttribute('data-tab');
            if (targetTab === 'agent-chat') {
                document.getElementById('agent-chat-tab').classList.add('active');
            } else {
                document.getElementById('requisitions-tab').classList.add('active');
            }
        });
    });

    // --- Fetch & Render Requisitions ---
    async function loadRequisitions() {
        try {
            const status = filterStatus.value;
            const category = filterCategory.value;
            let url = `${API_BASE}/requisitions?`;
            if (status) url += `status=${status}&`;
            if (category) url += `category=${encodeURIComponent(category)}&`;

            const res = await fetch(url);
            const reqs = await res.json();

            renderTable(reqs);
            updateMetrics(reqs);
        } catch (err) {
            console.error("Error loading requisitions:", err);
        }
    }

    function renderTable(reqs) {
        requisitionsTbody.innerHTML = '';
        if (reqs.length === 0) {
            requisitionsTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color: var(--text-muted);">No requisitions found.</td></tr>`;
            return;
        }

        reqs.forEach(req => {
            const tr = document.createElement('tr');
            const statusVal = req.status;

            tr.innerHTML = `
                <td><strong>${req.requisition_id}</strong></td>
                <td>${escapeHtml(req.requester_name)}</td>
                <td>${escapeHtml(req.item_category)}</td>
                <td><strong>$${req.amount.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}</strong></td>
                <td><span class="status-badge ${statusVal}">${statusVal}</span></td>
                <td><code>${escapeHtml(req.current_approver || 'N/A')}</code></td>
                <td>
                    <button class="btn btn-secondary btn-sm view-btn" data-id="${req.requisition_id}">
                        <i class="fa-solid fa-eye"></i> Details & Route
                    </button>
                </td>
            `;
            requisitionsTbody.appendChild(tr);
        });

        // Add event listeners to view buttons
        document.querySelectorAll('.view-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const reqId = btn.getAttribute('data-id');
                openDetailModal(reqId);
            });
        });
    }

    function updateMetrics(reqs) {
        metricTotal.textContent = reqs.length;
        metricPending.textContent = reqs.filter(r => r.status.includes('PENDING')).length;
        metricApproved.textContent = reqs.filter(r => r.status === 'APPROVED').length;
        metricEscalated.textContent = reqs.filter(r => r.status.includes('ESCALATED')).length;
    }

    // --- Detail & BPM Route Modal ---
    async function openDetailModal(reqId) {
        try {
            const res = await fetch(`${API_BASE}/requisitions/${reqId}`);
            if (!res.ok) return;
            const req = await res.json();
            const bpm = req.bpm_routing || {};

            modalReqTitle.textContent = `BPM Routing Details - ${req.requisition_id}`;
            
            const historyHtml = req.history.map(h => `
                <div style="background: rgba(15, 23, 42, 0.4); padding: 8px 12px; border-radius: 8px; margin-top: 6px; font-size: 12px;">
                    <strong>${h.actor}</strong> ➔ <span class="status-badge ${h.new_status}">${h.new_status}</span>
                    <p style="color: var(--text-secondary); margin-top: 2px;">${h.comments || 'No comments'}</p>
                </div>
            `).join('') || '<p style="color: var(--text-muted); font-size: 12px;">No historical audit records yet.</p>';

            const ragPolicies = (bpm.rag_policies_retrieved || []).map(p => `<li>${escapeHtml(p)}</li>`).join('') || '<li>Standard policy compliance.</li>';

            modalReqBody.innerHTML = `
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 14px; margin-bottom: 16px;">
                    <div><strong>Requester:</strong> ${escapeHtml(req.requester_name)}</div>
                    <div><strong>Cost Center:</strong> ${escapeHtml(req.cost_center)}</div>
                    <div><strong>Category:</strong> ${escapeHtml(req.item_category)}</div>
                    <div><strong>Amount:</strong> $${req.amount.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
                    <div><strong>Current Status:</strong> <span class="status-badge ${req.status}">${req.status}</span></div>
                    <div><strong>Pending Approver:</strong> <code>${req.current_approver || 'N/A'}</code></div>
                    <div><strong>Fallback Delegate:</strong> <code>${req.fallback_approver_id || 'DELEGATE_VP'}</code></div>
                </div>

                <div style="background: rgba(30, 41, 59, 0.6); padding: 14px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 16px;">
                    <h4 style="font-size: 13px; color: var(--accent-blue); text-transform: uppercase;">BPM Routing Engine & Vertex AI RAG</h4>
                    <p style="font-size: 13px; margin-top: 4px;"><strong>Applied Rule:</strong> ${escapeHtml(bpm.rule_applied || 'N/A')}</p>
                    <p style="font-size: 13px; margin-top: 2px;"><strong>Current Step:</strong> ${escapeHtml(bpm.current_step || 'N/A')}</p>
                    <p style="font-size: 13px; margin-top: 2px;"><strong>Required Approvers:</strong> <code>${(bpm.required_approvers || []).join(' ➔ ') || 'None'}</code></p>
                    
                    <div style="margin-top: 8px; font-size: 12px; color: var(--text-secondary);">
                        <strong>Vertex AI RAG Grounded Policies:</strong>
                        <ul style="margin-left: 18px; margin-top: 4px;">${ragPolicies}</ul>
                    </div>
                    
                    <p style="font-size: 13px; margin-top: 8px; color: var(--text-secondary);"><em>${escapeHtml(bpm.reasoning || '')}</em></p>
                </div>


                <div>
                    <h4 style="font-size: 13px; color: var(--text-secondary); text-transform: uppercase;">Audit History:</h4>
                    ${historyHtml}
                </div>
            `;

            modalReqFooter.innerHTML = `
                <button class="btn btn-secondary update-status-btn" data-id="${req.requisition_id}" data-status="REJECTED">Reject</button>
                <button class="btn btn-primary advance-bpm-btn" data-id="${req.requisition_id}">Advance BPM Step</button>
            `;

            detailModal.classList.add('show');

            document.querySelectorAll('.advance-bpm-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    await fetch(`${API_BASE}/requisitions/${id}/route?actor=Manager`, { method: 'POST' });
                    detailModal.classList.remove('show');
                    loadRequisitions();
                });
            });

            document.querySelectorAll('.update-status-btn').forEach(btn => {
                btn.addEventListener('click', async () => {
                    const id = btn.getAttribute('data-id');
                    const newStatus = btn.getAttribute('data-status');
                    await updateStatus(id, newStatus, 'Manager');
                    detailModal.classList.remove('show');
                });
            });

        } catch (err) {
            console.error("Error opening details:", err);
        }
    }

    async function updateStatus(reqId, newStatus, actor) {
        try {
            await fetch(`${API_BASE}/requisitions/${reqId}/status`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    status: newStatus,
                    actor: actor,
                    comments: `Status updated to ${newStatus} from Web Dashboard.`
                })
            });
            loadRequisitions();
        } catch (err) {
            console.error("Error updating status:", err);
        }
    }

    // 48-Hour Inactivity Escalation Check
    staleCheckBtn.addEventListener('click', async () => {
        try {
            const res = await fetch(`${API_BASE}/requisitions/check-stale`, { method: 'POST' });
            const staleList = await res.json();
            alert(`48-Hour Inactivity Check Complete: Escalated ${staleList.length} request(s) to fallback user delegates.`);
            loadRequisitions();
        } catch (err) {
            console.error("Error running stale check:", err);
        }
    });

    // --- Modal Controls ---
    openNewModalBtn.addEventListener('click', () => createModal.classList.add('show'));
    document.querySelectorAll('.close-modal').forEach(el => el.addEventListener('click', () => detailModal.classList.remove('show')));
    document.querySelectorAll('.close-create-modal').forEach(el => el.addEventListener('click', () => createModal.classList.remove('show')));

    // Form Submission for New Requisition
    createReqForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const payload = {
            requester_name: document.getElementById('create-requester').value,
            cost_center: document.getElementById('create-cost-center').value,
            amount: parseFloat(document.getElementById('create-amount').value),
            item_category: document.getElementById('create-category').value,
            line_manager_id: document.getElementById('create-line-manager').value,
            department_head_id: document.getElementById('create-dept-head').value,
            fallback_approver_id: document.getElementById('create-fallback').value || 'DELEGATE_VP'
        };

        try {
            const res = await fetch(`${API_BASE}/requisitions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (res.ok) {
                createModal.classList.remove('show');
                createReqForm.reset();
                loadRequisitions();
            }
        } catch (err) {
            console.error("Error creating requisition:", err);
        }
    });

    // --- Agent Chat & A2UI Actions ---
    async function sendMessageToAgent(text, targetReqId = null) {
        appendMessage('user', text);
        chatInput.value = '';

        try {
            const res = await fetch(`${API_BASE}/agent/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: currentSessionId,
                    message: text,
                    requisition_id: targetReqId
                })
            });
            const data = await res.json();
            appendMessage('assistant', data.response, data.a2ui_components);
            loadRequisitions();
        } catch (err) {
            appendMessage('assistant', "⚠️ Error connecting to POApprovalAgent server.");
        }
    }

    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text) sendMessageToAgent(text);
    });

    window.triggerA2UIAction = function(reqId, action) {
        if (action === 'approve') sendMessageToAgent(`Approve ${reqId}`, reqId);
        else if (action === 'reject') sendMessageToAgent(`Reject ${reqId}`, reqId);
        else if (action === 'escalate') sendMessageToAgent(`Escalate ${reqId}`, reqId);
    };

    window.submitA2UIForm = function() {
        const amount = document.getElementById('a2ui-amount').value;
        const currency = document.getElementById('a2ui-currency').value;
        const category = document.getElementById('a2ui-category').value;
        const cc = document.getElementById('a2ui-costcenter').value;
        const msg = `Create new requisition for $${amount} ${currency} in ${category} for cost center ${cc}`;
        sendMessageToAgent(msg);
    };

    function appendMessage(role, text, a2uiComponents = []) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-msg ${role}`;
        
        let html = formatMarkdown(escapeHtml(text));

        // Render A2UI Components
        if (a2uiComponents && a2uiComponents.length > 0) {
            a2uiComponents.forEach(comp => {
                if (comp.type === 'status_card') {
                    html += `
                        <div class="a2ui-card a2ui-status-card ${comp.status_color || 'yellow'}">
                            <div class="a2ui-header">
                                <strong>${comp.requisition_id}</strong>
                                <span class="status-badge ${comp.status}">${comp.status}</span>
                            </div>
                            <div style="font-size: 13px; color: var(--text-secondary);">
                                <div>Category: <strong>${escapeHtml(comp.category)}</strong></div>
                                <div>Amount: <strong>${comp.amount_display}</strong></div>
                                <div>Pending Approver: <code>${escapeHtml(comp.approver)}</code></div>
                            </div>
                        </div>
                    `;
                } else if (comp.type === 'workflow_diagram' && comp.diagram_url) {
                    html += `
                        <div style="margin-top: 10px;">
                            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">BPM Workflow Hierarchy Diagram:</div>
                            <img src="${comp.diagram_url}" class="a2ui-diagram-img" alt="Workflow Diagram" onclick="window.open(this.src)">
                        </div>
                    `;
                } else if (comp.type === 'action_buttons') {
                    const btnsHtml = (comp.buttons || []).map(b => `
                        <button class="a2ui-btn ${b.style}" onclick="triggerA2UIAction('${comp.requisition_id}', '${b.action}')">${b.label}</button>
                    `).join('');
                    html += `<div class="a2ui-actions">${btnsHtml}</div>`;
                } else if (comp.type === 'approval_form') {
                    html += `
                        <div class="a2ui-card">
                            <h4 style="font-size: 13px; color: var(--accent-blue); margin-bottom: 8px;">${escapeHtml(comp.title || 'Requisition Approval Form')}</h4>
                            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;">
                                <div>
                                    <label style="display:block; color: var(--text-muted);">Amount</label>
                                    <input type="number" id="a2ui-amount" value="25000" style="width:100%; padding: 4px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: #fff; border-radius: 4px;">
                                </div>
                                <div>
                                    <label style="display:block; color: var(--text-muted);">Currency</label>
                                    <select id="a2ui-currency" style="width:100%; padding: 4px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: #fff; border-radius: 4px;">
                                        <option value="USD">USD</option>
                                        <option value="EUR">EUR</option>
                                        <option value="GBP">GBP</option>
                                    </select>
                                </div>
                                <div>
                                    <label style="display:block; color: var(--text-muted);">Category</label>
                                    <select id="a2ui-category" style="width:100%; padding: 4px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: #fff; border-radius: 4px;">
                                        <option value="Hardware">Hardware</option>
                                        <option value="Software">Software</option>
                                        <option value="Consulting">Consulting</option>
                                    </select>
                                </div>
                                <div>
                                    <label style="display:block; color: var(--text-muted);">Cost Center</label>
                                    <input type="text" id="a2ui-costcenter" value="CC-ENG-101" style="width:100%; padding: 4px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: #fff; border-radius: 4px;">
                                </div>
                            </div>
                            <button class="a2ui-btn btn-success" style="width:100%; margin-top:10px;" onclick="submitA2UIForm()">Submit Requisition</button>
                        </div>
                    `;
                }
            });
        }

        msgDiv.innerHTML = html;
        chatMessages.appendChild(msgDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function formatMarkdown(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    function escapeHtml(str) {
        return (str || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Initial greeting in chat
    appendMessage('assistant', "Hello! I am **POApprovalAgent** with A2UI rich components, Python sandbox landed cost calculation, and workflow diagram generator.\n\nTry asking `Approve REQ-1002` or `Check status of REQ-1003`.", [
        {
            "type": "approval_form",
            "title": "Interactive Requisition Approval Form"
        }
    ]);


    filterStatus.addEventListener('change', loadRequisitions);
    filterCategory.addEventListener('change', loadRequisitions);
    refreshBtn.addEventListener('click', loadRequisitions);

    loadRequisitions();
});

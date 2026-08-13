/**
 * Cloud Control Panel - Admin module (instances CRUD, operator assignment)
 */

import { state, api, showToast, escapeHtml } from './utils.js';
import { refreshInstances } from './instances.js';

export function showAddInstanceForm() {
    document.getElementById("instance-form").classList.remove("hidden");
    document.getElementById("inst-id").value = "";
    document.getElementById("inst-id").disabled = false;
    document.getElementById("inst-name").value = "";
    document.getElementById("inst-ec2-id").value = "";
    document.getElementById("inst-desc").value = "";
    document.getElementById("inst-port").value = "";
    document.getElementById("inst-inline-group").classList.add("hidden");

    // Populate groups dropdown
    const select = document.getElementById("inst-group");
    const groups = state.cachedInstancesData?.groups || [];
    select.innerHTML = '<option value="">Sin grupo (independiente)</option>' +
        groups.map(g => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("");

    renderOperatorAssignment("inst");
}

export function showInlineGroupCreate() {
    const inline = document.getElementById("inst-inline-group");
    inline.classList.toggle("hidden");
    if (!inline.classList.contains("hidden")) {
        document.getElementById("inst-new-grp-id").value = "";
        document.getElementById("inst-new-grp-name").value = "";
        document.getElementById("inst-new-grp-color").value = "#6366f1";
    }
}

export function cancelInstanceForm() {
    document.getElementById("instance-form").classList.add("hidden");
    document.getElementById("inst-id").disabled = false;
    const saveBtn = document.querySelector("#instance-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear instancia"; }
}

export async function saveInstance() {
    const id = document.getElementById("inst-id").value.trim();
    const isEditing = document.getElementById("inst-id").disabled;
    const name = document.getElementById("inst-name").value.trim();
    const instanceId = document.getElementById("inst-ec2-id").value.trim();
    const description = document.getElementById("inst-desc").value.trim();
    const port = document.getElementById("inst-port").value.trim();
    let group = document.getElementById("inst-group").value || null;

    if (!id) { showToast("ID es requerido"); return; }
    if (!name) { showToast("Nombre es requerido"); return; }
    if (!instanceId) { showToast("Instance ID de EC2 es requerido"); return; }

    // Check if creating inline group
    const inlineGroup = document.getElementById("inst-inline-group");
    if (!inlineGroup.classList.contains("hidden")) {
        const grpId = document.getElementById("inst-new-grp-id").value.trim();
        const grpName = document.getElementById("inst-new-grp-name").value.trim();
        const grpColor = document.getElementById("inst-new-grp-color").value;
        if (grpId && grpName) {
            try {
                await api("POST", `/accounts/${state.currentAccountId}/groups`, {
                    id: grpId, name: grpName, description: "", color: grpColor,
                    startOrder: [id], stopOrder: [id]
                });
                group = grpId;
            } catch (e) { showToast("Error creando grupo"); return; }
        }
    }

    try {
        await api("POST", `/accounts/${state.currentAccountId}/instances`, {
            id, name, instanceId, description,
            dashboardPort: port ? parseInt(port) : null,
            group
        });

        // Update operator/admin access
        await updateOperatorAccess("inst");

        showToast(isEditing ? "Instancia actualizada" : "Instancia creada");
        cancelInstanceForm();
        refreshInstances();
    } catch (e) { showToast("Error guardando instancia"); }
}

export async function deleteInstance(instanceId) {
    if (!confirm(`Eliminar la instancia "${instanceId}" de la configuracion?`)) return;
    try {
        await api("DELETE", `/accounts/${state.currentAccountId}/instances/${instanceId}`);
        showToast("Instancia eliminada");
        refreshInstances();
    } catch (e) { showToast("Error eliminando instancia"); }
}

export function editInstance(instanceId) {
    const instances = state.cachedInstancesData?.instances || [];
    const inst = instances.find(i => i.id === instanceId);
    if (!inst) return;

    // Open the instance form pre-filled
    document.getElementById("instance-form").classList.remove("hidden");
    document.getElementById("inst-id").value = inst.id;
    document.getElementById("inst-id").disabled = true;
    document.getElementById("inst-name").value = inst.name || "";
    document.getElementById("inst-ec2-id").value = inst.instanceId || "";
    document.getElementById("inst-desc").value = inst.description || "";
    document.getElementById("inst-port").value = inst.dashboardPort || "";
    document.getElementById("inst-inline-group").classList.add("hidden");

    // Populate groups dropdown and select current
    const select = document.getElementById("inst-group");
    const groups = state.cachedInstancesData?.groups || [];
    select.innerHTML = '<option value="">Sin grupo (independiente)</option>' +
        groups.map(g => `<option value="${g.id}" ${g.id === inst.group ? 'selected' : ''}>${escapeHtml(g.name)}</option>`).join("");

    renderOperatorAssignment("inst");

    // Change button to "Guardar"
    const saveBtn = document.querySelector("#instance-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Guardar cambios"; }
}

// ─── Operator Assignment ───────────────────────────────────────────────

export async function renderOperatorAssignment(prefix) {
    const adminsContainer = document.getElementById(`${prefix}-admins`);
    const opsContainer = document.getElementById(`${prefix}-operators`);

    try {
        const data = await api("GET", "/keys/list");
        const admins = (data.keys || []).filter(k => k.role === "admin");
        const operators = (data.keys || []).filter(k => k.role === "operator");

        // Render admins
        if (adminsContainer) {
            if (admins.length === 0) {
                adminsContainer.innerHTML = '<span class="muted">No hay admins</span>';
            } else {
                adminsContainer.innerHTML = admins.map(op => {
                    const hasAccess = (op.accounts || []).includes(state.currentAccountId) || (op.accounts || []).includes("*");
                    return `<label class="checkbox-item"><input type="checkbox" value="${op.key}" ${hasAccess ? "checked" : ""}><span>${escapeHtml(op.name)} <small class="role-tag" style="color:#fbbf24">admin</small>${(op.accounts || []).includes("*") ? ' <small style="color:var(--text-muted)">(todas)</small>' : ''}</span></label>`;
                }).join("");
            }
        }

        // Render operators
        if (opsContainer) {
            if (operators.length === 0) {
                opsContainer.innerHTML = '<span class="muted">No hay operadores</span>';
            } else {
                opsContainer.innerHTML = operators.map(op => {
                    const hasAccess = (op.accounts || []).includes(state.currentAccountId) || (op.accounts || []).includes("*");
                    return `<label class="checkbox-item"><input type="checkbox" value="${op.key}" ${hasAccess ? "checked" : ""}><span>${escapeHtml(op.name)} <small class="role-tag" style="color:#34d399">operator</small>${(op.accounts || []).includes("*") ? ' <small style="color:var(--text-muted)">(todas)</small>' : ''}</span></label>`;
                }).join("");
            }
        }
    } catch (e) {
        if (adminsContainer) adminsContainer.innerHTML = '<span class="muted">Error</span>';
        if (opsContainer) opsContainer.innerHTML = '<span class="muted">Error</span>';
    }
}

export async function updateOperatorAccess(prefix) {
    const containers = [
        document.getElementById(`${prefix}-admins`),
        document.getElementById(`${prefix}-operators`)
    ].filter(Boolean);

    if (containers.length === 0) return;

    let keysData;
    try {
        keysData = await api("GET", "/keys/list");
    } catch (e) { return; }
    const allKeys = keysData.keys || [];

    // Get all account IDs for expanding "*" to specific list
    let allAccountIds = [];
    try {
        const accData = await api("GET", "/accounts");
        allAccountIds = (accData.accounts || []).map(a => a.id);
    } catch (e) {}

    let updated = 0;
    for (const container of containers) {
        const checkboxes = container.querySelectorAll("input[type=checkbox]");
        for (const cb of checkboxes) {
            const opKey = cb.value;
            const shouldHaveAccess = cb.checked;
            const opData = allKeys.find(k => k.key === opKey);
            if (!opData) continue;

            let accounts = [...(opData.accounts || [])];
            const hasAll = accounts.includes("*");
            const hasAccess = hasAll || accounts.includes(state.currentAccountId);

            let newAccounts = accounts;

            if (shouldHaveAccess && !hasAccess) {
                // Give access
                if (hasAll) continue; // already has all
                newAccounts = [...accounts, state.currentAccountId];
            } else if (!shouldHaveAccess && hasAccess) {
                // Remove access
                if (hasAll) {
                    // Expand "*" to all accounts except current
                    newAccounts = allAccountIds.filter(id => id !== state.currentAccountId);
                } else {
                    newAccounts = accounts.filter(a => a !== state.currentAccountId);
                }
            } else {
                continue;
            }

            try {
                const result = await api("PUT", `/keys/${opKey}/accounts`, { accounts: newAccounts });
                if (!result.error) updated++;
            } catch (e) {
                // Don't show toast for each failure
            }
        }
    }
    if (updated > 0) {
        showToast(`Acceso actualizado para ${updated} usuario(s)`);
    }
}

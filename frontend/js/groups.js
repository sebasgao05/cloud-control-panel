/**
 * Cloud Control Panel - Groups module
 */

import { state, api, showToast, escapeHtml } from './utils.js';
import { showScreen } from './navigation.js';
import { refreshInstances, renderTypeBadge } from './instances.js';
import { renderOperatorAssignment, updateOperatorAccess } from './admin.js';

export function openGroup(groupId) {
    state.currentGroupId = groupId;
    const groups = state.cachedInstancesData?.groups || [];
    const group = groups.find(g => g.id === groupId);
    if (!group) return;

    document.getElementById("group-title").textContent = group.name;
    document.getElementById("group-description").textContent = group.description || "";
    document.getElementById("group-btn-start").disabled = group.state === "running";
    document.getElementById("group-btn-stop").disabled = group.state === "stopped";

    showScreen("group-screen");
    renderGroupInstances(group);
}

export function renderGroupInstances(group) {
    const container = document.getElementById("group-instances-list");
    const allInstances = state.cachedInstancesData?.instances || [];
    const memberIds = group.members || [];

    const members = memberIds.map(mid => allInstances.find(i => i.id === mid)).filter(Boolean);

    container.innerHTML = members.map(inst => {
        const stateClass = inst.state || "stopped";
        return `
        <div class="instance-item" onclick="openInstance('${inst.id}', true)">
            <div class="instance-info">
                <span class="indicator ${stateClass}"></span>
                <div class="instance-text">
                    <span class="instance-name">${escapeHtml(inst.name)}</span>
                    ${renderTypeBadge(inst.type)}
                    <span class="instance-meta">${inst.instanceId}${inst.publicIp ? ' · ' + inst.publicIp : ''}</span>
                </div>
            </div>
            <div class="instance-right">
                <span class="instance-state-badge ${stateClass}">${inst.state}</span>
                ${inst.uptime ? `<span class="instance-uptime">${inst.uptime}</span>` : ''}
            </div>
        </div>`;
    }).join("");
}

export async function refreshGroupInstances() {
    if (!state.currentAccountId || !state.currentGroupId) return;
    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/instances`);
        state.cachedInstancesData = data;
        const group = (data.groups || []).find(g => g.id === state.currentGroupId);
        if (group) renderGroupInstances(group);
    } catch (e) {}
}

export async function startCurrentGroup() {
    if (!confirm("Encender todas las instancias del grupo?")) return;
    try {
        await api("POST", `/accounts/${state.currentAccountId}/groups/${state.currentGroupId}/start`);
        showToast("Grupo encendiendo...");
        setTimeout(refreshGroupInstances, 3000);
    } catch (e) {
        showToast("Error al encender grupo");
    }
}

export async function stopCurrentGroup() {
    if (!confirm("Apagar todas las instancias del grupo?")) return;
    try {
        await api("POST", `/accounts/${state.currentAccountId}/groups/${state.currentGroupId}/stop`);
        showToast("Grupo apagando...");
        setTimeout(refreshGroupInstances, 3000);
    } catch (e) {
        showToast("Error al apagar grupo");
    }
}

// ─── Admin CRUD (Groups) ───────────────────────────────────────────────

export function showAddGroupForm() {
    document.getElementById("groups-section").classList.remove("hidden");
    document.getElementById("group-form").classList.remove("hidden");
    document.getElementById("grp-id").value = "";
    document.getElementById("grp-name").value = "";
    document.getElementById("grp-desc").value = "";
    document.getElementById("grp-color").value = "#6366f1";
    // Populate instances checkboxes from cached data
    renderGroupInstancesCheckboxes([]);
    renderOperatorAssignment("grp");
}

export function renderGroupInstancesCheckboxes(selected) {
    const container = document.getElementById("grp-instances-checkboxes");
    const instances = state.cachedInstancesData?.instances || [];
    if (instances.length === 0) {
        container.innerHTML = '<span class="muted">No hay instancias en esta cuenta</span>';
        return;
    }
    container.innerHTML = instances.map(inst => {
        const checked = selected.includes(inst.id) ? "checked" : "";
        return `<label class="checkbox-item"><input type="checkbox" value="${inst.id}" ${checked}><span>${escapeHtml(inst.name)} <small style="color:var(--text-muted)">(${inst.id})</small></span></label>`;
    }).join("");
}

export function cancelGroupForm() {
    document.getElementById("group-form").classList.add("hidden");
    document.getElementById("grp-id").disabled = false;
    const saveBtn = document.querySelector("#group-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear grupo"; }
}

export async function saveGroup() {
    const id = document.getElementById("grp-id").value.trim();
    const name = document.getElementById("grp-name").value.trim();
    const description = document.getElementById("grp-desc").value.trim();
    const color = document.getElementById("grp-color").value;

    // Get selected instances from checkboxes
    const checkboxes = document.querySelectorAll("#grp-instances-checkboxes input[type=checkbox]:checked");
    const members = Array.from(checkboxes).map(cb => cb.value);

    if (!id) { showToast("ID es requerido"); return; }
    if (!name) { showToast("Nombre es requerido"); return; }

    try {
        await api("POST", `/accounts/${state.currentAccountId}/groups`, {
            id, name, description, color,
            startOrder: members,
            stopOrder: [...members].reverse()
        });

        // Update operator access
        await updateOperatorAccess("grp");

        showToast("Grupo creado");
        cancelGroupForm();
        refreshInstances();
    } catch (e) { showToast("Error creando grupo"); }
}

export async function deleteGroup(groupId) {
    if (!confirm(`Eliminar el grupo "${groupId}"?`)) return;
    try {
        await api("DELETE", `/accounts/${state.currentAccountId}/groups/${groupId}`);
        showToast("Grupo eliminado");
        refreshInstances();
    } catch (e) { showToast("Error eliminando grupo"); }
}

export function editGroup(groupId) {
    const groups = state.cachedInstancesData?.groups || [];
    const grp = groups.find(g => g.id === groupId);
    if (!grp) return;

    // Open the group form pre-filled
    document.getElementById("groups-section").classList.remove("hidden");
    document.getElementById("group-form").classList.remove("hidden");
    document.getElementById("grp-id").value = grp.id;
    document.getElementById("grp-id").disabled = true;
    document.getElementById("grp-name").value = grp.name || "";
    document.getElementById("grp-desc").value = grp.description || "";
    document.getElementById("grp-color").value = grp.color || "#6366f1";
    renderGroupInstancesCheckboxes(grp.members || []);
    renderOperatorAssignment("grp");

    // Change button to "Guardar"
    const saveBtn = document.querySelector("#group-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Guardar cambios"; }
}

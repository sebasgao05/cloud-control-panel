/**
 * Cloud Control Panel - Instances module
 */

import { state, api, showToast, escapeHtml, logActivity } from './utils.js';
import { showScreen } from './navigation.js';
import { initUptimeChart, destroyUptimeChart } from './uptime-chart.js';
import { initMetricsCharts, destroyMetricsCharts } from './metrics-chart.js';

// ─── Resource Type Badge Helper ────────────────────────────────────────

const RESOURCE_TYPE_LABELS = {
    ec2: "EC2",
    rds: "RDS",
    ecs: "ECS",
    lightsail: "Lightsail",
    apprunner: "AppRunner",
};

/**
 * Returns HTML for a resource type badge.
 * Falls back to "EC2" if type is not recognized (backward compat).
 */
export function renderTypeBadge(type) {
    const normalized = (type || "ec2").toLowerCase();
    const label = RESOURCE_TYPE_LABELS[normalized] || RESOURCE_TYPE_LABELS["ec2"];
    const cssClass = RESOURCE_TYPE_LABELS[normalized] ? normalized : "ec2";
    return `<span class="resource-type-badge resource-type-${cssClass}">${label}</span>`;
}

// ─── View Toggle (Card / Table) ────────────────────────────────────────

const VIEW_PREFERENCE_KEY = "ccp-view-preference";

/**
 * Returns the current view preference from localStorage.
 * Defaults to "card" if no preference is stored.
 */
export function getViewPreference() {
    const stored = localStorage.getItem(VIEW_PREFERENCE_KEY);
    return stored === "table" ? "table" : "card";
}

/**
 * Sets the view preference in localStorage and re-renders without data re-fetch.
 */
export function setViewPreference(preference) {
    const value = preference === "table" ? "table" : "card";
    localStorage.setItem(VIEW_PREFERENCE_KEY, value);
    updateViewToggleButtons(value);
    // Re-render using cached data (no API call)
    if (state.cachedInstancesData) {
        renderSoloInstances(
            state.cachedInstancesData.instances || [],
            state.cachedInstancesData.groups || []
        );
    }
}

/**
 * Updates the toggle button active states.
 */
function updateViewToggleButtons(activeView) {
    const cardBtn = document.getElementById("view-toggle-card");
    const tableBtn = document.getElementById("view-toggle-table");
    if (cardBtn && tableBtn) {
        cardBtn.classList.toggle("active", activeView === "card");
        tableBtn.classList.toggle("active", activeView === "table");
    }
}

export async function refreshInstances() {
    if (!state.currentAccountId) return;

    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/instances`);
        state.cachedInstancesData = data;
        renderGroups(data.groups || []);
        renderSoloInstances(data.instances || [], data.groups || []);
        checkSettingsVisibility();

        // Initialize view toggle button state
        updateViewToggleButtons(getViewPreference());

        // Show add buttons for superadmin only
        const isSuperadmin = state.userRole === "superadmin";
        document.getElementById("btn-add-group").classList.toggle("hidden", !isSuperadmin);
        document.getElementById("btn-add-instance").classList.toggle("hidden", !isSuperadmin);
    } catch (e) {
        if (e.message !== "Unauthorized") {
            showToast("Error cargando instancias");
        }
    }
}

async function checkSettingsVisibility() {
    // Show settings button if scheduler or notifications or costs are available, or user is admin/superadmin
    const btn = document.getElementById("btn-settings-panel");

    // Superadmin and admin ALWAYS see the settings button (they manage keys at minimum)
    if (state.userRole === "superadmin" || state.userRole === "admin") {
        btn.classList.remove("hidden");
        return;
    }

    // For operators, check if any feature is accessible
    try {
        const schedData = await api("GET", `/accounts/${state.currentAccountId}/schedule`);
        const hasScheduler = schedData.enabled && schedData.permissions?.view;
        if (hasScheduler) {
            btn.classList.remove("hidden");
            return;
        }
    } catch (e) {}

    btn.classList.add("hidden");
}

export function renderGroups(groups) {
    const section = document.getElementById("groups-section");
    const container = document.getElementById("groups-list");

    if (groups.length === 0) {
        section.classList.add("hidden");
        return;
    }

    section.classList.remove("hidden");
    container.innerHTML = groups.map(grp => {
        const stateClass = grp.state || "stopped";
        const groupColor = grp.color || "#6366f1";
        return `
        <div class="group-item clickable" style="--group-color: ${groupColor}" onclick="openGroup('${grp.id}')">
            <div class="group-header">
                <div class="group-info">
                    <span class="indicator ${stateClass}"></span>
                    <span class="group-name">${escapeHtml(grp.name)}</span>
                    <span class="group-state-badge ${stateClass}">${grp.state}</span>
                </div>
                <div class="account-item-actions">
                    ${state.userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editGroup('${grp.id}')" title="Editar grupo">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm btn-icon-danger" onclick="event.stopPropagation(); deleteGroup('${grp.id}')" title="Eliminar grupo">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>` : ''}
                    <span class="account-arrow">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                    </span>
                </div>
            </div>
            <div class="group-members">
                ${grp.members.map(m => {
                    const memberInst = (state.cachedInstancesData?.instances || []).find(i => i.id === m);
                    const memberType = memberInst ? memberInst.type : "ec2";
                    return `<span class="member-tag" style="border-color: ${groupColor}40; color: ${groupColor}">${renderTypeBadge(memberType)}${m}</span>`;
                }).join("")}
            </div>
        </div>`;
    }).join("");
}

export function renderSoloInstances(instances, groups) {
    const container = document.getElementById("instances-list");
    const section = document.getElementById("solo-instances-section");

    // Filter out instances that belong to a group
    const groupMemberIds = new Set();
    groups.forEach(grp => {
        (grp.members || []).forEach(m => groupMemberIds.add(m));
    });

    const soloInstances = instances.filter(inst => !groupMemberIds.has(inst.id));

    if (soloInstances.length === 0 && groups.length > 0) {
        section.classList.add("hidden");
        return;
    }

    section.classList.remove("hidden");

    if (soloInstances.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg class="empty-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
                <p class="empty-text">No hay instancias independientes</p>
            </div>`;
        return;
    }

    const viewMode = getViewPreference();

    if (viewMode === "table") {
        container.innerHTML = renderTableView(soloInstances);
    } else {
        container.innerHTML = renderCardView(soloInstances);
    }
}

/**
 * Renders resources as individual cards (default view).
 * Each card shows: name, type badge, state indicator, and IP/identifier.
 */
function renderCardView(instances) {
    return instances.map(inst => {
        const stateClass = inst.state || "stopped";
        return `
        <div class="instance-item view-card" onclick="openInstance('${inst.id}', false)">
            <div class="instance-info">
                <span class="indicator ${stateClass}"></span>
                <div class="instance-text">
                    <span class="instance-name">${escapeHtml(inst.name)}</span>
                    ${renderTypeBadge(inst.type)}
                    <span class="instance-meta">${inst.instanceId || inst.resourceId || ''}${inst.publicIp ? ' · ' + inst.publicIp : ''}</span>
                </div>
            </div>
            <div class="instance-right">
                ${state.userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editInstance('${inst.id}')" title="Editar instancia">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="btn-icon btn-icon-sm btn-icon-danger" onclick="event.stopPropagation(); deleteInstance('${inst.id}')" title="Eliminar instancia">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>` : ''}
                <span class="instance-state-badge ${stateClass}">${inst.state}</span>
            </div>
        </div>`;
    }).join("");
}

/**
 * Renders resources as a table with columns: Name, Type, State, IP/Identifier.
 */
function renderTableView(instances) {
    const rows = instances.map(inst => {
        const stateClass = inst.state || "stopped";
        const ip = inst.publicIp || inst.instanceId || inst.resourceId || "--";
        return `
        <tr class="view-table-row" onclick="openInstance('${inst.id}', false)">
            <td class="view-table-cell view-table-cell-name">
                <span class="indicator indicator-sm ${stateClass}"></span>
                <span>${escapeHtml(inst.name)}</span>
            </td>
            <td class="view-table-cell view-table-cell-type">${renderTypeBadge(inst.type)}</td>
            <td class="view-table-cell view-table-cell-state"><span class="instance-state-badge ${stateClass}">${inst.state || "stopped"}</span></td>
            <td class="view-table-cell view-table-cell-ip">${escapeHtml(ip)}</td>
        </tr>`;
    }).join("");

    return `
    <table class="view-table">
        <thead>
            <tr>
                <th class="view-table-header">Nombre</th>
                <th class="view-table-header">Tipo</th>
                <th class="view-table-header">Estado</th>
                <th class="view-table-header">IP / Identificador</th>
            </tr>
        </thead>
        <tbody>${rows}</tbody>
    </table>`;
}

// ─── Instance Detail ───────────────────────────────────────────────────

export function openInstance(instanceId, fromGroup) {
    state.currentInstanceId = instanceId;
    state.cameFromGroup = fromGroup;
    showScreen("detail-screen");
    refreshInstanceDetail();
    loadActivity();
    initUptimeChart();
    initMetricsCharts();
    if (state.statusInterval) clearInterval(state.statusInterval);
    state.statusInterval = setInterval(refreshInstanceDetail, 30000);
}

export async function refreshInstanceDetail() {
    if (!state.currentAccountId || !state.currentInstanceId) return;

    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/instances/${state.currentInstanceId}/status`);
        updateDetailUI(data);
    } catch (e) {
        if (e.message !== "Unauthorized") {
            document.getElementById("detail-status-text").textContent = "Error de conexion";
        }
    }
}

export function updateDetailUI(data) {
    document.getElementById("detail-title").textContent = data.name || "Instancia";

    const statusCard = document.getElementById("detail-status-card");
    statusCard.className = `card status-card state-${data.state || 'stopped'}`;

    document.getElementById("detail-indicator").className = `indicator ${data.state || "stopped"}`;

    const stateLabels = {
        running: "Running", stopped: "Stopped", pending: "Starting...",
        stopping: "Stopping...", "shutting-down": "Shutting down", terminated: "Terminated",
    };
    document.getElementById("detail-status-text").textContent = stateLabels[data.state] || data.state;

    document.getElementById("detail-public-ip").textContent = data.publicIp || "--";
    document.getElementById("detail-uptime").textContent = data.uptime || "--";
    document.getElementById("detail-instance-id").textContent = data.instanceId || "--";
    document.getElementById("detail-description").textContent = data.description || "--";

    document.getElementById("detail-btn-start").disabled = data.state === "running" || data.state === "pending";
    document.getElementById("detail-btn-stop").disabled = data.state === "stopped" || data.state === "stopping";
    document.getElementById("detail-btn-update").disabled = data.state !== "running";
    document.getElementById("detail-btn-dashboard").disabled = data.state !== "running" || !data.dashboardPort;
}

// ─── Instance Actions ──────────────────────────────────────────────────

export async function startCurrentInstance() {
    const btn = document.getElementById("detail-btn-start");
    btn.disabled = true;
    try {
        await api("POST", `/accounts/${state.currentAccountId}/instances/${state.currentInstanceId}/start`);
        logActivity("Instancia encendiendo...");
        showToast("Encendiendo instancia...");
        setTimeout(refreshInstanceDetail, 3000);
    } catch (e) {
        showToast("Error al encender");
        btn.disabled = false;
    }
}

export async function stopCurrentInstance() {
    if (!confirm("Apagar esta instancia?")) return;
    const btn = document.getElementById("detail-btn-stop");
    btn.disabled = true;
    try {
        await api("POST", `/accounts/${state.currentAccountId}/instances/${state.currentInstanceId}/stop`);
        logActivity("Instancia apagando...");
        showToast("Apagando instancia...");
        setTimeout(refreshInstanceDetail, 3000);
    } catch (e) {
        showToast("Error al apagar");
        btn.disabled = false;
    }
}

export async function updateCurrentInstance() {
    if (!confirm("Ejecutar actualizacion? Esto reiniciara el servicio.")) return;
    const btn = document.getElementById("detail-btn-update");
    btn.disabled = true;
    try {
        const data = await api("POST", `/accounts/${state.currentAccountId}/instances/${state.currentInstanceId}/update`);
        logActivity(`Update iniciado (${data.commandId})`);
        showToast("Actualizacion iniciada");
    } catch (e) {
        showToast("Error al actualizar");
    } finally {
        setTimeout(() => { btn.disabled = false; }, 5000);
    }
}

export async function openCurrentDashboard() {
    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/instances/${state.currentInstanceId}/dashboard-url`);
        if (data.url) {
            window.open(data.url, "_blank");
        } else {
            showToast(data.reason || "Dashboard no disponible");
        }
    } catch (e) {
        showToast("Error obteniendo URL");
    }
}

// ─── Persistent Activity Log ────────────────────────────────────────────

export async function loadActivity() {
    if (!state.currentAccountId) return;
    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/activity`);
        renderPersistentActivity(data.activities || []);
    } catch (e) {}
}

export function renderPersistentActivity(activities) {
    const log = document.getElementById("detail-activity-log");
    if (!log) return;

    if (activities.length === 0) {
        log.innerHTML = `
            <div class="empty-state">
                <p class="empty-text">Sin actividad registrada</p>
            </div>`;
        return;
    }

    log.innerHTML = activities.slice(0, 20).map(a => {
        const time = new Date(a.timestamp).toLocaleString("es", { 
            month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" 
        });
        const actionLabel = a.action === "start" ? "Encendido" : a.action === "stop" ? "Apagado" : a.action;
        return `<div class="log-entry"><span class="log-time">${time}</span><span>${actionLabel} por ${a.user || 'Sistema'}</span></div>`;
    }).join("");
}

export async function clearActivity() {
    if (!confirm("Limpiar todo el historial de actividad?")) return;
    try {
        await api("DELETE", `/accounts/${state.currentAccountId}/activity`);
        showToast("Actividad limpiada");
        loadActivity();
    } catch (e) {
        showToast("Error limpiando actividad");
    }
}

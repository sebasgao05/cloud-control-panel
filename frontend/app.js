/**
 * Cloud Control Panel - Frontend App (Multi-account, Multi-instance)
 * Vanilla JS with transitions, skeletons, and micro-interactions.
 */

const API_BASE = "/api";
let apiKey = "";
let currentAccountId = null;
let currentInstanceId = null;
let statusInterval = null;

// ─── Auth ──────────────────────────────────────────────────────────────

function authenticate() {
    const input = document.getElementById("api-key-input");
    const key = input.value.trim();
    if (!key) {
        showToast("Ingresa tu API Key");
        return;
    }

    apiKey = key;

    if (document.getElementById("remember-key").checked) {
        localStorage.setItem("ccp-api-key", key);
    }

    loadAccounts();
}

function logout() {
    apiKey = "";
    currentAccountId = null;
    currentInstanceId = null;
    localStorage.removeItem("ccp-api-key");
    if (statusInterval) clearInterval(statusInterval);
    showScreen("auth-screen");
}

// ─── Navigation ────────────────────────────────────────────────────────

function showScreen(screenId) {
    document.querySelectorAll(".screen").forEach(s => s.classList.add("hidden"));
    const target = document.getElementById(screenId);
    target.classList.remove("hidden");
    target.style.animation = "none";
    target.offsetHeight;
    target.style.animation = "";
}

function goBackToAccounts() {
    currentAccountId = null;
    if (statusInterval) clearInterval(statusInterval);
    showScreen("accounts-screen");
}

function goBackToInstances() {
    currentInstanceId = null;
    if (statusInterval) clearInterval(statusInterval);
    showScreen("instances-screen");
    refreshInstances();
}

// ─── API Calls ─────────────────────────────────────────────────────────

async function api(method, path, body = null) {
    const opts = {
        method,
        headers: {
            "Content-Type": "application/json",
            "X-Api-Key": apiKey,
        },
    };
    if (body) opts.body = JSON.stringify(body);

    const res = await fetch(`${API_BASE}${path}`, opts);

    if (res.status === 401 || res.status === 403) {
        showToast("API Key invalida o sin permisos");
        logout();
        throw new Error("Unauthorized");
    }

    return res.json();
}

// ─── Accounts ──────────────────────────────────────────────────────────

async function loadAccounts() {
    try {
        const data = await api("GET", "/accounts");
        document.getElementById("user-name").textContent = data.user || "";
        const accounts = data.accounts || [];

        // Always render the accounts list (so "back to accounts" works)
        renderAccounts(accounts);

        if (accounts.length === 1) {
            // Single account: skip accounts screen, go directly to instances
            openAccount(accounts[0].id, accounts[0].name);
            return;
        }

        showScreen("accounts-screen");
    } catch (e) {
        if (e.message !== "Unauthorized") {
            showToast("Error cargando cuentas");
        }
    }
}

function renderAccounts(accounts) {
    const container = document.getElementById("accounts-list");

    if (accounts.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg class="empty-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
                <p class="empty-text">No hay cuentas configuradas</p>
                <p class="empty-hint">Edita config/accounts.json para agregar cuentas</p>
            </div>
        `;
        return;
    }

    container.innerHTML = accounts.map(acc => `
        <div class="account-item" onclick="openAccount('${acc.id}', '${escapeHtml(acc.name)}')">
            <div class="account-info">
                <span class="account-name">${escapeHtml(acc.name)}</span>
                <span class="account-meta">
                    ${acc.instanceCount} instancia${acc.instanceCount !== 1 ? 's' : ''}
                    <span class="dot"></span>
                    ${acc.groupCount} grupo${acc.groupCount !== 1 ? 's' : ''}
                    <span class="dot"></span>
                    ${acc.region}
                </span>
            </div>
            <span class="account-arrow">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="9 18 15 12 9 6"/>
                </svg>
            </span>
        </div>
    `).join("");
}

function openAccount(accountId, accountName) {
    currentAccountId = accountId;
    document.getElementById("account-title").textContent = accountName;
    showScreen("instances-screen");
    refreshInstances();
}

// ─── Instances List ────────────────────────────────────────────────────

async function refreshInstances() {
    if (!currentAccountId) return;

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/instances`);
        renderGroups(data.groups || []);
        renderInstances(data.instances || []);
    } catch (e) {
        if (e.message !== "Unauthorized") {
            showToast("Error cargando instancias");
        }
    }
}

function renderGroups(groups) {
    const section = document.getElementById("groups-section");
    const container = document.getElementById("groups-list");

    if (groups.length === 0) {
        section.classList.add("hidden");
        return;
    }

    section.classList.remove("hidden");
    container.innerHTML = groups.map(grp => {
        const stateClass = grp.state || "stopped";

        return `
        <div class="group-item">
            <div class="group-header">
                <div class="group-info">
                    <span class="indicator ${stateClass}"></span>
                    <span class="group-name">${escapeHtml(grp.name)}</span>
                    <span class="group-state-badge ${stateClass}">${grp.state}</span>
                </div>
                <div class="group-actions">
                    <button class="btn btn-sm btn-start" onclick="event.stopPropagation(); startGroup('${grp.id}')" ${grp.state === 'running' ? 'disabled' : ''}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        Encender
                    </button>
                    <button class="btn btn-sm btn-stop" onclick="event.stopPropagation(); stopGroup('${grp.id}')" ${grp.state === 'stopped' ? 'disabled' : ''}>
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
                        Apagar
                    </button>
                </div>
            </div>
            <div class="group-members">
                ${grp.members.map(m => `<span class="member-tag">${m}</span>`).join("")}
            </div>
            ${grp.description ? `<p class="group-desc">${escapeHtml(grp.description)}</p>` : ''}
        </div>
    `;
    }).join("");
}

function renderInstances(instances) {
    const container = document.getElementById("instances-list");

    if (instances.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <svg class="empty-icon" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
                <p class="empty-text">No hay instancias configuradas</p>
                <p class="empty-hint">Agrega instancias en config/accounts.json</p>
            </div>
        `;
        return;
    }

    container.innerHTML = instances.map(inst => {
        const stateClass = inst.state || "stopped";

        return `
        <div class="instance-item" onclick="openInstance('${inst.id}')">
            <div class="instance-info">
                <span class="indicator ${stateClass}"></span>
                <div class="instance-text">
                    <span class="instance-name">${escapeHtml(inst.name)}</span>
                    <span class="instance-meta">${inst.instanceId}${inst.publicIp ? ' · ' + inst.publicIp : ''}</span>
                </div>
            </div>
            <div class="instance-right">
                <span class="instance-state-badge ${stateClass}">${inst.state}</span>
                ${inst.group ? `<span class="instance-group-tag">${inst.group}</span>` : ''}
            </div>
        </div>
    `;
    }).join("");
}

// ─── Instance Detail ───────────────────────────────────────────────────

function openInstance(instanceId) {
    currentInstanceId = instanceId;
    showScreen("detail-screen");
    refreshInstanceDetail();
    if (statusInterval) clearInterval(statusInterval);
    statusInterval = setInterval(refreshInstanceDetail, 30000);
}

async function refreshInstanceDetail() {
    if (!currentAccountId || !currentInstanceId) return;

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/instances/${currentInstanceId}/status`);
        updateDetailUI(data);
    } catch (e) {
        if (e.message !== "Unauthorized") {
            document.getElementById("detail-status-text").textContent = "Error de conexion";
        }
    }
}

function updateDetailUI(data) {
    document.getElementById("detail-title").textContent = data.name || "Instancia";

    const statusCard = document.getElementById("detail-status-card");
    statusCard.className = `card status-card state-${data.state || 'stopped'}`;

    const indicator = document.getElementById("detail-indicator");
    const statusText = document.getElementById("detail-status-text");

    indicator.className = `indicator ${data.state || "stopped"}`;

    const stateLabels = {
        running: "Running",
        stopped: "Stopped",
        pending: "Starting...",
        stopping: "Stopping...",
        "shutting-down": "Shutting down",
        terminated: "Terminated",
    };
    statusText.textContent = stateLabels[data.state] || data.state;

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

async function startCurrentInstance() {
    const btn = document.getElementById("detail-btn-start");
    btn.disabled = true;
    try {
        await api("POST", `/accounts/${currentAccountId}/instances/${currentInstanceId}/start`);
        logActivity("Instancia encendiendo...");
        showToast("Encendiendo instancia...");
        setTimeout(refreshInstanceDetail, 3000);
    } catch (e) {
        showToast("Error al encender");
        btn.disabled = false;
    }
}

async function stopCurrentInstance() {
    if (!confirm("Apagar esta instancia?")) return;

    const btn = document.getElementById("detail-btn-stop");
    btn.disabled = true;
    try {
        await api("POST", `/accounts/${currentAccountId}/instances/${currentInstanceId}/stop`);
        logActivity("Instancia apagando...");
        showToast("Apagando instancia...");
        setTimeout(refreshInstanceDetail, 3000);
    } catch (e) {
        showToast("Error al apagar");
        btn.disabled = false;
    }
}

async function updateCurrentInstance() {
    if (!confirm("Ejecutar actualizacion? Esto reiniciara el servicio.")) return;

    const btn = document.getElementById("detail-btn-update");
    btn.disabled = true;
    try {
        const data = await api("POST", `/accounts/${currentAccountId}/instances/${currentInstanceId}/update`);
        logActivity(`Update iniciado (${data.commandId})`);
        showToast("Actualizacion iniciada");
    } catch (e) {
        showToast("Error al actualizar");
    } finally {
        setTimeout(() => { btn.disabled = false; }, 5000);
    }
}

async function openCurrentDashboard() {
    try {
        const data = await api("GET", `/accounts/${currentAccountId}/instances/${currentInstanceId}/dashboard-url`);
        if (data.url) {
            window.open(data.url, "_blank");
        } else {
            showToast(data.reason || "Dashboard no disponible");
        }
    } catch (e) {
        showToast("Error obteniendo URL");
    }
}

// ─── Group Actions ─────────────────────────────────────────────────────

async function startGroup(groupId) {
    if (!confirm("Encender todas las instancias del grupo?")) return;

    try {
        await api("POST", `/accounts/${currentAccountId}/groups/${groupId}/start`);
        showToast("Grupo encendiendo...");
        setTimeout(refreshInstances, 3000);
    } catch (e) {
        showToast("Error al encender grupo");
    }
}

async function stopGroup(groupId) {
    if (!confirm("Apagar todas las instancias del grupo?")) return;

    try {
        await api("POST", `/accounts/${currentAccountId}/groups/${groupId}/stop`);
        showToast("Grupo apagando...");
        setTimeout(refreshInstances, 3000);
    } catch (e) {
        showToast("Error al apagar grupo");
    }
}

// ─── Utilities ─────────────────────────────────────────────────────────

function logActivity(message) {
    const log = document.getElementById("detail-activity-log");
    const time = new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

    const emptyState = log.querySelector(".empty-state");
    if (emptyState) emptyState.remove();

    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.innerHTML = `<span class="log-time">${time}</span><span>${message}</span>`;
    log.prepend(entry);

    while (log.children.length > 20) {
        log.lastChild.remove();
    }
}

function showToast(message) {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(-50%) translateY(8px)";
        toast.style.transition = "all 0.2s ease";
        setTimeout(() => toast.remove(), 200);
    }, 2800);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// ─── Init ──────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    const savedKey = localStorage.getItem("ccp-api-key");
    if (savedKey) {
        apiKey = savedKey;
        loadAccounts();
    }

    document.getElementById("api-key-input").addEventListener("keypress", (e) => {
        if (e.key === "Enter") authenticate();
    });
});

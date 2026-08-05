/**
 * Cloud Control Panel - Frontend App (Multi-account, Multi-instance)
 * Vanilla JS with transitions, skeletons, and micro-interactions.
 */

const API_BASE = "/api";
let apiKey = "";
let currentAccountId = null;
let currentInstanceId = null;
let currentGroupId = null;
let statusInterval = null;
let cachedInstancesData = null;
let cameFromGroup = false;
let userRole = "operator";

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
    currentGroupId = null;
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
    currentGroupId = null;
    if (statusInterval) clearInterval(statusInterval);
    closeSettingsPanel();
    showScreen("accounts-screen");
}

function goBackToInstances() {
    currentInstanceId = null;
    if (statusInterval) clearInterval(statusInterval);
    if (cameFromGroup && currentGroupId) {
        showScreen("group-screen");
        refreshGroupInstances();
    } else {
        showScreen("instances-screen");
        refreshInstances();
    }
}

function goBackFromGroup() {
    currentGroupId = null;
    showScreen("instances-screen");
}

// ─── Settings Panel ────────────────────────────────────────────────────

function openSettingsPanel() {
    document.getElementById("settings-overlay").classList.remove("hidden");
    document.getElementById("settings-panel").classList.add("open");
    loadSchedule();
    loadNotifications();
    loadCosts();
    loadKeys();
    // Export/Import only for superadmin
    const exportSection = document.getElementById("settings-export");
    if (exportSection) {
        exportSection.style.display = userRole === "superadmin" ? "" : "none";
    }
    // If admin, only show costs and keys (not scheduler/notifs)
    if (userRole === "admin") {
        const schedSection = document.getElementById("settings-scheduler");
        if (schedSection) schedSection.style.display = "none";
        const notifSection = document.getElementById("settings-notifications");
        if (notifSection) notifSection.style.display = "none";
    }
}

function closeSettingsPanel() {
    document.getElementById("settings-overlay").classList.add("hidden");
    document.getElementById("settings-panel").classList.remove("open");
}

function toggleSettingsSection(section) {
    const content = document.getElementById(`settings-${section}-content`);
    const header = content.previousElementSibling;
    content.classList.toggle("collapsed");
    header.classList.toggle("collapsed");
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

    if (res.status === 401) {
        showToast("API Key invalida");
        logout();
        throw new Error("Unauthorized");
    }

    // Don't logout on 403 for non-GET requests (permission denied for action)
    if (res.status === 403 && method === "GET") {
        showToast("Sin permisos");
        logout();
        throw new Error("Unauthorized");
    }

    const data = await res.json();

    // If 403 on mutation, show error but don't logout
    if (res.status === 403) {
        showToast(data.error || "Sin permisos para esta accion");
        throw new Error(data.error || "Forbidden");
    }

    return data;
}

// ─── Accounts ──────────────────────────────────────────────────────────

async function loadAccounts() {
    try {
        const data = await api("GET", "/accounts");
        document.getElementById("user-name").textContent = data.user || "";
        const accounts = data.accounts || [];

        // Show add button for superadmin
        const addBtn = document.getElementById("btn-add-account");
        if (data.role === "superadmin") {
            addBtn.classList.remove("hidden");
            userRole = data.role;
        } else {
            addBtn.classList.add("hidden");
            userRole = data.role || "operator";
        }

        renderAccounts(accounts);

        if (accounts.length === 1) {
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
                <p class="empty-hint">Edita config/accounts.json</p>
            </div>`;
        return;
    }

    container.innerHTML = accounts.map(acc => `
        <div class="account-item" onclick="openAccount('${acc.id}', '${escapeHtml(acc.name)}')">
            <div class="account-info">
                <span class="account-name">${escapeHtml(acc.name)}</span>
                <span class="account-meta">
                    ${acc.instanceCount} instancia${acc.instanceCount !== 1 ? 's' : ''}
                    <span class="dot"></span>
                    ${acc.region}
                </span>
            </div>
            <div class="account-item-actions">
                ${userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editAccount('${acc.id}')" title="Editar cuenta">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                </button>
                <button class="btn-icon btn-icon-sm btn-icon-danger" onclick="event.stopPropagation(); deleteAccount('${acc.id}')" title="Eliminar cuenta">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>` : ''}
                <span class="account-arrow">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                </span>
            </div>
        </div>
    `).join("");
}

function openAccount(accountId, accountName) {
    currentAccountId = accountId;
    document.getElementById("account-title").textContent = accountName;
    showScreen("instances-screen");
    refreshInstances();
}

// ─── Admin CRUD (Accounts, Groups, Instances) ──────────────────────────

function showAddAccountForm() {
    document.getElementById("account-form").classList.remove("hidden");
    document.getElementById("acc-id").value = "";
    document.getElementById("acc-name").value = "";
    document.getElementById("acc-aws-id").value = "";
    document.getElementById("acc-region").value = "us-east-1";
    document.getElementById("acc-role-arn").value = "";
}

function cancelAccountForm() {
    document.getElementById("account-form").classList.add("hidden");
}

async function saveAccount() {
    const id = document.getElementById("acc-id").value.trim();
    const name = document.getElementById("acc-name").value.trim();
    const awsAccountId = document.getElementById("acc-aws-id").value.trim();
    const region = document.getElementById("acc-region").value.trim() || "us-east-1";
    const roleArn = document.getElementById("acc-role-arn").value.trim() || null;

    if (!id) { showToast("ID es requerido"); return; }
    if (!name) { showToast("Nombre es requerido"); return; }

    try {
        await api("POST", "/accounts", {
            id, name, awsAccountId, region,
            crossAccountRoleArn: roleArn,
            features: { scheduler: true, notifications: true, costEstimate: true }
        });
        showToast("Cuenta creada");
        cancelAccountForm();
        loadAccounts();
    } catch (e) { showToast("Error creando cuenta"); }
}

async function deleteAccount(accountId) {
    if (!confirm(`Eliminar la cuenta "${accountId}" y todo su contenido (instancias, grupos, reglas)?`)) return;
    try {
        await api("DELETE", `/accounts/${accountId}`);
        showToast("Cuenta eliminada");
        loadAccounts();
    } catch (e) { showToast("Error eliminando cuenta"); }
}

function editAccount(accountId) {
    const newName = prompt("Nuevo nombre de la cuenta:");
    if (!newName) return;
    api("POST", "/accounts", { id: accountId, name: newName })
        .then(() => { showToast("Cuenta actualizada"); loadAccounts(); })
        .catch(() => showToast("Error actualizando cuenta"));
}

function editGroup(groupId) {
    const groups = cachedInstancesData?.groups || [];
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

function editInstance(instanceId) {
    const instances = cachedInstancesData?.instances || [];
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
    const groups = cachedInstancesData?.groups || [];
    select.innerHTML = '<option value="">Sin grupo (independiente)</option>' +
        groups.map(g => `<option value="${g.id}" ${g.id === inst.group ? 'selected' : ''}>${escapeHtml(g.name)}</option>`).join("");

    renderOperatorAssignment("inst");

    // Change button to "Guardar"
    const saveBtn = document.querySelector("#instance-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Guardar cambios"; }
}

function showAddGroupForm() {
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

function renderGroupInstancesCheckboxes(selected) {
    const container = document.getElementById("grp-instances-checkboxes");
    const instances = cachedInstancesData?.instances || [];
    if (instances.length === 0) {
        container.innerHTML = '<span class="muted">No hay instancias en esta cuenta</span>';
        return;
    }
    container.innerHTML = instances.map(inst => {
        const checked = selected.includes(inst.id) ? "checked" : "";
        return `<label class="checkbox-item"><input type="checkbox" value="${inst.id}" ${checked}><span>${escapeHtml(inst.name)} <small style="color:var(--text-muted)">(${inst.id})</small></span></label>`;
    }).join("");
}

async function renderOperatorAssignment(prefix) {
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
                    const hasAccess = (op.accounts || []).includes(currentAccountId) || (op.accounts || []).includes("*");
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
                    const hasAccess = (op.accounts || []).includes(currentAccountId) || (op.accounts || []).includes("*");
                    return `<label class="checkbox-item"><input type="checkbox" value="${op.key}" ${hasAccess ? "checked" : ""}><span>${escapeHtml(op.name)} <small class="role-tag" style="color:#34d399">operator</small>${(op.accounts || []).includes("*") ? ' <small style="color:var(--text-muted)">(todas)</small>' : ''}</span></label>`;
                }).join("");
            }
        }
    } catch (e) {
        if (adminsContainer) adminsContainer.innerHTML = '<span class="muted">Error</span>';
        if (opsContainer) opsContainer.innerHTML = '<span class="muted">Error</span>';
    }
}

async function renderKeyAccountsCheckboxes(selectedAccounts) {
    const container = document.getElementById("key-accounts-checkboxes");
    if (!container) return;
    try {
        // Get all accounts from the config
        const data = await api("GET", "/accounts");
        const accounts = data.accounts || [];
        const isAll = selectedAccounts.includes("*");

        container.innerHTML = `<label class="checkbox-item"><input type="checkbox" value="*" ${isAll ? "checked" : ""} onchange="toggleAllAccounts(this)"><span><strong>Todas las cuentas</strong></span></label>` +
            accounts.map(acc => {
                const checked = isAll || selectedAccounts.includes(acc.id) ? "checked" : "";
                return `<label class="checkbox-item"><input type="checkbox" value="${acc.id}" ${checked} ${isAll ? "disabled" : ""}><span>${escapeHtml(acc.name)} <small style="color:var(--text-muted)">${acc.id}</small></span></label>`;
            }).join("");
    } catch (e) {
        container.innerHTML = '<span class="muted">Error cargando cuentas</span>';
    }
}

function toggleAllAccounts(checkbox) {
    const container = document.getElementById("key-accounts-checkboxes");
    const others = container.querySelectorAll('input[type=checkbox]:not([value="*"])');
    others.forEach(cb => {
        cb.disabled = checkbox.checked;
        if (checkbox.checked) cb.checked = true;
    });
}

function cancelGroupForm() {
    document.getElementById("group-form").classList.add("hidden");
    document.getElementById("grp-id").disabled = false;
    const saveBtn = document.querySelector("#group-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear grupo"; }
}

async function saveGroup() {
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
        await api("POST", `/accounts/${currentAccountId}/groups`, {
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

async function updateOperatorAccess(prefix) {
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
            const hasAccess = hasAll || accounts.includes(currentAccountId);

            let newAccounts = accounts;

            if (shouldHaveAccess && !hasAccess) {
                // Give access
                if (hasAll) continue; // already has all
                newAccounts = [...accounts, currentAccountId];
            } else if (!shouldHaveAccess && hasAccess) {
                // Remove access
                if (hasAll) {
                    // Expand "*" to all accounts except current
                    newAccounts = allAccountIds.filter(id => id !== currentAccountId);
                } else {
                    newAccounts = accounts.filter(a => a !== currentAccountId);
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

async function deleteGroup(groupId) {
    if (!confirm(`Eliminar el grupo "${groupId}"?`)) return;
    try {
        await api("DELETE", `/accounts/${currentAccountId}/groups/${groupId}`);
        showToast("Grupo eliminado");
        refreshInstances();
    } catch (e) { showToast("Error eliminando grupo"); }
}

function showAddInstanceForm() {
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
    const groups = cachedInstancesData?.groups || [];
    select.innerHTML = '<option value="">Sin grupo (independiente)</option>' +
        groups.map(g => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join("");

    renderOperatorAssignment("inst");
}

function showInlineGroupCreate() {
    const inline = document.getElementById("inst-inline-group");
    inline.classList.toggle("hidden");
    if (!inline.classList.contains("hidden")) {
        document.getElementById("inst-new-grp-id").value = "";
        document.getElementById("inst-new-grp-name").value = "";
        document.getElementById("inst-new-grp-color").value = "#6366f1";
    }
}

function cancelInstanceForm() {
    document.getElementById("instance-form").classList.add("hidden");
    document.getElementById("inst-id").disabled = false;
    const saveBtn = document.querySelector("#instance-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear instancia"; }
}

async function saveInstance() {
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
                await api("POST", `/accounts/${currentAccountId}/groups`, {
                    id: grpId, name: grpName, description: "", color: grpColor,
                    startOrder: [id], stopOrder: [id]
                });
                group = grpId;
            } catch (e) { showToast("Error creando grupo"); return; }
        }
    }

    try {
        await api("POST", `/accounts/${currentAccountId}/instances`, {
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

async function deleteInstance(instanceId) {
    if (!confirm(`Eliminar la instancia "${instanceId}" de la configuracion?`)) return;
    try {
        await api("DELETE", `/accounts/${currentAccountId}/instances/${instanceId}`);
        showToast("Instancia eliminada");
        refreshInstances();
    } catch (e) { showToast("Error eliminando instancia"); }
}

// ─── Instances List ────────────────────────────────────────────────────

async function refreshInstances() {
    if (!currentAccountId) return;

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/instances`);
        cachedInstancesData = data;
        renderGroups(data.groups || []);
        renderSoloInstances(data.instances || [], data.groups || []);
        checkSettingsVisibility();

        // Show add buttons for superadmin only
        const isSuperadmin = userRole === "superadmin";
        document.getElementById("btn-add-group").classList.toggle("hidden", !isSuperadmin);
        document.getElementById("btn-add-instance").classList.toggle("hidden", !isSuperadmin);
    } catch (e) {
        if (e.message !== "Unauthorized") {
            showToast("Error cargando instancias");
        }
    }
}

async function checkSettingsVisibility() {
    // Show settings button if scheduler or notifications or costs are available, or user is admin
    const btn = document.getElementById("btn-settings-panel");
    try {
        const schedData = await api("GET", `/accounts/${currentAccountId}/schedule`);
        const notifData = await api("GET", `/accounts/${currentAccountId}/notifications`);
        const costsData = await api("GET", `/accounts/${currentAccountId}/costs`);
        const hasScheduler = schedData.enabled && schedData.permissions?.view;
        const hasNotifs = notifData.enabled && notifData.canEdit;
        const hasCosts = costsData.enabled;
        // Always show for admin (they can manage keys)
        if (hasScheduler || hasNotifs || hasCosts) {
            btn.classList.remove("hidden");
        } else {
            // Try to load keys to check if admin
            try {
                const keysData = await api("GET", `/keys/list`);
                if (keysData.keys) {
                    btn.classList.remove("hidden");
                    return;
                }
            } catch (e) {}
            btn.classList.add("hidden");
        }
    } catch (e) {
        btn.classList.add("hidden");
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
                    ${userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editGroup('${grp.id}')" title="Editar grupo">
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
                ${grp.members.map(m => `<span class="member-tag" style="border-color: ${groupColor}40; color: ${groupColor}">${m}</span>`).join("")}
            </div>
        </div>`;
    }).join("");
}

function renderSoloInstances(instances, groups) {
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

    container.innerHTML = soloInstances.map(inst => {
        const stateClass = inst.state || "stopped";
        return `
        <div class="instance-item" onclick="openInstance('${inst.id}', false)">
            <div class="instance-info">
                <span class="indicator ${stateClass}"></span>
                <div class="instance-text">
                    <span class="instance-name">${escapeHtml(inst.name)}</span>
                    <span class="instance-meta">${inst.instanceId}${inst.publicIp ? ' · ' + inst.publicIp : ''}</span>
                </div>
            </div>
            <div class="instance-right">
                ${userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editInstance('${inst.id}')" title="Editar instancia">
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

// ─── Group Screen ──────────────────────────────────────────────────────

function openGroup(groupId) {
    currentGroupId = groupId;
    const groups = cachedInstancesData?.groups || [];
    const group = groups.find(g => g.id === groupId);
    if (!group) return;

    document.getElementById("group-title").textContent = group.name;
    document.getElementById("group-description").textContent = group.description || "";
    document.getElementById("group-btn-start").disabled = group.state === "running";
    document.getElementById("group-btn-stop").disabled = group.state === "stopped";

    showScreen("group-screen");
    renderGroupInstances(group);
}

function renderGroupInstances(group) {
    const container = document.getElementById("group-instances-list");
    const allInstances = cachedInstancesData?.instances || [];
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

async function refreshGroupInstances() {
    if (!currentAccountId || !currentGroupId) return;
    try {
        const data = await api("GET", `/accounts/${currentAccountId}/instances`);
        cachedInstancesData = data;
        const group = (data.groups || []).find(g => g.id === currentGroupId);
        if (group) renderGroupInstances(group);
    } catch (e) {}
}

async function startCurrentGroup() {
    if (!confirm("Encender todas las instancias del grupo?")) return;
    try {
        await api("POST", `/accounts/${currentAccountId}/groups/${currentGroupId}/start`);
        showToast("Grupo encendiendo...");
        setTimeout(refreshGroupInstances, 3000);
    } catch (e) {
        showToast("Error al encender grupo");
    }
}

async function stopCurrentGroup() {
    if (!confirm("Apagar todas las instancias del grupo?")) return;
    try {
        await api("POST", `/accounts/${currentAccountId}/groups/${currentGroupId}/stop`);
        showToast("Grupo apagando...");
        setTimeout(refreshGroupInstances, 3000);
    } catch (e) {
        showToast("Error al apagar grupo");
    }
}

// ─── Instance Detail ───────────────────────────────────────────────────

function openInstance(instanceId, fromGroup) {
    currentInstanceId = instanceId;
    cameFromGroup = fromGroup;
    showScreen("detail-screen");
    refreshInstanceDetail();
    loadActivity();
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

// ─── Scheduler ─────────────────────────────────────────────────────────

let schedulerData = null;
let schedulerPermissions = { view: false, edit: false };
let editingRuleId = null;
let accountInstances = [];

async function loadSchedule() {
    if (!currentAccountId) return;

    const section = document.getElementById("settings-scheduler");
    const addBtn = document.getElementById("settings-scheduler-add-btn");

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/schedule`);
        schedulerData = data;
        schedulerPermissions = data.permissions || { view: false, edit: false };

        if (!data.enabled || !schedulerPermissions.view) {
            section.classList.add("hidden");
            return;
        }

        section.classList.remove("hidden");

        if (schedulerPermissions.edit) {
            addBtn.classList.remove("hidden");
        } else {
            addBtn.classList.add("hidden");
        }

        accountInstances = data.instanceMap || {};
        renderScheduleRules(data.schedule || { rules: [] });
    } catch (e) {
        section.classList.add("hidden");
    }
}

function renderScheduleRules(schedule) {
    const container = document.getElementById("scheduler-list");
    const rules = schedule.rules || [];

    if (rules.length === 0) {
        container.innerHTML = `
            <div class="empty-state small">
                <p class="empty-text">Sin programacion configurada</p>
                <p class="empty-hint">${schedulerPermissions.edit ? 'Agrega una regla' : 'Sin horarios configurados'}</p>
            </div>`;
        return;
    }

    container.innerHTML = rules.map(rule => {
        const instanceNames = (rule.instances || []).map(id => accountInstances[id] || id);
        const enabledClass = rule.enabled ? "enabled" : "disabled";
        const enabledLabel = rule.enabled ? "Activa" : "Inactiva";

        return `
        <div class="schedule-rule ${enabledClass}">
            <div class="rule-header">
                <div class="rule-info">
                    <span class="rule-description">${escapeHtml(rule.description || 'Sin descripcion')}</span>
                    <span class="rule-status-badge ${enabledClass}">${enabledLabel}</span>
                </div>
                ${schedulerPermissions.edit ? `
                <div class="rule-actions">
                    <button class="btn-icon btn-icon-sm" onclick="toggleRule('${rule.id}')" title="${rule.enabled ? 'Desactivar' : 'Activar'}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm" onclick="editRule('${rule.id}')" title="Editar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm btn-icon-danger" onclick="deleteRule('${rule.id}')" title="Eliminar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>` : ''}
            </div>
            <div class="rule-details">
                <div class="rule-cron">
                    <span class="rule-cron-item">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        ${escapeHtml(cronToHuman(rule.startCron))}
                    </span>
                    <span class="rule-cron-item">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
                        ${escapeHtml(cronToHuman(rule.stopCron))}
                    </span>
                </div>
                <div class="rule-instances-tags">
                    ${instanceNames.map(name => `<span class="member-tag">${escapeHtml(name)}</span>`).join("")}
                </div>
            </div>
        </div>`;
    }).join("");
}

function cronToHuman(cron) {
    if (!cron) return "No definido";
    const parts = cron.split(" ");
    if (parts.length < 5) return cron;
    const [min, hour, , , dow] = parts;
    const dayMap = {
        "0": "Dom", "1": "Lun", "2": "Mar", "3": "Mie", "4": "Jue", "5": "Vie", "6": "Sab", "7": "Dom",
        "*": "Todos", "1-5": "L-V", "1-6": "L-S", "0-6": "Todos"
    };
    const dayStr = dayMap[dow] || dow;
    const timeStr = `${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
    return `${timeStr} (${dayStr})`;
}

function showAddRuleForm() {
    editingRuleId = null;
    document.getElementById("scheduler-form-title").textContent = "Nueva regla";
    document.getElementById("rule-description").value = "";
    document.getElementById("rule-start-time").value = "07:00";
    document.getElementById("rule-stop-time").value = "20:00";
    // Reset day buttons
    document.querySelectorAll(".day-btn").forEach(btn => btn.classList.remove("active"));
    // Default: L-V selected
    document.querySelectorAll('.day-btn[data-day="1"], .day-btn[data-day="2"], .day-btn[data-day="3"], .day-btn[data-day="4"], .day-btn[data-day="5"]').forEach(btn => btn.classList.add("active"));
    renderInstanceCheckboxes([]);
    document.getElementById("scheduler-form").classList.remove("hidden");
    initDayButtons();
}

function editRule(ruleId) {
    const rules = schedulerData?.schedule?.rules || [];
    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;
    editingRuleId = ruleId;
    document.getElementById("scheduler-form-title").textContent = "Editar regla";
    document.getElementById("rule-description").value = rule.description || "";

    // Parse cron to time and days
    const startParts = (rule.startCron || "0 7 * * 1-5").split(" ");
    const stopParts = (rule.stopCron || "0 20 * * 1-5").split(" ");
    document.getElementById("rule-start-time").value = `${startParts[1].padStart(2,'0')}:${startParts[0].padStart(2,'0')}`;
    document.getElementById("rule-stop-time").value = `${stopParts[1].padStart(2,'0')}:${stopParts[0].padStart(2,'0')}`;

    // Parse days from cron
    const daysStr = startParts[4] || "1-5";
    const activeDays = parseCronDays(daysStr);
    document.querySelectorAll(".day-btn").forEach(btn => {
        const day = parseInt(btn.dataset.day);
        btn.classList.toggle("active", activeDays.includes(day));
    });

    renderInstanceCheckboxes(rule.instances || []);
    document.getElementById("scheduler-form").classList.remove("hidden");
    initDayButtons();
}

function initDayButtons() {
    document.querySelectorAll(".day-btn").forEach(btn => {
        btn.onclick = () => btn.classList.toggle("active");
    });
}

function parseCronDays(daysStr) {
    const days = new Set();
    const parts = daysStr.split(",");
    for (const part of parts) {
        if (part.includes("-")) {
            const [start, end] = part.split("-").map(Number);
            for (let i = start; i <= end; i++) days.add(i);
        } else if (part === "*") {
            for (let i = 0; i <= 6; i++) days.add(i);
        } else {
            days.add(parseInt(part));
        }
    }
    return [...days];
}

function daysToCron(activeDays) {
    if (activeDays.length === 7) return "*";
    activeDays.sort((a, b) => a - b);
    // Check for consecutive ranges
    const ranges = [];
    let start = activeDays[0], prev = activeDays[0];
    for (let i = 1; i <= activeDays.length; i++) {
        if (i < activeDays.length && activeDays[i] === prev + 1) {
            prev = activeDays[i];
        } else {
            ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
            if (i < activeDays.length) { start = activeDays[i]; prev = activeDays[i]; }
        }
    }
    return ranges.join(",");
}

function renderInstanceCheckboxes(selectedInstances) {
    const container = document.getElementById("rule-instances-checkboxes");
    const entries = Object.entries(accountInstances);
    if (entries.length === 0) {
        container.innerHTML = '<span class="muted">No hay instancias</span>';
        return;
    }
    container.innerHTML = entries.map(([id, name]) => {
        const checked = selectedInstances.includes(id) ? "checked" : "";
        return `<label class="checkbox-item"><input type="checkbox" value="${id}" ${checked}><span>${escapeHtml(name)}</span></label>`;
    }).join("");
}

function cancelRuleForm() {
    document.getElementById("scheduler-form").classList.add("hidden");
    editingRuleId = null;
}

async function saveRule() {
    const description = document.getElementById("rule-description").value.trim();
    const startTime = document.getElementById("rule-start-time").value;
    const stopTime = document.getElementById("rule-stop-time").value;
    const checkboxes = document.querySelectorAll("#rule-instances-checkboxes input[type=checkbox]:checked");
    const instances = Array.from(checkboxes).map(cb => cb.value);

    // Get selected days
    const activeDays = [];
    document.querySelectorAll(".day-btn.active").forEach(btn => activeDays.push(parseInt(btn.dataset.day)));

    if (!description) { showToast("Ingresa una descripcion"); return; }
    if (!startTime) { showToast("Selecciona hora de encendido"); return; }
    if (!stopTime) { showToast("Selecciona hora de apagado"); return; }
    if (activeDays.length === 0) { showToast("Selecciona al menos un dia"); return; }
    if (instances.length === 0) { showToast("Selecciona al menos una instancia"); return; }

    // Build cron from visual selectors
    const [startH, startM] = startTime.split(":");
    const [stopH, stopM] = stopTime.split(":");
    const cronDays = daysToCron(activeDays);
    const startCron = `${parseInt(startM)} ${parseInt(startH)} * * ${cronDays}`;
    const stopCron = `${parseInt(stopM)} ${parseInt(stopH)} * * ${cronDays}`;

    const rules = [...(schedulerData?.schedule?.rules || [])];
    if (editingRuleId) {
        const idx = rules.findIndex(r => r.id === editingRuleId);
        if (idx >= 0) rules[idx] = { ...rules[idx], description, startCron, stopCron, instances };
    } else {
        rules.push({ id: `rule-${Date.now()}`, description, startCron, stopCron, instances, enabled: true });
    }

    try {
        const tz = schedulerData?.schedule?.timezone || "America/Bogota";
        await api("PUT", `/accounts/${currentAccountId}/schedule`, { rules, timezone: tz });
        showToast(editingRuleId ? "Regla actualizada" : "Regla creada");
        cancelRuleForm();
        loadSchedule();
    } catch (e) { showToast("Error guardando regla"); }
}

async function toggleRule(ruleId) {
    const rules = [...(schedulerData?.schedule?.rules || [])];
    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;
    rule.enabled = !rule.enabled;
    try {
        const tz = schedulerData?.schedule?.timezone || "America/Bogota";
        await api("PUT", `/accounts/${currentAccountId}/schedule`, { rules, timezone: tz });
        showToast(rule.enabled ? "Regla activada" : "Regla desactivada");
        loadSchedule();
    } catch (e) { showToast("Error actualizando regla"); }
}

async function deleteRule(ruleId) {
    if (!confirm("Eliminar esta regla de programacion?")) return;
    const rules = (schedulerData?.schedule?.rules || []).filter(r => r.id !== ruleId);
    try {
        const tz = schedulerData?.schedule?.timezone || "America/Bogota";
        await api("PUT", `/accounts/${currentAccountId}/schedule`, { rules, timezone: tz });
        showToast("Regla eliminada");
        loadSchedule();
    } catch (e) { showToast("Error eliminando regla"); }
}

// ─── Notifications ─────────────────────────────────────────────────────

let notificationsData = null;
let editingChannelId = null;

async function loadNotifications() {
    if (!currentAccountId) return;
    const section = document.getElementById("settings-notifications");
    const addBtn = document.getElementById("notif-add-btn");

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/notifications`);
        notificationsData = data;

        if (!data.enabled || !data.canEdit) {
            section.classList.add("hidden");
            return;
        }

        section.classList.remove("hidden");
        addBtn.classList.remove("hidden");
        renderNotificationChannels(data.channels || []);
    } catch (e) {
        section.classList.add("hidden");
    }
}

function renderNotificationChannels(channels) {
    const container = document.getElementById("notifications-list");
    if (channels.length === 0) {
        container.innerHTML = `
            <div class="empty-state small">
                <p class="empty-text">Sin canales configurados</p>
                <p class="empty-hint">Agrega email, Telegram o Teams</p>
            </div>`;
        return;
    }

    container.innerHTML = channels.map(ch => {
        const enabledClass = ch.enabled ? "enabled" : "disabled";
        const enabledLabel = ch.enabled ? "Activo" : "Inactivo";
        const typeIcon = getChannelTypeIcon(ch.type);
        const typeLabel = { email: "Email", telegram: "Telegram", teams: "Teams" }[ch.type] || ch.type;
        const eventsStr = (ch.events || []).map(e => {
            return { started: "Encendido", stopped: "Apagado", error: "Error", scheduler_executed: "Scheduler" }[e] || e;
        }).join(", ");

        return `
        <div class="schedule-rule ${enabledClass}">
            <div class="rule-header">
                <div class="rule-info">
                    <span class="notif-type-icon">${typeIcon}</span>
                    <span class="rule-description">${escapeHtml(ch.name)}</span>
                    <span class="notif-type-badge">${typeLabel}</span>
                    <span class="rule-status-badge ${enabledClass}">${enabledLabel}</span>
                </div>
                <div class="rule-actions">
                    <button class="btn-icon btn-icon-sm" onclick="testChannel('${ch.id}')" title="Probar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm" onclick="toggleChannel('${ch.id}')" title="${ch.enabled ? 'Desactivar' : 'Activar'}">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/><line x1="12" y1="2" x2="12" y2="12"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm" onclick="editChannel('${ch.id}')" title="Editar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="btn-icon btn-icon-sm btn-icon-danger" onclick="deleteChannel('${ch.id}')" title="Eliminar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>
            <div class="rule-details">
                <span class="notif-events-text">${eventsStr}</span>
            </div>
        </div>`;
    }).join("");
}

function getChannelTypeIcon(type) {
    switch (type) {
        case "email": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`;
        case "telegram": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
        case "teams": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
        default: return "";
    }
}

function updateChannelFields() {
    const type = document.querySelector('input[name="notif-type"]:checked')?.value || "email";
    document.getElementById("notif-fields-email").classList.toggle("hidden", type !== "email");
    document.getElementById("notif-fields-telegram").classList.toggle("hidden", type !== "telegram");
    document.getElementById("notif-fields-teams").classList.toggle("hidden", type !== "teams");
}

function showAddChannelForm() {
    editingChannelId = null;
    document.getElementById("notif-form-title").textContent = "Nuevo canal";
    document.getElementById("notif-name").value = "";
    document.querySelector('input[name="notif-type"][value="email"]').checked = true;
    updateChannelFields();
    clearChannelFields();
    document.querySelectorAll("#notif-form .checkboxes-grid input[type=checkbox]").forEach(cb => {
        cb.checked = cb.value === "started" || cb.value === "stopped";
    });
    document.getElementById("notif-form").classList.remove("hidden");
}

function editChannel(channelId) {
    const channels = notificationsData?.channels || [];
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    editingChannelId = channelId;
    document.getElementById("notif-form-title").textContent = "Editar canal";
    document.getElementById("notif-name").value = ch.name || "";
    const typeRadio = document.querySelector(`input[name="notif-type"][value="${ch.type}"]`);
    if (typeRadio) typeRadio.checked = true;
    updateChannelFields();
    clearChannelFields();
    const config = ch.config || {};
    if (ch.type === "email") {
        document.getElementById("notif-email-to").value = config.to || "";
        document.getElementById("notif-smtp-host").value = config.smtpHost || "";
        document.getElementById("notif-smtp-port").value = config.smtpPort || "";
        document.getElementById("notif-smtp-user").value = config.smtpUser || "";
    } else if (ch.type === "telegram") {
        document.getElementById("notif-tg-token").value = config.botToken || "";
        document.getElementById("notif-tg-chatid").value = config.chatId || "";
    } else if (ch.type === "teams") {
        document.getElementById("notif-teams-url").value = config.webhookUrl || "";
    }
    document.querySelectorAll("#notif-form .checkboxes-grid input[type=checkbox]").forEach(cb => {
        cb.checked = (ch.events || []).includes(cb.value);
    });
    document.getElementById("notif-form").classList.remove("hidden");
}

function clearChannelFields() {
    document.getElementById("notif-email-to").value = "";
    document.getElementById("notif-smtp-host").value = "";
    document.getElementById("notif-smtp-port").value = "";
    document.getElementById("notif-smtp-user").value = "";
    document.getElementById("notif-tg-token").value = "";
    document.getElementById("notif-tg-chatid").value = "";
    document.getElementById("notif-teams-url").value = "";
}

function cancelChannelForm() {
    document.getElementById("notif-form").classList.add("hidden");
    editingChannelId = null;
}

async function saveChannel() {
    const name = document.getElementById("notif-name").value.trim();
    const type = document.querySelector('input[name="notif-type"]:checked')?.value;
    if (!name) { showToast("Ingresa un nombre"); return; }

    let config = {};
    if (type === "email") {
        const to = document.getElementById("notif-email-to").value.trim();
        if (!to) { showToast("Ingresa el email"); return; }
        config = { to, smtpHost: document.getElementById("notif-smtp-host").value.trim(), smtpPort: parseInt(document.getElementById("notif-smtp-port").value) || 587, smtpUser: document.getElementById("notif-smtp-user").value.trim() };
    } else if (type === "telegram") {
        const chatId = document.getElementById("notif-tg-chatid").value.trim();
        if (!chatId) { showToast("Ingresa el Chat ID"); return; }
        config = { botToken: document.getElementById("notif-tg-token").value.trim(), chatId };
    } else if (type === "teams") {
        const webhookUrl = document.getElementById("notif-teams-url").value.trim();
        if (!webhookUrl) { showToast("Ingresa la URL del webhook"); return; }
        config = { webhookUrl };
    }

    const events = Array.from(document.querySelectorAll("#notif-form .checkboxes-grid input[type=checkbox]:checked")).map(cb => cb.value);
    if (events.length === 0) { showToast("Selecciona al menos un evento"); return; }

    const channels = [...(notificationsData?.channels || [])];
    if (editingChannelId) {
        const idx = channels.findIndex(c => c.id === editingChannelId);
        if (idx >= 0) channels[idx] = { ...channels[idx], name, type, config, events };
    } else {
        channels.push({ id: `ch-${Date.now()}`, type, name, config, events, enabled: true });
    }

    try {
        await api("PUT", `/accounts/${currentAccountId}/notifications`, { channels });
        showToast(editingChannelId ? "Canal actualizado" : "Canal creado");
        cancelChannelForm();
        loadNotifications();
    } catch (e) { showToast("Error guardando canal"); }
}

async function toggleChannel(channelId) {
    const channels = [...(notificationsData?.channels || [])];
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    ch.enabled = !ch.enabled;
    try {
        await api("PUT", `/accounts/${currentAccountId}/notifications`, { channels });
        showToast(ch.enabled ? "Canal activado" : "Canal desactivado");
        loadNotifications();
    } catch (e) { showToast("Error actualizando canal"); }
}

async function deleteChannel(channelId) {
    if (!confirm("Eliminar este canal?")) return;
    const channels = (notificationsData?.channels || []).filter(c => c.id !== channelId);
    try {
        await api("PUT", `/accounts/${currentAccountId}/notifications`, { channels });
        showToast("Canal eliminado");
        loadNotifications();
    } catch (e) { showToast("Error eliminando canal"); }
}

async function testChannel(channelId) {
    try {
        const data = await api("POST", `/accounts/${currentAccountId}/notifications/test`, { channelId });
        showToast(data.error || data.message || "Prueba enviada");
    } catch (e) { showToast("Error enviando prueba"); }
}

// ─── Users & API Keys ──────────────────────────────────────────────────

async function loadKeys() {
    if (!currentAccountId) return;
    const section = document.getElementById("settings-users");

    try {
        const data = await api("GET", `/keys/list`);
        if (data.error) {
            section.classList.add("hidden");
            return;
        }
        section.classList.remove("hidden");
        renderKeys(data.keys || []);
        // Admin can create operators, superadmin can create all
        const addBtn = document.querySelector("#settings-users-content .scheduler-actions-row .btn");
        if (addBtn) {
            addBtn.style.display = (userRole === "superadmin" || userRole === "admin") ? "" : "none";
        }
    } catch (e) {
        section.classList.add("hidden");
    }
}

function renderKeys(keys) {
    const container = document.getElementById("keys-list");
    if (keys.length === 0) {
        container.innerHTML = `<div class="empty-state small"><p class="empty-text">Sin API Keys</p></div>`;
        return;
    }

    container.innerHTML = keys.map(k => {
        const roleColors = { superadmin: "#f87171", admin: "#fbbf24", operator: "#34d399" };
        const roleColor = roleColors[k.role] || "#a1a1b5";
        const maskedKey = k.key.substring(0, 8) + "..." + k.key.substring(k.key.length - 4);
        const accountsStr = (k.accounts || []).join(", ");
        const isSelf = k.key === apiKey;

        // Delete button logic:
        // - Never show for self
        // - Superadmin: can delete admin and operator (not other superadmin)
        // - Admin: can delete operator only
        // - Operator: cannot delete anyone
        let canDelete = false;
        if (!isSelf) {
            if (userRole === "superadmin" && k.role !== "superadmin") canDelete = true;
            if (userRole === "admin" && k.role === "operator") canDelete = true;
        }

        // Edit permissions button (superadmin can edit all, admin can edit operators)
        let canEdit = false;
        if (!isSelf) {
            if (userRole === "superadmin" && k.role !== "superadmin") canEdit = true;
            if (userRole === "admin" && k.role === "operator") canEdit = true;
        }

        return `
        <div class="schedule-rule enabled">
            <div class="rule-header">
                <div class="rule-info">
                    <span class="rule-description">${escapeHtml(k.name || 'Sin nombre')}</span>
                    <span class="notif-type-badge" style="background:${roleColor}20;color:${roleColor}">${k.role || 'operator'}</span>
                    ${isSelf ? '<span class="notif-type-badge" style="background:#6366f120;color:#6366f1">Tu</span>' : ''}
                </div>
                <div class="rule-actions">
                    ${canEdit ? `<button class="btn-icon btn-icon-sm" onclick="editKeyPermissions('${k.key}')" title="Editar permisos">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>` : ''}
                    ${canDelete ? `<button class="btn-icon btn-icon-sm btn-icon-danger" onclick="deleteKey('${k.key}')" title="Eliminar">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>` : ''}
                </div>
            </div>
            <div class="rule-details">
                <span class="notif-events-text"><code>${maskedKey}</code> · Cuentas: ${accountsStr || '*'}</span>
            </div>
        </div>`;
    }).join("");
}

function showAddKeyForm() {
    document.getElementById("key-form").classList.remove("hidden");
    document.getElementById("key-result").classList.add("hidden");
    document.getElementById("key-name").value = "";
    document.querySelector('input[name="key-role"][value="operator"]').checked = true;
    document.getElementById("key-sched-view").checked = true;
    document.getElementById("key-sched-edit").checked = false;

    // Admin can only create operators - hide other role options
    const adminRadio = document.querySelector('input[name="key-role"][value="admin"]');
    const superRadio = document.querySelector('input[name="key-role"][value="superadmin"]');
    if (adminRadio) adminRadio.parentElement.style.display = userRole === "superadmin" ? "" : "none";
    if (superRadio) superRadio.parentElement.style.display = userRole === "superadmin" ? "" : "none";

    // Render account checkboxes
    renderKeyAccountsCheckboxes(["*"]);

    // Reset save button
    const saveBtn = document.querySelector("#key-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear Key"; saveBtn.onclick = saveKey; }
}

function cancelKeyForm() {
    document.getElementById("key-form").classList.add("hidden");
    // Reset save button to create mode
    const saveBtn = document.querySelector("#key-form .btn-save-rule");
    if (saveBtn) {
        saveBtn.textContent = "Crear Key";
        saveBtn.onclick = saveKey;
    }
}

async function saveKey() {
    const name = document.getElementById("key-name").value.trim();
    const role = document.querySelector('input[name="key-role"]:checked')?.value || "operator";

    // Read accounts from checkboxes
    const allChecked = document.querySelector('#key-accounts-checkboxes input[value="*"]')?.checked;
    let accounts;
    if (allChecked) {
        accounts = ["*"];
    } else {
        accounts = Array.from(document.querySelectorAll('#key-accounts-checkboxes input[type=checkbox]:checked:not([value="*"])')).map(cb => cb.value);
    }

    const schedView = document.getElementById("key-sched-view").checked;
    const schedEdit = document.getElementById("key-sched-edit").checked;

    if (!name) { showToast("Ingresa un nombre"); return; }

    const body = { name, role, accounts, scheduler: { view: schedView, edit: schedEdit } };

    try {
        const data = await api("POST", `/keys/create`, body);
        if (data.key) {
            document.getElementById("key-form").classList.add("hidden");
            document.getElementById("key-result").classList.remove("hidden");
            document.getElementById("key-result-value").textContent = data.key;
            showToast("API Key creada");
            loadKeys();
        } else {
            showToast(data.error || "Error creando key");
        }
    } catch (e) { showToast("Error creando key"); }
}

function copyKey() {
    const key = document.getElementById("key-result-value").textContent;
    navigator.clipboard.writeText(key).then(() => showToast("Key copiada al portapapeles"));
}

function closeKeyResult() {
    document.getElementById("key-result").classList.add("hidden");
}

async function deleteKey(keyId) {
    if (!confirm("Eliminar esta API Key? El usuario perdera acceso inmediatamente.")) return;
    try {
        const data = await api("DELETE", `/keys/${keyId}`);
        if (data.error) { showToast(data.error); return; }
        showToast("Key eliminada");
        loadKeys();
    } catch (e) {
        showToast("Error eliminando key");
    }
}

async function editKeyPermissions(keyId) {
    let keysData;
    try {
        keysData = await api("GET", "/keys/list");
    } catch (e) { showToast("Error cargando keys"); return; }

    const keyData = (keysData.keys || []).find(k => k.key === keyId);
    if (!keyData) { showToast("Key no encontrada"); return; }

    const form = document.getElementById("key-form");
    form.classList.remove("hidden");
    document.getElementById("key-result").classList.add("hidden");

    document.getElementById("key-name").value = keyData.name || "";
    renderKeyAccountsCheckboxes(keyData.accounts || []);

    // Set role radio
    const roleRadio = document.querySelector(`input[name="key-role"][value="${keyData.role || 'operator'}"]`);
    if (roleRadio) roleRadio.checked = true;

    // Hide role options based on caller role
    const adminRadio = document.querySelector('input[name="key-role"][value="admin"]');
    const superRadio = document.querySelector('input[name="key-role"][value="superadmin"]');
    if (userRole === "superadmin") {
        // Superadmin can see all but can't escalate to superadmin
        if (adminRadio) adminRadio.parentElement.style.display = "";
        if (superRadio) superRadio.parentElement.style.display = "none";
    } else {
        // Admin can only keep as operator
        if (adminRadio) adminRadio.parentElement.style.display = "none";
        if (superRadio) superRadio.parentElement.style.display = "none";
    }

    // Set scheduler checkboxes
    const sched = keyData.scheduler || {};
    document.getElementById("key-sched-view").checked = sched.view || false;
    document.getElementById("key-sched-edit").checked = sched.edit || false;

    // Change button to "Actualizar"
    const saveBtn = form.querySelector(".btn-save-rule");
    saveBtn.textContent = "Actualizar permisos";
    saveBtn.onclick = () => updateKeyPermissions(keyId);
}

async function updateKeyPermissions(keyId) {
    const name = document.getElementById("key-name").value.trim();
    const role = document.querySelector('input[name="key-role"]:checked')?.value || "operator";

    // Read accounts from checkboxes
    const allChecked = document.querySelector('#key-accounts-checkboxes input[value="*"]')?.checked;
    let accounts;
    if (allChecked) {
        accounts = ["*"];
    } else {
        accounts = Array.from(document.querySelectorAll('#key-accounts-checkboxes input[type=checkbox]:checked:not([value="*"])')).map(cb => cb.value);
    }

    const schedView = document.getElementById("key-sched-view").checked;
    const schedEdit = document.getElementById("key-sched-edit").checked;

    try {
        await api("POST", "/keys/create", {
            key: keyId, name, role, accounts,
            scheduler: { view: schedView, edit: schedEdit }
        });
        showToast("Permisos actualizados");
        cancelKeyForm();
        loadKeys();
    } catch (e) { showToast("Error actualizando permisos"); }
}

// ─── Cost Estimation ───────────────────────────────────────────────────

async function loadCosts() {
    if (!currentAccountId) return;
    const section = document.getElementById("settings-costs");

    try {
        const data = await api("GET", `/accounts/${currentAccountId}/costs`);
        if (!data.enabled || !data.costs || data.costs.length === 0) {
            section.classList.add("hidden");
            return;
        }

        section.classList.remove("hidden");
        renderCosts(data);
    } catch (e) {
        section.classList.add("hidden");
    }
}

function renderCosts(data) {
    const container = document.getElementById("costs-list");
    const totalContainer = document.getElementById("costs-total");

    container.innerHTML = data.costs.map(c => {
        const barWidth = data.totalCost > 0 ? Math.min((c.costThisMonth / data.totalCost) * 100, 100) : 0;
        return `
        <div class="cost-item">
            <div class="cost-item-header">
                <div class="cost-item-info">
                    <span class="cost-item-name">${escapeHtml(c.name)}</span>
                    <span class="cost-item-type">${c.instanceType}</span>
                </div>
                <span class="cost-item-value">$${c.costThisMonth.toFixed(2)}</span>
            </div>
            <div class="cost-bar-bg">
                <div class="cost-bar" style="width: ${barWidth}%"></div>
            </div>
            <div class="cost-item-meta">
                <span>${c.uptimeHours}h encendida</span>
                <span>$${c.hourlyRate.toFixed(4)}/h</span>
                <span>Proy: $${c.projection.toFixed(2)}</span>
            </div>
        </div>`;
    }).join("");

    totalContainer.innerHTML = `
        <div class="costs-total-row">
            <div class="costs-total-item">
                <span class="costs-total-label">Total acumulado</span>
                <span class="costs-total-value">$${data.totalCost.toFixed(2)} ${data.currency}</span>
            </div>
            <div class="costs-total-item">
                <span class="costs-total-label">Proyeccion mes</span>
                <span class="costs-total-value projection">$${data.totalProjection.toFixed(2)} ${data.currency}</span>
            </div>
        </div>
        <p class="costs-disclaimer">Basado en ${data.daysElapsed} dias de actividad registrada. Precios On-Demand us-east-1.</p>
    `;
}

// ─── Export / Import ────────────────────────────────────────────────────

async function exportConfig() {
    try {
        const data = await api("GET", "/config");
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `cloud-control-config-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        showToast("Config exportada");
    } catch (e) {
        showToast("Error exportando config");
    }
}

async function importConfig(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!confirm("Importar reemplazara TODA la configuracion actual. Continuar?")) {
        event.target.value = "";
        return;
    }
    try {
        const text = await file.text();
        const data = JSON.parse(text);
        await api("PUT", "/config", data);
        showToast("Config importada exitosamente. Recarga la pagina.");
        event.target.value = "";
    } catch (e) {
        showToast("Error importando: verifica que el JSON sea valido");
        event.target.value = "";
    }
}

// ─── Persistent Activity Log ────────────────────────────────────────────

async function loadActivity() {
    if (!currentAccountId) return;
    try {
        const data = await api("GET", `/accounts/${currentAccountId}/activity`);
        renderPersistentActivity(data.activities || []);
    } catch (e) {}
}

function renderPersistentActivity(activities) {
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

async function clearActivity() {
    if (!confirm("Limpiar todo el historial de actividad?")) return;
    try {
        await api("DELETE", `/accounts/${currentAccountId}/activity`);
        showToast("Actividad limpiada");
        loadActivity();
    } catch (e) {
        showToast("Error limpiando actividad");
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
    while (log.children.length > 20) log.lastChild.remove();
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

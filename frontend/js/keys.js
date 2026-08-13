/**
 * Cloud Control Panel - Users & API Keys module
 */

import { state, api, showToast, escapeHtml } from './utils.js';

export async function loadKeys() {
    if (!state.currentAccountId) return;
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
            addBtn.style.display = (state.userRole === "superadmin" || state.userRole === "admin") ? "" : "none";
        }
    } catch (e) {
        section.classList.add("hidden");
    }
}

export function renderKeys(keys) {
    const container = document.getElementById("keys-list");
    if (keys.length === 0) {
        container.innerHTML = `<div class="empty-state small"><p class="empty-text">Sin API Keys</p></div>`;
        return;
    }

    container.innerHTML = keys.map(k => {
        const roleColors = { superadmin: "#f87171", admin: "#fbbf24", operator: "#34d399" };
        const roleColor = roleColors[k.role] || "#a1a1b5";
        const maskedKey = k.key_preview || (k.key_id ? k.key_id.substring(0, 8) + "..." : "???");
        const accountsStr = (k.accounts || []).join(", ");
        const keyRef = k.key_id || k.key || "";
        const isSelf = false; // Can't determine self with hashed keys

        // Delete button logic:
        // - Never show for self
        // - Superadmin: can delete admin and operator (not other superadmin)
        // - Admin: can delete operator only
        // - Operator: cannot delete anyone
        let canDelete = false;
        if (!isSelf) {
            if (state.userRole === "superadmin" && k.role !== "superadmin") canDelete = true;
            if (state.userRole === "admin" && k.role === "operator") canDelete = true;
        }

        // Edit permissions button (superadmin can edit all, admin can edit operators)
        let canEdit = false;
        if (!isSelf) {
            if (state.userRole === "superadmin" && k.role !== "superadmin") canEdit = true;
            if (state.userRole === "admin" && k.role === "operator") canEdit = true;
        }

        return `
        <div class="schedule-rule enabled">
            <div class="rule-header">
                <div class="rule-info">
                    <span class="rule-description">${escapeHtml(k.name || 'Sin nombre')}</span>
                    <span class="notif-type-badge" style="background:${roleColor}20;color:${roleColor}">${k.role || 'operator'}</span>
                </div>
                <div class="rule-actions">
                    ${canEdit ? `<button class="btn-icon btn-icon-sm" onclick="editKeyPermissions('${keyRef}')" title="Editar permisos">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>` : ''}
                    ${canDelete ? `<button class="btn-icon btn-icon-sm btn-icon-danger" onclick="deleteKey('${keyRef}')" title="Eliminar">
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

export function showAddKeyForm() {
    document.getElementById("key-form").classList.remove("hidden");
    document.getElementById("key-result").classList.add("hidden");
    document.getElementById("key-name").value = "";
    document.querySelector('input[name="key-role"][value="operator"]').checked = true;
    document.getElementById("key-sched-view").checked = true;
    document.getElementById("key-sched-edit").checked = false;

    // Admin can only create operators - hide other role options
    const adminRadio = document.querySelector('input[name="key-role"][value="admin"]');
    const superRadio = document.querySelector('input[name="key-role"][value="superadmin"]');
    if (adminRadio) adminRadio.parentElement.style.display = state.userRole === "superadmin" ? "" : "none";
    if (superRadio) superRadio.parentElement.style.display = state.userRole === "superadmin" ? "" : "none";

    // Render account checkboxes
    renderKeyAccountsCheckboxes(["*"]);

    // Reset save button
    const saveBtn = document.querySelector("#key-form .btn-save-rule");
    if (saveBtn) { saveBtn.textContent = "Crear Key"; saveBtn.onclick = saveKey; }
}

export function cancelKeyForm() {
    document.getElementById("key-form").classList.add("hidden");
    // Reset save button to create mode
    const saveBtn = document.querySelector("#key-form .btn-save-rule");
    if (saveBtn) {
        saveBtn.textContent = "Crear Key";
        saveBtn.onclick = saveKey;
    }
}

export async function saveKey() {
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

export function copyKey() {
    const key = document.getElementById("key-result-value").textContent;
    navigator.clipboard.writeText(key).then(() => showToast("Key copiada al portapapeles"));
}

export function closeKeyResult() {
    document.getElementById("key-result").classList.add("hidden");
}

export async function deleteKey(keyId) {
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

export async function renderKeyAccountsCheckboxes(selectedAccounts) {
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

export function toggleAllAccounts(checkbox) {
    const container = document.getElementById("key-accounts-checkboxes");
    const others = container.querySelectorAll('input[type=checkbox]:not([value="*"])');
    others.forEach(cb => {
        cb.disabled = checkbox.checked;
        if (checkbox.checked) cb.checked = true;
    });
}

export async function editKeyPermissions(keyId) {
    let keysData;
    try {
        keysData = await api("GET", "/keys/list");
    } catch (e) { showToast("Error cargando keys"); return; }

    const keyData = (keysData.keys || []).find(k => k.key_id === keyId);
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
    if (state.userRole === "superadmin") {
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

export async function updateKeyPermissions(keyId) {
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
        await api("PUT", `/keys/${keyId}`, {
            name, role, accounts,
            scheduler: { view: schedView, edit: schedEdit }
        });
        showToast("Permisos actualizados");
        cancelKeyForm();
        loadKeys();
    } catch (e) { showToast("Error actualizando permisos"); }
}

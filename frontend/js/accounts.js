/**
 * Cloud Control Panel - Accounts module
 */

import { state, api, showToast, escapeHtml } from './utils.js';
import { showScreen } from './navigation.js';
import { refreshInstances } from './instances.js';

export async function loadAccounts() {
    try {
        const data = await api("GET", "/accounts");
        document.getElementById("user-name").textContent = data.user || "";
        const accounts = data.accounts || [];

        // Show add button for superadmin
        const addBtn = document.getElementById("btn-add-account");
        if (data.role === "superadmin") {
            addBtn.classList.remove("hidden");
            state.userRole = data.role;
        } else {
            addBtn.classList.add("hidden");
            state.userRole = data.role || "operator";
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

export function renderAccounts(accounts) {
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
                ${state.userRole === "superadmin" ? `<button class="btn-icon btn-icon-sm" onclick="event.stopPropagation(); editAccount('${acc.id}')" title="Editar cuenta">
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

export function openAccount(accountId, accountName) {
    state.currentAccountId = accountId;
    document.getElementById("account-title").textContent = accountName;
    showScreen("instances-screen");
    refreshInstances();
}

// ─── Admin CRUD (Accounts) ─────────────────────────────────────────────

export function showAddAccountForm() {
    document.getElementById("account-form").classList.remove("hidden");
    document.getElementById("acc-id").value = "";
    document.getElementById("acc-name").value = "";
    document.getElementById("acc-aws-id").value = "";
    document.getElementById("acc-region").value = "us-east-1";
    document.getElementById("acc-role-arn").value = "";
}

export function cancelAccountForm() {
    document.getElementById("account-form").classList.add("hidden");
}

export async function saveAccount() {
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

export async function deleteAccount(accountId) {
    if (!confirm(`Eliminar la cuenta "${accountId}" y todo su contenido (instancias, grupos, reglas)?`)) return;
    try {
        await api("DELETE", `/accounts/${accountId}`);
        showToast("Cuenta eliminada");
        loadAccounts();
    } catch (e) { showToast("Error eliminando cuenta"); }
}

export function editAccount(accountId) {
    const newName = prompt("Nuevo nombre de la cuenta:");
    if (!newName) return;
    api("POST", "/accounts", { id: accountId, name: newName })
        .then(() => { showToast("Cuenta actualizada"); loadAccounts(); })
        .catch(() => showToast("Error actualizando cuenta"));
}

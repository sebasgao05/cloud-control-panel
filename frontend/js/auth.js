/**
 * Cloud Control Panel - Authentication module
 */

import { state, api, showToast } from './utils.js';
import { showScreen } from './navigation.js';

export async function authenticate() {
    const input = document.getElementById("api-key-input");
    const key = input.value.trim();
    if (!key) {
        showToast("Ingresa tu API Key");
        return;
    }

    state.apiKey = key;

    try {
        const data = await api("GET", "/accounts");

        // Auth successful
        if (document.getElementById("remember-key").checked) {
            localStorage.setItem("ccp-api-key", key);
        }

        document.getElementById("user-name").textContent = data.user || "";
        const accounts = data.accounts || [];

        const addBtn = document.getElementById("btn-add-account");
        if (data.role === "superadmin") {
            addBtn.classList.remove("hidden");
            state.userRole = data.role;
        } else {
            addBtn.classList.add("hidden");
            state.userRole = data.role || "operator";
        }

        // Import and use accounts rendering
        const { renderAccounts, openAccount } = await import('./accounts.js');
        renderAccounts(accounts);

        if (accounts.length === 1) {
            openAccount(accounts[0].id, accounts[0].name);
            return;
        }

        showScreen("accounts-screen");
    } catch (e) {
        state.apiKey = "";
        localStorage.removeItem("ccp-api-key");

        if (e.message === "Unauthorized") {
            showAuthError("Autenticación fallida", "La API Key ingresada no es válida o no existe.");
        } else if (e.message === "Forbidden") {
            showAuthError("Acceso denegado", "La API Key no tiene permisos para acceder.");
        } else if (e.message === "NetworkError") {
            showAuthError("Error de red", "No se pudo conectar con el servidor. Verifica tu conexión.");
        } else {
            showAuthError("Error", e.message || "Error desconocido al autenticar.");
        }
    }
}

function showAuthError(title, message) {
    // Remove existing error notification
    const existing = document.querySelector(".auth-error");
    if (existing) existing.remove();

    const container = document.getElementById("auth-screen") || document.body;
    const errorDiv = document.createElement("div");
    errorDiv.className = "auth-error";
    errorDiv.innerHTML = `
        <div class="auth-error-content">
            <div class="auth-error-header">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
                <strong>${title}</strong>
                <button class="auth-error-close" onclick="this.closest('.auth-error').remove()">×</button>
            </div>
            <p>${message}</p>
        </div>
    `;

    // Insert after the login form
    const form = container.querySelector(".auth-card") || container.querySelector(".card") || container;
    form.parentNode.insertBefore(errorDiv, form.nextSibling);

    // Auto-dismiss after 8 seconds
    setTimeout(() => errorDiv.remove(), 8000);
}

export function logout() {
    state.apiKey = "";
    state.currentAccountId = null;
    state.currentInstanceId = null;
    state.currentGroupId = null;
    localStorage.removeItem("ccp-api-key");
    if (state.statusInterval) clearInterval(state.statusInterval);
    showScreen("auth-screen");
}

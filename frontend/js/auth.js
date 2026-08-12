/**
 * Cloud Control Panel - Authentication module
 */

import { state, showToast } from './utils.js';
import { showScreen } from './navigation.js';
import { loadAccounts } from './accounts.js';

export function authenticate() {
    const input = document.getElementById("api-key-input");
    const key = input.value.trim();
    if (!key) {
        showToast("Ingresa tu API Key");
        return;
    }

    state.apiKey = key;

    if (document.getElementById("remember-key").checked) {
        localStorage.setItem("ccp-api-key", key);
    }

    loadAccounts();
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

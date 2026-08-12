/**
 * Cloud Control Panel - Navigation module
 */

import { state } from './utils.js';
import { closeSettingsPanel } from './settings.js';

export function showScreen(screenId) {
    document.querySelectorAll(".screen").forEach(s => s.classList.add("hidden"));
    const target = document.getElementById(screenId);
    target.classList.remove("hidden");
    target.style.animation = "none";
    target.offsetHeight;
    target.style.animation = "";
}

export function goBackToAccounts() {
    state.currentAccountId = null;
    state.currentGroupId = null;
    if (state.statusInterval) clearInterval(state.statusInterval);
    closeSettingsPanel();
    showScreen("accounts-screen");
}

export function goBackToInstances() {
    state.currentInstanceId = null;
    if (state.statusInterval) clearInterval(state.statusInterval);
    if (state.cameFromGroup && state.currentGroupId) {
        showScreen("group-screen");
        // Dynamic import to avoid circular dependency
        import('./groups.js').then(m => m.refreshGroupInstances());
    } else {
        showScreen("instances-screen");
        import('./instances.js').then(m => m.refreshInstances());
    }
}

export function goBackFromGroup() {
    state.currentGroupId = null;
    showScreen("instances-screen");
}

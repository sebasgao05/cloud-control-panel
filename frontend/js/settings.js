/**
 * Cloud Control Panel - Settings Panel module
 */

import { state, api, showToast } from './utils.js';
import { loadSchedule } from './scheduler.js';
import { loadNotifications } from './notifications.js';
import { loadCosts } from './costs.js';
import { loadKeys } from './keys.js';

export function openSettingsPanel() {
    document.getElementById("settings-overlay").classList.remove("hidden");
    document.getElementById("settings-panel").classList.add("open");
    loadSchedule();
    loadNotifications();
    loadCosts();
    loadKeys();
    // Export/Import only for superadmin
    const exportSection = document.getElementById("settings-export");
    if (exportSection) {
        exportSection.style.display = state.userRole === "superadmin" ? "" : "none";
    }
    // If admin, only show costs and keys (not scheduler/notifs)
    if (state.userRole === "admin") {
        const schedSection = document.getElementById("settings-scheduler");
        if (schedSection) schedSection.style.display = "none";
        const notifSection = document.getElementById("settings-notifications");
        if (notifSection) notifSection.style.display = "none";
    }
}

export function closeSettingsPanel() {
    document.getElementById("settings-overlay").classList.add("hidden");
    document.getElementById("settings-panel").classList.remove("open");
}

export function toggleSettingsSection(section) {
    const content = document.getElementById(`settings-${section}-content`);
    const header = content.previousElementSibling;
    content.classList.toggle("collapsed");
    header.classList.toggle("collapsed");
}

// ─── Export / Import ────────────────────────────────────────────────────

export async function exportConfig() {
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

export async function importConfig(event) {
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

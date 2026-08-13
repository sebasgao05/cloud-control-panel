/**
 * Cloud Control Panel - Notifications module
 */

import { state, api, showToast, escapeHtml } from './utils.js';

let notificationsData = null;
let editingChannelId = null;

export async function loadNotifications() {
    if (!state.currentAccountId) return;
    const section = document.getElementById("settings-notifications");
    const addBtn = document.getElementById("notif-add-btn");

    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/notifications`);
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

export function renderNotificationChannels(channels) {
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

export function getChannelTypeIcon(type) {
    switch (type) {
        case "email": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`;
        case "telegram": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
        case "teams": return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
        default: return "";
    }
}

export function updateChannelFields() {
    const type = document.querySelector('input[name="notif-type"]:checked')?.value || "email";
    document.getElementById("notif-fields-email").classList.toggle("hidden", type !== "email");
    document.getElementById("notif-fields-telegram").classList.toggle("hidden", type !== "telegram");
    document.getElementById("notif-fields-teams").classList.toggle("hidden", type !== "teams");
}

export function showAddChannelForm() {
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

export function editChannel(channelId) {
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
        document.getElementById("notif-smtp-pass").value = config.smtpPass || "";
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
    document.getElementById("notif-smtp-pass").value = "";
    document.getElementById("notif-tg-token").value = "";
    document.getElementById("notif-tg-chatid").value = "";
    document.getElementById("notif-teams-url").value = "";
}

export function cancelChannelForm() {
    document.getElementById("notif-form").classList.add("hidden");
    editingChannelId = null;
}

export async function saveChannel() {
    const name = document.getElementById("notif-name").value.trim();
    const type = document.querySelector('input[name="notif-type"]:checked')?.value;
    if (!name) { showToast("Ingresa un nombre"); return; }

    let config = {};
    if (type === "email") {
        const to = document.getElementById("notif-email-to").value.trim();
        if (!to) { showToast("Ingresa el email"); return; }
        config = { to, smtpHost: document.getElementById("notif-smtp-host").value.trim(), smtpPort: parseInt(document.getElementById("notif-smtp-port").value) || 587, smtpUser: document.getElementById("notif-smtp-user").value.trim(), smtpPass: document.getElementById("notif-smtp-pass").value.trim() };
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
        await api("PUT", `/accounts/${state.currentAccountId}/notifications`, { channels });
        showToast(editingChannelId ? "Canal actualizado" : "Canal creado");
        cancelChannelForm();
        loadNotifications();
    } catch (e) { showToast("Error guardando canal"); }
}

export async function toggleChannel(channelId) {
    const channels = [...(notificationsData?.channels || [])];
    const ch = channels.find(c => c.id === channelId);
    if (!ch) return;
    ch.enabled = !ch.enabled;
    try {
        await api("PUT", `/accounts/${state.currentAccountId}/notifications`, { channels });
        showToast(ch.enabled ? "Canal activado" : "Canal desactivado");
        loadNotifications();
    } catch (e) { showToast("Error actualizando canal"); }
}

export async function deleteChannel(channelId) {
    if (!confirm("Eliminar este canal?")) return;
    const channels = (notificationsData?.channels || []).filter(c => c.id !== channelId);
    try {
        await api("PUT", `/accounts/${state.currentAccountId}/notifications`, { channels });
        showToast("Canal eliminado");
        loadNotifications();
    } catch (e) { showToast("Error eliminando canal"); }
}

export async function testChannel(channelId) {
    try {
        const data = await api("POST", `/accounts/${state.currentAccountId}/notifications/test`, { channelId });
        showToast(data.error || data.message || "Prueba enviada");
    } catch (e) { showToast("Error enviando prueba"); }
}

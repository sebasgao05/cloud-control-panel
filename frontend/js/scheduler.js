/**
 * Cloud Control Panel - Scheduler module
 */

import { state, api, showToast, escapeHtml } from './utils.js';

let schedulerData = null;
let schedulerPermissions = { view: false, edit: false };
let editingRuleId = null;
let accountInstances = [];

export async function loadSchedule() {
    if (!state.currentAccountId) return;

    const section = document.getElementById("settings-scheduler");
    const addBtn = document.getElementById("settings-scheduler-add-btn");

    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/schedule`);
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

export function renderScheduleRules(schedule) {
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

export function cronToHuman(cron) {
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

export function showAddRuleForm() {
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

export function editRule(ruleId) {
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

export function cancelRuleForm() {
    document.getElementById("scheduler-form").classList.add("hidden");
    editingRuleId = null;
}

export async function saveRule() {
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
        await api("PUT", `/accounts/${state.currentAccountId}/schedule`, { rules, timezone: tz });
        showToast(editingRuleId ? "Regla actualizada" : "Regla creada");
        cancelRuleForm();
        loadSchedule();
    } catch (e) { showToast("Error guardando regla"); }
}

export async function toggleRule(ruleId) {
    const rules = [...(schedulerData?.schedule?.rules || [])];
    const rule = rules.find(r => r.id === ruleId);
    if (!rule) return;
    rule.enabled = !rule.enabled;
    try {
        const tz = schedulerData?.schedule?.timezone || "America/Bogota";
        await api("PUT", `/accounts/${state.currentAccountId}/schedule`, { rules, timezone: tz });
        showToast(rule.enabled ? "Regla activada" : "Regla desactivada");
        loadSchedule();
    } catch (e) { showToast("Error actualizando regla"); }
}

export async function deleteRule(ruleId) {
    if (!confirm("Eliminar esta regla de programacion?")) return;
    const rules = (schedulerData?.schedule?.rules || []).filter(r => r.id !== ruleId);
    try {
        const tz = schedulerData?.schedule?.timezone || "America/Bogota";
        await api("PUT", `/accounts/${state.currentAccountId}/schedule`, { rules, timezone: tz });
        showToast("Regla eliminada");
        loadSchedule();
    } catch (e) { showToast("Error eliminando regla"); }
}

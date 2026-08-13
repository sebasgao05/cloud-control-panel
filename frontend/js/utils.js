/**
 * Cloud Control Panel - Shared utilities and state
 */

export const API_BASE = "/api";

// Shared mutable state object
export const state = {
    apiKey: "",
    currentAccountId: null,
    currentInstanceId: null,
    currentGroupId: null,
    statusInterval: null,
    cachedInstancesData: null,
    cameFromGroup: false,
    userRole: "operator",
};

// ─── API Helper ────────────────────────────────────────────────────────

export async function api(method, path, body = null) {
    const opts = {
        method,
        headers: {
            "Content-Type": "application/json",
            "X-Api-Key": state.apiKey,
        },
    };
    if (body) opts.body = JSON.stringify(body);

    let res;
    try {
        res = await fetch(`${API_BASE}${path}`, opts);
    } catch (e) {
        throw new Error("NetworkError");
    }

    if (res.status === 401) {
        throw new Error("Unauthorized");
    }

    // Don't logout on 403 for non-GET requests (permission denied for action)
    if (res.status === 403 && method === "GET") {
        throw new Error("Forbidden");
    }

    const data = await res.json();

    // If 403 on mutation, show error but don't logout
    if (res.status === 403) {
        showToast(data.error || "Sin permisos para esta accion");
        throw new Error(data.error || "Forbidden");
    }

    return data;
}

// ─── Utilities ─────────────────────────────────────────────────────────

export function logActivity(message) {
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

export function showToast(message) {
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

export function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

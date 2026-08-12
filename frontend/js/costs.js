/**
 * Cloud Control Panel - Cost Estimation module
 */

import { state, api, escapeHtml } from './utils.js';

export async function loadCosts() {
    if (!state.currentAccountId) return;
    const section = document.getElementById("settings-costs");

    try {
        const data = await api("GET", `/accounts/${state.currentAccountId}/costs`);
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

export function renderCosts(data) {
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

/**
 * Cloud Control Panel - CloudWatch Metrics Chart module
 * Renders CPU and Memory utilization line charts using Chart.js.
 * Fetches data from GET /api/accounts/{accountId}/resources/{resourceId}/metrics
 * Auto-refreshes every 60 seconds while the detail view is open.
 */

import { state, api } from './utils.js';

let cpuChartInstance = null;
let memoryChartInstance = null;
let metricsRefreshInterval = null;

/**
 * Initialize the metrics charts when a resource detail view is opened.
 * Fetches metrics data and sets up auto-refresh every 60 seconds.
 */
export function initMetricsCharts() {
    loadMetricsData();
    stopMetricsAutoRefresh();
    metricsRefreshInterval = setInterval(loadMetricsData, 60000);
}

/**
 * Destroy chart instances and stop auto-refresh when leaving the detail view.
 */
export function destroyMetricsCharts() {
    stopMetricsAutoRefresh();
    if (cpuChartInstance) {
        cpuChartInstance.destroy();
        cpuChartInstance = null;
    }
    if (memoryChartInstance) {
        memoryChartInstance.destroy();
        memoryChartInstance = null;
    }
}

/**
 * Stop the auto-refresh interval.
 */
function stopMetricsAutoRefresh() {
    if (metricsRefreshInterval) {
        clearInterval(metricsRefreshInterval);
        metricsRefreshInterval = null;
    }
}

/**
 * Fetch metrics data from the API and render charts.
 */
async function loadMetricsData() {
    const cpuContainer = document.getElementById('metrics-cpu-container');
    const memContainer = document.getElementById('metrics-memory-container');

    if (!cpuContainer || !memContainer) return;
    if (!state.currentAccountId || !state.currentInstanceId) return;

    const cpuCanvas = document.getElementById('metrics-cpu-canvas');
    const cpuMessage = document.getElementById('metrics-cpu-message');
    const memCanvas = document.getElementById('metrics-memory-canvas');
    const memMessage = document.getElementById('metrics-memory-message');

    if (!cpuCanvas || !cpuMessage || !memCanvas || !memMessage) return;

    try {
        const data = await api(
            'GET',
            `/accounts/${state.currentAccountId}/resources/${state.currentInstanceId}/metrics`
        );

        // Handle non-running state: reason field present
        if (data.reason) {
            showMetricsMessage(cpuCanvas, cpuMessage, data.reason);
            showMetricsMessage(memCanvas, memMessage, data.reason);
            destroyChartInstances();
            return;
        }

        // Handle error response
        if (data.error) {
            showMetricsMessage(cpuCanvas, cpuMessage, 'Metrics temporarily unavailable');
            showMetricsMessage(memCanvas, memMessage, 'Metrics temporarily unavailable');
            destroyChartInstances();
            return;
        }

        // Render CPU chart
        const cpuData = data.cpu || [];
        if (cpuData.length > 0) {
            cpuMessage.classList.add('hidden');
            cpuCanvas.classList.remove('hidden');
            renderCpuChart(cpuData);
        } else {
            showMetricsMessage(cpuCanvas, cpuMessage, 'No CPU data available');
            if (cpuChartInstance) {
                cpuChartInstance.destroy();
                cpuChartInstance = null;
            }
        }

        // Render Memory chart
        const memData = data.memory || [];
        if (memData.length > 0) {
            memMessage.classList.add('hidden');
            memCanvas.classList.remove('hidden');
            renderMemoryChart(memData);
        } else {
            showMetricsMessage(memCanvas, memMessage, 'Memory monitoring not enabled on this resource');
            if (memoryChartInstance) {
                memoryChartInstance.destroy();
                memoryChartInstance = null;
            }
        }
    } catch (e) {
        // Network or unexpected error
        showMetricsMessage(cpuCanvas, cpuMessage, 'Metrics temporarily unavailable');
        showMetricsMessage(memCanvas, memMessage, 'Metrics temporarily unavailable');
        destroyChartInstances();
    }
}

/**
 * Show a message and hide the canvas for a metrics section.
 */
function showMetricsMessage(canvas, messageEl, text) {
    canvas.classList.add('hidden');
    messageEl.classList.remove('hidden');
    messageEl.textContent = text;
}

/**
 * Destroy both chart instances without stopping the refresh interval.
 */
function destroyChartInstances() {
    if (cpuChartInstance) {
        cpuChartInstance.destroy();
        cpuChartInstance = null;
    }
    if (memoryChartInstance) {
        memoryChartInstance.destroy();
        memoryChartInstance = null;
    }
}

/**
 * Format timestamp for chart axis labels.
 * Shows HH:MM format.
 */
function formatTimestamp(isoString) {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
    });
}

/**
 * Shared Chart.js options for metrics line charts.
 */
function getChartOptions(label, color) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
            duration: 300,
        },
        interaction: {
            intersect: false,
            mode: 'index',
        },
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                backgroundColor: '#1e2030',
                titleColor: '#eaeaf0',
                bodyColor: '#a1a1b5',
                borderColor: '#252838',
                borderWidth: 1,
                padding: 10,
                displayColors: false,
                callbacks: {
                    title: function (context) {
                        const raw = context[0].raw;
                        if (raw && raw.x) {
                            return new Date(raw.x).toLocaleString('en', {
                                month: 'short',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                                hour12: false,
                            });
                        }
                        return context[0].label;
                    },
                    label: function (context) {
                        return `${label}: ${context.parsed.y.toFixed(1)}%`;
                    },
                },
            },
        },
        scales: {
            x: {
                type: 'category',
                grid: {
                    color: 'rgba(37, 40, 56, 0.5)',
                },
                ticks: {
                    color: '#5e5f73',
                    font: { size: 10 },
                    maxRotation: 0,
                    maxTicksLimit: 8,
                },
            },
            y: {
                min: 0,
                max: 100,
                grid: {
                    color: 'rgba(37, 40, 56, 0.5)',
                },
                ticks: {
                    color: '#5e5f73',
                    font: { size: 10 },
                    callback: function (value) {
                        return value + '%';
                    },
                    stepSize: 25,
                },
            },
        },
        elements: {
            line: {
                tension: 0.3,
                borderWidth: 2,
                borderColor: color,
                fill: true,
                backgroundColor: color.replace('1)', '0.1)'),
            },
            point: {
                radius: 2,
                hoverRadius: 5,
                backgroundColor: color,
                borderColor: color,
            },
        },
    };
}

/**
 * Render the CPU utilization line chart.
 */
function renderCpuChart(dataPoints) {
    const canvas = document.getElementById('metrics-cpu-canvas');
    if (!canvas) return;

    if (cpuChartInstance) {
        cpuChartInstance.destroy();
        cpuChartInstance = null;
    }

    const ctx = canvas.getContext('2d');
    const labels = dataPoints.map(d => formatTimestamp(d.timestamp));
    const values = dataPoints.map(d => d.value);
    const color = 'rgba(99, 102, 241, 1)';

    cpuChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                borderColor: color,
                backgroundColor: 'rgba(99, 102, 241, 0.1)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: color,
                pointBorderColor: color,
            }],
        },
        options: getChartOptions('CPU', color),
    });
}

/**
 * Render the Memory utilization line chart.
 */
function renderMemoryChart(dataPoints) {
    const canvas = document.getElementById('metrics-memory-canvas');
    if (!canvas) return;

    if (memoryChartInstance) {
        memoryChartInstance.destroy();
        memoryChartInstance = null;
    }

    const ctx = canvas.getContext('2d');
    const labels = dataPoints.map(d => formatTimestamp(d.timestamp));
    const values = dataPoints.map(d => d.value);
    const color = 'rgba(52, 211, 153, 1)';

    memoryChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                borderColor: color,
                backgroundColor: 'rgba(52, 211, 153, 0.1)',
                fill: true,
                tension: 0.3,
                borderWidth: 2,
                pointRadius: 2,
                pointHoverRadius: 5,
                pointBackgroundColor: color,
                pointBorderColor: color,
            }],
        },
        options: getChartOptions('Memory', color),
    });
}

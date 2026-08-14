/**
 * Cloud Control Panel - Uptime Chart module
 * Renders a horizontal timeline chart showing resource uptime/downtime over 7 or 30 days.
 * Uses Chart.js for rendering with 1-hour interval segments.
 */

import { state, api } from './utils.js';

// Color scheme for interval states
const STATE_COLORS = {
    running: '#28a745',
    stopped: '#dc3545',
    unknown: '#6c757d',
};

let uptimeChartInstance = null;
let currentRange = 7; // Default to 7-day range

/**
 * Initialize the uptime chart when a resource detail view is opened.
 * Sets up the range selector and loads data for the default range.
 */
export function initUptimeChart() {
    currentRange = 7;
    updateRangeButtons();
    loadUptimeData(currentRange);
}

/**
 * Destroy the chart instance when leaving the detail view.
 */
export function destroyUptimeChart() {
    if (uptimeChartInstance) {
        uptimeChartInstance.destroy();
        uptimeChartInstance = null;
    }
}

/**
 * Select a time range and reload the chart data.
 * @param {number} days - Number of days (7 or 30)
 */
export function selectUptimeRange(days) {
    if (days === currentRange) return;
    currentRange = days;
    updateRangeButtons();
    loadUptimeData(days);
}

/**
 * Update the active state of range selector buttons.
 */
function updateRangeButtons() {
    const btn7 = document.getElementById('uptime-range-7');
    const btn30 = document.getElementById('uptime-range-30');
    if (!btn7 || !btn30) return;

    btn7.classList.toggle('active', currentRange === 7);
    btn30.classList.toggle('active', currentRange === 30);
}

/**
 * Fetch uptime data from the API and render the chart.
 * @param {number} days - Range in days (7 or 30)
 */
async function loadUptimeData(days) {
    const container = document.getElementById('uptime-chart-container');
    const messageEl = document.getElementById('uptime-no-data-message');
    const canvasEl = document.getElementById('uptime-chart-canvas');

    if (!container || !messageEl || !canvasEl) return;

    // Show loading state
    messageEl.classList.add('hidden');
    canvasEl.classList.remove('hidden');

    if (!state.currentAccountId || !state.currentInstanceId) return;

    try {
        const data = await api(
            'GET',
            `/accounts/${state.currentAccountId}/resources/${state.currentInstanceId}/uptime?range=${days}`
        );

        const intervals = data.intervals || [];

        // Check if all intervals are unknown
        const allUnknown = intervals.length === 0 || intervals.every(i => i.state === 'unknown');

        if (allUnknown) {
            canvasEl.classList.add('hidden');
            messageEl.classList.remove('hidden');
            messageEl.textContent = 'No activity data available';
            destroyUptimeChart();
            return;
        }

        renderChart(intervals, days);
    } catch (e) {
        // On error, show message
        canvasEl.classList.add('hidden');
        messageEl.classList.remove('hidden');
        messageEl.textContent = 'No activity data available';
        destroyUptimeChart();
    }
}

/**
 * Render the uptime chart using Chart.js.
 * Creates a horizontal bar chart where each bar segment represents a 1-hour interval.
 * @param {Array} intervals - Array of {hour: ISO string, state: string}
 * @param {number} days - The range in days
 */
function renderChart(intervals, days) {
    const canvas = document.getElementById('uptime-chart-canvas');
    if (!canvas) return;

    destroyUptimeChart();

    const ctx = canvas.getContext('2d');

    // Group intervals into days for display
    const dayGroups = groupIntervalsByDay(intervals);
    const labels = dayGroups.map(g => g.label);

    // Set container height based on number of days
    const container = document.getElementById('uptime-chart-container');
    const rowHeight = 28;
    const minHeight = 120;
    container.style.height = Math.max(minHeight, dayGroups.length * rowHeight + 20) + 'px';

    // Build stacked dataset: each hour is a segment within a day
    // For a horizontal stacked bar, each "segment" is a dataset
    // We'll use a simpler approach: one dataset per hour-slot (0-23)
    const datasets = [];

    for (let hour = 0; hour < 24; hour++) {
        const data = dayGroups.map(group => {
            const interval = group.hours[hour];
            return interval ? 1 : 0;
        });

        const colors = dayGroups.map(group => {
            const interval = group.hours[hour];
            return interval ? STATE_COLORS[interval.state] || STATE_COLORS.unknown : STATE_COLORS.unknown;
        });

        datasets.push({
            label: `Hour ${hour}`,
            data: data,
            backgroundColor: colors,
            borderWidth: 0,
            barPercentage: 0.85,
            categoryPercentage: 0.9,
        });
    }

    uptimeChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: datasets,
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 300,
            },
            plugins: {
                legend: {
                    display: false,
                },
                tooltip: {
                    callbacks: {
                        title: function (context) {
                            return context[0].label;
                        },
                        label: function (context) {
                            const dayGroup = dayGroups[context.dataIndex];
                            const hour = context.datasetIndex;
                            const interval = dayGroup.hours[hour];
                            if (!interval) return '';
                            const time = new Date(interval.hour).toLocaleTimeString('en', {
                                hour: '2-digit',
                                minute: '2-digit',
                                hour12: false,
                            });
                            return `${time}: ${interval.state}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    stacked: true,
                    display: false,
                    max: 24,
                },
                y: {
                    stacked: true,
                    grid: {
                        display: false,
                    },
                    ticks: {
                        color: '#a1a1b5',
                        font: {
                            size: 11,
                        },
                    },
                },
            },
        },
    });
}

/**
 * Group intervals into day buckets for chart rendering.
 * @param {Array} intervals - Flat array of hourly intervals
 * @returns {Array} Array of {label, hours: {0..23: interval}}
 */
function groupIntervalsByDay(intervals) {
    const dayMap = new Map();

    for (const interval of intervals) {
        const date = new Date(interval.hour);
        const dayKey = date.toISOString().split('T')[0];

        if (!dayMap.has(dayKey)) {
            dayMap.set(dayKey, {
                label: date.toLocaleDateString('en', { month: 'short', day: 'numeric' }),
                hours: {},
            });
        }

        const hour = date.getUTCHours();
        dayMap.get(dayKey).hours[hour] = interval;
    }

    // Sort by date and return as array
    const sorted = [...dayMap.entries()].sort((a, b) => a[0].localeCompare(b[0]));
    return sorted.map(([, value]) => value);
}

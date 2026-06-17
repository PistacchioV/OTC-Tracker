/**
 * OTC Tracker — Dashboard
 * Fetches real deal data from /api/dashboard-stats and renders Charts.js charts.
 */

const bodyFont = getComputedStyle(document.body).fontFamily.trim();

// ─── status config ──────────────────────────────────────────────────────────

const STATUS_CONFIG = {
    Approved:  { cls: 'bg-success-subtle text-success' },
    Sent:      { cls: 'bg-primary-subtle text-primary'  },
    Pending:   { cls: 'bg-warning-subtle text-warning'  },
    New:       { cls: 'bg-info-subtle text-info'        },
    Error:     { cls: 'bg-danger-subtle text-danger'    },
};

function statusBadge(status, translatedStatus) {
    const cfg = STATUS_CONFIG[status] || { cls: 'bg-secondary-subtle text-secondary' };
    return `<span class="badge ${cfg.cls}">${translatedStatus || status || '—'}</span>`;
}

// ─── translation helper ─────────────────────────────────────────────────────
// Reads the translation key from a [data-lang] element that I18nManager already translated.

function getTranslatedText(key) {
    const el = document.querySelector(`[data-lang="${key}"]`);
    return el ? el.textContent.trim() : key;
}

// ─── chart instances ────────────────────────────────────────────────────────

let pieChart      = null;
let flowChart     = null;
let clientsChart  = null;
let productsChart = null;

function buildPieChart(ndf, opt) {
    const ctx = document.getElementById('multi-pie-chart');
    if (!ctx) return;
    if (pieChart) pieChart.destroy();

    pieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['NDF Commodities', 'Option Commodities'],
            datasets: [{
                data: [ndf, opt],
                backgroundColor: [ins('chart-primary'), ins('chart-secondary')],
                borderColor: 'transparent',
                borderWidth: 1,
                cutout: '65%',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        font: { family: bodyFont },
                        color: ins('secondary-color'),
                        usePointStyle: true,
                        pointStyle: 'circle',
                        boxWidth: 8,
                        padding: 15,
                    }
                },
                tooltip: {
                    callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` }
                }
            }
        }
    });
}

function buildFlowChart(monthlyNdf, monthlyOpt) {
    const ctx = document.getElementById('sales-analytics-chart');
    if (!ctx) return;
    if (flowChart) flowChart.destroy();

    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];

    flowChart = new Chart(ctx, {
        data: {
            labels: months,
            datasets: [
                {
                    type: 'bar',
                    label: 'NDF Commodities',
                    data: monthlyNdf,
                    backgroundColor: ins('chart-primary'),
                    borderColor: ins('chart-primary'),
                    stack: 'deals',
                    barThickness: 20,
                    borderRadius: 6,
                },
                {
                    type: 'bar',
                    label: 'Option Commodities',
                    data: monthlyOpt,
                    backgroundColor: ins('chart-secondary'),
                    borderColor: ins('chart-secondary'),
                    stack: 'deals',
                    barThickness: 20,
                    borderRadius: 6,
                },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: -10 } },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        font: { family: bodyFont },
                        color: ins('secondary-color'),
                        usePointStyle: true,
                        pointStyle: 'circle',
                        boxWidth: 8,
                        padding: 15,
                    }
                }
            },
            scales: {
                x: {
                    stacked: true,
                    ticks: { font: { family: bodyFont }, color: ins('secondary-color') },
                    grid: { display: false },
                    border: { display: false }
                },
                y: {
                    stacked: true,
                    ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 },
                    grid: { color: ins('chart-border-color'), lineWidth: 1 },
                    border: { display: false, dash: [5, 5] }
                }
            }
        }
    });
}

function buildClientsChart(top5) {
    const ctx = document.getElementById('top5-clients-chart');
    if (!ctx) return;
    if (clientsChart) clientsChart.destroy();

    if (!top5.length) {
        ctx.closest('.card-body').innerHTML = '<p class="text-muted text-center py-5 mb-0" data-lang="dash-no-deals">Nenhum deal encontrado para o período.</p>';
        return;
    }

    clientsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: top5.map(d => d.label),
            datasets: [{
                label: 'Deals',
                data: top5.map(d => d.count),
                backgroundColor: ins('chart-primary'),
                borderRadius: 6,
                barThickness: 22,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: { label: ctx => ` ${ctx.parsed.x} deal${ctx.parsed.x !== 1 ? 's' : ''}` }
                }
            },
            scales: {
                x: {
                    ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 },
                    grid: { color: ins('chart-border-color') },
                    border: { display: false }
                },
                y: {
                    ticks: {
                        font: { family: bodyFont, size: 11 },
                        color: ins('secondary-color'),
                        callback: function (val) {
                            const lbl = this.getLabelForValue(val);
                            return lbl.length > 22 ? lbl.slice(0, 21) + '…' : lbl;
                        }
                    },
                    grid: { display: false },
                    border: { display: false }
                }
            }
        }
    });
}

function buildProductsChart(top5) {
    const ctx = document.getElementById('top5-products-chart');
    if (!ctx) return;
    if (productsChart) productsChart.destroy();

    if (!top5.length) {
        ctx.closest('.card-body').innerHTML = '<p class="text-muted text-center py-5 mb-0" data-lang="dash-no-deals">Nenhum deal encontrado para o período.</p>';
        return;
    }

    const colors = [
        ins('chart-primary'),
        ins('chart-secondary'),
        ins('chart-dark'),
        ins('chart-gray'),
        ins('chart-primary-rgb', 0.5),
    ];

    productsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: top5.map(d => d.label),
            datasets: [{
                data: top5.map(d => d.count),
                backgroundColor: colors,
                borderColor: 'transparent',
                borderWidth: 2,
                cutout: '60%',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        font: { family: bodyFont, size: 11 },
                        color: ins('secondary-color'),
                        usePointStyle: true,
                        pointStyle: 'circle',
                        boxWidth: 8,
                        padding: 12,
                    }
                },
                tooltip: {
                    callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` }
                }
            }
        }
    });
}

// ─── recent deals table ─────────────────────────────────────────────────────

function renderRecentTable(recent) {
    const tbody = document.getElementById('dash-recent-tbody');
    if (!tbody) return;

    if (!recent || !recent.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">${getTranslatedText('dash-no-deals')}</td></tr>`;
        return;
    }

    tbody.innerHTML = recent.map(d => {
        const prod = d.type === 'OPT'
            ? `<span class="badge bg-info-subtle text-info">${getTranslatedText('dash-prod-opt')}</span>`
            : `<span class="badge bg-primary-subtle text-primary">${getTranslatedText('dash-prod-ndf')}</span>`;
        const statusTrans = getTranslatedText(`dash-status-${(d.status || '').toLowerCase()}`) || d.status || '—';
        return `<tr>
            <td><span class="fw-semibold text-primary">${d.deal || '—'}</span></td>
            <td>${prod}</td>
            <td>${d.client || '—'}</td>
            <td>${d.date || '—'}</td>
            <td>${statusBadge(d.status, statusTrans)}</td>
        </tr>`;
    }).join('');
}

// ─── period badge update ─────────────────────────────────────────────────────

function updatePeriodBadges(period) {
    const langKey = `dash-filter-${period}`;
    const label = getTranslatedText(langKey);

    ['dash-top5-clients-period', 'dash-top5-products-period'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.setAttribute('data-lang', langKey);
            el.textContent = label;
        }
    });
}

// ─── main load ──────────────────────────────────────────────────────────────

async function loadDashboard(period) {
    try {
        const res  = await fetch(`/api/dashboard-stats?period=${period}`);
        const data = await res.json();

        // Widgets
        document.getElementById('dash-ndf-count').textContent     = data.ndf_total;
        document.getElementById('dash-opt-count').textContent     = data.opt_total;
        document.getElementById('dash-pending-count').textContent = data.pending_total;
        document.getElementById('dash-total-count').textContent   = data.total_deals;

        updatePeriodBadges(period);

        buildPieChart(data.ndf_total, data.opt_total);
        buildFlowChart(data.monthly_ndf, data.monthly_opt);
        buildClientsChart(data.top5_clients);
        buildProductsChart(data.top5_products);
        renderRecentTable(data.recent_deals);

    } catch (err) {
        console.error('[Dashboard] Failed to load stats:', err);
        const tbody = document.getElementById('dash-recent-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Erro ao carregar dados.</td></tr>';
    }
}

// ─── init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Wait a tick so I18nManager has applied translations before we read them
    setTimeout(() => loadDashboard('month'), 300);

    document.querySelectorAll('#dash-period-filter [data-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#dash-period-filter [data-period]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadDashboard(btn.dataset.period);
        });
    });
});

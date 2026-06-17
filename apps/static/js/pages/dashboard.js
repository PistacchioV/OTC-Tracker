/**
 * OTC Tracker — Dashboard
 * Fetches real deal data from /api/dashboard-stats and renders Charts.js charts.
 */

const bodyFont = getComputedStyle(document.body).fontFamily.trim();

// ─── helpers ───────────────────────────────────────────────────────────────

const PERIOD_LABELS = { month: 'Mês Atual', year: 'Ano Atual', all: 'Todos' };

const STATUS_CONFIG = {
    Approved:  { cls: 'bg-success-subtle text-success',  label: 'Aprovado'  },
    Sent:      { cls: 'bg-primary-subtle text-primary',   label: 'Enviado'   },
    Pending:   { cls: 'bg-warning-subtle text-warning',   label: 'Pendente'  },
    New:       { cls: 'bg-info-subtle text-info',         label: 'Novo'      },
    Error:     { cls: 'bg-danger-subtle text-danger',     label: 'Erro'      },
};

function statusBadge(status) {
    const cfg = STATUS_CONFIG[status] || { cls: 'bg-secondary-subtle text-secondary', label: status || '—' };
    return `<span class="badge ${cfg.cls}">${cfg.label}</span>`;
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
            labels: ['NDF Commodities', 'OPT Commodities'],
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
                    callbacks: {
                        label: ctx => ` ${ctx.label}: ${ctx.parsed}`
                    }
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
                    label: 'OPT Commodities',
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

    const labels = top5.map(d => d.label);
    const data   = top5.map(d => d.count);

    clientsChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Deals',
                data,
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
                        callback: function(val) {
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

    const labels = top5.map(d => d.label);
    const data   = top5.map(d => d.count);

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
            labels,
            datasets: [{
                data,
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
                    callbacks: {
                        label: ctx => ` ${ctx.label}: ${ctx.parsed}`
                    }
                }
            }
        }
    });
}

// ─── recent deals table ─────────────────────────────────────────────────────

function renderRecentTable(allDeals) {
    const tbody = document.getElementById('dash-recent-tbody');
    if (!tbody) return;

    // Sort by file date desc, take last 10
    const sorted = [...allDeals].sort((a, b) => (b._fdate || '').localeCompare(a._fdate || '')).slice(0, 10);

    if (!sorted.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">Nenhum deal encontrado para o período.</td></tr>';
        return;
    }

    tbody.innerHTML = sorted.map(d => {
        const prod = d._type === 'OPT'
            ? '<span class="badge bg-info-subtle text-info">OPT Commodities</span>'
            : '<span class="badge bg-primary-subtle text-primary">NDF Commodities</span>';
        return `<tr>
            <td><span class="fw-semibold text-primary">${d.Deal || '—'}</span></td>
            <td>${prod}</td>
            <td>${d.Client || '—'}</td>
            <td>${d.TradeDate || d._fdate || '—'}</td>
            <td>${statusBadge(d.Status)}</td>
        </tr>`;
    }).join('');
}

// ─── main load ──────────────────────────────────────────────────────────────

let _rawDeals = [];

async function loadDashboard(period) {
    try {
        const res  = await fetch(`/api/dashboard-stats?period=${period}`);
        const data = await res.json();

        // Update widgets
        document.getElementById('dash-ndf-count').textContent     = data.ndf_total;
        document.getElementById('dash-opt-count').textContent     = data.opt_total;
        document.getElementById('dash-pending-count').textContent = data.pending_total;
        document.getElementById('dash-total-count').textContent   = data.total_deals;

        // Update period badges
        const periodLabel = PERIOD_LABELS[period] || 'Todos';
        const el1 = document.getElementById('dash-top5-clients-period');
        const el2 = document.getElementById('dash-top5-products-period');
        if (el1) el1.textContent = periodLabel;
        if (el2) el2.textContent = periodLabel;

        // Build / update charts
        buildPieChart(data.ndf_total, data.opt_total);
        buildFlowChart(data.monthly_ndf, data.monthly_opt);
        buildClientsChart(data.top5_clients);
        buildProductsChart(data.top5_products);

    } catch (err) {
        console.error('[Dashboard] Failed to load stats:', err);
    }
}

// ─── init ───────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Default period = month
    loadDashboard('month');

    document.querySelectorAll('#dash-period-filter [data-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#dash-period-filter [data-period]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadDashboard(btn.dataset.period);
        });
    });
});

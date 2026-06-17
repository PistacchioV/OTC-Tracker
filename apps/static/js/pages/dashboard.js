/**
 * OTC Tracker — Dashboard
 */

const bodyFont = getComputedStyle(document.body).fontFamily.trim();

// ─── translations ────────────────────────────────────────────────────────────

let _trans = {};

async function loadTranslations() {
    const lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en';
    try {
        const res = await fetch(`/static/data/translations/${lang}.json`);
        if (res.ok) _trans = await res.json();
    } catch { /* silent */ }
}

function t(key, fallback) {
    return _trans[key] || fallback || key;
}

// ─── status helpers ──────────────────────────────────────────────────────────

const STATUS_CLS = {
    Approved: 'bg-success-subtle text-success',
    Sent:     'bg-primary-subtle text-primary',
    Pending:  'bg-warning-subtle text-warning',
    New:      'bg-info-subtle text-info',
    Error:    'bg-danger-subtle text-danger',
};

function statusBadge(status) {
    const cls = STATUS_CLS[status] || 'bg-secondary-subtle text-secondary';
    const label = t(`dash-status-${(status || '').toLowerCase()}`, status || '—');
    return `<span class="badge ${cls}">${label}</span>`;
}

function productBadge(product, type) {
    if ((type || '').toUpperCase() === 'OPT' || (product || '').toLowerCase().startsWith('option')) {
        return `<span class="badge bg-info-subtle text-info">${product || t('dash-prod-opt', 'Option Commodities')}</span>`;
    }
    return `<span class="badge bg-primary-subtle text-primary">${product || t('dash-prod-ndf', 'NDF Commodities')}</span>`;
}

// ─── chart instances ─────────────────────────────────────────────────────────

let pieChart = null, flowChart = null, clientsChart = null, productsChart = null;

function buildPieChart(ndf, opt) {
    const ctx = document.getElementById('multi-pie-chart');
    if (!ctx) return;
    if (pieChart) pieChart.destroy();
    pieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['NDF Commodities', 'Option Commodities'],
            datasets: [{ data: [ndf, opt], backgroundColor: [ins('chart-primary'), ins('chart-secondary')], borderColor: 'transparent', borderWidth: 1, cutout: '65%' }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'bottom', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } }
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
                { type: 'bar', label: 'NDF Commodities', data: monthlyNdf, backgroundColor: ins('chart-primary'), borderColor: ins('chart-primary'), stack: 'deals', barThickness: 20, borderRadius: 6 },
                { type: 'bar', label: 'Option Commodities', data: monthlyOpt, backgroundColor: ins('chart-secondary'), borderColor: ins('chart-secondary'), stack: 'deals', barThickness: 20, borderRadius: 6 },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: -10 } },
            plugins: { legend: { display: true, position: 'top', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } } },
            scales: {
                x: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color') }, grid: { display: false }, border: { display: false } },
                y: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color'), lineWidth: 1 }, border: { display: false, dash: [5, 5] } }
            }
        }
    });
}

function buildClientsChart(top5) {
    const ctx = document.getElementById('top5-clients-chart');
    if (!ctx) return;
    if (clientsChart) clientsChart.destroy();
    if (!top5.length) {
        ctx.closest('.card-body').innerHTML = `<p class="text-muted text-center py-5 mb-0">${t('dash-no-deals')}</p>`;
        return;
    }
    clientsChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: top5.map(d => d.label), datasets: [{ label: 'Deals', data: top5.map(d => d.count), backgroundColor: ins('chart-primary'), borderRadius: 6, barThickness: 22 }] },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.x} deal${ctx.parsed.x !== 1 ? 's' : ''}` } } },
            scales: {
                x: { ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color') }, border: { display: false } },
                y: { ticks: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color'), callback(val) { const l = this.getLabelForValue(val); return l.length > 22 ? l.slice(0, 21) + '…' : l; } }, grid: { display: false }, border: { display: false } }
            }
        }
    });
}

function buildProductsChart(top5) {
    const ctx = document.getElementById('top5-products-chart');
    if (!ctx) return;
    if (productsChart) productsChart.destroy();
    if (!top5.length) {
        ctx.closest('.card-body').innerHTML = `<p class="text-muted text-center py-5 mb-0">${t('dash-no-deals')}</p>`;
        return;
    }
    const colors = [ins('chart-primary'), ins('chart-secondary'), ins('chart-dark'), ins('chart-gray'), ins('chart-primary-rgb', 0.5)];
    productsChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: top5.map(d => d.label), datasets: [{ data: top5.map(d => d.count), backgroundColor: colors, borderColor: 'transparent', borderWidth: 2, cutout: '60%' }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 12 } },
                tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } }
            }
        }
    });
}

// ─── recent deals ────────────────────────────────────────────────────────────

let _allRecentDeals = [];
let _activeProduct  = 'all';

function buildProductDropdown(deals) {
    const menu = document.getElementById('dash-product-filter-menu');
    if (!menu) return;

    // Collect unique product labels, sort alphabetically
    const products = [...new Set(deals.map(d => d.product).filter(Boolean))].sort();

    // Rebuild menu: "All" item + divider + product items
    menu.innerHTML = `
        <li><a class="dropdown-item ${_activeProduct === 'all' ? 'active' : ''}" href="#" data-product="all">${t('dash-filter-all', 'Todos')}</a></li>
        <li><hr class="dropdown-divider"></li>
        ${products.map(p => `<li><a class="dropdown-item ${_activeProduct === p ? 'active' : ''}" href="#" data-product="${p}">${p}</a></li>`).join('')}
    `;

    menu.querySelectorAll('[data-product]').forEach(item => {
        item.addEventListener('click', e => {
            e.preventDefault();
            _activeProduct = item.dataset.product;
            const label = document.getElementById('dash-product-filter-label');
            if (label) label.textContent = _activeProduct === 'all' ? t('dash-filter-all', 'Todos') : _activeProduct;
            menu.querySelectorAll('.dropdown-item').forEach(el => el.classList.remove('active'));
            item.classList.add('active');
            renderRecentTable(_allRecentDeals);
        });
    });
}

function renderRecentTable(deals) {
    const tbody = document.getElementById('dash-recent-tbody');
    if (!tbody) return;

    const filtered = _activeProduct === 'all'
        ? deals
        : deals.filter(d => d.product === _activeProduct);

    const visible = filtered.slice(0, 10);

    if (!visible.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted py-4">${t('dash-no-deals', 'Nenhum negócio encontrado para o período.')}</td></tr>`;
        return;
    }

    tbody.innerHTML = visible.map(d => `<tr>
        <td><span class="fw-semibold text-primary">${d.deal || '—'}</span></td>
        <td>${productBadge(d.product, d.type)}</td>
        <td>${d.client || '—'}</td>
        <td>${d.date || '—'}</td>
        <td>${statusBadge(d.status)}</td>
    </tr>`).join('');
}

// ─── period badge ────────────────────────────────────────────────────────────

function updatePeriodBadges(period) {
    const langKey = `dash-filter-${period}`;
    const label   = t(langKey);
    ['dash-top5-clients-period', 'dash-top5-products-period'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.setAttribute('data-lang', langKey); el.textContent = label; }
    });
}

// ─── main load ───────────────────────────────────────────────────────────────

async function loadDashboard(period) {
    try {
        const res  = await fetch(`/api/dashboard-stats?period=${period}`);
        const data = await res.json();

        document.getElementById('dash-ndf-count').textContent     = data.ndf_total;
        document.getElementById('dash-opt-count').textContent     = data.opt_total;
        document.getElementById('dash-pending-count').textContent = data.pending_total;
        document.getElementById('dash-total-count').textContent   = data.total_deals;

        updatePeriodBadges(period);
        buildPieChart(data.ndf_total, data.opt_total);
        buildFlowChart(data.monthly_ndf, data.monthly_opt);
        buildClientsChart(data.top5_clients);
        buildProductsChart(data.top5_products);

        _allRecentDeals = data.recent_deals || [];
        _activeProduct  = 'all';
        buildProductDropdown(_allRecentDeals);
        renderRecentTable(_allRecentDeals);

        // Sync filter label with current translation
        const label = document.getElementById('dash-product-filter-label');
        if (label) label.textContent = t('dash-filter-all', 'Todos');

    } catch (err) {
        console.error('[Dashboard] Failed to load stats:', err);
        const tbody = document.getElementById('dash-recent-tbody');
        if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Erro ao carregar dados.</td></tr>';
    }
}

// ─── init ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    loadDashboard('month');

    document.querySelectorAll('#dash-period-filter [data-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#dash-period-filter [data-period]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadDashboard(btn.dataset.period);
        });
    });
});

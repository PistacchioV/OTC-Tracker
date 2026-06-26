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

// ─── chart theme helpers ─────────────────────────────────────────────────────

function isDark() {
    return document.documentElement.getAttribute('data-bs-theme') === 'dark';
}

/** Premium theme-aware tooltip config (shared by all charts). */
function premiumTooltip(extra) {
    const dark = isDark();
    return Object.assign({
        backgroundColor: dark ? 'rgba(30, 41, 59, 0.95)' : 'rgba(255, 255, 255, 0.97)',
        titleColor:      dark ? '#f1f5f9' : '#1e293b',
        bodyColor:       dark ? '#cbd5e1' : '#475569',
        borderColor:     dark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.08)',
        borderWidth: 1,
        padding: 12,
        cornerRadius: 10,
        titleFont: { family: bodyFont, weight: '600', size: 13 },
        bodyFont:  { family: bodyFont, size: 12 },
        usePointStyle: true,
        boxPadding: 6,
        displayColors: true,
    }, extra || {});
}

/** Vertical gradient (bottom → top) for area/bar fills. */
function vGradient(hex, topAlpha, bottomAlpha) {
    return (context) => {
        const { ctx, chartArea } = context.chart;
        if (!chartArea) return hexToRgba(hex, topAlpha);
        const g = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
        g.addColorStop(0, hexToRgba(hex, bottomAlpha));
        g.addColorStop(1, hexToRgba(hex, topAlpha));
        return g;
    };
}

/** Horizontal gradient (left → right) for horizontal-bar fills. */
function hGradient(hex, leftAlpha, rightAlpha) {
    return (context) => {
        const { ctx, chartArea } = context.chart;
        if (!chartArea) return hexToRgba(hex, rightAlpha);
        const g = ctx.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
        g.addColorStop(0, hexToRgba(hex, leftAlpha));
        g.addColorStop(1, hexToRgba(hex, rightAlpha));
        return g;
    };
}

/**
 * Per-segment vertical gradient for doughnut/pie charts. Returns a SINGLE
 * scriptable function (Chart.js does not resolve an array of functions as
 * scriptable — it would render them as invalid → black), picking the segment
 * color by context.dataIndex.
 */
function doughnutGradient(hexColors, topAlpha, bottomAlpha) {
    return (context) => {
        const hex = hexColors[context.dataIndex] || hexColors[0];
        const { ctx, chartArea } = context.chart;
        if (!chartArea) return hexToRgba(hex, topAlpha);
        const g = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
        g.addColorStop(0, hexToRgba(hex, bottomAlpha));
        g.addColorStop(1, hexToRgba(hex, topAlpha));
        return g;
    };
}

function hexToRgba(hex, a) {
    hex = (hex || '').trim();
    if (hex.startsWith('rgb')) return hex;
    const h = hex.replace('#', '');
    const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
    const n = parseInt(full, 16);
    if (isNaN(n)) return `rgba(106, 17, 203, ${a})`;
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

// ─── chart instances ─────────────────────────────────────────────────────────

let pieChart = null, flowChart = null, clientsChart = null, productsChart = null, commoditiesChart = null;

function buildPieChart(ndf, opt, fxo) {
    const ctx = document.getElementById('multi-pie-chart');
    if (!ctx) return;
    if (pieChart) pieChart.destroy();
    pieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['NDF Commodities', 'Option Commodities', 'Option FXO'],
            datasets: [{
                data: [ndf, opt, fxo || 0],
                backgroundColor: doughnutGradient([ins('chart-primary'), ins('chart-secondary'), '#10b981'], 1, 0.55),
                borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff',
                borderWidth: 2,
                hoverOffset: 8,
                cutout: '65%'
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { animateRotate: true, animateScale: true, duration: 700 },
            plugins: {
                legend: { position: 'bottom', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } })
            }
        }
    });
}

function buildFlowChart(monthlyNdf, monthlyOpt, monthlyFxo) {
    const ctx = document.getElementById('sales-analytics-chart');
    if (!ctx) return;
    if (flowChart) flowChart.destroy();
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    flowChart = new Chart(ctx, {
        data: {
            labels: months,
            datasets: [
                { type: 'bar', label: 'NDF Commodities', data: monthlyNdf, backgroundColor: vGradient(ins('chart-primary'), 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: 6 },
                { type: 'bar', label: 'Option Commodities', data: monthlyOpt, backgroundColor: vGradient(ins('chart-secondary'), 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: 6 },
                { type: 'bar', label: 'Option FXO', data: monthlyFxo || [], backgroundColor: vGradient('#10b981', 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: 6 },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: -10 } },
            animation: { duration: 700, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: true, position: 'top', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: premiumTooltip({ mode: 'index', intersect: false })
            },
            scales: {
                x: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color') }, grid: { display: false }, border: { display: false } },
                y: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color'), lineWidth: 1 }, border: { display: false, dash: [5, 5] } }
            }
        }
    });
}

// ─── Settlement Forecast (by product) — next 14 business days ─────────────────
let forecastChart = null;
let _forecastData = null;

const FC_PRODUCT_COLORS = {
    'NDF Moeda':       () => ins('chart-primary'),
    'NDF Commodities': () => ins('chart-secondary'),
    'Opt FXO':         () => '#10b981',
    'OPT Comm':        () => '#0ea5e9',
    'OPT EDG':         () => '#a855f7',
    'SWAP CEM':        () => '#f59e0b',
    'SWAP EDG':        () => '#f43f5e',
    'SWAP CEMHYB':     () => '#94a3b8',
};
const FC_FALLBACK = ['#4f46e5', '#0ea5e9', '#10b981', '#a855f7', '#f59e0b', '#f43f5e', '#14b8a6', '#94a3b8'];

async function loadForecastChart() {
    const ctx = document.getElementById('forecast-product-chart');
    if (!ctx) return;
    try {
        const res = await fetch('/api/control-panel/settlement-forecast/data', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}'
        });
        const data = await res.json();
        if (!data || data.success === false || !(data.products || []).length) {
            const body = ctx.closest('.card-body');
            if (body) body.innerHTML = `<p class="text-muted text-center py-5 mb-0">${t('dash-no-deals', 'Sem dados')}</p>`;
            return;
        }
        _forecastData = data;
        buildForecastProductChart(data);
    } catch (err) {
        console.error('[Dashboard] forecast load failed:', err);
    }
}

function buildForecastProductChart(data) {
    const ctx = document.getElementById('forecast-product-chart');
    if (!ctx) return;
    if (forecastChart) forecastChart.destroy();
    let fb = 0;
    const datasets = (data.products || []).map(p => {
        const c = FC_PRODUCT_COLORS[p.label] ? FC_PRODUCT_COLORS[p.label]() : FC_FALLBACK[fb++ % FC_FALLBACK.length];
        return {
            type: 'bar', label: p.label, data: p.values,
            backgroundColor: vGradient(c, 1, 0.45), borderColor: 'transparent',
            stack: 'fc', maxBarThickness: 24, borderRadius: 6
        };
    });
    forecastChart = new Chart(ctx, {
        data: { labels: data.date_labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: -10 } },
            animation: { duration: 700, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: true, position: 'top', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: premiumTooltip({ mode: 'index', intersect: false })
            },
            scales: {
                x: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color') }, grid: { display: false }, border: { display: false } },
                y: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color'), lineWidth: 1 }, border: { display: false, dash: [5, 5] } }
            }
        }
    });
}

// Per-product colors — aligned with the Deal Distribution / Flow charts
function _productColor(p) {
    switch (p) {
        case 'NDF Commodities':     return ins('chart-primary');
        case 'Option Commodities':  return ins('chart-secondary');
        case 'Option FXO':          return '#10b981';
        case 'NDF FWD Start':       return ins('chart-dark');
        case 'NDF Other Publisher': return ins('chart-gray');
        default:                    return null;   // pulled from fallback palette
    }
}
const PRODUCT_FALLBACK = ['#0ea5e9', '#14b8a6', '#f59e0b', '#f43f5e', '#a855f7'];

function buildClientsChart(top5) {
    const ctx = document.getElementById('top5-clients-chart');
    if (!ctx) return;
    if (clientsChart) clientsChart.destroy();
    if (!top5.length) {
        ctx.closest('.card-body').innerHTML = `<p class="text-muted text-center py-5 mb-0">${t('dash-no-deals')}</p>`;
        return;
    }
    // Distinct products across the top-5 clients → one stacked dataset each
    const products = [];
    top5.forEach(c => Object.keys(c.by_product || {}).forEach(p => { if (products.indexOf(p) === -1) products.push(p); }));
    const stacked = products.length > 0;
    let fb = 0;
    const datasets = stacked
        ? products.map(p => {
            const base = _productColor(p) || PRODUCT_FALLBACK[fb++ % PRODUCT_FALLBACK.length];
            return { label: p, data: top5.map(c => (c.by_product && c.by_product[p]) || 0),
                     backgroundColor: hGradient(base, 0.55, 1), borderRadius: 4, barThickness: 22, stack: 'clients' };
        })
        : [{ label: 'Deals', data: top5.map(c => c.count), backgroundColor: hGradient(ins('chart-primary'), 0.55, 1), borderRadius: 6, barThickness: 22 }];

    clientsChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: top5.map(d => d.label), datasets: datasets },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            animation: { duration: 700, easing: 'easeOutQuart' },
            plugins: {
                legend: stacked
                    ? { position: 'bottom', labels: { font: { family: bodyFont, size: 10 }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 10 } }
                    : { display: false },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.x} deal${ctx.parsed.x !== 1 ? 's' : ''}` } })
            },
            scales: {
                x: { stacked: stacked, ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color') }, border: { display: false } },
                y: { stacked: stacked, ticks: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color'), callback(val) { const l = this.getLabelForValue(val); return l.length > 22 ? l.slice(0, 21) + '…' : l; } }, grid: { display: false }, border: { display: false } }
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
    const baseColors = [ins('chart-primary'), ins('chart-secondary'), ins('chart-dark'), ins('chart-gray'), ins('chart-primary')];
    productsChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: top5.map(d => d.label), datasets: [{ data: top5.map(d => d.count), backgroundColor: doughnutGradient(baseColors, 1, 0.6), borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff', borderWidth: 2, hoverOffset: 8, cutout: '60%' }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { animateRotate: true, animateScale: true, duration: 700 },
            plugins: {
                legend: { position: 'right', labels: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 12 } },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } })
            }
        }
    });
}

// Distinct, light multi-hue palette for commodities — harmonious with the
// theme but visually separate from the products chart (purple/blue tokens).
const COMMODITY_COLORS = ['#0ea5e9', '#14b8a6', '#f59e0b', '#f43f5e', '#a855f7'];

function buildCommoditiesChart(top5) {
    const ctx = document.getElementById('top5-commodities-chart');
    if (!ctx) return;
    if (commoditiesChart) commoditiesChart.destroy();
    if (!top5 || !top5.length) {
        ctx.closest('.card-body').innerHTML = `<p class="text-muted text-center py-5 mb-0">${t('dash-no-deals')}</p>`;
        return;
    }
    commoditiesChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: top5.map(d => d.label), datasets: [{ data: top5.map(d => d.count), backgroundColor: doughnutGradient(COMMODITY_COLORS, 1, 0.6), borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff', borderWidth: 2, hoverOffset: 8, cutout: '60%' }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: { animateRotate: true, animateScale: true, duration: 700 },
            plugins: {
                legend: { position: 'right', labels: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 12 } },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } })
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
    ['dash-top5-clients-period', 'dash-top5-products-period', 'dash-top5-commodities-period'].forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.setAttribute('data-lang', langKey); el.textContent = label; }
    });
}

// ─── main load ───────────────────────────────────────────────────────────────

let _lastData = null;

async function loadDashboard(period) {
    try {
        const res  = await fetch(`/api/dashboard-stats?period=${period}`);
        const data = await res.json();
        _lastData = data;

        // Null-safe: a missing/renamed count element must never halt chart rendering
        const setText = (id, val) => {
            const el = document.getElementById(id);
            if (el) el.textContent = val;
        };
        setText('dash-ndf-count', data.ndf_total);
        setText('dash-opt-count', data.opt_total);
        setText('dash-swap-count', data.swap_total ?? 0);
        setText('dash-total-count', data.total_deals);

        updatePeriodBadges(period);
        buildPieChart(data.dist_ndf, data.dist_opt, data.dist_fxo);
        buildFlowChart(data.monthly_ndf, data.monthly_opt, data.monthly_fxo);
        buildClientsChart(data.top5_clients);
        buildProductsChart(data.top5_products);
        buildCommoditiesChart(data.top5_underlying);

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

// ─── theme-aware re-render ───────────────────────────────────────────────────

/** Rebuild every chart from the cached data using the current theme's tokens. */
function rerenderCharts() {
    if (!_lastData) return;
    buildPieChart(_lastData.dist_ndf, _lastData.dist_opt, _lastData.dist_fxo);
    buildFlowChart(_lastData.monthly_ndf, _lastData.monthly_opt, _lastData.monthly_fxo);
    buildClientsChart(_lastData.top5_clients);
    buildProductsChart(_lastData.top5_products);
    buildCommoditiesChart(_lastData.top5_underlying);
    if (_forecastData) buildForecastProductChart(_forecastData);
}

// ─── init ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    loadDashboard('month');
    loadForecastChart();   // independent of the period filter

    document.querySelectorAll('#dash-period-filter [data-period]').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            document.querySelectorAll('#dash-period-filter [data-period]').forEach(b => b.classList.remove('active'));
            item.classList.add('active');
            const label = document.getElementById('dash-period-label');
            if (label) {
                label.setAttribute('data-lang', 'dash-filter-' + item.dataset.period);
                label.textContent = item.textContent;
            }
            loadDashboard(item.dataset.period);
        });
    });

    // Re-render charts when the theme (light/dark) or skin changes so colors,
    // gradients and tooltips follow the active palette. Debounced to coalesce
    // the rapid attribute flips the theme switcher can emit.
    const _rerender = debounce(rerenderCharts, 120);
    new MutationObserver(_rerender).observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-bs-theme', 'data-skin']
    });
});

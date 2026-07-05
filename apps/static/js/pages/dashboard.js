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
        footerColor:     dark ? '#f1f5f9' : '#1e293b',
        titleFont: { family: bodyFont, weight: '600', size: 13 },
        bodyFont:  { family: bodyFont, size: 12 },
        footerFont:{ family: bodyFont, weight: '600', size: 12 },
        footerMarginTop: 8,
        usePointStyle: true,
        boxPadding: 6,
        displayColors: true,
    }, extra || {});
}

/** Tooltip footer callback: appends a "Total" line summing the visible values. */
function totalFooter(items) {
    if (!items || !items.length) return '';
    const sum = items.reduce((acc, it) => acc + (Number(it.parsed.y) || 0), 0);
    const pretty = Number.isInteger(sum) ? sum.toLocaleString() : sum.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return `${t('dash-tooltip-total', 'Total')}: ${pretty}`;
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

// ─── shared "grow" animation ─────────────────────────────────────────────────
// Every card animates the SAME way the Settlement Forecast does: bars rise from
// the baseline, doughnuts scale/rotate in. Because every chart is destroyed and
// re-created on data change, this fires on first paint AND on every range/date/
// filter change — no extra wiring needed.
const GROW_ANIM     = { duration: 850, easing: 'easeOutQuart' };
const GROW_ANIM_PIE = { animateRotate: true, animateScale: true, duration: 850, easing: 'easeOutQuart' };

// Live Position display labels: SWAP → Swap, CEMHYB → HYB (house convention).
function liveDisplayLabel(label) {
    return String(label == null ? '' : label).replace(/^SWAP /, 'Swap ').replace(/CEMHYB/, 'HYB');
}
// Live Position bar color per product — aligned with the Settlement Forecast palette.
function liveProductColor(label, idx) {
    const fn = FC_PRODUCT_COLORS[label];
    return fn ? fn() : LIVE_COLORS[idx % LIVE_COLORS.length];
}

// ─── chart instances ─────────────────────────────────────────────────────────

let pieChart = null, flowChart = null, clientsChart = null, productsChart = null, commoditiesChart = null;

function buildPieChart(ndf, opt, fxo, swap) {
    const ctx = document.getElementById('multi-pie-chart');
    if (!ctx) return;
    if (pieChart) pieChart.destroy();
    pieChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['NDF Commodities', 'Option Commodities', 'Option FXO', 'Swap'],
            datasets: [{
                data: [ndf, opt, fxo || 0, swap || 0],
                backgroundColor: doughnutGradient([ins('chart-primary'), ins('chart-secondary'), '#10b981', '#f59e0b'], 1, 0.55),
                borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff',
                borderWidth: 2,
                hoverOffset: 8,
                cutout: '65%'
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: GROW_ANIM_PIE,
            plugins: {
                legend: { position: 'bottom', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } })
            }
        }
    });
}

function buildFlowChart(monthlyNdf, monthlyOpt, monthlyFxo, monthlySwap) {
    const ctx = document.getElementById('sales-analytics-chart');
    if (!ctx) return;
    if (flowChart) flowChart.destroy();
    const months = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez'];
    flowChart = new Chart(ctx, {
        data: {
            labels: months,
            datasets: [
                { type: 'bar', label: 'NDF Commodities', data: monthlyNdf, backgroundColor: vGradient(ins('chart-primary'), 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: stackEndRadius(6, 'bottom'), borderSkipped: false },
                { type: 'bar', label: 'Option Commodities', data: monthlyOpt, backgroundColor: vGradient(ins('chart-secondary'), 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: stackEndRadius(6, 'bottom'), borderSkipped: false },
                { type: 'bar', label: 'Option FXO', data: monthlyFxo || [], backgroundColor: vGradient('#10b981', 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: stackEndRadius(6, 'bottom'), borderSkipped: false },
                { type: 'bar', label: 'Swap', data: monthlySwap || [], backgroundColor: vGradient('#f59e0b', 1, 0.45), borderColor: 'transparent', stack: 'deals', barThickness: 20, borderRadius: stackEndRadius(6, 'bottom'), borderSkipped: false },
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            layout: { padding: { top: -10 } },
            animation: GROW_ANIM,
            plugins: {
                legend: { display: true, position: 'top', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
                tooltip: premiumTooltip({ mode: 'index', intersect: false, callbacks: { footer: totalFooter } })
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
let _forecastProductFilter = '__all__';   // '__all__' or a product label
let _forecastDays = 15;                    // look-ahead window (15 | 20 | 30 business days)
let _subTemplate = null;                   // cached "…{n}…" subtitle template (current language)

const FC_PRODUCT_COLORS = {
    'NDF Moeda':       () => ins('chart-primary'),
    'NDF Commodities': () => ins('chart-secondary'),
    'Option FXO':      () => '#10b981',
    'Option Commodities': () => '#0ea5e9',
    'Option EDG':      () => '#a855f7',
    'SWAP CEM':        () => '#f59e0b',
    'SWAP EDG':        () => '#f43f5e',
    'SWAP CEMHYB':     () => '#94a3b8',
};
const FC_FALLBACK = ['#4f46e5', '#0ea5e9', '#10b981', '#a855f7', '#f59e0b', '#f43f5e', '#14b8a6', '#94a3b8'];
// Per-entity colors — aligned with the e-mail's "Settlements by Entity" chart
// (settlement-forecast.js entityColors). Unknown entities fall back to the palette.
const FC_ENTITY_COLORS = {
    'LAWTON':  () => ins('chart-primary'),
    'MGT':     () => '#10b981',
    'ATACAMA': () => '#f59e0b',
};
let forecastEntityChart = null;

// Non-destructive empty state: toggle the charts wrapper vs a message WITHOUT
// wiping the card body (which would delete the canvases and stop later reloads).
function _setForecastEmpty(ctx, isEmpty) {
    const body  = ctx.closest('.card-body');
    const inner = ctx.closest('[dir="ltr"]');   // wraps both product + entity charts
    if (!body) return;
    let msg = body.querySelector('.fc-empty-msg');
    if (isEmpty) {
        if (!msg) {
            msg = document.createElement('p');
            msg.className = 'fc-empty-msg text-muted text-center py-5 mb-0';
            body.appendChild(msg);
        }
        msg.textContent = t('dash-no-deals', 'No deals found for the period.');
        msg.style.display = '';
        if (inner) inner.style.display = 'none';
    } else {
        if (msg) msg.style.display = 'none';
        if (inner) inner.style.display = '';
    }
}

async function loadForecastChart() {
    const ctx = document.getElementById('forecast-product-chart');
    if (!ctx) return;
    try {
        // Dashboard shows the latest available data: D-1, else D-2, … (mode:'latest').
        const res = await fetch('/api/control-panel/settlement-forecast/data', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'latest', days: _forecastDays })
        });
        const data = await res.json();
        if (!data || data.success === false || !(data.products || []).length) {
            _setForecastEmpty(ctx, true);
            return;
        }
        _setForecastEmpty(ctx, false);
        _forecastData = data;
        if (data.days) _forecastDays = data.days;   // backend is the source of truth (clamps to allowed set)
        renderForecastSub();
        // Show which position date the chart is based on.
        const asOf = document.getElementById('forecast-asof');
        if (asOf && data.ref_date_fmt) {
            asOf.textContent = `${t('dash-forecast-asof', 'as of')} ${data.ref_date_fmt}`;
        }
        populateForecastFilter(data);
        buildForecastProductChart(data);
        buildForecastEntityChart(data);
    } catch (err) {
        console.error('[Dashboard] forecast load failed:', err);
    }
}

// Build the product dropdown from the data and wire selection → re-render
function populateForecastFilter(data) {
    const menu = document.getElementById('fc-product-menu');
    if (!menu) return;
    const products = (data.products || []).map(p => p.label);
    // Keep "All" (first item), drop any previously-appended product items
    menu.querySelectorAll('[data-product]:not([data-product="__all__"])').forEach(el => el.closest('li').remove());
    products.forEach(label => {
        const li = document.createElement('li');
        li.innerHTML = `<a class="dropdown-item" href="#" data-product="${label}">${label}</a>`;
        menu.appendChild(li);
    });
    // If the current filter no longer exists in this dataset, reset to All
    if (_forecastProductFilter !== '__all__' && products.indexOf(_forecastProductFilter) === -1) {
        _forecastProductFilter = '__all__';
    }
    syncForecastFilterUI();

    if (!menu.dataset.bound) {
        menu.addEventListener('click', (e) => {
            const a = e.target.closest('[data-product]');
            if (!a) return;
            e.preventDefault();
            _forecastProductFilter = a.getAttribute('data-product');
            syncForecastFilterUI();
            if (_forecastData) buildForecastProductChart(_forecastData);
        });
        menu.dataset.bound = '1';
    }
}

function syncForecastFilterUI() {
    const menu = document.getElementById('fc-product-menu');
    const label = document.getElementById('fc-product-label');
    if (!menu) return;
    menu.querySelectorAll('[data-product]').forEach(a => {
        a.classList.toggle('active', a.getAttribute('data-product') === _forecastProductFilter);
    });
    if (label) {
        if (_forecastProductFilter === '__all__') {
            label.textContent = t('dash-fc-filter-all', 'All');
            label.setAttribute('data-lang', 'dash-fc-filter-all');
        } else {
            label.textContent = _forecastProductFilter;
            label.removeAttribute('data-lang');
        }
    }
}

// Subtitle "Next {n} business days, by product" — {n} tracks the selected range.
// The template comes from the translation file; we substitute {n} at render time.
function renderForecastSub() {
    const el = document.getElementById('forecast-sub');
    if (!el) return;
    if (!_subTemplate) _subTemplate = t('dash-forecast-sub', 'Próximos {n} dias úteis, por produto');
    el.textContent = _subTemplate.replace('{n}', _forecastDays);
}

// Range dropdown (15 | 20 | 30 business days) → reload the forecast on selection.
function wireForecastRange() {
    const menu = document.getElementById('fc-range-menu');
    const btn  = document.getElementById('fc-range-label');
    if (!menu) return;
    menu.addEventListener('click', (e) => {
        const a = e.target.closest('[data-days]');
        if (!a) return;
        e.preventDefault();
        const days = parseInt(a.getAttribute('data-days'), 10);
        if (!days || days === _forecastDays) return;
        _forecastDays = days;
        menu.querySelectorAll('[data-days]').forEach(x => x.classList.toggle('active', x === a));
        if (btn) btn.innerHTML = a.innerHTML;
        renderForecastSub();
        loadForecastChart();
    });

    // app.js re-applies data-lang on load/language-switch, restoring the raw
    // "{n}" template — capture the fresh (correct-language) template and re-fill.
    const sub = document.getElementById('forecast-sub');
    if (sub) {
        if (sub.textContent.indexOf('{n}') !== -1) _subTemplate = sub.textContent;
        new MutationObserver(() => {
            if (sub.textContent.indexOf('{n}') !== -1) {
                _subTemplate = sub.textContent;
                renderForecastSub();
            }
        }).observe(sub, { childList: true, characterData: true, subtree: true });
        renderForecastSub();
    }
}

// Index of the top-most visible dataset that has a value > 0 at bar `i`.
function _lastVisibleDatasetAt(chart, i) {
    const ds = chart.data.datasets;
    let last = -1;
    for (let d = 0; d < ds.length; d++) {
        if (!chart.isDatasetVisible(d)) continue;
        const v = ds[d].data[i];
        if (v != null && +v > 0) last = d;
    }
    return last;
}

// Scriptable borderRadius for stacked bars: round ONLY the two corners at the
// OUTER end of the top-most visible segment (flat everywhere else) so the whole
// stack reads as a single bar with one rounded tip, regardless of which product
// is last. Returns a per-corner OBJECT and must be paired with
// `borderSkipped: false` — that combo is the one Chart.js v4 honours reliably in
// stacked charts (a plain number + `borderSkipped: 'bottom'` gets dropped on the
// top segment). `edge` is the growth direction: 'bottom' → vertical bars grow up
// (round top corners); 'left' → horizontal bars grow right (round right corners).
function stackEndRadius(R, edge) {
    var end = (edge === 'left')
        ? { topLeft: 0, bottomLeft: 0, topRight: R, bottomRight: R }   // horizontal → grows right
        : { bottomLeft: 0, bottomRight: 0, topLeft: R, topRight: R };  // vertical   → grows up
    var flat = { topLeft: 0, topRight: 0, bottomLeft: 0, bottomRight: 0 };
    return function (c) {
        if (!c || c.type !== 'data') return flat;
        return c.datasetIndex === _lastVisibleDatasetAt(c.chart, c.dataIndex) ? end : flat;
    };
}

// Plugin: round the top of the WHOLE stacked column (not the last segment).
// The per-segment scriptable radius (stackEndRadius) only rounds the top-most
// segment — which in the forecast is often a 1–3px sliver (a small SWAP/Option
// product), so Chart.js clamps the radius to that sliver's height and the tip
// reads as flat. Clipping every column to a rounded-top rectangle before the
// bars draw guarantees a visible rounded tip regardless of how thin the top
// product is, while leaving each segment's gradient untouched.
const roundedStackTopClip = {
    id: 'roundedStackTopClip',
    beforeDatasetsDraw(chart, _args, opts) {
        const R = (opts && opts.radius) || 6;
        const ctx = chart.ctx;
        const n = (chart.data.labels || []).length;
        const path = new Path2D();
        let drew = false;
        for (let i = 0; i < n; i++) {
            let topY = Infinity, botY = -Infinity, cx = null, w = null;
            chart.data.datasets.forEach((ds, di) => {
                if (!chart.isDatasetVisible(di)) return;
                const el = chart.getDatasetMeta(di).data[i];
                const v = ds.data[i];
                if (!el || v == null || +v <= 0) return;
                topY = Math.min(topY, el.y);
                botY = Math.max(botY, el.base);
                cx = el.x; w = el.width;
            });
            if (cx == null) continue;
            const left = cx - w / 2, right = cx + w / 2;
            const r = Math.min(R, w / 2, Math.max(0, (botY - topY) / 2));
            path.moveTo(left, botY);
            path.lineTo(left, topY + r);
            path.arcTo(left, topY, left + r, topY, r);
            path.lineTo(right - r, topY);
            path.arcTo(right, topY, right, topY + r, r);
            path.lineTo(right, botY);
            path.closePath();
            drew = true;
        }
        ctx.save();
        if (drew) ctx.clip(path);
    },
    afterDatasetsDraw(chart) {
        chart.ctx.restore();
    }
};

// Shared options for both forecast stacked charts (by product / by entity).
function _forecastStackOptions() {
    return {
        responsive: true, maintainAspectRatio: false,
        layout: { padding: { top: -10 } },
        animation: GROW_ANIM,
        plugins: {
            legend: { display: true, position: 'top', labels: { font: { family: bodyFont }, color: ins('secondary-color'), usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 15 } },
            tooltip: premiumTooltip({ mode: 'index', intersect: false, callbacks: { footer: totalFooter } })
        },
        scales: {
            x: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color') }, grid: { display: false }, border: { display: false } },
            y: { stacked: true, ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color'), lineWidth: 1 }, border: { display: false, dash: [5, 5] } }
        }
    };
}

function buildForecastProductChart(data) {
    const ctx = document.getElementById('forecast-product-chart');
    if (!ctx) return;
    if (forecastChart) forecastChart.destroy();
    let fb = 0;
    let products = data.products || [];
    if (_forecastProductFilter !== '__all__') {
        products = products.filter(p => p.label === _forecastProductFilter);
    }
    const datasets = products.map(p => {
        const c = FC_PRODUCT_COLORS[p.label] ? FC_PRODUCT_COLORS[p.label]() : FC_FALLBACK[fb++ % FC_FALLBACK.length];
        return {
            type: 'bar', label: p.label, data: p.values,
            backgroundColor: vGradient(c, 1, 0.45), borderColor: 'transparent',
            stack: 'fc', maxBarThickness: 24, borderRadius: 0, borderSkipped: false
        };
    });
    forecastChart = new Chart(ctx, {
        plugins: [roundedStackTopClip],
        data: { labels: data.date_labels, datasets },
        options: _forecastStackOptions()
    });
}

// "Settlements by Entity" — same stacked model as the product chart, LOB colors
// aligned with the e-mail. Hidden when the dataset has no entity rows.
function buildForecastEntityChart(data) {
    const ctx = document.getElementById('forecast-entity-chart');
    if (!ctx) return;
    const section  = document.getElementById('forecast-entity-section');
    const entities = data.entities || [];
    if (!entities.length) { if (section) section.style.display = 'none'; return; }
    if (section) section.style.display = '';
    if (forecastEntityChart) forecastEntityChart.destroy();
    let fb = 0;
    const datasets = entities.map(en => {
        const c = FC_ENTITY_COLORS[en.label] ? FC_ENTITY_COLORS[en.label]() : FC_FALLBACK[fb++ % FC_FALLBACK.length];
        return {
            type: 'bar', label: en.label, data: en.values,
            backgroundColor: vGradient(c, 1, 0.45), borderColor: 'transparent',
            stack: 'fc', maxBarThickness: 24, borderRadius: 0, borderSkipped: false
        };
    });
    forecastEntityChart = new Chart(ctx, {
        plugins: [roundedStackTopClip],
        data: { labels: data.date_labels, datasets },
        options: _forecastStackOptions()
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

// Toggle a card's canvas ↔ empty-state message WITHOUT removing the canvas from
// the DOM. Replacing card-body.innerHTML (the old approach) deleted the <canvas>,
// so once a period returned no deals the element was gone and no later period —
// even one WITH deals — could ever re-render (getElementById returned null).
// Returns true when the empty state was applied (caller should bail).
function _setChartEmpty(canvas, isEmpty) {
    const body = canvas.closest('.card-body');
    const wrap = canvas.parentElement;              // fixed-height chart wrapper
    if (!body) return isEmpty;
    let msg = body.querySelector('.dash-empty-msg');
    if (isEmpty) {
        if (!msg) {
            msg = document.createElement('p');
            msg.className = 'dash-empty-msg text-muted text-center py-5 mb-0';
            body.appendChild(msg);
        }
        msg.textContent = t('dash-no-deals');
        msg.style.display = '';
        if (wrap) wrap.style.display = 'none';
    } else {
        if (msg) msg.style.display = 'none';
        if (wrap) wrap.style.display = '';
    }
    return isEmpty;
}

function buildClientsChart(top5) {
    const ctx = document.getElementById('top5-clients-chart');
    if (!ctx) return;
    if (clientsChart) clientsChart.destroy();
    if (_setChartEmpty(ctx, !top5.length)) return;
    // Distinct products across the top-5 clients → one stacked dataset each
    const products = [];
    top5.forEach(c => Object.keys(c.by_product || {}).forEach(p => { if (products.indexOf(p) === -1) products.push(p); }));
    const stacked = products.length > 0;
    let fb = 0;
    const datasets = stacked
        ? products.map(p => {
            const base = _productColor(p) || PRODUCT_FALLBACK[fb++ % PRODUCT_FALLBACK.length];
            return { label: p, data: top5.map(c => (c.by_product && c.by_product[p]) || 0),
                     backgroundColor: hGradient(base, 0.55, 1), borderRadius: stackEndRadius(6, 'left'), borderSkipped: false, barThickness: 22, stack: 'clients' };
        })
        : [{ label: 'Deals', data: top5.map(c => c.count), backgroundColor: hGradient(ins('chart-primary'), 0.55, 1), borderRadius: 6, barThickness: 22 }];

    clientsChart = new Chart(ctx, {
        type: 'bar',
        data: { labels: top5.map(d => d.label), datasets: datasets },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            animation: GROW_ANIM,
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
    if (_setChartEmpty(ctx, !top5.length)) return;
    const baseColors = [ins('chart-primary'), ins('chart-secondary'), ins('chart-dark'), ins('chart-gray'), ins('chart-primary')];
    productsChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: top5.map(d => d.label), datasets: [{ data: top5.map(d => d.count), backgroundColor: doughnutGradient(baseColors, 1, 0.6), borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff', borderWidth: 2, hoverOffset: 8, cutout: '60%' }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: GROW_ANIM_PIE,
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
    if (_setChartEmpty(ctx, !top5 || !top5.length)) return;
    commoditiesChart = new Chart(ctx, {
        type: 'doughnut',
        data: { labels: top5.map(d => d.label), datasets: [{ data: top5.map(d => d.count), backgroundColor: doughnutGradient(COMMODITY_COLORS, 1, 0.6), borderColor: isDark() ? 'rgba(30,41,59,0.6)' : '#fff', borderWidth: 2, hoverOffset: 8, cutout: '60%' }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            animation: GROW_ANIM_PIE,
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

// ─── live position (custody snapshot) ────────────────────────────────────────

let liveChart = null;
let _liveData = null;
let _liveDrp = null;  // daterangepicker instance for the Live Position date field
// Multi-hue palette for the by-product bars (distinct from the flow/pie tokens).
const LIVE_COLORS = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#f43f5e', '#a855f7', '#14b8a6', '#64748b'];

/** Toggle a centered "no data" message over the live-position canvas. */
function _setLiveEmpty(canvas, isEmpty) {
    const wrap = canvas.parentElement;
    let msg = wrap.querySelector('.dash-empty-msg');
    if (isEmpty) {
        if (!msg) {
            msg = document.createElement('div');
            msg.className = 'dash-empty-msg text-center text-muted d-flex align-items-center justify-content-center h-100';
            wrap.appendChild(msg);
        }
        msg.textContent = t('dash-live-empty', 'Sem arquivos de posição para esta data.');
        msg.style.display = '';
        canvas.style.display = 'none';
    } else if (msg) {
        msg.style.display = 'none';
        canvas.style.display = '';
    }
    return isEmpty;
}

function buildLivePositionChart(data) {
    const ctx = document.getElementById('live-position-chart');
    if (!ctx) return;
    if (liveChart) liveChart.destroy();
    const rows = data.by_product || [];
    if (_setLiveEmpty(ctx, !rows.length)) return;
    // Horizontal gradient (left→right) keyed by the product's Settlement Forecast
    // color, so the two cards read as one consistent palette.
    const barColor = (context) => {
        const raw = rows[context.dataIndex] ? rows[context.dataIndex].label : '';
        const hex = liveProductColor(raw, context.dataIndex);
        const { ctx: c, chartArea } = context.chart;
        if (!chartArea) return hexToRgba(hex, 1);
        const g = c.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
        g.addColorStop(0, hexToRgba(hex, 0.5));
        g.addColorStop(1, hexToRgba(hex, 1));
        return g;
    };
    liveChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: rows.map(r => liveDisplayLabel(r.label)),
            datasets: [{
                label: t('dash-live-total', 'Live operations'),
                data: rows.map(r => r.count),
                backgroundColor: barColor,
                borderRadius: stackEndRadius(6, 'left'), borderSkipped: false,
                barThickness: 22,
            }]
        },
        options: {
            indexAxis: 'y', responsive: true, maintainAspectRatio: false,
            animation: GROW_ANIM,
            plugins: {
                legend: { display: false },
                tooltip: premiumTooltip({ callbacks: { label: ctx => ` ${ctx.parsed.x}` } })
            },
            scales: {
                x: { ticks: { font: { family: bodyFont }, color: ins('secondary-color'), precision: 0 }, grid: { color: ins('chart-border-color') }, border: { display: false } },
                y: { ticks: { font: { family: bodyFont, size: 11 }, color: ins('secondary-color') }, grid: { display: false }, border: { display: false } }
            }
        }
    });
}

function renderLiveEntityStats(entities) {
    const box = document.getElementById('live-entity-stats');
    if (!box) return;
    if (!entities || !entities.length) { box.innerHTML = ''; return; }
    box.innerHTML = entities.map(e => `
        <div class="d-flex align-items-center justify-content-between">
            <span class="text-muted fs-xs">${e.label}</span>
            <span class="badge bg-light text-body fw-semibold">${e.count}</span>
        </div>`).join('');
}

async function loadLivePosition(dateStr) {
    try {
        const qs = dateStr ? `?date=${dateStr}` : '';
        const res = await fetch(`/api/dashboard-live-position${qs}`);
        const data = await res.json();
        _liveData = data;

        const total = document.getElementById('live-total');
        if (total) total.textContent = (data.total ?? 0).toLocaleString();

        const asOf = document.getElementById('live-asof');
        if (asOf && data.ref_date_fmt) asOf.textContent = `${t('dash-forecast-asof', 'as of')} ${data.ref_date_fmt}`;

        // Keep the picker in sync with the resolved reference date (default D-1 ANBIMA).
        // daterangepicker.setStartDate auto-updates the input (dd/mm/yyyy) and doesn't
        // re-fire the change callback, so no recursion.
        if (_liveDrp && data.ref_date && window.moment) {
            const m = window.moment(data.ref_date, 'YYYY-MM-DD');
            _liveDrp.setStartDate(m);
            _liveDrp.setEndDate(m);
        } else {
            const picker = document.getElementById('live-date');
            if (picker && data.ref_date && !picker.value) {
                const p = data.ref_date.split('-');
                if (p.length === 3) picker.value = p[2] + '/' + p[1] + '/' + p[0];
            }
        }

        renderLiveEntityStats(data.by_entity);
        buildLivePositionChart(data);
    } catch (err) {
        console.error('[Dashboard] Failed to load live position:', err);
    }
}

function wireLivePosition(attempt) {
    const inp = document.getElementById('live-date');
    if (!inp) return;
    // MANDATORY project pattern: jQuery daterangepicker (dd/mm/yyyy), assets loaded on
    // the page. NEVER a native <input type="date"> (inherits the OS locale → mm/dd/yyyy
    // on the JP Windows env) nor the "global" flatpickr (failed intermittently).
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
        const $d = jQuery('#live-date');
        // Start already on the resolved ref date if loadLivePosition finished first.
        const startISO = (_liveData && _liveData.ref_date) ? _liveData.ref_date : null;
        $d.daterangepicker({
            singleDatePicker: true, autoApply: true, showDropdowns: true,
            locale: { format: 'DD/MM/YYYY' },
            startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment()
        }, function (start) { loadLivePosition(start.format('YYYY-MM-DD')); });
        jQuery('#liveDateWrap .live-cal-btn').on('click', function () { $d.trigger('click'); });
        _liveDrp = $d.data('daterangepicker');
        return;
    }
    // Plugin not ready yet (slow/late script load) — RETRY briefly instead of dropping to
    // the text fallback permanently. ~40 × 50ms = 2s before giving up.
    attempt = attempt || 0;
    if (attempt < 40) {
        setTimeout(function () { wireLivePosition(attempt + 1); }, 50);
        return;
    }
    // True fallback: plain dd/mm/yyyy text field only if the plugin genuinely failed to load.
    inp.removeAttribute('readonly');
    inp.addEventListener('change', function () {
        const m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (m) loadLivePosition(m[3] + '-' + m[2] + '-' + m[1]);
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
        buildPieChart(data.dist_ndf, data.dist_opt, data.dist_fxo, data.dist_swap);
        buildFlowChart(data.monthly_ndf, data.monthly_opt, data.monthly_fxo, data.monthly_swap);
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
    buildPieChart(_lastData.dist_ndf, _lastData.dist_opt, _lastData.dist_fxo, _lastData.dist_swap);
    buildFlowChart(_lastData.monthly_ndf, _lastData.monthly_opt, _lastData.monthly_fxo, _lastData.monthly_swap);
    buildClientsChart(_lastData.top5_clients);
    buildProductsChart(_lastData.top5_products);
    buildCommoditiesChart(_lastData.top5_underlying);
    if (_forecastData) buildForecastProductChart(_forecastData);
    if (_liveData) buildLivePositionChart(_liveData);
}

// ─── init ────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await loadTranslations();
    loadDashboard('year');
    wireForecastRange();
    loadForecastChart();   // independent of the period filter
    wireLivePosition();
    loadLivePosition();    // custody snapshot at D-1 ANBIMA (independent of period)

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

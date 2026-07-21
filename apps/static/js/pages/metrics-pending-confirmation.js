/**
 * OTC Tracker — Pending Confirmation Metrics
 * History (volume + period-over-period %) and Top-5 offenders (> 30 days).
 */
(function () {
    'use strict';

    const bodyFont = getComputedStyle(document.body).fontFamily.trim();
    const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const GROW = { duration: 850, easing: 'easeOutQuart' };

    const isDark = () => document.documentElement.getAttribute('data-bs-theme') === 'dark';
    const txtColor = () => (isDark() ? '#cbd5e1' : '#475569');
    const gridColor = () => (isDark() ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.06)');

    // Semantic colour for the period-over-period change: fewer pending is GOOD
    // (green), flat is neutral (grey), more pending is BAD (red). Pending is a
    // metric you want to go DOWN, so the scale is inverted vs. a typical KPI.
    const C_GOOD = '#16a34a', C_NEUTRAL = '#94a3b8', C_BAD = '#dc2626';
    function changeColor(pct) {
        if (pct == null) return C_NEUTRAL;
        if (pct < 0) return C_GOOD;      // decreased → improvement
        if (pct > 0) return C_BAD;       // increased → worse
        return C_NEUTRAL;                // unchanged → neutral
    }

    function hexToRgba(hex, a) {
        const h = (hex || '').replace('#', '');
        const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
        const n = parseInt(full, 16);
        if (isNaN(n)) return `rgba(0,102,204,${a})`;
        return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
    }
    // Vertical gradient (bottom→top) for bars.
    function vGrad(hex, top, bottom) {
        return (c) => {
            const { ctx, chartArea } = c.chart;
            if (!chartArea) return hexToRgba(hex, top);
            const g = ctx.createLinearGradient(0, chartArea.bottom, 0, chartArea.top);
            g.addColorStop(0, hexToRgba(hex, bottom));
            g.addColorStop(1, hexToRgba(hex, top));
            return g;
        };
    }
    // Horizontal gradient (left→right) for horizontal bars.
    function hGrad(hex, left, right) {
        return (c) => {
            const { ctx, chartArea } = c.chart;
            if (!chartArea) return hexToRgba(hex, right);
            const g = ctx.createLinearGradient(chartArea.left, 0, chartArea.right, 0);
            g.addColorStop(0, hexToRgba(hex, left));
            g.addColorStop(1, hexToRgba(hex, right));
            return g;
        };
    }
    function tooltip(extra) {
        const d = isDark();
        return Object.assign({
            backgroundColor: d ? 'rgba(30,41,59,.95)' : 'rgba(255,255,255,.97)',
            titleColor: d ? '#f1f5f9' : '#1e293b',
            bodyColor: d ? '#cbd5e1' : '#475569',
            borderColor: d ? 'rgba(255,255,255,.12)' : 'rgba(0,0,0,.08)',
            borderWidth: 1, padding: 12, cornerRadius: 10, usePointStyle: true, boxPadding: 6,
            titleFont: { family: bodyFont, weight: '600', size: 13 },
            bodyFont: { family: bodyFont, size: 12 },
        }, extra || {});
    }

    // ── data ──────────────────────────────────────────────────────────────
    let HISTORY = null, OFFENDERS = null;
    const charts = {};   // id -> Chart instance

    const fmtMonth = (p) => { const [y, m] = p.split('-'); return `${MONTHS[+m - 1]}/${y.slice(2)}`; };
    const fmtDay = (d) => { const [, m, dd] = d.split('-'); return `${dd}/${m}`; };
    const truncate = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : (s || ''));

    // Pick the series for the current scope + range.
    function pickSeries() {
        const scope = document.getElementById('pcm-scope').value;   // gt30 | all
        const range = document.getElementById('pcm-range').value;   // cy | l24 | daily
        const bucket = (HISTORY && HISTORY[scope]) || { monthly: [], daily: [] };
        if (range === 'daily') {
            const now = new Date();
            const ym = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
            let pts = (bucket.daily || []).filter(p => p.date.startsWith(ym));
            if (!pts.length) pts = bucket.daily || [];   // fall back to whatever daily we have
            return { pts, key: 'date', label: fmtDay, isDaily: true };
        }
        let months = bucket.monthly || [];
        if (range === 'cy') {
            const y = String(new Date().getFullYear());
            const cy = months.filter(p => p.period.startsWith(y));
            months = cy.length ? cy : months.slice(-12);
        } else { // l24
            months = months.slice(-24);
        }
        return { pts: months, key: 'period', label: fmtMonth, isDaily: false };
    }

    function renderHistory() {
        const { pts, key, label, isDaily } = pickSeries();
        const cv = document.getElementById('pcm-history-chart');
        const note = document.getElementById('pcm-history-note');
        if (charts.history) { charts.history.destroy(); charts.history = null; }
        if (!pts.length) {
            note.textContent = 'No data for this selection yet.';
            const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, cv.width, cv.height);
            return;
        }
        var rangeTxt = isDaily ? 'Daily snapshots for the current month.'
            : (document.getElementById('pcm-range').value === 'cy' ? 'Month-end volume, current year.' : 'Month-end volume, trailing 24 months.');
        note.innerHTML = rangeTxt + ' &nbsp;·&nbsp; Change: '
            + '<span style="color:' + C_GOOD + ';font-weight:600">▼ down = fewer pending (good)</span>&nbsp;&nbsp;'
            + '<span style="color:' + C_NEUTRAL + ';font-weight:600">► flat</span>&nbsp;&nbsp;'
            + '<span style="color:' + C_BAD + ';font-weight:600">▲ up = more pending (bad)</span>';
        const barColor = '#0066cc';
        charts.history = new Chart(cv, {
            data: {
                labels: pts.map(p => label(p[key])),
                datasets: [
                    {
                        type: 'bar', label: 'Volume', yAxisID: 'y',
                        data: pts.map(p => p.volume),
                        backgroundColor: vGrad(barColor, 1, 0.45), borderColor: 'transparent',
                        borderRadius: 6, borderSkipped: false, barThickness: isDaily ? 26 : 'flex',
                        maxBarThickness: 34, order: 2,
                    },
                    {
                        type: 'line', label: 'Change', yAxisID: 'y1',
                        data: pts.map(p => (p.pct == null ? null : p.pct)),
                        borderColor: C_NEUTRAL, borderWidth: 2, tension: 0.35,
                        pointRadius: 4, pointHoverRadius: 6,
                        pointBackgroundColor: (ctx) => changeColor(ctx.raw),
                        pointBorderColor:     (ctx) => changeColor(ctx.raw),
                        // Colour each segment by the point it lands on: down → green
                        // (good), up → red (bad), flat → grey — trend reads at a glance.
                        segment: { borderColor: (ctx) => changeColor(ctx.p1.parsed.y) },
                        spanGaps: true, order: 1,
                    },
                ],
            },
            options: {
                responsive: true, maintainAspectRatio: false, animation: GROW,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: true, position: 'top', align: 'end',
                        labels: { usePointStyle: true, boxWidth: 8, font: { family: bodyFont }, color: txtColor() } },
                    tooltip: tooltip({
                        callbacks: {
                            label: (it) => it.dataset.label === 'Change'
                                ? (it.parsed.y == null ? '' : `Change: ${it.parsed.y > 0 ? '▲ +' : (it.parsed.y < 0 ? '▼ ' : '► ')}${it.parsed.y}%`)
                                : `Volume: ${it.parsed.y}`,
                        },
                    }),
                },
                scales: {
                    x: { ticks: { font: { family: bodyFont }, color: txtColor(), maxRotation: 0, autoSkip: true }, grid: { display: false }, border: { display: false } },
                    y: { beginAtZero: true, ticks: { font: { family: bodyFont }, color: txtColor(), precision: 0 }, grid: { color: gridColor() }, border: { display: false }, title: { display: true, text: 'Volume', color: txtColor(), font: { family: bodyFont, size: 11 } } },
                    y1: { position: 'right', ticks: { font: { family: bodyFont }, color: txtColor(), callback: (v) => v + '%' }, grid: { display: false }, border: { display: false } },
                },
            },
        });
    }

    // ── KPI hero (from gt30 series) ───────────────────────────────────────
    function renderKPI() {
        const g = (HISTORY && HISTORY.gt30) || { monthly: [], daily: [] };
        const daily = g.daily || [], monthly = g.monthly || [];
        const latest = daily.length ? daily[daily.length - 1] : (monthly.length ? monthly[monthly.length - 1] : null);
        const setTxt = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
        if (!latest) { setTxt('pcm-kpi-value', '—'); return; }
        setTxt('pcm-kpi-value', latest.volume);
        // trend = latest point's own pct (DoD if daily, MoM if monthly)
        const tr = document.getElementById('pcm-kpi-trend');
        const p = latest.pct;
        if (p == null) { tr.className = 'pcm-trend flat mb-2'; tr.textContent = '—'; }
        else {
            tr.className = 'pcm-trend mb-2 ' + (p > 0 ? 'up' : (p < 0 ? 'down' : 'flat'));
            tr.innerHTML = `<i class="ti ti-${p > 0 ? 'trending-up' : (p < 0 ? 'trending-down' : 'minus')}"></i>${p > 0 ? '+' : ''}${p}%`;
        }
        const noteLbl = daily.length
            ? 'Latest: ' + fmtDay(latest.date) + ' (day-over-day)'
            : 'Latest month (month-over-month)';
        setTxt('pcm-kpi-note', noteLbl);
        // monthly context
        const prev = monthly.length ? monthly[monthly.length - 1] : null;
        setTxt('pcm-mini-prev', prev ? prev.volume : '—');
        const last12 = monthly.slice(-12);
        setTxt('pcm-mini-avg', last12.length ? Math.round(last12.reduce((a, m) => a + m.volume, 0) / last12.length) : '—');
        const last24 = monthly.slice(-24);
        setTxt('pcm-mini-peak', last24.length ? Math.max.apply(null, last24.map(m => m.volume)) : '—');
    }

    // ── Top-5 offenders (horizontal bars) ─────────────────────────────────
    function offenderChart(id, items, hex, valueLabel) {
        if (charts[id]) { charts[id].destroy(); charts[id] = null; }
        const cv = document.getElementById(id);
        if (!cv) return;
        if (!items || !items.length) {
            const ctx = cv.getContext('2d');
            ctx.clearRect(0, 0, cv.width, cv.height);
            ctx.save();
            ctx.font = '13px ' + bodyFont; ctx.fillStyle = txtColor();
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText('No pending > 30 days in the latest snapshot', cv.width / 2, cv.height / 2);
            ctx.restore();
            return;
        }
        charts[id] = new Chart(cv, {
            type: 'bar',
            data: {
                labels: items.map(i => truncate(i.label, 26)),
                datasets: [{
                    label: valueLabel, data: items.map(i => i.value),
                    backgroundColor: hGrad(hex, 0.5, 1), borderColor: 'transparent',
                    borderRadius: 6, borderSkipped: false, barThickness: 22,
                }],
            },
            options: {
                indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: GROW,
                plugins: {
                    legend: { display: false },
                    tooltip: tooltip({
                        callbacks: {
                            title: (it) => items[it[0].dataIndex].label,   // full (untruncated) name
                            label: (it) => `${valueLabel}: ${it.parsed.x}`,
                        },
                    }),
                },
                scales: {
                    x: { beginAtZero: true, ticks: { font: { family: bodyFont }, color: txtColor(), precision: 0 }, grid: { color: gridColor() }, border: { display: false } },
                    y: { ticks: { font: { family: bodyFont, size: 11 }, color: txtColor() }, grid: { display: false }, border: { display: false } },
                },
            },
        });
    }

    function renderOffenders() {
        const o = OFFENDERS || {};
        offenderChart('pcm-bankers-chart', o.bankers, '#0066cc', 'Contracts');
        offenderChart('pcm-clients-chart', o.clients, '#10b981', 'Contracts');
        offenderChart('pcm-egroups-chart', o.egroups, '#f59e0b', 'Contracts');
        const src = document.getElementById('pcm-source');
        if (src && o.source) {
            src.textContent = o.source === 'live' ? 'Source: live pending DB'
                : (o.source === 'none' ? 'No data' : 'Snapshot: ' + o.source);
        }
    }

    function renderAll() { renderKPI(); renderHistory(); renderOffenders(); }

    // ── fetch + wire ──────────────────────────────────────────────────────
    function load() {
        Promise.all([
            fetch('/api/metrics-pending-confirmation/history', { credentials: 'same-origin' }).then(r => r.json()),
            fetch('/api/metrics-pending-confirmation/offenders', { credentials: 'same-origin' }).then(r => r.json()),
        ]).then(([h, o]) => {
            HISTORY = (h && h.success) ? { gt30: h.gt30, all: h.all } : { gt30: { monthly: [], daily: [] }, all: { monthly: [], daily: [] } };
            OFFENDERS = (o && o.success) ? o : { bankers: [], clients: [], egroups: [], source: 'none' };
            renderAll();
        }).catch(() => {
            HISTORY = { gt30: { monthly: [], daily: [] }, all: { monthly: [], daily: [] } };
            OFFENDERS = { bankers: [], clients: [], egroups: [], source: 'none' };
            renderAll();
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        document.getElementById('pcm-scope').addEventListener('change', renderHistory);
        document.getElementById('pcm-range').addEventListener('change', renderHistory);
        // Re-render on theme toggle so axis/tooltip colors follow.
        new MutationObserver(() => { if (HISTORY) renderAll(); })
            .observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme'] });
        load();
    });
})();

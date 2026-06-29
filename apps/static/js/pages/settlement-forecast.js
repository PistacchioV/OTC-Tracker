/* ============================================================================
 *  Settlement Forecast — dashboard charts (Chart.js, "Deal Flow Analytics" style)
 * ----------------------------------------------------------------------------
 *  Triggered by the "Run" button on the Settlement Forecast card (Control Panel).
 *  Flow:
 *    1. POST the reference date → /settlement-forecast/data  (compute forecast)
 *    2. render the 2 stacked-bar charts OFF-SCREEN on <canvas> (same Chart.js
 *       look/colours/format as the dashboard's Deal Flow Analytics, but DAILY:
 *       the next 14 business days from today)
 *    3. export each canvas to a PNG data URI (canvas.toDataURL)
 *    4. POST {date, images} → /settlement-forecast/email  (server embeds the
 *       PNGs and e-mails the report to OTC Ops)
 *
 *  Value labels are drawn ALWAYS-VISIBLE (tooltip-style badge with the bar total
 *  + per-segment values) by a small custom plugin, so they appear in the e-mail
 *  image instead of only on hover.
 * ========================================================================== */
(function () {
  'use strict';

  var bodyFont = getComputedStyle(document.body).fontFamily.trim() || 'sans-serif';

  function cssVar(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue('--ins-' + name).trim();
    return v || fallback;
  }
  function hexToRgba(hex, a) {
    hex = (hex || '').trim();
    if (hex.indexOf('rgb') === 0) return hex;
    var h = hex.replace('#', '');
    if (h.length === 3) h = h.split('').map(function (c) { return c + c; }).join('');
    var n = parseInt(h, 16);
    if (isNaN(n)) return 'rgba(79,70,229,' + a + ')';
    return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  // Vertical gradient (bottom → top) — identical approach to the dashboard.
  function vGradient(hex, topAlpha, bottomAlpha) {
    return function (context) {
      var ch = context.chart, area = ch.chartArea;
      if (!area) return hexToRgba(hex, topAlpha);
      var g = ch.ctx.createLinearGradient(0, area.bottom, 0, area.top);
      g.addColorStop(0, hexToRgba(hex, bottomAlpha));
      g.addColorStop(1, hexToRgba(hex, topAlpha));
      return g;
    };
  }

  // Base colour per product / entity (theme tokens first, like the dashboard).
  function productColors() {
    return {
      'NDF Moeda':       cssVar('chart-primary', '#4f46e5'),
      'NDF Commodities': cssVar('chart-secondary', '#818cf8'),
      'Option FXO':      '#10b981',
      'Option Commodities': '#0ea5e9',
      'Option EDG':      '#a855f7',
      'SWAP CEM':        '#f59e0b',
      'SWAP EDG':        '#f43f5e',
      'SWAP CEMHYB':     '#94a3b8',
      'SWAP':            '#f59e0b'
    };
  }
  function entityColors() {
    return { 'LAWTON': cssVar('chart-primary', '#4f46e5'), 'MGT': '#10b981', 'ATACAMA': '#f59e0b' };
  }
  var FALLBACK = ['#4f46e5', '#0ea5e9', '#10b981', '#a855f7', '#f59e0b', '#f43f5e', '#14b8a6', '#94a3b8'];

  // Minimal i18n (Swal copy).
  var LANG = (localStorage.getItem('__OTC_TRACKER_LANG__') || 'en').slice(0, 2);
  var TXT = {
    en: { running: 'Running…', sending: 'Sending e-mail…', noData: 'No data',
          okTitle: 'Forecast sent', okMsg: 'Settlement Forecast e-mailed to OTC Ops.',
          errTitle: 'Forecast failed', net: 'Network error.' },
    br: { running: 'Executando…', sending: 'Enviando e-mail…', noData: 'Sem dados',
          okTitle: 'Forecast enviado', okMsg: 'Settlement Forecast enviado por e-mail para a OTC Ops.',
          errTitle: 'Falha no forecast', net: 'Erro de rede.' },
    es: { running: 'Ejecutando…', sending: 'Enviando correo…', noData: 'Sin datos',
          okTitle: 'Forecast enviado', okMsg: 'Settlement Forecast enviado por correo a OTC Ops.',
          errTitle: 'Error en el forecast', net: 'Error de red.' }
  };
  function tr(k) { return (TXT[LANG] || TXT.en)[k] || TXT.en[k] || k; }

  function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // Paint a white background so the exported PNG isn't transparent (→ black) in e-mail.
  var whiteBg = {
    id: 'whiteBg',
    beforeDraw: function (c) {
      var ctx = c.ctx;
      ctx.save();
      ctx.globalCompositeOperation = 'destination-over';
      ctx.fillStyle = '#ffffff';
      ctx.fillRect(0, 0, c.width, c.height);
      ctx.restore();
    }
  };

  // Always-visible value labels: per-segment value (white, inside the bar) +
  // a tooltip-style rounded badge with the stack TOTAL on top of each bar.
  var valueLabels = {
    id: 'valueLabels',
    afterDatasetsDraw: function (chart) {
      var ctx = chart.ctx;
      var nLabels = chart.data.labels.length;

      // per-segment values
      chart.data.datasets.forEach(function (ds, di) {
        var meta = chart.getDatasetMeta(di);
        if (meta.hidden) return;
        meta.data.forEach(function (bar, i) {
          var v = ds.data[i];
          if (!v) return;
          var props = bar.getProps(['x', 'y', 'base'], true);
          var h = Math.abs(props.base - props.y);
          if (h < 15) return;                       // segment too short for a label
          ctx.save();
          ctx.fillStyle = '#ffffff';
          ctx.font = '700 11px ' + bodyFont;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.fillText(String(v), props.x, (props.y + props.base) / 2);
          ctx.restore();
        });
      });

      // tooltip-style total badge on top of each bar
      for (var i = 0; i < nLabels; i++) {
        var total = 0, topY = Infinity, x = null;
        chart.data.datasets.forEach(function (ds, di) {
          var meta = chart.getDatasetMeta(di);
          if (meta.hidden) return;
          var v = ds.data[i] || 0;
          total += v;
          if (v > 0) {
            var bar = meta.data[i];
            var p = bar.getProps(['x', 'y'], true);
            if (p.y < topY) topY = p.y;
            x = p.x;
          }
        });
        if (!total || x === null) continue;

        var text = String(total);
        ctx.save();
        ctx.font = '800 12px ' + bodyFont;
        var tw = ctx.measureText(text).width;
        var padX = 7, bh = 19, bw = tw + padX * 2;
        var bx = x - bw / 2, by = topY - bh - 7;
        if (by < 2) by = 2;
        roundRect(ctx, bx, by, bw, bh, 9);
        ctx.fillStyle = 'rgba(255,255,255,0.97)';
        ctx.strokeStyle = 'rgba(0,0,0,0.08)';
        ctx.lineWidth = 1;
        ctx.shadowColor = 'rgba(15,23,42,0.12)';
        ctx.shadowBlur = 5;
        ctx.shadowOffsetY = 2;
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.stroke();
        ctx.fillStyle = '#1e293b';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, x, by + bh / 2);
        ctx.restore();
      }
    }
  };

  function stackedConfig(data, rows, colorMap, title, subtitle) {
    var datasets = rows.map(function (r, idx) {
      var base = colorMap[r.label] || FALLBACK[idx % FALLBACK.length];
      return {
        type: 'bar', label: r.label, data: r.values,
        backgroundColor: vGradient(base, 1, 0.45),
        borderColor: 'transparent', stack: 'fc',
        maxBarThickness: 30, borderRadius: 6
      };
    });
    return {
      type: 'bar',
      data: { labels: data.date_labels, datasets: datasets },
      options: {
        responsive: false, maintainAspectRatio: false, animation: false,
        layout: { padding: { top: 26, right: 8, left: 4, bottom: 2 } },
        plugins: {
          legend: { display: true, position: 'top',
                    labels: { font: { family: bodyFont }, color: '#54545a',
                              usePointStyle: true, pointStyle: 'circle', boxWidth: 8, padding: 14 } },
          tooltip: { enabled: false },
          title: { display: true, text: title, align: 'start',
                   color: '#1d1d1f', font: { family: bodyFont, size: 16, weight: '700' },
                   padding: { bottom: 2 } },
          subtitle: { display: true, text: subtitle, align: 'start',
                      color: '#6e6e73', font: { family: bodyFont, size: 12 },
                      padding: { bottom: 12 } }
        },
        scales: {
          x: { stacked: true, grid: { display: false }, border: { display: false },
               ticks: { font: { family: bodyFont }, color: '#54545a' } },
          y: { stacked: true, beginAtZero: true,
               grid: { color: '#eceef2', lineWidth: 1 },
               border: { display: false, dash: [5, 5] },
               ticks: { precision: 0, font: { family: bodyFont }, color: '#54545a' } }
        }
      },
      plugins: [whiteBg, valueLabels]
    };
  }

  // Render a chart on the off-screen canvas, then export it to a PNG data URI.
  function renderAndExport(canvasId, config) {
    return new Promise(function (resolve) {
      var cv = document.getElementById(canvasId);
      if (!cv || typeof Chart === 'undefined') { resolve(null); return; }
      var chart;
      try { chart = new Chart(cv, config); } catch (e) { resolve(null); return; }
      // animation:false → drawn synchronously; small delay lets gradients settle.
      setTimeout(function () {
        var uri = null;
        try { uri = cv.toDataURL('image/png', 1.0); } catch (e) {}
        try { chart.destroy(); } catch (e) {}
        resolve(uri);
      }, 80);
    });
  }

  function isoDateFrom(inputId) {
    var di = document.getElementById(inputId);
    if (!di || !di.value) return '';
    var m = di.value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : di.value;
  }

  function runForecast(btn) {
    var label = btn.querySelector('span');
    var icon = btn.querySelector('i');
    var orig = label ? label.textContent : '';
    btn.disabled = true;
    if (label) label.textContent = tr('running');
    if (icon) icon.className = 'ti ti-loader-2 ti-spin';

    var date = isoDateFrom(btn.getAttribute('data-date-input'));

    fetch('/api/control-panel/settlement-forecast/data', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date: date })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.body || res.body.success === false) {
          throw { msg: (res.body && res.body.error) || tr('noData') };
        }
        var data = res.body;
        if (label) label.textContent = tr('sending');
        return Promise.all([
          renderAndExport('fcstStageProduct',
            stackedConfig(data, data.products, productColors(),
              'Settlements by Product', 'Next 14 business days, by product')),
          renderAndExport('fcstStageEntity',
            stackedConfig(data, data.entities, entityColors(),
              'Settlements by Entity', 'Next 14 business days, by entity'))
        ]).then(function (imgs) {
          return fetch('/api/control-panel/settlement-forecast/email', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date: data.ref_date,
                                   images: { by_product: imgs[0], by_entity: imgs[1] } })
          }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
        });
      })
      .then(function (res) {
        if (res.ok && res.body && res.body.success !== false) {
          Swal.fire({ icon: 'success', title: tr('okTitle'),
                      html: res.body.message || tr('okMsg'), confirmButtonColor: '#0066cc' });
        } else {
          Swal.fire({ icon: 'error', title: tr('errTitle'),
                      html: (res.body && res.body.error) || tr('net'), confirmButtonColor: '#0066cc' });
        }
      })
      .catch(function (err) {
        Swal.fire({ icon: 'error', title: tr('errTitle'),
                    html: (err && err.msg) || tr('net'), confirmButtonColor: '#0066cc' });
      })
      .finally(function () {
        btn.disabled = false;
        if (label) label.textContent = orig;
        if (icon) icon.className = 'ti ti-player-play';
      });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-forecast-run]');
    if (btn && !btn.disabled) runForecast(btn);
  });
})();

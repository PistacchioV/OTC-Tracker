/* ============================================================================
 *  Settlement Forecast — dashboard charts (ApexCharts) + Run flow
 * ----------------------------------------------------------------------------
 *  Triggered by the "Run" button on the Settlement Forecast card (Control Panel).
 *  Flow:
 *    1. POST the reference date → /settlement-forecast/data  (compute forecast)
 *    2. render the 3 dashboard charts OFF-SCREEN (stacked bar by product, by
 *       entity, donut product-mix)
 *    3. export each chart to a PNG data URI (ApexCharts.dataURI)
 *    4. POST {date, images} → /settlement-forecast/email  (server embeds the
 *       PNGs + tables and e-mails the report to OTC Ops)
 *  This keeps the *real* dashboard chart in the e-mail with no head-less browser.
 * ========================================================================== */
(function () {
  'use strict';

  // ── Cohesive product / entity palettes (match the dashboard look) ──────────
  var PRODUCT_COLORS = {
    'NDF Moeda':         '#0066cc',
    'OPÇÃO Moeda':       '#1ba0d4',
    'OPÇÃO Commodities': '#17b39a',
    'OPÇÃO Equities':    '#7c5cd6',
    'SWAP CEM':          '#f5a524',
    'SWAP EDG':          '#e5484d',
    'SWAP CEMHYB':       '#8a929e',
    'SWAP':              '#f5a524'
  };
  var ENTITY_COLORS = {
    'LAWTON':  '#0066cc',
    'MGT':     '#17b39a',
    'ATACAMA': '#f5a524'
  };
  var FALLBACK = ['#0066cc', '#1ba0d4', '#17b39a', '#7c5cd6', '#f5a524', '#e5484d', '#8a929e'];

  // Minimal i18n (Swal copy) — reads the app language from localStorage.
  var LANG = (localStorage.getItem('__OTC_TRACKER_LANG__') || 'en').slice(0, 2);
  var TXT = {
    en: { running: 'Running…', noData: 'No data', sending: 'Sending e-mail…',
          okTitle: 'Forecast sent', okMsg: 'Settlement Forecast e-mailed to OTC Ops.',
          errTitle: 'Forecast failed', net: 'Network error.' },
    br: { running: 'Executando…', noData: 'Sem dados', sending: 'Enviando e-mail…',
          okTitle: 'Forecast enviado', okMsg: 'Settlement Forecast enviado por e-mail para a OTC Ops.',
          errTitle: 'Falha no forecast', net: 'Erro de rede.' },
    es: { running: 'Ejecutando…', noData: 'Sin datos', sending: 'Enviando correo…',
          okTitle: 'Forecast enviado', okMsg: 'Settlement Forecast enviado por correo a OTC Ops.',
          errTitle: 'Error en el forecast', net: 'Error de red.' }
  };
  function tr(k) { return (TXT[LANG] || TXT.en)[k] || TXT.en[k] || k; }

  function colorsFor(rows, map) {
    return rows.map(function (r, i) { return map[r.label] || FALLBACK[i % FALLBACK.length]; });
  }
  function toSeries(rows) {
    return rows.map(function (r) { return { name: r.label, data: r.values }; });
  }

  // ── ApexCharts option builders (dashboard style) ───────────────────────────
  var BASE_CHART = {
    fontFamily: 'inherit',
    background: '#ffffff',
    toolbar: { show: false },
    animations: { enabled: false },   // off → dataURI captures the final frame
    parentHeightOffset: 0
  };

  function stackedBarOptions(data, rows, colorMap, title, subtitle) {
    return {
      chart: Object.assign({ type: 'bar', stacked: true, height: 420, width: 880 }, BASE_CHART),
      series: toSeries(rows),
      colors: colorsFor(rows, colorMap),
      plotOptions: { bar: { columnWidth: '55%', borderRadius: 5, borderRadiusApplication: 'end' } },
      dataLabels: { enabled: false },
      stroke: { show: true, width: 2, colors: ['#fff'] },
      grid: { borderColor: '#eceef2', strokeDashArray: 4, padding: { left: 8, right: 8 } },
      xaxis: {
        categories: data.date_labels,
        axisBorder: { show: false }, axisTicks: { show: false },
        labels: { style: { colors: '#54545a', fontSize: '12px' } }
      },
      yaxis: { labels: { style: { colors: '#54545a', fontSize: '12px' } }, forceNiceScale: true },
      legend: { position: 'bottom', horizontalAlign: 'center', fontSize: '13px',
                markers: { radius: 12 }, itemMargin: { horizontal: 10 } },
      title: { text: title, align: 'left',
               style: { fontSize: '18px', fontWeight: 700, color: '#1d1d1f' } },
      subtitle: { text: subtitle, align: 'left',
                  style: { fontSize: '13px', color: '#6e6e73' }, offsetY: 26 }
    };
  }

  function donutOptions(rows, colorMap, title, subtitle) {
    var labels = rows.map(function (r) { return r.label; });
    var totals = rows.map(function (r) { return r.total; });
    return {
      chart: Object.assign({ type: 'donut', height: 420, width: 560 }, BASE_CHART),
      series: totals,
      labels: labels,
      colors: colorsFor(rows, colorMap),
      stroke: { width: 2, colors: ['#fff'] },
      dataLabels: { enabled: true, formatter: function (v) { return Math.round(v) + '%'; },
                    style: { fontSize: '12px', fontWeight: 600 } },
      plotOptions: { pie: { donut: { size: '64%', labels: {
        show: true,
        total: { show: true, label: 'Total', fontSize: '14px', color: '#6e6e73',
                 formatter: function (w) {
                   return w.globals.seriesTotals.reduce(function (a, b) { return a + b; }, 0);
                 } }
      } } } },
      legend: { position: 'right', fontSize: '13px', markers: { radius: 12 },
                itemMargin: { vertical: 4 } },
      title: { text: title, align: 'left',
               style: { fontSize: '18px', fontWeight: 700, color: '#1d1d1f' } },
      subtitle: { text: subtitle, align: 'left',
                  style: { fontSize: '13px', color: '#6e6e73' }, offsetY: 26 }
    };
  }

  // Render a chart into the off-screen stage and export it to a PNG data URI.
  function renderAndExport(elId, options) {
    return new Promise(function (resolve) {
      var el = document.getElementById(elId);
      if (!el || typeof ApexCharts === 'undefined') { resolve(null); return; }
      el.innerHTML = '';
      var chart = new ApexCharts(el, options);
      chart.render().then(function () {
        // small delay lets fonts/labels settle before the snapshot
        setTimeout(function () {
          chart.dataURI({ scale: 2 }).then(function (out) {
            resolve(out && out.imgURI ? out.imgURI : null);
            try { chart.destroy(); } catch (e) {}
          }).catch(function () { resolve(null); try { chart.destroy(); } catch (e) {} });
        }, 120);
      }).catch(function () { resolve(null); });
    });
  }

  function isoDateFrom(inputId) {
    var di = document.getElementById(inputId);
    if (!di || !di.value) return '';
    var m = di.value.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : di.value;
  }

  // ── Run flow ───────────────────────────────────────────────────────────────
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
        // Render the 3 charts off-screen, then export to PNG.
        return Promise.all([
          renderAndExport('fcstStageProduct',
            stackedBarOptions(data, data.products, PRODUCT_COLORS,
              'Settlements by Product', 'Upcoming settlements per business day')),
          renderAndExport('fcstStageEntity',
            stackedBarOptions(data, data.entities, ENTITY_COLORS,
              'Settlements by Entity', 'Upcoming settlements per business day')),
          renderAndExport('fcstStageMix',
            donutOptions(data.products, PRODUCT_COLORS,
              'Product Mix', 'Share of upcoming settlements'))
        ]).then(function (imgs) {
          return fetch('/api/control-panel/settlement-forecast/email', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              date: data.ref_date,
              images: { by_product: imgs[0], by_entity: imgs[1], mix: imgs[2] }
            })
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

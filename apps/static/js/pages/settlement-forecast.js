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
  // Apple system-color palette (cohesive, modern) — base colour per product.
  var PRODUCT_COLORS = {
    'NDF Moeda':       '#0a84ff',   // blue
    'NDF Commodities': '#5e5ce6',   // indigo
    'Opt FXO':         '#5ac8fa',   // cyan
    'OPT Comm':        '#30d158',   // green
    'OPT EDG':         '#bf5af2',   // purple
    'OPT Equities':    '#bf5af2',   // purple (alias)
    'SWAP CEM':        '#ff9f0a',   // orange
    'SWAP EDG':        '#ff453a',   // red
    'SWAP CEMHYB':     '#8e8e93',   // gray
    'SWAP':            '#ff9f0a'
  };
  var ENTITY_COLORS = {
    'LAWTON':  '#0a84ff',
    'MGT':     '#30d158',
    'ATACAMA': '#ff9f0a'
  };
  var FALLBACK = ['#0a84ff', '#5e5ce6', '#5ac8fa', '#30d158', '#bf5af2', '#ff9f0a', '#ff453a', '#8e8e93'];

  // Lighten a hex colour toward white (amt 0..1) — used for the bar gradient top.
  function lighten(hex, amt) {
    hex = (hex || '#888888').replace('#', '');
    var r = parseInt(hex.substr(0, 2), 16),
        g = parseInt(hex.substr(2, 2), 16),
        b = parseInt(hex.substr(4, 2), 16);
    r = Math.round(r + (255 - r) * amt);
    g = Math.round(g + (255 - g) * amt);
    b = Math.round(b + (255 - b) * amt);
    return '#' + [r, g, b].map(function (x) { return ('0' + x.toString(16)).slice(-2); }).join('');
  }

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
    var base = colorsFor(rows, colorMap);
    var gradTo = base.map(function (c) { return lighten(c, 0.30); });

    // Per-day stacked totals → drive the y-axis cap and the "hide tiny label" rule.
    var n = data.date_labels.length;
    var dayTotals = [];
    for (var i = 0; i < n; i++) {
      var s = 0;
      for (var j = 0; j < rows.length; j++) { s += (rows[j].values[i] || 0); }
      dayTotals.push(s);
    }
    var maxTotal = dayTotals.length ? Math.max.apply(null, dayTotals) : 0;
    var yMax = maxTotal <= 900 ? 900 : Math.ceil(maxTotal / 100) * 100;   // cap at 900, grow if needed
    var labelMin = Math.max(maxTotal * 0.03, 1);   // hide segment labels smaller than ~3% of max

    return {
      chart: Object.assign({ type: 'bar', stacked: true, height: 470, width: 940 }, BASE_CHART),
      series: toSeries(rows),
      colors: base,
      fill: {
        type: 'gradient',
        gradient: {
          shade: 'light', type: 'vertical', shadeIntensity: 0.25,
          gradientToColors: gradTo, inverseColors: false,
          opacityFrom: 1, opacityTo: 1, stops: [0, 100]
        }
      },
      plotOptions: {
        bar: {
          columnWidth: '52%', borderRadius: 6, borderRadiusApplication: 'end',
          // Stacked total on top of each bar — dark, always readable on white
          dataLabels: {
            total: {
              enabled: true,
              formatter: function (v) { return v > 0 ? v : ''; },
              offsetY: -4,
              style: { fontSize: '12px', fontWeight: 800, color: '#1d1d1f' }
            }
          }
        }
      },
      // Apple-md value labels: rounded pill in the segment colour → readable even
      // when the value overflows the bar height (fixes white-on-white).
      dataLabels: {
        enabled: true,
        formatter: function (v) { return (v && v >= labelMin) ? v : ''; },
        style: { fontSize: '11px', fontWeight: 700, colors: ['#ffffff'] },
        background: {
          enabled: true, borderRadius: 6, borderWidth: 0, padding: 5,
          opacity: 0.95, foreColor: '#ffffff',
          dropShadow: { enabled: true, top: 1, left: 0, blur: 2, opacity: 0.22 }
        }
      },
      stroke: { show: true, width: 3, colors: ['#fff'] },
      grid: { borderColor: '#eceef2', strokeDashArray: 4, padding: { left: 8, right: 8 } },
      xaxis: {
        categories: data.date_labels,
        axisBorder: { show: false }, axisTicks: { show: false },
        labels: { style: { colors: '#54545a', fontSize: '12px', fontWeight: 600 } }
      },
      yaxis: {
        min: 0, max: yMax, tickAmount: 6, forceNiceScale: false,
        labels: { style: { colors: '#54545a', fontSize: '12px' } }
      },
      legend: {
        position: 'bottom', horizontalAlign: 'center', fontSize: '13px', fontWeight: 600,
        markers: { shape: 'circle', size: 7, radius: 12 },
        itemMargin: { horizontal: 10, vertical: 4 }
      },
      title: { text: title, align: 'left',
               style: { fontSize: '19px', fontWeight: 800, color: '#1d1d1f' } },
      subtitle: { text: subtitle, align: 'left',
                  style: { fontSize: '13px', color: '#6e6e73' }, offsetY: 28 }
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
        // Render the 2 charts off-screen, then export to PNG.
        return Promise.all([
          renderAndExport('fcstStageProduct',
            stackedBarOptions(data, data.products, PRODUCT_COLORS,
              'Settlements by Product', 'Upcoming settlements per business day, by product')),
          renderAndExport('fcstStageEntity',
            stackedBarOptions(data, data.entities, ENTITY_COLORS,
              'Settlements by Entity', 'Upcoming settlements per business day, by entity'))
        ]).then(function (imgs) {
          return fetch('/api/control-panel/settlement-forecast/email', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              date: data.ref_date,
              images: { by_product: imgs[0], by_entity: imgs[1] }
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

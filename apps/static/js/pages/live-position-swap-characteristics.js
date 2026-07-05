/**
 * Live Position › Swap › Characteristics
 * Read-only view of the swap book in custody on a reference date (D-1 ANBIMA
 * default). Widgets + a wide DataTable whose header/columns come straight from
 * the backend (single source of truth). Smart filter + Columns/Export toolbar
 * follow the New Deals pattern; the date picker follows the Live Position one.
 */
(function () {
  'use strict';

  var API = '/api/live-position-swap-characteristics/data';
  var page = document.getElementById('swapchar-page');
  if (!page) return;

  var dt = null;               // jQuery DataTables instance
  var COLS = [];               // [{label, idx}]
  var activeField = null;      // smart-filter: column chosen, awaiting a value
  var chips = [];              // [{idx, value}]

  // Minimal i18n for the few JS-driven strings (rest via data-lang in app.js).
  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter by column…', valuePh: 'Type value for "{f}" + Enter',
          status: 'In Custody', pickCol: 'Pick a column' },
    br: { filterPh: 'Filtrar por coluna…', valuePh: 'Digite o valor para "{f}" + Enter',
          status: 'Em Custódia', pickCol: 'Escolha uma coluna' },
    es: { filterPh: 'Filtrar por columna…', valuePh: 'Escriba el valor para "{f}" + Enter',
          status: 'En Custodia', pickCol: 'Elija una columna' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ── Data load ─────────────────────────────────────────────────────────────
  function load(dateStr) {
    var url = API + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : '');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        renderWidgets(d.widgets, d.ref_date_fmt);
        buildTable(d.columns, d.rows);
        var asof = document.getElementById('sc-total-asof');
        if (asof) asof.textContent = d.ref_date_fmt || '—';
      })
      .catch(function () {});
  }

  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  function renderWidgets(w, refFmt) {
    if (!w) return;
    setVal('sc-w-tipo-total', w.tipo.total); setVal('sc-w-tipo-cashflow', w.tipo.cashflow); setVal('sc-w-tipo-bullet', w.tipo.bullet);
    setVal('sc-w-lob-total', w.lob.total);
    ['CEM', 'EDG', 'COMM', 'HYB'].forEach(function (k) { setVal('sc-w-lob-' + k, w.lob[k]); });
    setVal('sc-w-index-total', w.index.total); setVal('sc-w-index-vcp', w.index.vcp); setVal('sc-w-index-calculado', w.index.calculado);
    setVal('sc-w-func-total', w.func.total);
    ['forward_start', 'notional', 'premio', 'arrependimento', 'sem'].forEach(function (k) { setVal('sc-w-func-' + k, w.func[k]); });
    setVal('sc-w-total', w.total);
  }

  // ── Table ─────────────────────────────────────────────────────────────────
  function buildTable(columns, rows) {
    COLS = columns.map(function (label, i) { return { label: label, idx: i }; });

    // Header: title row (checkbox, status, columns) + per-column filter row.
    var titleRow =
      '<tr id="swapchar-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="scCheckAll" class="form-check-input"></th>' +
      '<th data-lang="sc-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="sc-th-filter">' +
      '<th></th><th></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="sc-col-filter" data-col="' + (i + 2) +
          '" placeholder="' + esc(c) + '"></th>';
      }).join('') + '</tr>';
    document.querySelector('#swapchar-table thead').innerHTML = titleRow + filterRow;

    var statusBadge = '<span class="badge bg-secondary-subtle text-secondary" data-lang="sc-status-custody">' + esc(t('status')) + '</span>';
    var data = rows.map(function (r) {
      return ['<input type="checkbox" class="form-check-input sc-row-check">', statusBadge].concat(
        r.map(function (v) { return esc(v); })
      );
    });

    if (dt) { dt.destroy(); }
    var colDefs = [{ orderable: false, className: 'text-center', targets: 0 }];

    dt = jQuery('#swapchar-table').DataTable({
      data: data,
      columns: [{}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: colDefs,
      scrollX: true,
      autoWidth: true,
      orderCellsTop: true,          // sort listeners on the title row, not the filter row
      deferRender: true,
      pageLength: 25,
      lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']],
      order: [],
      dom: "<'row'<'col-sm-12'tr>><'d-md-flex justify-content-between align-items-center mt-2'ip>",
      buttons: [{
        extend: 'collection',
        text: '<i class="ti ti-download me-1"></i> Export',
        className: 'btn btn-sm btn-info bg-gradient dropdown-toggle',
        autoClose: true,
        buttons: [
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
        ],
      }],
    });

    // Place export dropdown into its wrapper.
    var expWrap = document.querySelector('.scExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    // Per-column filter row → column search (debounced by keyup/change).
    jQuery('#swapchar-table thead').off('keyup.sccol change.sccol')
      .on('keyup.sccol change.sccol', '.sc-col-filter', function () {
        var col = +this.getAttribute('data-col');
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('sc-count', rows.length);
    buildColumnsToggle();
    reapplyChips();
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    // Select-all checkbox
    var checkAll = document.getElementById('scCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#swapchar-table tbody .sc-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  // ── Columns show/hide (New Deals ti-columns pattern) ───────────────────────
  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim();
      return '<li class="px-3 py-1">' +
        '<div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="scCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="scCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="scColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('scColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  // ── Smart filter ───────────────────────────────────────────────────────────
  function reapplyChips() {
    if (!dt) return;
    dt.columns().every(function () { this.search(''); });
    // Keep the per-column filter row inputs alongside the smart-filter chips.
    document.querySelectorAll('#swapchar-table .sc-col-filter').forEach(function (inp) {
      if (inp.value) dt.column(+inp.getAttribute('data-col')).search(inp.value);
    });
    chips.forEach(function (c) { dt.column(c.idx + 2).search(c.value); });
    dt.draw();
  }

  function renderChips() {
    var box = document.getElementById('scChips');
    box.innerHTML = chips.map(function (c, i) {
      return '<span class="smart-filter-chip">' + esc(COLS[c.idx].label) + ': ' + esc(c.value) +
        '<span class="sf-chip-remove" data-i="' + i + '">&times;</span></span>';
    }).join('');
    box.querySelectorAll('.sf-chip-remove').forEach(function (x) {
      x.addEventListener('click', function () {
        chips.splice(parseInt(this.dataset.i, 10), 1);
        renderChips(); reapplyChips();
      });
    });
  }

  function colType(label) {
    var n = label.toLowerCase();
    if (n.indexOf('data') === 0) return 'date';
    if (/valor|saldo|percentual|taxa|pu |premio|prêmio|rebate|cota|aliquota|alíquota|fator/.test(n)) return 'value';
    return 'text';
  }

  function showDropdown(term) {
    var dd = document.getElementById('scDropdown');
    var lo = (term || '').toLowerCase();
    var matches = COLS.filter(function (c) { return c.label.toLowerCase().indexOf(lo) !== -1; }).slice(0, 40);
    if (!matches.length) { dd.style.display = 'none'; return; }
    dd.innerHTML = matches.map(function (c) {
      var ty = colType(c.label);
      return '<li data-idx="' + c.idx + '"><span class="sf-type-badge sf-type-' + ty + '">' + ty + '</span>' + esc(c.label) + '</li>';
    }).join('');
    dd.style.display = 'block';
    dd.querySelectorAll('li').forEach(function (li) {
      li.addEventListener('click', function () {
        activeField = COLS[parseInt(this.dataset.idx, 10)];
        var inp = document.getElementById('scInput');
        inp.value = '';
        inp.placeholder = t('valuePh').replace('{f}', activeField.label);
        dd.style.display = 'none';
        inp.focus();
      });
    });
  }

  function wireSmartFilter() {
    var inp = document.getElementById('scInput');
    var dd = document.getElementById('scDropdown');
    if (!inp) return;
    inp.addEventListener('focus', function () { if (!activeField) showDropdown(inp.value); });
    inp.addEventListener('input', function () { if (!activeField) showDropdown(inp.value); });
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (activeField && inp.value.trim()) {
          chips.push({ idx: activeField.idx, value: inp.value.trim() });
          activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
          renderChips(); reapplyChips();
        }
      } else if (e.key === 'Escape') {
        activeField = null; inp.value = ''; inp.placeholder = t('filterPh'); dd.style.display = 'none';
      }
    });
    document.addEventListener('click', function (e) {
      if (!document.getElementById('scSmartFilter').contains(e.target)) dd.style.display = 'none';
    });
    var clr = document.getElementById('scClearFilters');
    if (clr) clr.addEventListener('click', function () {
      chips = []; activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
      document.querySelectorAll('#swapchar-table .sc-col-filter').forEach(function (i) { i.value = ''; });
      renderChips(); reapplyChips();
    });
    inp.placeholder = t('filterPh');
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  // ── Reference date picker (MANDATORY: jQuery daterangepicker, dd/mm/yyyy) ───
  function wireDatePicker(attempt) {
    var inp = document.getElementById('sc-date');
    if (!inp) return;
    var startISO = page.getAttribute('data-ref-date');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#sc-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment(),
        maxDate: moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#scDateWrap .sc-cal-btn').on('click', function () { $d.trigger('click'); });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    if (startISO) { var p = startISO.split('-'); inp.value = p[2] + '/' + p[1] + '/' + p[0]; }
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireSmartFilter();
    wireDatePicker();
    load(page.getAttribute('data-ref-date'));
  });
})();

/**
 * Live Position › Option  (model: Live Position NDF)
 * Read-only view of the Option book from the DPOSICAO position file (columns
 * come from the server, including any dynamic "Média Asiática" date block).
 * Widgets are placeholders (to be defined per metric). Smart filter + per-column
 * filter + Columns/Export + Show entries + reference date, same as the NDF page.
 */
(function () {
  'use strict';

  var API = '/api/live-position-option/data';
  var page = document.getElementById('live-position-option-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // [{label, idx}]
  var activeField = null;      // smart-filter: column chosen, awaiting a value
  var chips = [];              // [{idx, value}]

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter by column…', valuePh: 'Type value for "{f}" + Enter', status: 'In Custody' },
    br: { filterPh: 'Filtrar por coluna…', valuePh: 'Digite o valor para "{f}" + Enter', status: 'Em Custódia' },
    es: { filterPh: 'Filtrar por columna…', valuePh: 'Escriba el valor para "{f}" + Enter', status: 'En Custodia' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  function load(dateStr) {
    fetch(API + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        var w = d.widgets || {};
        setVal('lo-w-a', w.a || 0); setVal('lo-w-b', w.b || 0);
        setVal('lo-w-c', w.c || 0); setVal('lo-w-total', w.total || 0);
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  function buildTable(columns, rows) {
    COLS = columns.map(function (label, i) { return { label: label, idx: i }; });

    var titleRow =
      '<tr id="lnopt-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="loCheckAll" class="form-check-input"></th>' +
      '<th data-lang="lo-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="ln-th-filter">' +
      '<th></th><th></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ln-col-filter" data-col="' +
          (i + 2) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#lnopt-table thead').innerHTML = titleRow + filterRow;

    var statusBadge = '<span class="badge bg-secondary-subtle text-secondary">' + esc(t('status')) + '</span>';
    var data = rows.map(function (r) {
      return ['<input type="checkbox" class="form-check-input ln-row-check">', statusBadge]
        .concat(r.map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#lnopt-table').DataTable({
      data: data,
      columns: [{}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [{ orderable: false, className: 'text-center', targets: 0 }],
      scrollX: false, autoWidth: false, orderCellsTop: true, deferRender: true,
      pageLength: 50, lengthMenu: [[25, 50, 100, 200, -1], [25, 50, 100, 200, 'All']], order: [],
      dom: "<'row'<'col-sm-12'tr>><'d-md-flex justify-content-between align-items-center mt-2'ip>",
      buttons: [{
        extend: 'collection',
        text: '<i class="ti ti-download me-1"></i> Export',
        className: 'btn btn-sm btn-info bg-gradient dropdown-toggle', autoClose: true,
        buttons: [
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: ':gt(1)', modifier: { page: 'all' } } },
        ],
      }],
    });

    var expWrap = document.querySelector('.loExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#lnopt-table thead').off('keyup.locol change.locol')
      .on('keyup.locol change.locol', '.ln-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('ln-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('lo-count', rows.length);
    buildColumnsToggle();
    var pl = document.querySelector('.ln-page-len');
    if (pl) pl.value = String(dt.page.len());
    reapplyChips();
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('loCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#lnopt-table tbody .ln-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim();
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="loCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="loCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="loColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('loColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  // ── Smart filter ───────────────────────────────────────────────────────────
  function reapplyChips() {
    if (!dt) return;
    dt.columns().every(function () { this.search(''); });
    document.querySelectorAll('#lnopt-table .ln-col-filter').forEach(function (inp) {
      if (inp.value) dt.column(+inp.getAttribute('data-col')).search(inp.value);
    });
    chips.forEach(function (c) { dt.column(c.idx + 2).search(c.value); });
    dt.draw();
  }

  function renderChips() {
    var box = document.getElementById('loChips');
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
    if (/valor|saldo|percentual|taxa|premio|prêmio|cota|strike|quantidade|barreira/.test(n)) return 'value';
    return 'text';
  }

  function showDropdown(term) {
    var dd = document.getElementById('loDropdown');
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
        var inp = document.getElementById('loInput');
        inp.value = ''; inp.placeholder = t('valuePh').replace('{f}', activeField.label);
        dd.style.display = 'none'; inp.focus();
      });
    });
  }

  function wireSmartFilter() {
    var inp = document.getElementById('loInput');
    var dd = document.getElementById('loDropdown');
    if (!inp) return;
    inp.addEventListener('focus', function () { if (!activeField) showDropdown(inp.value); });
    inp.addEventListener('input', function () { if (!activeField) showDropdown(inp.value); });
    function commit() {
      if (activeField && inp.value.trim()) {
        chips.push({ idx: activeField.idx, value: inp.value.trim() });
        activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
        renderChips(); reapplyChips(); dd.style.display = 'none';
      }
    }
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') { activeField = null; inp.value = ''; inp.placeholder = t('filterPh'); dd.style.display = 'none'; }
    });
    document.addEventListener('click', function (e) {
      if (!document.getElementById('loSmartFilter').contains(e.target)) dd.style.display = 'none';
    });
    var searchBtn = document.getElementById('loSearchBtn');
    if (searchBtn) searchBtn.addEventListener('click', commit);
    var clr = document.getElementById('loClearFilters');
    if (clr) clr.addEventListener('click', function () {
      chips = []; activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
      document.querySelectorAll('#lnopt-table .ln-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('ln-has-val'); });
      renderChips(); reapplyChips();
    });
    inp.placeholder = t('filterPh');
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function isoToDmy(iso) {
    if (!iso) return '';
    var p = String(iso).split('-');
    return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : '';
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('lo-date');
    if (!inp) return;
    var startISO = page.getAttribute('data-ref-date');
    // Always show the reference date (D-1 ANBIMA) up front — the picker's own
    // autoUpdateInput can't be relied on to write the field on init.
    if (startISO && !inp.value) inp.value = isoToDmy(startISO);
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      try {
        var $d = jQuery('#lo-date');
        $d.daterangepicker({
          singleDatePicker: true, autoApply: true, showDropdowns: true,
          autoUpdateInput: true, locale: { format: 'DD/MM/YYYY' },
          startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment(),
          maxDate: moment(),
        }, function (start) { inp.value = start.format('DD/MM/YYYY'); load(start.format('YYYY-MM-DD')); });
        if (startISO) inp.value = isoToDmy(startISO);   // ensure it's visible even if the plugin skips it
        jQuery('#loDateWrap .ln-cal-btn').on('click', function () { $d.trigger('click'); });
        return;
      } catch (e) { /* fall through to the plain-input fallback */ }
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  function wirePageLen() {
    var sel = document.querySelector('.ln-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    // Load the table FIRST so a datepicker/plugin hiccup can never block the data.
    load(page.getAttribute('data-ref-date'));
    try { wireSmartFilter(); } catch (e) {}
    try { wirePageLen(); } catch (e) {}
    try { wireDatePicker(); } catch (e) {}
  });
})();

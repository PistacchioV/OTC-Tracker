/**
 * Live Position › NDF  (model: Live Position Swap Characteristics)
 * Read-only view of the NDF book from the DPOSICAO-TER position file (columns
 * come from the server, including the dynamic "Média Asiática" date block).
 * Widgets: Vanilla / Other Publisher / T+0 (NDF Summary classification, no
 * maturity filter) + Commodities (Classe do Ativo Subjacente = Commodities) +
 * Total (live-position row count). Smart filter + per-column
 * filter + Columns/Export + Show entries + reference date, same as the Swap page.
 */
(function () {
  'use strict';

  // dd/mm/yyyy chronological sort — DataTables orders strings by default, so date
  // columns were sorted as text (by day). This type detector makes any date column
  // sort oldest↔newest correctly on header click.
  if (jQuery.fn.dataTable && !jQuery.fn.dataTable.ext.type.order['date-dmy-pre']) {
    var _DMY = /^(\d{2})\/(\d{2})\/(\d{4})$/;
    jQuery.fn.dataTable.ext.type.detect.unshift(function (d) {
      if (d === null || d === '') return 'date-dmy';
      return (typeof d === 'string' && _DMY.test(d.trim())) ? 'date-dmy' : null;
    });
    jQuery.fn.dataTable.ext.type.order['date-dmy-pre'] = function (d) {
      var m = String(d == null ? '' : d).trim().match(_DMY);
      return m ? (+m[3]) * 10000 + (+m[2]) * 100 + (+m[1]) : 0;
    };
  }

  var API = '/api/live-position-ndf/data';
  var page = document.getElementById('live-position-ndf-page');
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
        setVal('ln-w-vanilla', w.vanilla || 0); setVal('ln-w-other', w.other_publisher || 0);
        setVal('ln-w-t0', w.t0 || 0); setVal('ln-w-commodities', w.commodities || 0);
        setVal('ln-w-total', w.total || 0);
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  function buildTable(columns, rows) {
    COLS = columns.map(function (label, i) { return { label: label, idx: i }; });

    var titleRow =
      '<tr id="lnndf-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="lnCheckAll" class="form-check-input"></th>' +
      '<th data-lang="ln-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="ln-th-filter">' +
      '<th></th><th></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ln-col-filter" data-col="' +
          (i + 2) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#lnndf-table thead').innerHTML = titleRow + filterRow;

    var statusBadge = '<span class="badge bg-secondary-subtle text-secondary">' + esc(t('status')) + '</span>';
    var data = rows.map(function (r) {
      return ['<input type="checkbox" class="form-check-input ln-row-check">', statusBadge]
        .concat(r.map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#lnndf-table').DataTable({
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

    var expWrap = document.querySelector('.lnExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#lnndf-table thead').off('keyup.lncol change.lncol')
      .on('keyup.lncol change.lncol', '.ln-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('ln-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('ln-count', rows.length);
    buildColumnsToggle();
    var pl = document.querySelector('.ln-page-len');
    if (pl) pl.value = String(dt.page.len());
    reapplyChips();
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('lnCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#lnndf-table tbody .ln-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim();
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="lnCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="lnCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="lnColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('lnColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  // ── Smart filter ───────────────────────────────────────────────────────────
  function reapplyChips() {
    if (!dt) return;
    dt.columns().every(function () { this.search(''); });
    document.querySelectorAll('#lnndf-table .ln-col-filter').forEach(function (inp) {
      if (inp.value) dt.column(+inp.getAttribute('data-col')).search(inp.value);
    });
    chips.forEach(function (c) { dt.column(c.idx + 2).search(c.value); });
    dt.draw();
  }

  function renderChips() {
    var box = document.getElementById('lnChips');
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
    if (/valor|saldo|percentual|taxa|premio|prêmio|cota/.test(n)) return 'value';
    return 'text';
  }

  function showDropdown(term) {
    var dd = document.getElementById('lnDropdown');
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
        var inp = document.getElementById('lnInput');
        inp.value = ''; inp.placeholder = t('valuePh').replace('{f}', activeField.label);
        dd.style.display = 'none'; inp.focus();
      });
    });
  }

  function wireSmartFilter() {
    var inp = document.getElementById('lnInput');
    var dd = document.getElementById('lnDropdown');
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
      if (!document.getElementById('lnSmartFilter').contains(e.target)) dd.style.display = 'none';
    });
    var searchBtn = document.getElementById('lnSearchBtn');
    if (searchBtn) searchBtn.addEventListener('click', commit);
    var clr = document.getElementById('lnClearFilters');
    if (clr) clr.addEventListener('click', function () {
      chips = []; activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
      document.querySelectorAll('#lnndf-table .ln-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('ln-has-val'); });
      renderChips(); reapplyChips();
    });
    inp.placeholder = t('filterPh');
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('ln-date');
    if (!inp) return;
    var startISO = page.getAttribute('data-ref-date');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#ln-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment(),
        maxDate: moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#lnDateWrap .ln-cal-btn').on('click', function () { $d.trigger('click'); });
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

  function wirePageLen() {
    var sel = document.querySelector('.ln-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireSmartFilter();
    wirePageLen();
    wireDatePicker();
    load(page.getAttribute('data-ref-date'));
  });
})();

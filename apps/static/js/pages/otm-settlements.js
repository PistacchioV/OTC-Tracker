/**
 * Other Products › OTM Settlements
 * Imports the cashflows_*.xlsx (server-side, replacing the legacy VBA macro) and
 * shows the cleaned rows in a wide table with widgets, per-column filter, Columns
 * and Export. Settlement date defaults to today; the JSON is written per-day.
 */
(function () {
  'use strict';

  var API = '/api/otm-settlements/data';
  var IMPORT_API = '/api/otm-settlements/import';
  var page = document.getElementById('otm-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // current data columns (for the Add-row modal)
  var BREAK_IDX = 17;          // "Break Reason" is the last of the 18 data columns
  var ACTIONS_HTML = '<button class="btn btn-sm btn-icon btn-ghost-secondary" type="button" title="Details"><i class="ti ti-dots"></i></button>';

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter…', ok: 'OK', brk: 'Break', importing: 'Importing…',
          noFile: 'No cashflows file found in the source folder.', imported: 'Imported', rows: 'row(s)', updated: 'Updated' },
    br: { filterPh: 'Filtrar…', ok: 'OK', brk: 'Break', importing: 'Importando…',
          noFile: 'Nenhum arquivo cashflows na pasta de origem.', imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado' },
    es: { filterPh: 'Filtrar…', ok: 'OK', brk: 'Break', importing: 'Importando…',
          noFile: 'Ningún archivo cashflows en la carpeta de origen.', imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado' },
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
        setVal('otm-w-rates', w.rates || 0); setVal('otm-w-equities', w.equities || 0);
        setVal('otm-w-commodities', w.commodities || 0); setVal('otm-w-total', w.total || 0);
        setVal('otm-updated', d.updated ? (t('updated') + ' ' + d.updated) : '');
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  function statusBadge(breakReason) {
    if (breakReason && String(breakReason).trim()) {
      return '<span class="badge bg-danger-subtle text-danger">' + esc(t('brk')) + '</span>';
    }
    return '<span class="badge bg-success-subtle text-success">' + esc(t('ok')) + '</span>';
  }

  function buildTable(columns, rows) {
    COLS = columns;
    // Header: checkbox, actions, status, then the server columns + filter row.
    var titleRow =
      '<tr id="otm-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="otmCheckAll" class="form-check-input"></th>' +
      '<th data-lang="otm-actions">Actions</th>' +
      '<th data-lang="otm-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="otm-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm otm-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm otm-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#otm-table thead').innerHTML = titleRow + filterRow;

    var actionsCell = ACTIONS_HTML;
    var data = rows.map(function (r) {
      return ['<input type="checkbox" class="form-check-input otm-row-check">', actionsCell, statusBadge(r[BREAK_IDX])]
        .concat(r.map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#otm-table').DataTable({
      data: data,
      columns: [{}, {}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [
        { orderable: false, className: 'text-center', targets: 0 },
        { orderable: false, searchable: false, className: 'text-center', targets: 1 },
      ],
      // No scrollX: one table → header/body never misalign; .table-responsive scrolls.
      scrollX: false, autoWidth: false, orderCellsTop: true, deferRender: true,
      pageLength: 200, order: [],
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

    var expWrap = document.querySelector('.otmExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#otm-table thead').off('keyup.otmcol change.otmcol')
      .on('keyup.otmcol change.otmcol', '.otm-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('otm-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('otm-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.otm-page-len');   // sync "Show entries" to current length
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('otmCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#otm-table tbody .otm-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="otmCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="otmCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="otmColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('otmColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireClear() {
    var clr = document.getElementById('otmClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#otm-table .otm-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('otm-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  function currentDate() {
    var inp = document.getElementById('otm-date');
    if (window.jQuery && jQuery('#otm-date').data && jQuery('#otm-date').data('daterangepicker')) {
      return jQuery('#otm-date').data('daterangepicker').startDate.format('YYYY-MM-DD');
    }
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-today');
  }

  function wireImport() {
    var btn = document.getElementById('otmImportBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var info = document.getElementById('otm-import-info');
      btn.disabled = true; if (info) info.textContent = t('importing');
      fetch(IMPORT_API, { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          if (d && d.success) {
            if (info) info.textContent = t('imported') + ': ' + d.rows + ' ' + t('rows') + ' · ' + d.file;
            // Import always writes today's JSON — sync the picker to today then load.
            if (window.jQuery && jQuery('#otm-date').data('daterangepicker')) {
              jQuery('#otm-date').data('daterangepicker').setStartDate(moment(d.date, 'YYYY-MM-DD'));
            }
            load(d.date);
            if (window.Swal) Swal.fire({ icon: 'success', title: t('imported'), text: d.rows + ' ' + t('rows'), timer: 1800, showConfirmButton: false });
          } else {
            var msg = (d && d.error) || t('noFile');
            if (info) info.textContent = msg;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'OTM', text: msg });
          }
          if (window.fetchNotifications) window.fetchNotifications();
        })
        .catch(function () { btn.disabled = false; });
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('otm-date');
    if (!inp) return;
    var today = page.getAttribute('data-today');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#otm-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: today ? moment(today, 'YYYY-MM-DD') : moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#otmDateWrap .otm-cal-btn').on('click', function () { $d.trigger('click'); });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    if (today) { var p = today.split('-'); inp.value = p[2] + '/' + p[1] + '/' + p[0]; }
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  function wirePageLen() {
    var sel = document.querySelector('.otm-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  // Add row → modal with a field per column (New Deals pattern).
  function wireAddRow() {
    var btn = document.getElementById('otmAddBtn');
    if (btn) btn.addEventListener('click', function () {
      document.getElementById('otmAddFields').innerHTML = COLS.map(function (c, i) {
        return '<div class="col-md-4"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
          '<input type="text" class="form-control form-control-sm otm-add-fld" data-i="' + i + '"></div>';
      }).join('');
      if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('otmAddModal')).show();
    });
    var save = document.getElementById('otmAddSave');
    if (save) save.addEventListener('click', function () {
      if (!dt) return;
      var row = ['<input type="checkbox" class="form-check-input otm-row-check">', ACTIONS_HTML, statusBadge('')];
      document.querySelectorAll('#otmAddFields .otm-add-fld').forEach(function (f) { row.push(esc(f.value)); });
      dt.row.add(row).draw(false);
      setVal('otm-count', dt.rows().count());
      if (window.bootstrap) bootstrap.Modal.getInstance(document.getElementById('otmAddModal')).hide();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireClear();
    wireImport();
    wirePageLen();
    wireAddRow();
    wireDatePicker();
    load(page.getAttribute('data-today'));
  });
})();

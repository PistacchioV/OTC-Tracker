/**
 * Operations B3
 * Imports the B3 "Operações" file (server-side), keeps the reporting columns and
 * shows them in a wide table with widgets, per-column filter, Columns and Export.
 * The date defaults to today; the JSON is written per-day. The "last updated"
 * timestamp comes from row 2 col A of the source file (extraction time).
 * Widgets A/B/C are placeholders — to be defined per metric.
 */
(function () {
  'use strict';

  var API = '/api/operations-b3/data';
  var IMPORT_API = '/api/operations-b3/import';
  var page = document.getElementById('operations-b3-page');
  if (!page) return;

  var dt = null;

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { status: 'New', importing: 'Importing…', noFile: 'No Operações file found in the source folder.',
          imported: 'Imported', rows: 'row(s)', updated: 'Updated' },
    br: { status: 'New', importing: 'Importando…', noFile: 'Nenhum arquivo Operações na pasta de origem.',
          imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado' },
    es: { status: 'New', importing: 'Importando…', noFile: 'Ningún archivo Operações en la carpeta de origen.',
          imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  // Dynamic breakdown widgets: header total + one sub-line per distinct value.
  function renderSubs(containerId, block, iconClass) {
    var el = document.getElementById(containerId);
    if (!el) return;
    var items = (block && block.items) || [];
    el.innerHTML = items.map(function (it) {
      return '<div class="ob-widget__sub"><i class="ti ti-point-filled ' + iconClass + '"></i>' +
        '<span>' + esc(it.label) + '</span><span class="ob-sub-val">' + it.count + '</span></div>';
    }).join('');
  }

  function renderWidgets(w) {
    var op = w.tipo_operacao || {}, ti = w.tipo_titulo || {}, mo = w.modalidade || {};
    setVal('ob-w-tipoop-total', op.total || 0);
    setVal('ob-w-tipotit-total', ti.total || 0);
    setVal('ob-w-modliq-total', mo.total || 0);
    setVal('ob-w-total', w.total || 0);
    renderSubs('ob-subs-tipoop', op, 'text-primary');
    renderSubs('ob-subs-tipotit', ti, 'text-info');
    renderSubs('ob-subs-modliq', mo, 'text-warning');
  }

  function load(dateStr) {
    fetch(API + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        renderWidgets(d.widgets || {});
        setVal('ob-updated', d.updated ? (t('updated') + ' ' + d.updated) : '');
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  function buildTable(columns, rows) {
    var titleRow =
      '<tr id="opb3-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="obCheckAll" class="form-check-input"></th>' +
      '<th data-lang="ob-actions">Actions</th>' +
      '<th data-lang="ob-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="ob-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm ob-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ob-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#opb3-table thead').innerHTML = titleRow + filterRow;

    var actionsCell = '<button class="btn btn-sm btn-icon btn-ghost-secondary" type="button" title="Details"><i class="ti ti-dots"></i></button>';
    var statusBadge = '<span class="badge bg-secondary-subtle text-secondary">' + esc(t('status')) + '</span>';
    var data = rows.map(function (r) {
      return ['<input type="checkbox" class="form-check-input ob-row-check">', actionsCell, statusBadge]
        .concat(r.map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#opb3-table').DataTable({
      data: data,
      columns: [{}, {}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [
        { orderable: false, className: 'text-center', targets: 0 },
        { orderable: false, searchable: false, className: 'text-center', targets: 1 },
      ],
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

    var expWrap = document.querySelector('.obExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#opb3-table thead').off('keyup.obcol change.obcol')
      .on('keyup.obcol change.obcol', '.ob-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('ob-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('ob-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.ob-page-len');
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('obCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#opb3-table tbody .ob-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="obCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="obCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="obColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('obColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireClear() {
    var clr = document.getElementById('obClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#opb3-table .ob-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('ob-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  function wireImport() {
    var btn = document.getElementById('obImportBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var info = document.getElementById('ob-import-info');
      btn.disabled = true; if (info) info.textContent = t('importing');
      fetch(IMPORT_API, { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          if (d && d.success) {
            if (info) info.textContent = t('imported') + ': ' + d.rows + ' ' + t('rows') + ' · ' + d.file;
            if (window.jQuery && jQuery('#ob-date').data('daterangepicker')) {
              jQuery('#ob-date').data('daterangepicker').setStartDate(moment(d.date, 'YYYY-MM-DD'));
            }
            load(d.date);
            if (window.Swal) Swal.fire({ icon: 'success', title: t('imported'), text: d.rows + ' ' + t('rows'), timer: 1800, showConfirmButton: false });
          } else {
            var msg = (d && d.error) || t('noFile');
            if (info) info.textContent = msg;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'Operations B3', text: msg });
          }
          if (window.fetchNotifications) window.fetchNotifications();
        })
        .catch(function () { btn.disabled = false; });
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('ob-date');
    if (!inp) return;
    var today = page.getAttribute('data-today');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#ob-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: today ? moment(today, 'YYYY-MM-DD') : moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#obDateWrap .ob-cal-btn').on('click', function () { $d.trigger('click'); });
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
    var sel = document.querySelector('.ob-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireClear();
    wireImport();
    wirePageLen();
    wireDatePicker();
    load(page.getAttribute('data-today'));
  });
})();

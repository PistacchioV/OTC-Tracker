/**
 * Other Products › Option › Cognos (FXO Detail - Beta)
 * Imports the cashflows_*.xlsx (server-side, replacing the legacy VBA macro) and
 * shows the cleaned rows in a wide table with widgets, per-column filter, Columns
 * and Export. Settlement date defaults to today; the JSON is written per-day.
 */
(function () {
  'use strict';

  // ':gt(1)' NÃO serve aqui: o thead tem duas linhas (títulos + filtros), o jQuery
  // enumera 2×N <th> e os das colunas 0/1 da segunda linha caem em posição > 1,
  // devolvendo checkbox e Actions para a exportação. Índice de COLUNA, então.
  function exportFromData(idx) { return idx > 1; }

  var API = '/api/cognos/data';
  var IMPORT_API = '/api/cognos/import';
  var page = document.getElementById('cog-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // current data columns (for the Add/Edit modal)
  var CURRENT_ROWS = [];       // last-loaded rows (each: [...18 data..., status, maker, checker, id])
  var EDIT_ID = null;          // id of the row being edited (null → Add mode)

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter…', ok: 'OK', pending: 'Pending', newst: 'New', importing: 'Importing…',
          noFile: 'No FXO Detail file found in the source folder.', imported: 'Imported', rows: 'row(s)', updated: 'Updated',
          edit: 'Edit', del: 'Delete', confirm: 'Confirm', addTitle: 'Add row', editTitle: 'Edit row',
          delTitle: 'Delete row?', delText: 'This row will be removed and the change saved.', yes: 'Yes, delete',
          cancel: 'Cancel', saved: 'Saved', deleted: 'Deleted', confirmed: 'Confirmed',
          sameUser: 'A different user must confirm a row you changed.', err: 'Action failed.' },
    br: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendente', newst: 'Novo', importing: 'Importando…',
          noFile: 'Nenhum arquivo FXO Detail na pasta de origem.', imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado',
          edit: 'Editar', del: 'Excluir', confirm: 'Confirmar', addTitle: 'Adicionar linha', editTitle: 'Editar linha',
          delTitle: 'Excluir linha?', delText: 'A linha será removida e a alteração salva.', yes: 'Sim, excluir',
          cancel: 'Cancelar', saved: 'Salvo', deleted: 'Excluído', confirmed: 'Confirmado',
          sameUser: 'Outro usuário precisa confirmar uma linha que você alterou.', err: 'Falha na ação.' },
    es: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendiente', newst: 'Nuevo', importing: 'Importando…',
          noFile: 'Ningún archivo FXO Detail en la carpeta de origen.', imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado',
          edit: 'Editar', del: 'Eliminar', confirm: 'Confirmar', addTitle: 'Agregar fila', editTitle: 'Editar fila',
          delTitle: '¿Eliminar fila?', delText: 'La fila será eliminada y el cambio guardado.', yes: 'Sí, eliminar',
          cancel: 'Cancelar', saved: 'Guardado', deleted: 'Eliminado', confirmed: 'Confirmado',
          sameUser: 'Otro usuario debe confirmar una fila que usted cambió.', err: 'Acción fallida.' },
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
        setVal('cog-w-call', w.call || 0); setVal('cog-w-put', w.put || 0);
        setVal('cog-w-total', w.total || 0);
        setVal('cog-updated', d.updated ? (t('updated') + ' ' + d.updated) : '');
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  // Standard status badge (project format): OK=success, Pending=warning, New=info.
  function statusBadge(status) {
    var s = String(status || 'OK').toLowerCase();
    if (s === 'pending') return '<span class="badge text-bg-warning bg-gradient">' + esc(t('pending')) + '</span>';
    if (s === 'new')     return '<span class="badge bg-info text-white bg-gradient">' + esc(t('newst')) + '</span>';
    return '<span class="badge text-bg-success bg-gradient">' + esc(t('ok')) + '</span>';
  }

  function metaOf(r) {
    var n = COLS.length;
    return { status: r[n], maker: r[n + 1], checker: r[n + 2], id: r[n + 3] };
  }

  // Action buttons — standard rounded-square format (global head-css) via btn-row-* classes.
  function actionsHtml(id) {
    return '<div class="d-inline-flex gap-1">' +
      '<button class="btn btn-info btn-sm rounded-circle btn-row-edit" data-id="' + esc(id) + '" title="' + esc(t('edit')) + '"><i class="ti ti-pencil"></i></button>' +
      '<button class="btn btn-success btn-sm rounded-circle btn-row-confirm" data-id="' + esc(id) + '" title="' + esc(t('confirm')) + '"><i class="ti ti-check"></i></button>' +
      '<button class="btn btn-danger btn-sm rounded-circle btn-row-delete" data-id="' + esc(id) + '" title="' + esc(t('del')) + '"><i class="ti ti-trash"></i></button>' +
      '</div>';
  }

  function buildTable(columns, rows) {
    COLS = columns;
    CURRENT_ROWS = rows;
    // Header: checkbox, actions, status, then the server columns + filter row.
    var titleRow =
      '<tr id="cog-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="cogCheckAll" class="form-check-input"></th>' +
      '<th data-lang="cog-actions">Actions</th>' +
      '<th data-lang="cog-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="cog-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm cog-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm cog-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#cog-table thead').innerHTML = titleRow + filterRow;

    var data = rows.map(function (r) {
      var m = metaOf(r);
      return ['<input type="checkbox" class="form-check-input cog-row-check">', actionsHtml(m.id), statusBadge(m.status)]
        .concat(r.slice(0, COLS.length).map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#cog-table').DataTable({
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
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
        ],
      }],
    });

    var expWrap = document.querySelector('.cogExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#cog-table thead').off('keyup.cogcol change.cogcol')
      .on('keyup.cogcol change.cogcol', '.cog-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('cog-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('cog-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.cog-page-len');   // sync "Show entries" to current length
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('cogCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#cog-table tbody .cog-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="cogCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="cogCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="cogColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('cogColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireClear() {
    var clr = document.getElementById('cogClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#cog-table .cog-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('cog-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  function currentDate() {
    var inp = document.getElementById('cog-date');
    if (window.jQuery && jQuery('#cog-date').data && jQuery('#cog-date').data('daterangepicker')) {
      return jQuery('#cog-date').data('daterangepicker').startDate.format('YYYY-MM-DD');
    }
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-today');
  }

  function wireImport() {
    var btn = document.getElementById('cogImportBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var info = document.getElementById('cog-import-info');
      btn.disabled = true; if (info) info.textContent = t('importing');
      fetch(IMPORT_API, { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          if (d && d.success) {
            if (info) info.textContent = t('imported') + ': ' + d.rows + ' ' + t('rows') + ' · ' + d.file;
            // Import always writes today's JSON — sync the picker to today then load.
            if (window.jQuery && jQuery('#cog-date').data('daterangepicker')) {
              jQuery('#cog-date').data('daterangepicker').setStartDate(moment(d.date, 'YYYY-MM-DD'));
            }
            load(d.date);
            if (window.Swal) Swal.fire({ icon: 'success', title: t('imported'), text: d.rows + ' ' + t('rows'), timer: 1800, showConfirmButton: false });
          } else {
            var msg = (d && d.error) || t('noFile');
            if (info) info.textContent = msg;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'Cognos', text: msg });
          }
          if (window.fetchNotifications) window.fetchNotifications();
        })
        .catch(function () { btn.disabled = false; });
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('cog-date');
    if (!inp) return;
    var today = page.getAttribute('data-today');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#cog-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: today ? moment(today, 'YYYY-MM-DD') : moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#cogDateWrap .cog-cal-btn').on('click', function () { $d.trigger('click'); });
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
    var sel = document.querySelector('.cog-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  // New Deals glass modal: a field per column. editId=null → Add; else Edit (prefilled).
  function openModal(editId, prefillCells) {
    EDIT_ID = editId || null;
    var title = document.getElementById('cogModalTitle');
    if (title) title.textContent = EDIT_ID ? t('editTitle') : t('addTitle');
    document.getElementById('cogAddFields').innerHTML = COLS.map(function (c, i) {
      var val = (prefillCells && prefillCells[i] != null) ? prefillCells[i] : '';
      return '<div class="col-md-4"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
        '<input type="text" class="form-control form-control-sm cog-add-fld" data-i="' + i + '" value="' + esc(val) + '"></div>';
    }).join('');
    if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('cogAddModal')).show();
  }

  function afterMutation(titleKey) {
    if (window.bootstrap) {
      var inst = bootstrap.Modal.getInstance(document.getElementById('cogAddModal'));
      if (inst) inst.hide();
    }
    load(currentDate());
    if (window.fetchNotifications) window.fetchNotifications();
    if (window.Swal) Swal.fire({ icon: 'success', title: t(titleKey), timer: 1200, showConfirmButton: false });
  }

  // Add row (or save edit) → persist to the day's JSON, then reload.
  function wireAddRow() {
    var btn = document.getElementById('cogAddBtn');
    if (btn) btn.addEventListener('click', function () { openModal(null, null); });
    var save = document.getElementById('cogAddSave');
    if (save) save.addEventListener('click', function () {
      var cells = [];
      document.querySelectorAll('#cogAddFields .cog-add-fld').forEach(function (f) { cells[+f.getAttribute('data-i')] = f.value; });
      var url = EDIT_ID ? '/api/cognos/row/edit' : '/api/cognos/row/add';
      var body = { date: currentDate(), cells: cells };
      if (EDIT_ID) body.id = EDIT_ID;
      save.disabled = true;
      postJSON(url, body).then(function (res) {
        save.disabled = false;
        if (res.ok && res.body && res.body.success) { afterMutation('saved'); }
        else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Cognos', text: (res.body && res.body.message) || t('err') }); }
      }).catch(function () { save.disabled = false; });
    });
  }

  // Edit / Confirm / Delete (delegated — survives DataTables redraws).
  function wireActions() {
    jQuery('#cog-table').off('click.cogact')
      .on('click.cogact', '.btn-row-edit', function () {
        var id = this.getAttribute('data-id');
        var row = CURRENT_ROWS.filter(function (r) { return String(metaOf(r).id) === String(id); })[0];
        openModal(id, row ? row.slice(0, COLS.length) : null);
      })
      .on('click.cogact', '.btn-row-confirm', function () {
        var id = this.getAttribute('data-id');
        postJSON('/api/cognos/row/confirm', { date: currentDate(), id: id }).then(function (res) {
          if (res.ok && res.body && res.body.success) { afterMutation('confirmed'); }
          else if (window.Swal) {
            var msg = (res.body && res.body.error === 'same_user') ? t('sameUser') : ((res.body && res.body.message) || t('err'));
            Swal.fire({ icon: 'warning', title: 'Cognos', text: msg });
          }
        });
      })
      .on('click.cogact', '.btn-row-delete', function () {
        var id = this.getAttribute('data-id');
        function doDelete() {
          postJSON('/api/cognos/row/delete', { date: currentDate(), id: id }).then(function (res) {
            if (res.ok && res.body && res.body.success) { afterMutation('deleted'); }
            else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Cognos', text: t('err') }); }
          });
        }
        if (window.Swal) {
          Swal.fire({ icon: 'warning', title: t('delTitle'), text: t('delText'), showCancelButton: true,
            confirmButtonText: t('yes'), cancelButtonText: t('cancel'), confirmButtonColor: '#dc3545' })
            .then(function (r) { if (r.isConfirmed) doDelete(); });
        } else { doDelete(); }
      });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireClear();
    wireImport();
    wirePageLen();
    wireAddRow();
    wireActions();
    wireDatePicker();
    load(page.getAttribute('data-today'));
  });
})();

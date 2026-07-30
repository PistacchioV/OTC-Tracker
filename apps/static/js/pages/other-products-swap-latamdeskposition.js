/**
 * Other Products › Latam Desk Position
 * Importa o FbiRptLatamDeskPostion-NY-* (server-side, no lugar da macro VBA) e
 * mostra as linhas filtradas em uma tabela larga com widgets, filtro por coluna,
 * Columns e Export.
 *
 * O relatório NÃO é diário: a página abre SEM data no request e o servidor
 * devolve o último arquivo disponível — o date picker é então sincronizado com a
 * data que veio. Escolher uma data no picker passa a pedir aquele dia exato.
 */
(function () {
  'use strict';

  var BASE = '/api/other-products-swap-latamdeskposition';
  var page = document.getElementById('ldp-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // colunas de dados atuais (para o modal Add/Edit)
  var CURRENT_ROWS = [];       // últimas linhas carregadas ([...dados, status, maker, checker, id])
  var EDIT_ID = null;          // id da linha em edição (null → modo Add)
  var LOADED_DATE = null;      // data efetivamente carregada (YYYY-MM-DD)
  var AVAILABLE = [];          // datas que têm arquivo, mais nova primeiro

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter…', ok: 'OK', pending: 'Pending', newst: 'New', importing: 'Importing…',
          noFile: 'No FbiRptLatamDeskPostion-NY-* file found in the Settlements folder.',
          imported: 'Imported', rows: 'row(s)', updated: 'Updated', latest: 'latest available',
          noData: 'No data for this date', lastAvailable: 'Last available',
          edit: 'Edit', del: 'Delete', confirm: 'Confirm', addTitle: 'Add row', editTitle: 'Edit row',
          delTitle: 'Delete row?', delText: 'This row will be removed and the change saved.', yes: 'Yes, delete',
          cancel: 'Cancel', saved: 'Saved', deleted: 'Deleted', confirmed: 'Confirmed',
          missing: 'Columns not found in the file header', filtered: 'filtered out',
          sameUser: 'A different user must confirm a row you changed.', err: 'Action failed.' },
    br: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendente', newst: 'Novo', importing: 'Importando…',
          noFile: 'Nenhum arquivo FbiRptLatamDeskPostion-NY-* na pasta Settlements.',
          imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado', latest: 'último disponível',
          noData: 'Sem dados nesta data', lastAvailable: 'Último disponível',
          edit: 'Editar', del: 'Excluir', confirm: 'Confirmar', addTitle: 'Adicionar linha', editTitle: 'Editar linha',
          delTitle: 'Excluir linha?', delText: 'A linha será removida e a alteração salva.', yes: 'Sim, excluir',
          cancel: 'Cancelar', saved: 'Salvo', deleted: 'Excluído', confirmed: 'Confirmado',
          missing: 'Colunas não encontradas no header do arquivo', filtered: 'filtradas',
          sameUser: 'Outro usuário precisa confirmar uma linha que você alterou.', err: 'Falha na ação.' },
    es: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendiente', newst: 'Nuevo', importing: 'Importando…',
          noFile: 'Ningún archivo FbiRptLatamDeskPostion-NY-* en la carpeta Settlements.',
          imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado', latest: 'último disponible',
          noData: 'Sin datos en esta fecha', lastAvailable: 'Último disponible',
          edit: 'Editar', del: 'Eliminar', confirm: 'Confirmar', addTitle: 'Agregar fila', editTitle: 'Editar fila',
          delTitle: '¿Eliminar fila?', delText: 'La fila será eliminada y el cambio guardado.', yes: 'Sí, eliminar',
          cancel: 'Cancelar', saved: 'Guardado', deleted: 'Eliminado', confirmed: 'Confirmado',
          missing: 'Columnas no encontradas en el encabezado', filtered: 'filtradas',
          sameUser: 'Otro usuario debe confirmar una fila que usted cambió.', err: 'Acción fallida.' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }
  function toDMY(iso) {
    var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? (m[3] + '/' + m[2] + '/' + m[1]) : '';
  }

  // dateStr null/undefined → pede o ÚLTIMO arquivo disponível (o relatório não é diário).
  function load(dateStr) {
    fetch(BASE + '/data' + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : ''),
          { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        var w = d.widgets || {};
        setVal('ldp-w-calls', w.calls || 0); setVal('ldp-w-puts', w.puts || 0);
        setVal('ldp-w-cptys', w.counterparties || 0); setVal('ldp-w-total', w.total || 0);
        LOADED_DATE = d.date || null;
        AVAILABLE = d.dates || [];
        // Nota do cabeçalho: hora do import, arquivo de origem e — quando a data não
        // foi escolhida pelo usuário — o aviso de que é o último arquivo disponível.
        var note = [];
        if (d.updated) note.push(t('updated') + ' ' + d.updated);
        if (d.file) note.push(d.file);
        if (d.latest) note.push('(' + t('latest') + ')');
        setVal('ldp-updated', note.join(' · '));
        syncPicker(d.date);
        buildTable(d.columns || [], d.rows || []);
        var info = document.getElementById('ldp-import-info');
        if (info && !(d.rows || []).length) {
          info.textContent = t('noData') + (AVAILABLE.length
            ? ' · ' + t('lastAvailable') + ': ' + toDMY(AVAILABLE[0]) : '');
        }
      })
      .catch(function () {});
  }

  // Status badge padrão do projeto: OK=success, Pending=warning, New=info.
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
    var titleRow =
      '<tr id="ldp-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="ldpCheckAll" class="form-check-input"></th>' +
      '<th data-lang="ldp-actions">Actions</th>' +
      '<th data-lang="ldp-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="ldp-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm ldp-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ldp-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#ldp-table thead').innerHTML = titleRow + filterRow;

    var data = rows.map(function (r) {
      var m = metaOf(r);
      return ['<input type="checkbox" class="form-check-input ldp-row-check">', actionsHtml(m.id), statusBadge(m.status)]
        .concat(r.slice(0, COLS.length).map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    // Ordenação padrão: Counterparty A→Z e, dentro da contraparte, Deal_ID A→Z.
    // Índices pelo nome (+3 pelas colunas fixas checkbox/actions/status).
    var iCpty = columns.indexOf('Counterparty');
    var iDeal = columns.indexOf('Deal_ID');
    var defaultOrder = [];
    if (iCpty >= 0) defaultOrder.push([iCpty + 3, 'asc']);
    if (iDeal >= 0) defaultOrder.push([iDeal + 3, 'asc']);
    dt = jQuery('#ldp-table').DataTable({
      data: data,
      columns: [{}, {}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [
        { orderable: false, className: 'text-center', targets: 0 },
        { orderable: false, searchable: false, className: 'text-center', targets: 1 },
      ],
      // Sem scrollX: uma tabela só → header e corpo nunca desalinham; .table-responsive rola.
      scrollX: false, autoWidth: false, orderCellsTop: true, deferRender: true,
      pageLength: 200, order: defaultOrder,
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

    var expWrap = document.querySelector('.ldpExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#ldp-table thead').off('keyup.ldpcol change.ldpcol')
      .on('keyup.ldpcol change.ldpcol', '.ldp-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('ldp-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('ldp-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.ldp-page-len');   // sincroniza "Show entries"
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('ldpCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#ldp-table tbody .ldp-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="ldpCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="ldpCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="ldpColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('ldpColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireClear() {
    var clr = document.getElementById('ldpClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#ldp-table .ldp-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('ldp-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  // Data carregada (não a de hoje): é ela que as ações de linha precisam usar.
  function currentDate() {
    if (LOADED_DATE) return LOADED_DATE;
    var inp = document.getElementById('ldp-date');
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-ref');
  }

  function syncPicker(iso) {
    if (!iso) return;
    if (window.jQuery && jQuery('#ldp-date').data && jQuery('#ldp-date').data('daterangepicker')) {
      jQuery('#ldp-date').data('daterangepicker').setStartDate(moment(iso, 'YYYY-MM-DD'));
      jQuery('#ldp-date').val(toDMY(iso));
      return;
    }
    var inp = document.getElementById('ldp-date');
    if (inp) inp.value = toDMY(iso);
  }

  function wireImport() {
    var btn = document.getElementById('ldpImportBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var info = document.getElementById('ldp-import-info');
      btn.disabled = true; if (info) info.textContent = t('importing');
      // Sem 'date' no corpo: o import grava na data de HOJE (o dia em que o
      // arquivo foi processado) e a página passa a mostrar esse arquivo.
      fetch(BASE + '/import', { method: 'POST', credentials: 'same-origin',
                                headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          if (d && d.success) {
            var txt = t('imported') + ': ' + d.rows + ' ' + t('rows') +
                      ' · ' + (d.filtered || 0) + ' ' + t('filtered') + ' · ' + d.file;
            if (info) info.textContent = txt;
            load(d.date);
            if (window.Swal) {
              var html = d.rows + ' ' + t('rows') + '<br><small>' + esc(d.file) + '</small>';
              if (d.missing && d.missing.length) {
                html += '<br><br><small class="text-warning">' + esc(t('missing')) + ':<br>' +
                        esc(d.missing.join(', ')) + '</small>';
              }
              Swal.fire({ icon: (d.missing && d.missing.length) ? 'warning' : 'success',
                          title: t('imported'), html: html,
                          timer: (d.missing && d.missing.length) ? undefined : 2200,
                          showConfirmButton: !!(d.missing && d.missing.length) });
            }
          } else {
            var msg = (d && d.error) || t('noFile');
            if (info) info.textContent = msg;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'Latam Desk Position', text: msg });
          }
          if (window.fetchNotifications) window.fetchNotifications();
        })
        .catch(function () { btn.disabled = false; });
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('ldp-date');
    if (!inp) return;
    var ref = page.getAttribute('data-ref') || page.getAttribute('data-today');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#ldp-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: ref ? moment(ref, 'YYYY-MM-DD') : moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#ldpDateWrap .ldp-cal-btn').on('click', function () { $d.trigger('click'); });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    if (ref) inp.value = toDMY(ref);
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  function wirePageLen() {
    var sel = document.querySelector('.ldp-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  // Modal glass do New Deals: um campo por coluna. editId=null → Add; senão Edit.
  function openModal(editId, prefillCells) {
    EDIT_ID = editId || null;
    var title = document.getElementById('ldpModalTitle');
    if (title) title.textContent = EDIT_ID ? t('editTitle') : t('addTitle');
    document.getElementById('ldpAddFields').innerHTML = COLS.map(function (c, i) {
      var val = (prefillCells && prefillCells[i] != null) ? prefillCells[i] : '';
      return '<div class="col-md-3"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
        '<input type="text" class="form-control form-control-sm ldp-add-fld" data-i="' + i + '" value="' + esc(val) + '"></div>';
    }).join('');
    if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('ldpAddModal')).show();
  }

  function afterMutation(titleKey) {
    if (window.bootstrap) {
      var inst = bootstrap.Modal.getInstance(document.getElementById('ldpAddModal'));
      if (inst) inst.hide();
    }
    load(currentDate());
    if (window.fetchNotifications) window.fetchNotifications();
    if (window.Swal) Swal.fire({ icon: 'success', title: t(titleKey), timer: 1200, showConfirmButton: false });
  }

  function wireAddRow() {
    var btn = document.getElementById('ldpAddBtn');
    if (btn) btn.addEventListener('click', function () { openModal(null, null); });
    var save = document.getElementById('ldpAddSave');
    if (save) save.addEventListener('click', function () {
      var cells = [];
      document.querySelectorAll('#ldpAddFields .ldp-add-fld').forEach(function (f) { cells[+f.getAttribute('data-i')] = f.value; });
      var url = BASE + (EDIT_ID ? '/row/edit' : '/row/add');
      var body = { date: currentDate(), cells: cells };
      if (EDIT_ID) body.id = EDIT_ID;
      save.disabled = true;
      postJSON(url, body).then(function (res) {
        save.disabled = false;
        if (res.ok && res.body && res.body.success) { afterMutation('saved'); }
        else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Latam Desk Position', text: (res.body && res.body.message) || t('err') }); }
      }).catch(function () { save.disabled = false; });
    });
  }

  // Edit / Confirm / Delete (delegado — sobrevive aos redraws do DataTables).
  function wireActions() {
    jQuery('#ldp-table').off('click.ldpact')
      .on('click.ldpact', '.btn-row-edit', function () {
        var id = this.getAttribute('data-id');
        var row = CURRENT_ROWS.filter(function (r) { return String(metaOf(r).id) === String(id); })[0];
        openModal(id, row ? row.slice(0, COLS.length) : null);
      })
      .on('click.ldpact', '.btn-row-confirm', function () {
        var id = this.getAttribute('data-id');
        postJSON(BASE + '/row/confirm', { date: currentDate(), id: id }).then(function (res) {
          if (res.ok && res.body && res.body.success) { afterMutation('confirmed'); }
          else if (window.Swal) {
            var msg = (res.body && res.body.error === 'same_user') ? t('sameUser') : ((res.body && res.body.message) || t('err'));
            Swal.fire({ icon: 'warning', title: 'Latam Desk Position', text: msg });
          }
        });
      })
      .on('click.ldpact', '.btn-row-delete', function () {
        var id = this.getAttribute('data-id');
        function doDelete() {
          postJSON(BASE + '/row/delete', { date: currentDate(), id: id }).then(function (res) {
            if (res.ok && res.body && res.body.success) { afterMutation('deleted'); }
            else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Latam Desk Position', text: t('err') }); }
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
    load(null);          // sem data → servidor devolve o último arquivo disponível
  });
})();

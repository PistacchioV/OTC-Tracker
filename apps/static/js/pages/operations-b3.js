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

  // ':gt(1)' NÃO serve aqui: o thead tem duas linhas (títulos + filtros), o jQuery
  // enumera 2×N <th> e os das colunas 0/1 da segunda linha caem em posição > 1,
  // devolvendo checkbox e Actions para a exportação. Índice de COLUNA, então.
  function exportFromData(idx) { return idx > 1; }

  var API = '/api/operations-b3/data';
  var IMPORT_API = '/api/operations-b3/import';
  var page = document.getElementById('operations-b3-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // current data columns (for the Add/Edit modal)
  var CURRENT_ROWS = [];       // last-loaded rows (each: [...data..., status, maker, checker, id])
  var EDIT_ID = null;          // id of the row being edited (null → Add mode)
  // Linhas marcadas. Vive fora da tabela porque o DataTables recria o HTML das
  // células a cada draw (paginação/filtro), o que perderia o `checked`. Só serve
  // à Mensageria: destrava a REgeração das linhas já com status Generated.
  var SELECTED = Object.create(null);

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { ok: 'OK', pending: 'Pending', newst: 'New', importing: 'Importing…',
          noFile: 'No Operações file found in the source folder.',
          imported: 'Imported', rows: 'row(s)', updated: 'Updated',
          edit: 'Edit', del: 'Delete', confirm: 'Confirm', addTitle: 'Add row', editTitle: 'Edit row',
          delTitle: 'Delete row?', delText: 'This row will be removed and the change saved.', yes: 'Yes, delete',
          cancel: 'Cancel', saved: 'Saved', deleted: 'Deleted', confirmed: 'Confirmed',
          sameUser: 'A different user must confirm a row you changed.', err: 'Action failed.',
          generated: 'Generated', msgTitle: 'Generate mensageria e-mails?',
          msgText: 'Drafts will be generated for the Bilateral/Bruta operations not yet generated. Rows already marked as Generated are only included when their checkbox is ticked.',
          msgTextSel: 'Drafts will be generated for the Bilateral/Bruta operations not yet generated, plus the {n} ticked row(s).',
          msgYes: 'Yes, generate' },
    br: { ok: 'OK', pending: 'Pendente', newst: 'Novo', importing: 'Importando…',
          noFile: 'Nenhum arquivo Operações na pasta de origem.',
          imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado',
          edit: 'Editar', del: 'Excluir', confirm: 'Confirmar', addTitle: 'Adicionar linha', editTitle: 'Editar linha',
          delTitle: 'Excluir linha?', delText: 'A linha será removida e a alteração salva.', yes: 'Sim, excluir',
          cancel: 'Cancelar', saved: 'Salvo', deleted: 'Excluído', confirmed: 'Confirmado',
          sameUser: 'Outro usuário precisa confirmar uma linha que você alterou.', err: 'Falha na ação.',
          generated: 'Gerado', msgTitle: 'Gerar os e-mails de mensageria?',
          msgText: 'Serão gerados drafts das operações Bilateral/Bruta ainda não geradas. Linhas já com status Gerado só entram com o checkbox marcado.',
          msgTextSel: 'Serão gerados drafts das operações Bilateral/Bruta ainda não geradas, mais a(s) {n} linha(s) marcada(s).',
          msgYes: 'Sim, gerar' },
    es: { ok: 'OK', pending: 'Pendiente', newst: 'Nuevo', importing: 'Importando…',
          noFile: 'Ningún archivo Operações en la carpeta de origen.',
          imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado',
          edit: 'Editar', del: 'Eliminar', confirm: 'Confirmar', addTitle: 'Agregar fila', editTitle: 'Editar fila',
          delTitle: '¿Eliminar fila?', delText: 'La fila será eliminada y el cambio guardado.', yes: 'Sí, eliminar',
          cancel: 'Cancelar', saved: 'Guardado', deleted: 'Eliminado', confirmed: 'Confirmado',
          sameUser: 'Otro usuario debe confirmar una fila que usted cambió.', err: 'Acción fallida.',
          generated: 'Generado', msgTitle: '¿Generar los correos de mensajería?',
          msgText: 'Se generarán borradores de las operaciones Bilateral/Bruta aún no generadas. Las filas ya marcadas como Generado solo entran con su casilla tildada.',
          msgTextSel: 'Se generarán borradores de las operaciones Bilateral/Bruta aún no generadas, más la(s) {n} fila(s) tildada(s).',
          msgYes: 'Sí, generar' },
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

  // Standard status badge (project format): OK=success, Pending=warning, New=info,
  // Generated=primary (linha que já virou e-mail de mensageria).
  function statusBadge(status) {
    var s = String(status || 'New').toLowerCase();
    if (s === 'pending')   return '<span class="badge text-bg-warning bg-gradient">' + esc(t('pending')) + '</span>';
    if (s === 'ok')        return '<span class="badge text-bg-success bg-gradient">' + esc(t('ok')) + '</span>';
    if (s === 'generated') return '<span class="badge text-bg-primary bg-gradient">' + esc(t('generated')) + '</span>';
    return '<span class="badge bg-info text-white bg-gradient">' + esc(t('newst')) + '</span>';
  }

  function metaOf(r) {
    var n = COLS.length;
    return { status: r[n], maker: r[n + 1], checker: r[n + 2], id: r[n + 3] };
  }

  // Action buttons — standard rounded-square format via btn-row-* classes.
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
      '<tr id="opb3-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="obCheckAll" class="form-check-input"></th>' +
      '<th data-lang="ob-actions">Actions</th>' +
      '<th data-lang="ob-status">Status</th>' +
      columns.map(function (c) {
        // Coluna derivada Type (match do Título × Live Position): inglês default + i18n.
        if (c === 'Type') return '<th data-lang="ob-col-type">Type</th>';
        // O "Status" que vem do arquivo é o da B3 — o da terceira coluna é o
        // maker/checker da página. Renomeado para não confundir os dois.
        if (c === 'Status') return '<th data-lang="ob-col-status-b3">Status B3</th>';
        return '<th>' + esc(c) + '</th>';
      }).join('') + '</tr>';
    var filterRow =
      '<tr class="ob-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm ob-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ob-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c === 'Status' ? 'Status B3' : c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#opb3-table thead').innerHTML = titleRow + filterRow;

    SELECTED = Object.create(null);          // dados novos → seleção antiga não vale mais
    var data = rows.map(function (r) {
      var m = metaOf(r);
      return ['<input type="checkbox" class="form-check-input ob-row-check" data-id="' + esc(m.id) + '">',
              actionsHtml(m.id), statusBadge(m.status)]
        .concat(r.slice(0, COLS.length).map(function (v) { return esc(v); }));
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
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
        ],
      }],
    });

    // Seleção de célula + Ctrl+C — o padrão do New Deals para qualquer tabela
    // (static/js/table-std.js). Fora da seleção: checkbox e Actions. O helper é
    // idempotente e delega no nó da tabela, então sobrevive aos redraws e ao
    // rebuild que este `buildTable` faz a cada carga.
    if (window.otcCellCopy) otcCellCopy('#opb3-table', { skip: [0, 1] });
    // Item Advanced do menu Export — opt-in como o otcCellCopy: onde o
    // export-advanced.js não estiver carregado, é um no-op.
    if (window.otcExportAdvanced) window.otcExportAdvanced('#opb3-table');

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

    // Seleção fora da tabela: guarda o id no change e repõe o `checked` a cada
    // draw (o DataTables recria a célula a partir do HTML original).
    jQuery('#opb3-table tbody').off('change.obsel')
      .on('change.obsel', '.ob-row-check', function () {
        var id = this.getAttribute('data-id');
        if (this.checked) SELECTED[id] = true; else delete SELECTED[id];
      });
    jQuery('#opb3-table').off('draw.obsel').on('draw.obsel', function () {
      document.querySelectorAll('#opb3-table tbody .ob-row-check').forEach(function (c) {
        c.checked = !!SELECTED[c.getAttribute('data-id')];
      });
    });

    var checkAll = document.getElementById('obCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#opb3-table tbody .ob-row-check').forEach(function (c) {
        c.checked = checkAll.checked;
        var id = c.getAttribute('data-id');
        if (checkAll.checked) SELECTED[id] = true; else delete SELECTED[id];
      });
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

  function currentDate() {
    var inp = document.getElementById('ob-date');
    if (window.jQuery && jQuery('#ob-date').data && jQuery('#ob-date').data('daterangepicker')) {
      return jQuery('#ob-date').data('daterangepicker').startDate.format('YYYY-MM-DD');
    }
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-today');
  }

  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  // Colunas editáveis: a derivada Type (última, calculada no servidor) fica fora
  // do Add/Edit — não é persistida, nasce do match com a posição.
  function dataCols() {
    return (COLS.length && COLS[COLS.length - 1] === 'Type') ? COLS.slice(0, -1) : COLS;
  }

  // New Deals glass modal: a field per column. editId=null → Add; else Edit (prefilled).
  function openModal(editId, prefillCells) {
    EDIT_ID = editId || null;
    var title = document.getElementById('obModalTitle');
    if (title) title.textContent = EDIT_ID ? t('editTitle') : t('addTitle');
    document.getElementById('obAddFields').innerHTML = dataCols().map(function (c, i) {
      var val = (prefillCells && prefillCells[i] != null) ? prefillCells[i] : '';
      return '<div class="col-md-4"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
        '<input type="text" class="form-control form-control-sm ob-add-fld" data-i="' + i + '" value="' + esc(val) + '"></div>';
    }).join('');
    if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('obAddModal')).show();
  }

  function afterMutation(titleKey) {
    if (window.bootstrap) {
      var inst = bootstrap.Modal.getInstance(document.getElementById('obAddModal'));
      if (inst) inst.hide();
    }
    load(currentDate());
    if (window.fetchNotifications) window.fetchNotifications();
    if (window.Swal) Swal.fire({ icon: 'success', title: t(titleKey), timer: 1200, showConfirmButton: false });
  }

  // Add row (or save edit) → persist to the day's JSON, then reload.
  function wireAddRow() {
    var btn = document.getElementById('obAddBtn');
    if (btn) btn.addEventListener('click', function () { openModal(null, null); });
    var save = document.getElementById('obAddSave');
    if (save) save.addEventListener('click', function () {
      var cells = [];
      document.querySelectorAll('#obAddFields .ob-add-fld').forEach(function (f) { cells[+f.getAttribute('data-i')] = f.value; });
      var url = EDIT_ID ? '/api/operations-b3/row/edit' : '/api/operations-b3/row/add';
      var body = { date: currentDate(), cells: cells };
      if (EDIT_ID) body.id = EDIT_ID;
      save.disabled = true;
      postJSON(url, body).then(function (res) {
        save.disabled = false;
        if (res.ok && res.body && res.body.success) { afterMutation('saved'); }
        else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Operations B3', text: (res.body && res.body.message) || t('err') }); }
      }).catch(function () { save.disabled = false; });
    });
  }

  // Edit / Confirm / Delete (delegated — survives DataTables redraws).
  function wireActions() {
    jQuery('#opb3-table').off('click.obact')
      .on('click.obact', '.btn-row-edit', function () {
        var id = this.getAttribute('data-id');
        var row = CURRENT_ROWS.filter(function (r) { return String(metaOf(r).id) === String(id); })[0];
        openModal(id, row ? row.slice(0, dataCols().length) : null);
      })
      .on('click.obact', '.btn-row-confirm', function () {
        var id = this.getAttribute('data-id');
        postJSON('/api/operations-b3/row/confirm', { date: currentDate(), id: id }).then(function (res) {
          if (res.ok && res.body && res.body.success) { afterMutation('confirmed'); }
          else if (window.Swal) {
            var msg = (res.body && res.body.error === 'same_user') ? t('sameUser') : ((res.body && res.body.message) || t('err'));
            Swal.fire({ icon: 'warning', title: 'Operations B3', text: msg });
          }
        });
      })
      .on('click.obact', '.btn-row-delete', function () {
        var id = this.getAttribute('data-id');
        function doDelete() {
          postJSON('/api/operations-b3/row/delete', { date: currentDate(), id: id }).then(function (res) {
            if (res.ok && res.body && res.body.success) { afterMutation('deleted'); }
            else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Operations B3', text: t('err') }); }
          });
        }
        if (window.Swal) {
          Swal.fire({ icon: 'warning', title: t('delTitle'), text: t('delText'), showCancelButton: true,
            confirmButtonText: t('yes'), cancelButtonText: t('cancel'), confirmButtonColor: '#dc3545' })
            .then(function (r) { if (r.isConfirmed) doDelete(); });
        } else { doDelete(); }
      });
  }

  // ── Mensageria: destinatários persistidos (cards CEM / Equities) + geração ──
  var MSG_REC_URL = '/api/operations-b3/mensageria/recipients';
  function msgFields() {
    return {
      cem: { to: document.getElementById('obCemTo'), cc: document.getElementById('obCemCc') },
      equities: { to: document.getElementById('obEqTo'), cc: document.getElementById('obEqCc') },
    };
  }
  function msgLoadRecipients() {
    var f = msgFields();
    if (!f.cem.to) return;
    fetch(MSG_REC_URL, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        ['cem', 'equities'].forEach(function (k) {
          if (d[k]) { f[k].to.value = d[k].to || ''; f[k].cc.value = d[k].cc || ''; }
        });
      })
      .catch(function () {});
  }
  function msgSaveRecipients() {
    var f = msgFields();
    if (!f.cem.to) return Promise.resolve();
    return postJSON(MSG_REC_URL, {
      cem: { to: f.cem.to.value.trim(), cc: f.cem.cc.value.trim() },
      equities: { to: f.equities.to.value.trim(), cc: f.equities.cc.value.trim() },
    }).catch(function () {});
  }
  function wireMensageria() {
    document.querySelectorAll('.ob-msg-fld').forEach(function (el) {
      el.addEventListener('blur', msgSaveRecipients);
    });
    var btn = document.getElementById('obMsgBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var ids = Object.keys(SELECTED);
      var text = ids.length ? t('msgTextSel').replace('{n}', ids.length) : t('msgText');
      if (!window.Swal) return runMensageria(ids);
      Swal.fire({ icon: 'question', title: t('msgTitle'), text: text, showCancelButton: true,
        confirmButtonText: t('msgYes'), cancelButtonText: t('cancel') })
        .then(function (r) { if (r.isConfirmed) runMensageria(ids); });
    });

    function runMensageria(ids) {
      btn.disabled = true;
      // Salva os TO/CC primeiro para a geração usar exatamente o que está nos cards.
      msgSaveRecipients().then(function () {
        return fetch('/api/operations-b3/mensageria', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ date: currentDate(), ids: ids }),
        });
      }).then(function (r) {
        var ct = r.headers.get('Content-Type') || '';
        if (ct.indexOf('json') !== -1) {
          return r.json().then(function (j) {
            btn.disabled = false;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'Mensageria', text: (j && j.error) || t('err') });
          });
        }
        var count = r.headers.get('X-Draft-Count') || '';
        var cd = r.headers.get('Content-Disposition') || '';
        var m = /filename="?([^";]+)"?/.exec(cd);
        return r.blob().then(function (blob) {
          btn.disabled = false;
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = (m && m[1]) || 'mensageria.zip';
          document.body.appendChild(a); a.click();
          setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
          // Status/Status B3 mudaram no servidor → recarrega para refletir.
          load(currentDate());
          if (window.Swal) Swal.fire({ icon: 'success', title: 'Mensageria',
            text: count ? (count + ' draft(s) generated.') : 'Drafts generated.',
            timer: 2200, showConfirmButton: false });
        });
      }).catch(function () { btn.disabled = false; });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireClear();
    wireImport();
    wirePageLen();
    wireAddRow();
    wireActions();
    wireDatePicker();
    wireMensageria();
    msgLoadRecipients();
    load(page.getAttribute('data-today'));
  });
})();

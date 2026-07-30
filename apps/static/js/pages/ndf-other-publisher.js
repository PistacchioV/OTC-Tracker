/**
 * Daily Settlement › NDF › Other Publisher
 * Read-only view of the day's Operations B3 PENDENTE_CAMBIO entries joined to the
 * NDF Cockpit and Live Position NDF by the CETIP contract. Table modelled on the
 * Swap VCP page (widgets + wide DataTable + Columns/Export), plus the standard
 * checkbox / Actions / Status trio: values are derived on every load, only the
 * confirmation (maker/checker) is persisted.
 */
(function () {
  'use strict';

  // ':gt(1)' NÃO serve aqui: o thead tem duas linhas (títulos + filtros), o jQuery
  // enumera 2×N <th> e os das colunas 0/1 da segunda linha caem em posição > 1,
  // devolvendo checkbox e Actions para a exportação. Índice de COLUNA, então.
  function exportFromData(idx) { return idx > 1; }

  var page = document.getElementById('nop-page');
  if (!page) return;

  var API = page.getAttribute('data-api') || '/api/ndf-other-publisher/data';
  var CONFIRM_API = '/api/ndf-other-publisher/row/confirm';
  var EDIT_API = '/api/ndf-other-publisher/row/edit';
  var DELETE_API = '/api/ndf-other-publisher/row/delete';
  var SEND_API = '/api/ndf-other-publisher/send';
  var PREVIEW_API = '/api/ndf-other-publisher/row/preview';
  var dt = null;
  var COLS = [];
  var CURRENT_ROWS = [];       // last-loaded rows (each: [...data..., status, maker, checker, id])
  var EDIT_ID = null;

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { ok: 'OK', pending: 'Pending', newst: 'New', confirm: 'Confirm', edit: 'Edit', del: 'Delete',
          confirmed: 'Confirmed', saved: 'Saved', deleted: 'Deleted', err: 'Action failed.',
          delTitle: 'Delete row?', delText: 'This row will be hidden from the page.',
          yes: 'Yes, delete', cancel: 'Cancel',
          send: 'Send', sendTitle: 'Send to Conecta?',
          sendText: '{n} row(s) will be written to the Batch Conecta file.',
          yesSend: 'Yes, send', sentOk: 'Sent' },
    br: { ok: 'OK', pending: 'Pendente', newst: 'Novo', confirm: 'Confirmar', edit: 'Editar', del: 'Excluir',
          confirmed: 'Confirmado', saved: 'Salvo', deleted: 'Excluído', err: 'Falha na ação.',
          delTitle: 'Excluir linha?', delText: 'Esta linha será ocultada da página.',
          yes: 'Sim, excluir', cancel: 'Cancelar',
          send: 'Enviar', sendTitle: 'Enviar para o Conecta?',
          sendText: '{n} linha(s) serão gravadas no arquivo do Batch Conecta.',
          yesSend: 'Sim, enviar', sentOk: 'Enviado' },
    es: { ok: 'OK', pending: 'Pendiente', newst: 'Nuevo', confirm: 'Confirmar', edit: 'Editar', del: 'Eliminar',
          confirmed: 'Confirmado', saved: 'Guardado', deleted: 'Eliminado', err: 'Acción fallida.',
          delTitle: '¿Eliminar fila?', delText: 'Esta fila se ocultará de la página.',
          yes: 'Sí, eliminar', cancel: 'Cancelar',
          send: 'Enviar', sendTitle: '¿Enviar a Conecta?',
          sendText: '{n} fila(s) se escribirán en el archivo de Batch Conecta.',
          yesSend: 'Sí, enviar', sentOk: 'Enviado' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  // Standard status badge (project format): OK=success, Pending=warning, New=info,
  // Sent=badge-sent (global head-css class, same as New Deals).
  function statusBadge(status) {
    var s = String(status || 'New').toLowerCase();
    if (s === 'ok')      return '<span class="badge text-bg-success bg-gradient">' + esc(t('ok')) + '</span>';
    if (s === 'sent')    return '<span class="badge badge-sent bg-gradient">' + esc(t('sentOk')) + '</span>';
    if (s === 'pending') return '<span class="badge text-bg-warning bg-gradient">' + esc(t('pending')) + '</span>';
    return '<span class="badge bg-info text-white bg-gradient">' + esc(t('newst')) + '</span>';
  }

  // Rows carry [...data..., status, maker, checker, id] — same tail as the Cockpit.
  function metaOf(r) {
    var n = COLS.length;
    return { status: r[n], maker: r[n + 1], checker: r[n + 2], id: r[n + 3] };
  }

  // Action buttons — standard rounded-square format (global head-css) via btn-row-*.
  function actionsHtml(id) {
    return '<div class="d-inline-flex gap-1">' +
      '<button class="btn btn-primary btn-sm rounded-circle btn-row-send" data-id="' + esc(id) + '" title="' + esc(t('send')) + '"><i class="ti ti-brand-telegram"></i></button>' +
      '<button class="btn btn-info btn-sm rounded-circle btn-row-edit" data-id="' + esc(id) + '" title="' + esc(t('edit')) + '"><i class="ti ti-pencil"></i></button>' +
      '<button class="btn btn-success btn-sm rounded-circle btn-row-confirm" data-id="' + esc(id) + '" title="' + esc(t('confirm')) + '"><i class="ti ti-check"></i></button>' +
      '<button class="btn btn-danger btn-sm rounded-circle btn-row-delete" data-id="' + esc(id) + '" title="' + esc(t('del')) + '"><i class="ti ti-trash"></i></button>' +
      '</div>';
  }

  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  // Glass modal: a field per column; B3 ID is the row key, so it is read-only.
  function openModal(id, cells) {
    EDIT_ID = id;
    document.getElementById('nopEditFields').innerHTML = COLS.map(function (c, i) {
      var val = (cells && cells[i] != null) ? cells[i] : '';
      return '<div class="col-md-4"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
        '<input type="text" class="form-control form-control-sm nop-edit-fld" data-i="' + i + '" value="' +
        esc(val) + '"' + (c === 'B3 ID' ? ' readonly' : '') + '></div>';
    }).join('');
    if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('nopEditModal')).show();
  }

  function afterMutation(titleKey) {
    if (window.bootstrap) {
      var inst = bootstrap.Modal.getInstance(document.getElementById('nopEditModal'));
      if (inst) inst.hide();
    }
    load(currentDate());
    if (window.fetchNotifications) window.fetchNotifications();
    if (window.Swal) Swal.fire({ icon: 'success', title: t(titleKey), timer: 1200, showConfirmButton: false });
  }

  function load(dateStr) {
    fetch(API + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : ''), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        setVal('nop-w-total', (d.widgets || {}).total || 0);
        setVal('nop-total-asof', d.ref_date_fmt || '—');
        buildTable(d.columns || [], d.rows || []);
      })
      .catch(function () {});
  }

  function buildTable(columns, rows) {
    COLS = columns;
    CURRENT_ROWS = rows;
    var titleRow =
      '<tr>' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="nopCheckAll" class="form-check-input"></th>' +
      '<th data-lang="nop-actions">Actions</th>' +
      '<th data-lang="nop-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="nop-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm nop-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm nop-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#nop-table thead').innerHTML = titleRow + filterRow;

    var data = rows.map(function (r) {
      var m = metaOf(r);
      return ['<input type="checkbox" class="form-check-input nop-row-check" data-id="' + esc(m.id) + '">',
              actionsHtml(m.id), statusBadge(m.status)]
        .concat(r.slice(0, COLS.length).map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    dt = jQuery('#nop-table').DataTable({
      data: data,
      columns: [{}, {}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [
        { orderable: false, className: 'text-center', targets: 0 },
        { orderable: false, searchable: false, className: 'text-center', targets: 1 },
      ],
      scrollX: false, autoWidth: false, orderCellsTop: true, deferRender: true,
      pageLength: 25, order: [],
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

    var expWrap = document.querySelector('.nopExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#nop-table thead').off('keyup.nopcol change.nopcol')
      .on('keyup.nopcol change.nopcol', '.nop-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('nop-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('nop-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.nop-page-len');
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }

    var checkAll = document.getElementById('nopCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#nop-table tbody .nop-row-check').forEach(function (c) { c.checked = checkAll.checked; });
      updateSendBatch();
    });
    updateSendBatch();
  }

  // ── Send to Conecta ─────────────────────────────────────────────────────────
  function checkedIds() {
    return Array.prototype.map.call(
      document.querySelectorAll('#nop-table tbody .nop-row-check:checked'),
      function (c) { return c.getAttribute('data-id'); }).filter(Boolean);
  }

  // The batch button only shows up with 2+ rows checked — a single row is sent
  // by its own row-level button.
  function updateSendBatch() {
    var btn = document.getElementById('nopSendBatch');
    if (btn) btn.classList.toggle('d-none', checkedIds().length < 2);
  }

  function doSend(ids) {
    if (!ids.length) return;
    Swal.fire({
      icon: 'question', title: t('sendTitle'),
      text: t('sendText').replace('{n}', ids.length),
      showCancelButton: true, confirmButtonText: t('yesSend'),
      cancelButtonText: t('cancel'), confirmButtonColor: '#0066cc',
    }).then(function (r) {
      if (!r.isConfirmed) return;
      postJSON(SEND_API, { date: currentDate(), ids: ids }).then(function (res) {
        if (res.ok && res.body && res.body.success) {
          var files = (res.body.files || []).map(function (f) {
            return f.filename + ' (' + f.count + ')';
          }).join('  ·  ');
          if (window.fetchNotifications) window.fetchNotifications();
          Swal.fire({ icon: 'success', title: t('sentOk'), text: files });
          load(currentDate());
        } else {
          Swal.fire({ icon: 'error', title: 'OTM', text: (res.body && res.body.error) || t('err') });
        }
      }).catch(function () {});
    });
  }

  // ── Conecta preview (double-click) ──────────────────────────────────────────
  function closePreview() {
    var el = page.querySelector('.nop-preview');
    if (el) el.remove();
  }

  function showPreview(id, pageX, pageY) {
    closePreview();
    fetch(PREVIEW_API + '?date=' + encodeURIComponent(currentDate()) + '&id=' + encodeURIComponent(id),
          { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        var views = d.views || [];
        if (!views.length) return;
        var html = '<div class="nop-preview-head"><i class="ti ti-eye me-1"></i>' + esc(d.id) +
          '<button type="button" class="btn-close nop-preview-close" aria-label="Close"></button></div>' +
          '<div class="nop-preview-scroll"><table>';
        if (views.length > 1) {
          html += '<tr><th></th>' + views.map(function (v) {
            return '<th class="nop-preview-vt">' + esc(v.title) + '</th>';
          }).join('') + '</tr>';
        }
        (views[0].fields || []).forEach(function (f, i) {
          html += '<tr><th>' + esc(f[0]) + '</th>' + views.map(function (v) {
            return '<td class="nop-preview-val">' + esc(v.fields[i][1]) + '</td>';
          }).join('') + '</tr>';
        });
        html += '</table></div>';
        var el = document.createElement('div');
        el.className = 'nop-preview';
        el.innerHTML = html;
        page.appendChild(el);
        // Anchor at the double-click point (page coords → #nop-page coords),
        // clamped so the popover never leaves the page area.
        var rect = page.getBoundingClientRect();
        var left = pageX - (rect.left + window.scrollX);
        var top = pageY - (rect.top + window.scrollY);
        left = Math.max(8, Math.min(left, page.clientWidth - el.offsetWidth - 8));
        el.style.left = left + 'px';
        el.style.top = top + 'px';
        el.querySelector('.nop-preview-close').addEventListener('click', closePreview);
      })
      .catch(function () {});
  }

  function wirePreviewClose() {
    document.addEventListener('click', function (e) {
      var el = page.querySelector('.nop-preview');
      if (el && !el.contains(e.target)) closePreview();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePreview();
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="nopCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="nopCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="nopColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('nopColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function currentDate() {
    if (window.jQuery && jQuery('#nop-date').data && jQuery('#nop-date').data('daterangepicker')) {
      return jQuery('#nop-date').data('daterangepicker').startDate.format('YYYY-MM-DD');
    }
    var inp = document.getElementById('nop-date');
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-ref-date');
  }

  function wireClear() {
    var clr = document.getElementById('nopClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#nop-table .nop-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('nop-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  function wirePageLen() {
    var sel = document.querySelector('.nop-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('nop-date');
    if (!inp) return;
    var ref = page.getAttribute('data-ref-date');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#nop-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: ref ? moment(ref, 'YYYY-MM-DD') : moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#nopDateWrap .nop-cal-btn').on('click', function () { $d.trigger('click'); });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    if (ref) { var p = ref.split('-'); inp.value = p[2] + '/' + p[1] + '/' + p[0]; }
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  // Send / Edit / Confirm / Delete (delegated — survives DataTables redraws).
  function wireActions() {
    jQuery('#nop-table').off('click.nopact dblclick.nopact change.nopact')
      .on('change.nopact', '.nop-row-check', updateSendBatch)
      .on('dblclick.nopact', 'tbody tr', function (e) {
        if (e.target.closest('button, a, input')) return;
        var btn = this.querySelector('.btn-row-confirm');
        var id = btn && btn.getAttribute('data-id');
        if (id) showPreview(id, e.pageX, e.pageY);
      })
      .on('click.nopact', '.btn-row-send', function () {
        doSend([this.getAttribute('data-id')]);
      })
      .on('click.nopact', '.btn-row-edit', function () {
        var id = this.getAttribute('data-id');
        var row = CURRENT_ROWS.filter(function (r) { return String(metaOf(r).id) === String(id); })[0];
        openModal(id, row ? row.slice(0, COLS.length) : null);
      })
      .on('click.nopact', '.btn-row-confirm', function () {
        var id = this.getAttribute('data-id');
        postJSON(CONFIRM_API, { date: currentDate(), id: id }).then(function (res) {
          if (res.ok && res.body && res.body.success) { afterMutation('confirmed'); }
          else if (window.Swal) { Swal.fire({ icon: 'error', title: 'OTM', text: (res.body && res.body.error) || t('err') }); }
        }).catch(function () {});
      })
      .on('click.nopact', '.btn-row-delete', function () {
        var id = this.getAttribute('data-id');
        function doDelete() {
          postJSON(DELETE_API, { date: currentDate(), id: id }).then(function (res) {
            if (res.ok && res.body && res.body.success) { afterMutation('deleted'); }
            else if (window.Swal) { Swal.fire({ icon: 'error', title: 'OTM', text: t('err') }); }
          }).catch(function () {});
        }
        if (window.Swal) {
          Swal.fire({ icon: 'warning', title: t('delTitle'), text: t('delText'), showCancelButton: true,
            confirmButtonText: t('yes'), cancelButtonText: t('cancel'), confirmButtonColor: '#dc3545' })
            .then(function (r) { if (r.isConfirmed) doDelete(); });
        } else { doDelete(); }
      });
  }

  function wireEditSave() {
    var save = document.getElementById('nopEditSave');
    if (!save) return;
    save.addEventListener('click', function () {
      var cells = [];
      document.querySelectorAll('#nopEditFields .nop-edit-fld').forEach(function (f) {
        cells[+f.getAttribute('data-i')] = f.value;
      });
      save.disabled = true;
      postJSON(EDIT_API, { date: currentDate(), id: EDIT_ID, cells: cells }).then(function (res) {
        save.disabled = false;
        if (res.ok && res.body && res.body.success) { afterMutation('saved'); }
        else if (window.Swal) { Swal.fire({ icon: 'error', title: 'OTM', text: (res.body && res.body.error) || t('err') }); }
      }).catch(function () { save.disabled = false; });
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireClear();
    wirePageLen();
    wireActions();
    wireEditSave();
    wirePreviewClose();
    var batch = document.getElementById('nopSendBatch');
    if (batch) batch.addEventListener('click', function () { doSend(checkedIds()); });
    wireDatePicker();
    load(page.getAttribute('data-ref-date'));
  });
})();

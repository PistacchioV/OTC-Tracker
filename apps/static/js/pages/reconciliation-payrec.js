/**
 * Pay/Rec Reconciliation
 * Dropzone HOLDS the input files (nothing runs on drop) until the user clicks
 * "Run reconciliation". Alternatively "Import from folder" processes the files
 * already sitting in the network Pay_Rec folder. "End process" e-mails the final
 * situation of the day to OTC Ops (Danilo + Renato in copy).
 */
(function () {
  'use strict';

  var page = document.getElementById('payrec-page');
  if (!page) return;

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { running: 'Running…', sending: 'Sending…', run: 'Run reconciliation', end: 'End process',
          noFiles: 'No files', noFilesMsg: 'Attach files in the dropzone or make sure the Pay/Rec folder has the input files for this date.',
          failTitle: 'Reconciliation failed', netErr: 'Network error.', done: 'Reconciliation completed',
          sentTitle: 'Process finalised', sentMsg: 'The end-of-day situation was e-mailed to OTC Ops.',
          confirmEnd: 'Do you want to send the final Pay/Rec situation of the day?',
          yes: 'Yes, send', cancel: 'Cancel', empty: 'No records',
          pendTitle: 'Pending settlements',
          pendMsg: 'There are pending settlements. Do you want to justify the pending items or run the reconciliation again?',
          justify: 'Justify pending', runAgain: 'Run again', justified: 'Justified',
          commentPh: 'Enter justification…', commentReq: 'Please enter a justification comment.',
          justifyFail: 'Could not save the justification.' },
    br: { running: 'Processando…', sending: 'Enviando…', run: 'Rodar reconciliação', end: 'Encerrar processo',
          noFiles: 'Sem arquivos', noFilesMsg: 'Anexe os arquivos no dropzone ou verifique se a pasta Pay/Rec tem os arquivos de insumo desta data.',
          failTitle: 'Reconciliação falhou', netErr: 'Erro de rede.', done: 'Reconciliação concluída',
          sentTitle: 'Processo encerrado', sentMsg: 'A situação final do dia foi enviada por e-mail para a OTC Ops.',
          confirmEnd: 'Deseja enviar a situação final do Pay/Rec do dia?',
          yes: 'Sim, enviar', cancel: 'Cancelar', empty: 'Sem registros',
          pendTitle: 'Liquidações pendentes',
          pendMsg: 'Existem liquidações pendentes. Deseja justificar as pendências ou rodar a reconciliação novamente?',
          justify: 'Justificar pendências', runAgain: 'Rodar novamente', justified: 'Justificado',
          commentPh: 'Digite a justificativa…', commentReq: 'Informe um comentário de justificativa.',
          justifyFail: 'Não foi possível salvar a justificativa.' },
    es: { running: 'Procesando…', sending: 'Enviando…', run: 'Ejecutar reconciliación', end: 'Finalizar proceso',
          noFiles: 'Sin archivos', noFilesMsg: 'Adjunte los archivos en el dropzone o verifique que la carpeta Pay/Rec tenga los archivos de esta fecha.',
          failTitle: 'La reconciliación falló', netErr: 'Error de red.', done: 'Reconciliación completada',
          sentTitle: 'Proceso finalizado', sentMsg: 'La situación final del día se envió por correo a OTC Ops.',
          confirmEnd: '¿Desea enviar la situación final de Pay/Rec del día?',
          yes: 'Sí, enviar', cancel: 'Cancelar', empty: 'Sin registros',
          pendTitle: 'Liquidaciones pendientes',
          pendMsg: 'Hay liquidaciones pendientes. ¿Desea justificar las pendencias o ejecutar la reconciliación nuevamente?',
          justify: 'Justificar pendientes', runAgain: 'Ejecutar de nuevo', justified: 'Justificado',
          commentPh: 'Ingrese la justificación…', commentReq: 'Ingrese un comentario de justificación.',
          justifyFail: 'No se pudo guardar la justificación.' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ── Number formatting (BR-ish thousands, 2 dp) ──────────────────────────────
  function fmtNum(v) {
    if (v === '' || v === null || v === undefined) return '';
    var n = (typeof v === 'number') ? v : parseFloat(String(v).replace(/\./g, '').replace(',', '.'));
    if (isNaN(n)) return esc(v);
    return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function numCell(v) {
    if (v === '' || v === null || v === undefined) return '<td class="pr-num"></td>';
    var n = (typeof v === 'number') ? v : parseFloat(String(v).replace(/\./g, '').replace(',', '.'));
    var neg = !isNaN(n) && n < 0;
    return '<td class="pr-num' + (neg ? ' pr-neg' : '') + '">' + fmtNum(v) + '</td>';
  }
  function checkChip(v) {
    var ok = String(v).toUpperCase() === 'OK';
    return '<span class="pr-check ' + (ok ? 'pr-check--ok' : 'pr-check--no') + '">' +
      '<i class="ti ' + (ok ? 'ti-check' : 'ti-alert-triangle') + '"></i>' + esc(v) + '</span>';
  }
  function isPending(v) { return String(v || '').toLowerCase().indexOf('pend') !== -1; }
  function isJustified(v) { return String(v || '').toLowerCase().indexOf('justif') !== -1; }
  function statusBadge(v) {
    var s = String(v || '').toLowerCase();
    var cls, label = v;
    if (isJustified(v)) { cls = 'badge-justified'; label = t('justified'); }
    else if (s.indexOf('settl') !== -1) { cls = 'badge-settled'; }
    else { cls = 'badge-pending'; }
    return '<span class="badge-status ' + cls + '">' + esc(label) + '</span>';
  }

  // Justify mode: revealed when the operator chooses to justify pending items
  // from the End-process dialog. Adds the Comment + Actions columns.
  var justifyMode = false;
  var _lastData = null;

  // ── Render results ──────────────────────────────────────────────────────────
  function show(id, on) { var el = document.getElementById(id); if (el) el.hidden = !on; }
  function setText(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  function renderSummary(rows) {
    var body = document.getElementById('prSummaryBody');
    if (!rows || !rows.length) { show('prCardSummary', false); return; }
    body.innerHTML = rows.map(function (r) {
      var isTotal = String(r.pay_receive).toUpperCase() === 'TOTAL';
      return '<tr' + (isTotal ? ' class="pr-total"' : '') + '>' +
        '<td>' + esc(r.pay_receive) + '</td>' +
        '<td class="pr-num">' + esc(r.jpm_qty) + '</td>' +
        '<td class="pr-num">' + esc(r.client_qty) + '</td>' +
        '<td>' + checkChip(r.check_qty) + '</td>' +
        numCell(r.jpm_value) + numCell(r.client_value) + numCell(r.difference) +
        '<td>' + checkChip(r.check_value) + '</td>' +
      '</tr>';
    }).join('');
    show('prCardSummary', true);
  }

  function renderList(cardId, bodyId, countId, rows, kind, tableKey) {
    var body = document.getElementById(bodyId);
    var span = countId ? String(rows ? rows.length : 0) : '';
    if (countId) setText(countId, span);
    if (!rows || !rows.length) {
      body.innerHTML = '<tr><td colspan="10" class="pr-empty">' + esc(t('empty')) + '</td></tr>';
      show(cardId, true);
      return;
    }
    body.innerHTML = rows.map(function (r, i) {
      var base =
        '<td>' + esc(r.le || '') + '</td>' +
        '<td>' + esc(r.product) + '</td>' +
        '<td>' + esc(r.jpm_cpty) + '</td>' +
        '<td>' + esc(r.client) + '</td>' +
        '<td>' + esc(r.pay_receive) + '</td>' +
        numCell(r.jpm_value) + numCell(r.client_value);
      if (kind === 'settled') {
        return '<tr>' + base + '<td>' + esc(r.sistema) + '</td><td>' + statusBadge(r.status) +
          '</td><td>' + esc(r.snumconta) + '</td></tr>';
      }
      // Pending tables: the Comment column is always visible. The Edit/Confirm
      // action buttons (New Deals rounded-circle style) only appear for rows that
      // still need justifying — that's when the comment becomes editable.
      var needs = isPending(r.status);
      var actions = needs
        ? '<div class="d-flex justify-content-center gap-1">' +
          '<button type="button" class="btn btn-info btn-sm rounded-circle pr-act-edit" title="Edit"><i class="ti ti-edit"></i></button>' +
          '<button type="button" class="btn btn-success btn-sm rounded-circle pr-act-confirm" title="Confirm"><i class="ti ti-check"></i></button>' +
          '</div>'
        : '';
      return '<tr data-pr-table="' + esc(tableKey || '') + '" data-pr-index="' + i + '">' + base +
        '<td class="pr-status-cell">' + statusBadge(r.status) + '</td>' +
        '<td class="pr-comment-cell">' + esc(r.comment || '') + '</td>' +
        '<td class="pr-actions-cell">' + actions + '</td>' +
        '</tr>';
    }).join('');
    show(cardId, true);
  }

  function render(d) {
    _lastData = d || {};
    renderSummary(d.summary || []);
    renderList('prCardPendPay', 'prPendPayBody', 'prPendPayCount', d.pending_payment || [], 'pend', 'pay');
    renderList('prCardPendRec', 'prPendRecBody', 'prPendRecCount', d.pending_receivement || [], 'pend', 'rec');
    renderList('prCardSettled', 'prSettledBody', 'prSettledCount', d.settled || [], 'settled');
    show('prEmpty', false);
    // The final situation can only be e-mailed once there is a processed result.
    var endBtn = document.getElementById('prEndBtn');
    if (endBtn) endBtn.disabled = false;
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();
  }

  function applyTranslationsIfAny() { if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} } }

  // ── Busy helper (spinner on a button) ───────────────────────────────────────
  function busy(btn, on, runningKey) {
    if (!btn) return;
    var label = btn.querySelector('span'), icon = btn.querySelector('i');
    if (on) {
      btn._orig = { txt: label ? label.textContent : '', ico: icon ? icon.className : '' };
      btn.disabled = true;
      if (label) label.textContent = t(runningKey || 'running');
      if (icon) icon.className = 'ti ti-loader-2 ti-spin';
    } else {
      btn.disabled = false;
      if (label && btn._orig) label.textContent = btn._orig.txt;
      if (icon && btn._orig) icon.className = btn._orig.ico;
    }
  }

  function refDate() {
    var inp = document.getElementById('pr-date');
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    if (m) return m[3] + '-' + m[2] + '-' + m[1];
    return page.getAttribute('data-ref-date') || '';
  }

  // ── Run: dropzone files (manual) OR folder scan (auto) ──────────────────────
  function run(mode, btn) {
    busy(btn, true, 'running');
    var opts;
    if (mode === 'manual' && dzFiles.length) {
      var fd = new FormData();
      fd.append('mode', 'manual');
      fd.append('recon_date', refDate());
      dzFiles.forEach(function (f) { fd.append('files', f); });
      opts = { method: 'POST', body: fd, credentials: 'same-origin' };
    } else {
      var p = new URLSearchParams(); p.set('mode', 'auto'); p.set('recon_date', refDate());
      opts = { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: p.toString(), credentials: 'same-origin' };
    }
    fetch('/reconciliation-payrec/run', opts)
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var b = res.body || {};
        if (res.ok && b.success !== false && !b.error && !b.not_found) {
          if (mode === 'manual') clearDzFiles();   // uploads are now saved in the folder — clear the dropzone
          resetJustify();
          render(b);
          setText('prMeta', (b.meta || '') + (b.recon_date_fmt ? ('  ·  ' + b.recon_date_fmt) : ''));
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'success', title: t('done'), html: b.meta || '', confirmButtonColor: '#0066cc', timer: 1600, showConfirmButton: false });
        } else if (b.not_found) {
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'warning', title: t('noFiles'), html: b.detail || t('noFilesMsg'), confirmButtonColor: '#0066cc' });
        } else {
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: b.error || t('netErr'), confirmButtonColor: '#0066cc' });
        }
      })
      .catch(function () { if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: t('netErr'), confirmButtonColor: '#0066cc' }); })
      .finally(function () { busy(btn, false); });
  }

  // ── End process → e-mail the final situation ────────────────────────────────
  function endProcess(btn) {
    var go = function () {
      busy(btn, true, 'sending');
      var p = new URLSearchParams(); p.set('recon_date', refDate());
      fetch('/reconciliation-payrec/end-process', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: p.toString(), credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
        .then(function (res) {
          var b = res.body || {};
          if (res.ok && b.success) {
            if (typeof Swal !== 'undefined') Swal.fire({ icon: 'success', title: t('sentTitle'), html: t('sentMsg'), confirmButtonColor: '#0066cc' });
          } else {
            if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: (b && b.error) || t('netErr'), confirmButtonColor: '#0066cc' });
          }
        })
        .catch(function () { if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: t('netErr'), confirmButtonColor: '#0066cc' }); })
        .finally(function () { busy(btn, false); });
    };
    // Any settlement still Pending in the Summary / Pending tables? Warn first and
    // offer to justify the pending items — otherwise go straight to the send flow.
    if (pendingCount() > 0 && typeof Swal !== 'undefined') {
      Swal.fire({
        icon: 'warning', title: t('pendTitle'), html: t('pendMsg'),
        showConfirmButton: true, showDenyButton: true, showCloseButton: true,
        confirmButtonText: t('justify'), denyButtonText: t('runAgain'),
        confirmButtonColor: '#0066cc', denyButtonColor: '#6c757d'
      }).then(function (r) {
        // Justify → reveal the Comment/Actions columns. Run again / close → no-op.
        if (r.isConfirmed) enterJustifyMode();
      });
      return;
    }
    if (typeof Swal !== 'undefined') {
      Swal.fire({ icon: 'question', title: t('end'), html: t('confirmEnd'), showCancelButton: true,
        confirmButtonText: t('yes'), cancelButtonText: t('cancel'), confirmButtonColor: '#198754', cancelButtonColor: '#6c757d' })
        .then(function (r) { if (r.isConfirmed) go(); });
    } else { go(); }
  }

  // Count pending rows across the two pending tables (Summary has no per-row
  // status; "status Pending" lives only in the pending tables).
  function pendingCount() {
    if (!_lastData) return 0;
    var n = 0;
    (_lastData.pending_payment || []).forEach(function (r) { if (isPending(r.status)) n++; });
    (_lastData.pending_receivement || []).forEach(function (r) { if (isPending(r.status)) n++; });
    return n;
  }

  function resetJustify() { justifyMode = false; if (page) page.classList.remove('pr-justify'); }

  function enterJustifyMode() {
    justifyMode = true;
    page.classList.add('pr-justify');
    if (_lastData) render(_lastData);   // re-render to expose Comment + Actions
  }

  // Edit / Confirm on a pending row (event delegation over both pending tbodies).
  function wireJustifyActions() {
    ['prPendPayBody', 'prPendRecBody'].forEach(function (bodyId) {
      var body = document.getElementById(bodyId);
      if (!body) return;
      body.addEventListener('click', function (e) {
        var editBtn = e.target.closest('.pr-act-edit');
        var okBtn = e.target.closest('.pr-act-confirm');
        var cancelBtn = e.target.closest('.pr-act-cancel');
        if (!editBtn && !okBtn && !cancelBtn) return;
        var tr = e.target.closest('tr'); if (!tr) return;
        // Cancel → discard the edit and restore the row to its previous state
        // (no request made). Re-rendering from _lastData reverts the cells and
        // brings back the original Edit/Confirm buttons.
        if (cancelBtn) { render(_lastData); return; }
        var cell = tr.querySelector('.pr-comment-cell'); if (!cell) return;
        var table = tr.getAttribute('data-pr-table');
        var index = parseInt(tr.getAttribute('data-pr-index'), 10);
        // The carry-forward status offered depends on the table: Pending Payment
        // for the payment table, Pending Receivement for the receivement table.
        var carryStatus = table === 'pay' ? 'Pending Payment' : 'Pending Receivement';
        var statusCell = tr.querySelector('.pr-status-cell');
        if (editBtn) {
          if (cell.querySelector('input')) return;   // already editing
          var cur = cell.textContent.trim();
          cell.innerHTML = '<input type="text" class="pr-comment-input" value="' +
            cur.replace(/"/g, '&quot;') + '" placeholder="' + esc(t('commentPh')) + '">';
          // Make the Status column editable too: a dropdown offering the plain
          // "Pending" (→ justify on confirm) and the carry-forward status.
          if (statusCell && !statusCell.querySelector('select')) {
            var arrE = table === 'pay' ? (_lastData.pending_payment || []) : (_lastData.pending_receivement || []);
            var curStatus = (arrE[index] && arrE[index].status) || 'Pending';
            var isCarryNow = String(curStatus).toLowerCase() === carryStatus.toLowerCase();
            statusCell.innerHTML =
              '<select class="form-select form-select-sm pr-status-input">' +
                '<option value="Pending"' + (isCarryNow ? '' : ' selected') + '>Pending</option>' +
                '<option value="' + esc(carryStatus) + '"' + (isCarryNow ? ' selected' : '') + '>' + esc(carryStatus) + '</option>' +
              '</select>';
          }
          // Swap the Edit button for a Cancel button → the row now shows
          // Cancel + Confirm while it's being edited.
          editBtn.classList.remove('pr-act-edit', 'btn-info');
          editBtn.classList.add('pr-act-cancel', 'btn-danger');
          editBtn.setAttribute('title', 'Cancel');
          editBtn.innerHTML = '<i class="ti ti-x"></i>';
          var inp = cell.querySelector('input'); if (inp) inp.focus();
          return;
        }
        // Confirm → read the chosen status + comment.
        //  • Status "Pending" + comment  → Justified (comment required).
        //  • Status "Pending Payment/Receivement" → keep it as a carry-forward
        //    item (comment optional); it will reappear in the next days' recon
        //    until it settles (OK) or is justified.
        var statusSel = statusCell ? statusCell.querySelector('select') : null;
        var chosenStatus = statusSel ? statusSel.value : 'Pending';
        var isCarry = /^pending (payment|receivement)$/i.test(chosenStatus);
        var input = cell.querySelector('input');
        var comment = (input ? input.value : cell.textContent).trim();
        if (!isCarry && !comment) {
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'info', title: t('pendTitle'), html: t('commentReq'), confirmButtonColor: '#0066cc' });
          else if (input) input.focus();
          return;
        }
        fetch('/reconciliation-payrec/justify', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
          body: JSON.stringify({ recon_date: refDate(), table: table, index: index, comment: comment, status: chosenStatus })
        }).then(function (r) { return r.json(); }).then(function (res) {
          if (res && res.success) {
            var arr = table === 'pay' ? (_lastData.pending_payment || []) : (_lastData.pending_receivement || []);
            if (arr[index]) { arr[index].status = isCarry ? chosenStatus : 'Justified'; arr[index].comment = comment; }
            render(_lastData);
          } else if (typeof Swal !== 'undefined') {
            Swal.fire({ icon: 'error', title: t('failTitle'), html: (res && res.error) || t('justifyFail'), confirmButtonColor: '#0066cc' });
          }
        }).catch(function () {
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: t('netErr'), confirmButtonColor: '#0066cc' });
        });
      });
    });
  }

  // ── Dropzone (holds files until Run) ────────────────────────────────────────
  var dzFiles = [];
  var dzRenderChips = function () {};        // set by wireDropzone; used to redraw the chips
  function clearDzFiles() { dzFiles.length = 0; dzRenderChips(); }
  function wireDropzone() {
    var drop = document.getElementById('prDrop');
    var input = document.getElementById('prFiles');
    var listEl = document.getElementById('prDzList');
    if (!drop || !input || !listEl) return;
    function renderChips() {
      listEl.innerHTML = dzFiles.map(function (f, i) {
        return '<li><i class="ti ti-file"></i>' + esc(f.name) + '<span class="pr-dz-x" data-i="' + i + '">&times;</span></li>';
      }).join('');
      listEl.querySelectorAll('.pr-dz-x').forEach(function (x) {
        x.addEventListener('click', function (e) { e.stopPropagation(); dzFiles.splice(+this.dataset.i, 1); renderChips(); });
      });
    }
    drop.addEventListener('click', function (e) { if (e.target.closest('.pr-dz-x')) return; input.click(); });
    drop.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); } });
    dzRenderChips = renderChips;             // expose for clearDzFiles() after a run
    input.addEventListener('change', function () { Array.prototype.forEach.call(input.files, function (f) { dzFiles.push(f); }); input.value = ''; renderChips(); });
    ['dragenter', 'dragover'].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('pr-dz-over'); }); });
    ['dragleave', 'dragend'].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('pr-dz-over'); }); });
    drop.addEventListener('drop', function (e) {
      e.preventDefault(); drop.classList.remove('pr-dz-over');
      Array.prototype.forEach.call(e.dataTransfer.files, function (f) { dzFiles.push(f); }); renderChips();
    });
  }

  function wireDatePicker(attempt) {
    var inp = document.getElementById('pr-date');
    if (!inp) return;
    var startISO = page.getAttribute('data-ref-date');
    function isoToDmy(iso) { var p = String(iso || '').split('-'); return p.length === 3 ? (p[2] + '/' + p[1] + '/' + p[0]) : ''; }
    if (startISO && !inp.value) inp.value = isoToDmy(startISO);
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      try {
        var $d = jQuery('#pr-date');
        $d.daterangepicker({ singleDatePicker: true, autoApply: true, showDropdowns: true, autoUpdateInput: true,
          locale: { format: 'DD/MM/YYYY' }, startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment(), maxDate: moment() },
          function (start) { inp.value = start.format('DD/MM/YYYY'); loadLast(); });   // pull that day's saved status
        if (startISO) inp.value = isoToDmy(startISO);
        jQuery('#prDateWrap .pr-cal-btn').on('click', function () { $d.trigger('click'); });
        return;
      } catch (e) {}
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    inp.addEventListener('change', function () {
      if (/^\d{2}\/\d{2}\/\d{4}$/.test(this.value || '')) loadLast();   // pull that day's saved status
    });
  }

  // Hide every result block and show the empty state (used when a date has no
  // saved status, e.g. browsing a past day that was never finalised).
  function clearResults() {
    resetJustify();
    ['prCardSummary', 'prCardPendPay', 'prCardPendRec', 'prCardSettled'].forEach(function (id) { show(id, false); });
    show('prEmpty', true);
    setText('prMeta', '');
    var endBtn = document.getElementById('prEndBtn');
    if (endBtn) endBtn.disabled = true;
  }

  // Pull the saved status for the current reference date (finalised history, or
  // the latest working run). Renders it, or clears the screen if there's none.
  function loadLast() {
    fetch('/reconciliation-payrec/data?recon_date=' + encodeURIComponent(refDate()), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var has = d && ((d.summary && d.summary.length) || (d.settled && d.settled.length) ||
                  (d.pending_payment && d.pending_payment.length) || (d.pending_receivement && d.pending_receivement.length));
        if (has) { resetJustify(); render(d); setText('prMeta', d.meta || ''); }
        else { clearResults(); }
      })
      .catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    try { wireDropzone(); } catch (e) {}
    try { wireDatePicker(); } catch (e) {}
    try { wireJustifyActions(); } catch (e) {}
    var runBtn = document.getElementById('prRunBtn');
    var impBtn = document.getElementById('prImportBtn');
    var endBtn = document.getElementById('prEndBtn');
    if (runBtn) runBtn.addEventListener('click', function () { run('manual', runBtn); });
    if (impBtn) impBtn.addEventListener('click', function () { run('auto', impBtn); });
    if (endBtn) endBtn.addEventListener('click', function () { endProcess(endBtn); });
    try { loadLast(); } catch (e) {}
  });
})();

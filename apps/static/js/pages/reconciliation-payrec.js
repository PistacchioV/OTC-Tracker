/**
 * Pay/Rec Reconciliation
 * UM botão de ação: "Run". A dropzone SEGURA os arquivos (nada roda ao soltar) e
 * é ela que decide o que o Run faz — com arquivos anexados, roda com eles; sem
 * nenhum, varre a pasta de rede Pay_Rec, que era o antigo "Import from folder".
 * "End process" envia a situação final do dia por e-mail para a OTC Ops
 * (Danilo + Renato em cópia).
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
          justifyFail: 'Could not save the justification.',
          runFolder: 'Run with the files from the Pay/Rec folder',
          runFiles: 'Run with the attached file(s)',
          e_ndf_source_failed: 'Could not read the NDF settlements (Athena API + unwinds):',
          branchTag: 'Branch Settl.', branchTitle: 'Branch Settlement — VP approval',
          branchDone: 'The approval e-mail draft was downloaded. Open it in Outlook, review and send it to the VP.',
          branchWarn: 'Check before sending:',
          e_branch_none: 'There is no settlement with the Branch on this date. Run the reconciliation first.',
          e_branch_no_recipient: 'No TO recipient saved. Fill it in Control Panel › Branch Settlement Reverse Approval.',
          e_branch_no_reversal: 'Operations B3 has no Branch client settlement (73760.20-5 × 04880.00-6) for this date — there is no reversal to approve.',
          w_branch_no_account: 'No approved {slot} account for {entity} in Reference Data › Counterparty Details.',
          w_branch_legacy_route: '{n} settlement(s) still through the MGT omnibus 04880.10-9 (net {value}) — not in the reversal.',
          branchTagB2b: 'B2B', branchTagRev: 'Branch Reversal',
          matchTitle: 'Manual match',
          matchCpty: 'Counterparty', matchValue: 'Value', matchTotal: 'Total', matchSum: 'Sum of the rows', matchDiff: 'Difference (JPM − Client)', matchJpm: 'JPM', matchClient: 'Client',
          matchTol: 'Tolerance', matchWithin: 'Within tolerance', matchOver: 'Above tolerance',
          matchDo: 'Match', matchDone: 'Rows matched and moved to Settled.', matchTag: 'Manual',
          e_match_need_two: 'Select at least two rows to match.',
          e_match_cpty_differs: 'The selected rows are not from the same counterparty: {names}',
          e_match_over_tolerance: 'The difference {net} is above the tolerance of {tol}.',
          e_match_no_recon: 'There is no reconciliation for this date. Run it first.',
          e_match_row_missing: 'A selected row is no longer pending. Reload the page.',
          e_match_already_matched: 'A selected row was already matched by the reconciliation.' },
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
          justifyFail: 'Não foi possível salvar a justificativa.',
          runFolder: 'Rodar com os arquivos da pasta Pay/Rec',
          runFiles: 'Rodar com o(s) arquivo(s) anexado(s)',
          e_ndf_source_failed: 'Não foi possível ler as liquidações de NDF (API Athena + recompras):',
          branchTag: 'Branch Settl.', branchTitle: 'Branch Settlement — aprovação do VP',
          branchDone: 'O rascunho do e-mail de aprovação foi baixado. Abra no Outlook, revise e envie ao VP.',
          branchWarn: 'Confira antes de enviar:',
          e_branch_none: 'Não há liquidação com a Branch nesta data. Rode a reconciliação primeiro.',
          e_branch_no_recipient: 'Nenhum destinatário PARA salvo. Preencha em Control Panel › Branch Settlement Reverse Approval.',
          e_branch_no_reversal: 'O Operations B3 não tem liquidação de cliente da Branch (73760.20-5 × 04880.00-6) nesta data — não há reversão para aprovar.',
          w_branch_no_account: 'Sem conta {slot} aprovada para {entity} em Reference Data › Counterparty Details.',
          w_branch_legacy_route: '{n} liquidação(ões) ainda pela guarda-chuva da MGT 04880.10-9 (net {value}) — fora da reversão.',
          branchTagB2b: 'B2B', branchTagRev: 'Branch Reversal',
          matchTitle: 'Match manual',
          matchCpty: 'Contraparte', matchValue: 'Valor', matchTotal: 'Total', matchSum: 'Soma das linhas', matchDiff: 'Diferença (JPM − Client)', matchJpm: 'JPM', matchClient: 'Client',
          matchTol: 'Tolerância', matchWithin: 'Dentro da tolerância', matchOver: 'Acima da tolerância',
          matchDo: 'Casar', matchDone: 'Linhas casadas e movidas para Settled.', matchTag: 'Manual',
          e_match_need_two: 'Selecione ao menos duas linhas para casar.',
          e_match_cpty_differs: 'As linhas selecionadas não são da mesma contraparte: {names}',
          e_match_over_tolerance: 'A diferença {net} está acima da tolerância de {tol}.',
          e_match_no_recon: 'Não há reconciliação nesta data. Rode-a primeiro.',
          e_match_row_missing: 'Uma linha selecionada não está mais pendente. Recarregue a página.',
          e_match_already_matched: 'Uma linha selecionada já foi casada pela reconciliação.' },
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
          justifyFail: 'No se pudo guardar la justificación.',
          runFolder: 'Ejecutar con los archivos de la carpeta Pay/Rec',
          runFiles: 'Ejecutar con el/los archivo(s) adjunto(s)',
          e_ndf_source_failed: 'No se pudieron leer las liquidaciones de NDF (API Athena + recompras):',
          branchTag: 'Branch Settl.', branchTitle: 'Branch Settlement — aprobación del VP',
          branchDone: 'Se descargó el borrador del correo de aprobación. Ábralo en Outlook, revíselo y envíelo al VP.',
          branchWarn: 'Verifique antes de enviar:',
          e_branch_none: 'No hay liquidación con la Branch en esta fecha. Ejecute la reconciliación primero.',
          e_branch_no_recipient: 'No hay destinatario PARA guardado. Complételo en Control Panel › Branch Settlement Reverse Approval.',
          e_branch_no_reversal: 'Operations B3 no tiene liquidación de cliente de la Branch (73760.20-5 × 04880.00-6) en esta fecha — no hay reversión para aprobar.',
          w_branch_no_account: 'Sin cuenta {slot} aprobada para {entity} en Reference Data › Counterparty Details.',
          w_branch_legacy_route: '{n} liquidación(es) aún por la cuenta ómnibus de la MGT 04880.10-9 (net {value}) — fuera de la reversión.',
          branchTagB2b: 'B2B', branchTagRev: 'Branch Reversal',
          matchTitle: 'Match manual',
          matchCpty: 'Contraparte', matchValue: 'Valor', matchTotal: 'Total', matchSum: 'Suma de las filas', matchDiff: 'Diferencia (JPM − Client)', matchJpm: 'JPM', matchClient: 'Client',
          matchTol: 'Tolerancia', matchWithin: 'Dentro de la tolerancia', matchOver: 'Por encima de la tolerancia',
          matchDo: 'Conciliar', matchDone: 'Filas conciliadas y movidas a Settled.', matchTag: 'Manual',
          e_match_need_two: 'Seleccione al menos dos filas para conciliar.',
          e_match_cpty_differs: 'Las filas seleccionadas no son de la misma contraparte: {names}',
          e_match_over_tolerance: 'La diferencia {net} está por encima de la tolerancia de {tol}.',
          e_match_no_recon: 'No hay reconciliación en esta fecha. Ejecútela primero.',
          e_match_row_missing: 'Una fila seleccionada ya no está pendiente. Recargue la página.',
          e_match_already_matched: 'Una fila seleccionada ya fue conciliada por la reconciliación.' },
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
  // Only the plain, initial "Pending" (a break) blocks End process — the
  // carry-forward "Pending Payment"/"Pending Receivement" items are meant to
  // finalize and be brought forward to the next day.
  function isPlainPending(v) { return String(v || '').trim().toLowerCase() === 'pending'; }
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
      body.innerHTML = '<tr><td colspan="11" class="pr-empty">' + esc(t('empty')) + '</td></tr>';
      show(cardId, true);
      return;
    }
    body.innerHTML = rows.map(function (r, i) {
      var base =
        '<td>' + esc(r.le || '') + '</td>' +
        '<td>' + esc(r.product) + '</td>' +
        '<td>' + esc(r.jpm_cpty) + (r.branch ? '<span class="pr-branch-tag">' + esc(t(r.branch === 'b2b' ? 'branchTagB2b' : (r.branch === 'reversal' ? 'branchTagRev' : 'branchTag'))) + '</span>' : '') +
          (r.manual_match ? '<span class="pr-manual-tag" title="' + esc(r.matched_by || '') + '">' + esc(t('matchTag')) + '</span>' : '') + '</td>' +
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
      // Caixinha do match manual: só na linha com UM lado (a que o motor não casou).
      var selKey = tableKey + ':' + i;
      var canSel = !!sideValue(r);
      var sel = canSel && matchSel[selKey];
      var selCell = '<td class="pr-sel-col">' + (canSel
        ? '<input type="checkbox" class="form-check-input pr-sel" data-sel="' + esc(selKey) + '"' + (sel ? ' checked' : '') + '>'
        : '') + '</td>';
      return '<tr data-pr-table="' + esc(tableKey || '') + '" data-pr-index="' + i + '"' + (sel ? ' class="pr-selected"' : '') + '>' + selCell + base +
        '<td class="pr-status-cell">' + statusBadge(r.status) + '</td>' +
        '<td class="pr-comment-cell">' + esc(r.comment || '') + '</td>' +
        '<td class="pr-actions-cell">' + actions + '</td>' +
        '</tr>';
    }).join('');
    show(cardId, true);
  }

  function render(d) {
    if (d !== _lastData) matchSel = {};   // resultado novo → seleção antiga não vale
    _lastData = d || {};
    renderSummary(d.summary || []);
    renderList('prCardPendPay', 'prPendPayBody', 'prPendPayCount', d.pending_payment || [], 'pend', 'pay');
    renderList('prCardPendRec', 'prPendRecBody', 'prPendRecCount', d.pending_receivement || [], 'pend', 'rec');
    renderList('prCardSettled', 'prSettledBody', 'prSettledCount', d.settled || [], 'settled');
    show('prEmpty', false);
    // The final situation can only be e-mailed once there is a processed result.
    var endBtn = document.getElementById('prEndBtn');
    if (endBtn) endBtn.disabled = false;
    syncBranchBtn(d);
    syncMatchBtn();
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

  // ── Run: um botão só ────────────────────────────────────────────────────────
  // Com arquivos na dropzone, roda com ELES; sem nenhum, varre a pasta de
  // insumos — que era o que o botão "Import from folder" fazia. Quem decide é a
  // dropzone, não mais o usuário escolhendo entre dois botões.
  //
  // O servidor repete a MESMA regra (`_gather_sources` em recon_payrec.py:
  // `if mode == 'manual' and files:` … senão a pasta), então um `manual` sem
  // arquivo cairia na pasta de qualquer jeito. Mandar o modo certo daqui é o que
  // mantém as duas cópias dizendo a mesma coisa — e é o que decide se o
  // `clearDzFiles()` abaixo tem sentido.
  function run(btn) {
    var manual = dzFiles.length > 0;
    busy(btn, true, 'running');
    var opts;
    if (manual) {
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
          if (manual) clearDzFiles();   // uploads are now saved in the folder — clear the dropzone
          resetJustify();
          render(b);
          setText('prMeta', (b.meta || '') + (b.recon_date_fmt ? ('  ·  ' + b.recon_date_fmt) : ''));
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'success', title: t('done'), html: b.meta || '', confirmButtonColor: '#0066cc', timer: 1600, showConfirmButton: false });
        } else if (b.not_found) {
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'warning', title: t('noFiles'), html: b.detail || t('noFilesMsg'), confirmButtonColor: '#0066cc' });
        } else {
          // Erro com código sai pelo `_TRANS`; o `error` do servidor fica de fallback (§486).
          var msg = (b.code && t('e_' + b.code))
            ? t('e_' + b.code) + (b.params && b.params.reason ? '<br><small>' + esc(b.params.reason) + '</small>' : '')
            : (b.error ? esc(b.error) : t('netErr'));
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: msg, confirmButtonColor: '#0066cc' });
        }
      })
      .catch(function () { if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('failTitle'), html: t('netErr'), confirmButtonColor: '#0066cc' }); })
      .finally(function () { busy(btn, false); });
  }

  // ── Branch Settlement: rascunho do pedido de aprovação ao VP ────────────────
  // O botão só existe com liquidação contra a MGT na data de HOJE (o G&O é um
  // controle do T+0); um dia passado mostra a linha, mas não pede aprovação.
  function syncBranchBtn(d) {
    var btn = document.getElementById('prBranchBtn');
    if (!btn) return;
    var today = page.getAttribute('data-ref-date') || '';
    btn.hidden = !(d && d.branch && d.branch.has_settlement && today && refDate() === today);
  }

  function fmtParams(s, params) {
    return String(s || '').replace(/\{(\w+)\}/g, function (m, k) {
      return (params && params[k] != null) ? params[k] : m;
    });
  }

  function branchEmail(btn) {
    busy(btn, true, 'running');
    fetch('/reconciliation-payrec/branch-email', {
      method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recon_date: refDate() })
    })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
      .then(function (res) {
        var b = res.body || {};
        if (!(res.ok && b.success && b.b64)) {
          var msg = (b.code && t('e_' + b.code)) ? t('e_' + b.code) : (b.error ? esc(b.error) : t('netErr'));
          if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('branchTitle'), html: msg, confirmButtonColor: '#0066cc' });
          return;
        }
        var bin = atob(b.b64), bytes = new Uint8Array(bin.length);
        for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        var url = URL.createObjectURL(new Blob([bytes], { type: 'message/rfc822' }));
        var a = document.createElement('a');
        a.href = url; a.download = b.filename || 'Branch_Settlement_Reverse_Approval.eml';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
        // Aviso vem por código (§486); o `text` do servidor é só o fallback.
        var avisos = (b.warnings || []).map(function (w) {
          var tr = t('w_' + w.code);
          return '<li>' + esc(tr ? fmtParams(tr, w.params) : (w.text || w.code)) + '</li>';
        });
        if (typeof Swal !== 'undefined') Swal.fire({
          icon: avisos.length ? 'warning' : 'success', title: t('branchTitle'),
          html: esc(t('branchDone')) + (avisos.length ? '<br><br><b>' + esc(t('branchWarn')) +
                '</b><ul class="text-start mb-0">' + avisos.join('') + '</ul>' : ''),
          confirmButtonColor: '#0066cc'
        });
      })
      .catch(function () { if (typeof Swal !== 'undefined') Swal.fire({ icon: 'error', title: t('branchTitle'), html: t('netErr'), confirmButtonColor: '#0066cc' }); })
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

  // Count the rows that must block End process: only the plain, initial
  // "Pending" (a break needing justification). "Pending Payment"/"Pending
  // Receivement" are carry-forward items — they finalize and reappear the next
  // day, so they do NOT block. (Summary has no per-row status; "status Pending"
  // lives only in the pending tables.)
  function pendingCount() {
    if (!_lastData) return 0;
    var n = 0;
    (_lastData.pending_payment || []).forEach(function (r) { if (isPlainPending(r.status)) n++; });
    (_lastData.pending_receivement || []).forEach(function (r) { if (isPlainPending(r.status)) n++; });
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
          // "Pending" (→ justify on confirm) and the carry-forward status
          // (→ keep it so it reappears the next day until settled or justified).
          // The operator must pick the carry status manually.
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

  // ── Match manual (débito × crédito da mesma contraparte) ───────────────────
  // A mesa marca linhas do Pending Payment (débito) e do Pending Receivement
  // (crédito) que o motor não casou; o Swal mostra os dois lados, os totais e a
  // soma, e só deixa casar quando a soma fica dentro da tolerância e todas são
  // da mesma contraparte. O servidor confere tudo de novo — o JS é conveniência.
  var matchSel = {};
  var MATCH_TOL = parseFloat(page.getAttribute('data-match-tol')) || 1;

  function toNum(v) {
    if (typeof v === 'number') return v;
    var n = parseFloat(String(v).replace(/\./g, '').replace(',', '.'));
    return isNaN(n) ? 0 : n;
  }
  // { value, cpty, side } da linha com UM lado só; null quando tem os dois ou nenhum.
  function sideValue(r) {
    var hasJ = r.jpm_value !== '' && r.jpm_value != null;
    var hasC = r.client_value !== '' && r.client_value != null;
    if (hasJ === hasC) return null;
    return hasJ ? { value: toNum(r.jpm_value), cpty: r.jpm_cpty || '', side: 'jpm' }
                : { value: toNum(r.client_value), cpty: r.client || '', side: 'client' };
  }
  // A mesma chave do servidor (`_cpty_key`): só letras e dígitos, sem sufixo societário.
  function cptyKey(name) {
    var u = String(name || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase();
    u = u.replace(/[^A-Z0-9 ]/g, '').trim().replace(/\s+(SA|LTDA|ME|EPP)$/, '');
    return u.replace(/ /g, '');
  }
  function selectedRows(tableKey) {
    var arr = tableKey === 'pay' ? (_lastData && _lastData.pending_payment) : (_lastData && _lastData.pending_receivement);
    var out = [];
    Object.keys(matchSel).forEach(function (k) {
      var p = k.split(':');
      if (p[0] !== tableKey || !matchSel[k]) return;
      var i = parseInt(p[1], 10), r = (arr || [])[i], sv = r && sideValue(r);
      if (sv) out.push({ index: i, cpty: sv.cpty, value: sv.value, side: sv.side, table: tableKey });
    });
    return out.sort(function (a, b) { return a.index - b.index; });
  }
  function syncMatchBtn() {
    var btn = document.getElementById('prMatchBtn');
    // Duas linhas ou mais, em QUALQUER das tabelas (§623): perna JPM × perna
    // Client do mesmo lado também se casa, não só débito × crédito.
    if (btn) btn.disabled = selectedRows('pay').length + selectedRows('rec').length < 2;
  }
  function wireMatchSelection() {
    ['prPendPayBody', 'prPendRecBody'].forEach(function (bodyId) {
      var body = document.getElementById(bodyId);
      if (!body) return;
      body.addEventListener('change', function (e) {
        var cb = e.target.closest('.pr-sel');
        if (!cb) return;
        matchSel[cb.getAttribute('data-sel')] = cb.checked;
        var tr = cb.closest('tr'); if (tr) tr.classList.toggle('pr-selected', cb.checked);
        syncMatchBtn();
      });
    });
  }

  function matchError(b) {
    if (b && b.code && t('e_' + b.code)) return esc(fmtParams(t('e_' + b.code), b.params));
    return b && b.error ? esc(b.error) : t('netErr');
  }

  function openMatch(btn) {
    var deb = selectedRows('pay'), cred = selectedRows('rec'), all = deb.concat(cred);
    if (all.length < 2) {
      Swal.fire({ icon: 'info', title: t('matchTitle'), html: esc(t('e_match_need_two')), confirmButtonColor: '#0066cc' });
      return;
    }
    var sum = function (a) { return a.reduce(function (s, r) { return s + r.value; }, 0); };
    var jpm = all.filter(function (r) { return r.side === 'jpm'; });
    var cli = all.filter(function (r) { return r.side === 'client'; });
    var totJ = sum(jpm), totCl = sum(cli);
    var r2 = function (v) { return Math.round(v * 100) / 100; };
    var fits = function (v) { return Math.abs(v) <= MATCH_TOL + 1e-9; };
    // A MESMA regra do servidor (`_manual_balance`): JPM × Client fecha pela
    // diferença; linhas que se compensam (§617), pela soma.
    var diff = r2(totJ - totCl), soma = r2(totJ + totCl);
    var usaDiff = jpm.length && cli.length && (fits(diff) || !fits(soma));
    var net = usaDiff ? diff : soma;
    var names = {};
    all.forEach(function (r) { names[cptyKey(r.cpty)] = r.cpty; });
    var keys = Object.keys(names);
    var sameCpty = keys.length === 1 && keys[0] !== '';
    var within = fits(net);
    var num = function (v) { return '<td class="pr-num' + (v < 0 ? ' pr-neg' : '') + '">' + fmtNum(v) + '</td>'; };
    var n = Math.max(jpm.length, cli.length), rows = '';
    for (var i = 0; i < n; i++) {
      var d = jpm[i], c = cli[i];
      rows += '<tr>' +
        '<td>' + (d ? esc(d.cpty) : '') + '</td>' + (d ? num(d.value) : '<td></td>') +
        '<td>' + (c ? esc(c.cpty) : '') + '</td>' + (c ? num(c.value) : '<td></td>') + '</tr>';
    }
    var html =
      '<div class="table-responsive"><table class="pr-match-table">' +
        '<thead><tr><th>' + esc(t('matchJpm')) + ' — ' + esc(t('matchCpty')) + '</th><th>' + esc(t('matchValue')) + '</th>' +
        '<th>' + esc(t('matchClient')) + ' — ' + esc(t('matchCpty')) + '</th><th>' + esc(t('matchValue')) + '</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '<tfoot><tr><td>' + esc(t('matchTotal')) + ' ' + esc(t('matchJpm')) + '</td>' + num(totJ) +
        '<td>' + esc(t('matchTotal')) + ' ' + esc(t('matchClient')) + '</td>' + num(totCl) + '</tr></tfoot>' +
      '</table></div>' +
      '<div class="pr-match-sum">' + esc(t(usaDiff ? 'matchDiff' : 'matchSum')) + ': <b class="' + (net < 0 ? 'pr-neg' : '') + '">' + fmtNum(net) + '</b>' +
        '<span class="pr-match-chip ' + (within ? 'ok' : 'no') + '">' + esc(t(within ? 'matchWithin' : 'matchOver')) +
        ' · ' + esc(t('matchTol')) + ' ' + fmtNum(MATCH_TOL) + '</span></div>' +
      (sameCpty ? '' : '<div class="pr-match-err">' + esc(fmtParams(t('e_match_cpty_differs'),
        { names: keys.map(function (k) { return names[k] || '—'; }).join(', ') })) + '</div>');
    var allowed = within && sameCpty;
    Swal.fire({
      title: t('matchTitle'), html: html, width: 760,
      showCancelButton: true, confirmButtonText: t('matchDo'), cancelButtonText: t('cancel'),
      confirmButtonColor: '#198754', cancelButtonColor: '#6c757d',
      didOpen: function () { if (!allowed) Swal.getConfirmButton().disabled = true; },
      showLoaderOnConfirm: true,
      preConfirm: function () {
        if (!allowed) return false;
        return fetch('/reconciliation-payrec/manual-match', {
          method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ recon_date: refDate(),
                                 pay: deb.map(function (r) { return r.index; }),
                                 rec: cred.map(function (r) { return r.index; }) })
        }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); })
          .then(function (res) {
            if (!(res.ok && res.body && res.body.success)) { Swal.showValidationMessage(matchError(res.body)); return false; }
            return res.body;
          })
          .catch(function () { Swal.showValidationMessage(t('netErr')); return false; });
      },
      allowOutsideClick: function () { return !Swal.isLoading(); }
    }).then(function (r) {
      if (!r.isConfirmed || !r.value) return;
      render(r.value.data || _lastData);
      Swal.fire({ icon: 'success', title: t('matchTitle'), html: esc(t('matchDone')), confirmButtonColor: '#0066cc', timer: 1600, showConfirmButton: false });
    });
  }

  // ── Dropzone (holds files until Run) ────────────────────────────────────────
  var dzFiles = [];
  var dzRenderChips = function () {};        // set by wireDropzone; used to redraw the chips
  function clearDzFiles() { dzFiles.length = 0; dzRenderChips(); }

  // Com dois botões dava para ver qual caminho seria tomado; com um só, não —
  // então o Run diz no tooltip o que vai fazer, e isso acompanha a dropzone.
  function syncRunHint() {
    var btn = document.getElementById('prRunBtn');
    if (btn) btn.title = t(dzFiles.length ? 'runFiles' : 'runFolder');
  }
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
      syncRunHint();
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
    syncBranchBtn(null);
    matchSel = {}; syncMatchBtn();
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
    try { wireMatchSelection(); } catch (e) {}
    var matchBtn = document.getElementById('prMatchBtn');
    if (matchBtn) matchBtn.addEventListener('click', function () { if (typeof Swal !== 'undefined') openMatch(matchBtn); });
    var runBtn = document.getElementById('prRunBtn');
    var endBtn = document.getElementById('prEndBtn');
    if (runBtn) runBtn.addEventListener('click', function () { run(runBtn); });
    if (endBtn) endBtn.addEventListener('click', function () { endProcess(endBtn); });
    var branchBtn = document.getElementById('prBranchBtn');
    if (branchBtn) branchBtn.addEventListener('click', function () { branchEmail(branchBtn); });
    syncRunHint();
    try { loadLast(); } catch (e) {}
  });
})();

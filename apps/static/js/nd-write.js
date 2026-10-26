/* nd-write.js — a gravação das telas de New Deals SÓ muda a tela com o
 * sucesso do servidor (26/10/2026, HANDOFF §685; CLAUDE.md §430/§521).
 *
 * As seis telas (NDF Vanilla, FWD Start, Other Publisher, NDF Comm, Opt FXO,
 * Opt Comm) pintavam a linha antes da resposta e nunca a liam: Edit, Confirm,
 * Send, Apply Column e Delete em lote viravam "Saved"/"Approved"/"Sent" na
 * grade com o servidor recusando (409 da aba velha, 403 do 4-olhos, 404, 503
 * do banco ocupado), e o recarregamento desmentia. Aqui fica o que as seis
 * repetiriam: o pedido que rejeita quando o servidor não gravou, a frase da
 * recusa pelo código (en/br/es, CLAUDE.md §2 i18n) e o aviso do envio.
 */
(function (w) {
  'use strict';

  var TR = {
    en: {
      t_save: 'Could not save', t_confirm: 'Could not confirm', t_delete: 'Could not delete',
      t_send: 'Not sent', t_partial: 'Not done for every row', t_sent_unsaved: 'Sent — status not saved',
      e_status_regression: 'This deal was already sent — reload the page.',
      e_same_user: 'A different user must approve or send a deal you imported or last edited.',
      e_not_found: 'Deal not found on the server — reload the page.',
      e_deal_exists: 'This deal is already saved — edit it instead.',
      e_database_busy: 'The database is in use by another instance — try again in a few seconds.',
      e_database_unreadable: 'The database could not be read — check the application log.',
      e_not_sendable: 'Its status on the server does not allow sending ({status}) — reload the page.',
      e_row_not_found: 'Row not found on the server.',
      e_no_deal: 'This row has no Deal ID, so it cannot be saved.',
      e_request: 'Request failed.',
      w_sent_unsaved: 'The file is already in the B3 folder, but {n} deal(s) could not be marked as Sent. Do NOT send them again — reload the page.',
      w_refused: '{n} deal(s) cannot be sent. Nothing was written to the B3 folder:',
      w_partial: '{n} row(s) were left as they were:'
    },
    br: {
      t_save: 'Não foi possível salvar', t_confirm: 'Não foi possível confirmar', t_delete: 'Não foi possível excluir',
      t_send: 'Não enviado', t_partial: 'Nem todas as linhas foram feitas', t_sent_unsaved: 'Enviado — status não gravado',
      e_status_regression: 'Esta operação já foi enviada — recarregue a página.',
      e_same_user: 'Outro usuário precisa aprovar ou enviar uma operação que você importou ou editou por último.',
      e_not_found: 'Operação não encontrada no servidor — recarregue a página.',
      e_deal_exists: 'Esta operação já está gravada — use o Edit.',
      e_database_busy: 'O banco está em uso por outra instância — tente de novo em alguns segundos.',
      e_database_unreadable: 'O banco não pôde ser lido — veja o log da aplicação.',
      e_not_sendable: 'O status dela no servidor não permite o envio ({status}) — recarregue a página.',
      e_row_not_found: 'Linha não encontrada no servidor.',
      e_no_deal: 'Esta linha não tem Deal ID, então não pode ser gravada.',
      e_request: 'A requisição falhou.',
      w_sent_unsaved: 'O arquivo já está na pasta da B3, mas {n} operação(ões) não puderam ser marcadas como Sent. NÃO as envie de novo — recarregue a página.',
      w_refused: '{n} operação(ões) não podem ser enviadas. Nada foi gravado na pasta da B3:',
      w_partial: '{n} linha(s) ficaram como estavam:'
    },
    es: {
      t_save: 'No se pudo guardar', t_confirm: 'No se pudo confirmar', t_delete: 'No se pudo eliminar',
      t_send: 'No enviado', t_partial: 'No se hicieron todas las filas', t_sent_unsaved: 'Enviado — estado no guardado',
      e_status_regression: 'Esta operación ya fue enviada — recargue la página.',
      e_same_user: 'Otro usuario debe aprobar o enviar una operación que usted importó o editó por última vez.',
      e_not_found: 'Operación no encontrada en el servidor — recargue la página.',
      e_deal_exists: 'Esta operación ya está guardada — use Edit.',
      e_database_busy: 'La base está en uso por otra instancia — intente de nuevo en unos segundos.',
      e_database_unreadable: 'No se pudo leer la base — revise el log de la aplicación.',
      e_not_sendable: 'Su estado en el servidor no permite el envío ({status}) — recargue la página.',
      e_row_not_found: 'Fila no encontrada en el servidor.',
      e_no_deal: 'Esta fila no tiene Deal ID, así que no se puede guardar.',
      e_request: 'La solicitud falló.',
      w_sent_unsaved: 'El archivo ya está en la carpeta de B3, pero {n} operación(es) no se pudieron marcar como Sent. NO las envíe de nuevo — recargue la página.',
      w_refused: '{n} operación(es) no se pueden enviar. No se escribió nada en la carpeta de B3:',
      w_partial: '{n} fila(s) quedaron como estaban:'
    }
  };

  function lang() {
    var l = 'en';
    try { l = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { l = 'en'; }
    return TR[l] ? l : 'en';
  }
  function t(k, p) {
    var s = TR[lang()][k] || TR.en[k] || k;
    if (p) { for (var x in p) { if (Object.prototype.hasOwnProperty.call(p, x)) s = s.split('{' + x + '}').join(String(p[x])); } }
    return s;
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function codeOf(status, j) {
    var c = String((j && (j.error || j.code)) || '');
    if (/^[a-z_]+$/.test(c)) return c;
    if (status === 404) return 'not_found';
    if (status === 503) return 'database_busy';
    return '';
  }
  // A frase do código; sem código conhecido, a mensagem que o servidor deu.
  function reason(code, extra, fallback) {
    if (code && TR.en['e_' + code]) return t('e_' + code, extra || {});
    return fallback || code || t('e_request');
  }
  function errText(status, j) {
    var code = codeOf(status, j);
    var txt = reason(code, { status: (j && j.status) || '' }, (j && (j.message || j.error)) || '');
    return txt + (status ? ' (HTTP ' + status + ')' : '');
  }

  // fetch que RESOLVE só quando o servidor diz que gravou; rejeita com o motivo.
  w.otcNdWrite = function (url, method, body) {
    var opts = { method: method || 'POST', credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(url, opts).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.ok && j.success !== false && j.ok !== false) return j;
        var e = new Error(errText(r.status, j));
        e.status = r.status; e.body = j; e.code = codeOf(r.status, j);
        throw e;
      });
    });
  };

  // Erro da gravação na tela: `kind` = save | confirm | delete | send.
  w.otcNdFail = function (kind, err) {
    var txt = (err && err.message) || String(err || '');
    if (err && !err.status && err.name === 'TypeError') txt = t('e_request') + ' ' + txt;
    Swal.fire({ title: t('t_' + kind), text: txt, icon: 'error', confirmButtonColor: '#dc3545' });
  };

  // A chave de uma linha como o servidor a devolve (`done`, `marked`…).
  w.otcNdKey = function (deal, client) {
    return String(deal == null ? '' : deal).trim() + '|' + String(client == null ? '' : client).trim();
  };
  w.otcNdKeySet = function (items, dealField) {
    var s = {};
    (items || []).forEach(function (x) { s[w.otcNdKey(x[dealField || 'deal'], x.client)] = x; });
    return s;
  };

  function lista(items, dealField) {
    return '<ul class="text-start mb-0 mt-2">' + (items || []).slice(0, 15).map(function (x) {
      var d = x[dealField || 'deal'] || '—';
      var why = reason(x.error || '', { status: x.status || '' }, x.reason || '');
      return '<li><b>' + esc(d) + '</b>' + (x.client ? ' — ' + esc(x.client) : '') +
             (why ? '<br><small>' + esc(why) + '</small>' : '') + '</li>';
    }).join('') + ((items || []).length > 15 ? '<li>…</li>' : '') + '</ul>';
  }

  // O que o bulk (patch/delete) NÃO fez: recusados pelo 4-olhos e não achados.
  // Devolve true quando mostrou o aviso.
  w.otcNdPartial = function (res, dealField) {
    var f = dealField || 'deal_id';
    var faltou = (res.refused || []).concat((res.not_found || []).map(function (x) {
      return Object.assign({ error: 'not_found' }, x);
    }));
    if (!faltou.length) return false;
    Swal.fire({ title: t('t_partial'), icon: 'warning', confirmButtonColor: '#6c757d',
                html: esc(t('w_partial', { n: faltou.length })) + lista(faltou, f) });
    return true;
  };

  // O resultado do send-conecta: recusa ANTES do arquivo (409) ou status que
  // não gravou DEPOIS dele. Devolve true quando mostrou o aviso.
  w.otcNdSendIssues = function (res) {
    if (res && res.refused && res.refused.length) {
      Swal.fire({ title: t('t_send'), icon: 'warning', confirmButtonColor: '#6c757d',
                  html: esc(t('w_refused', { n: res.refused.length })) + lista(res.refused) });
      return true;
    }
    if (res && res.status_failed && res.status_failed.length) {
      Swal.fire({ title: t('t_sent_unsaved'), icon: 'warning', confirmButtonColor: '#dc3545',
                  html: esc(t('w_sent_unsaved', { n: res.status_failed.length })) + lista(res.status_failed) });
      return true;
    }
    return false;
  };

  w.otcNdT = t;
})(window);

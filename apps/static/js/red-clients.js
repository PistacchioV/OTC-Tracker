/* RED Clients — Rapid Exposure nas telas de LIQUIDAÇÃO (§730).
 *
 * 1. A PÍLULA: toda DataTable da tela tem a coluna da contraparte achada pelo
 *    TÍTULO (Counterparty, Contraparte, Cliente…) e, a cada desenho, o nome de
 *    contraparte RED ganha a pílula vermelha AO LADO — só no DOM: as telas
 *    releem o nome da célula para gerar o aviso (`decodeHtml(d[3])`), e o
 *    texto "RED" mora no `::before` da `.otc-red-pill`, fora do Export.
 * 2. O AVISO: a resposta de um aviso de liquidação gerado com cliente RED traz
 *    o cabeçalho `X-Red-Clients` (o servidor decide, pelos avisos que de fato
 *    saíram — `platform/red_clients.anota_avisos`). Aqui o `fetch` é
 *    embrulhado: antes de a tela receber a resposta, um aviso por cliente.
 *
 * A comparação de nome é a MESMA do servidor (`platform/red_clients.name_key`):
 * sem acento, pontuação e sufixo societário — o check_red_clients a executa no
 * node e compara.
 */
(function () {
  'use strict';
  if (window.otcRed) return;

  var SUFIXOS = [' SA', ' S A', ' LTDA', ' LTD', ' INC', ' LLC', ' PLC', ' AG', ' NV', ' BV'];
  function nameKey(nome) {
    var s = String(nome == null ? '' : nome).normalize('NFKD').replace(/[̀-ͯ]/g, '').toUpperCase();
    s = s.replace(/[^A-Z0-9]/g, ' ').replace(/\s+/g, ' ').trim();
    var mudou = true;
    while (mudou && s) {
      mudou = false;
      for (var i = 0; i < SUFIXOS.length; i++) {
        var suf = SUFIXOS[i];
        if (s.length > suf.length && s.slice(-suf.length) === suf) { s = s.slice(0, -suf.length).trim(); mudou = true; }
      }
    }
    return s;
  }

  // ── textos (o idioma da tela) ─────────────────────────────────────────────
  var _TRANS = {
    en: { title: 'RED Client',
          msg: 'Client {name} is on the RED Clients list — please request Credit approval before making the payment.' },
    br: { title: 'Cliente RED',
          msg: 'Cliente {name} na lista de RED Clientes, favor solicitar aprovação de Crédito antes de efetuar o pagamento.' },
    es: { title: 'Cliente RED',
          msg: 'Cliente {name} en la lista de RED Clientes, por favor solicite la aprobación de Crédito antes de efectuar el pago.' }
  };
  function t(k) {
    var lang = 'en';
    try { lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    return (_TRANS[lang] || _TRANS.en)[k] || _TRANS.en[k];
  }
  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ── quem está RED ─────────────────────────────────────────────────────────
  var KEYS = null;
  var pronto = fetch('/api/red-clients', { credentials: 'same-origin' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) {
      KEYS = {};
      ((j && j.clients) || []).forEach(function (c) { var k = nameKey(c.name); if (k) KEYS[k] = 1; });
      decorateAll();
    })
    .catch(function () { KEYS = {}; });
  function isRed(nome) { var k = nameKey(nome); return !!(KEYS && k && KEYS[k]); }

  // ── a pílula na coluna da contraparte ─────────────────────────────────────
  var CPTY_HEADERS = { COUNTERPARTY: 1, CONTRAPARTE: 1, CLIENTE: 1, CLIENT: 1, CPTYNAME: 1,
                       NMCOUNTERPARTY: 1, COUNTERPARTYNAME: 1, CONTRAPARTENOMESIMPL: 1,
                       NOMEDACONTRAPARTE: 1, NOMECONTRAPARTE: 1 };
  function headerKey(th) {
    return String((th && th.textContent) || '').normalize('NFKD').replace(/[̀-ͯ]/g, '')
      .toUpperCase().replace(/[^A-Z0-9]/g, '');
  }
  function cptyColumns(api) {
    var cols = [];
    api.columns().every(function (i) {
      var th = this.header();
      if (th && CPTY_HEADERS[headerKey(th)]) cols.push(i);
    });
    return cols;
  }
  function cellName(td) {
    var clone = td.cloneNode(true);
    Array.prototype.forEach.call(clone.querySelectorAll('.otc-red-pill'), function (p) { p.remove(); });
    return clone.textContent.trim();
  }
  function decorate(api) {
    if (!KEYS) return;
    var cols = cptyColumns(api);
    if (!cols.length) return;
    cols.forEach(function (ci) {
      api.cells(null, ci, { page: 'current' }).nodes().each(function (td) {
        if (!td) return;
        var has = td.querySelector('.otc-red-pill');
        var red = isRed(cellName(td));
        if (red && !has) {
          var pill = document.createElement('span');
          pill.className = 'otc-red-pill';
          pill.setAttribute('data-tag', 'RED');
          pill.setAttribute('title', t('title'));
          td.appendChild(pill);
        } else if (!red && has) {
          has.remove();
        }
      });
    });
  }
  function decorateAll() {
    if (!window.jQuery || !jQuery.fn.dataTable) return;
    jQuery.fn.dataTable.tables().forEach(function (tb) { decorate(new jQuery.fn.dataTable.Api(tb)); });
  }
  function ligar() {
    if (!window.jQuery || !jQuery.fn.dataTable) return;
    jQuery(document).on('draw.dt.otcred init.dt.otcred', function (e, settings) {
      if (e.namespace !== 'dt') return;
      decorate(new jQuery.fn.dataTable.Api(settings));
    });
    decorateAll();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ligar);
  else ligar();

  // ── o aviso antes do resultado do aviso de liquidação ─────────────────────
  function lerCabecalho(resp) {
    try {
      var v = resp.headers.get('X-Red-Clients');
      if (!v) return [];
      var bin = atob(v), bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      var nomes = JSON.parse(new TextDecoder('utf-8').decode(bytes));
      return Array.isArray(nomes) ? nomes : [];
    } catch (e) { return []; }
  }
  function avisar(nomes) {
    var html = nomes.map(function (n) {
      return '<div class="text-start mb-2"><span class="otc-red-pill" data-tag="RED" style="margin:0 .4rem 0 0"></span>' +
        esc(t('msg').replace('{name}', n)) + '</div>';
    }).join('');
    if (!window.Swal) { window.alert(nomes.map(function (n) { return t('msg').replace('{name}', n); }).join('\n')); return Promise.resolve(); }
    return Swal.fire({ icon: 'warning', title: t('title'), html: html, confirmButtonColor: '#d92d3a' });
  }
  if (window.fetch) {
    var f0 = window.fetch;
    window.fetch = function () {
      return f0.apply(this, arguments).then(function (resp) {
        var nomes = lerCabecalho(resp);
        if (!nomes.length) return resp;
        return avisar(nomes).then(function () { return resp; }, function () { return resp; });
      });
    };
  }

  window.otcRed = { ready: pronto, isRed: isRed, nameKey: nameKey, decorateAll: decorateAll };
})();

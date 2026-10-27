/*
 * swap-deal.js — o que as telas de SWAP (Bullet e as do catálogo) dizem do
 * deal igual, para não divergirem (§698):
 *
 *   otcSwapCurveText(e, 'A'|'B') — a curva como a equipe a lê no card:
 *     "CDI + 3.00%", "110% CDI", "6M TERM SFR - 0.50%". O percentual só
 *     aparece fora dos 100%; a taxa, só quando há.
 *
 *   otcSwapTypeLabel(v, t) — o Type gravado (o termo da B3, "Fluxo de Caixa",
 *     "Pagamento Final") no idioma da tela; o dado não muda.
 *
 *   otcSwapB2BFund(e) — o fundo do B2B de um deal contra cliente, pela LOB:
 *     CEM → LAWTON, EDG → ATACAMA; '' sem LOB (não se chuta).
 *
 *   otcSwapIsB2B(e) — o deal já é um B2B (LE Atacama/Lawton)?
 *
 *   otcSwapB2B(e) — o deal do B2B, pronto para o modal de Add: as pernas
 *     ATIVA e PASSIVA trocadas (a Curva A do Banco passa a ser a que ele
 *     paga ao cliente, que é a que ele recebe do fundo), a LE e o Client = o
 *     fundo, quem paga o prêmio invertido, e sem nada que identifique a
 *     operação do cliente (Deal, B3 ID, SPN, conta). null sem fundo.
 *
 *   otcSwapModalPrep(grid, e) / otcSwapModalValue(el, e) — os campos do modal
 *     de Edit/Add no formato da equipe: valores #,##0.00 (Notional, Notional
 *     Foreign Ccy, Premium Amount), FX Start #0.00000000, o Client Tax ID com a
 *     máscara de CNPJ, e o VCP/Vanilla Holder pela CONTA B3 de quem carrega a
 *     perna (só leitura: o texto do DT segue gravado, é o que o e-mail lê). O
 *     `Value` devolve o dado CRU (sem milhar, sem pontuação), e o valor que só
 *     mudou de formato volta como estava — o Edit não vira Amend por isso.
 *
 *   otcSwapSetAccounts(map) — as contas PRÓPRIAS do `b3-accounts` ({LE: conta}),
 *     que a busca da página devolve (`own_accounts`).
 *
 *   otcSwapFlags(e, t) — as marcas do card (Forward Start, Atualização de
 *     Notional, Curva VCP, Prêmio): detectadas pelos campos, corrigíveis à
 *     mão (`SwapFlags` no deal), §701.
 *
 *   otcSwapModalLayout(cells, t) — os campos do modal agrupados em blocos
 *     (identificação, datas e valores, prêmio, atualização de notional, as
 *     curvas lado a lado, VCP, observações; o resto em "Other"), §701.
 */
(function () {
  'use strict';

  var FUND_BY_LOB = { CEM: 'LAWTON', EDG: 'ATACAMA' };
  var FUND_NAME = { LAWTON: 'Lawton', ATACAMA: 'Atacama' };

  function num(v) {
    var n = parseFloat(String(v == null ? '' : v).replace(',', '.'));
    return isNaN(n) ? null : n;
  }

  // 3 → "3.00", 0.9123 → "0.9123": duas casas no mínimo, até quatro
  function pct(n) {
    var s = String(+n.toFixed(4));
    return (s.split('.')[1] || '').length < 2 ? n.toFixed(2) : s;
  }

  window.otcSwapCurveText = function (e, x) {
    var p = 'Curve' + x;
    var nome = String(e[p] || e[p + 'Category'] || '').trim();
    if (!nome) return '';
    var perc = num(e[p + 'Pct']), taxa = num(e[p + 'Rate']);
    var s = (perc && Math.abs(perc - 100) > 1e-9 ? pct(perc) + '% ' : '') + nome;
    if (taxa) {
      var neg = (String(e[p + 'Sign'] || '+').trim() === '-') !== (taxa < 0);
      s += (neg ? ' - ' : ' + ') + pct(Math.abs(taxa)) + '%';
    }
    return s;
  };

  var TYPE_KEY = { 'FLUXO DE CAIXA': ['nd-swap-type-cashflow', 'Cash Flow'],
                   'PAGAMENTO FINAL': ['nd-swap-type-bullet', 'Bullet'] };
  window.otcSwapTypeLabel = function (v, t) {
    var k = TYPE_KEY[String(v || '').trim().toUpperCase()];
    return k ? (t ? t(k[0], k[1]) : k[1]) : String(v || '');
  };

  window.otcSwapIsB2B = function (e) {
    var le = String((e && e.LE) || '').trim().toUpperCase();
    return le === 'ATACAMA' || le === 'LAWTON';
  };

  window.otcSwapB2BFund = function (e) {
    return FUND_BY_LOB[String((e && e.LOB) || '').trim().toUpperCase()] || '';
  };

  var OURS = /\b(JP\s*MORGAN|JPM|BANCO|BANK)\b/i;

  window.otcSwapB2B = function (e) {
    var fund = window.otcSwapB2BFund(e);
    if (!fund) return null;
    var d = JSON.parse(JSON.stringify(e || {}));
    // as pernas: todo campo CurveA… troca com o CurveB… de mesmo sufixo
    var suf = {};
    Object.keys(e).forEach(function (k) { var m = /^Curve[AB](.*)$/.exec(k); if (m) suf[m[1]] = 1; });
    Object.keys(suf).forEach(function (s) {
      var a = e['CurveA' + s], b = e['CurveB' + s];
      d['CurveA' + s] = b == null ? '' : b;
      d['CurveB' + s] = a == null ? '' : a;
    });
    // quem carrega cada perna no DT (texto) acompanha a troca
    var vh = e.VcpHolder, nh = e.VanillaHolder;
    if (vh != null || nh != null) { d.VcpHolder = nh == null ? '' : nh; d.VanillaHolder = vh == null ? '' : vh; }
    // o prêmio também inverte: o cliente pagava ao Banco → no B2B o Banco paga
    // ao fundo; o Banco pagava ao cliente → o fundo paga ao Banco
    if (String(e.PremiumPayer || '').trim()) {
      d.PremiumPayer = OURS.test(e.PremiumPayer) ? FUND_NAME[fund] : 'Banco';
    }
    d.LE = fund;
    d.Client = FUND_NAME[fund];
    ['_id', 'Deal', 'B3ID', 'Status', 'Maker', 'Checker', 'SPN', 'ClientDT', 'ClientAccount',
     'ClientTaxId', 'ClientRefData', 'ClientAccountNote', 'SentFiles', 'MappedBy', 'MappedAt',
     'MyNumber', 'MyNumberMirror', 'FlowMyNumber', 'FlowMyNumberMirror', 'PremiumMyNumber',
     'PremiumMyNumberMirror', 'Pair', 'Title'].forEach(function (k) { if (k in d) d[k] = ''; });
    return d;
  };

  // ── As MARCAS do card (§701) ───────────────────────────────────────────
  // O que a equipe confere de relance num swap: Forward Start, Atualização de
  // Notional, Curva VCP e Prêmio. Cada uma é DETECTADA pelos campos do deal e
  // pode ser corrigida à mão quando a leitura errou — a correção vai no deal
  // (`SwapFlags`, {chave: true|false}) e o card a destaca. O arquivo da B3
  // continua saindo dos CAMPOS: a marca é a leitura da equipe, não um campo.
  function iso10(v) {
    v = String(v == null ? '' : v).trim();
    var m = /^(\d{2})\/(\d{2})\/(\d{4})/.exec(v);
    return m ? m[3] + '-' + m[2] + '-' + m[1] : v.slice(0, 10);
  }
  function up(v) { return String(v == null ? '' : v).trim().toUpperCase(); }
  window.otcSwapHasPremium = function (e) {
    var s = up(e && e.PremiumSchedule);
    return !!(parseFloat(e && e.PremiumAmount) || s === 'SIM' || s === 'YES' || s === 'S' || s === 'Y');
  };
  var FLAGS = [
    { k: 'fwd', key: 'nd-swb-flag-fwd', d: 'Forward Start',
      det: function (e) { var a = iso10(e.StartDate), b = iso10(e.TradeDate); return !!(a && b && a !== b); } },
    { k: 'notional', key: 'nd-swb-flag-notional', d: 'Notional Update',
      det: function (e) { return !!(String(e.NotionalIndex || '').trim() && String(e.NotionalObsDate || '').trim()); } },
    { k: 'vcp', key: 'nd-swb-flag-vcp', d: 'VCP Curve',
      det: function (e) { return up(e.CurveACategory) === 'VCP' || up(e.CurveBCategory) === 'VCP'; } },
    { k: 'premium', key: 'nd-swb-flag-premium', d: 'Premium',
      det: function (e) { return window.otcSwapHasPremium(e); } }
  ];
  window.OTC_SWAP_FLAG_KEYS = FLAGS.map(function (f) { return f.k; });
  // → [{k, label, detected, on, manual, title}]; `t` traduz (chave, padrão)
  window.otcSwapFlags = function (e, t) {
    e = e || {};
    var ov = (e.SwapFlags && typeof e.SwapFlags === 'object') ? e.SwapFlags : {};
    return FLAGS.map(function (f) {
      var det = f.det(e);
      var manual = typeof ov[f.k] === 'boolean' && ov[f.k] !== det;
      var on = manual ? ov[f.k] : det;
      var tip = manual
        ? (t ? t('nd-swb-flag-manual', 'Marked by hand — the B3 file follows the deal fields; review them.') : 'Marked by hand')
        : (t ? t('nd-swb-flag-auto', 'Detected from the deal fields — click to correct.') : 'Detected');
      return { k: f.k, label: t ? t(f.key, f.d) : f.d, detected: det, on: on, manual: manual, title: tip };
    });
  };

  // ── O modal em BLOCOS (§701) ───────────────────────────────────────────
  // Os campos do Edit/Add agrupados pelo que a equipe procura: identificação,
  // datas e valores, prêmio, atualização de notional, as duas curvas lado a
  // lado, a VCP e as observações. Campo que nenhum bloco nomeia vai para
  // "Other" — coluna nova aparece, nunca some. `cells` = {campo: HTML do
  // campo (rótulo + input)}, na ordem da página.
  var BLOCKS = [
    { k: 'id', key: 'nd-swb-blk-id', d: 'Identification', icon: 'ti-id-badge-2',
      f: ['TradeDate', 'LE', 'LOB', 'Deal', 'B3ID', 'Type', 'Client', 'ClientDT', 'SPN', 'ClientAccount',
          'ClientTaxId', 'Adhesion', 'Functionality', 'Tranche', 'Block', 'Booking', 'Venue', 'Direction',
          'MyNumber', 'Subject'] },
    { k: 'terms', key: 'nd-swb-blk-terms', d: 'Dates & Notional', icon: 'ti-calendar-dollar',
      f: ['StartDate', 'MaturityDate', 'Currency', 'Notional', 'NotionalUSD', 'FxRate', 'FXStart', 'NotionalFC',
          'Reset', 'AmortizationType', 'Flows'] },
    { k: 'premium', key: 'nd-swb-blk-premium', d: 'Premium', icon: 'ti-coin',
      f: ['PremiumSchedule', 'PremiumDate', 'PremiumPayer', 'PremiumAmount'] },
    { k: 'notional', key: 'nd-swb-blk-notional', d: 'Notional Update', icon: 'ti-refresh-dot',
      f: ['NotionalIndex', 'NotionalObsDate', 'NotionalDescription'] },
    { k: 'curveA', key: 'nd-swb-blk-curvea', d: 'Curve A', icon: 'ti-chart-line', half: true, prefix: 'CurveA' },
    { k: 'curveB', key: 'nd-swb-blk-curveb', d: 'Curve B', icon: 'ti-chart-line', half: true, prefix: 'CurveB' },
    { k: 'legs', key: 'nd-swb-blk-legs', d: 'Legs', icon: 'ti-arrows-exchange',
      f: ['FixedRate', 'FixedPayer', 'WePay', 'WeRec', 'Accruals', 'Payments', 'FxFixing', 'FxSettlement'] },
    { k: 'vcp', key: 'nd-swb-blk-vcp', d: 'VCP', icon: 'ti-chart-candle',
      f: ['VcpHolder', 'VanillaHolder', 'VcpCurve', 'VcpCode', 'VcpCategory', 'VcpDescription', 'InitialPrice',
          'InfoSource', 'QuoteDate', 'QuoteDateCode', 'Denomination1', 'Denomination2', 'Denomination3', 'VcpText'] },
    { k: 'notes', key: 'nd-swb-blk-notes', d: 'Observations', icon: 'ti-notes', f: ['Observations'] }
  ];
  var WIDE = { VcpText: 'col-12', Observations: 'col-12', Subject: 'col-12', VcpDescription: 'col-md-6',
               Denomination1: 'col-md-6', Denomination2: 'col-md-6', Denomination3: 'col-md-6',
               NotionalDescription: 'col-md-6', Client: 'col-md-6', ClientDT: 'col-md-6' };
  function escH(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  window.otcSwapModalLayout = function (cells, t) {
    var usado = {};
    function bloco(b, campos) {
      if (!campos.length) return '';
      var col = b.half ? 'col-12 col-lg-6' : 'col-12';
      var w = b.half ? 'col-6 col-md-4' : 'col-6 col-md-4 col-xl-2';
      return '<div class="' + col + '"><section class="otc-swap-blk" data-blk="' + b.k + '">' +
        '<h6 class="otc-swap-blk__title"><i class="ti ' + b.icon + '"></i>' +
        escH(t ? t(b.key, b.d) : b.d) + '</h6><div class="row g-2">' +
        campos.map(function (f) {
          var cw = WIDE[f] || w;
          if (b.half && cw === 'col-md-6') cw = 'col-12 col-md-8';
          return '<div class="' + cw + '">' + cells[f] + '</div>';
        }).join('') + '</div></section></div>';
    }
    var html = BLOCKS.map(function (b) {
      var campos = b.prefix
        ? Object.keys(cells).filter(function (f) { return f.indexOf(b.prefix) === 0 && !usado[f]; })
        : (b.f || []).filter(function (f) { return cells[f] != null && !usado[f]; });
      campos.forEach(function (f) { usado[f] = 1; });
      return bloco(b, campos);
    }).join('');
    var resto = Object.keys(cells).filter(function (f) { return !usado[f]; });
    return html + bloco({ k: 'other', key: 'nd-swb-blk-other', d: 'Other', icon: 'ti-dots' }, resto);
  };

  // ── O modal ────────────────────────────────────────────────────────────
  var OWN = {};
  window.otcSwapSetAccounts = function (m) { if (m && typeof m === 'object') OWN = m; };

  var MONEY = { Notional: 1, NotionalFC: 1, PremiumAmount: 1 };
  var DEC = { FXStart: 8 };
  var HOLDER = { VcpHolder: 1, VanillaHolder: 1 };

  function digits(v) { return String(v == null ? '' : v).replace(/\D/g, ''); }
  function rawNum(v) { return String(v == null ? '' : v).replace(/,/g, '').trim(); }

  // 73760009 → 73760.00-9 (a grafia da B3)
  window.otcSwapAccountText = function (v) {
    var d = digits(v);
    return d.length === 8 ? d.slice(0, 5) + '.' + d.slice(5, 7) + '-' + d.slice(7) : d;
  };

  function cnpjText(d) {
    var t = d.slice(0, 2);
    if (d.length > 2) t += '.' + d.slice(2, 5);
    if (d.length > 5) t += '.' + d.slice(5, 8);
    if (d.length > 8) t += '/' + d.slice(8, 12);
    if (d.length > 12) t += '-' + d.slice(12, 14);
    return t;
  }
  // CNPJ só quando o texto é número; Tax ID estrangeiro ou N/A fica como veio
  function taxText(v) {
    v = String(v == null ? '' : v);
    if (!v.trim() || /[A-Za-z]/.test(v)) return v;
    var d = digits(v);
    return d.length > 11 ? cnpjText(d.slice(-14).padStart(14, '0')) : cnpjText(d);
  }

  function numText(f, v) {
    var n = parseFloat(rawNum(v));
    if (isNaN(n) || !String(v == null ? '' : v).trim()) return v == null ? '' : String(v);
    if (MONEY[f]) return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return n.toFixed(DEC[f]);
  }

  // A conta B3 de quem carrega a perna: o Banco é a conta própria da JPM; o
  // outro é a contraparte da linha — o fundo no B2B, a conta do cliente (ou a
  // guarda-chuva) contra cliente.
  window.otcSwapHolderAccount = function (e, nome) {
    nome = String(nome || '').trim();
    if (!nome) return '';
    if (OURS.test(nome)) return OWN.JPM || '';
    var le = String((e && e.LE) || '').trim().toUpperCase();
    if (FUND_NAME[le]) return OWN[le] || digits(e.ClientAccount);
    return digits(e && e.ClientAccount);
  };

  window.otcSwapModalPrep = function (grid, e) {
    if (!grid) return;
    e = e || {};
    grid.querySelectorAll('input[data-f]').forEach(function (el) {
      var f = el.getAttribute('data-f');
      if (MONEY[f] || DEC[f]) {
        el.value = numText(f, el.value);
        el.classList.add('text-end');
        el.addEventListener('focus', function () { el.value = rawNum(el.value); });
        el.addEventListener('blur', function () { el.value = numText(f, el.value); });
      } else if (f === 'ClientTaxId') {
        el.value = taxText(el.value);
        el.setAttribute('placeholder', '00.000.000/0000-00');
        el.setAttribute('autocomplete', 'off');
        el.addEventListener('input', function () {
          if (/[A-Za-z]/.test(el.value)) return;
          var t = cnpjText(digits(el.value).slice(0, 14));
          if (t !== el.value) el.value = t;
        });
      } else if (HOLDER[f]) {
        var acc = window.otcSwapHolderAccount(e, e[f]);
        el.value = acc ? window.otcSwapAccountText(acc) : '';
        el.title = String(e[f] || '');
        el.readOnly = true;
        el.setAttribute('data-view', '1');      // mostra a conta; não volta ao servidor
      }
    });
  };

  // O dado cru do campo; `null` = o campo não volta ao servidor
  window.otcSwapModalValue = function (el, e) {
    var f = el.getAttribute('data-f'), v = (el.value || '').trim();
    var orig = e && e[f] != null ? String(e[f]) : '';
    // o holder mostra a conta e devolve o texto do DT como estava (o Create B2B
    // leva o dele para o deal novo)
    if (el.getAttribute('data-view')) return orig || null;
    if (MONEY[f] || DEC[f]) {
      v = rawNum(v);
      var a = parseFloat(v), b = parseFloat(rawNum(orig));
      return !isNaN(a) && !isNaN(b) && Math.abs(a - b) < 1e-9 ? orig : v;
    }
    if (f === 'ClientTaxId' && !/[A-Za-z]/.test(v)) {
      v = digits(v);
      return v.replace(/^0+/, '') === digits(orig).replace(/^0+/, '') ? orig : v;
    }
    return v;
  };
})();

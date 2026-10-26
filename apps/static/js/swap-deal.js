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

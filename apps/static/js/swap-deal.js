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
})();

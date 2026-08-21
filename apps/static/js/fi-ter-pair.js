/* fi-ter-pair.js — cópia no navegador da regra de par de pernas do TER
   (routes.py: _ter_le_side / _ter_le_pair / _fi_variant_key). O preview de
   duplo clique escolhe a MESMA variante de template do File Interpreter que o
   arquivo gerado usa — as duas cópias têm de concordar campo a campo
   (scripts/tests/check_fi_variants.py compara as duas). */
(function () {
    'use strict';

    /* Entidades do grupo pelo cadastro le-spn (LE → razão social): resolve o
       nome que nenhuma heurística de substring saberia — 'JPMORGAN CHASE
       BANK, N.A. - SAO PAULO BRANCH' é a MGT, e o regex do JPM casaria com o
       'JPMORGAN' antes. Carregado uma vez por página; sem fetch (jsc) ou com
       falha, ficam só as heurísticas. */
    var ENTITIES = [];
    function normName(s) {
        return String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    }
    function setEntities(rows) {
        ENTITIES = [];
        (rows || []).forEach(function (r) {
            var nm = normName(r['NAME']);
            var le = String(r['LE'] || '').toUpperCase();
            if (!nm || !le) return;
            var tok = ['LAWTON', 'ATACAMA', 'MGT', 'JPM'].filter(function (t) {
                return le.indexOf(t) !== -1;
            })[0];
            if (tok) ENTITIES.push({ name: nm, side: tok });
        });
    }
    if (typeof fetch === 'function') {
        fetch('/api/mappings/le-spn', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (d) { if (d && d.success && d.rows) setEntities(d.rows); })
            .catch(function () {});
    }

    /* Lado de um par a partir de um nome (LE ou contraparte): JPM, MGT,
       LAWTON, ATACAMA — ou null para cliente externo. O cadastro le-spn
       (razão social exata, normalizada) vence; o resto são as substrings dos
       testes de conta do gerador (_is_jpm/_is_mgt/_is_lawton). */
    function side(name) {
        var u = String(name || '').toUpperCase();
        if (!u.replace(/\s+/g, '')) return null;
        var nm = normName(name);
        for (var i = 0; i < ENTITIES.length; i++) {
            if (ENTITIES[i].name === nm) return ENTITIES[i].side;
        }
        if (u.indexOf('LAWTON') !== -1) return 'LAWTON';
        if (u.indexOf('ATACAMA') !== -1) return 'ATACAMA';
        if (u.indexOf('MGT') !== -1) return 'MGT';
        if (/J\.?P\.?\s*MORGAN/.test(u) || u.trim() === 'JPM' || u.trim() === 'BANCO') return 'JPM';
        return null;
    }

    /* 'mgt × Jpm ' ≡ 'MGT X JPM' — cega a caixa, espaço extra e ao sinal
       de vezes, como _fi_le_pair_norm no servidor. */
    function norm(pair) {
        return String(pair || '').toUpperCase().replace(/×/g, 'X')
            .replace(/\s+/g, ' ').trim();
    }

    /* Par 'NOSSA PERNA x CONTRAPARTE' de um deal — a mesma regra do bucket
       do gerador: LE Lawton (ou contraparte JPM = perna espelhada) → LAWTON;
       LE MGT → MGT; senão JPM. Contraparte fora do grupo é CLI. */
    function pairOf(le, client) {
        var leU = String(le || '').toUpperCase();
        var ours;
        if (leU.indexOf('LAWTON') !== -1) ours = 'LAWTON';
        else if (side(client) === 'JPM') ours = 'LAWTON';
        else ours = leU.trim() === 'MGT' ? 'MGT' : 'JPM';
        return ours + ' x ' + (side(client) || 'CLI');
    }

    /* Par dos geradores OPC (Opt FXO / Opt Commodities): a perna nossa segue
       os testes de SUBSTRING que o gerador usa para as contas ('BANCO J.P
       MORGAN' / 'JP MORGAN', sem regex) — grafia fora do padrão não casa par
       de grupo e cai no template base, o comportamento de sempre. Cópia de
       routes._opc_le_pair. */
    function pairOpc(client) {
        var c = String(client || '').toUpperCase();
        var isJpm = c.indexOf('BANCO J.P MORGAN') !== -1 || c.indexOf('JP MORGAN') !== -1;
        var ours = isJpm ? 'LAWTON' : 'JPM';
        var theirs = c.indexOf('LAWTON') !== -1 ? 'LAWTON'
            : (isJpm ? 'JPM' : (side(client) || 'CLI'));
        return ours + ' x ' + theirs;
    }

    /* Par SEM a perna espelhada: LE × contraparte como a mesa lê (MGT x JPM).
       É o par das páginas em que o app não escreve o arquivo (NDF Vanilla) —
       lá não existe visão Lawton sintetizada. */
    function pairSimple(le, client) {
        return (side(le) || 'JPM') + ' x ' + (side(client) || 'CLI');
    }

    /* Escolhe o spec do page-spec para um PAR: a variante cadastrada para ele
       (base_key = baseKey) vence; sem variante vale o template base. */
    function pickByPair(templates, baseKey, pair) {
        templates = templates || [];
        var want = norm(pair);
        var base = null;
        for (var i = 0; i < templates.length; i++) {
            var t = templates[i] || {};
            if ((t.base_key || '') === baseKey && norm(t.le_pair) === want) return t;
            if (t.key === baseKey && !base) base = t;
        }
        return base || templates[0] || null;
    }

    /* Atalho: escolhe pelo par do DEAL (com a regra da perna espelhada). */
    function pick(templates, baseKey, le, client) {
        return pickByPair(templates, baseKey, pairOf(le, client));
    }

    /* ── Fórmulas cadastradas no Source Field/Value — espelho do
       _fi_calc_value do servidor. FIELD / DATE / BIZDIFF / ADDBIZ / LOOKUP,
       argumentos por ';', campo casado com o deal cego a caixa/espaço
       ('Last Fixing Date' ≡ LastFixingDate). null = não é fórmula (vale o
       valor do gerador). BIZDIFF/ADDBIZ usam o calendário ANBIMA e LOOKUP as
       linhas do mapping — os dois carregados por prime(), chamado pelas
       páginas depois do page-spec. check_fi_calc.py compara as duas cópias. */
    var CALC_RE = /^\s*(BIZDIFF|ADDBIZ|DATE|FIELD|LOOKUP)\s*\(([\s\S]*)\)\s*$/i;
    var HOLS = {};       // 'YYYY-MM-DD' → true (ANBIMA)
    var MAP_ROWS = {};   // mapping key → rows

    function dealGet(deal, name) {
        var want = String(name || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
        if (!want || !deal) return '';
        for (var k in deal) {
            if (String(k).toUpperCase().replace(/[^A-Z0-9]/g, '') === want)
                return String(deal[k] == null ? '' : deal[k]).replace(/<[^>]+>/g, '').trim();
        }
        return '';
    }
    function parseDate(v) {
        v = String(v || '').trim();
        var m = v.match(/^(\d{4})-(\d{2})-(\d{2})/);
        if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
        m = v.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
        if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
        m = v.match(/^(\d{4})(\d{2})(\d{2})$/);
        if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
        return null;
    }
    function pad2(n) { return String(n).length < 2 ? '0' + n : String(n); }
    function ymdDash(d) { return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate()); }
    function ymd8(d) { return '' + d.getFullYear() + pad2(d.getMonth() + 1) + pad2(d.getDate()); }
    function isBiz(d) { var w = d.getDay(); return w !== 0 && w !== 6 && !HOLS[ymdDash(d)]; }
    function bizDiff(a, b) {
        if (!a || !b || a >= b) return 0;
        var n = 0, c = new Date(a.getTime());
        while (c < b) { c.setDate(c.getDate() + 1); if (isBiz(c)) n++; }
        return n;
    }
    function addBiz(d, n) {
        var c = new Date(d.getTime()), left = n;
        while (left > 0) { c.setDate(c.getDate() + 1); if (isBiz(c)) left--; }
        return c;
    }
    function widthOf(fmt) {
        var m = /^[X9]\((\d+)\)$/.exec(String(fmt || ''));
        return m ? +m[1] : null;
    }
    function calc(spec, deal, fmt) {
        var m = CALC_RE.exec(String(spec || ''));
        if (!m || !deal) return null;
        var fn = m[1].toUpperCase();
        var args = m[2].split(';').map(function (s) { return s.trim(); });
        try {
            if (fn === 'FIELD') return dealGet(deal, args[0]);
            if (fn === 'DATE') {
                var d1 = parseDate(dealGet(deal, args[0]));
                return d1 ? ymd8(d1) : '';
            }
            if (fn === 'BIZDIFF') {
                var a = parseDate(dealGet(deal, args[0]));
                var b = parseDate(dealGet(deal, args[1]));
                var s = String(bizDiff(a, b));
                var w = widthOf(fmt);
                return w ? s.padStart(w, '0').slice(0, w) : s;
            }
            if (fn === 'ADDBIZ') {
                var d2 = parseDate(dealGet(deal, args[0]));
                return d2 ? ymd8(addBiz(d2, parseInt(args[1], 10) || 0)) : '';
            }
            if (fn === 'LOOKUP') {
                var rows = MAP_ROWS[args[0]] || [];
                var alvo = dealGet(deal, args[3]).toUpperCase().replace(/[^A-Z0-9]/g, '');
                if (!alvo) return '';
                for (var i = 0; i < rows.length; i++) {
                    var v = String(rows[i][args[1]] || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
                    if (v && v === alvo) return String(rows[i][args[2]] || '');
                }
                return '';
            }
        } catch (e) { return null; }
        return null;
    }
    /* Pré-carrega o que o calc precisa: ANBIMA (BIZDIFF/ADDBIZ) e as linhas
       dos mappings citados em LOOKUP nos templates da página. */
    function prime(templates) {
        if (typeof fetch !== 'function') return;
        fetch('/static/data/anbima.json')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                (d || []).forEach(function (x) {
                    var k = (x && x.date) || x;
                    if (k) HOLS[k] = true;
                });
            }).catch(function () {});
        var keys = {};
        (templates || []).forEach(function (t) {
            ((t && t.blocks) || []).forEach(function (b) {
                (b.fields || []).forEach(function (f) {
                    var m = CALC_RE.exec(String(f.source_detail || ''));
                    if (m && m[1].toUpperCase() === 'LOOKUP') {
                        var k = m[2].split(';')[0].trim();
                        if (k) keys[k] = true;
                    }
                });
            });
        });
        Object.keys(keys).forEach(function (k) {
            fetch('/api/mappings/' + encodeURIComponent(k), { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (d) { if (d && d.success) MAP_ROWS[k] = d.rows || []; })
                .catch(function () {});
        });
    }
    function setHolidays(arr) {
        (arr || []).forEach(function (x) {
            var k = (x && x.date) || x;
            if (k) HOLS[k] = true;
        });
    }
    function setMappingRows(key, rows) { MAP_ROWS[key] = rows || []; }

    window.FiTer = { side: side, norm: norm, pair: pairOf, pairSimple: pairSimple,
                     pairOpc: pairOpc, pick: pick, pickByPair: pickByPair,
                     setEntities: setEntities, calc: calc, prime: prime,
                     setHolidays: setHolidays, setMappingRows: setMappingRows };
})();

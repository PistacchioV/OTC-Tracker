/* fi-ter-pair.js — cópia no navegador da regra de par de pernas do TER
   (routes.py: _ter_le_side / _ter_le_pair / _fi_variant_key). O preview de
   duplo clique escolhe a MESMA variante de template do File Interpreter que o
   arquivo gerado usa — as duas cópias têm de concordar campo a campo
   (scripts/tests/check_fi_variants.py compara as duas). */
(function () {
    'use strict';

    /* Lado de um par a partir de um nome (LE ou contraparte): JPM, MGT,
       LAWTON, ATACAMA — ou null para cliente externo. Substrings iguais às
       dos testes de conta do gerador (_is_jpm/_is_mgt/_is_lawton). */
    function side(name) {
        var u = String(name || '').toUpperCase();
        if (!u.replace(/\s+/g, '')) return null;
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

    window.FiTer = { side: side, norm: norm, pair: pairOf, pairSimple: pairSimple,
                     pairOpc: pairOpc, pick: pick, pickByPair: pickByPair };
})();

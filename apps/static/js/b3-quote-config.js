/* ============================================================================
 * Tipo de Cotação / Fonte de Informação do Ativo Subjacente — cópia de tela
 * ----------------------------------------------------------------------------
 * Espelha `_b3_quote_cfg` de routes.py. As páginas de New Deals montam o
 * arquivo Conecta DUAS VEZES — no navegador (preview do duplo clique e o
 * download) e no servidor (o envio) —, então esta regra tem de existir dos dois
 * lados e dizer a mesma coisa. É UM arquivo compartilhado de propósito: a mesma
 * regra copiada por página foi o que fez as duas cópias do código B3 divergirem
 * (§164).
 *
 * O que era literal no código e agora é cadastro (§177):
 *   Termo  (NDF Comm) → Tipo de Cotação 'F'/'A' e Fonte de Informação 340/358,
 *                       conforme o Fixed Quote
 *   Opção  (Opt Comm) → Tipo de Cotação '5', fixo
 * Coluna vazia — ou subjacente sem linha no cadastro — devolve exatamente esses
 * valores, então o comportamento só muda quando alguém edita a tabela.
 *
 * Uso:
 *   B3Quote.load();                          // uma vez, ao carregar a página
 *   var q = B3Quote.cfg(underlying);         // { ndf, opt, source, fixed }
 * ========================================================================== */
window.B3Quote = (function () {
    'use strict';

    var ROWS = null;                 // null = cadastro ainda não chegou
    var OPT_DEFAULT = '5';

    function txt(v) { return String(v == null ? '' : v).trim(); }

    /* Mesma regra de `_b3_code_matches`: literal nas linhas FIXED, prefixo +
       sufixo nas PREFIX ('HO"MY"', 'C_"MY"', 'KO"MY"BNMK'), exigindo ao menos um
       caractere de mês/ano no meio. */
    function matches(pattern, code) {
        var pat = txt(pattern), cod = txt(code).toUpperCase();
        if (!pat || !cod) return false;
        if (pat.indexOf('"') === -1 && pat.indexOf('_') === -1) {
            return pat.toUpperCase() === cod;
        }
        var m = /"\s*MY\s*"/i.exec(pat);
        var head = (m ? pat.slice(0, m.index) : pat).replace(/_/g, ' ').toUpperCase();
        var tail = (m ? pat.slice(m.index + m[0].length) : '').replace(/_/g, ' ').toUpperCase();
        return cod.indexOf(head) === 0 &&
               cod.lastIndexOf(tail) === cod.length - tail.length &&
               cod.length > head.length + tail.length;
    }

    function load(cb) {
        fetch('/api/mappings/commodities-b3', { credentials: 'same-origin' })
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (d && d.success && d.rows) ROWS = d.rows;
                if (cb) cb();
            })
            .catch(function () { if (cb) cb(); });   // sem cadastro → defaults
    }

    function cfg(underlying) {
        var row = {};
        for (var i = 0; ROWS && i < ROWS.length; i++) {
            if (matches(ROWS[i]['B3 CODE'], underlying)) { row = ROWS[i]; break; }
        }
        var fixed = txt(row['FIXED QUOTE']).toUpperCase() === 'YES';
        return {
            fixed:  fixed,
            ndf:    txt(row['QUOTE TYPE NDF']) || (fixed ? 'F' : 'A'),
            opt:    txt(row['QUOTE TYPE OPT']) || OPT_DEFAULT,
            source: txt(row['INFO SOURCE']) || (fixed ? '340' : '358')
        };
    }

    return { load: load, cfg: cfg, matches: matches };
})();

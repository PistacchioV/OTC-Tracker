/* Alinhamento da "Definição das Partes" NA TELA das confirmações do Word.
 *
 * O bloco é um export do Word: o nome de cada Parte é posicionado por TAB
 * (`mso-tab-count`, que o Word lê como tabulação e o navegador como uma fila de
 * &nbsp;), e o CNPJ da linha de baixo por margem de parágrafo MAIS um recuo de
 * &nbsp; dentro de `<!--[if !supportLists]-->`, que o Word esconde e o
 * conversor de PDF (`word_html_pdf`, que não lê margem) usa. O navegador mostra
 * as DUAS coisas: o CNPJ da Parte A saía 172px à direita do nome e o da Parte B
 * 21px à esquerda (MGT × Cliente, 23/09/2026).
 *
 * Este script só roda na TELA: o `.doc` e o PDF são renderizados de novo pelo
 * servidor em modo `doc_only`, sem ele, e o Word não executa script — então o
 * que se mexe aqui não chega ao arquivo. E por isso é JS e não CSS: uma regra
 * de <style> valeria também no Word, que desalinharia do outro lado.
 *
 * O que faz: esconde o recuo de &nbsp; que vem ANTES do "CNPJ" e põe a margem
 * do parágrafo do CNPJ exatamente na coordenada em que o nome começa. Acha as
 * linhas pelo TEXTO ("Parte A:" / "Parte B:" e o próximo parágrafo com CNPJ),
 * porque os documentos não usam os mesmos ids.
 */
(function () {
    'use strict';

    var VAZIO = /^[\s ]*$/;

    function texto(p) { return (p.textContent || '').replace(/\s+/g, ' '); }

    // Coordenada x do primeiro caractere depois de `rotulo` (o nome da Parte).
    // A busca é no texto INTEIRO do parágrafo, não nó a nó: o export do Word
    // parte o rótulo entre elementos ("Parte" num <span>, " A" em outro, na
    // Opção de Câmbio vanilla) e quebra a linha no meio dele ("Parte\nB").
    function inicioDoNome(p, rotulo) {
        var nos = [], todo = '', n;
        var w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT);
        while ((n = w.nextNode())) { nos.push({ n: n, ini: todo.length }); todo += n.textContent; }
        var m = new RegExp(rotulo.replace(/ /g, '[\\s\\u00a0]+')).exec(todo);
        if (!m) { return null; }
        var resto = todo.slice(m.index + m[0].length);
        var k = resto.search(/[^\s\u00a0:]/);
        if (k < 0) { return null; }
        var pos = m.index + m[0].length + k;
        for (var q = nos.length - 1; q >= 0; q--) {
            if (nos[q].ini <= pos) {
                var r = document.createRange();
                r.setStart(nos[q].n, pos - nos[q].ini);
                r.setEnd(nos[q].n, pos - nos[q].ini + 1);
                var box = r.getClientRects()[0];
                return box ? box.left : null;
            }
        }
        return null;
    }

    // O nó de texto com "CNPJ" e a coordenada dele.
    function cnpj(p) {
        var w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT), n;
        while ((n = w.nextNode())) {
            var i = n.textContent.indexOf('CNPJ');
            if (i < 0) { continue; }
            var r = document.createRange();
            r.setStart(n, i);
            r.setEnd(n, i + 4);
            var box = r.getClientRects()[0];
            return box ? { node: n, x: box.left } : null;
        }
        return null;
    }

    // Esconde os elementos SÓ de espaço que vêm antes do "CNPJ" (o recuo do
    // PDF e o tab da Parte B), sem tocar no que vem depois dele.
    function escondeRecuo(p, noCnpj) {
        Array.prototype.forEach.call(p.querySelectorAll('span'), function (el) {
            if (!VAZIO.test(el.textContent) || el.contains(noCnpj)) { return; }
            if (el.compareDocumentPosition(noCnpj) & Node.DOCUMENT_POSITION_FOLLOWING) {
                el.style.display = 'none';
            }
        });
    }

    function alinha() {
        var ps = Array.prototype.slice.call(document.querySelectorAll('.WordSection1 p'));
        ['Parte A', 'Parte B'].forEach(function (rotulo) {
            var i = -1;
            for (var k = 0; k < ps.length; k++) {
                if (texto(ps[k]).indexOf(rotulo + ':') >= 0) { i = k; break; }
            }
            if (i < 0) { return; }
            var alvo = null;
            for (var j = i + 1; j < Math.min(i + 4, ps.length); j++) {
                if (texto(ps[j]).indexOf('CNPJ') >= 0) { alvo = ps[j]; break; }
            }
            if (!alvo) { return; }
            var x = inicioDoNome(ps[i], rotulo);
            var c = cnpj(alvo);
            if (x === null || !c) { return; }
            escondeRecuo(alvo, c.node);
            alvo.style.textIndent = '0';
            alvo.style.marginLeft = '0';
            c = cnpj(alvo);
            if (!c) { return; }
            alvo.style.marginLeft = Math.max(0, x - c.x) + 'px';
        });
    }

    var espera = null;
    function agenda() {
        if (espera) { clearTimeout(espera); }
        espera = setTimeout(alinha, 60);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', alinha);
    } else {
        alinha();
    }
    // A fonte do Word pode chegar depois do DOMContentLoaded e mudar a largura
    // do rótulo; o painel lateral muda a largura da coluna.
    window.addEventListener('load', alinha);
    window.addEventListener('resize', agenda);
    window.otcAlinhaPartes = alinha;
})();

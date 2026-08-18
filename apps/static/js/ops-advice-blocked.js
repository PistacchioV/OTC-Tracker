/* O disclaimer do BLOCKER dos avisos de liquidação, num arquivo só.
 *
 * O servidor recusa gerar o aviso da contraparte que tem valor não identificado
 * (Resultado Bruto / Líquido em branco) — o aviso é o documento pelo qual o
 * cliente paga, e em branco ele não diz quanto mas parece completo. A recusa
 * TEM de aparecer: uma contraparte que some do lote sem dizer por quê é uma
 * contraparte que ninguém vai cobrar.
 *
 * Quatro telas mostram esse aviso (Settlement Summary e as três de Settlement
 * Advice), e por isso a frase mora aqui: quatro cópias divergiriam na primeira
 * correção de texto.
 *
 * O payload chega por dois caminhos, porque a resposta tem dois formatos:
 *   · JSON (até 2 rascunhos) → o campo `blocked`;
 *   · .zip (3+)             → o cabeçalho `X-Blocked`, em base64, porque nome
 *                             de contraparte tem acento e cabeçalho HTTP é
 *                             latin-1.
 */
(function () {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (ch) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch];
        });
    }

    /* `X-Blocked` → array. Cabeçalho ausente ou ilegível devolve [] em vez de
       explodir: o lote FOI gerado, e uma falha no disclaimer não pode virar um
       erro de geração. */
    function fromHeader(resp) {
        try {
            var raw = resp && resp.headers && resp.headers.get('X-Blocked');
            if (!raw) return [];
            // atob → bytes → UTF-8 (o servidor manda base64 de JSON UTF-8).
            var bin = atob(raw), bytes = new Uint8Array(bin.length);
            for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            var txt = new TextDecoder('utf-8').decode(bytes);
            var arr = JSON.parse(txt);
            return Array.isArray(arr) ? arr : [];
        } catch (e) {
            return [];
        }
    }

    /* O bloco HTML do disclaimer, ou '' quando não há nada bloqueado. */
    function html(blocked) {
        if (!blocked || !blocked.length) return '';
        var itens = blocked.map(function (b) {
            var cols = (b.columns || []).join(', ');
            return '<li style="text-align:left;">' +
                   '<strong>' + esc(b.counterparty || '—') + '</strong>' +
                   ' &middot; ' + esc(b.product || '') +
                   (cols ? ' <span style="opacity:.75">(' + esc(cols) + ')</span>' : '') +
                   '</li>';
        }).join('');
        return '<div style="margin-top:.75rem;text-align:left;">' +
               '<div style="color:#b02a37;font-weight:600;margin-bottom:.25rem;">' +
               'Aviso NÃO gerado — valor não identificado:</div>' +
               '<ul style="margin:0;padding-left:1.1rem;font-size:.9em;">' + itens + '</ul>' +
               '<div style="font-size:.8em;opacity:.75;margin-top:.35rem;">' +
               'Corrija a origem do valor e gere de novo.</div></div>';
    }

    window.opsAdviceBlocked = { html: html, fromHeader: fromHeader, esc: esc };
})();

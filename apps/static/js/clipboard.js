/* ===========================================================================
 * OTC Tracker — cópia para a área de transferência
 * ===========================================================================
 * POR QUE ESTE ARQUIVO EXISTE
 *
 * `navigator.clipboard` só existe em SECURE CONTEXT: https, ou http em
 * localhost/127.0.0.1. A aplicação roda em `http://<IP-da-maquina>:8050`
 * (start-prod.bat), que NÃO é secure context — ali o objeto é `undefined` e
 * `navigator.clipboard.writeText(...)` estoura um TypeError antes mesmo de
 * existir promise para o `.catch()` pegar. Resultado: o Ctrl+C das tabelas
 * falhava calado na instância da equipe e funcionava na máquina de quem
 * desenvolveu (localhost), que é o motivo de ter passado despercebido.
 *
 * O botão Copy do DataTables sempre funcionou porque a lib usa
 * `document.execCommand('copy')` — a API legada, que não exige secure context.
 * É essa a saída de emergência daqui.
 *
 * `otcCopyText(texto)` devolve SEMPRE uma promise: usa a API moderna quando
 * ela existe e cai no textarea + execCommand quando não existe (ou quando ela
 * rejeita, o que acontece quando a aba está sem foco ou a permissão foi
 * negada).
 * ======================================================================== */
(function (window, document) {
    'use strict';

    function legacyCopy(text) {
        // O textarea precisa estar VISÍVEL para o browser aceitar a seleção —
        // `display:none` e `visibility:hidden` fazem o execCommand devolver
        // false. Por isso ele é posicionado fora da tela em vez de escondido.
        var ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.top = '0';
        ta.style.left = '-9999px';
        ta.style.opacity = '0';
        document.body.appendChild(ta);

        // Guardar e restaurar a seleção do usuário: sem isso, copiar apaga o
        // que estava selecionado na página.
        var sel = document.getSelection();
        var prev = (sel && sel.rangeCount > 0) ? sel.getRangeAt(0) : null;

        var ok = false;
        try {
            ta.select();
            ta.setSelectionRange(0, ta.value.length);   // iOS ignora o select()
            ok = document.execCommand('copy');
        } catch (e) {
            ok = false;
        }
        document.body.removeChild(ta);
        if (prev && sel) { sel.removeAllRanges(); sel.addRange(prev); }
        return ok;
    }

    /** Copia `text`. Promise resolvida em sucesso, rejeitada quando nem a API
     *  moderna nem o execCommand deram conta. */
    window.otcCopyText = function (text) {
        text = (text == null) ? '' : String(text);
        if (!text) return Promise.resolve();
        var nav = window.navigator;
        if (nav && nav.clipboard && window.isSecureContext) {
            return nav.clipboard.writeText(text)['catch'](function () {
                // Rejeitou (aba sem foco, permissão negada): ainda dá para o
                // caminho legado salvar.
                return legacyCopy(text) ? Promise.resolve()
                                        : Promise.reject(new Error('copy failed'));
            });
        }
        return legacyCopy(text) ? Promise.resolve()
                                : Promise.reject(new Error('clipboard unavailable'));
    };

    /* ── Ctrl+C genérico nas tabelas ──────────────────────────────────────
     * Algumas páginas (New Deals, Pending Confirmation) têm handler próprio,
     * com regras de extração específicas. Este aqui cobre TODA tabela que não
     * tem — Index B3, Intrag, MTM, Accrual, Metrics… — e sai de cena quando:
     *   • a página já tratou o evento (`defaultPrevented`);
     *   • o usuário tem texto selecionado (aí o Ctrl+C nativo faz melhor);
     *   • o foco está num campo de digitação.
     * O listener fica em `window`, não em `document`: o evento borbulha
     * target → document → window, então os handlers das páginas (registrados
     * em `document` via jQuery) rodam ANTES e o `defaultPrevented` já chega
     * decidido aqui. */

    function cellText(node) {
        if (!node) return '';
        var el = node.querySelector('select');
        if (el) {
            // Texto da opção, não o value: o value costuma ser um código.
            return (el.selectedIndex >= 0 && el.options[el.selectedIndex])
                ? el.options[el.selectedIndex].text.trim() : (el.value || '');
        }
        el = node.querySelector('input[type="text"], input[type="date"], input[type="number"]');
        if (el) return el.value || '';
        el = node.querySelector('input[type="checkbox"]');
        if (el) return el.checked ? 'Yes' : 'No';
        return (node.textContent || '').trim();
    }

    function selectionFromTables() {
        var dt = window.jQuery && window.jQuery.fn && window.jQuery.fn.dataTable;
        if (!dt || !dt.tables) return '';
        var out = [];
        var tables;
        try {
            tables = dt.tables({ api: true });
        } catch (e) {
            return '';
        }
        tables.every(function () {
            var api = this;
            var cells;
            try {
                cells = api.cells({ selected: true });
            } catch (e) {
                return true;                    // Select não carregado na página
            }
            if (cells && cells.count()) {
                // Agrupar por linha preserva o retângulo colado no Excel; uma
                // única string com tabs jogaria tudo numa linha só.
                var byRow = {};
                var order = [];
                cells.every(function (rowIdx, colIdx) {
                    if (!byRow[rowIdx]) { byRow[rowIdx] = []; order.push(rowIdx); }
                    byRow[rowIdx].push(cellText(this.node()));
                    return true;
                });
                order.forEach(function (r) { out.push(byRow[r].join('\t')); });
                return true;
            }
            var rows;
            try {
                rows = api.rows({ selected: true });
            } catch (e) {
                return true;
            }
            if (rows && rows.count()) {
                rows.every(function () {
                    var tds = this.node() ? this.node().querySelectorAll('td') : [];
                    var vals = [];
                    for (var i = 0; i < tds.length; i++) {
                        // A coluna do checkbox de seleção não interessa na cópia.
                        if (tds[i].querySelector('input[type="checkbox"].dt-checkboxes, .dt-checkbox')) continue;
                        vals.push(cellText(tds[i]));
                    }
                    out.push(vals.join('\t'));
                    return true;
                });
            }
            return true;
        });
        return out.join('\n');
    }

    window.addEventListener('keydown', function (e) {
        if (!(e.ctrlKey || e.metaKey)) return;
        if ((e.key || '').toLowerCase() !== 'c') return;
        if (e.defaultPrevented) return;                 // a página já tratou

        var tag = (document.activeElement && document.activeElement.tagName || '').toUpperCase();
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
        if (document.activeElement && document.activeElement.isContentEditable) return;

        var native = window.getSelection ? String(window.getSelection()) : '';
        if (native && native.trim()) return;             // deixa o browser copiar

        var text = selectionFromTables();
        if (!text) return;
        e.preventDefault();
        window.otcCopyText(text)['catch'](function () {});
    });
})(window, document);

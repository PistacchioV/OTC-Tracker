/* ============================================================================
 * table-std.js — seleção de célula + Ctrl+C, o padrão do New Deals para
 * qualquer tabela do app.
 * ----------------------------------------------------------------------------
 * As seis páginas de New Deals fazem isso com a extensão `select` do
 * DataTables (items:'cell') + um handler de Ctrl+C próprio. Este helper
 * entrega o MESMO comportamento e o MESMO visual para as páginas que não
 * carregam a extensão — funciona sobre DataTable ou tabela estática, porque
 * opera só no DOM (delegação no nó da tabela, que o DataTables preserva nos
 * redraws e move inteiro para o corpo rolável no scrollX).
 *
 * Uso, depois de a tabela existir no DOM:
 *     otcCellCopy('#minha-tabela', { skip: [0, 1] })
 *
 *  - skip: índices (0-based) de colunas fora da seleção — checkbox e Actions,
 *    como no New Deals, onde essas colunas mantêm cursor default.
 *  - Clique seleciona a célula; Ctrl/Cmd+clique acrescenta; Ctrl/Cmd+C copia
 *    (célula → texto como no New Deals: select/input → value, checkbox →
 *    Yes/No, resto → textContent) com \t entre células da mesma linha e \n
 *    entre linhas — cola direto no Excel; Esc ou clique fora limpa.
 *  - O flash verde de "copiado" é o mesmo #90EE90 do New Deals.
 *
 * Chamar duas vezes na mesma tabela não duplica handlers (marca no nó).
 * ========================================================================== */
(function () {
    'use strict';

    var STYLE_ID = 'otc-cellcopy-style';

    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        var s = document.createElement('style');
        s.id = STYLE_ID;
        s.textContent = [
            /* mesmos tons do New Deals; inset box-shadow em vez de border para
               a célula não mudar de tamanho ao selecionar */
            '.otc-cellcopy tbody td.otc-sel { background-color:#b3d7ff !important; box-shadow: inset 0 0 0 2px #0066cc; }',
            '.otc-cellcopy tbody td:not(.otc-nosel):hover { background-color:#e6f2ff; cursor:cell; }',
            /* o azul-claro com texto claro do tema escuro seria ilegível */
            '[data-bs-theme=dark] .otc-cellcopy tbody td.otc-sel { background-color:rgba(0,102,204,.38) !important; }',
            '[data-bs-theme=dark] .otc-cellcopy tbody td:not(.otc-nosel):hover { background-color:rgba(0,102,204,.14); }'
        ].join('\n');
        document.head.appendChild(s);
    }

    function cellText(td) {
        var sel = td.querySelector('select');
        if (sel) return sel.value || '';
        var inp = td.querySelector('input[type="text"], input[type="date"], input[type="number"]');
        if (inp) return inp.value || '';
        var chk = td.querySelector('input[type="checkbox"]');
        if (chk) return chk.checked ? 'Yes' : 'No';
        return (td.textContent || '').trim();
    }

    function copyText(text) {
        if (window.otcCopyText) return window.otcCopyText(text);
        if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
        return new Promise(function (resolve, reject) {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(ta);
            ta.select();
            try { document.execCommand('copy') ? resolve() : reject(new Error('execCommand')); }
            catch (e) { reject(e); }
            document.body.removeChild(ta);
        });
    }

    window.otcCellCopy = function (tableSel, opts) {
        var table = typeof tableSel === 'string' ? document.querySelector(tableSel) : tableSel;
        if (!table || table.__otcCellCopy) return;
        table.__otcCellCopy = true;
        opts = opts || {};
        var skip = opts.skip || [];

        ensureStyle();
        table.classList.add('otc-cellcopy');

        function markNosel() {
            /* cursor default nas colunas fora da seleção (checkbox, Actions) */
            skip.forEach(function (i) {
                table.querySelectorAll('tbody tr').forEach(function (tr) {
                    var td = tr.cells[i];
                    if (td) td.classList.add('otc-nosel');
                });
            });
        }

        function clear() {
            table.querySelectorAll('td.otc-sel').forEach(function (td) { td.classList.remove('otc-sel'); });
        }

        table.addEventListener('click', function (e) {
            var td = e.target.closest('td');
            if (!td || !table.contains(td)) return;
            /* clique num controle é o controle, não uma seleção de célula */
            if (e.target.closest('button, a, select, input, label, .btn')) return;
            if (skip.indexOf(td.cellIndex) !== -1) { td.classList.add('otc-nosel'); return; }
            if (e.ctrlKey || e.metaKey) td.classList.toggle('otc-sel');
            else { clear(); td.classList.add('otc-sel'); }
            markNosel();
        });

        document.addEventListener('keydown', function (e) {
            var cells = table.querySelectorAll('td.otc-sel');
            if (!cells.length) return;
            if (e.key === 'Escape') { clear(); return; }
            if ((e.ctrlKey || e.metaKey) && e.key === 'c') {
                e.preventDefault();
                /* agrupa por linha: \t dentro da linha, \n entre linhas */
                var byRow = new Map();
                cells.forEach(function (td) {
                    var tr = td.parentNode;
                    if (!byRow.has(tr)) byRow.set(tr, []);
                    byRow.get(tr).push(cellText(td));
                });
                var text = Array.from(byRow.values())
                    .map(function (arr) { return arr.join('\t'); }).join('\n');
                copyText(text).then(function () {
                    cells.forEach(function (td) { td.style.backgroundColor = '#90EE90'; });
                    setTimeout(function () {
                        cells.forEach(function (td) { td.style.backgroundColor = ''; });
                    }, 200);
                })['catch'](function () {});
            }
        });

        /* clique fora da tabela limpa — igual ao comportamento 'os' do New Deals */
        document.addEventListener('click', function (e) {
            if (!table.contains(e.target)) clear();
        });
    };
})();

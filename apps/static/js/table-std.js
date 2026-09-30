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
 *
 * MODO AUTOMÁTICO (mesa, 30/09/2026): carregado pelo layout base depois dos
 * scripts da página, liga-se SOZINHO a toda DataTable (as que existem e as que
 * nascem depois, pelo `init.dt`) — a seleção de célula e o Ctrl+C valem em
 * toda tabela do app sem a página escrever nada. Fica de fora: a tabela que
 * usa a extensão `select` por célula (New Deals, Intrag — ela tem seleção e
 * Ctrl+C próprios), e a marcada com `data-cell-copy="off"`. Coluna sem dado
 * (checkbox, Actions, botões) não é selecionável, com ou sem `skip`.
 *
 * O Ctrl+C é UM listener só, e copia a tabela em que se clicou por ÚLTIMO:
 * com um listener por tabela, duas tabelas com seleção copiavam juntas (ou a
 * outra por cima). Com o foco num campo de digitação, o Ctrl+C/Ctrl+V é do
 * campo — antes o handler o engolia. A tecla vale com Shift/Caps Lock.
 * ========================================================================== */
(function () {
    'use strict';
    // Carregado pela página E pelo base: o núcleo entra uma vez; o modo
    // automático, uma vez, na primeira carga que já encontra o jQuery.
    if (!window.__otcTableStd) {
    window.__otcTableStd = true;

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
            '[data-bs-theme=dark] .otc-cellcopy tbody td:not(.otc-nosel):hover { background-color:rgba(0,102,204,.14); }',
            /* A célula selecionada pela extensão `select` (New Deals, Intrag,
               recompras) com o MESMO visual: o padrão do DataTables é um
               preenchimento sem contorno (box-shadow de 9999px). Só a CÉLULA —
               a linha marcada no checkbox (tr.selected) segue como está. */
            'table.dataTable > tbody > tr > td.selected { box-shadow: inset 0 0 0 2px #0066cc !important; background-color:#b3d7ff !important; color:inherit !important; }',
            '[data-bs-theme=dark] table.dataTable > tbody > tr > td.selected { background-color:rgba(0,102,204,.38) !important; }'
        ].join('\n');
        document.head.appendChild(s);
    }

    window.__otcCellStyle = ensureStyle;

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

    /* Célula sem dado: checkbox de seleção, Actions, botões. */
    function isControlCell(td) {
        return !!td.querySelector('button, .btn, input[type="checkbox"], input[type="radio"], .dt-checkbox');
    }

    var ACTIVE = null;                          // a tabela do último clique

    function clearTable(table) {
        table.querySelectorAll('td.otc-sel').forEach(function (td) { td.classList.remove('otc-sel'); });
    }

    function isTyping() {
        var el = document.activeElement;
        if (!el) return false;
        var tag = (el.tagName || '').toUpperCase();
        return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable;
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
            table.querySelectorAll('tbody tr').forEach(function (tr) {
                Array.prototype.forEach.call(tr.cells, function (td) {
                    if (skip.indexOf(td.cellIndex) !== -1 || isControlCell(td)) td.classList.add('otc-nosel');
                });
            });
        }

        table.addEventListener('click', function (e) {
            var td = e.target.closest('td');
            if (!td || !table.contains(td) || td.closest('thead')) return;
            /* clique num controle é o controle, não uma seleção de célula */
            if (e.target.closest('button, a, select, input, textarea, label, .btn')) return;
            if (td.classList.contains('dt-empty')) return;
            if (skip.indexOf(td.cellIndex) !== -1 || isControlCell(td)) { td.classList.add('otc-nosel'); return; }
            if (ACTIVE && ACTIVE !== table) clearTable(ACTIVE);
            ACTIVE = table;
            if (e.ctrlKey || e.metaKey) td.classList.toggle('otc-sel');
            else { clearTable(table); td.classList.add('otc-sel'); }
            markNosel();
        });

        /* clique fora da tabela limpa — igual ao comportamento 'os' do New Deals */
        document.addEventListener('click', function (e) {
            if (!table.contains(e.target)) {
                clearTable(table);
                if (ACTIVE === table) ACTIVE = null;
            }
        });
    };

    document.addEventListener('keydown', function (e) {
        if (!ACTIVE || !document.contains(ACTIVE)) return;
        var cells = ACTIVE.querySelectorAll('td.otc-sel');
        if (!cells.length) return;
        if (e.key === 'Escape') { clearTable(ACTIVE); return; }
        if (!(e.ctrlKey || e.metaKey) || (e.key || '').toLowerCase() !== 'c') return;
        if (isTyping()) return;                 // o Ctrl+C é do campo
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
    });

    }

    /* ── modo automático: toda DataTable do app ─────────────────────────── */
    var $ = window.jQuery;
    if (!$ || !$.fn || !$.fn.dataTable || window.__otcTableStdAuto) return;
    window.__otcTableStdAuto = true;
    window.__otcCellStyle();

    function usesCellSelect(settings) {
        var sel = settings && settings._select;
        return !!(sel && /cell/.test(String(sel.items || '')));
    }

    function autoAttach(node) {
        try {
            if (!node || node.__otcCellCopy) return;
            if (node.getAttribute('data-cell-copy') === 'off') return;
            if (!$.fn.dataTable.isDataTable(node)) return;
            if (usesCellSelect($(node).DataTable().settings()[0])) return;
            window.otcCellCopy(node, {});
        } catch (e) {
            if (window.console) console.warn('[table-std]', e);
        }
    }

    $(document).on('init.dt.otccell', function (e, settings) {
        if (e.namespace !== 'dt') return;
        var node = settings && settings.nTable;
        // depois do handler de init da página, que pode chamar com o `skip` dela
        if (node) setTimeout(function () { autoAttach(node); }, 0);
    });
    $.fn.dataTable.tables().forEach(autoAttach);
})();

/* ──────────────────────────────────────────────────────────────────────────
 * excel-filter.js — o filtro "de Excel" no cabeçalho de uma DataTable
 *
 * Cada coluna ganha um funil no cabeçalho que abre um menu como o do Excel:
 * ordenar A→Z / Z→A, limpar o filtro da coluna, busca e a LISTA dos valores
 * distintos com caixinhas ((Selecionar tudo), (Vazias)), OK e Cancelar. Os
 * filtros de várias colunas se somam (E), e a lista de cada coluna mostra só
 * os valores que sobram depois dos filtros das OUTRAS — como no Excel.
 *
 * Convive com a linha de filtro por texto: o filtro daqui é um
 * `DataTable.ext.search` próprio, que o `column().search()` não toca.
 *
 *   otcExcelFilter('#tabela', { skip: [0, 1] })  // liga (idempotente por init)
 *   otcExcelFilter.clear('#tabela')              // o Clear Filters da toolbar
 *
 * O valor comparado é o TEXTO da célula como a tela mostra (sem HTML), para
 * o que a pessoa marca ser exatamente o que ela lê.
 *
 * Piloto: Operations B3 (29/09/2026). Depois de aprovado, vai para as outras.
 * ────────────────────────────────────────────────────────────────────────── */
(function (w, $) {
    'use strict';
    if (!$ || !$.fn || !$.fn.dataTable || w.otcExcelFilter) return;

    var DT = $.fn.dataTable;
    var BLANK = '\u0000blank';          // chave interna de "(Vazias)"
    var MAX_ITEMS = 500;                 // acima disso, a lista pede a busca
    var STATE = new WeakMap();           // nó da <table> → { dt, skip, filters }

    // ── i18n (a regra da casa: texto nasce em inglês, `_TRANS` + t()) ───────
    var _TRANS = {
        en: { asc: 'Sort A to Z', desc: 'Sort Z to A', clear: 'Clear filter from', search: 'Search',
              all: '(Select All)', allRes: '(Select All Search Results)', blanks: '(Blanks)',
              ok: 'OK', cancel: 'Cancel', more: 'Showing the first {n} values — use the search to narrow.',
              none: 'No values.', title: 'Filter' },
        br: { asc: 'Classificar de A a Z', desc: 'Classificar de Z a A', clear: 'Limpar filtro de', search: 'Pesquisar',
              all: '(Selecionar Tudo)', allRes: '(Selecionar Todos os Resultados)', blanks: '(Vazias)',
              ok: 'OK', cancel: 'Cancelar', more: 'Mostrando os primeiros {n} valores — use a pesquisa para filtrar.',
              none: 'Nenhum valor.', title: 'Filtrar' },
        es: { asc: 'Ordenar de A a Z', desc: 'Ordenar de Z a A', clear: 'Borrar filtro de', search: 'Buscar',
              all: '(Seleccionar todo)', allRes: '(Seleccionar todos los resultados)', blanks: '(Vacías)',
              ok: 'Aceptar', cancel: 'Cancelar', more: 'Mostrando los primeros {n} valores — use la búsqueda para filtrar.',
              none: 'Sin valores.', title: 'Filtrar' }
    };
    function lang() {
        var l = 'en';
        try { l = (localStorage.getItem('__OTC_TRACKER_LANG__') || localStorage.getItem('language') || 'en').toLowerCase(); }
        catch (e) { l = 'en'; }
        return _TRANS[l] ? l : 'en';
    }
    function t(k) { return _TRANS[lang()][k] || _TRANS.en[k]; }

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function norm(v) { return String(v == null ? '' : v).replace(/\s+/g, ' ').trim(); }
    function keyOf(v) { var s = norm(v); return s === '' ? BLANK : s; }

    // Texto da célula como a tela mostra: o HTML de exibição, sem tags.
    var _tmp = document.createElement('div');
    function cellText(html) {
        if (html == null) return '';
        var s = String(html);
        if (s.indexOf('<') === -1 && s.indexOf('&') === -1) return s;
        _tmp.innerHTML = s;
        return _tmp.textContent || '';
    }

    // ── o filtro em si: um ext.search para todas as tabelas ligadas ────────
    DT.ext.search.push(function (settings, searchData, dataIndex) {
        var st = STATE.get(settings.nTable);
        if (!st) return true;
        var cols = Object.keys(st.filters);
        if (!cols.length) return true;
        var row = settings.aoData[dataIndex];
        var raw = row && row._aData;
        for (var i = 0; i < cols.length; i++) {
            var c = +cols[i];
            if (!st.filters[c].has(keyOf(cellText(raw ? raw[c] : searchData[c])))) return false;
        }
        return true;
    });

    // Valores distintos da coluna `col` entre as linhas que passam nos filtros
    // das OUTRAS colunas (o que o Excel mostra na lista).
    function distinct(st, col) {
        var dt = st.dt;
        var others = Object.keys(st.filters).filter(function (c) { return +c !== col; });
        var seen = Object.create(null), out = [];
        dt.rows().every(function () {
            var d = this.data();
            for (var i = 0; i < others.length; i++) {
                var oc = +others[i];
                if (!st.filters[oc].has(keyOf(cellText(d[oc])))) return;
            }
            var k = keyOf(cellText(d[col]));
            if (!seen[k]) { seen[k] = true; out.push(k); }
        });
        // Ordem do Excel: números como números, o resto alfabético; Vazias no fim.
        var numRe = /^-?[\d.,]+$/;
        function asNum(v) {                    // 1.250.000,50 e 1,250,000.50
            return parseFloat(v.replace(/[.,](?=\d{3}(\D|$))/g, '').replace(',', '.'));
        }
        out.sort(function (a, b) {
            if (a === BLANK) return 1;
            if (b === BLANK) return -1;
            if (numRe.test(a) && numRe.test(b)) return asNum(a) - asNum(b);
            return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
        });
        return out;
    }

    // ── o menu ─────────────────────────────────────────────────────────────
    var menu = null;          // o menu aberto (um por vez)

    function closeMenu() {
        if (!menu) return;
        menu.el.remove();
        document.removeEventListener('mousedown', menu.outside, true);
        document.removeEventListener('keydown', menu.key, true);
        w.removeEventListener('resize', menu.reposition);
        w.removeEventListener('scroll', menu.reposition, true);
        menu = null;
    }

    function openMenu(st, col, btn) {
        if (menu && menu.btn === btn) { closeMenu(); return; }
        closeMenu();
        var dt = st.dt;
        var values = distinct(st, col);
        var current = st.filters[col];                     // Set ou undefined
        var checked = new Set(current ? values.filter(function (v) { return current.has(v); }) : values);
        var title = norm($(dt.column(col).header()).clone().find('.oxf-btn').remove().end().text());

        var el = document.createElement('div');
        el.className = 'oxf-menu';
        el.setAttribute('role', 'dialog');
        el.innerHTML =
            '<button type="button" class="oxf-item" data-act="asc"><i class="ti ti-sort-ascending-letters"></i>' + esc(t('asc')) + '</button>' +
            '<button type="button" class="oxf-item" data-act="desc"><i class="ti ti-sort-descending-letters"></i>' + esc(t('desc')) + '</button>' +
            '<div class="oxf-sep"></div>' +
            '<button type="button" class="oxf-item" data-act="clear"' + (current ? '' : ' disabled') + '>' +
                '<i class="ti ti-filter-off"></i>' + esc(t('clear')) + ' "' + esc(title) + '"</button>' +
            '<div class="oxf-sep"></div>' +
            '<div class="oxf-search"><i class="ti ti-search"></i><input type="text" autocomplete="off" placeholder="' + esc(t('search')) + '"></div>' +
            '<div class="oxf-list" role="listbox"></div>' +
            '<div class="oxf-note"></div>' +
            '<div class="oxf-foot">' +
                '<button type="button" class="btn btn-sm btn-primary" data-act="ok">' + esc(t('ok')) + '</button>' +
                '<button type="button" class="btn btn-sm btn-secondary" data-act="cancel">' + esc(t('cancel')) + '</button>' +
            '</div>';
        document.body.appendChild(el);

        var list = el.querySelector('.oxf-list');
        var note = el.querySelector('.oxf-note');
        var input = el.querySelector('.oxf-search input');
        var okBtn = el.querySelector('[data-act="ok"]');

        function matches() {
            var q = norm(input.value).toLowerCase();
            if (!q) return values;
            return values.filter(function (v) {
                return (v === BLANK ? t('blanks') : v).toLowerCase().indexOf(q) !== -1;
            });
        }

        function render() {
            var vis = matches();
            var searching = !!norm(input.value);
            var allOn = vis.length && vis.every(function (v) { return checked.has(v); });
            var someOn = vis.some(function (v) { return checked.has(v); });
            var html = vis.length
                ? '<label class="oxf-opt oxf-all"><input type="checkbox" data-all="1"' + (allOn ? ' checked' : '') + '>' +
                      '<span>' + esc(searching ? t('allRes') : t('all')) + '</span></label>'
                : '';
            html += vis.slice(0, MAX_ITEMS).map(function (v, i) {
                return '<label class="oxf-opt"><input type="checkbox" data-i="' + i + '"' + (checked.has(v) ? ' checked' : '') + '>' +
                       '<span' + (v === BLANK ? ' class="oxf-blank"' : '') + '>' + esc(v === BLANK ? t('blanks') : v) + '</span></label>';
            }).join('');
            list.innerHTML = html;
            var all = list.querySelector('[data-all]');
            if (all) all.indeterminate = !allOn && someOn;
            note.textContent = !vis.length ? t('none')
                : (vis.length > MAX_ITEMS ? t('more').replace('{n}', MAX_ITEMS) : '');
            // Sem busca, OK exige ao menos um marcado (como o Excel). Com busca,
            // o que vale é o marcado ENTRE os resultados.
            okBtn.disabled = !vis.some(function (v) { return checked.has(v); });
            list._vis = vis;
        }

        list.addEventListener('change', function (e) {
            var cb = e.target;
            var vis = list._vis || [];
            if (cb.hasAttribute('data-all')) {
                vis.forEach(function (v) { if (cb.checked) checked.add(v); else checked.delete(v); });
            } else {
                var v = vis[+cb.getAttribute('data-i')];
                if (cb.checked) checked.add(v); else checked.delete(v);
            }
            render();
        });

        input.addEventListener('input', function () {
            // Como o Excel: ao pesquisar, os resultados nascem todos marcados.
            matches().forEach(function (v) { checked.add(v); });
            render();
        });

        function apply() {
            var vis = matches();
            var searching = !!norm(input.value);
            var keep = (searching ? vis : values).filter(function (v) { return checked.has(v); });
            if (!searching && keep.length === values.length) delete st.filters[col];
            else st.filters[col] = new Set(keep);
            // Valores que a lista não mostrava (filtrados por outra coluna)
            // continuam valendo se já estavam no filtro desta: o Excel faz igual.
            paint(st);
            dt.draw();
            closeMenu();
        }

        el.addEventListener('click', function (e) {
            var b = e.target.closest('[data-act]');
            if (!b || b.disabled) return;
            var act = b.getAttribute('data-act');
            if (act === 'asc' || act === 'desc') { dt.order([[col, act]]).draw(); closeMenu(); }
            else if (act === 'clear') { delete st.filters[col]; paint(st); dt.draw(); closeMenu(); }
            else if (act === 'ok') apply();
            else if (act === 'cancel') closeMenu();
        });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !okBtn.disabled) { e.preventDefault(); apply(); }
        });

        function reposition() {
            var r = btn.getBoundingClientRect();
            var mw = el.offsetWidth, mh = el.offsetHeight;
            var left = Math.min(Math.max(8, r.right - mw), w.innerWidth - mw - 8);
            var top = r.bottom + 4;
            if (top + mh > w.innerHeight - 8 && r.top - mh - 4 > 8) top = r.top - mh - 4;
            el.style.left = left + 'px';
            el.style.top = top + 'px';
        }
        menu = {
            el: el, btn: btn, reposition: reposition,
            outside: function (e) { if (!el.contains(e.target) && e.target !== btn && !btn.contains(e.target)) closeMenu(); },
            key: function (e) { if (e.key === 'Escape') { e.stopPropagation(); closeMenu(); } }
        };
        render();
        reposition();
        document.addEventListener('mousedown', menu.outside, true);
        document.addEventListener('keydown', menu.key, true);
        w.addEventListener('resize', reposition);
        w.addEventListener('scroll', reposition, true);
        setTimeout(function () { input.focus(); }, 0);
    }

    // Funil aceso nas colunas filtradas (nos cabeçalhos original e clonado).
    function paint(st) {
        var root = st.dt.table().container();
        $(root).find('.oxf-btn').each(function () {
            var on = !!st.filters[+this.getAttribute('data-oxf-col')];
            this.classList.toggle('is-active', on);
            this.innerHTML = '<i class="ti ' + (on ? 'ti-filter-filled' : 'ti-filter') + '"></i>';
        });
    }

    function addButtons(st) {
        var dt = st.dt;
        dt.columns().every(function (idx) {
            if (st.skip.indexOf(idx) !== -1) return;
            var th = this.header();
            if (!th || th.querySelector('.oxf-btn')) return;
            var b = document.createElement('button');
            b.type = 'button';
            b.className = 'oxf-btn';
            b.setAttribute('data-oxf-col', idx);
            b.setAttribute('aria-label', t('title'));
            b.title = t('title');
            // O clique no funil NÃO pode ordenar a coluna: o th é o botão de
            // sort do DataTables, então o evento para AQUI, no botão.
            ['mousedown', 'keydown', 'keyup'].forEach(function (ev) {
                b.addEventListener(ev, function (e) { e.stopPropagation(); });
            });
            b.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                openMenu(st, idx, b);
            });
            th.classList.add('oxf-th');
            th.appendChild(b);
        });
        paint(st);
    }

    function otcExcelFilter(selector, opts) {
        opts = opts || {};
        var $t = $(selector);
        if (!$t.length || !DT.isDataTable($t[0])) return null;
        var dt = $t.DataTable();
        var node = dt.table().node();
        // Reconstruir a tabela (destroy + DataTable) é dado novo: filtro velho
        // não vale mais, como o SELECTED da página.
        var st = { dt: dt, skip: (opts.skip || []).slice(), filters: {} };
        STATE.set(node, st);
        closeMenu();
        addButtons(st);
        // A tradução da página (data-lang no th) reescreve o cabeçalho e leva o
        // funil junto: ele volta a cada draw (addButtons é idempotente).
        dt.off('draw.oxf').on('draw.oxf', function () { addButtons(st); });
        dt.off('destroy.oxf').on('destroy.oxf', function () { closeMenu(); STATE.delete(node); });
        return dt;
    }

    otcExcelFilter.clear = function (selector) {
        var node = $(selector)[0];
        var st = node && STATE.get(node);
        if (!st) return;
        st.filters = {};
        closeMenu();
        paint(st);
    };

    // ── estilo (uma vez) — menu pende do <body>: fundo SÓLIDO (§7) ──────────
    var css =
        '.oxf-th{position:relative;padding-right:22px!important}' +
        '.oxf-btn{position:absolute;right:3px;top:50%;translate:0 -50%;width:18px;height:18px;padding:0;border:0;' +
            'border-radius:5px;background:transparent;color:var(--ins-secondary-color,#6c757d);opacity:.55;' +
            'display:inline-flex;align-items:center;justify-content:center;font-size:.8rem;cursor:pointer;' +
            'transition:opacity var(--sf-dur-fast,140ms) var(--sf-ease-out,ease-out),background-color var(--sf-dur-fast,140ms) var(--sf-ease-out,ease-out)}' +
        '.oxf-th:hover .oxf-btn,.oxf-btn:focus-visible{opacity:1}' +
        '.oxf-btn:hover{background:rgba(0,102,204,.10)}' +
        '.oxf-btn.is-active{opacity:1;color:#0066cc;background:rgba(0,102,204,.12)}' +
        '[data-bs-theme=dark] .oxf-btn.is-active{color:#6aa9ff;background:rgba(106,169,255,.16)}' +
        '.oxf-menu{position:fixed;z-index:2100;width:280px;padding:6px;border-radius:12px;' +
            'background:#fff;color:#212529;border:1px solid rgba(0,0,0,.14);box-shadow:0 10px 32px rgba(0,0,0,.18);' +
            'font-size:.8rem;text-align:left;animation:oxf-in var(--sf-dur-base,200ms) var(--sf-ease-out,ease-out) both}' +
        '[data-bs-theme=dark] .oxf-menu{background:#2b2f3a;color:#dee2e6;border-color:rgba(255,255,255,.14)}' +
        '@keyframes oxf-in{from{opacity:0;translate:0 -4px}to{opacity:1;translate:0 0}}' +
        '.oxf-item{display:flex;align-items:center;gap:8px;width:100%;padding:6px 8px;border:0;border-radius:7px;' +
            'background:transparent;color:inherit;text-align:left;font-size:.8rem;cursor:pointer}' +
        '.oxf-item i{font-size:1rem;opacity:.75}' +
        '.oxf-item:hover:not(:disabled){background:rgba(0,102,204,.08);color:#0066cc}' +
        '[data-bs-theme=dark] .oxf-item:hover:not(:disabled){background:rgba(106,169,255,.12);color:#9cc5ff}' +
        '.oxf-item:disabled{opacity:.4;cursor:default}' +
        '.oxf-sep{height:1px;margin:4px 2px;background:rgba(0,0,0,.08)}' +
        '[data-bs-theme=dark] .oxf-sep{background:rgba(255,255,255,.1)}' +
        '.oxf-search{position:relative;margin:4px 2px 6px}' +
        '.oxf-search i{position:absolute;left:9px;top:50%;translate:0 -50%;opacity:.5;font-size:.9rem}' +
        '.oxf-search input{width:100%;height:30px;padding:3px 9px 3px 28px;font-size:.78rem;border-radius:8px;' +
            'border:1px solid rgba(0,0,0,.18);background:transparent;color:inherit;outline:none}' +
        '[data-bs-theme=dark] .oxf-search input{border-color:rgba(255,255,255,.18)}' +
        '.oxf-search input:focus{border-color:#0066cc;box-shadow:0 0 0 3px rgba(0,102,204,.15)}' +
        '.oxf-list{max-height:240px;overflow:auto;margin:0 2px;padding:4px;border-radius:8px;border:1px solid rgba(0,0,0,.1)}' +
        '[data-bs-theme=dark] .oxf-list{border-color:rgba(255,255,255,.1)}' +
        '.oxf-opt{display:flex;align-items:center;gap:7px;margin:0;padding:3px 5px;border-radius:5px;cursor:pointer;white-space:nowrap}' +
        '.oxf-opt:hover{background:rgba(0,102,204,.06)}' +
        '.oxf-opt input{margin:0;flex:none;cursor:pointer}' +
        '.oxf-opt span{overflow:hidden;text-overflow:ellipsis}' +
        '.oxf-all{font-weight:600}' +
        '.oxf-blank{font-style:italic;opacity:.75}' +
        '.oxf-note{margin:4px 4px 0;font-size:.7rem;opacity:.65}' +
        '.oxf-note:empty{display:none}' +
        '.oxf-foot{display:flex;justify-content:flex-end;gap:6px;margin-top:8px;padding:0 2px 2px}' +
        '.oxf-foot .btn{min-width:72px}' +
        'html.sf-reduced .oxf-menu{animation:none}' +
        '@media (prefers-reduced-motion:reduce){.oxf-menu{animation:none}.oxf-btn{transition:none}}';
    var style = document.createElement('style');
    style.id = 'otc-excel-filter-css';
    style.textContent = css;
    document.head.appendChild(style);

    w.otcExcelFilter = otcExcelFilter;
})(window, window.jQuery);

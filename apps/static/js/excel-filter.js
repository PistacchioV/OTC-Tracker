/* ──────────────────────────────────────────────────────────────────────────
 * excel-filter.js — o filtro "de Excel" no cabeçalho de uma DataTable
 *
 * Cada coluna ganha um funil no cabeçalho que abre um menu como o do Excel:
 * ordenar A→Z / Z→A, limpar o filtro da coluna, busca e a LISTA dos valores
 * distintos com caixinhas ((Selecionar tudo), (Vazias)), OK e Cancelar. Os
 * filtros de várias colunas se somam (E), e a lista de cada coluna mostra só
 * os valores que sobram depois dos filtros das OUTRAS — como no Excel.
 *
 * O filtro é um `DataTable.ext.search` próprio: não briga com o
 * `column().search()` nem com a busca global que a página ainda use.
 *
 * Carregado pelo layout base, liga-se SOZINHO a toda DataTable do app (as
 * que existem e as que nascem depois, pelo `init.dt`), REMOVE a linha de
 * filtro por coluna (que ele substitui) e pula as colunas sem dado (checkbox,
 * Actions, `searchable: false`). O "Clear Filters" de cada tela limpa os
 * funis também. Uma tabela fica de fora com `data-excel-filter="off"`.
 *
 *   otcExcelFilter('#tabela', { skip: [0, 1] })  // a página escolhe as colunas
 *   otcExcelFilter.clear('#tabela')              // limpa uma tabela
 *   otcExcelFilter.clearAll()                    // limpa todas (o Clear Filters)
 *
 * O valor comparado é o TEXTO da célula como a tela mostra (sem HTML), para
 * o que a pessoa marca ser exatamente o que ela lê.
 *
 * Piloto no Operations B3 e, aprovado, em todas as tabelas (29/09/2026).
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
              addSel: 'Add current selection to filter',
              ok: 'OK', cancel: 'Cancel', more: 'Showing the first {n} values — use the search to narrow.',
              none: 'No values.', title: 'Filter' },
        br: { asc: 'Classificar de A a Z', desc: 'Classificar de Z a A', clear: 'Limpar filtro de', search: 'Pesquisar',
              all: '(Selecionar Tudo)', allRes: '(Selecionar Todos os Resultados)', blanks: '(Vazias)',
              addSel: 'Adicionar seleção atual ao filtro',
              ok: 'OK', cancel: 'Cancelar', more: 'Mostrando os primeiros {n} valores — use a pesquisa para filtrar.',
              none: 'Nenhum valor.', title: 'Filtrar' },
        es: { asc: 'Ordenar de A a Z', desc: 'Ordenar de Z a A', clear: 'Borrar filtro de', search: 'Buscar',
              all: '(Seleccionar todo)', allRes: '(Seleccionar todos los resultados)', blanks: '(Vacías)',
              addSel: 'Agregar selección actual al filtro',
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

    // O valor da célula é o que o DataTables DESENHA nela (`render('display')`,
    // sem HTML) — nunca `data()[col]`: tabela montada com objetos
    // (`columns: [{data: 'campo'}]`) não tem posição, e `row[3]` saía
    // `undefined` em toda linha, a lista inteira virando "(Vazias)" ou nada.
    function cellKey(dt, rowIdx, col) {
        var v;
        try { v = dt.cell(rowIdx, col).render('display'); } catch (e) { v = ''; }
        return keyOf(cellText(v));
    }

    // ── o filtro em si: um ext.search para todas as tabelas ligadas ────────
    DT.ext.search.push(function (settings, searchData, dataIndex) {
        var st = STATE.get(settings.nTable);
        if (!st) return true;
        var cols = Object.keys(st.filters);
        if (!cols.length) return true;
        for (var i = 0; i < cols.length; i++) {
            var c = +cols[i];
            if (!st.filters[c].has(cellKey(st.dt, dataIndex, c))) return false;
        }
        return true;
    });

    // Valores distintos da coluna `col` entre as linhas que passam nos filtros
    // das OUTRAS colunas (o que o Excel mostra na lista).
    function distinct(st, col) {
        var dt = st.dt;
        var others = Object.keys(st.filters).filter(function (c) { return +c !== col; });
        var seen = Object.create(null), out = [];
        dt.rows().every(function (rowIdx) {
            for (var i = 0; i < others.length; i++) {
                var oc = +others[i];
                if (!st.filters[oc].has(cellKey(dt, rowIdx, oc))) return;
            }
            var k = cellKey(dt, rowIdx, col);
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
            '<label class="oxf-add" hidden><input type="checkbox"><span>' + esc(t('addSel')) + '</span></label>' +
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
        var addBox = el.querySelector('.oxf-add');
        var addSel = addBox.querySelector('input');

        // A busca aceita LISTA (`123; 456`, os Trade IDs colados de uma
        // coluna do Excel): o valor entra se casar com QUALQUER item — era o
        // que a linha de filtro fazia pelo sf-multi.js. A vírgula não separa
        // (é o milhar de `1,250,000`).
        function matches() {
            var q = norm(input.value).toLowerCase();
            if (!q) return values;
            var toks = q.split(/\s*[;\t\r\n]\s*/).filter(Boolean);
            return values.filter(function (v) {
                var txt = (v === BLANK ? t('blanks') : v).toLowerCase();
                return toks.some(function (tk) { return txt.indexOf(tk) !== -1; });
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
            // "Adicionar seleção atual ao filtro" (o do Excel): só faz sentido
            // pesquisando numa coluna que JÁ tem filtro — marcado, o OK SOMA os
            // resultados escolhidos ao que já estava filtrado, em vez de trocar.
            addBox.hidden = !(searching && current);
            if (addBox.hidden) addSel.checked = false;
            var all = list.querySelector('[data-all]');
            if (all) all.indeterminate = !allOn && someOn;
            note.textContent = !vis.length ? t('none')
                : (vis.length > MAX_ITEMS ? t('more').replace('{n}', MAX_ITEMS) : '');
            // Sem busca, OK exige ao menos um marcado (como o Excel). Com busca,
            // o que vale é o marcado ENTRE os resultados.
            okBtn.disabled = !vis.some(function (v) { return checked.has(v); }) && !addSel.checked;
            list._vis = vis;
        }

        addSel.addEventListener('change', render);
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
            if (searching && current && addSel.checked) {
                // Soma ao filtro que já estava (inclusive o que a lista não
                // mostrava, por estar fora dos filtros das outras colunas).
                var union = new Set(current);
                keep.forEach(function (v) { union.add(v); });
                st.filters[col] = union;
            } else if (!searching && keep.length === values.length) delete st.filters[col];
            else st.filters[col] = new Set(keep);
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
        input.addEventListener('paste', function (e) {
            var cb = e.clipboardData || w.clipboardData;
            var txt = cb ? cb.getData('text') : '';
            if (!/[\t\r\n]/.test(txt)) return;
            e.preventDefault();
            input.value = txt.split(/[\t\r\n]+/).map(function (x) { return x.trim(); })
                             .filter(Boolean).join('; ');
            input.dispatchEvent(new Event('input'));
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

    // Colunas sem funil: as que a página passou em `skip` e, no modo
    // automático, as que não têm o que filtrar — cabeçalho vazio, a de
    // checkbox (o "marcar todos"), a de Actions, e a que a página declarou
    // `searchable: false` (é como ela diz que a coluna não é dado).
    var ACTIONS_RE = /^(actions?|a[cç][oõ]es|acciones|a[cç][aã]o|acci[oó]n)$/i;
    function skipColumn(st, dt, idx) {
        if (st.skip.indexOf(idx) !== -1) return true;
        if (!st.auto) return false;
        var th = dt.column(idx).header();
        if (!th) return true;
        if (th.querySelector('input[type=checkbox]')) return true;
        var txt = norm($(th).clone().find('.oxf-btn').remove().end().text());
        if (!txt || ACTIONS_RE.test(txt)) return true;
        var col = dt.settings()[0].aoColumns[idx];
        return !!(col && col.bSearchable === false);
    }

    function addButtons(st) {
        var dt = st.dt;
        var node = dt.table().node();
        dt.columns().every(function (idx) {
            var th = this.header();
            if (!th || th.querySelector('.oxf-btn') || skipColumn(st, dt, idx)) return;
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
                // O estado VIGENTE da tabela, não o da hora em que o botão
                // nasceu: a página pode religar o filtro (rebuild, skip próprio).
                var cur = STATE.get(node);
                if (cur) openMenu(cur, idx, b);
            });
            th.classList.add('oxf-th');
            // No DataTables 2 o cabeçalho é um flex (`.dt-column-header`): o
            // título e o ícone de ordenação. O funil entra como TERCEIRA peça,
            // entre os dois, de tamanho fixo — quem encolhe é o título (quebra,
            // ou "…" onde a página não deixa quebrar). Absoluto no canto ele
            // ficava por cima do texto nas páginas que fixam a largura do th;
            // dentro do título, caía sozinho numa linha ou era cortado.
            var hdr = th.querySelector('.dt-column-header');
            if (hdr) hdr.insertBefore(b, hdr.querySelector('.dt-column-order'));
            else th.appendChild(b);
        });
        paint(st);
    }

    // Título cortado ("CETIP CONTRAC…"): páginas que fixam a largura de cada
    // coluna no CSS (as Intrag, o Reference Data) mediram o th para o TEXTO,
    // e o funil tirou ~20px dali. Essas tabelas são `table-layout: fixed` —
    // min-width no th não vale nada —, então a largura nova vai para o
    // PRÓPRIO DataTables (`sWidthOrig`/`sWidth` da coluna) e o `adjust` a
    // aplica no cabeçalho e no corpo. Ele mede de novo numa tabela oculta, e
    // uma passada só não fecha (27 → 17 → 0 na Intrag NDF): até três.
    // Idempotente: sem título cortado, não mexe em nada.
    function widenTruncated(dt) {
        var s0 = dt.settings()[0];
        for (var pass = 0; pass < 3; pass++) {
            var mudou = false;
            dt.columns().every(function (i) {
                var th = this.header();
                var title = th && th.querySelector('.oxf-btn') && th.querySelector('.dt-column-title');
                if (!title || !th.offsetWidth) return;
                // o que falta: o título cortado ("…" nele) OU o cabeçalho inteiro
                // (título + funil + ícone de ordenação) passando do th — aí
                // quem corta é o th, e o título sozinho parece caber
                var hdr = th.querySelector('.dt-column-header') || title;
                var falta = Math.max(title.scrollWidth - title.clientWidth,
                                     hdr.scrollWidth - hdr.clientWidth,
                                     th.scrollWidth - th.clientWidth);
                if (falta <= 1) return;
                var w = (th.offsetWidth + falta + 2) + 'px';
                s0.aoColumns[i].sWidthOrig = w;
                s0.aoColumns[i].sWidth = w;
                th.style.width = w;
                th.style.minWidth = w;
                mudou = true;
            });
            if (!mudou) return;
            try { dt.columns.adjust(); } catch (e) { return; }
            // linha montada pela página depois da init (initComplete)
            removeFilterRows(dt);
        }
    }

    // Título CENTRADO de verdade. O cabeçalho é um flex "título · funil ·
    // ordenação", e o título centrava só no espaço que SOBRA: ficava à esquerda
    // do texto do corpo pela largura dos ícones (~20px), em toda tabela
    // centralizada (§7). A largura do que está à direita do título vira o mesmo
    // respiro à ESQUERDA (medida: coluna sem funil ou sem ordenação não tem os
    // ícones), e o DataTables REMEDE as colunas com ele (`columns.adjust`), que
    // é o que alarga cabeçalho e corpo JUNTOS. Alargar só o th (o caminho do
    // `widenTruncated`) deixava as duas larguras diferentes e o desalinho
    // acumulava coluna a coluna. Devolve se algum respiro mudou.
    // Só no th centralizado.
    function centerTitles(dt) {
        var mudou = false;
        $(dt.table().container()).find('thead th').each(function () {
            var h = this.querySelector('.dt-column-header');
            var ti = h && h.querySelector('.dt-column-title');
            if (!ti) return;
            var antes = h.style.paddingLeft;
            var pad = '';
            if (getComputedStyle(this).textAlign === 'center') {
                h.classList.add('oxf-ctr');
                var gap = parseFloat(getComputedStyle(h).columnGap) || 0, w = 0;
                for (var el = ti.nextElementSibling; el; el = el.nextElementSibling) {
                    var es = getComputedStyle(el);
                    if (es.display === 'none' || es.position === 'absolute') continue;
                    w += el.offsetWidth + (parseFloat(es.marginLeft) || 0) + (parseFloat(es.marginRight) || 0) + gap;
                }
                // `oxfCap`: o teto que a coluna aguenta (ver centerAndAdjust)
                var cap = parseFloat(h.dataset.oxfCap);
                if (!isNaN(cap)) w = Math.min(w, cap);
                pad = w >= 1 ? (Math.round(w) + 'px') : '';
            } else {
                h.classList.remove('oxf-ctr');
            }
            if (pad !== antes) { h.style.paddingLeft = pad; mudou = true; }
        });
        return mudou;
    }
    // Página que trava o cabeçalho (`white-space: nowrap`, `min-width` no th —
    // o Pending Confirmation) não deixa o DataTables encaixar o respiro: o th
    // estica sozinho e o corpo não acompanha. Depois do adjust, a coluna cujo
    // cabeçalho passou do corpo perde do respiro exatamente o excesso (teto
    // guardado em `data-oxf-cap`), e o adjust roda de novo.
    function centerAndAdjust(dt) {
        if (!centerTitles(dt)) return;
        try { dt.columns.adjust(); } catch (e) { return; }
        var box = dt.table().container();
        var head = box.querySelector('.dt-scroll-head thead') || dt.table().header();
        var tr = box.querySelector('.dt-scroll-body tbody tr') || dt.table().body().querySelector('tr');
        if (!head || !tr || tr.querySelector('.dt-empty')) return;
        var ths = head.querySelectorAll('tr:last-child > th'), tds = tr.children, corrigiu = false;
        for (var i = 0; i < ths.length && i < tds.length; i++) {
            var excesso = ths[i].offsetWidth - tds[i].offsetWidth;
            var h = ths[i].querySelector('.dt-column-header');
            if (excesso < 1 || !h || !h.style.paddingLeft) continue;
            var cap = Math.max(0, (parseFloat(h.style.paddingLeft) || 0) - excesso);
            // as DUAS cópias do cabeçalho (a visível e a que mede no corpo)
            $(box).find('thead tr:last-child > th:nth-child(' + (i + 1) + ') .dt-column-header').each(function () {
                this.dataset.oxfCap = String(cap);
            });
            corrigiu = true;
        }
        if (corrigiu && centerTitles(dt)) { try { dt.columns.adjust(); } catch (e) {} }
    }

    // A linha de filtro por coluna (a 2ª linha do <thead>, com um campo por
    // coluna) saiu: o funil a substitui em todas as tabelas (mesa, 29/09/2026),
    // e ela é REMOVIDA, não escondida (mesa, 29/09/2026). O DataTables redesenha
    // o cabeçalho a partir do layout que leu na init (`aoHeader`, uma entrada
    // por <tr> com o `.row` dele) e recolocaria a linha apagada só do DOM; por
    // isso ela sai em dois tempos:
    //   1. no `options.dt`, que o DataTables dispara ANTES de ler o cabeçalho —
    //      a linha nem entra no layout (é o caminho de quase toda tela, que
    //      monta a tabela depois deste arquivo carregar);
    //   2. depois da init, para a tabela que nasceu antes deste arquivo ou a
    //      linha que a página montou no `initComplete`: sai do `aoHeader` E do
    //      DOM.
    // O que estava digitado nela é limpo, senão a tabela seguiria filtrada por
    // um campo que ninguém vê.
    var FIELD_SEL = 'input:not([type=checkbox]):not([type=radio]):not([type=hidden]), select, textarea';
    function isFilterRow(tr) {
        if (!tr.querySelector(FIELD_SEL)) return false;
        // A linha de TÍTULOS nunca: é a que tem o texto das colunas.
        return !Array.prototype.some.call(tr.children, function (c) {
            return !c.querySelector(FIELD_SEL) && norm(c.textContent) !== '';
        });
    }
    function filterRowsIn(root) {
        return $(root).find('thead tr').addBack('tr').filter(function () {
            return isFilterRow(this);
        }).get();
    }
    // Quem fica de fora do funil (`data-excel-filter="off"`, `serverSide`,
    // `searching: false`) fica também com a linha: ali ela pode ser o único
    // filtro que a tela tem.
    function keepsOwnFilters(node, opts) {
        if (node.getAttribute('data-excel-filter') === 'off') return true;
        opts = opts || {};
        return opts.serverSide === true || opts.bServerSide === true ||
               opts.searching === false || opts.bFilter === false;
    }
    $(document).on('options.dt.oxf', function (e, opts) {
        if (e.namespace !== 'dt' || !e.target || e.target.nodeName !== 'TABLE') return;
        if (keepsOwnFilters(e.target, opts)) return;
        filterRowsIn(e.target.tHead).forEach(function (tr) { tr.parentNode.removeChild(tr); });
    });
    function removeFilterRows(dt) {
        var changed = false;
        var s0 = dt.settings()[0];
        var rows = [];
        [dt.table().header(), dt.table().container()].forEach(function (root) {
            filterRowsIn(root).forEach(function (tr) { if (rows.indexOf(tr) < 0) rows.push(tr); });
        });
        rows.forEach(function (tr) {
            $(tr).find(FIELD_SEL).each(function () { if (this.value) changed = true; });
            if (s0 && Array.isArray(s0.aoHeader)) {
                s0.aoHeader = s0.aoHeader.filter(function (layoutRow) { return layoutRow.row !== tr; });
            }
            if (tr.parentNode) tr.parentNode.removeChild(tr);
        });
        dt.columns().every(function () {
            if (this.search()) { this.search(''); changed = true; }
        });
        return changed;
    }

    function attach(dt, opts) {
        opts = opts || {};
        var node = dt.table().node();
        if (node.getAttribute('data-excel-filter') === 'off') return null;
        var s0 = dt.settings()[0];
        if (s0 && s0.oFeatures && s0.oFeatures.bServerSide) return null;   // filtra no servidor
        // `searching: false` desliga TODA filtragem do DataTables, a do funil
        // inclusive: o menu abriria e marcar valores não mudaria nada. São as
        // tabelas escondidas que só servem ao Export (Tickets, Advanced Export).
        if (s0 && s0.oFeatures && s0.oFeatures.bFilter === false) return null;
        var prev = STATE.get(node);
        // Reconstruir a tabela (destroy + DataTable) é dado novo: filtro velho
        // não vale mais, como o SELECTED da página. Religar a MESMA instância
        // (a página chamando depois do automático) mantém o que está filtrado.
        var st = { dt: dt, skip: (opts.skip || []).slice(), auto: !!opts.auto,
                   filters: (prev && prev.dt === dt) ? prev.filters : {} };
        STATE.set(node, st);
        closeMenu();
        if (!opts.auto) {
            // a página escolheu as colunas: refaz os funis por esse critério
            $(dt.table().container()).find('.oxf-btn').remove();
        }
        var changed = removeFilterRows(dt);
        addButtons(st);
        // A tradução da página (data-lang no th) reescreve o cabeçalho e leva o
        // funil junto: ele volta a cada draw (addButtons é idempotente).
        dt.off('draw.oxf').on('draw.oxf', function () {
            var cur = STATE.get(node);
            if (cur) { removeFilterRows(cur.dt); addButtons(cur); centerAndAdjust(cur.dt); widenTruncated(cur.dt); }
        });
        // Linha montada pela página DEPOIS da init (initComplete, dado que
        // chegou): sai no primeiro redesenho do cabeçalho.
        dt.off('column-sizing.oxf').on('column-sizing.oxf', function () {
            var cur = STATE.get(node);
            if (cur) { removeFilterRows(cur.dt); centerTitles(cur.dt); }
        });
        dt.off('destroy.oxf').on('destroy.oxf', function () { closeMenu(); STATE.delete(node); });
        if (changed) dt.draw(false);
        try { dt.columns.adjust(); } catch (e) {}
        centerAndAdjust(dt);
        widenTruncated(dt);
        return dt;
    }

    function otcExcelFilter(selector, opts) {
        var $t = $(selector);
        if (!$t.length || !DT.isDataTable($t[0])) return null;
        return attach($t.DataTable(), opts);
    }

    otcExcelFilter.clear = function (selector) {
        var node = $(selector)[0];
        var st = node && STATE.get(node);
        if (!st) return;
        st.filters = {};
        closeMenu();
        paint(st);
    };

    // Filtro posto por CÓDIGO (deep-link: ?spn= da notificação). A linha de
    // filtro antiga saiu e o `removeFilterRows` zera a busca por coluna, então
    // o `column().search()` que a página fazia era apagado em silêncio. Os
    // valores casam cegos à caixa com os que a coluna DESENHA; sem nenhum
    // casamento o filtro fica com o valor pedido (a tabela vazia diz que não há).
    otcExcelFilter.set = function (selector, col, values) {
        var node = $(selector)[0];
        if (!node || !DT.isDataTable(node)) return false;
        var dt = $(node).DataTable();
        var st = STATE.get(node);
        if (!st || st.dt !== dt) { attach(dt, { auto: true }); st = STATE.get(node); }
        if (!st) return false;
        var wanted = (Array.isArray(values) ? values : [values]).map(function (v) { return norm(v).toUpperCase(); });
        var hit = new Set();
        dt.rows().every(function (rowIdx) {
            var k = cellKey(dt, rowIdx, col);
            if (wanted.indexOf(k.toUpperCase()) >= 0) hit.add(k);
        });
        st.filters[col] = hit.size ? hit : new Set(wanted);
        paint(st);
        dt.draw();
        return true;
    };

    // Limpa os funis de TODAS as tabelas da página (o Clear Filters de cada
    // tela). Devolve as tabelas que tinham filtro, para quem chamou redesenhar.
    otcExcelFilter.clearAll = function () {
        var sujas = [];
        $.fn.dataTable.tables().forEach(function (node) {
            var st = STATE.get(node);
            if (st && Object.keys(st.filters).length) {
                st.filters = {};
                paint(st);
                sujas.push(st.dt);
            }
        });
        closeMenu();
        return sujas;
    };

    // ── modo automático: toda DataTable do app ganha os funis ─────────────
    // Carregado pelo layout base DEPOIS dos scripts da página: as tabelas que
    // já existem são ligadas agora, as que nascem depois (a maioria monta a
    // tabela quando os dados chegam), no `init.dt`.
    function autoAttach(node) {
        try {
            if (!DT.isDataTable(node)) return;
            var dt = $(node).DataTable();
            var cur = STATE.get(node);
            if (cur && cur.dt === dt) return;           // a página já ligou
            attach(dt, { auto: true });
        } catch (e) {
            if (w.console) console.warn('[excel-filter]', e);
        }
    }
    $(document).on('init.dt.oxf', function (e, settings) {
        if (e.namespace !== 'dt') return;
        var node = settings && settings.nTable;
        // depois dos handlers de init da própria página (que ainda podem
        // mexer no cabeçalho, traduzir, montar a linha de filtro)
        if (node) setTimeout(function () { autoAttach(node); }, 0);
    });
    $.fn.dataTable.tables().forEach(autoAttach);

    // O botão "Clear Filters" de cada tela limpa também os funis. As telas
    // têm um id cada (`btnClearFilters`, `obClearFilters`, `cgd-clear`…), e o
    // que elas têm em comum é o rótulo traduzido: `…clear-filters` ou
    // `…btn-clear` no data-lang (o `b3-btn-clear` é "Clear Fields", de um
    // formulário, e fica de fora). O redesenho vai DEPOIS do handler da tela.
    var CLEAR_ID_RE = /clear-?filters?$/i;
    var CLEAR_LANG_RE = /(clear-filters|-btn-clear)$/i;
    function isClearFilters(btn) {
        if (CLEAR_ID_RE.test(btn.id || '') || /^(ob|cgd|cfm)-clear$/.test(btn.id || '')) return true;
        var langs = [btn.getAttribute('data-lang') || ''];
        $(btn).find('[data-lang]').each(function () { langs.push(this.getAttribute('data-lang')); });
        return langs.some(function (l) { return CLEAR_LANG_RE.test(l) && l !== 'b3-btn-clear'; });
    }
    //
    // Botão com `data-oxf-table="#id"` é o Clear Filters de UM card (página
    // com uma tabela por card, como os Summaries): limpa só aquela tabela —
    // os funis, a busca por coluna e a global —, sem JS nenhum na página.
    document.addEventListener('click', function (e) {
        var btn = e.target.closest && e.target.closest('button, a.btn');
        if (!btn) return;
        var alvo = btn.getAttribute('data-oxf-table');
        if (alvo) {
            var node = $(alvo)[0];
            if (!node || !DT.isDataTable(node)) return;
            var dt = $(node).DataTable();
            otcExcelFilter.clear(alvo);
            dt.search('');
            dt.columns().every(function () { if (this.search()) this.search(''); });
            dt.draw();
            return;
        }
        if (!isClearFilters(btn)) return;
        var sujas = otcExcelFilter.clearAll();
        if (sujas.length) setTimeout(function () { sujas.forEach(function (dt) { dt.draw(); }); }, 0);
    });

    // ── estilo (uma vez) — menu pende do <body>: fundo SÓLIDO (§7) ──────────
    var css =
        // Com scrollX o DataTables deixa uma CÓPIA do cabeçalho dentro do corpo
        // (altura zero, só para medir as larguras): o funil dela some da vista
        // mas OCUPA o espaço (visibility, não display), para a medida bater.
        '.dt-scroll-body thead .oxf-btn,.dataTables_scrollBody thead .oxf-btn{visibility:hidden!important}' +
        // O funil é uma peça do flex do cabeçalho (ver addButtons), nunca
        // absoluto; o título é que cede espaço.
        '.oxf-btn{position:static!important;display:inline-flex;vertical-align:middle;margin:0 0 0 2px;width:18px;height:18px;padding:0;border:0;' +
            'border-radius:5px;background:transparent;color:var(--ins-secondary-color,#6c757d);opacity:.55;' +
            'align-items:center;justify-content:center;font-size:.8rem;line-height:1;cursor:pointer;flex:none;' +
            'transition:opacity var(--sf-dur-fast,140ms) var(--sf-ease-out,ease-out),background-color var(--sf-dur-fast,140ms) var(--sf-ease-out,ease-out)}' +
        '.oxf-th .dt-column-header{display:flex;align-items:center}' +
        '.dt-column-header.oxf-ctr>.dt-column-title{flex:1 1 auto;text-align:center}' +
        // Palavra não se parte ("FUNCTIONALIT/Y" numa coluna estreita): sem
        // caber, o th transborda e o widenTruncated alarga a coluna.
        '.oxf-th .dt-column-title{min-width:0;overflow:hidden;text-overflow:ellipsis;overflow-wrap:normal;word-break:normal;hyphens:none}' +
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
        '.oxf-add{display:flex;align-items:center;gap:7px;margin:6px 4px 0;padding:3px 5px;cursor:pointer;font-size:.78rem}' +
        '.oxf-add[hidden]{display:none}' +
        '.oxf-add input{margin:0;flex:none;cursor:pointer}' +
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

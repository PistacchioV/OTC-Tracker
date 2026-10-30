/* Database Explorer (Data Base › Database Explorer) — só o MASTER.
 *
 * Banco → tabela → linhas. Os dois combos são de busca (a pasta tem perto de
 * duzentos bancos, e um banco do armazém tem centenas de tabelas). A grade é
 * uma DataTable que se REFAZ a cada tabela (as colunas mudam) e, depois de uma
 * gravação, só troca as linhas — o funil, a ordem e a página ficam.
 *
 * Cada linha chega com o `rowid` e a impressão digital da linha inteira; é ela
 * que o servidor confere antes de gravar (linha que mudou desde a leitura é
 * recusada, nunca sobrescrita). Toda gravação recarrega a grade do banco: no
 * DuckDB o UPDATE de algumas colunas troca o `rowid` da linha.
 */
(function () {
    'use strict';
    var API = '/api/database-explorer';
    var LANG = 'en';
    try { LANG = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    var _TRANS = {};
    function t(k, fb, params) {
        var s = _TRANS[k] || fb || k;
        if (params) s = String(s).replace(/\{(\w+)\}/g, function (m, p) { return params[p] != null ? params[p] : m; });
        return s;
    }

    var S = {
        dbs: [], db: null, dbInfo: null, tables: [], table: null,
        data: null, dt: null, sig: null, byRid: new Map(), sel: new Map(),
        edit: null, pedido: 0, dayCol: -1, day: '',
        expand: undefined,   // undefined = o padrão do servidor; '' = como está gravado
        section: ''          // a seção do objeto aberta na visão expandida ('' = visão geral)
    };

    function el(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function fmtInt(n) { return n == null ? '—' : Number(n).toLocaleString('en-US'); }
    function fmtSize(b) {
        if (b == null) return '';
        var u = ['B', 'KB', 'MB', 'GB'], i = 0, v = b;
        while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
        return (i ? v.toFixed(1) : v) + ' ' + u[i];
    }
    function pad(n) { return (n < 10 ? '0' : '') + n; }
    function fmtEpoch(s) {
        if (!s) return '';
        var d = new Date(s * 1000);
        return pad(d.getDate()) + '/' + pad(d.getMonth() + 1) + '/' + d.getFullYear() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes());
    }
    // A data do banco vem em ISO; a tela a escreve dd/mm/aaaa (§7).
    function dmy(v) {
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v));
        return m ? m[3] + '/' + m[2] + '/' + m[1] : String(v);
    }
    function dmyTime(v) {
        var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}:\d{2}:\d{2})(\.\d+)?$/.exec(String(v));
        return m ? m[3] + '/' + m[2] + '/' + m[1] + ' ' + m[4] + (m[5] || '') : String(v);
    }

    // ── API ──────────────────────────────────────────────────────────────────
    function errText(body, status) {
        if (body && body.code) return t('dbx-e-' + body.code, body.error, body.params || {});
        if (body && body.error) return body.error;
        return t('dbx-e-http', 'Request failed (HTTP {status})', { status: status });
    }
    function api(method, path, body) {
        return fetch(API + path, {
            method: method, credentials: 'same-origin',
            headers: body ? { 'Content-Type': 'application/json' } : {},
            body: body ? JSON.stringify(body) : undefined
        }).then(function (r) {
            return r.json().catch(function () { return null; }).then(function (j) {
                if (!r.ok || !j || j.success === false) {
                    var e = new Error(errText(j, r.status));
                    e.body = j; e.status = r.status;
                    throw e;
                }
                return j;
            });
        });
    }
    function fail(e) {
        if (window.Swal) Swal.fire({ icon: 'error', title: t('dbx-error-title', 'Could not complete'), text: e && e.message || '' });
    }
    function toast(msg) { if (window.otcToast) window.otcToast(msg); }

    // ── combos de busca (nunca <datalist>, §7) ───────────────────────────────
    function Combo(input, menu, opts) {
        var self = this;
        self.input = input; self.menu = menu; self.opts = opts;
        self.list = []; self.active = -1; self.picked = null;
        input.addEventListener('focus', function () { input.select(); self.open(''); });
        input.addEventListener('input', function () { self.open(input.value); });
        input.addEventListener('keydown', function (e) {
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                e.preventDefault();
                if (menu.style.display !== 'block') self.open(input.value);
                var n = self.list.length;
                if (!n) return;
                self.active = (self.active + (e.key === 'ArrowDown' ? 1 : -1) + n) % n;
                self.paint(true);
            } else if (e.key === 'Enter') {
                e.preventDefault();
                if (self.active >= 0 && self.list[self.active]) self.pick(self.list[self.active]);
            } else if (e.key === 'Escape') {
                self.close(); input.blur();
            }
        });
        input.addEventListener('blur', function () {
            setTimeout(function () {
                self.close();
                input.value = self.picked ? opts.label(self.picked) : '';
            }, 120);
        });
        // `mousedown`, antes do blur do campo (§7)
        menu.addEventListener('mousedown', function (e) {
            var o = e.target.closest('[data-ix]');
            e.preventDefault();
            if (o) self.pick(self.list[+o.getAttribute('data-ix')]);
        });
    }
    Combo.prototype.open = function (q) {
        var self = this, opts = self.opts;
        q = String(q || '').trim().toLowerCase();
        var picked = self.picked ? opts.label(self.picked) : null;
        // o campo mostra a escolha atual: reabrir sem digitar lista tudo
        if (picked && q === picked.toLowerCase()) q = '';
        self.list = opts.items().filter(function (it) { return !q || opts.text(it).toLowerCase().indexOf(q) >= 0; });
        self.active = self.list.length ? 0 : -1;
        var html = [], grupo = null;
        self.list.forEach(function (it, i) {
            var g = opts.group ? opts.group(it) : null;
            if (g !== null && g !== grupo) { html.push('<div class="dbx-group">' + esc(g) + '</div>'); grupo = g; }
            html.push('<div class="dbx-opt" data-ix="' + i + '" role="option"><span class="dbx-opt__name">' + esc(opts.label(it)) +
                      '</span><span class="dbx-opt__meta">' + esc(opts.meta(it)) + '</span></div>');
        });
        if (!self.list.length) html.push('<div class="dbx-none">' + esc(t('dbx-no-match', 'No match')) + '</div>');
        self.menu.innerHTML = html.join('');
        self.menu.style.display = 'block';
        self.paint(false);
    };
    Combo.prototype.paint = function (scroll) {
        var self = this;
        Array.prototype.forEach.call(self.menu.querySelectorAll('[data-ix]'), function (o) {
            var on = +o.getAttribute('data-ix') === self.active;
            o.classList.toggle('active', on);
            if (on && scroll) o.scrollIntoView({ block: 'nearest' });
        });
    };
    Combo.prototype.close = function () { this.menu.style.display = 'none'; };
    Combo.prototype.pick = function (it) {
        this.picked = it;
        this.input.value = this.opts.label(it);
        this.close();
        this.input.blur();
        this.opts.onPick(it);
    };
    Combo.prototype.reset = function () { this.picked = null; this.input.value = ''; this.close(); };

    var dbCombo = new Combo(el('dbxDbInput'), el('dbxDbMenu'), {
        items: function () { return S.dbs; },
        label: function (d) { return d.name; },
        text: function (d) { return d.path; },
        meta: function (d) { return fmtSize(d.size); },
        group: function (d) { return d.folder || t('dbx-root', 'Databases folder'); },
        onPick: function (d) { pickDb(d); }
    });
    var tblCombo = new Combo(el('dbxTblInput'), el('dbxTblMenu'), {
        items: function () { return S.tables; },
        label: function (x) { return x.schema === 'main' ? x.name : x.schema + '.' + x.name; },
        text: function (x) { return x.schema + '.' + x.name; },
        meta: function (x) {
            return x.kind === 'view'
                ? t('dbx-view', 'view') + ' · ' + t('dbx-n-cols', '{n} cols', { n: x.columns })
                : '≈ ' + fmtInt(x.rows) + ' · ' + t('dbx-n-cols', '{n} cols', { n: x.columns });
        },
        group: null,
        onPick: function (x) { pickTable(x); }
    });

    // ── banco e tabela ───────────────────────────────────────────────────────
    function loadDbs(fresh) {
        return api('GET', '/databases' + (fresh ? '?fresh=1' : '')).then(function (j) {
            S.dbs = j.databases || [];
            el('dbx-kpi-dbs').textContent = fmtInt(S.dbs.length);
        }).catch(fail);
    }

    function dbMeta() {
        var box = el('dbxDbMeta');
        if (!S.dbInfo) { box.textContent = ''; return; }
        var d = S.dbInfo;
        box.innerHTML = esc(d.db.path) + ' · ' + esc(fmtSize(d.db.size)) + ' · ' +
            esc(t('dbx-modified', 'modified {when}', { when: fmtEpoch(d.db.mtime) })) +
            (d.store ? ' · <b>' + esc(t('dbx-store-ro', 'read-only (data store)')) + '</b>' : '');
    }
    function tblMeta() {
        var x = S.table, box = el('dbxTblMeta');
        if (!x) { box.textContent = S.dbInfo ? t('dbx-n-tables', '{n} tables', { n: S.tables.length }) : ''; return; }
        box.textContent = (x.kind === 'view' ? t('dbx-view', 'view') : '≈ ' + fmtInt(x.rows) + ' ' + t('dbx-rows-word', 'rows')) +
            ' · ' + t('dbx-n-cols', '{n} cols', { n: x.columns });
    }

    function pickDb(d) {
        S.db = d.path; S.dbInfo = null; S.tables = []; S.table = null;
        tblCombo.reset();
        el('dbxTblInput').disabled = true;
        el('dbxLoad').disabled = true;
        el('dbx-kpi-tables').textContent = '…';
        el('dbxDbMeta').textContent = t('dbx-reading', 'Reading…');
        tblMeta();
        clearGrid();
        var meu = ++S.pedido;
        api('GET', '/tables?db=' + encodeURIComponent(d.path)).then(function (j) {
            if (meu !== S.pedido) return;
            S.dbInfo = j; S.tables = j.tables || [];
            el('dbx-kpi-tables').textContent = fmtInt(S.tables.length);
            dbMeta(); tblMeta();
            var inp = el('dbxTblInput');
            inp.disabled = false;
            if (S.tables.length === 1) tblCombo.pick(S.tables[0]);
            else inp.focus();
        }).catch(function (e) {
            if (meu !== S.pedido) return;
            el('dbx-kpi-tables').textContent = '—';
            el('dbxDbMeta').textContent = '';
            fail(e);
        });
    }

    function pickTable(x) {
        S.table = x;
        S.expand = undefined;
        S.section = '';
        el('dbxLoad').disabled = false;
        tblMeta();
        loadRows(false);
    }

    // ── as linhas ────────────────────────────────────────────────────────────
    function clearGrid() {
        if (S.dt) { S.dt.destroy(); S.dt = null; }
        S.data = null; S.sig = null; S.sel.clear(); S.byRid = new Map();
        var tb = el('dbxTable');
        tb.removeAttribute('data-otc-expadv');
        tb.innerHTML = '';
        el('dbxTableWrap').classList.add('d-none');
        el('dbxToolbar').classList.add('d-none');
        el('dbxBanner').classList.add('d-none');
        el('dbxEmpty').classList.remove('d-none');
        el('dbx-kpi-rows').textContent = '—';
        el('dbx-kpi-loaded').textContent = '—';
        syncSel();
    }

    function setBusy(on) {
        var b = el('dbxLoad');
        b.disabled = on || !S.table;
        b.querySelector('i').className = on ? 'ti ti-loader-2 otc-spin me-1' : 'ti ti-database-search me-1';
        el('dbxRefresh').classList.toggle('is-busy', on);
    }

    // `keep`: as mesmas colunas só trocam as linhas (filtro, ordem e página ficam).
    function loadRows(keep) {
        if (!S.db || !S.table) return Promise.resolve();
        var meu = ++S.pedido;
        setBusy(true);
        return api('POST', '/rows', {
            db: S.db, schema: S.table.schema, table: S.table.name, limit: +el('dbxLimit').value,
            expand: S.expand, section: S.section || null
        }).then(function (j) {
            if (meu !== S.pedido) return;
            S.data = j;
            render(keep);
        }).catch(function (e) {
            if (meu !== S.pedido) return;
            fail(e);
        }).finally(function () { if (meu === S.pedido) setBusy(false); });
    }

    function banner() {
        var d = S.data, b = el('dbxBanner'), partes = [];
        if (d.readonly && d.readonly !== 'expanded') {
            partes.push('<i class="ti ti-lock me-1"></i>' + t('dbx-ro-' + d.readonly, 'Read-only.'));
        }
        if (d.expanded && d.section) {
            partes.push('<i class="ti ti-table me-1"></i>' + t('dbx-expanded-section',
                'Section <b>{sec}</b> of the JSON in <b>{col}</b>: {n} rows. Read-only — pick another one in Section, or "Overview" to see the fields.',
                { sec: esc(d.section), col: esc(d.expanded), n: fmtInt(d.rows.length) }));
        } else if (d.expanded && (d.sections || []).length) {
            partes.push('<i class="ti ti-table me-1"></i>' + t('dbx-expanded-overview',
                'The JSON in <b>{col}</b> has {n} tables inside it. Pick one in Section — or click the row count in its column — to see it as a table.',
                { col: esc(d.expanded), n: fmtInt(d.sections.length) }));
        } else if (d.expanded) {
            partes.push('<i class="ti ti-table me-1"></i>' + t('dbx-expanded',
                'The JSON in <b>{col}</b> is shown as a table: {n} rows from {m} records. Read-only — pick "As stored" in View to see the column as saved.',
                { col: esc(d.expanded), n: fmtInt(d.rows.length), m: fmtInt(d.source_rows) }));
        }
        if (d.truncated) {
            partes.push('<i class="ti ti-info-circle me-1"></i>' + esc(t('dbx-truncated',
                'The expansion stopped at {n} rows.', { n: fmtInt(d.rows.length) })));
        }
        var lidas = d.source_rows != null ? d.source_rows : d.rows.length;
        if (d.total > lidas) {
            partes.push('<i class="ti ti-info-circle me-1"></i>' + esc(t('dbx-partial',
                'Showing the first {n} of {total} rows — raise "Rows" to load more.',
                { n: fmtInt(lidas), total: fmtInt(d.total) })));
        }
        b.innerHTML = partes.join('<br>');
        b.classList.toggle('d-none', !partes.length);
    }

    function shown(c, v) {
        if (c.kind === 'date' && typeof v === 'string') return dmy(v);
        if (c.kind === 'timestamp') return dmyTime(v);
        if (typeof v === 'boolean') return v ? 'true' : 'false';
        return String(v);
    }
    // número decimal com separador de milhar NA TELA, até 8 casas (o resto é
    // o ruído do float: 230927.6600000002); o Export leva o cru
    function disp(c, v) {
        if (typeof v === 'number' && c.kind === 'float') return v.toLocaleString('en-US', { maximumFractionDigits: 8 });
        return shown(c, v);
    }
    // ── JSON dentro da célula: nunca o texto cru ────────────────────────────
    // Lista de valores simples vira o texto deles separados por vírgula; lista
    // de registros ou objeto vira um link ("3 rows ›", "5 fields ›") que abre a
    // janela com a tabela. O Export segue com o JSON cru (é o dado gravado).
    var JSON_MEMO = new Map();
    function asJson(v) {
        if (v !== null && typeof v === 'object') return v;
        if (typeof v !== 'string') return undefined;
        var s0 = v.charAt(0);
        if (s0 !== '[' && s0 !== '{') return undefined;
        if (JSON_MEMO.has(v)) return JSON_MEMO.get(v);
        var out;
        try { out = JSON.parse(v); } catch (e) { out = undefined; }
        if (out !== null && typeof out !== 'object') out = undefined;
        if (JSON_MEMO.size > 5000) JSON_MEMO.clear();
        JSON_MEMO.set(v, out);
        return out;
    }
    function nRows(n) {
        return n === 1 ? t('dbx-sec-row', '1 row') : t('dbx-sec-rows', '{n} rows', { n: fmtInt(n) });
    }
    function isPlain(x) { return x === null || typeof x !== 'object'; }
    // o texto curto que a célula mostra no lugar do JSON (e o funil compara)
    function jsonLabel(j) {
        if (Array.isArray(j)) {
            if (!j.length) return t('dbx-json-empty', 'empty');
            if (j.every(isPlain)) return j.map(function (x) { return x === null ? 'NULL' : String(x); }).join(', ');
            if (j.every(function (x) { return x && typeof x === 'object' && !Array.isArray(x); })) {
                return nRows(j.length);
            }
            return t('dbx-json-items', '{n} items', { n: fmtInt(j.length) });
        }
        var n = Object.keys(j).length;
        return n ? t('dbx-json-fields', '{n} fields', { n: fmtInt(n) }) : t('dbx-json-empty', 'empty');
    }
    // abre na janela? (lista de valores simples e vazio já se leem na célula)
    function jsonOpens(j) {
        if (Array.isArray(j)) return j.length > 0 && !j.every(isPlain);
        return Object.keys(j).length > 0;
    }
    function jsonCell(j, attrs) {
        var lab = esc(jsonLabel(j));
        if (!jsonOpens(j)) return '<span class="dbx-json-flat">' + lab + '</span>';
        return '<a href="#" class="dbx-json-link" ' + attrs + '>' + lab + ' <i class="ti ti-chevron-right"></i></a>';
    }

    function cellRender(c) {
        return function (v, type, _row, meta) {
            if (c.kind === 'section' && v != null) {
                // a contagem da seção abre a seção (visão geral do objeto)
                if (type === 'display') return '<a href="#" class="dbx-sec-link" data-sec="' + esc(c.section || c.name) + '">' +
                    esc(nRows(v)) + ' <i class="ti ti-chevron-right"></i></a>';
                return v;
            }
            var j = (type === 'display' || type === 'filter' || type === 'sort') ? asJson(v) : undefined;
            if (j !== undefined) {
                if (type !== 'display') return jsonLabel(j);
                return jsonCell(j, 'data-r="' + meta.row + '" data-c="' + meta.col + '" data-name="' + esc(c.name) + '"');
            }
            if (type === 'display') {
                if (v === null || v === undefined) return '<span class="dbx-null">NULL</span>';
                var s = disp(c, v);
                return s.length > 48 ? '<span class="dbx-cell" title="' + esc(s.slice(0, 1500)) + '">' + esc(s) + '</span>' : esc(s);
            }
            if (v === null || v === undefined) return '';
            if (type === 'export') return shown(c, v);
            return v;          // ordenação/filtro pelo cru (a data ISO ordena certo)
        };
    }

    function actions(rid) {
        return '<div class="d-inline-flex gap-1">' +
            '<button type="button" class="btn btn-info btn-sm rounded-circle btn-act btn-row-edit dbx-edit" data-rid="' + rid + '" ' +
            'data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="' + esc(t('dbx-edit', 'Edit')) + '" data-bs-custom-class="tooltip-info"><i class="ti ti-edit"></i></button>' +
            '<button type="button" class="btn btn-danger btn-sm rounded-circle btn-act btn-row-delete dbx-del" data-rid="' + rid + '" ' +
            'data-bs-toggle="tooltip" data-bs-placement="auto" data-bs-title="' + esc(t('dbx-delete', 'Delete')) + '" data-bs-custom-class="tooltip-danger"><i class="ti ti-trash"></i></button>' +
            '</div>';
    }

    function exportButtons() {
        var ec = { columns: ':visible:not(.dbx-noexp)', orthogonal: 'export', modifier: { page: 'all' } };
        function item(ext, icon, label) {
            return { extend: ext, text: '<i class="ti ' + icon + ' me-1 fs-lg align-middle"></i> ' + label,
                     className: 'dropdown-item', footer: true, exportOptions: ec };
        }
        return [{
            extend: 'collection',
            text: '<i class="ti ti-download me-1"></i> Export',
            className: 'btn btn-sm btn-info bg-gradient dropdown-toggle btn-toolbar-all btn-toolbar-export',
            autoClose: true,
            buttons: [
                item('copy', 'ti-copy', 'Copy'),
                item('csv', 'ti-file-type-csv', 'CSV'),
                item('excel', 'ti-file-spreadsheet', 'Excel'),
                item('print', 'ti-printer', 'Print'),
                item('pdf', 'ti-file-text', 'PDF')
            ]
        }];
    }

    function colsMenu(off) {
        var items = S.data.columns.map(function (c, i) {
            return '<li class="dropdown-item"><div class="form-check">' +
                '<input class="form-check-input dbx-colvis" type="checkbox" data-column="' + (i + off) + '" id="dbxCv' + i + '"' + (c.hidden ? '' : ' checked') + '>' +
                '<label class="form-check-label fw-medium" for="dbxCv' + i + '">' + esc(c.name) + '</label></div></li>';
        }).join('');
        el('dbxColsSlot').innerHTML =
            '<div class="dropdown"><button class="btn btn-sm btn-soft-primary dropdown-toggle btn-toolbar-all" type="button" ' +
            'data-bs-toggle="dropdown" data-bs-auto-close="outside"><i class="ti ti-columns me-1"></i>' +
            '<span>' + esc(t('dbx-columns', 'Columns')) + '</span></button>' +
            '<ul class="dropdown-menu dbx-cols-menu">' + items + '</ul></div>';
    }

    function viewSelect(d) {
        var sel = el('dbxView'), cols = d.json_columns || [];
        sel.classList.toggle('d-none', !cols.length);
        sel.innerHTML = '<option value="">' + esc(t('dbx-view-raw', 'View: as stored')) + '</option>' +
            cols.map(function (c) {
                return '<option value="' + esc(c) + '">' + esc(t('dbx-view-expand', 'View: expand JSON in {col}', { col: c })) + '</option>';
            }).join('');
        sel.value = d.expanded || '';
    }

    // ── visão expandida: a SEÇÃO ─────────────────────────────────────────────
    // O objeto de uma rotina (o dia do Pay/Rec) tem várias tabelas dentro
    // (summary, settled, pending_payment…): cada uma é uma seção, aberta em
    // linhas e colunas. "Visão geral" são os campos soltos com a contagem de
    // cada seção.
    function sectionSelect(d) {
        var sel = el('dbxSection'), secs = d.sections || [];
        sel.classList.toggle('d-none', !d.expanded || !secs.length);
        sel.innerHTML = '<option value="">' + esc(t('dbx-section-overview', 'Section: overview (fields)')) + '</option>' +
            secs.map(function (s) {
                return '<option value="' + esc(s.name) + '">' + esc(t('dbx-section', 'Section: {sec} — {n} rows',
                    { sec: s.name, n: fmtInt(s.rows) })) + '</option>';
            }).join('');
        S.section = d.section || '';
        sel.value = S.section;
    }
    function openSection(name) { S.section = name || ''; S.day = ''; loadRows(false); }

    // ── visão expandida: o DIA e o total ─────────────────────────────────────
    // O ledger (e todo JSON por data) se lê UM DIA POR VEZ: o seletor mostra
    // cada dia com quantas linhas ele tem, e a grade fica só com a quebra dele.
    // O filtro é um `ext.search` próprio (o `column().search()` o funil zera).
    function dayColumn(d) {
        if (!d.expanded) return -1;
        for (var i = 0; i < d.columns.length; i++) if (d.columns[i].kind === 'date') return i;
        return -1;
    }
    function daySelect(d, keepDay) {
        var sel = el('dbxDay'), i = dayColumn(d), antes = keepDay ? S.day : '';
        S.dayCol = i; S.day = '';
        sel.classList.toggle('d-none', i < 0);
        if (i < 0) { sel.innerHTML = ''; return; }
        var cont = {}, dias = [];
        d.rows.forEach(function (r) {
            var v = r[i + 2];
            if (v == null) return;
            if (!cont[v]) { cont[v] = 0; dias.push(v); }
            cont[v]++;
        });
        dias.sort();
        sel.innerHTML = '<option value="">' + esc(t('dbx-day-all', 'Day: all ({n} days)', { n: fmtInt(dias.length) })) + '</option>' +
            dias.map(function (v) {
                return '<option value="' + esc(v) + '">' + esc(t('dbx-day', 'Day: {day} — {n} rows', { day: dmy(v), n: fmtInt(cont[v]) })) + '</option>';
            }).join('');
        if (antes && cont[antes]) S.day = antes;
        sel.value = S.day;
    }
    jQuery.fn.dataTable.ext.search.push(function (settings, _data, _idx, row) {
        if (!S.day || S.dayCol < 0 || settings.nTable !== el('dbxTable')) return true;
        return !row || row[S.dayCol + 2] === S.day;
    });

    // o total das colunas decimais, do que a grade MOSTRA (dia e funil incluídos)
    function sumColumns(d) {
        var out = [];
        d.columns.forEach(function (c, i) { if (c.kind === 'float' || c.kind === 'decimal') out.push(i); });
        return out;
    }
    function footerSums(api, d, off) {
        var linhas = api.rows({ search: 'applied' }).data().toArray();
        var ths = jQuery(api.table().footer()).find('th');
        sumColumns(d).forEach(function (i) {
            var s = 0;
            linhas.forEach(function (r) { var v = parseFloat(r[i + 2]); if (!isNaN(v)) s += v; });
            ths.eq(i + off).text(s.toLocaleString('en-US', { maximumFractionDigits: 2 }));
        });
    }

    function render(keep) {
        var d = S.data;
        var editable = !d.readonly;
        viewSelect(d);
        sectionSelect(d);
        daySelect(d, keep);
        S.byRid = new Map();
        if (editable) d.rows.forEach(function (r) { S.byRid.set(r[0], r); });
        S.sel.clear();
        el('dbx-kpi-rows').textContent = fmtInt(d.total);
        el('dbx-kpi-loaded').textContent = fmtInt(d.rows.length);
        banner();
        el('dbxEmpty').classList.add('d-none');
        el('dbxTableWrap').classList.remove('d-none');
        el('dbxToolbar').classList.remove('d-none');
        Array.prototype.forEach.call(document.querySelectorAll('#dbx-page .dbx-edit-only'), function (b) {
            b.classList.toggle('d-none', !editable);
        });

        var sig = JSON.stringify([S.db, S.table.schema, S.table.name, d.columns, d.readonly]);
        if (keep && S.dt && sig === S.sig) {
            S.dt.clear().rows.add(d.rows).draw(false);
            syncSel();
            return;
        }
        S.sig = sig;
        if (S.dt) { S.dt.destroy(); S.dt = null; }
        var tb = el('dbxTable');
        tb.removeAttribute('data-otc-expadv');
        var off = editable ? 2 : 0;
        var somas = sumColumns(d);
        // o rótulo do total vai na primeira coluna que não é somada
        var rotulo = -1;
        for (var k = 0; k < d.columns.length; k++) { if (somas.indexOf(k) < 0) { rotulo = k; break; } }
        tb.innerHTML = '<thead><tr>' +
            (editable ? '<th class="dbx-noexp" style="width:34px"><input type="checkbox" class="form-check-input" id="dbxAll" aria-label="Select all"></th>' +
                        '<th class="dbx-noexp" style="width:84px">' + esc(t('dbx-actions', 'Actions')) + '</th>' : '') +
            d.columns.map(function (c) { return '<th title="' + esc(c.type) + '">' + esc(c.name) + '</th>'; }).join('') +
            '</tr></thead>' +
            (somas.length ? '<tfoot><tr>' + (editable ? '<th class="dbx-noexp"></th><th class="dbx-noexp"></th>' : '') +
                d.columns.map(function (c, i) { return '<th>' + (i === rotulo ? esc(t('dbx-total', 'Total')) : '') + '</th>'; }).join('') +
                '</tr></tfoot>' : '');
        var cols = [];
        if (editable) {
            cols.push({ data: null, orderable: false, searchable: false, className: 'dbx-noexp',
                        render: function (r, type) {
                            return type === 'display' ? '<input type="checkbox" class="form-check-input dbx-sel" data-rid="' + r[0] + '">' : '';
                        } });
            cols.push({ data: null, orderable: false, searchable: false, className: 'dbx-noexp text-nowrap',
                        render: function (r, type) { return type === 'display' ? actions(r[0]) : ''; } });
        }
        d.columns.forEach(function (c, i) {
            cols.push({ data: i + 2, render: cellRender(c), defaultContent: '', visible: !c.hidden });
        });
        S.dt = jQuery(tb).DataTable({
            data: d.rows,
            columns: cols,
            deferRender: true,
            // a visão expandida por data abre agrupada por DIA
            order: S.dayCol >= 0 ? [[off + S.dayCol, 'asc']] : [],
            pageLength: 50,
            lengthChange: false,
            autoWidth: true,
            dom: "rt<'d-md-flex justify-content-between align-items-center mt-2'ip>",
            buttons: exportButtons(),
            language: {
                emptyTable: t('dbx-no-rows', 'The table has no rows.'),
                paginate: {
                    first: '<i class="ti ti-chevrons-left"></i>',
                    previous: '<i class="ti ti-chevron-left"></i>',
                    next: '<i class="ti ti-chevron-right"></i>',
                    last: '<i class="ti ti-chevrons-right"></i>'
                }
            },
            drawCallback: function () { syncSel(); },
            footerCallback: function () { if (somas.length) footerSums(this.api(), d, off); }
        });
        jQuery('#dbxExportSlot').empty().append(S.dt.buttons().container());
        colsMenu(off);
        if (window.otcExportAdvanced) otcExportAdvanced('#dbxTable', { skip: editable ? [0, 1] : [] });
        if (window.otcCellCopy) otcCellCopy('#dbxTable', { skip: editable ? [0, 1] : [] });
    }

    // ── seleção (checkbox) ───────────────────────────────────────────────────
    function syncSel() {
        var n = S.sel.size;
        el('dbxSelCount').textContent = fmtInt(n);
        el('dbxBatchEdit').disabled = !n;
        el('dbxBatchDelete').disabled = !n;
        if (!S.dt) return;
        jQuery(S.dt.table().node()).find('input.dbx-sel').each(function () {
            this.checked = S.sel.has(+this.getAttribute('data-rid'));
        });
        var all = el('dbxAll');
        if (!all) return;
        var vis = S.dt.rows({ search: 'applied' }).data().toArray();
        var marcadas = vis.filter(function (r) { return S.sel.has(r[0]); }).length;
        all.checked = vis.length > 0 && marcadas === vis.length;
        all.indeterminate = marcadas > 0 && marcadas < vis.length;
    }

    jQuery('#dbxTableWrap').on('change', 'input.dbx-sel', function () {
        var rid = +this.getAttribute('data-rid'), r = S.byRid.get(rid);
        if (this.checked && r) S.sel.set(rid, r[1]); else S.sel.delete(rid);
        syncSel();
    });
    // o "todas" marca as linhas que o filtro deixa ver (todas as páginas)
    jQuery('#dbxTableWrap').on('change', '#dbxAll', function () {
        var on = this.checked;
        S.dt.rows({ search: 'applied' }).data().toArray().forEach(function (r) {
            if (on) S.sel.set(r[0], r[1]); else S.sel.delete(r[0]);
        });
        syncSel();
    });

    jQuery('#dbxColsSlot').on('change', '.dbx-colvis', function () {
        if (S.dt) S.dt.column(+this.getAttribute('data-column')).visible(this.checked);
    });

    // ── modal: Edit de uma linha e alteração em lote ─────────────────────────
    function editStr(c, v) {
        if (v === null || v === undefined) return '';
        if (c.kind === 'date') return String(v);          // ISO: é o que o flatpickr guarda
        if (c.kind === 'timestamp') return dmyTime(v);
        if (typeof v === 'boolean') return v ? 'true' : 'false';
        return String(v);
    }

    function fieldHtml(c, i, v, mode) {
        var lbl = esc(c.name) + '<span class="dbx-type">' + esc(c.type) + '</span>';
        if (!c.kind) {
            if (mode === 'batch') return '';
            return '<div class="col-md-6 col-xl-4"><label class="form-label fs-xs text-muted mb-1">' + lbl + '</label>' +
                '<div class="dt-cell-readonly text-truncate" title="' + esc(t('dbx-col-ro', 'This column type is not edited here')) + '">' +
                (v === null || v === undefined ? 'NULL' : esc(v)) + '</div></div>';
        }
        var isNull = mode === 'row' && (v === null || v === undefined);
        var val = mode === 'row' ? editStr(c, v) : '';
        var id = 'dbxF' + i, input;
        if (c.kind === 'bool') {
            input = '<select class="form-select form-select-sm dbx-in" id="' + id + '">' +
                '<option value="true"' + (val === 'true' ? ' selected' : '') + '>true</option>' +
                '<option value="false"' + (val === 'false' ? ' selected' : '') + '>false</option></select>';
        } else if (c.kind === 'json' || (c.kind === 'text' && (val.length > 60 || val.indexOf('\n') >= 0))) {
            input = '<textarea class="form-control form-control-sm dbx-in" id="' + id + '" rows="3">' + esc(val) + '</textarea>';
        } else {
            var ph = c.kind === 'timestamp' ? 'dd/mm/aaaa hh:mm:ss' : '';
            input = '<input type="text" class="form-control form-control-sm dbx-in' + (c.kind === 'date' ? ' otc-datefield' : '') +
                '" id="' + id + '" value="' + esc(val) + '"' + (ph ? ' placeholder="' + ph + '"' : '') + '>';
        }
        var head = mode === 'batch'
            ? '<div class="form-check m-0"><input class="form-check-input dbx-apply" type="checkbox" id="dbxA' + i + '">' +
              '<label class="form-check-label form-label fs-xs text-muted mb-0" for="dbxA' + i + '">' + lbl + '</label></div>'
            : '<label class="form-label fs-xs text-muted mb-0" for="' + id + '">' + lbl + '</label>';
        return '<div class="col-md-6 col-xl-4 dbx-field' + (mode === 'batch' ? ' is-off' : '') + '" data-i="' + i + '">' +
            '<div class="d-flex align-items-center justify-content-between gap-2 mb-1">' + head +
            '<div class="form-check m-0"><input class="form-check-input dbx-null" type="checkbox" id="dbxN' + i + '"' + (isNull ? ' checked' : '') + '>' +
            '<label class="form-check-label fs-xs" for="dbxN' + i + '">NULL</label></div></div>' + input + '</div>';
    }

    // campo desligado = NULL marcado, ou (no lote) coluna não escolhida
    function syncField(f) {
        var nul = f.querySelector('.dbx-null').checked;
        var ap = f.querySelector('.dbx-apply');
        var off = nul || (ap && !ap.checked);
        var inp = f.querySelector('.dbx-in');
        inp.disabled = off;
        if (inp._flatpickr && inp._flatpickr.altInput) inp._flatpickr.altInput.disabled = off;
        f.classList.toggle('is-off', !!(ap && !ap.checked));
    }

    function openEdit(mode, rid) {
        var cols = S.data.columns;
        var row = mode === 'row' ? S.byRid.get(rid) : null;
        if (mode === 'row' && !row) return;
        S.edit = { mode: mode, rid: rid, orig: {} };
        var grid = el('dbxEditGrid');
        grid.innerHTML = cols.map(function (c, i) {
            var v = row ? row[i + 2] : null;
            if (row && c.kind) S.edit.orig[i] = { nul: v === null || v === undefined, val: editStr(c, v) };
            return fieldHtml(c, i, v, mode);
        }).join('');
        Array.prototype.forEach.call(grid.querySelectorAll('.otc-datefield'), function (inp) {
            if (window.otcDateField) otcDateField(inp);
        });
        Array.prototype.forEach.call(grid.querySelectorAll('.dbx-field'), syncField);
        el('dbxEditTitle').textContent = mode === 'row'
            ? t('dbx-edit-title', 'Edit row') + ' · ' + S.table.name
            : t('dbx-batch-title', 'Batch edit — {n} rows', { n: fmtInt(S.sel.size) });
        el('dbxEditNote').innerHTML = esc(mode === 'row'
            ? t('dbx-edit-note', 'Only the fields you change are written. An empty field is NULL in non-text columns.')
            : t('dbx-batch-note', 'Tick the columns to change: the same value goes to every selected row.'));
        bootstrap.Modal.getOrCreateInstance(el('dbxEditModal')).show();
    }

    el('dbxEditGrid').addEventListener('change', function (e) {
        if (e.target.classList.contains('dbx-null') || e.target.classList.contains('dbx-apply')) {
            syncField(e.target.closest('.dbx-field'));
        }
    });

    function collect() {
        var cols = S.data.columns, values = {};
        Array.prototype.forEach.call(el('dbxEditGrid').querySelectorAll('.dbx-field'), function (f) {
            var i = +f.getAttribute('data-i'), c = cols[i];
            var nul = f.querySelector('.dbx-null').checked;
            var val = f.querySelector('.dbx-in').value;
            if (S.edit.mode === 'batch') {
                if (!f.querySelector('.dbx-apply').checked) return;
            } else {
                var o = S.edit.orig[i];
                if (o && o.nul === nul && (nul || o.val === val)) return;
            }
            values[c.name] = { value: nul ? null : val, null: nul };
        });
        return values;
    }

    function items(rids) {
        return rids.map(function (rid) {
            var r = S.byRid.get(rid);
            return { rowid: rid, h: r ? r[1] : (S.sel.get(rid) || '') };
        });
    }

    function grava(path, body, okMsg) {
        return api('POST', path, Object.assign({ db: S.db, schema: S.table.schema, table: S.table.name }, body))
            .then(function (j) {
                toast(okMsg(j));
                S.sel.clear();
                return loadRows(true);
            })
            .catch(function (e) {
                fail(e);
                // linha que mudou desde a leitura: a grade volta a mostrar o banco
                if (e && e.body && e.body.code === 'row_changed') loadRows(true);
            });
    }

    el('dbxEditSave').addEventListener('click', function () {
        if (!S.edit) return;
        var values = collect();
        var nomes = Object.keys(values);
        var modal = bootstrap.Modal.getInstance(el('dbxEditModal'));
        if (!nomes.length) {
            if (S.edit.mode === 'row') { if (modal) modal.hide(); toast(t('dbx-no-changes', 'Nothing changed')); }
            else if (window.Swal) Swal.fire({ icon: 'info', title: t('dbx-pick-columns', 'Tick at least one column to change') });
            return;
        }
        var rids = S.edit.mode === 'row' ? [S.edit.rid] : Array.from(S.sel.keys());
        var vai = function () {
            if (modal) modal.hide();
            grava('/update', { items: items(rids), values: values }, function (j) {
                return t('dbx-done-updated', 'Done: {n} row(s) updated', { n: fmtInt(j.updated) });
            });
        };
        if (S.edit.mode === 'row' || !window.Swal) { vai(); return; }
        Swal.fire({
            icon: 'warning',
            title: t('dbx-batch-confirm', 'Change {n} rows?', { n: fmtInt(rids.length) }),
            text: t('dbx-batch-confirm-cols', 'Columns: {cols}', { cols: nomes.join(', ') }),
            showCancelButton: true,
            confirmButtonText: t('dbx-apply', 'Apply'),
            cancelButtonText: t('dbx-cancel', 'Cancel')
        }).then(function (r) { if (r.isConfirmed) vai(); });
    });

    function apaga(rids) {
        var go = function () {
            grava('/delete', { items: items(rids) }, function (j) {
                return t('dbx-done-deleted', 'Done: {n} row(s) deleted', { n: fmtInt(j.deleted) });
            });
        };
        if (!window.Swal) { go(); return; }
        Swal.fire({
            icon: 'warning',
            title: t('dbx-delete-confirm', 'Delete {n} row(s)?', { n: fmtInt(rids.length) }),
            text: t('dbx-delete-confirm-txt', 'This writes straight to the database and cannot be undone.'),
            showCancelButton: true,
            confirmButtonColor: 'var(--otc-danger)',
            confirmButtonText: t('dbx-delete', 'Delete'),
            cancelButtonText: t('dbx-cancel', 'Cancel')
        }).then(function (r) { if (r.isConfirmed) go(); });
    }

    jQuery('#dbxTableWrap').on('click', '.dbx-edit', function () { openEdit('row', +this.getAttribute('data-rid')); });
    jQuery('#dbxTableWrap').on('click', '.dbx-del', function () { apaga([+this.getAttribute('data-rid')]); });
    el('dbxBatchEdit').addEventListener('click', function () { if (S.sel.size) openEdit('batch'); });
    el('dbxBatchDelete').addEventListener('click', function () { if (S.sel.size) apaga(Array.from(S.sel.keys())); });

    // ── a janela do JSON: a tabela que mora numa célula ──────────────────────
    // Uma pilha: o JSON dentro do JSON abre por cima, e o Back volta.
    var JW = { stack: [], reg: [] };
    function flatObj(o, prefix, out) {
        Object.keys(o).forEach(function (k) {
            var x = o[k], nome = prefix + k;
            if (x && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).length && !jsonOpensAsRows(x)) {
                flatObj(x, nome + '.', out);
            } else {
                out[nome] = x;
            }
        });
        return out;
    }
    function jsonOpensAsRows(o) {
        var ks = Object.keys(o);
        return ks.length > 0 && ks.every(function (k) { return o[k] && typeof o[k] === 'object' && !Array.isArray(o[k]); });
    }
    function jwCell(x) {
        if (x === null || x === undefined) return '<span class="dbx-null">NULL</span>';
        if (typeof x === 'object') {
            if (!jsonOpens(x)) return esc(jsonLabel(x));
            JW.reg.push(x);
            return '<a href="#" class="dbx-json-link" data-j="' + (JW.reg.length - 1) + '">' + esc(jsonLabel(x)) +
                ' <i class="ti ti-chevron-right"></i></a>';
        }
        if (typeof x === 'number') return esc(x.toLocaleString('en-US', { maximumFractionDigits: 8 }));
        if (typeof x === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x)) return esc(dmy(x));
        return esc(String(x));
    }
    // registros (lista de objetos, ou objeto de objetos com a chave na frente)
    function jwRecords(recs, keyName) {
        var campos = [], vistos = {};
        var linhas = recs.map(function (r) {
            var f = flatObj(r.rec, '', {});
            Object.keys(f).forEach(function (k) { if (!vistos[k]) { vistos[k] = 1; campos.push(k); } });
            return { key: r.key, f: f };
        });
        var head = (keyName ? '<th>' + esc(keyName) + '</th>' : '') + campos.map(function (k) { return '<th>' + esc(k) + '</th>'; }).join('');
        var body = linhas.map(function (l) {
            return '<tr>' + (keyName ? '<td>' + esc(l.key) + '</td>' : '') +
                campos.map(function (k) { return '<td>' + jwCell(l.f[k]) + '</td>'; }).join('') + '</tr>';
        }).join('');
        return { head: head, body: body, n: linhas.length };
    }
    function jwTable(v) {
        var t0;
        if (Array.isArray(v)) {
            if (v.every(function (x) { return x && typeof x === 'object' && !Array.isArray(x); })) {
                t0 = jwRecords(v.map(function (x) { return { rec: x }; }), null);
            } else {
                t0 = { head: '<th>#</th><th>' + esc(t('dbx-json-value', 'value')) + '</th>', n: v.length,
                       body: v.map(function (x, i) { return '<tr><td>' + (i + 1) + '</td><td>' + jwCell(x) + '</td></tr>'; }).join('') };
            }
        } else if (jsonOpensAsRows(v)) {
            t0 = jwRecords(Object.keys(v).map(function (k) { return { key: k, rec: v[k] }; }), t('dbx-json-key', 'key'));
        } else {
            var f = flatObj(v, '', {});
            t0 = { head: '<th>' + esc(t('dbx-json-field', 'field')) + '</th><th>' + esc(t('dbx-json-value', 'value')) + '</th>',
                   n: Object.keys(f).length,
                   body: Object.keys(f).map(function (k) { return '<tr><td class="text-start fw-semibold">' + esc(k) + '</td><td class="text-start">' + jwCell(f[k]) + '</td></tr>'; }).join('') };
        }
        return '<div class="otc-mini-table-wrap"><table class="otc-mini-table dbx-json-table"><thead><tr>' + t0.head +
            '</tr></thead><tbody>' + t0.body + '</tbody></table></div>';
    }
    function jwPaint() {
        var top = JW.stack[JW.stack.length - 1];
        JW.reg = [];
        el('dbxJsonTitle').textContent = JW.stack.map(function (s) { return s.title; }).join(' › ');
        el('dbxJsonBody').innerHTML = jwTable(top.value);
        el('dbxJsonBack').classList.toggle('d-none', JW.stack.length < 2);
    }
    function jwOpen(title, value, fresh) {
        if (fresh) JW.stack = [];
        JW.stack.push({ title: title, value: value });
        jwPaint();
        if (fresh) bootstrap.Modal.getOrCreateInstance(el('dbxJsonModal')).show();
    }
    jQuery('#dbxTableWrap').on('click', '.dbx-json-link', function (e) {
        e.preventDefault();
        var r = +this.getAttribute('data-r'), c = +this.getAttribute('data-c');
        var row = S.dt && S.dt.row(r).data();
        var col = S.dt && S.dt.settings()[0].aoColumns[c];
        var j = row && col ? asJson(row[col.mData]) : undefined;
        if (j === undefined) return;
        var quem = S.table ? S.table.name : '';
        jwOpen(quem + ' · ' + this.getAttribute('data-name'), j, true);
    });
    jQuery('#dbxJsonBody').on('click', '.dbx-json-link', function (e) {
        e.preventDefault();
        var x = JW.reg[+this.getAttribute('data-j')];
        if (x === undefined) return;
        var cel = this.closest('td'), th = cel && cel.closest('table').querySelectorAll('thead th')[cel.cellIndex];
        jwOpen(th ? th.textContent : '…', x, false);
    });
    el('dbxJsonBack').addEventListener('click', function () {
        if (JW.stack.length > 1) { JW.stack.pop(); jwPaint(); }
    });

    // ── barra ────────────────────────────────────────────────────────────────
    el('dbxLoad').addEventListener('click', function () { loadRows(false); });
    el('dbxLimit').addEventListener('change', function () { if (S.table) loadRows(true); });
    el('dbxView').addEventListener('change', function () { S.expand = this.value; S.section = ''; loadRows(false); });
    el('dbxSection').addEventListener('change', function () { openSection(this.value); });
    jQuery('#dbxTableWrap').on('click', '.dbx-sec-link', function (e) { e.preventDefault(); openSection(this.getAttribute('data-sec')); });
    el('dbxDay').addEventListener('change', function () { S.day = this.value; if (S.dt) S.dt.draw(); });
    el('dbxRefresh').addEventListener('click', function () { loadRows(true); });
    // o funil limpa sozinho (excel-filter.js reconhece o botão); aqui a busca
    el('dbxClearFilters').addEventListener('click', function () {
        S.day = ''; el('dbxDay').value = '';
        if (S.dt) S.dt.search('').columns().search('').draw();
    });

    // Tooltip colorido criado no primeiro hover (os <td> são reescritos a cada
    // redraw), e escondido no clique (o botão some quando a linha recarrega).
    var TIP = '#dbx-page [data-bs-toggle="tooltip"], #dbxEditModal [data-bs-toggle="tooltip"]';
    jQuery(document).on('mouseenter', TIP, function () {
        if (!bootstrap.Tooltip.getInstance(this)) new bootstrap.Tooltip(this, { trigger: 'hover' }).show();
    });
    jQuery(document).on('click', TIP, function () {
        var inst = bootstrap.Tooltip.getInstance(this);
        if (inst) inst.hide();
    });

    // textos do JS no idioma de quem vê (o I18nManager traduz o HTML uma vez)
    fetch('/static/data/translations/' + LANG + '.json')
        .then(function (r) { return r.json(); })
        .then(function (tr) {
            _TRANS = tr || {};
            dbMeta(); tblMeta();
            if (S.data) render(false);
        })
        .catch(function () {});

    loadDbs(false);
})();

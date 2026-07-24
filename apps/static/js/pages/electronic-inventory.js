/* ==========================================================================
 * Electronic Inventory — per-counterparty document library.
 * Reads the network share through /api/electronic-inventory/*. All type
 * switching / searching happens client-side off a single "all documents"
 * fetch per counterparty, so the doc-type counts stay accurate and switching
 * is instant.
 * ========================================================================== */
(function () {
    'use strict';

    var API = '/api/electronic-inventory';
    var UPLOAD_TIMEOUT_MS = 90000;   // hard ceiling on a save to the (slow) I: share
    var PREVIEW_TIMEOUT_MS = 45000;  // ditto for streaming a PDF into the viewer
    var upModalReady = false;        // upload modal fully shown → dropzones may browse
    var state = {
        clients: [],          // [{name, spn, on_disk}]
        rootExists: false,
        subtypes: [],         // transactional types from the server
        client: null,         // selected counterparty name
        type: 'all',          // active doc-type rail
        subtype: '',          // transactional sub-type filter
        allDocs: [],          // every document for the current client
        selectedRel: null,
        previewTimer: null,   // bounds the "Loading PDF…" veil (see preview())
        confPath: []          // selected Confirmations folder ['2026','06','18','NDF']
    };

    /* ---- tiny helpers ---------------------------------------------------- */
    function $(id) { return document.getElementById(id); }
    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    // Windows-safe name (mirrors routes.py _ei_sanitize) for the filename preview.
    function sanitize(name) {
        return String(name || '').replace(/[<>:"/\\|?*\x00-\x1f]/g, '').replace(/\s+/g, ' ').trim().replace(/[. ]+$/, '');
    }
    function toast(icon, title, text) {
        if (typeof Swal !== 'undefined') {
            Swal.fire({ icon: icon, title: title, text: text || '', confirmButtonColor: '#0066cc',
                timer: icon === 'success' ? 2400 : undefined, showConfirmButton: icon !== 'success' });
        } else if (icon !== 'success') {
            // No SweetAlert2 on the page: still surface anything actionable.
            // Silently dropping warnings made the Upload button look dead when
            // no counterparty was selected.
            alert((title || '') + (text ? '\n' + text : ''));
        }
    }
    function icoFor(ext) {
        ext = String(ext || '').toLowerCase();
        if (ext === 'pdf') return { cls: 'pdf', i: 'ti-file-type-pdf' };
        if (['png', 'jpg', 'jpeg', 'gif'].indexOf(ext) >= 0) return { cls: 'img', i: 'ti-photo' };
        if (['msg', 'eml'].indexOf(ext) >= 0) return { cls: 'mail', i: 'ti-mail' };
        if (['xls', 'xlsx', 'csv'].indexOf(ext) >= 0) return { cls: 'sheet', i: 'ti-file-spreadsheet' };
        if (['doc', 'docx'].indexOf(ext) >= 0) return { cls: '', i: 'ti-file-text' };
        if (ext === 'zip') return { cls: '', i: 'ti-file-zip' };
        return { cls: '', i: 'ti-file' };
    }
    function fileUrl(rel, download) {
        return API + '/file?client=' + encodeURIComponent(state.client) +
               '&rel=' + encodeURIComponent(rel) + (download ? '&download=1' : '');
    }

    /* ---- share status + clients ----------------------------------------- */
    var eiSubtypesSeeded = false;
    function loadClients(isPoll) {
        var lbl0 = $('eiShareLabel');
        fetch(API + '/clients').then(function (r) { return r.json(); }).then(function (res) {
            if (!res || !res.success) {
                $('eiShareDot').className = 'ei-status-dot off';
                if (lbl0) lbl0.textContent = 'Session expired — please sign in again';
                return;
            }
            state.clients = res.clients || [];
            state.rootExists = !!res.root_exists;
            state.scanComplete = !!res.scan_complete;
            state.subtypes = res.transactional_types || [];
            state.confTypes = res.confirmation_types || [];
            var dot = $('eiShareDot'), lbl = $('eiShareLabel');
            if (!state.scanComplete) {
                // Share not fully enumerated yet — names come from RefData so the
                // picker works; we withhold "no folder" badges (unknown, not absent)
                // and poll again shortly to fill in the on-disk state.
                dot.className = 'ei-status-dot slow';
                lbl.textContent = state.clients.length + ' counterparties · checking share…';
                if (!state._pollT) {
                    state._pollT = setTimeout(function () { state._pollT = null; loadClients(true); }, 4000);
                }
            } else if (state.rootExists) {
                dot.className = 'ei-status-dot on';
                lbl.textContent = state.clients.filter(function (c) { return c.on_disk; }).length + ' counterparties on the share';
            } else {
                dot.className = 'ei-status-dot off';
                lbl.textContent = 'Share offline — browsing unavailable';
            }
            // If the combo is currently open, re-render so refreshed badges show.
            if (isPoll && $('eiClientMenu').classList.contains('show')) renderCombo($('eiClientInput').value);
            // seed the transactional sub-type selects (once). The upload modal's
            // select is repopulated per Document Type — see fillSubtypeOptions.
            if (!eiSubtypesSeeded && state.subtypes.length) {
                eiSubtypesSeeded = true;
                var opts = state.subtypes.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join('');
                $('eiSubtypeFilter').insertAdjacentHTML('beforeend', opts);
                fillSubtypeOptions($('eiUpType').value);
            }
        }).catch(function (e) {
            console.error('ei clients error', e);
            $('eiShareDot').className = 'ei-status-dot off';
            if (lbl0) lbl0.textContent = 'Could not load counterparties';
        });
    }

    /* ---- searchable counterparty combo ---------------------------------- */
    var comboKbd = -1;
    var COMBO_PAGE = 60;
    var comboLimit = COMBO_PAGE;     // grows as the user scrolls the menu
    function comboFilter(q) {
        q = (q || '').trim().toLowerCase();
        return state.clients.filter(function (c) {
            return !q || c.name.toLowerCase().indexOf(q) >= 0 || (c.spn && c.spn.indexOf(q) >= 0);
        });
    }
    function renderCombo(q) {
        var menu = $('eiClientMenu');
        var all = comboFilter(q);
        var list = all.slice(0, comboLimit);
        if (!all.length) {
            menu.innerHTML = '<li class="text-muted" style="cursor:default">No match</li>';
        } else {
            var html = list.map(function (c, i) {
                return '<li data-name="' + esc(c.name) + '"' + (i === comboKbd ? ' class="ei-kbd-active"' : '') + '>' +
                    '<span>' + esc(c.name) + '</span>' +
                    (c.on_disk === false ? '<span class="ei-nofolder">no folder</span>' : '') +
                    (c.spn ? '<span class="ei-combo-spn">SPN ' + esc(c.spn) + '</span>' : '') +
                    '</li>';
            }).join('');
            if (all.length > list.length) {
                html += '<li class="ei-combo-more text-muted text-center" style="cursor:default">' +
                        list.length + ' of ' + all.length + ' — scroll for more</li>';
            }
            menu.innerHTML = html;
        }
        menu.classList.add('show');
    }
    // Grow the rendered slice when the user scrolls near the bottom, preserving the
    // current scroll position (innerHTML rebuild would otherwise jump to the top).
    function comboMaybeLoadMore() {
        var menu = $('eiClientMenu');
        var total = comboFilter($('eiClientInput').value).length;
        if (comboLimit >= total) return;
        if (menu.scrollTop + menu.clientHeight >= menu.scrollHeight - 48) {
            var keep = menu.scrollTop;
            comboLimit += COMBO_PAGE;
            renderCombo($('eiClientInput').value);
            menu.scrollTop = keep;
        }
    }
    function closeCombo() { $('eiClientMenu').classList.remove('show'); comboKbd = -1; }

    function selectClient(name) {
        state.client = name;
        // Another counterparty's tree is a different tree — drop the open state
        // so the default expansion runs again instead of leaking stale keys.
        state.confPath = [];
        $('eiClientInput').value = name;
        closeCombo();
        $('eiCurrentClient').textContent = name;
        $('eiUpClient').value = name;
        loadDocuments();
    }

    /* ---- documents ------------------------------------------------------- */
    function loadDocuments() {
        if (!state.client) return;
        var list = $('eiDocList');
        list.innerHTML = '<div class="ei-empty"><div class="spinner-border text-primary" role="status"></div>' +
                         '<div class="fs-sm mt-2">Loading documents…</div></div>';
        fetch(API + '/documents?client=' + encodeURIComponent(state.client) + '&type=all')
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res || !res.success) { state.allDocs = []; renderConfTree(); renderDocs(); return; }
                state.allDocs = res.documents || [];
                updateTypeCounts();
                renderConfTree();
                renderDocs();
                if (!res.folder_exists && !state.rootExists) {
                    list.innerHTML = '<div class="ei-empty"><i class="ti ti-plug-connected-x ei-empty-ico"></i>' +
                        '<div class="fw-semibold">Share offline</div>' +
                        '<div class="fs-sm">Document browsing needs the JPM network share.</div></div>';
                }
            }).catch(function (e) { console.error('ei documents error', e); });
    }

    function updateTypeCounts() {
        var counts = { all: state.allDocs.length, Confirmations: 0, SSI: 0, Transactional: 0 };
        state.allDocs.forEach(function (d) { if (counts[d.doctype] != null) counts[d.doctype]++; });
        document.querySelectorAll('#eiTypeList .ei-type-badge').forEach(function (b) {
            b.textContent = counts[b.dataset.count] || 0;
        });
    }

    /* ---- Confirmations folder navigation --------------------------------
     * The rail mirrors the share: Confirmations › Year › Month › Day › Product.
     * Clicking a level selects it and reveals the level below; the list on the
     * right shows the documents inside the selected folder (and everything
     * under it, so a partial path is never a dead end).
     * ------------------------------------------------------------------- */
    var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                  'July', 'August', 'September', 'October', 'November', 'December'];

    function monthLabel(mm) {
        var n = parseInt(mm, 10);
        return MONTHS[n - 1] ? mm + '. ' + MONTHS[n - 1] : mm;
    }

    // ['2026','06','18','NDF'] for a confirmation; [] when the date is unreadable.
    function docPath(d) {
        var p = (d.doc_date || '').split('/');       // dd/mm/yyyy
        if (p.length !== 3) return [];
        return [p[2], p[1], p[0], (d.subtype || 'Other').toUpperCase()];
    }

    function labelFor(seg, depth) { return depth === 1 ? monthLabel(seg) : seg; }

    function matchesSearch(d) {
        var q = ($('eiDocSearch').value || '').trim().toLowerCase();
        if (!q) return true;
        return d.name.toLowerCase().indexOf(q) >= 0 || (d.subtype || '').toLowerCase().indexOf(q) >= 0;
    }

    // Nested counts for the confirmations under the current search, so the rail
    // never offers a folder that would open empty.
    function confTree() {
        var root = {};
        state.allDocs.forEach(function (d) {
            if (d.doctype !== 'Confirmations' || !matchesSearch(d)) return;
            var path = docPath(d);
            if (!path.length) return;
            var node = root;
            path.forEach(function (seg) {
                node[seg] = node[seg] || { __n: 0, __c: {} };
                node[seg].__n++;
                node = node[seg].__c;
            });
        });
        return root;
    }

    function confBranchHtml(nodes, depth, prefix) {
        var keys = Object.keys(nodes).sort();
        // Years, months and days read newest-first; products stay alphabetical.
        if (depth < 3) keys.reverse();
        return keys.map(function (seg) {
            var path = prefix.concat([seg]);
            var onPath = state.confPath.length > depth && state.confPath[depth] === seg;
            var isSel = onPath && state.confPath.length === path.length;
            var kids = nodes[seg].__c;
            var hasKids = Object.keys(kids).length > 0;
            return '<div class="ei-fold" data-depth="' + depth + '">' +
                '<a class="ei-fold-item' + (isSel ? ' is-sel' : '') + (onPath ? ' is-open' : '') + '"' +
                   ' data-path="' + esc(path.join('/')) + '">' +
                    (hasKids ? '<i class="ti ti-chevron-right ei-fold-chev"></i>'
                             : '<span class="ei-fold-chev"></span>') +
                    '<i class="ti ' + (depth === 3 ? 'ti-file-check' : 'ti-folder') + ' ei-fold-ico"></i>' +
                    '<span class="ei-fold-label">' + esc(labelFor(seg, depth)) + '</span>' +
                    '<span class="ei-fold-count">' + nodes[seg].__n + '</span>' +
                '</a>' +
                (hasKids ? '<div class="ei-fold-panel"><div class="ei-fold-inner">' +
                    (onPath ? confBranchHtml(kids, depth + 1, path) : '') +
                '</div></div>' : '') +
            '</div>';
        }).join('');
    }

    function renderConfTree() {
        var wrap = $('eiConfTree');
        if (state.type !== 'Confirmations') { wrap.innerHTML = ''; wrap.classList.add('d-none'); return; }
        var html = confBranchHtml(confTree(), 0, []);
        wrap.innerHTML = html || '<div class="ei-fold-empty">No confirmations yet.</div>';
        wrap.classList.remove('d-none');
    }

    function visibleDocs() {
        return state.allDocs.filter(function (d) {
            if (state.type !== 'all' && d.doctype !== state.type) return false;
            // Case-insensitive: the filter carries the registry casing ('CGD Amendment')
            // while d.subtype is parsed from the (upper-case) filename.
            if (state.type === 'Transactional' && state.subtype &&
                (d.subtype || '').toUpperCase() !== state.subtype.toUpperCase()) return false;
            // Confirmations are scoped to the folder picked in the rail.
            if (state.type === 'Confirmations' && state.confPath.length) {
                var path = docPath(d);
                for (var i = 0; i < state.confPath.length; i++) {
                    if (path[i] !== state.confPath[i]) return false;
                }
            }
            if (!matchesSearch(d)) return false;
            return true;
        });
    }

    // 'Confirmations › 2026 › 06. June › 18 › NDF' — where the list is coming from.
    function crumbHtml() {
        if (state.type !== 'Confirmations') return '';
        var parts = ['Confirmations'].concat(state.confPath.map(function (s, i) { return labelFor(s, i); }));
        return parts.map(esc).join(' <i class="ti ti-chevron-right ei-crumb-sep"></i> ');
    }

    function docRowHtml(d, idx) {
        var ic = icoFor(d.ext);
        var meta = [d.doctype + (d.subtype ? ' · ' + esc(d.subtype) : ''),
                    d.doc_date ? d.doc_date : d.modified_h, d.size_h].filter(Boolean).join(' &nbsp;·&nbsp; ');
        // Stagger is capped: past ~8 items the delay would read as lag, not polish.
        var delay = Math.min(idx == null ? 0 : idx, 8) * 30;
        return '<div class="ei-doc-row' + (d.rel === state.selectedRel ? ' is-active' : '') + '"' +
                   ' data-rel="' + esc(d.rel) + '" style="animation-delay:' + delay + 'ms">' +
            '<span class="ei-doc-ico ' + ic.cls + '"><i class="ti ' + ic.i + '"></i></span>' +
            '<div class="flex-grow-1 min-w-0">' +
                '<div class="ei-doc-name">' + esc(d.name) + '</div>' +
                '<div class="ei-doc-meta">' + meta + '</div>' +
            '</div>' +
            '<span class="ei-chip">' + esc(d.ext || '') + '</span>' +
        '</div>';
    }

    function renderDocs() {
        var list = $('eiDocList');
        var docs = visibleDocs();
        $('eiDocCount').textContent = docs.length;
        var crumb = $('eiCrumb');
        crumb.innerHTML = crumbHtml();
        crumb.classList.toggle('d-none', state.type !== 'Confirmations');
        if (!docs.length) {
            list.innerHTML = '<div class="ei-empty"><i class="ti ti-folder-off ei-empty-ico"></i>' +
                '<div class="fw-semibold">No documents</div>' +
                '<div class="fs-sm">Nothing here yet for this filter. Use <b>Upload Document</b> to add one.</div></div>';
            return;
        }
        list.innerHTML = docs.map(function (d, i) { return docRowHtml(d, i); }).join('');
    }

    /* ---- preview --------------------------------------------------------- */
    function preview(rel) {
        var d = state.allDocs.filter(function (x) { return x.rel === rel; })[0];
        if (!d) return;
        state.selectedRel = rel;
        document.querySelectorAll('#eiDocList .ei-doc-row').forEach(function (r) {
            r.classList.toggle('is-active', r.dataset.rel === rel);
        });
        $('eiPreviewTitle').textContent = d.name;
        var dl = $('eiPreviewDownload'), op = $('eiPreviewOpen');
        dl.href = fileUrl(rel, true); dl.classList.remove('d-none');
        op.href = fileUrl(rel, false); op.classList.remove('d-none');

        var body = $('eiPreviewBody');
        if (d.previewable) {
            // Loading veil while the PDF streams from the (possibly slow) network
            // share — hidden as soon as the iframe fires 'load'.
            body.innerHTML =
                '<div class="ei-preview-loading" id="eiPvLoad">' +
                    '<div class="ei-spin"></div>' +
                    '<div class="fs-sm">Loading PDF…</div>' +
                    '<div class="fs-xxs text-muted text-truncate px-3" style="max-width:90%">' + esc(d.name) + '</div>' +
                '</div>' +
                '<iframe class="ei-preview-frame" id="eiFrame" title="PDF preview"></iframe>';
            var fr = $('eiFrame');
            if (state.previewTimer) clearTimeout(state.previewTimer);
            fr.addEventListener('load', function () {
                clearTimeout(state.previewTimer);
                fr.classList.add('ready');
                var ld = $('eiPvLoad'); if (ld) ld.remove();
            });
            // Chrome's built-in PDF viewer does not always fire 'load' on the
            // iframe, and the share itself can stall — either way the veil would
            // sit there forever. Give up after a bound and offer a way out.
            state.previewTimer = setTimeout(function () {
                var ld = $('eiPvLoad');
                if (!ld) return;                       // already loaded
                fr.classList.add('ready');             // show whatever did render
                ld.innerHTML =
                    '<i class="ti ti-cloud-off fs-1 text-muted"></i>' +
                    '<div class="fw-semibold">Still loading from the share</div>' +
                    '<div class="fs-sm text-muted px-3 text-center" style="max-width:32ch">' +
                        'The preview is taking longer than usual. Use Download or Open to view the file.' +
                    '</div>' +
                    '<button type="button" class="btn btn-sm btn-light ei-btn" id="eiPvDismiss">Dismiss</button>';
                var btn = $('eiPvDismiss');
                if (btn) btn.addEventListener('click', function () { ld.remove(); });
            }, PREVIEW_TIMEOUT_MS);
            // Set src AFTER wiring the handler so a fast cache hit still clears the veil.
            fr.src = fileUrl(rel, false);
        } else {
            body.innerHTML = '<div class="ei-empty"><i class="ti ti-file-download ei-empty-ico"></i>' +
                '<div class="fw-semibold">No inline preview for .' + esc((d.ext || '').toLowerCase()) + '</div>' +
                '<div class="fs-sm">Use Download or Open to view this file.</div></div>';
        }
    }

    /* ---- upload sub-type (Transactional / Confirmation) ------------------- */
    // One select serves both: Transactional agreements (CGD, Appendix, …) and
    // Confirmations by product (NDF, Option, Swap). SSI has no sub-type.
    function fillSubtypeOptions(doctype) {
        var wrap = $('eiUpSubtypeWrap'), sel = $('eiUpSubtype');
        var list = doctype === 'Confirmations' ? (state.confTypes || [])
                 : doctype === 'Transactional' ? (state.subtypes || [])
                 : [];
        wrap.classList.toggle('d-none', !list.length);
        $('eiUpSubtypeLabel').textContent =
            doctype === 'Confirmations' ? 'Confirmation Type' : 'Transactional Type';
        sel.innerHTML = '<option value="">— Select —</option>' + list.map(function (t) {
            return '<option value="' + esc(t) + '">' + esc(t) + '</option>';
        }).join('');
    }

    /* ---- date field (dd/mm/yyyy) ----------------------------------------- */
    // App-wide standard is jQuery daterangepicker in singleDatePicker mode —
    // never <input type="date"> (inherits the OS locale) and never flatpickr
    // (proved flaky when loaded from the shared bundle). See HANDOFF.

    function todayStr() {
        var t = new Date();
        return ('0' + t.getDate()).slice(-2) + '/' + ('0' + (t.getMonth() + 1)).slice(-2) + '/' + t.getFullYear();
    }

    // Typing mask: keep the digits, re-insert the slashes. Deleting works
    // naturally because a slash is only appended once a digit follows it.
    function maskDate(el) {
        var digits = (el.value.match(/\d/g) || []).join('').slice(0, 8);
        var out = digits.slice(0, 2);
        if (digits.length > 2) out += '/' + digits.slice(2, 4);
        if (digits.length > 4) out += '/' + digits.slice(4, 8);
        el.value = out;
        return digits;
    }

    // Keep the calendar on whatever the user typed, as soon as it is a real date.
    function syncPickerFromInput(el, digits) {
        if (digits.length !== 8 || typeof moment === 'undefined' || !window.jQuery) return;
        var pk = window.jQuery(el).data('daterangepicker');
        if (!pk) return;
        var m = moment(digits, 'DDMMYYYY', true);
        if (!m.isValid()) return;
        pk.setStartDate(m);
        pk.setEndDate(m);
    }

    function resetDate(el) {
        el.value = todayStr();
        syncPickerFromInput(el, el.value.replace(/\D/g, ''));
    }

    // Works for the first block and for every block the "+" adds.
    function attachDatePicker(el, tries) {
        if (!(window.jQuery && window.jQuery.fn && window.jQuery.fn.daterangepicker)) {
            // Plugin not parsed yet — retry briefly instead of degrading permanently.
            if ((tries || 0) < 40) return setTimeout(function () { attachDatePicker(el, (tries || 0) + 1); }, 50);
            return;
        }
        window.jQuery(el).daterangepicker({
            singleDatePicker: true, autoApply: true, showDropdowns: true,
            locale: { format: 'DD/MM/YYYY' }, startDate: moment()
        }, function () { updateNamePreview(); });
        el.addEventListener('input', function () {
            syncPickerFromInput(this, maskDate(this));
            updateNamePreview();
        });
        // Clicking the date selects it whole — typing a new date replaces the old
        // one instead of splicing digits into the middle of it.
        el.addEventListener('focus', function () { this.select(); });
        el.addEventListener('click', function () { this.select(); });
        resetDate(el);
    }

    /* ---- upload ---------------------------------------------------------- */
    function updateNamePreview() {
        var type = $('eiUpType').value;
        var f = $('eiUpFile').files[0];
        var out = $('eiUpNamePreview');
        if (!f) { out.textContent = ''; return; }
        var ext = (f.name.match(/\.[^.]+$/) || [''])[0].toLowerCase();
        var dd = (($('eiUpDate').value || '').match(/\d+/g) || []).join('');
        if (dd.length !== 8) { var t = new Date(); dd = ('0' + t.getDate()).slice(-2) + ('0' + (t.getMonth() + 1)).slice(-2) + t.getFullYear(); }
        var cname = sanitize(state.client || '');
        var st = sanitize($('eiUpSubtype').value).toUpperCase();
        var name;
        if (type === 'Confirmations') {
            name = 'Confirmations/' + dd.slice(4) + '/' + dd.slice(2, 4) + '/' + dd.slice(0, 2) + '/'
                 + (st || 'CONFIRMATION') + ' - ' + cname + ' - ' + dd + ext;
        } else if (type === 'SSI') {
            name = 'SSI/SSI - ' + cname + ' - ' + dd + ext;
        } else {
            name = 'Transactional/' + (st || 'DOC') + ' - ' + cname + ' - ' + dd + ext;
        }
        // The server prefixes an ordinal (2nd, 3rd, …) when a document of the same
        // kind already exists, so this is the first-copy name.
        out.innerHTML = 'Will be saved as: <code>' + esc(name) + '</code>'
            + '<span class="d-block text-muted">Numbered automatically (2nd, 3rd…) if this kind already exists.</span>';
    }

    /* ---- extra document blocks ------------------------------------------
     * A batch usually mixes products and dates (a day's NDF and Option
     * confirmations arrive together), so each block carries its own Type /
     * Sub-type / Date / File rather than sharing one header.
     * ------------------------------------------------------------------- */
    var extraSeq = 0;

    function typeOptionsHtml() {
        return ['Confirmations', 'SSI', 'Transactional'].map(function (t) {
            return '<option value="' + t + '">' + t + '</option>';
        }).join('');
    }

    function addExtraBlock() {
        var id = ++extraSeq;
        var el = document.createElement('div');
        el.className = 'ei-up-block';
        el.dataset.block = id;
        // Same field sizes and layout as the first (fixed) block: full-size
        // controls, Type/Date on md-3 columns, sub-type on md-6, and the tall
        // p-4 dropzone with the large icon.
        el.innerHTML =
            '<div class="ei-up-block-head">' +
                '<span class="ei-up-block-n">Document ' + (id + 1) + '</span>' +
                '<button type="button" class="btn btn-sm btn-danger ei-btn ei-up-del" title="Remove">' +
                    '<i class="ti ti-x"></i></button>' +
            '</div>' +
            '<div class="row g-3">' +
                '<div class="col-md-3">' +
                    '<label class="form-label fw-semibold">Document Type</label>' +
                    '<select class="form-select ei-up-type">' + typeOptionsHtml() + '</select>' +
                '</div>' +
                '<div class="col-md-3">' +
                    '<label class="form-label fw-semibold">Date</label>' +
                    '<input type="text" class="form-control ei-up-date" placeholder="dd/mm/yyyy" autocomplete="off">' +
                '</div>' +
                '<div class="col-md-6 d-none ei-up-sub-wrap">' +
                    '<label class="form-label fw-semibold ei-up-sub-label">Transactional Type</label>' +
                    '<select class="form-select ei-up-sub"></select>' +
                '</div>' +
                '<div class="col-12">' +
                    '<label class="form-label fw-semibold">File</label>' +
                    '<div class="ei-drop ei-up-drop border border-dashed rounded-3 p-4 text-center" style="cursor:pointer;">' +
                        '<button type="button" class="btn btn-sm btn-danger rounded-circle ei-drop-clear d-none ei-up-clear" title="Remove attached file"><i class="ti ti-x"></i></button>' +
                        '<i class="ti ti-file-upload fs-1 text-muted d-block mb-1"></i>' +
                        '<span class="fw-medium ei-up-drop-label">Drop a file here or click to browse</span>' +
                        '<input type="file" class="d-none ei-up-file">' +
                    '</div>' +
                '</div>' +
            '</div>';
        $('eiUpExtra').appendChild(el);

        var typeSel = el.querySelector('.ei-up-type');
        var fill = function () { fillBlockSubtype(el, typeSel.value); };
        typeSel.value = $('eiUpType').value;   // start where the first block is
        fill();
        typeSel.addEventListener('change', fill);

        attachDatePicker(el.querySelector('.ei-up-date'), 0);

        var drop = el.querySelector('.ei-up-drop'), file = el.querySelector('.ei-up-file');
        var clearBtn = el.querySelector('.ei-up-clear');
        drop.addEventListener('click', function () { if (upModalReady) file.click(); });
        file.addEventListener('change', function () {
            el.querySelector('.ei-up-drop-label').textContent =
                this.files[0] ? this.files[0].name : 'Drop a file here or click to browse';
            clearBtn.classList.toggle('d-none', !this.files[0]);
        });
        // X on the dropzone: detach a file picked by mistake without reopening
        // the browse dialog (the click must not bubble to the dropzone).
        clearBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            file.value = '';
            file.dispatchEvent(new Event('change'));
        });
        ['dragenter', 'dragover'].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); this.classList.add('border-primary'); });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            drop.addEventListener(ev, function (e) { e.preventDefault(); this.classList.remove('border-primary'); });
        });
        drop.addEventListener('drop', function (e) {
            if (e.dataTransfer && e.dataTransfer.files[0]) {
                file.files = e.dataTransfer.files;
                file.dispatchEvent(new Event('change'));
            }
        });
        el.querySelector('.ei-up-del').addEventListener('click', function () {
            el.remove(); renumberBlocks();
        });
        el.querySelector('.ei-up-date').focus();
    }

    function fillBlockSubtype(el, doctype) {
        var list = doctype === 'Confirmations' ? (state.confTypes || [])
                 : doctype === 'Transactional' ? (state.subtypes || []) : [];
        el.querySelector('.ei-up-sub-wrap').classList.toggle('d-none', !list.length);
        el.querySelector('.ei-up-sub-label').textContent =
            doctype === 'Confirmations' ? 'Confirmation Type' : 'Transactional Type';
        el.querySelector('.ei-up-sub').innerHTML = '<option value="">— Select —</option>' +
            list.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join('');
    }

    function renumberBlocks() {
        var blocks = $('eiUpExtra').querySelectorAll('.ei-up-block');
        blocks.forEach(function (b, i) { b.querySelector('.ei-up-block-n').textContent = 'Document ' + (i + 2); });
    }

    function clearExtraBlocks() { $('eiUpExtra').innerHTML = ''; extraSeq = 0; }

    // Every block that actually carries a file, first block included.
    function collectUploads() {
        var out = [];
        var f0 = $('eiUpFile').files[0];
        if (f0) {
            out.push({ type: $('eiUpType').value, subtype: $('eiUpSubtype').value,
                       date: $('eiUpDate').value || '', file: f0 });
        }
        $('eiUpExtra').querySelectorAll('.ei-up-block').forEach(function (b) {
            var f = b.querySelector('.ei-up-file').files[0];
            if (!f) return;
            out.push({ type: b.querySelector('.ei-up-type').value,
                       subtype: b.querySelector('.ei-up-sub').value,
                       date: b.querySelector('.ei-up-date').value || '', file: f });
        });
        return out;
    }

    // One request per document, sequentially: the share is slow and parallel
    // writes to it are not faster, and a serial run gives honest progress plus a
    // clean per-file result.
    function uploadOne(item) {
        var fd = new FormData();
        fd.append('client', state.client);
        fd.append('type', item.type);
        fd.append('subtype', item.type === 'SSI' ? '' : item.subtype);
        fd.append('date', item.date);
        fd.append('file', item.file);
        var ctl = window.AbortController ? new AbortController() : null;
        var timedOut = false;
        var timer = setTimeout(function () { timedOut = true; if (ctl) ctl.abort(); }, UPLOAD_TIMEOUT_MS);
        return fetch(API + '/upload', { method: 'POST', body: fd, signal: ctl && ctl.signal })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                clearTimeout(timer);
                return (res && res.success)
                    ? { ok: true, saved: res.saved }
                    : { ok: false, name: item.file.name, why: (res && res.message) || 'rejected' };
            })
            .catch(function (e) {
                clearTimeout(timer);
                console.error('ei upload error', e);
                return { ok: false, name: item.file.name,
                         why: timedOut ? 'the share did not respond in time' : 'network error' };
            });
    }

    function doUpload() {
        if (!state.client) { toast('warning', 'Select a counterparty first'); return; }
        var items = collectUploads();
        if (!items.length) { toast('warning', 'Choose a file to upload'); return; }

        var btn = $('eiUpSubmit'); btn.disabled = true;
        var done = [], failed = [];

        function step(i) {
            if (i >= items.length) return finish();
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving' +
                (items.length > 1 ? ' ' + (i + 1) + ' of ' + items.length : '') + '…';
            return uploadOne(items[i]).then(function (r) {
                (r.ok ? done : failed).push(r);
                return step(i + 1);
            });
        }

        function finish() {
            btn.disabled = false;
            btn.innerHTML = '<i class="ti ti-device-floppy me-1"></i> Save to Inventory';
            if (done.length) {
                bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).hide();
                state.selectedRel = done[done.length - 1].saved ? done[done.length - 1].saved.rel : null;
                loadDocuments();
            }
            if (failed.length && done.length) {
                toast('warning', done.length + ' of ' + items.length + ' saved',
                      'Not saved: ' + failed.map(function (f) { return f.name + ' (' + f.why + ')'; }).join('; '));
            } else if (failed.length) {
                toast('error', 'Upload failed', failed[0].why);
            } else {
                toast('success', items.length > 1 ? items.length + ' documents saved' : 'Document saved',
                      items.length === 1 ? (done[0].saved && done[0].saved.name) : '');
            }
        }

        step(0);
    }

    /* ---- wiring ---------------------------------------------------------- */
    function wire() {
        var input = $('eiClientInput');
        // Clicking into the field selects the whole text, so typing replaces the
        // previous counterparty instead of appending to it.
        input.addEventListener('focus', function () { this.select(); comboLimit = COMBO_PAGE; renderCombo(this.value); });
        input.addEventListener('click', function () { this.select(); });
        input.addEventListener('input', function () { comboKbd = -1; comboLimit = COMBO_PAGE; renderCombo(this.value); });
        input.addEventListener('keydown', function (e) {
            var menu = $('eiClientMenu');
            var items = menu.querySelectorAll('li[data-name]');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                // At the bottom of the rendered slice, load the next page first.
                if (comboKbd + 1 >= items.length && comboLimit < comboFilter(this.value).length) {
                    comboLimit += COMBO_PAGE; renderCombo(this.value);
                    items = menu.querySelectorAll('li[data-name]');
                }
                comboKbd = Math.min(comboKbd + 1, items.length - 1);
                renderCombo(this.value);
            }
            else if (e.key === 'ArrowUp') { e.preventDefault(); comboKbd = Math.max(comboKbd - 1, 0); renderCombo(this.value); }
            else if (e.key === 'Enter') { e.preventDefault(); if (comboKbd >= 0 && items[comboKbd]) selectClient(items[comboKbd].dataset.name); }
            else if (e.key === 'Escape') { closeCombo(); return; }
            var act = menu.querySelector('li.ei-kbd-active');
            if (act) act.scrollIntoView({ block: 'nearest' });
        });
        $('eiClientMenu').addEventListener('scroll', comboMaybeLoadMore);
        $('eiClientMenu').addEventListener('mousedown', function (e) {
            var li = e.target.closest('li[data-name]');
            if (li) { e.preventDefault(); selectClient(li.dataset.name); }
        });
        document.addEventListener('click', function (e) {
            if (!e.target.closest('#eiClientCombo')) closeCombo();
        });

        // doc-type rail
        document.querySelectorAll('#eiTypeList .ei-type-item').forEach(function (a) {
            a.addEventListener('click', function () {
                document.querySelectorAll('#eiTypeList .ei-type-item').forEach(function (x) { x.classList.remove('is-active'); });
                a.classList.add('is-active');
                state.type = a.dataset.type;
                $('eiSubtypeWrap').classList.toggle('d-none', state.type !== 'Transactional');
                if (state.type !== 'Transactional') { state.subtype = ''; $('eiSubtypeFilter').value = ''; }
                // Leaving Confirmations drops the folder selection, so coming
                // back starts at the top instead of a stale deep path.
                if (state.type !== 'Confirmations') state.confPath = [];
                renderConfTree();
                renderDocs();
            });
        });
        $('eiSubtypeFilter').addEventListener('change', function () { state.subtype = this.value; renderDocs(); });
        $('eiDocSearch').addEventListener('input', function () { renderConfTree(); renderDocs(); });

        // Confirmations rail: pick a folder (click the selected one to go up).
        $('eiConfTree').addEventListener('click', function (e) {
            var item = e.target.closest('.ei-fold-item');
            if (!item) return;
            var path = item.dataset.path.split('/');
            var depth = path.length - 1;
            // A node is open when the selected path runs through it — at ANY
            // depth below, not just when it is the exact selection. Clicking an
            // open node collapses it in one click (cutting the path above it)
            // instead of merely trimming one level and leaving it expanded.
            var isOpen = state.confPath.length > depth && state.confPath[depth] === path[depth];
            state.confPath = isOpen ? path.slice(0, depth) : path;
            renderConfTree();
            renderDocs();
        });

        // document click → preview
        $('eiDocList').addEventListener('click', function (e) {
            var row = e.target.closest('.ei-doc-row');
            if (row) preview(row.dataset.rel);
        });

        // upload modal
        // Browse-dialog guard: the dropzones only react AFTER the modal is fully
        // shown. Without this, the second click of a habitual double-click (or a
        // click while the modal is still fading in) lands on the centred dropzone
        // that now covers the Upload button's position, and the OS file picker
        // opens "directly" — which is exactly what some users reported.
        upModalReady = false;
        $('eiUploadModal').addEventListener('shown.bs.modal', function () { upModalReady = true; });
        $('eiUploadModal').addEventListener('hide.bs.modal', function () { upModalReady = false; });
        $('eiUploadBtn').addEventListener('click', function () {
            if (!state.client) { toast('warning', 'Select a counterparty first', 'Choose one on the left, then upload.'); return; }
            $('eiUpClient').value = state.client;
            $('eiUpType').value = state.type !== 'all' ? state.type : 'Confirmations';
            fillSubtypeOptions($('eiUpType').value);   // also resets the sub-type to "— Select —"
            $('eiUpFile').value = ''; $('eiDropLabel').textContent = 'Drop a file here or click to browse';
            $('eiDropClear').classList.add('d-none');
            $('eiUpNamePreview').textContent = '';
            clearExtraBlocks();
            resetDate($('eiUpDate'));
            try {
                bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).show();
            } catch (err) {
                // bootstrap missing/broken (stale cache, unsupported browser):
                // fail loudly instead of leaving a dead button.
                console.error('ei: upload modal failed to open', err);
                toast('error', 'Could not open the upload window',
                      'Refresh the page with Ctrl+F5 and try again.');
            }
        });
        $('eiUpType').addEventListener('change', function () {
            fillSubtypeOptions(this.value);
            updateNamePreview();
        });
        $('eiUpSubtype').addEventListener('change', updateNamePreview);
        $('eiDrop').addEventListener('click', function () { if (upModalReady) $('eiUpFile').click(); });
        $('eiUpFile').addEventListener('change', function () {
            $('eiDropLabel').textContent = this.files[0] ? this.files[0].name : 'Drop a file here or click to browse';
            $('eiDropClear').classList.toggle('d-none', !this.files[0]);
            updateNamePreview();
        });
        $('eiDropClear').addEventListener('click', function (e) {
            e.stopPropagation();                       // don't reopen the browse dialog
            $('eiUpFile').value = '';
            $('eiUpFile').dispatchEvent(new Event('change'));
        });
        ['dragenter', 'dragover'].forEach(function (ev) {
            $('eiDrop').addEventListener(ev, function (e) { e.preventDefault(); this.classList.add('border-primary'); });
        });
        ['dragleave', 'drop'].forEach(function (ev) {
            $('eiDrop').addEventListener(ev, function (e) { e.preventDefault(); this.classList.remove('border-primary'); });
        });
        $('eiDrop').addEventListener('drop', function (e) {
            if (e.dataTransfer && e.dataTransfer.files[0]) {
                $('eiUpFile').files = e.dataTransfer.files;
                $('eiUpFile').dispatchEvent(new Event('change'));
            }
        });
        $('eiUpSubmit').addEventListener('click', doUpload);

        attachDatePicker($('eiUpDate'), 0);
        $('eiUpAdd').addEventListener('click', addExtraBlock);
    }

    document.addEventListener('DOMContentLoaded', function () {
        wire();
        loadClients();
        if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    });
})();

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
    var state = {
        clients: [],          // [{name, spn, on_disk}]
        rootExists: false,
        subtypes: [],         // transactional types from the server
        client: null,         // selected counterparty name
        type: 'all',          // active doc-type rail
        subtype: '',          // transactional sub-type filter
        allDocs: [],          // every document for the current client
        selectedRel: null,
        previewTimer: null    // bounds the "Loading PDF…" veil (see preview())
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
                if (!res || !res.success) { state.allDocs = []; renderDocs(); return; }
                state.allDocs = res.documents || [];
                updateTypeCounts();
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

    function visibleDocs() {
        var q = ($('eiDocSearch').value || '').trim().toLowerCase();
        return state.allDocs.filter(function (d) {
            if (state.type !== 'all' && d.doctype !== state.type) return false;
            // Case-insensitive: the filter carries the registry casing ('CGD Amendment')
            // while d.subtype is parsed from the (upper-case) filename.
            if (state.type === 'Transactional' && state.subtype &&
                (d.subtype || '').toUpperCase() !== state.subtype.toUpperCase()) return false;
            if (q && d.name.toLowerCase().indexOf(q) < 0 && (d.subtype || '').toLowerCase().indexOf(q) < 0) return false;
            return true;
        });
    }

    function renderDocs() {
        var list = $('eiDocList');
        var docs = visibleDocs();
        $('eiDocCount').textContent = docs.length;
        if (!docs.length) {
            list.innerHTML = '<div class="ei-empty"><i class="ti ti-folder-off ei-empty-ico"></i>' +
                '<div class="fw-semibold">No documents</div>' +
                '<div class="fs-sm">Nothing here yet for this filter. Use <b>Upload Document</b> to add one.</div></div>';
            return;
        }
        list.innerHTML = docs.map(function (d) {
            var ic = icoFor(d.ext);
            var meta = [d.doctype + (d.subtype ? ' · ' + esc(d.subtype) : ''),
                        d.doc_date ? d.doc_date : d.modified_h, d.size_h].filter(Boolean).join(' &nbsp;·&nbsp; ');
            return '<div class="ei-doc-row' + (d.rel === state.selectedRel ? ' is-active' : '') + '" data-rel="' + esc(d.rel) + '">' +
                '<span class="ei-doc-ico ' + ic.cls + '"><i class="ti ' + ic.i + '"></i></span>' +
                '<div class="flex-grow-1 min-w-0">' +
                    '<div class="ei-doc-name">' + esc(d.name) + '</div>' +
                    '<div class="ei-doc-meta">' + meta + '</div>' +
                '</div>' +
                '<span class="ei-chip">' + esc(d.ext || '') + '</span>' +
            '</div>';
        }).join('');
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
    var upPicker = null;

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
    function syncPickerFromInput(digits) {
        if (!upPicker || digits.length !== 8 || typeof moment === 'undefined') return;
        var m = moment(digits, 'DDMMYYYY', true);
        if (!m.isValid()) return;
        upPicker.setStartDate(m);
        upPicker.setEndDate(m);
    }

    // Reset to today — the modal must never reopen showing the previous upload's date.
    function resetUpDate() {
        var el = $('eiUpDate');
        el.value = todayStr();
        syncPickerFromInput(el.value.replace(/\D/g, ''));
    }

    function initDatePicker(tries) {
        if (!(window.jQuery && window.jQuery.fn && window.jQuery.fn.daterangepicker)) {
            // Plugin not parsed yet — retry briefly instead of degrading permanently.
            if ((tries || 0) < 40) return setTimeout(function () { initDatePicker((tries || 0) + 1); }, 50);
            return;
        }
        var $el = window.jQuery('#eiUpDate');
        $el.daterangepicker({
            singleDatePicker: true, autoApply: true, showDropdowns: true,
            locale: { format: 'DD/MM/YYYY' }, startDate: moment()
        }, function () { updateNamePreview(); });
        upPicker = $el.data('daterangepicker');
        resetUpDate();
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

    function doUpload() {
        if (!state.client) { toast('warning', 'Select a counterparty first'); return; }
        var f = $('eiUpFile').files[0];
        if (!f) { toast('warning', 'Choose a file to upload'); return; }
        var type = $('eiUpType').value;
        var fd = new FormData();
        fd.append('client', state.client);
        fd.append('type', type);
        fd.append('subtype', type === 'SSI' ? '' : $('eiUpSubtype').value);
        fd.append('date', $('eiUpDate').value || '');
        fd.append('file', f);
        var btn = $('eiUpSubmit'); btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving…';
        // The I: share can stall indefinitely. Bound the wait so the button always
        // comes back instead of spinning forever with no way out.
        var ctl = window.AbortController ? new AbortController() : null;
        var timedOut = false;
        var timer = setTimeout(function () {
            timedOut = true;
            if (ctl) ctl.abort();
        }, UPLOAD_TIMEOUT_MS);
        fetch(API + '/upload', { method: 'POST', body: fd, signal: ctl && ctl.signal })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                clearTimeout(timer);
                btn.disabled = false;
                btn.innerHTML = '<i class="ti ti-device-floppy me-1"></i> Save to Inventory';
                if (!res || !res.success) { toast('error', 'Upload failed', res && res.message); return; }
                bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).hide();
                toast('success', 'Document saved', res.saved && res.saved.name);
                state.selectedRel = res.saved ? res.saved.rel : null;
                loadDocuments();
            })
            .catch(function (e) {
                clearTimeout(timer);
                btn.disabled = false;
                btn.innerHTML = '<i class="ti ti-device-floppy me-1"></i> Save to Inventory';
                console.error('ei upload error', e);
                toast('error', 'Upload failed', timedOut
                    ? 'The share did not respond in time. The file may still have been saved — refresh the list before retrying.'
                    : 'Network error.');
            });
    }

    /* ---- wiring ---------------------------------------------------------- */
    function wire() {
        var input = $('eiClientInput');
        input.addEventListener('focus', function () { comboLimit = COMBO_PAGE; renderCombo(this.value); });
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
                renderDocs();
            });
        });
        $('eiSubtypeFilter').addEventListener('change', function () { state.subtype = this.value; renderDocs(); });
        $('eiDocSearch').addEventListener('input', renderDocs);

        // document click → preview
        $('eiDocList').addEventListener('click', function (e) {
            var row = e.target.closest('.ei-doc-row');
            if (row) preview(row.dataset.rel);
        });

        // upload modal
        $('eiUploadBtn').addEventListener('click', function () {
            if (!state.client) { toast('warning', 'Select a counterparty first', 'Choose one on the left, then upload.'); return; }
            $('eiUpClient').value = state.client;
            $('eiUpType').value = state.type !== 'all' ? state.type : 'Confirmations';
            fillSubtypeOptions($('eiUpType').value);   // also resets the sub-type to "— Select —"
            $('eiUpFile').value = ''; $('eiDropLabel').textContent = 'Drop a file here or click to browse';
            $('eiUpNamePreview').textContent = '';
            resetUpDate();
            bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).show();
        });
        $('eiUpType').addEventListener('change', function () {
            fillSubtypeOptions(this.value);
            updateNamePreview();
        });
        $('eiUpSubtype').addEventListener('change', updateNamePreview);
        $('eiUpDate').addEventListener('input', function () {
            syncPickerFromInput(maskDate(this));
            updateNamePreview();
        });
        $('eiDrop').addEventListener('click', function () { $('eiUpFile').click(); });
        $('eiUpFile').addEventListener('change', function () {
            $('eiDropLabel').textContent = this.files[0] ? this.files[0].name : 'Drop a file here or click to browse';
            updateNamePreview();
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

        initDatePicker(0);
    }

    document.addEventListener('DOMContentLoaded', function () {
        wire();
        loadClients();
        if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    });
})();

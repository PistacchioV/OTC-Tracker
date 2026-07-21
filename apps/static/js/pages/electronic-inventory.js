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
    var state = {
        clients: [],          // [{name, spn, on_disk}]
        rootExists: false,
        subtypes: [],         // transactional types from the server
        client: null,         // selected counterparty name
        type: 'all',          // active doc-type rail
        subtype: '',          // transactional sub-type filter
        allDocs: [],          // every document for the current client
        selectedRel: null
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
        } else if (icon === 'error') {
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
            // seed the transactional sub-type selects (once)
            if (!eiSubtypesSeeded && state.subtypes.length) {
                eiSubtypesSeeded = true;
                var opts = state.subtypes.map(function (t) { return '<option value="' + esc(t) + '">' + esc(t) + '</option>'; }).join('');
                $('eiUpSubtype').insertAdjacentHTML('beforeend', opts);
                $('eiSubtypeFilter').insertAdjacentHTML('beforeend', opts);
            }
        }).catch(function (e) {
            console.error('ei clients error', e);
            $('eiShareDot').className = 'ei-status-dot off';
            if (lbl0) lbl0.textContent = 'Could not load counterparties';
        });
    }

    /* ---- searchable counterparty combo ---------------------------------- */
    var comboKbd = -1;
    function renderCombo(q) {
        var menu = $('eiClientMenu');
        q = (q || '').trim().toLowerCase();
        var list = state.clients.filter(function (c) {
            return !q || c.name.toLowerCase().indexOf(q) >= 0 || (c.spn && c.spn.indexOf(q) >= 0);
        }).slice(0, 60);
        if (!list.length) {
            menu.innerHTML = '<li class="text-muted" style="cursor:default">No match</li>';
        } else {
            menu.innerHTML = list.map(function (c, i) {
                return '<li data-name="' + esc(c.name) + '"' + (i === comboKbd ? ' class="ei-kbd-active"' : '') + '>' +
                    '<span>' + esc(c.name) + '</span>' +
                    (c.on_disk === false ? '<span class="ei-nofolder">no folder</span>' : '') +
                    (c.spn ? '<span class="ei-combo-spn">SPN ' + esc(c.spn) + '</span>' : '') +
                    '</li>';
            }).join('');
        }
        menu.classList.add('show');
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
            if (state.type === 'Transactional' && state.subtype && d.subtype !== state.subtype) return false;
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
            fr.addEventListener('load', function () {
                fr.classList.add('ready');
                var ld = $('eiPvLoad'); if (ld) ld.remove();
            });
            // Set src AFTER wiring the handler so a fast cache hit still clears the veil.
            fr.src = fileUrl(rel, false);
        } else {
            body.innerHTML = '<div class="ei-empty"><i class="ti ti-file-download ei-empty-ico"></i>' +
                '<div class="fw-semibold">No inline preview for .' + esc((d.ext || '').toLowerCase()) + '</div>' +
                '<div class="fs-sm">Use Download or Open to view this file.</div></div>';
        }
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
        var name;
        if (type === 'Confirmations') {
            name = 'Confirmations/' + dd.slice(4) + '/' + dd.slice(2, 4) + '/' + dd.slice(0, 2) + '/' + f.name;
        } else if (type === 'SSI') {
            name = 'SSI/SSI - ' + cname + ' - ' + dd + ext;
        } else {
            var st = sanitize($('eiUpSubtype').value).toUpperCase() || 'DOC';
            name = 'Transactional/' + st + ' - ' + cname + ' - ' + dd + ext;
        }
        out.innerHTML = 'Will be saved as: <code>' + esc(name) + '</code>';
    }

    function doUpload() {
        if (!state.client) { toast('warning', 'Select a counterparty first'); return; }
        var f = $('eiUpFile').files[0];
        if (!f) { toast('warning', 'Choose a file to upload'); return; }
        var type = $('eiUpType').value;
        var fd = new FormData();
        fd.append('client', state.client);
        fd.append('type', type);
        fd.append('subtype', type === 'Transactional' ? $('eiUpSubtype').value : '');
        fd.append('date', $('eiUpDate').value || '');
        fd.append('file', f);
        var btn = $('eiUpSubmit'); btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving…';
        fetch(API + '/upload', { method: 'POST', body: fd })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                btn.disabled = false;
                btn.innerHTML = '<i class="ti ti-device-floppy me-1"></i> Save to Inventory';
                if (!res || !res.success) { toast('error', 'Upload failed', res && res.message); return; }
                bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).hide();
                toast('success', 'Document saved', res.saved && res.saved.name);
                state.selectedRel = res.saved ? res.saved.rel : null;
                loadDocuments();
            })
            .catch(function (e) {
                btn.disabled = false;
                btn.innerHTML = '<i class="ti ti-device-floppy me-1"></i> Save to Inventory';
                console.error('ei upload error', e); toast('error', 'Upload failed', 'Network error.');
            });
    }

    /* ---- wiring ---------------------------------------------------------- */
    function wire() {
        var input = $('eiClientInput');
        input.addEventListener('focus', function () { renderCombo(this.value); });
        input.addEventListener('input', function () { comboKbd = -1; renderCombo(this.value); });
        input.addEventListener('keydown', function (e) {
            var items = $('eiClientMenu').querySelectorAll('li[data-name]');
            if (e.key === 'ArrowDown') { e.preventDefault(); comboKbd = Math.min(comboKbd + 1, items.length - 1); renderCombo(this.value); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); comboKbd = Math.max(comboKbd - 1, 0); renderCombo(this.value); }
            else if (e.key === 'Enter') { e.preventDefault(); if (comboKbd >= 0 && items[comboKbd]) selectClient(items[comboKbd].dataset.name); }
            else if (e.key === 'Escape') { closeCombo(); }
        });
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
            $('eiUpType').dispatchEvent(new Event('change'));
            $('eiUpFile').value = ''; $('eiDropLabel').textContent = 'Drop a file here or click to browse';
            $('eiUpNamePreview').textContent = '';
            bootstrap.Modal.getOrCreateInstance($('eiUploadModal')).show();
        });
        $('eiUpType').addEventListener('change', function () {
            $('eiUpSubtypeWrap').classList.toggle('d-none', this.value !== 'Transactional');
            updateNamePreview();
        });
        $('eiUpSubtype').addEventListener('change', updateNamePreview);
        $('eiUpDate').addEventListener('input', updateNamePreview);
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

        // date picker (BR format) if flatpickr is present
        if (typeof flatpickr !== 'undefined') {
            flatpickr($('eiUpDate'), { dateFormat: 'd/m/Y', allowInput: true, disableMobile: true,
                onChange: updateNamePreview });
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        wire();
        loadClients();
        if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    });
})();

/* ============================================================================
 * Missing Counterparty badge — shared helper for New Deals pages
 * ----------------------------------------------------------------------------
 * Mirrors the "Missing Index B3" pattern, but for counterparties that are not
 * registered in RefData.json. A deal's counterparty is considered registered
 * when its SPN (leading-zeros stripped) OR its Accronym (Commodities / FX Cash)
 * matches a RefData record. When it does not, a red rounded-pill badge
 * "Missing Counterparty" is stamped onto the Status cell and every column that
 * pulls counterparty info (SPN / Client / Tax ID / Accronym — whichever are the
 * enriched columns for the page).
 *
 * The badge work is DOM-only (it never touches DataTables `cell.data()`), so it
 * coexists cleanly with the Missing Index B3 mechanism (which DOES swap the
 * Status cell data). Always invoke refreshAll() AFTER the B3 refresh. In the
 * Status cell the CP badge shows ALONE: whatever badge is there (status/B3)
 * is hidden while the counterparty is missing and restored when registered.
 *
 * Usage (inside the page script, after the DataTable is built):
 *   var inst = MissingCounterparty.init({
 *     table:      table,                         // DataTables API instance
 *     getRefData: function () { return _REFDATA; },
 *     setRefData: function (d) { _REFDATA = d; },
 *     cols:       { status:2, spn:8, acr:9, client:10, taxid:11, info:[8,10,11] },
 *     acrField:   'COMMODITIES ACCRONYM',        // field used to enrich Accronym
 *     t:          (typeof t === 'function' ? t : null)
 *   });
 *   window._cpInst = inst;
 * Then call window._cpInst.refreshAll() in drawCallback (after B3) and after the
 * data load; and gate the edit/approve handlers with rowMissing()/promptRegister().
 * ========================================================================== */
window.MissingCounterparty = (function () {
    'use strict';

    function normSpn(s) {
        s = String(s == null ? '' : s).trim();
        if (s.slice(-2) === '.0') s = s.slice(0, -2);
        s = s.replace(/^0+/, '');
        return s;
    }
    function strip(v) { return String(v == null ? '' : v).replace(/<[^>]+>/g, '').trim(); }

    function Inst(cfg) {
        this.cfg   = cfg || {};
        this.spnSet = {};
        this.acrSet = {};
        this.built  = false;
    }

    Inst.prototype.t = function (k, d) {
        var f = this.cfg.t;
        return (typeof f === 'function') ? f(k, d) : d;
    };

    Inst.prototype.badgeHtml = function () {
        return '<span class="badge rounded-pill bg-danger missing-cp-badge" ' +
               'style="font-size:0.74em;vertical-align:middle">' +
               this.t('badge-missing-cp', 'Missing Counterparty') + '</span>';
    };

    Inst.prototype.buildSets = function () {
        this.spnSet = {};
        this.acrSet = {};
        var rd = (this.cfg.getRefData && this.cfg.getRefData()) || [];
        for (var i = 0; i < rd.length; i++) {
            var r  = rd[i];
            var sp = normSpn(r['SPN']);                          if (sp) this.spnSet[sp] = true;
            var ca = String(r['COMMODITIES ACCRONYM'] || '').trim(); if (ca) this.acrSet[ca] = true;
            var fa = String(r['FX CASH ACCRONYM'] || '').trim();     if (fa) this.acrSet[fa] = true;
        }
        this.built = true;
    };

    Inst.prototype.rowVals = function (rd) {
        var c = this.cfg.cols;
        return { spn: strip(rd[c.spn]), acr: strip(rd[c.acr]) };
    };

    Inst.prototype.isMissing = function (spn, acr) {
        var rd = (this.cfg.getRefData && this.cfg.getRefData()) || [];
        if (!rd.length) return false;            // RefData not loaded yet → never flag
        if (!this.built) this.buildSets();
        var sp = normSpn(spn), ac = String(acr || '').trim();
        if (!sp && !ac) return false;            // no counterparty identifier on the row
        if (sp && this.spnSet[sp]) return false;
        if (ac && this.acrSet[ac]) return false;
        return true;
    };

    Inst.prototype.rowMissing = function (tr) {
        var t = this.cfg.table;
        if (!t || !tr) return false;
        var rd = t.row(tr).data();
        if (!rd) return false;
        var v = this.rowVals(rd);
        return this.isMissing(v.spn, v.acr);
    };

    Inst.prototype.refreshRow = function (tr) {
        var $ = window.jQuery, t = this.cfg.table, c = this.cfg.cols;
        var rd = t.row(tr).data();
        if (!rd) return;
        var v       = this.rowVals(rd);
        var missing = this.isMissing(v.spn, v.acr);
        var badge   = this.badgeHtml();

        // Status cell — when missing, the CP badge REPLACES the whole cell
        // content (stashed on the node for restore). Replacing beats hiding
        // children: hide() misses text nodes / unexpected markup, which left
        // "New" + badge side by side on some pages. Cell DATA stays untouched,
        // so a draw re-renders the original status and this runs again.
        var stNode = t.cell(tr, c.status).node();
        if (stNode) {
            var $st = $(stNode);
            if (!$st.find('.row-edit-field').length) {
                var hasBadge = $st.find('.missing-cp-badge').length > 0;
                if (missing && !hasBadge) {
                    $st.data('cpOrig', $st.html());
                    $st.html(badge);
                } else if (!missing && hasBadge) {
                    var orig = $st.data('cpOrig');
                    if (orig != null) $st.html(orig);
                    else $st.find('.missing-cp-badge').remove();
                    $st.removeData('cpOrig');
                }
            }
        }

        // Enriched counterparty columns — these are empty when the CP is missing.
        for (var k = 0; k < c.info.length; k++) {
            var node = t.cell(tr, c.info[k]).node();
            if (!node) continue;
            var $cell = $(node);
            $cell.find('.missing-cp-badge').remove();
            if ($cell.find('.row-edit-field, .dt-ac-wrap').length) continue;   // mid-edit
            if (missing) {
                if (!$cell.text().trim()) $cell.html(badge);
                else                      $cell.append(' ' + badge);
            }
        }

        if (missing) $(tr).attr('data-missing-cp', '1');
        else         $(tr).removeAttr('data-missing-cp');
    };

    Inst.prototype.refreshAll = function () {
        var t = this.cfg.table;
        if (!t) return;
        var rd = (this.cfg.getRefData && this.cfg.getRefData()) || [];
        if (!rd.length) return;
        if (!this.built) this.buildSets();
        var self = this;
        t.rows({ page: 'current' }).every(function () {
            var tr = this.node();
            if (tr) self.refreshRow(tr);
        });
    };

    // Reload RefData.json, re-enrich every row's counterparty columns from the
    // freshly registered records, then refresh the badges.
    Inst.prototype.reloadAndEnrich = function (cb) {
        var self = this, cfg = this.cfg, t = cfg.table;
        fetch(cfg.refDataUrl || '/static/data/RefData.json')
            .then(function (r) { return r.json(); })
            .then(function (d) {
                if (cfg.setRefData) cfg.setRefData(d);
                self.buildSets();
                var c = cfg.cols;
                t.rows({ search: 'none', page: 'all' }).every(function () {
                    var rowd = this.data();
                    if (!rowd) return;
                    var idx = this.index();
                    var v   = self.rowVals(rowd);
                    var rec = null;
                    for (var i = 0; i < d.length; i++) {
                        var r = d[i];
                        if (v.spn && normSpn(r['SPN']) === normSpn(v.spn)) { rec = r; break; }
                        if (v.acr && (String(r['COMMODITIES ACCRONYM'] || '').trim() === v.acr ||
                                      String(r['FX CASH ACCRONYM'] || '').trim()     === v.acr)) { rec = r; break; }
                    }
                    if (!rec) return;
                    if (c.info.indexOf(c.spn) >= 0) t.cell(idx, c.spn).data(rec['SPN'] || '');
                    t.cell(idx, c.client).data(rec['COUNTERPARTY'] || '');
                    t.cell(idx, c.taxid).data(rec['TAX ID'] || '');
                    if (c.info.indexOf(c.acr) >= 0) t.cell(idx, c.acr).data(rec[cfg.acrField] || '');
                });
                t.draw(false);
                self.refreshAll();
                if (cb) cb();
            })
            .catch(function (e) { if (window.console) console.warn('CP reload failed:', e); });
    };

    Inst.prototype.promptRegister = function () {
        var self = this, S = window.Swal;
        if (!S) { self.reloadAndEnrich(); return; }
        S.fire({
            title:            self.t('swal-missing-cp-title', 'Counterparty Not Registered'),
            html:             self.t('swal-missing-cp-html', 'This counterparty is not registered in Reference Data. Please register it, then reload.'),
            icon:             'warning',
            showConfirmButton: true,
            confirmButtonText: self.t('swal-reload-data', 'Reload Data'),
            showDenyButton:    true,
            denyButtonText:    self.t('swal-goto-refdata', 'Go to Reference Data'),
            showCancelButton:  true,
            cancelButtonText:  self.t('swal-cancel', 'Cancel'),
            confirmButtonColor: '#6c757d',
            denyButtonColor:    '#3abff8',
            cancelButtonColor:  '#dc3545'
        }).then(function (res) {
            if (res.isConfirmed)   self.reloadAndEnrich();
            else if (res.isDenied) window.location.href = '/reference-data';
        });
    };

    return {
        init: function (cfg) { return new Inst(cfg); }
    };
})();

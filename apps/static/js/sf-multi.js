/* ──────────────────────────────────────────────────────────────────────────
 * sf-multi.js — filter with SEVERAL values (a list of Trade IDs)
 *
 * The smart filter and the per-column filter row accept `123, 456; 789`: the
 * row passes when ANY of the values matches. Separators are `,`, `;`, tab and
 * line break. A column of IDs pasted from Excel arrives with line breaks, and
 * an <input type="text"> DROPS them on paste (the IDs would be glued into one),
 * so the paste handler below rewrites them as `; ` first.
 *
 * The New Deals pages filter on the server: there the same rule lives in
 * `platform/new_deals._filter_tokens` (used by `_deal_matches`). This file
 * covers what is filtered in the browser (Intrag, DCE, Unwinds and the column
 * filter row of every page that loads it).
 *
 *   otcSfMulti.tokens(value[, isNumber]) → ['123', '456']
 *   otcSfMulti.isMulti(value[, isNumber]) → true when more than one value
 *   otcSfMulti.columnSearch(dtColumn, value[, isNumber]) → true when the
 *       column search changed (the caller draws)
 * ────────────────────────────────────────────────────────────────────────── */
(function (w) {
    'use strict';
    if (w.otcSfMulti) return;

    var SEP = /[,;\t\r\n]+/;
    var SEP_NUMBER = /[;\t\r\n]+/;            // `,` is the thousands separator
    // "1,250,000.50" is ONE number, not three values
    var THOUSANDS = /^-?\d{1,3}(,\d{3})+(\.\d+)?$/;

    function tokens(value, isNumber) {
        var s = String(value == null ? '' : value).trim();
        if (!s) return [];
        var sep = (isNumber || THOUSANDS.test(s)) ? SEP_NUMBER : SEP;
        var out = s.split(sep).map(function (t) { return t.trim(); })
                   .filter(function (t) { return t; });
        return out.length ? out : [s];
    }

    function isMulti(value, isNumber) {
        return tokens(value, isNumber).length > 1;
    }

    function escRe(s) {
        return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // Applies `value` to a DataTables column: several values → case-insensitive
    // regex OR (no smart search: the smart search would AND the words); one
    // value → the DataTables default, as before.
    function columnSearch(col, value, isNumber) {
        var t = tokens(value, isNumber);
        var want, regex;
        if (t.length > 1) {
            want = t.map(escRe).join('|');
            regex = true;
        } else {
            want = String(value == null ? '' : value);
            regex = false;
        }
        if (col.search() === want) return false;
        if (regex) col.search(want, true, false, true);
        else col.search(want);
        return true;
    }

    // Paste of an Excel column: line breaks/tabs → `; ` before the input eats them
    document.addEventListener('paste', function (e) {
        var el = e.target;
        if (!el || el.tagName !== 'INPUT' || !el.matches) return;
        // the filter row: `.column-search-input-bar` or, in the Intrag pages,
        // a plain text input in the <thead> (DataTables clones it under scrollX)
        if (!el.matches('.smart-filter-input, thead input[type="text"], thead input:not([type])')) return;
        var cb = e.clipboardData || w.clipboardData;
        var txt = cb ? cb.getData('text') : '';
        if (!/[\t\r\n]/.test(txt)) return;
        var joined = txt.split(/[\t\r\n]+/).map(function (t) { return t.trim(); })
                        .filter(function (t) { return t; }).join('; ');
        e.preventDefault();
        var a = el.selectionStart == null ? el.value.length : el.selectionStart;
        var b = el.selectionEnd == null ? el.value.length : el.selectionEnd;
        el.value = el.value.slice(0, a) + joined + el.value.slice(b);
        var pos = a + joined.length;
        try { el.setSelectionRange(pos, pos); } catch (err) { /* not focusable */ }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('keyup', { bubbles: true }));
    }, true);

    w.otcSfMulti = { tokens: tokens, isMulti: isMulti, columnSearch: columnSearch };
})(window);

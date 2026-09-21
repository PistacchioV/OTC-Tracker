/* file-preview.js — o preview de arquivo da casa (o modelo nasceu no New
   Deals › Swap › Bullet, §480): UMA aba por arquivo/visão, a tabela
   Bloco · Campo · Formato · Valor (com o badge da origem do cadastro do File
   Interpreter) e, embaixo, o ARQUIVO CRU — header + registros — como vai
   para a B3/Intrag. Toda página que mostra o arquivo que vai gerar chama
   `otcFilePreview(...)`; o que muda de uma para outra é só de onde vêm os
   campos (servidor, ou o gerador do navegador) e os botões do rodapé.

   otcFilePreview({
       title, subtitle,            // texto (escapado aqui); subtitle aceita HTML em `subtitleHtml`
       width,                      // default 1000
       banner,                     // HTML acima das abas (calendário, espelho…)
       files: [{
           label,                  // rótulo da aba ('SWAP 0301 · JPM x CLI')
           file_name,              // nome do arquivo gerado
           fields: [{ seq, block, field|name, format, source, value }],
           blockFields,            // opcional: campos do template (mesma ordem) para
                                   //   completar seq/format/source/block dos `fields`
           blockTitle,             // opcional: título do bloco quando blockFields não traz
           spec: { file_type, separator },   // para montar o registro a partir dos campos
           header,                 // linha 0 (opcional)
           records,                // linhas do arquivo; sem elas, UMA montada dos campos
           extraHtml               // HTML depois da tabela (linhas tipo 2, etc.)
       }],
       buttons: { download: true|false, edit: true|false, send: true|false },
       rawFrom: { url, body },     // opcional: o endpoint de DOWNLOAD da página
                                   //   (`download: true`, não grava). O arquivo cru
                                   //   da aba passa a ser o que o SERVIDOR gera —
                                   //   o registro montado dos campos é o de TELA
                                   //   (Valor Base em #,##0.00) e não traz as
                                   //   linhas tipo 2 (datas da asiática).
       t                           // função de tradução (key, fallback) — opcional
   }) → a Promise do Swal (result.isConfirmed = download/send · result.isDenied = edit) */
(function () {
    'use strict';

    function esc(s) {
        return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }
    function tr(t, key, fb) {
        try { if (typeof t === 'function') { var v = t(key, fb); if (v) return v; } } catch (e) {}
        try {
            var lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en';
            var d = window.__OTC_TRANSLATIONS__ && window.__OTC_TRANSLATIONS__[lang];
            if (d && d[key]) return d[key];
        } catch (e2) {}
        return fb;
    }
    function seqKey(s) { s = String(s == null ? '' : s).trim(); return /^\d+$/.test(s) ? String(parseInt(s, 10)) : s; }

    /* Completa cada campo com o que o template sabe (seq, formato, origem,
       bloco): pelo seq quando os dois lados o têm, senão pela POSIÇÃO — os
       geradores do navegador devolvem a lista na ordem do bloco. */
    function enrich(fields, blockFields, blockTitle) {
        var bf = blockFields || [];
        var bySeq = {};
        bf.forEach(function (f) { if (f && f.seq != null) bySeq[seqKey(f.seq)] = f; });
        return (fields || []).map(function (f, i) {
            var o = {
                seq: f.seq, block: f.block || '', field: f.field || f.name || '',
                format: f.format || '', source: f.source || '', value: f.value == null ? '' : String(f.value)
            };
            var t = (o.seq != null && bySeq[seqKey(o.seq)]) || bf[i] || null;
            if (t) {
                if (o.seq == null) o.seq = t.seq;
                if (!o.format) o.format = t.format || '';
                if (!o.source) o.source = t.source || '';
                if (!o.field) o.field = t.field || '';
            }
            if (!o.block && blockTitle) o.block = blockTitle;
            if (o.seq == null) o.seq = i + 1;
            return o;
        });
    }

    /* O registro a partir dos campos: posicional concatena, delimitado junta
       pelo separador e fecha com token vazio — as duas regras do motor. */
    function lineOf(fields, spec) {
        var vals = fields.map(function (f) { return f.value == null ? '' : String(f.value); });
        if (spec && spec.file_type === 'delimited') {
            var sep = spec.separator || ';';
            return vals.join(sep) + sep;
        }
        return vals.join('');
    }

    function fieldsTable(fields, t) {
        var hasBlock = fields.some(function (f) { return f.block; });
        var hasFmt = fields.some(function (f) { return f.format; });
        var rows = fields.map(function (x, j) {
            var bg = j % 2 === 0 ? 'rgba(0,0,0,.03)' : 'transparent';
            var src = x.source ? '<span class="badge text-bg-light border ms-1" style="font-size:9px">' + esc(x.source) + '</span>' : '';
            var v = String(x.value == null ? '' : x.value);
            var disp = (v !== '' && v.trim() === '')
                ? '<span style="color:#bbb">' + '·'.repeat(Math.min(v.length, 60)) + '</span>'   // padding todo em branco
                : (v.trim() !== '' ? esc(v) : '<span style="color:#aaa">&mdash;</span>');
            return '<tr style="background:' + bg + '">' +
                (hasBlock ? '<td style="padding:2px 8px;white-space:nowrap;border:none;font-size:.78em;color:#888">' + esc(x.block) + '</td>' : '') +
                '<td style="padding:2px 8px;white-space:nowrap;font-weight:500;border:none;font-size:0.8em">' + esc(x.seq) + '. ' + esc(x.field) + src + '</td>' +
                (hasFmt ? '<td style="padding:2px 8px;border:none;font-size:.75em;color:#888;white-space:nowrap">' + esc(x.format) + '</td>' : '') +
                '<td style="padding:2px 8px;font-family:monospace;font-size:0.8em;border:none;word-break:break-all;text-align:left;white-space:pre-wrap">' + disp + '</td></tr>';
        }).join('');
        var th = function (txt) { return '<th style="padding:5px 8px;text-align:left;font-weight:600">' + txt + '</th>'; };
        return '<div style="overflow-y:auto;max-height:42vh;border:1px solid rgba(0,0,0,.12);border-radius:6px">' +
            '<table style="width:100%;border-collapse:collapse;font-size:0.85em"><thead><tr style="background:#343a40;color:#fff;position:sticky;top:0">' +
            (hasBlock ? th(esc(tr(t, 'nd-preview-col-block', 'Block'))) : '') +
            th('<span data-lang="nd-preview-col-field">' + esc(tr(t, 'nd-preview-col-field', 'Field')) + '</span>') +
            (hasFmt ? th(esc(tr(t, 'nd-preview-col-format', 'Format'))) : '') +
            th('<span data-lang="nd-preview-col-value">' + esc(tr(t, 'nd-preview-col-value', 'Value')) + '</span>') +
            '</tr></thead><tbody>' + rows + '</tbody></table></div>';
    }

    function paneOf(f, i, t, single) {
        var fields = enrich(f.fields, f.blockFields, f.blockTitle);
        var records = f.records && f.records.length ? f.records : (fields.length ? [lineOf(fields, f.spec)] : []);
        var raw = (f.header ? [f.header] : []).concat(records).join('\n');
        var html = '<div class="tab-pane' + (i === 0 ? ' show active' : '') + '" id="otcPv' + i + '">';
        if (f.file_name) html += '<div class="text-start fs-xs text-muted my-2"><b>' + esc(f.file_name) + '</b>' +
            (records.length > 1 ? ' <span class="text-muted">· ' + records.length + ' ' + esc(tr(t, 'nd-preview-records', 'record(s)')) + '</span>' : '') + '</div>';
        if (f.bannerHtml) html += f.bannerHtml;
        if (fields.length) html += fieldsTable(fields, t);
        if (f.extraHtml) html += f.extraHtml;
        if (raw) html += '<div class="text-start fs-xs text-muted mt-2">' + esc(tr(t, 'nd-swb-file-raw', 'Raw file')) + '</div>' +
            '<div class="otc-preview-line">' + esc(raw) + '</div>';
        html += '</div>';
        return html;
    }

    function ensureCss() {
        if (document.getElementById('otc-file-preview-css')) return;
        var st = document.createElement('style');
        st.id = 'otc-file-preview-css';
        st.textContent =
            '.otc-preview-line{font-family:monospace;font-size:.74rem;white-space:pre;overflow-x:auto;background:rgba(0,0,0,.04);border-radius:8px;padding:8px 10px;text-align:left}' +
            '[data-bs-theme=dark] .otc-preview-line{background:rgba(255,255,255,.06)}' +
            '.otc-preview-tabs .nav-link{font-size:.78rem;padding:.3rem .7rem}';
        document.head.appendChild(st);
    }

    /* Troca o arquivo cru de cada aba pelo conteúdo do servidor. Um arquivo por
       aba casa pela posição; quantidade diferente vai tudo na primeira aba. Se
       o servidor falha, fica o registro montado na tela — o preview não some. */
    function loadRaw(popup, src, nPanes) {
        fetch(src.url, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                         body: JSON.stringify(src.body || {}) })
            .then(function (r) { return r.json(); })
            .then(function (res) {
                if (!res || !res.ok) return;
                var txt = (res.files || []).map(function (f) { return f && f.content ? String(f.content).replace(/\r?\n$/, '') : ''; });
                if (!txt.length && res.content) txt = [String(res.content)];
                txt = txt.filter(Boolean);
                if (!txt.length) return;
                var byPane = txt.length === nPanes ? txt : [txt.join('\n')];
                byPane.forEach(function (content, i) {
                    var el = popup && popup.querySelector('#otcPv' + i + ' .otc-preview-line');
                    if (el) el.textContent = content.replace(/\r\n/g, '\n');
                });
            })
            .catch(function () {});
    }

    window.otcFilePreview = function (opts) {
        opts = opts || {};
        ensureCss();
        var t = opts.t;
        var files = (opts.files || []).filter(Boolean);
        var tabs = files.length > 1
            ? '<ul class="nav nav-tabs otc-preview-tabs">' + files.map(function (f, i) {
                return '<li class="nav-item"><a class="nav-link' + (i === 0 ? ' active' : '') + '" data-bs-toggle="tab" href="#otcPv' + i + '">' + esc(f.label || f.file_name || ('#' + (i + 1))) + '</a></li>';
            }).join('') + '</ul>'
            : '';
        var panes = '<div class="tab-content">' + files.map(function (f, i) { return paneOf(f, i, t, files.length === 1); }).join('') + '</div>';
        var sub = opts.subtitleHtml || (opts.subtitle ? esc(opts.subtitle) : '');
        var html = (sub ? '<div class="text-start fs-xs text-muted mb-2">' + sub + '</div>' : '') +
            (opts.banner || '') + tabs + panes;
        var b = opts.buttons || {};
        var cfg = {
            title: '<span style="font-size:1rem">' + esc(opts.title || tr(t, 'nd-preview-title', 'File preview')) + '</span>',
            html: html, width: opts.width || 1000,
            showCloseButton: true, focusConfirm: false, allowOutsideClick: true,
            showConfirmButton: !!(b.download || b.send),
            confirmButtonText: b.send ? '<i class="ti ti-brand-telegram"></i>' : '<i class="ti ti-download"></i>',
            confirmButtonColor: b.send ? '#0066cc' : '#6658dd',
            showDenyButton: !!b.edit, denyButtonText: '<i class="ti ti-edit"></i>', denyButtonColor: '#3abff8',
            showCancelButton: !!(b.download || b.send || b.edit), cancelButtonText: '<i class="ti ti-x"></i>', cancelButtonColor: '#dc3545',
            customClass: { htmlContainer: 'text-start', confirmButton: 'bg-gradient', denyButton: 'bg-gradient', cancelButton: 'bg-gradient' },
            didOpen: function () {
                var popup = Swal.getPopup();
                if (opts.rawFrom && opts.rawFrom.url) loadRaw(popup, opts.rawFrom, files.length);
                if (typeof opts.didOpen === 'function') opts.didOpen(popup);
            }
        };
        return Swal.fire(cfg);
    };
    window.otcFilePreview.lineOf = lineOf;
    window.otcFilePreview.enrich = enrich;
})();

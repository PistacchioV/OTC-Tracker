/* ============================================================================
 * export-advanced.js — o item "Advanced" do menu Export, para qualquer tabela
 * do app.
 * ----------------------------------------------------------------------------
 * O Export do padrão da casa (Copy · CSV · Excel · Print · PDF) exporta o que
 * está NA TELA: filtros aplicados, ordenação aplicada, colunas visíveis. É o
 * que se quer quase sempre, e por isso ele não muda. O que faltava era o
 * "quase": tirar um recorte que a tela não está mostrando — um intervalo de
 * datas, uma contraparte só, sem as colunas que não interessam — sem ter de
 * filtrar a tela inteira antes e desfazer depois.
 *
 * Uso, DEPOIS de a DataTable existir:
 *
 *     otcExportAdvanced('#minha-tabela', {
 *         name:  'reference-data',   // nome do arquivo (sem extensão)
 *         skip:  [0, 1],             // colunas que nunca se exportam
 *         menu:  '#meuDropdownUl'    // só quando o dropdown é markup da página
 *     });
 *
 * Sem `menu` o item entra na COLLECTION do DataTables Buttons (o dropdown que
 * o próprio Buttons desenha), no fim da lista. Com `menu`, num <ul> da página.
 * Chamar duas vezes na mesma tabela não duplica o item.
 *
 * Quem executa a exportação continua sendo o DataTables Buttons: o modal monta
 * um botão temporário com o mesmo `extend` de sempre e dispara. Escrever um
 * gerador de arquivo próprio criaria um segundo CSV, com outro separador e
 * outro BOM que o do resto do app — e os dois divergiriam no primeiro acento.
 *
 * O `rows` do export é uma FUNÇÃO sobre o índice da linha, com o modifier em
 * `search:'none'`: a seleção já foi decidida aqui (inclusive se os filtros da
 * tela entram ou não), e deixar o DataTables filtrar de novo aplicaria a busca
 * duas vezes — o "ignorar os filtros da tela" nunca chegaria a valer.
 * A ORDEM vem do `order:'applied'`, que é a que está na tela.
 *
 * Texto: mapa _TRANS local com t(), lendo o idioma do localStorage. O
 * I18nManager traduz os [data-lang] UMA vez, no load, e este modal nasce depois
 * — os [data-lang] dele nunca seriam traduzidos.
 * ========================================================================== */
(function () {
    'use strict';

    var STYLE_ID = 'otc-expadv-style';
    var MODAL_ID = 'otcExpAdvModal';
    var BTN_NAME = 'otcadv';          // nome do botão temporário do Buttons

    var LANG = (localStorage.getItem('__OTC_TRACKER_LANG__') ||
                localStorage.getItem('language') || 'en').toLowerCase();

    var _TRANS = {
        en: {
            advanced: 'Advanced', title: 'Advanced export',
            format: 'Format', filename: 'File name',
            rows: 'Rows', rowsAll: 'All rows', rowsPage: 'Current page only',
            rowsRange: 'Positions from–to',
            useScreen: 'Start from the filters applied on screen',
            useScreenHelp: 'Unchecked, the export starts from the full table and only the criteria below apply.',
            rangeTitle: 'Range', rangeCol: 'Column', from: 'From', to: 'To',
            rangeHelp: 'Dates, numbers and text — both ends optional.',
            critTitle: 'Filters', critAdd: 'Add filter', critCol: 'Column',
            op: 'Condition', value: 'Value',
            opContains: 'contains', opNot: 'does not contain', opEquals: 'is exactly',
            opBegins: 'begins with', opEnds: 'ends with',
            opBlank: 'is blank', opNotBlank: 'is not blank',
            colsTitle: 'Columns', colsAll: 'All', colsVisible: 'On screen', colsNone: 'None',
            optTitle: 'Options', header: 'Include the header row',
            sep: 'CSV separator', orient: 'PDF orientation',
            portrait: 'Portrait', landscape: 'Landscape',
            count: '{n} of {total} rows', noRows: 'No row matches — nothing to export',
            noCols: 'Pick at least one column', run: 'Export', cancel: 'Cancel',
            colPick: '— pick a column —'
        },
        br: {
            advanced: 'Advanced', title: 'Exportação avançada',
            format: 'Formato', filename: 'Nome do arquivo',
            rows: 'Linhas', rowsAll: 'Todas as linhas', rowsPage: 'Só a página atual',
            rowsRange: 'Posições de–até',
            useScreen: 'Partir dos filtros aplicados na tela',
            useScreenHelp: 'Desmarcado, a exportação parte da tabela inteira e valem só os critérios abaixo.',
            rangeTitle: 'Intervalo', rangeCol: 'Coluna', from: 'De', to: 'Até',
            rangeHelp: 'Datas, números e texto — as duas pontas são opcionais.',
            critTitle: 'Filtros', critAdd: 'Adicionar filtro', critCol: 'Coluna',
            op: 'Condição', value: 'Valor',
            opContains: 'contém', opNot: 'não contém', opEquals: 'é exatamente',
            opBegins: 'começa com', opEnds: 'termina com',
            opBlank: 'está vazia', opNotBlank: 'não está vazia',
            colsTitle: 'Colunas', colsAll: 'Todas', colsVisible: 'Da tela', colsNone: 'Nenhuma',
            optTitle: 'Opções', header: 'Levar a linha de cabeçalho',
            sep: 'Separador do CSV', orient: 'Orientação do PDF',
            portrait: 'Retrato', landscape: 'Paisagem',
            count: '{n} de {total} linhas', noRows: 'Nenhuma linha casa — não há o que exportar',
            noCols: 'Escolha ao menos uma coluna', run: 'Exportar', cancel: 'Cancelar',
            colPick: '— escolha uma coluna —'
        },
        es: {
            advanced: 'Advanced', title: 'Exportación avanzada',
            format: 'Formato', filename: 'Nombre del archivo',
            rows: 'Filas', rowsAll: 'Todas las filas', rowsPage: 'Solo la página actual',
            rowsRange: 'Posiciones de–hasta',
            useScreen: 'Partir de los filtros aplicados en la pantalla',
            useScreenHelp: 'Sin marcar, la exportación parte de la tabla entera y valen solo los criterios de abajo.',
            rangeTitle: 'Intervalo', rangeCol: 'Columna', from: 'De', to: 'Hasta',
            rangeHelp: 'Fechas, números y texto — los dos extremos son opcionales.',
            critTitle: 'Filtros', critAdd: 'Añadir filtro', critCol: 'Columna',
            op: 'Condición', value: 'Valor',
            opContains: 'contiene', opNot: 'no contiene', opEquals: 'es exactamente',
            opBegins: 'empieza con', opEnds: 'termina con',
            opBlank: 'está vacía', opNotBlank: 'no está vacía',
            colsTitle: 'Columnas', colsAll: 'Todas', colsVisible: 'De la pantalla', colsNone: 'Ninguna',
            optTitle: 'Opciones', header: 'Incluir la fila de encabezado',
            sep: 'Separador del CSV', orient: 'Orientación del PDF',
            portrait: 'Vertical', landscape: 'Horizontal',
            count: '{n} de {total} filas', noRows: 'Ninguna fila coincide — no hay nada que exportar',
            noCols: 'Elija al menos una columna', run: 'Exportar', cancel: 'Cancelar',
            colPick: '— elija una columna —'
        }
    };

    function t(k, vars) {
        var s = (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k] || k;
        if (vars) Object.keys(vars).forEach(function (v) { s = s.split('{' + v + '}').join(vars[v]); });
        return s;
    }

    function esc(v) {
        return String(v == null ? '' : v)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    /* Texto de uma célula como o export a veria: sem tags e com as entidades
       resolvidas. É o mesmo tratamento do DataTables Buttons — comparar contra o
       HTML cru faria um badge de status nunca casar com o que está escrito
       nele. */
    var _decoder = null;
    function plain(html) {
        var s = String(html == null ? '' : html).replace(/<[^>]*>/g, ' ');
        if (s.indexOf('&') !== -1) {
            if (!_decoder) _decoder = document.createElement('textarea');
            _decoder.innerHTML = s;
            s = _decoder.value;
        }
        return s.replace(/\s+/g, ' ').trim();
    }

    /* ── Comparação de intervalo ──────────────────────────────────────────
       O tipo do intervalo é decidido pelas PONTAS que a pessoa digitou, não
       pelo conteúdo da coluna: com 'De' e 'Até' em data, a célula que não for
       data fica de fora (é o que ela quis dizer); com pontas numéricas, o
       mesmo. Adivinhar pelo conteúdo faria a mesma coluna mudar de regra
       conforme a linha. */
    function parseDate(v) {
        var s = String(v == null ? '' : v).trim();
        var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s);
        if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
        m = /^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})$/.exec(s);
        if (m) {
            var y = +m[3];
            if (y < 100) y += y < 70 ? 2000 : 1900;
            return Date.UTC(y, +m[2] - 1, +m[1]);
        }
        return null;
    }
    function parseNum(v) {
        var s = String(v == null ? '' : v).trim().replace(/\s/g, '');
        if (!s || !/^-?[\d.,]+%?$/.test(s)) return null;
        s = s.replace(/%$/, '');
        var lastC = s.lastIndexOf(','), lastD = s.lastIndexOf('.');
        if (lastC > lastD)      s = s.replace(/\./g, '').replace(',', '.');   // 1.234,56
        else if (lastD > lastC) s = s.replace(/,/g, '');                      // 1,234.56
        else                    s = s.replace(/[.,]/g, '');
        var n = parseFloat(s);
        return isNaN(n) ? null : n;
    }
    function coerce(v, kind) {
        if (kind === 'date') return parseDate(v);
        if (kind === 'num')  return parseNum(v);
        return String(v == null ? '' : v).trim().toLowerCase();
    }
    function endKind(a, b) {
        var vals = [a, b].filter(function (x) { return String(x || '').trim() !== ''; });
        if (!vals.length) return null;
        if (vals.every(function (x) { return parseDate(x) !== null; })) return 'date';
        if (vals.every(function (x) { return parseNum(x) !== null; })) return 'num';
        return 'text';
    }

    /* ── Estilo (uma vez) ─────────────────────────────────────────────── */
    function ensureStyle() {
        if (document.getElementById(STYLE_ID)) return;
        var css = ''
            + '#' + MODAL_ID + ' .xa-sec{border:1px solid var(--vr-border,rgba(0,0,0,.1));border-radius:12px;padding:10px 12px;margin-bottom:10px}'
            + '#' + MODAL_ID + ' .xa-sec-h{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em;opacity:.75;margin-bottom:8px}'
            + '#' + MODAL_ID + ' .form-label{font-size:.72rem;margin-bottom:2px;opacity:.85}'
            + '#' + MODAL_ID + ' .form-control,#' + MODAL_ID + ' .form-select{font-size:.78rem}'
            + '#' + MODAL_ID + ' .form-control-sm,#' + MODAL_ID + ' .form-select-sm{height:31px}'
            + '#' + MODAL_ID + ' .xa-help{font-size:.68rem;opacity:.65;margin-top:4px}'
            + '#' + MODAL_ID + ' .xa-crit{display:grid;grid-template-columns:1fr 130px 1fr 32px;gap:6px;margin-bottom:6px;align-items:center}'
            + '#' + MODAL_ID + ' .xa-cols{max-height:180px;overflow:auto;display:grid;'
            +   'grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:2px 10px;'
            +   'border:1px solid var(--vr-border,rgba(0,0,0,.1));border-radius:8px;padding:8px}'
            + '#' + MODAL_ID + ' .xa-cols label{font-size:.75rem;display:flex;align-items:center;gap:6px;margin:0;cursor:pointer}'
            + '#' + MODAL_ID + ' .xa-count{font-size:.75rem;font-variant-numeric:tabular-nums;opacity:.8}'
            + '#' + MODAL_ID + ' .xa-count.xa-zero{color:var(--ins-danger,#d93025);opacity:1;font-weight:600}'
            + '#' + MODAL_ID + ' .xa-rm{width:28px;height:28px;border-radius:8px;padding:0;display:inline-flex;'
            +   'align-items:center;justify-content:center}';
        var el = document.createElement('style');
        el.id = STYLE_ID;
        el.textContent = css;
        document.head.appendChild(el);
    }

    /* ── Modal (um por página, reaproveitado) ─────────────────────────── */
    function ensureModal() {
        var el = document.getElementById(MODAL_ID);
        if (el) return el;
        ensureStyle();
        el = document.createElement('div');
        el.className = 'modal fade';
        el.id = MODAL_ID;
        el.tabIndex = -1;
        el.innerHTML =
        '<div class="modal-dialog modal-lg modal-dialog-scrollable">' +
          '<div class="modal-content">' +
            '<div class="modal-header py-2">' +
              '<h5 class="modal-title fs-6"><i class="ti ti-adjustments-alt me-1"></i>' + esc(t('title')) + '</h5>' +
              '<button type="button" class="btn-close" data-bs-dismiss="modal"></button>' +
            '</div>' +
            '<div class="modal-body">' +

              '<div class="row g-2 mb-2">' +
                '<div class="col-md-4"><label class="form-label">' + esc(t('format')) + '</label>' +
                  '<select class="form-select form-select-sm" id="xaFormat"></select></div>' +
                '<div class="col-md-5"><label class="form-label">' + esc(t('filename')) + '</label>' +
                  '<input type="text" class="form-control form-control-sm" id="xaName"></div>' +
                '<div class="col-md-3"><label class="form-label">' + esc(t('rows')) + '</label>' +
                  '<select class="form-select form-select-sm" id="xaScope">' +
                    '<option value="all">' + esc(t('rowsAll')) + '</option>' +
                    '<option value="page">' + esc(t('rowsPage')) + '</option>' +
                    '<option value="range">' + esc(t('rowsRange')) + '</option>' +
                  '</select></div>' +
              '</div>' +
              '<div class="row g-2 mb-2 d-none" id="xaPosWrap">' +
                '<div class="col-6"><label class="form-label">' + esc(t('from')) + '</label>' +
                  '<input type="number" min="1" class="form-control form-control-sm" id="xaPosFrom"></div>' +
                '<div class="col-6"><label class="form-label">' + esc(t('to')) + '</label>' +
                  '<input type="number" min="1" class="form-control form-control-sm" id="xaPosTo"></div>' +
              '</div>' +

              '<div class="form-check mb-2">' +
                '<input class="form-check-input" type="checkbox" id="xaScreen" checked>' +
                '<label class="form-check-label" for="xaScreen" style="font-size:.78rem">' + esc(t('useScreen')) + '</label>' +
                '<div class="xa-help">' + esc(t('useScreenHelp')) + '</div>' +
              '</div>' +

              '<div class="xa-sec">' +
                '<div class="xa-sec-h">' + esc(t('rangeTitle')) + '</div>' +
                '<div class="row g-2">' +
                  '<div class="col-md-6"><label class="form-label">' + esc(t('rangeCol')) + '</label>' +
                    '<select class="form-select form-select-sm" id="xaRangeCol"></select></div>' +
                  '<div class="col-md-3"><label class="form-label">' + esc(t('from')) + '</label>' +
                    '<input type="text" class="form-control form-control-sm" id="xaRangeFrom"></div>' +
                  '<div class="col-md-3"><label class="form-label">' + esc(t('to')) + '</label>' +
                    '<input type="text" class="form-control form-control-sm" id="xaRangeTo"></div>' +
                '</div>' +
                '<div class="xa-help">' + esc(t('rangeHelp')) + '</div>' +
              '</div>' +

              '<div class="xa-sec">' +
                '<div class="xa-sec-h">' + esc(t('critTitle')) + '</div>' +
                '<div id="xaCrits"></div>' +
                '<button type="button" class="btn btn-sm btn-outline-secondary" id="xaAddCrit">' +
                  '<i class="ti ti-plus me-1"></i>' + esc(t('critAdd')) + '</button>' +
              '</div>' +

              '<div class="xa-sec">' +
                '<div class="d-flex align-items-center justify-content-between mb-1">' +
                  '<div class="xa-sec-h mb-0">' + esc(t('colsTitle')) + '</div>' +
                  '<div class="btn-group btn-group-sm">' +
                    '<button type="button" class="btn btn-outline-secondary" data-xa-cols="all">' + esc(t('colsAll')) + '</button>' +
                    '<button type="button" class="btn btn-outline-secondary" data-xa-cols="visible">' + esc(t('colsVisible')) + '</button>' +
                    '<button type="button" class="btn btn-outline-secondary" data-xa-cols="none">' + esc(t('colsNone')) + '</button>' +
                  '</div>' +
                '</div>' +
                '<div class="xa-cols" id="xaCols"></div>' +
              '</div>' +

              '<div class="xa-sec mb-0">' +
                '<div class="xa-sec-h">' + esc(t('optTitle')) + '</div>' +
                '<div class="row g-2 align-items-end">' +
                  '<div class="col-md-4"><div class="form-check mt-3">' +
                    '<input class="form-check-input" type="checkbox" id="xaHeader" checked>' +
                    '<label class="form-check-label" for="xaHeader" style="font-size:.78rem">' + esc(t('header')) + '</label>' +
                  '</div></div>' +
                  '<div class="col-md-4" id="xaSepWrap"><label class="form-label">' + esc(t('sep')) + '</label>' +
                    '<select class="form-select form-select-sm" id="xaSep">' +
                      '<option value=";">;</option><option value=",">,</option>' +
                      '<option value="\t">Tab</option></select></div>' +
                  '<div class="col-md-4 d-none" id="xaOrientWrap"><label class="form-label">' + esc(t('orient')) + '</label>' +
                    '<select class="form-select form-select-sm" id="xaOrient">' +
                      '<option value="landscape">' + esc(t('landscape')) + '</option>' +
                      '<option value="portrait">' + esc(t('portrait')) + '</option></select></div>' +
                '</div>' +
              '</div>' +

            '</div>' +
            '<div class="modal-footer py-2">' +
              '<span class="xa-count me-auto" id="xaCount"></span>' +
              '<button type="button" class="btn btn-sm btn-outline-secondary" data-bs-dismiss="modal">' + esc(t('cancel')) + '</button>' +
              '<button type="button" class="btn btn-sm btn-primary bg-gradient" id="xaRun">' +
                '<i class="ti ti-download me-1"></i>' + esc(t('run')) + '</button>' +
            '</div>' +
          '</div>' +
        '</div>';
        document.body.appendChild(el);
        return el;
    }

    /* Formatos disponíveis NESTA página: Excel só com o JSZip carregado e PDF
       só com o pdfmake. Oferecer o que não tem biblioteca produz um clique que
       não faz nada e nenhuma mensagem — o menu de sempre já nasce assim,
       montado por página. */
    function formats() {
        var out = [{ v: 'excelHtml5', l: 'Excel (.xlsx)', need: !!(window.JSZip ||
                        (window.jQuery && jQuery.fn.dataTable && jQuery.fn.dataTable.Buttons &&
                         jQuery.fn.dataTable.Buttons.jszip)) },
                   { v: 'csvHtml5',  l: 'CSV', need: true },
                   { v: 'pdfHtml5',  l: 'PDF', need: !!window.pdfMake },
                   { v: 'print',     l: 'Print', need: true },
                   { v: 'copyHtml5', l: 'Copy', need: true }];
        return out.filter(function (o) { return o.need; });
    }

    /* ── Colunas oferecidas ───────────────────────────────────────────────
       Colunas SEM rótulo (a do checkbox) e a de Actions ficam de fora sozinhas
       — é o mesmo par que o `skip` do otcCellCopy tira em toda tela, e deixar
       que cada página o repita é uma lista para envelhecer. `opts.skip` existe
       para o que fugir desses dois casos. */
    var DROP_LABEL = /^(actions?|a[çc][õo]es|acciones)$/i;
    function columnList(dt, skip) {
        var out = [];
        dt.columns().every(function (i) {
            if (skip.indexOf(i) !== -1) return;
            // O texto do <th> pode carregar o campo de filtro quando a página
            // monta a linha de busca dentro do mesmo cabeçalho: só o texto
            // interessa, e um clone sem inputs é o jeito de tê-lo limpo.
            var $c = jQuery(this.header()).clone();
            $c.find('input,select,button').remove();
            var label = $c.text().replace(/\s+/g, ' ').trim();
            if (!label || DROP_LABEL.test(label)) return;
            out.push({ idx: i, label: label, visible: this.visible() });
        });
        return out;
    }

    /* Nome do arquivo: o título da página, que é como a pessoa chama a tela.
       O id da tabela é o último recurso — `ref-data-table` não é o nome de
       nada que se mande por e-mail. */
    function defaultName(node) {
        var h = document.querySelector('.page-title-head h4, .page-title-head h5');
        var s = h ? h.textContent : '';
        s = String(s || node.id || 'export').replace(/\s+/g, ' ').trim();
        return s.replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'export';
    }

    /* ── O modal em si ────────────────────────────────────────────────── */
    function open(dt, opts) {
        var el = ensureModal();
        var $el = jQuery(el);
        var cols = columnList(dt, opts.skip);
        var fmts = formats();

        $el.find('#xaFormat').html(fmts.map(function (f) {
            return '<option value="' + f.v + '">' + esc(f.l) + '</option>';
        }).join(''));
        $el.find('#xaName').val(opts.name || 'export');

        var colOpts = '<option value="">' + esc(t('colPick')) + '</option>' +
            cols.map(function (c) { return '<option value="' + c.idx + '">' + esc(c.label) + '</option>'; }).join('');
        $el.find('#xaRangeCol').html(colOpts).val('');
        $el.find('#xaRangeFrom,#xaRangeTo').val('');
        $el.find('#xaPosFrom,#xaPosTo').val('');
        $el.find('#xaScope').val('all');
        $el.find('#xaPosWrap').addClass('d-none');
        $el.find('#xaScreen,#xaHeader').prop('checked', true);
        $el.find('#xaSep').val(';');
        $el.find('#xaOrient').val('landscape');

        $el.find('#xaCols').html(cols.map(function (c) {
            return '<label><input type="checkbox" class="form-check-input xa-col" value="' + c.idx + '"' +
                   (c.visible ? ' checked' : '') + '><span>' + esc(c.label) + '</span></label>';
        }).join(''));

        var critHtml = function () {
            return '<div class="xa-crit">' +
                '<select class="form-select form-select-sm xa-c-col">' + colOpts + '</select>' +
                '<select class="form-select form-select-sm xa-c-op">' +
                    '<option value="contains">' + esc(t('opContains')) + '</option>' +
                    '<option value="not">' + esc(t('opNot')) + '</option>' +
                    '<option value="equals">' + esc(t('opEquals')) + '</option>' +
                    '<option value="begins">' + esc(t('opBegins')) + '</option>' +
                    '<option value="ends">' + esc(t('opEnds')) + '</option>' +
                    '<option value="blank">' + esc(t('opBlank')) + '</option>' +
                    '<option value="notblank">' + esc(t('opNotBlank')) + '</option>' +
                '</select>' +
                '<input type="text" class="form-control form-control-sm xa-c-val" placeholder="' + esc(t('value')) + '">' +
                '<button type="button" class="btn btn-sm btn-outline-danger xa-rm"><i class="ti ti-x"></i></button>' +
            '</div>';
        };
        $el.find('#xaCrits').html(critHtml());

        /* Lê o formulário. Uma leitura só, usada pela contagem e pelo export —
           duas leituras seriam duas respostas para a mesma pergunta. */
        function read() {
            var crits = [];
            $el.find('.xa-crit').each(function () {
                var col = jQuery(this).find('.xa-c-col').val();
                var op  = jQuery(this).find('.xa-c-op').val();
                var val = jQuery(this).find('.xa-c-val').val() || '';
                if (col === '' || col == null) return;
                // Critério sem valor é critério pela metade: aplicá-lo com o
                // valor vazio deixaria passar tudo (ou nada, no `equals`) sem
                // ninguém ter pedido. Blank/not blank são as exceções — são
                // eles próprios a pergunta.
                if (op !== 'blank' && op !== 'notblank' && !String(val).trim()) return;
                crits.push({ col: +col, op: op, val: String(val) });
            });
            return {
                format: $el.find('#xaFormat').val(),
                name:   (($el.find('#xaName').val() || '').trim() || 'export'),
                scope:  $el.find('#xaScope').val(),
                posFrom: parseInt($el.find('#xaPosFrom').val(), 10),
                posTo:   parseInt($el.find('#xaPosTo').val(), 10),
                screen: $el.find('#xaScreen').is(':checked'),
                header: $el.find('#xaHeader').is(':checked'),
                sep:    $el.find('#xaSep').val(),
                orient: $el.find('#xaOrient').val(),
                rangeCol: $el.find('#xaRangeCol').val(),
                rangeFrom: $el.find('#xaRangeFrom').val() || '',
                rangeTo:   $el.find('#xaRangeTo').val() || '',
                crits: crits,
                cols: $el.find('.xa-col:checked').map(function () { return +this.value; }).get()
            };
        }

        /* Os índices de linha que vão para o arquivo, já na ordem da tela. */
        function pick(o) {
            var base = dt.rows({
                search: o.screen ? 'applied' : 'none',
                order:  'applied',
                page:   o.scope === 'page' ? 'current' : 'all'
            }).indexes().toArray();

            var rk = o.rangeCol === '' ? null : endKind(o.rangeFrom, o.rangeTo);
            var lo = rk ? coerce(o.rangeFrom, rk) : null;
            var hi = rk ? coerce(o.rangeTo, rk) : null;
            if (String(o.rangeFrom).trim() === '') lo = null;
            if (String(o.rangeTo).trim() === '')   hi = null;

            var keep = base.filter(function (idx) {
                var i, c, cell;
                for (i = 0; i < o.crits.length; i++) {
                    c = o.crits[i];
                    cell = plain(dt.cell(idx, c.col).render('display'));
                    var hay = cell.toLowerCase(), ndl = String(c.val).trim().toLowerCase();
                    if (c.op === 'blank'    && cell !== '') return false;
                    if (c.op === 'notblank' && cell === '') return false;
                    if (c.op === 'contains' && hay.indexOf(ndl) === -1) return false;
                    if (c.op === 'not'      && hay.indexOf(ndl) !== -1) return false;
                    if (c.op === 'equals'   && hay !== ndl) return false;
                    if (c.op === 'begins'   && hay.indexOf(ndl) !== 0) return false;
                    if (c.op === 'ends'     && hay.lastIndexOf(ndl) !== hay.length - ndl.length) return false;
                }
                if (rk && (lo !== null || hi !== null)) {
                    var v = coerce(plain(dt.cell(idx, +o.rangeCol).render('display')), rk);
                    // Célula que não é do tipo do intervalo (data que não é
                    // data, número que não é número) fica de fora: incluí-la
                    // seria dizer que ela está dentro de um intervalo que não
                    // sabe medir.
                    if (v === null || v === '') return false;
                    if (lo !== null && v < lo) return false;
                    if (hi !== null && v > hi) return false;
                }
                return true;
            });

            if (o.scope === 'range') {
                var a = isNaN(o.posFrom) ? 1 : Math.max(1, o.posFrom);
                var b = isNaN(o.posTo) ? keep.length : Math.max(a, o.posTo);
                keep = keep.slice(a - 1, b);
            }
            return keep;
        }

        var lastKeep = [];
        function refresh() {
            var o = read();
            $el.find('#xaPosWrap').toggleClass('d-none', o.scope !== 'range');
            $el.find('#xaSepWrap').toggleClass('d-none', o.format !== 'csvHtml5');
            $el.find('#xaOrientWrap').toggleClass('d-none', o.format !== 'pdfHtml5');
            lastKeep = pick(o);
            var total = dt.rows().count();
            var $c = $el.find('#xaCount');
            var bad = !lastKeep.length || !o.cols.length;
            $c.text(!o.cols.length ? t('noCols')
                   : !lastKeep.length ? t('noRows')
                   : t('count', { n: lastKeep.length, total: total }))
              .toggleClass('xa-zero', bad);
            $el.find('#xaRun').prop('disabled', bad);
        }

        // Digitar recontava a cada tecla, e a contagem varre a tabela inteira:
        // numa tabela grande o campo engasgava. O `change` (select, checkbox)
        // continua imediato — ali não há tecla a esperar.
        var pending = null;
        function refreshSoon() {
            if (pending) clearTimeout(pending);
            pending = setTimeout(function () { pending = null; refresh(); }, 200);
        }

        // Um handler por abertura seria um handler a mais a cada clique no
        // menu: o namespace `.xa` é removido antes de religar.
        $el.off('.xa')
           .on('input.xa', 'input', refreshSoon)
           .on('change.xa', 'input,select', refresh)
           .on('click.xa', '#xaAddCrit', function () {
               jQuery(critHtml()).appendTo($el.find('#xaCrits'));
           })
           .on('click.xa', '.xa-rm', function () {
               var $all = $el.find('.xa-crit');
               if ($all.length > 1) jQuery(this).closest('.xa-crit').remove();
               else $all.find('.xa-c-val').val('');
               refresh();
           })
           .on('click.xa', '[data-xa-cols]', function () {
               var mode = this.getAttribute('data-xa-cols');
               $el.find('.xa-col').each(function () {
                   var box = this;
                   var c = cols.filter(function (x) { return x.idx === +box.value; })[0];
                   box.checked = mode === 'all' ? true : mode === 'none' ? false : !!(c && c.visible);
               });
               refresh();
           })
           .on('click.xa', '#xaRun', function () {
               var o = read();
               if (!lastKeep.length || !o.cols.length) return;
               run(dt, o, lastKeep);
               bootstrap.Modal.getInstance(el).hide();
           });

        refresh();
        bootstrap.Modal.getOrCreateInstance(el).show();
    }

    /* ── A exportação ─────────────────────────────────────────────────── */
    function run(dt, o, keep) {
        var set = {};
        keep.forEach(function (i) { set[i] = 1; });

        var conf = {
            extend: o.format,
            name: BTN_NAME,
            filename: o.name,
            header: o.header,
            footer: false,
            exportOptions: {
                columns: o.cols,
                rows: function (idx) { return set[idx] === 1; },
                modifier: { search: 'none', order: 'applied', page: 'all' }
            }
        };
        if (o.format === 'csvHtml5') { conf.fieldSeparator = o.sep; conf.bom = true; }
        if (o.format === 'pdfHtml5') { conf.orientation = o.orient; conf.pageSize = 'A4'; }

        // UMA instância de Buttons por tabela, guardada no nó: criar uma nova a
        // cada exportação empilharia instâncias no `_buttons` da tabela pela
        // vida da página. O botão anterior sai ANTES do trigger, e não depois —
        // Print e Copy trabalham fora do clique, e removê-lo em cima da ação
        // mataria a janela de impressão.
        var node = dt.table().node();
        if (!node._otcAdvButtons) {
            node._otcAdvButtons = new jQuery.fn.dataTable.Buttons(dt, { buttons: [] });
        }
        try { dt.button(BTN_NAME + ':name').remove(); } catch (e) { /* ainda não existe */ }
        node._otcAdvButtons.add(conf, 0);
        dt.button(BTN_NAME + ':name').trigger();
    }

    /* ── Ligação ao menu ──────────────────────────────────────────────── */
    function itemHtml() {
        return '<li><hr class="dropdown-divider"></li>' +
               '<li><a class="dropdown-item" href="#" data-otc-expadv>' +
               '<i class="ti ti-adjustments-alt me-1"></i>' + esc(t('advanced')) + '</a></li>';
    }

    /* Insere no fim da PRIMEIRA collection que a tabela tiver. `inst.add(conf,
       'j-n')` é a forma do Buttons de escrever dentro de uma collection já
       montada — recriar o menu por fora perderia as configurações de export
       que cada página escreveu nos itens dela. */
    function addToCollection(dt, conf) {
        var st = dt.settings()[0];
        var insts = (st && st._buttons) || [];
        for (var i = 0; i < insts.length; i++) {
            var inst = insts[i].inst;
            var list = (inst && inst.s && inst.s.buttons) || [];
            for (var j = 0; j < list.length; j++) {
                if (list[j].buttons && list[j].buttons.length) {
                    inst.add(conf, j + '-' + list[j].buttons.length);
                    return true;
                }
            }
        }
        return false;
    }

    /* Resolve a DataTable NA HORA do clique, e não na hora da ligação. Uma
       página que destrói e recria a tabela (a Recon FXO faz isso quando as
       colunas chegam do servidor) deixaria o item preso à instância morta —
       um menu que abre e não exporta nada, sem erro no console. */
    function resolveDt(target) {
        if (target && target.rows && target.columns) return target;
        try {
            var dt = jQuery(target).DataTable();
            return (dt && dt.settings && dt.settings()[0]) ? dt : null;
        } catch (e) { return null; }
    }

    window.otcExportAdvanced = function (target, opts) {
        opts = opts || {};
        if (!window.jQuery || !jQuery.fn.dataTable) return false;
        var dt = resolveDt(target);
        if (!dt) return false;

        var node = dt.table().node();
        if (node.getAttribute('data-otc-expadv') === '1') return true;   // idempotente
        node.setAttribute('data-otc-expadv', '1');

        if (!opts.name) opts.name = defaultName(node);
        if (!opts.skip) opts.skip = [];

        if (opts.menu) {
            var $ul = jQuery(opts.menu);
            if (!$ul.length) return false;
            $ul.append(itemHtml());
            $ul.on('click', '[data-otc-expadv]', function (e) {
                e.preventDefault();
                open(resolveDt(target) || dt, opts);
            });
            return true;
        }

        return addToCollection(dt, {
            text: '<i class="ti ti-adjustments-alt me-1"></i>' + esc(t('advanced')),
            className: 'dropdown-item',
            // O Buttons entrega a API da tabela do próprio botão — é ela que
            // vale, não a que estava em mãos quando o item foi criado.
            action: function (e, api) { open(api || resolveDt(target) || dt, opts); }
        });
    };
})();

/* ============================================================================
 * export-advanced.js — o item "Advanced Export" do menu Export, para qualquer
 * tabela do app.
 * ----------------------------------------------------------------------------
 * O Export do padrão da casa (Copy · CSV · Excel · Print · PDF) exporta o que
 * está NA TELA: filtros aplicados, ordenação aplicada, colunas visíveis. É o
 * que se quer quase sempre, e por isso ele não muda. O que faltava era o
 * "quase", e são duas coisas:
 *
 *  1. um recorte que a tela não está mostrando — uma contraparte só, sem as
 *     colunas que não interessam — sem filtrar a tela inteira antes e desfazer
 *     depois;
 *  2. VÁRIOS DIAS. A tela mostra um dia; os arquivos-dia do
 *     `static/data/cache/` guardam a série, e até aqui a única forma de olhar o
 *     mês era abrir a página vinte vezes, exportando uma planilha de cada vez.
 *
 * Uso, DEPOIS de a DataTable existir:
 *
 *     otcExportAdvanced('#minha-tabela', {
 *         name:  'reference-data',   // nome do arquivo (sem extensão)
 *         skip:  [0, 1],             // colunas que nunca se exportam
 *         menu:  '#meuDropdownUl',   // só quando o dropdown é markup da página
 *         daily: '/api/operations-b3/data'          // ou:
 *         daily: { url: '/reconciliation-fxo/data', // endpoint do dia
 *                  param: 'recon_date',             // padrão: 'date'
 *                  rows: 'data' }                   // padrão: 'rows'
 *     });
 *
 * `daily` é o endpoint que a PRÓPRIA página consulta para desenhar um dia. O
 * intervalo o chama uma vez por data e empilha o resultado — em vez de ler os
 * JSON do cache por fora, que seria uma segunda regra sobre os mesmos arquivos,
 * para discordar da tela no primeiro caso de borda. Cada linha sai com a
 * Reference Date do arquivo de onde veio.
 *
 * Tela SEM arquivo-dia não declara `daily`: o Reference Data é cadastro — existe
 * o de agora e nada mais —, e a seção do intervalo nasce desabilitada dizendo
 * por quê, em vez de sumir (um campo que some lê-se como defeito).
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
            advanced: 'Advanced Export', title: 'Advanced Export',
            format: 'Format', filename: 'File name',
            rows: 'Rows', rowsAll: 'All rows', rowsPage: 'Current page only',
            rowsRange: 'Positions from–to',
            useScreen: 'Start from the filters applied on screen',
            useScreenHelp: 'Unchecked, the export starts from the full table and only the criteria below apply.',
            daysTitle: 'Range — daily files', from: 'From', to: 'To',
            daysHelp: 'Leave empty to export the day on screen. With a range, one file is read '
                    + 'per day and every row carries its Reference Date.',
            daysNone: 'This page has no daily files — there is only the current registry, so the '
                    + 'export always covers what is on screen.',
            daysReading: 'Reading {d}… ({i}/{n})',
            daysFailed: 'Could not read {n} day(s)',
            daysEmpty: 'No day in the range has data',
            daysTooLong: 'Range too long — at most {n} days',
            daysBackwards: 'The end date comes before the start date',
            refDate: 'Reference Date',
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
            advanced: 'Advanced Export', title: 'Exportação avançada',
            format: 'Formato', filename: 'Nome do arquivo',
            rows: 'Linhas', rowsAll: 'Todas as linhas', rowsPage: 'Só a página atual',
            rowsRange: 'Posições de–até',
            useScreen: 'Partir dos filtros aplicados na tela',
            useScreenHelp: 'Desmarcado, a exportação parte da tabela inteira e valem só os critérios abaixo.',
            daysTitle: 'Intervalo — arquivos diários', from: 'De', to: 'Até',
            daysHelp: 'Em branco, exporta o dia que está na tela. Com intervalo, lê um arquivo '
                    + 'por dia e cada linha leva a Reference Date dela.',
            daysNone: 'Esta tela não tem arquivo diário — é o cadastro de agora, então o export '
                    + 'cobre sempre o que está na tela.',
            daysReading: 'Lendo {d}… ({i}/{n})',
            daysFailed: 'Não consegui ler {n} dia(s)',
            daysEmpty: 'Nenhum dia do intervalo tem dado',
            daysTooLong: 'Intervalo longo demais — no máximo {n} dias',
            daysBackwards: 'A data final é anterior à inicial',
            refDate: 'Reference Date',
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
            advanced: 'Advanced Export', title: 'Exportación avanzada',
            format: 'Formato', filename: 'Nombre del archivo',
            rows: 'Filas', rowsAll: 'Todas las filas', rowsPage: 'Solo la página actual',
            rowsRange: 'Posiciones de–hasta',
            useScreen: 'Partir de los filtros aplicados en la pantalla',
            useScreenHelp: 'Sin marcar, la exportación parte de la tabla entera y valen solo los criterios de abajo.',
            daysTitle: 'Intervalo — archivos diarios', from: 'De', to: 'Hasta',
            daysHelp: 'En blanco, exporta el día que está en la pantalla. Con intervalo, lee un '
                    + 'archivo por día y cada fila lleva su Reference Date.',
            daysNone: 'Esta pantalla no tiene archivo diario — es el registro de ahora, así que '
                    + 'la exportación cubre siempre lo que está en la pantalla.',
            daysReading: 'Leyendo {d}… ({i}/{n})',
            daysFailed: 'No pude leer {n} día(s)',
            daysEmpty: 'Ningún día del intervalo tiene datos',
            daysTooLong: 'Intervalo demasiado largo — como máximo {n} días',
            daysBackwards: 'La fecha final es anterior a la inicial',
            refDate: 'Reference Date',
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
            +   'align-items:center;justify-content:center}'
            // Seção desabilitada: fica à VISTA, apagada, com o motivo escrito.
            // Escondê-la faria a mesma tela parecer duas conforme a página.
            + '#' + MODAL_ID + ' .xa-off{opacity:.55}'
            + '#' + MODAL_ID + ' .xa-off .xa-help{font-style:italic}';
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

              /* O Range é o intervalo de DIAS dos arquivos do cache, não uma
                 faixa de valores de uma coluna: a tela mostra um dia, e o que
                 se quer exportar é a série. A tela que não tem arquivo diário
                 (Reference Data é cadastro, não é do dia) recebe a seção
                 DESABILITADA com o motivo escrito — em branco, ela pareceria
                 defeito. */
              '<div class="xa-sec" id="xaDaySec">' +
                '<div class="xa-sec-h">' + esc(t('daysTitle')) + '</div>' +
                '<div class="row g-2">' +
                  '<div class="col-md-6"><label class="form-label">' + esc(t('from')) + '</label>' +
                    '<input type="date" class="form-control form-control-sm" id="xaDayFrom"></div>' +
                  '<div class="col-md-6"><label class="form-label">' + esc(t('to')) + '</label>' +
                    '<input type="date" class="form-control form-control-sm" id="xaDayTo"></div>' +
                '</div>' +
                '<div class="xa-help" id="xaDayHelp">' + esc(t('daysHelp')) + '</div>' +
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

        // Sem arquivo diário a seção fica visível e DESABILITADA, com o motivo
        // escrito. Escondê-la faria a mesma tela parecer duas conforme a
        // página, e um campo que some sem explicação lê-se como defeito.
        var daily = normDaily(opts.daily);
        $el.find('#xaDayFrom,#xaDayTo').val('').prop('disabled', !daily);
        $el.find('#xaDaySec').toggleClass('xa-off', !daily);
        $el.find('#xaDayHelp').text(daily ? t('daysHelp') : t('daysNone'));
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
                // O RÓTULO vai junto do índice: no export por intervalo de dias
                // a tabela é outra (a que se monta com os arquivos), e o índice
                // da tela não vale nela — o que casa as duas é o nome da coluna.
                var lbl = (cols.filter(function (c) { return c.idx === +col; })[0] || {}).label || '';
                crits.push({ col: +col, label: lbl, op: op, val: String(val) });
            });
            var checked = $el.find('.xa-col:checked').map(function () { return +this.value; }).get();
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
                dayFrom: $el.find('#xaDayFrom').val() || '',
                dayTo:   $el.find('#xaDayTo').val() || '',
                crits: crits,
                cols: checked,
                colLabels: checked.map(function (i) {
                    return (cols.filter(function (c) { return c.idx === i; })[0] || {}).label || '';
                })
            };
        }

        /* Os índices de linha que vão para o arquivo, já na ordem da tabela.
           `tbl` é a tabela da TELA no caminho normal e a montada com os arquivos
           do dia no caminho do intervalo; `map` traduz o índice de coluna da
           tela para o dela. */
        function pick(o, tbl, map) {
            tbl = tbl || dt;
            var base = tbl.rows({
                search: (tbl === dt && o.screen) ? 'applied' : 'none',
                order:  'applied',
                page:   (tbl === dt && o.scope === 'page') ? 'current' : 'all'
            }).indexes().toArray();

            var crits = o.crits.map(function (c) {
                return { col: map ? map(c) : c.col, op: c.op, val: c.val };
            }).filter(function (c) { return c.col !== null && c.col >= 0; });

            var keep = base.filter(function (idx) {
                for (var i = 0; i < crits.length; i++) {
                    var c = crits[i];
                    var cell = plain(tbl.cell(idx, c.col).render('display'));
                    var hay = cell.toLowerCase(), ndl = String(c.val).trim().toLowerCase();
                    if (c.op === 'blank'    && cell !== '') return false;
                    if (c.op === 'notblank' && cell === '') return false;
                    if (c.op === 'contains' && hay.indexOf(ndl) === -1) return false;
                    if (c.op === 'not'      && hay.indexOf(ndl) !== -1) return false;
                    if (c.op === 'equals'   && hay !== ndl) return false;
                    if (c.op === 'begins'   && hay.indexOf(ndl) !== 0) return false;
                    if (c.op === 'ends'     && hay.lastIndexOf(ndl) !== hay.length - ndl.length) return false;
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
            var $c = $el.find('#xaCount');
            if (!o.cols.length) {
                $c.text(t('noCols')).addClass('xa-zero');
                $el.find('#xaRun').prop('disabled', true);
                return;
            }
            // Com intervalo de dias a contagem não é a da tela: as linhas ainda
            // estão em disco. Prometer um número aqui seria prometer o da tela,
            // que é justamente o que essa exportação NÃO é.
            var dayErr = dayRangeError(o);
            if (dayErr) {
                $c.text(dayErr).addClass('xa-zero');
                $el.find('#xaRun').prop('disabled', true);
                return;
            }
            if (o.dayFrom || o.dayTo) {
                $c.text(t('daysHelp')).removeClass('xa-zero');
                $el.find('#xaRun').prop('disabled', false);
                return;
            }
            lastKeep = pick(o);
            var total = dt.rows().count();
            var bad = !lastKeep.length;
            $c.text(bad ? t('noRows') : t('count', { n: lastKeep.length, total: total }))
              .toggleClass('xa-zero', bad);
            $el.find('#xaRun').prop('disabled', bad);
        }

        /* O intervalo pedido, ou a mensagem do que está errado nele. */
        function dayRangeError(o) {
            if (!daily || (!o.dayFrom && !o.dayTo)) return '';
            var a = o.dayFrom || o.dayTo, b = o.dayTo || o.dayFrom;
            if (b < a) return t('daysBackwards');
            if (dayList(a, b).length > MAX_DAYS) return t('daysTooLong', { n: MAX_DAYS });
            return '';
        }

        /* Exporta o intervalo: lê um arquivo por dia, junta tudo numa tabela
           oculta e devolve a exportação ao MESMO caminho de sempre. */
        function runDaily(o) {
            var dias = dayList(o.dayFrom || o.dayTo, o.dayTo || o.dayFrom);
            var $c = $el.find('#xaCount');
            $el.find('#xaRun').prop('disabled', true);
            fetchDays(daily, dias, function (i, d) {
                $c.text(t('daysReading', { d: d, i: i, n: dias.length })).removeClass('xa-zero');
            }).then(function (res) {
                $el.find('#xaRun').prop('disabled', false);
                if (!res.rows.length) {
                    $c.text(res.failed.length ? t('daysFailed', { n: res.failed.length })
                                              : t('daysEmpty')).addClass('xa-zero');
                    return;
                }
                var tbl = buildDailyTable(res);
                // A tabela dos arquivos não tem checkbox nem Actions e ganha a
                // Reference Date na frente: o casamento com o que a pessoa
                // escolheu na tela é pelo RÓTULO, e a Reference Date entra
                // sempre — sem ela, um arquivo de vinte dias não diz de que dia
                // é cada linha.
                function toDaily(c) {
                    var i = res.columns.indexOf(c.label);
                    return i === -1 ? null : i;
                }
                var keep = pick(o, tbl, toDaily);
                if (!keep.length) {
                    $c.text(t('noRows')).addClass('xa-zero');
                    return;
                }
                var cols = [0].concat(o.colLabels.map(function (l) {
                    return res.columns.indexOf(l);
                }).filter(function (i) { return i > 0; }));
                run(tbl, jQuery.extend({}, o, { cols: cols }), keep);
                $c.text(t('count', { n: keep.length, total: res.rows.length }))
                  .removeClass('xa-zero');
                if (res.failed.length) {
                    $c.text($c.text() + ' · ' + t('daysFailed', { n: res.failed.length }));
                }
                bootstrap.Modal.getInstance(el).hide();
            }).catch(function () {
                $el.find('#xaRun').prop('disabled', false);
                $c.text(t('daysFailed', { n: dias.length })).addClass('xa-zero');
            });
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
               if (!o.cols.length || dayRangeError(o)) return;
               if (daily && (o.dayFrom || o.dayTo)) { runDaily(o); return; }
               if (!lastKeep.length) return;
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

    /* ══════ O intervalo de dias: os arquivos do cache ══════════════════════
       A tela mostra UM dia. Os arquivos-dia (`static/data/cache/…`) guardam a
       série, e quem sabe transformar o arquivo de um dia nas colunas da tela é
       o endpoint que a própria página consulta — por isso o intervalo o chama
       uma vez por dia, com a data no lugar da de hoje, em vez de reler os JSON
       por fora. Um leitor próprio seria uma segunda regra sobre os mesmos
       arquivos, e as duas discordariam no primeiro caso de borda.

       Página SEM arquivo-dia (Reference Data é cadastro: existe o de agora e
       nada mais) não declara `daily`, e a seção nasce desabilitada dizendo por
       quê. */
    var MAX_DAYS = 120;              // ~seis meses úteis; acima disso o navegador é o gargalo

    /* `daily` aceita a URL crua ou o objeto completo. `param` é o nome do
       parâmetro de data (as recons usam `recon_date`, o resto usa `date`) e
       `rows` a chave do payload (a Recon FXO devolve `data`). */
    function normDaily(d) {
        if (!d) return null;
        if (typeof d === 'string') d = { url: d };
        if (!d.url) return null;
        return { url: d.url, param: d.param || 'date',
                 rows: d.rows || 'rows', columns: d.columns || 'columns' };
    }

    function pad2(n) { return (n < 10 ? '0' : '') + n; }
    function ymd(dt) {
        return dt.getUTCFullYear() + '-' + pad2(dt.getUTCMonth() + 1) + '-' + pad2(dt.getUTCDate());
    }
    /* Os dias do intervalo, inclusive nas duas pontas. Vai dia a dia do
       CALENDÁRIO, e não só nos úteis: um feriado sem arquivo simplesmente não
       devolve linha, enquanto pular dia útil por engano esconderia o arquivo de
       um dia em que houve movimento. */
    function dayList(a, b) {
        var out = [];
        var cur = new Date(a + 'T00:00:00Z'), end = new Date(b + 'T00:00:00Z');
        if (isNaN(cur.getTime()) || isNaN(end.getTime())) return out;
        while (cur <= end && out.length <= MAX_DAYS) {
            out.push(ymd(cur));
            cur.setUTCDate(cur.getUTCDate() + 1);
        }
        return out;
    }

    /* Lê os dias EM SÉRIE, um pedido por vez. Em paralelo, um intervalo de três
       meses abriria noventa requisições de uma vez sobre o mesmo processo — que
       é único e serve a mesa inteira (o app roda com threads, não com workers).
       Dia sem arquivo devolve zero linha e não é erro: é dia sem movimento. */
    function fetchDays(daily, dias, onStep) {
        var columns = [], rows = [], failed = [], empty = [];
        var chain = Promise.resolve();
        dias.forEach(function (d, i) {
            chain = chain.then(function () {
                if (onStep) onStep(i + 1, d);
                var sep = daily.url.indexOf('?') === -1 ? '?' : '&';
                return fetch(daily.url + sep + daily.param + '=' + encodeURIComponent(d),
                             { credentials: 'same-origin' })
                    .then(function (r) { return r.ok ? r.json() : null; })
                    .then(function (j) {
                        if (!j || j.error) { failed.push(d); return; }
                        var cs = j[daily.columns] || [];
                        var rs = j[daily.rows] || [];
                        if (!columns.length && cs.length) {
                            // A Reference Date é a primeira coluna e é a razão de
                            // ser deste export: sem ela o arquivo de vinte dias
                            // não diz de que dia é cada linha.
                            columns = [t('refDate')].concat(cs.map(String));
                        }
                        if (!rs.length) { empty.push(d); return; }
                        rs.forEach(function (r) {
                            // A linha pode trazer uma cauda que a página usa
                            // (status, maker, id): o que entra é o tamanho do
                            // cabeçalho, senão as colunas saem deslocadas.
                            var arr = Array.isArray(r) ? r : cs.map(function (c) { return r[c]; });
                            var line = [d];
                            for (var k = 0; k < cs.length; k++) {
                                line.push(arr[k] == null ? '' : arr[k]);
                            }
                            rows.push(line);
                        });
                    })
                    .catch(function () { failed.push(d); });
            });
        });
        return chain.then(function () {
            return { columns: columns, rows: rows, failed: failed, empty: empty };
        });
    }

    /* Uma DataTable oculta com o resultado do intervalo. Ela existe para o
       export continuar sendo o MESMO: filtro, seleção de colunas e Buttons
       trabalham sobre uma DataTable, e montar um arquivo por fora daqui seria o
       segundo gerador que este arquivo inteiro existe para não ter. */
    function buildDailyTable(res) {
        var host = document.getElementById('xaDailyHost');
        if (!host) {
            host = document.createElement('div');
            host.id = 'xaDailyHost';
            host.style.cssText = 'position:absolute;left:-9999px;top:0;width:1px;height:1px;overflow:hidden';
            document.body.appendChild(host);
        }
        var old = jQuery('#xaDailyTable');
        if (old.length && jQuery.fn.dataTable.isDataTable(old)) old.DataTable().destroy();
        host.innerHTML = '<table id="xaDailyTable"><thead><tr>' +
            res.columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') +
            '</tr></thead><tbody></tbody></table>';
        return jQuery('#xaDailyTable').DataTable({
            data: res.rows, paging: false, searching: false, info: false,
            ordering: false, autoWidth: false, destroy: true
        });
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

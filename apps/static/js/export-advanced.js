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
                    + 'per BUSINESS day (ANBIMA) into a single file, and every row carries its '
                    + 'Reference Date. A day with no file is skipped.',
            daysNone: 'This page has no daily files — there is only the current registry, so the '
                    + 'export always covers what is on screen.',
            daysLoading: 'Loading the calendar…',
            daysReading: 'Reading {d}… ({i}/{n})',
            daysBuilding: 'Building the file with {n} rows… (this may take a while)',
            doneTitle: 'Export finished', doneTitleWarn: 'Export finished with gaps',
            doneRows: '{n} row(s) exported', ok: 'OK',
            exporting: 'Exporting…', failTitle: 'Nothing exported',
            stepTable: 'Assembling the table ({n} rows)…', stepFilter: 'Applying the filters…',
            stepFile: 'Building the file ({n} rows)… the tab may stop responding until it is done',
            daysFailed: 'Could not read {n} day(s)',
            daysNoFile: '{n} day(s) with no file',
            daysDone: '{n} rows from {d} day(s)',
            daysNoBiz: 'No business day in the range',
            daysWillRead: '{n} business day(s) will be read',
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
                    + 'por dia ÚTIL (ANBIMA) num arquivo só, e cada linha leva a Reference Date '
                    + 'dela. Dia sem arquivo é pulado.',
            daysNone: 'Esta tela não tem arquivo diário — é o cadastro de agora, então o export '
                    + 'cobre sempre o que está na tela.',
            daysLoading: 'Carregando o calendário…',
            daysReading: 'Lendo {d}… ({i}/{n})',
            daysBuilding: 'Montando o arquivo com {n} linhas… (pode demorar)',
            doneTitle: 'Exportação concluída', doneTitleWarn: 'Exportação concluída com falhas',
            doneRows: '{n} linha(s) exportada(s)', ok: 'OK',
            exporting: 'Exportando…', failTitle: 'Nada exportado',
            stepTable: 'Montando a tabela ({n} linhas)…', stepFilter: 'Aplicando os filtros…',
            stepFile: 'Gerando o arquivo ({n} linhas)… a aba pode ficar sem resposta até terminar',
            daysFailed: 'Não consegui ler {n} dia(s)',
            daysNoFile: '{n} dia(s) sem arquivo',
            daysDone: '{n} linhas de {d} dia(s)',
            daysNoBiz: 'Nenhum dia útil no intervalo',
            daysWillRead: '{n} dia(s) útil(eis) a ler',
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
                    + 'archivo por día HÁBIL (ANBIMA) en un solo archivo, y cada fila lleva su '
                    + 'Reference Date. El día sin archivo se salta.',
            daysNone: 'Esta pantalla no tiene archivo diario — es el registro de ahora, así que '
                    + 'la exportación cubre siempre lo que está en la pantalla.',
            daysLoading: 'Cargando el calendario…',
            daysReading: 'Leyendo {d}… ({i}/{n})',
            daysBuilding: 'Armando el archivo con {n} filas… (puede tardar)',
            doneTitle: 'Exportación finalizada', doneTitleWarn: 'Exportación finalizada con fallas',
            doneRows: '{n} fila(s) exportada(s)', ok: 'OK',
            exporting: 'Exportando…', failTitle: 'Nada exportado',
            stepTable: 'Armando la tabla ({n} filas)…', stepFilter: 'Aplicando los filtros…',
            stepFile: 'Generando el archivo ({n} filas)… la pestaña puede dejar de responder hasta terminar',
            daysFailed: 'No pude leer {n} día(s)',
            daysNoFile: '{n} día(s) sin archivo',
            daysDone: '{n} filas de {d} día(s)',
            daysNoBiz: 'Ningún día hábil en el intervalo',
            daysWillRead: '{n} día(s) hábil(es) a leer',
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
            + '#' + MODAL_ID + ' .xa-off .xa-help{font-style:italic}'
            // A roda do SweetAlert de exportação. `will-change` a promove a
            // camada própria, e aí quem gira a animação é o compositor: ela
            // continua girando enquanto a thread principal está presa
            // montando o arquivo. Só no popup da exportação — promover
            // camada em todo SweetAlert da página seria custo sem motivo.
            + '.xa-busy .swal2-loader{will-change:transform}';
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
                /* NUNCA `type="date"`: o campo nativo desenha no locale do
                   SISTEMA, e no Windows do JP isso é mm/dd/yyyy. A data do app
                   é dd/mm/yyyy em toda tela. O flatpickr vem do vendors.min.js
                   (global) e o `altInput` é o que dá as duas coisas: o campo
                   que se vê em dd/mm/yyyy e o `value` em ISO, que é o que o
                   endpoint do dia espera. */
                '<div class="row g-2">' +
                  '<div class="col-md-6"><label class="form-label">' + esc(t('from')) + '</label>' +
                    '<input type="text" class="form-control form-control-sm" id="xaDayFrom" ' +
                      'placeholder="dd/mm/aaaa" autocomplete="off"></div>' +
                  '<div class="col-md-6"><label class="form-label">' + esc(t('to')) + '</label>' +
                    '<input type="text" class="form-control form-control-sm" id="xaDayTo" ' +
                      'placeholder="dd/mm/aaaa" autocomplete="off"></div>' +
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
       nada que se mande por e-mail.

       Ele sai LEGÍVEL ("Live Position NDF"), e não em slug: o padrão do app é
       o do anexo do BACC (`EA Metrics - 20260824.xlsx`) — nome como se lê, um
       hífen, a data compacta —, e é esse nome que a mesa procura na pasta de
       downloads. O slug minúsculo com hífens era o nome do arquivo de código,
       não o do documento. A limpeza é a MESMA classe de caracteres que o
       DataTables aceita ao montar o nome, para o campo mostrar o nome que o
       arquivo vai ter de verdade. */
    function defaultName(node) {
        var h = document.querySelector('.page-title-head h4, .page-title-head h5');
        var s = h ? h.textContent : '';
        s = String(s || node.id || 'export').replace(/\s+/g, ' ').trim();
        // Colapsar de novo depois da limpeza: o que foi tirado do meio
        // (a barra de "Confirmations / Track") deixa dois espaços.
        return s.replace(/[^a-zA-Z0-9_\u00A1-\uFFFF., \-!()]/g, '')
                .replace(/\s+/g, ' ').trim() || 'export';
    }

    /* A extensão por formato. `print` e `copyHtml5` não produzem arquivo — e é
       por isso que eles não ganham nem nome nem aviso de fim: a janela de
       impressão e o balão do próprio Buttons já são a resposta deles. */
    var EXT = { excelHtml5: '.xlsx', csvHtml5: '.csv', pdfHtml5: '.pdf' };

    function pad2(n) { return (n < 10 ? '0' : '') + n; }
    /* Hoje pelo relógio LOCAL. O `ymd()` das datas do intervalo é UTC de
       propósito (ele lê data ISO), e usá-lo aqui carimbaria o dia seguinte em
       toda exportação feita depois das 21h no Brasil. */
    function todayIso() {
        var d = new Date();
        return d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());
    }
    function flatDay(iso) { return String(iso || '').replace(/-/g, ''); }

    /* O aviso de fim. O arquivo baixa fora da tela e nada dizia que o processo
       acabou — num intervalo grande a espera se lê como travamento. Guard no
       `Swal` porque este helper é opt-in: onde o SweetAlert não estiver
       carregado, o resumo do modal continua sendo a resposta, como antes. */
    /* Fecha o modal e SÓ ENTÃO avisa. Aberto em cima dele, os dois backdrops se
       somam, e o `hidden.bs.modal` do Bootstrap — que devolve o foco ao botão
       que abriu — rouba o foco do SweetAlert no meio da transição. */
    function hideThen(el, fn) {
        var m = (window.bootstrap && bootstrap.Modal.getInstance(el)) || null;
        if (!m || !el.classList.contains('show')) { fn(); return; }
        jQuery(el).one('hidden.bs.modal', fn);
        m.hide();
    }

    function doneAlert(icon, title, html) {
        if (!window.Swal) return false;
        // O popup do spinner é REAPROVEITADO: o `fire` em cima de um aberto
        // troca o conteúdo no lugar, sem piscar. O loader não sai sozinho —
        // sem isto a roda continuaria girando ao lado do ícone de sucesso.
        if (Swal.isVisible && Swal.isVisible()) Swal.hideLoading();
        Swal.fire({ title: title, html: html, icon: icon,
                    confirmButtonText: t('ok'), confirmButtonColor: '#0066cc' });
        return true;
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
        var baseName = opts.name || 'export';
        $el.find('#xaName').val(baseName);

        var colOpts = '<option value="">' + esc(t('colPick')) + '</option>' +
            cols.map(function (c) { return '<option value="' + c.idx + '">' + esc(c.label) + '</option>'; }).join('');

        // Sem arquivo diário a seção fica visível e DESABILITADA, com o motivo
        // escrito. Escondê-la faria a mesma tela parecer duas conforme a
        // página, e um campo que some sem explicação lê-se como defeito.
        var daily = normDaily(opts.daily);
        $el.find('#xaDayFrom,#xaDayTo').each(function () {
            // Limpar pelo flatpickr, e não pelo .val(''): o campo que se VÊ é o
            // altInput, e zerar só o original deixaria a data anterior na tela.
            if (this._flatpickr) this._flatpickr.clear(); else this.value = '';
            dateField(this);
            jQuery(this).prop('disabled', !daily);
            if (this._flatpickr && this._flatpickr.altInput) {
                this._flatpickr.altInput.disabled = !daily;
            }
        });
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
                dayFrom: isoDay($el.find('#xaDayFrom').val()),
                dayTo:   isoDay($el.find('#xaDayTo').val()),
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

        /* O nome final: o do campo mais a data, no padrão do app
           (`EA Metrics - 20260824.xlsx`). Com intervalo vão as DUAS pontas —
           é o que distingue uma extração de duas semanas da do dia. O carimbo
           só entra enquanto o campo está como nasceu: quem renomeou à mão
           quis aquele nome, e não aquele nome mais uma data.

           Sem intervalo a data é a de HOJE, a da extração, e não a do dado na
           tela: a data de referência da página não chega aqui (cada tela a
           guarda do seu jeito), e inventar uma seria carimbar de errado. */
        function finalName(o) {
            if (o.name !== baseName) return o.name;
            var a = o.dayFrom || o.dayTo, b = o.dayTo || o.dayFrom;
            if (daily && a) {
                return baseName + ' - ' + flatDay(a) +
                       (b && b !== a ? ' a ' + flatDay(b) : '');
            }
            return baseName + ' - ' + flatDay(todayIso());
        }

        /* A primeira linha do aviso é o NOME do arquivo que acabou de baixar —
           é o que a pessoa vai procurar na pasta de downloads. */
        function fileLine(o) {
            return EXT[o.format]
                ? '<div class="fw-semibold mb-1">' + esc(o.name + EXT[o.format]) + '</div>'
                : '';
        }

        /* Daqui para a frente é tudo SÍNCRONO — montar a tabela do intervalo,
           filtrar e gerar o arquivo — e a aba fica congelada enquanto dura.
           `busy` põe o spinner na frente ANTES de começar: fecha o modal, abre
           o SweetAlert já em "Exportando…" e só dispara o trabalho um QUADRO
           depois de o spinner ter PINTADO. Disparado antes, a tela congela com
           o spinner ainda invisível e a espera volta a se ler como travamento —
           que é o buraco entre o último "Reading" e o download.

           O `didOpen` do SweetAlert já roda com o popup na tela; o par de
           `requestAnimationFrame` em cima dele garante o quadro do próprio
           spinner. Sem SweetAlert na página sobra a linha do rodapé do modal,
           que é como era. */
        function busy(n) {
            return new Promise(function (resolve) {
                if (!window.Swal) {
                    $el.find('#xaCount').text(t('daysBuilding', { n: n })).removeClass('xa-zero');
                    setTimeout(resolve, 0);
                    return;
                }
                hideThen(el, function () {
                    Swal.fire({
                        title: t('exporting'),
                        html: esc(t('daysBuilding', { n: n })),
                        allowOutsideClick: false, allowEscapeKey: false,
                        showConfirmButton: false,
                        // SEM animação de entrada. A `swal2-show` vai de
                        // `opacity:0` a 1 em 0,3 s e o trabalho começa no quadro
                        // seguinte: a caixa congelava com ~5% de opacidade —
                        // aparecia e "sumia", deixando só o desfundo desfocado
                        // pelo tempo todo da geração. Sem animação, o primeiro
                        // quadro pintado já é o popup inteiro.
                        // O objeto SUBSTITUI o padrão (não se soma), então o
                        // `backdrop` repete a classe de sempre — é ela que
                        // carrega o escurecido e o blur do tema.
                        showClass: { popup: '', backdrop: 'swal2-backdrop-show', icon: '' },
                        customClass: { container: 'xa-busy' },
                        didOpen: function () { Swal.showLoading(); frame(resolve); }
                    });
                });
            });
        }

        /* Um QUADRO de folga. O `didOpen` roda com o popup no DOM, não com ele
           pintado: emendar o trabalho ali congela a aba com o spinner ainda a
           meio caminho de aparecer — que é o "apareceu e sumiu". O par de
           `requestAnimationFrame` só devolve depois de o navegador ter pintado
           uma vez. */
        function frame(fn) {
            if (window.requestAnimationFrame) {
                requestAnimationFrame(function () { requestAnimationFrame(fn); });
            } else { setTimeout(fn, 30); }
        }

        /* Uma etapa pesada: escreve o que vai fazer, deixa a tela pintar e só
           então faz. As três — montar a tabela do intervalo, filtrar e gerar o
           arquivo — são síncronas, e emendadas num bloco só congelam a aba do
           começo ao fim; separadas, o navegador repinta entre elas, o spinner
           volta a girar e o texto avança. De quebra, o texto que estiver na
           tela diz QUAL das três está demorando. */
        function step(msg, fn) {
            say(msg);
            return new Promise(function (resolve, reject) {
                frame(function () {
                    try { resolve(fn()); } catch (e) { reject(e); }
                });
            });
        }

        /* O texto da etapa vai DIRETO no nó do popup, e não por `Swal.update()`:
           o update re-renderiza a caixa e, sem botão nenhum, esconde as ações —
           que é onde o loader mora. O spinner sumiria a cada troca de texto. */
        function say(msg) {
            if (window.Swal && Swal.isVisible() && Swal.getHtmlContainer()) {
                Swal.getHtmlContainer().textContent = msg;
            } else {
                $el.find('#xaCount').text(msg).removeClass('xa-zero');
            }
        }

        /* O desfecho ruim depois de o spinner estar de pé: o SweetAlert aberto
           vira a mensagem, senão ele giraria para sempre. Sem SweetAlert
           continua sendo a linha do rodapé, com o modal aberto — que é onde a
           pessoa conserta o filtro. */
        function fail(msg) {
            $el.find('#xaCount').text(msg).addClass('xa-zero');
            doneAlert('warning', t('failTitle'), esc(msg));
        }

        /* O desfecho bom: o spinner vira o aviso de fim, no MESMO popup. Print
           e Copy não produzem arquivo e não têm o que anunciar — ali o spinner
           só se fecha. */
        function finish(falhou, o, resumo) {
            $el.find('#xaCount').text(resumo).toggleClass('xa-zero', falhou);
            var vaiAvisar = !!EXT[o.format] && !!window.Swal;
            var aviso = function () {
                if (!vaiAvisar) { if (window.Swal) Swal.close(); return; }
                doneAlert(falhou ? 'warning' : 'success',
                          t(falhou ? 'doneTitleWarn' : 'doneTitle'),
                          fileLine(o) + '<div>' + esc(resumo) + '</div>');
            };
            // Com o spinner, o modal já fechou no `busy` e o `hideThen` cai
            // direto no aviso. Sem SweetAlert vale a regra de antes: o modal
            // fica de pé quando algum dia ficou de fora, senão some com a única
            // tela que diz quantos dias entraram e o que faltou.
            if (vaiAvisar || !falhou) hideThen(el, aviso); else aviso();
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
                // Quantos dias ele VAI ler — a ajuda inteira não cabe no rodapé,
                // e este número é o que diz se o intervalo é o que se quis: 14
                // dias úteis onde o calendário tem 20.
                var n = dayList(o.dayFrom || o.dayTo, o.dayTo || o.dayFrom, true).length;
                $c.text(t('daysWillRead', { n: n })).toggleClass('xa-zero', !n);
                $el.find('#xaRun').prop('disabled', !n);
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
            var $c = $el.find('#xaCount');
            $el.find('#xaRun').prop('disabled', true);
            $c.text(t('daysLoading')).removeClass('xa-zero');
            // O calendário primeiro: sem ele o intervalo pediria sábado, domingo
            // e feriado — dias em que a rotina não roda e não há nada a ler.
            loadHolidays().then(function () {
                var dias = dayList(o.dayFrom || o.dayTo, o.dayTo || o.dayFrom, true);
                if (!dias.length) {
                    $el.find('#xaRun').prop('disabled', false);
                    $c.text(t('daysNoBiz')).addClass('xa-zero');
                    return null;
                }
                return fetchDays(daily, dias, function (i, d) {
                    $c.text(t('daysReading', { d: d, i: i, n: dias.length })).removeClass('xa-zero');
                });
            }).then(function (res) {
                if (!res) return;
                $el.find('#xaRun').prop('disabled', false);
                // O arquivo sai com o que VEIO. Antes, um dia que falhava
                // derrubava a exportação inteira — e num intervalo de vinte dias
                // basta um para perder os dezenove que estavam lá.
                if (!res.rows.length) {
                    $c.text(res.failed.length
                            ? t('daysFailed', { n: res.failed.length }) +
                              (res.why ? ' — ' + res.why : '')
                            : t('daysEmpty')).addClass('xa-zero');
                    return;
                }
                // O "Reading" acabou e começa a parte que congela a aba: o
                // spinner entra AQUI, no lugar dele, e as três etapas seguintes
                // vão uma por quadro.
                var tbl = null;
                busy(res.rows.length).then(function () {
                    return step(t('stepTable', { n: res.rows.length }), function () {
                        tbl = buildDailyTable(res);
                    });
                }).then(function () {
                    return step(t('stepFilter'), function () {
                        // A tabela dos arquivos não tem checkbox nem Actions e ganha
                        // a Reference Date na frente: o casamento com o que a pessoa
                        // escolheu na tela é pelo RÓTULO, e a Reference Date entra
                        // sempre — sem ela, um arquivo de vinte dias não diz de que
                        // dia é cada linha.
                        return pick(o, tbl, function (c) {
                            var i = res.columns.indexOf(c.label);
                            return i === -1 ? null : i;
                        });
                    });
                }).then(function (keep) {
                    if (!keep.length) { fail(t('noRows')); return; }
                    var cols = [0].concat(o.colLabels.map(function (l) {
                        return res.columns.indexOf(l);
                    }).filter(function (i) { return i > 0; }));
                    return step(t('stepFile', { n: keep.length }), function () {
                        run(tbl, jQuery.extend({}, o, { cols: cols }), keep);
                        var dias_ok = res.rows.length ? (new Set(res.rows.map(function (r) { return r[0]; }))).size : 0;
                        var resumo = t('daysDone', { n: keep.length, d: dias_ok });
                        if (res.empty.length) resumo += ' · ' + t('daysNoFile', { n: res.empty.length });
                        if (res.failed.length) {
                            resumo += ' · ' + t('daysFailed', { n: res.failed.length }) +
                                      (res.why ? ' (' + res.why + ')' : '');
                        }
                        finish(!!res.failed.length, o, resumo);
                    });
                }).catch(function (err) {
                    // A rede das três etapas. Fora da cadeia da leitura, um erro
                    // aqui não teria mais quem o pegue e o spinner giraria para
                    // sempre — a tela de travamento por outro motivo.
                    fail(t('daysFailed', { n: 0 }) +
                         ((err && err.message) ? ' — ' + err.message : ''));
                });
            }).catch(function (e) {
                $el.find('#xaRun').prop('disabled', false);
                $c.text(t('daysFailed', { n: 0 }) +
                        ((e && e.message) ? ' — ' + e.message : '')).addClass('xa-zero');
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
               o.name = finalName(o);
               if (daily && (o.dayFrom || o.dayTo)) { runDaily(o); return; }
               if (!lastKeep.length) return;
               // O mesmo spinner do intervalo: a tela do dia também pode ter
               // dezenas de milhares de linhas, e a montagem é a mesma.
               busy(lastKeep.length).then(function () {
                   return step(t('stepFile', { n: lastKeep.length }), function () {
                       run(dt, o, lastKeep);
                       finish(false, o, t('doneRows', { n: lastKeep.length }));
                   });
               }).catch(function (err) {
                   fail(t('daysFailed', { n: 0 }) +
                        ((err && err.message) ? ' — ' + err.message : ''));
               });
           });

        refresh();
        // O calendário chega depois do primeiro refresh: sem este segundo passe,
        // a contagem de dias úteis nasceria contando os feriados.
        if (daily) loadHolidays().then(refresh);
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
    // Teto por DIA. O intervalo é lido em série, então um dia que não responde
    // segurava a fila inteira — e a exportação ficava parada sem dizer nada.
    var DAY_TIMEOUT_MS = 60000;

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

    /* ══════ Campo de data — o PADRÃO do app ════════════════════════════════
       dd/mm/aaaa na tela, ISO no `value`. E é padrão mesmo: **nunca**
       `<input type="date">` visível, porque o campo nativo desenha no locale do
       SISTEMA — no Windows do JP isso é mm/dd/yyyy, e a mesa lê 03/04 como 3 de
       abril quando o campo quis dizer 4 de março. Um erro de data que não dá
       erro nenhum.

       O `altInput` do flatpickr é o que dá as duas coisas ao mesmo tempo: ele
       esconde o input original (que segue com o valor ISO, e por isso NENHUM
       código em volta muda) e desenha ao lado um campo em dd/mm/aaaa, que é o
       que se vê e o que se digita.

       Quem escreve no campo por código tem de avisar o picker
       (`el._flatpickr.setDate(v, false)`): o `value` do original muda, mas o
       campo VISÍVEL é o outro, e ele ficaria com a data anterior.

       O flatpickr vem no vendors.min.js (global), mas o guard existe pelo mesmo
       motivo do resto do app — uma página que carregue antes do vendor ficaria
       com o campo quebrado em vez de um texto comum, e digitar dd/mm/aaaa
       continua funcionando porque o `isoDay` normaliza as duas escritas.

       Exposto como `window.otcDateField` para as páginas que já carregam este
       arquivo (é o único helper de data do app; ver o comentário do padrão em
       `pages/index.html`). */
    function dateField(el, opts) {
        if (typeof el === 'string') el = document.querySelector(el);
        if (!el || el._flatpickr || typeof flatpickr === 'undefined') return null;
        return flatpickr(el, jQuery.extend({
            dateFormat: 'Y-m-d',       // o que fica no value — é o que a API espera
            altInput: true, altFormat: 'd/m/Y',
            altInputClass: el.className,
            allowInput: true, disableMobile: true
        }, opts || {}));
    }
    window.otcDateField = dateField;

    /* Refaz o texto visível dos campos de data de um trecho depois de alguém
       escrever no `value` por código. Sem isto, abrir o modal numa linha e
       depois noutra mostra a data da PRIMEIRA. */
    window.otcDateSync = function (root) {
        var scope = (typeof root === 'string') ? document.querySelector(root) : root;
        if (!scope) return;
        Array.prototype.forEach.call(scope.querySelectorAll('input'), function (el) {
            if (el._flatpickr) el._flatpickr.setDate(el.value || '', false);
        });
    };

    /* O que a pessoa digitou/escolheu, em ISO. Aceita as duas escritas porque o
       campo é editável: com o flatpickr o `value` já vem `Y-m-d`, e sem ele (ou
       digitando à mão) chega `dd/mm/aaaa`. */
    function isoDay(v) {
        var s = String(v == null ? '' : v).trim();
        if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
        var m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s);
        if (!m) return '';
        return m[3] + '-' + (m[2].length === 1 ? '0' : '') + m[2] +
                     '-' + (m[1].length === 1 ? '0' : '') + m[1];
    }

    function ymd(dt) {
        return dt.getUTCFullYear() + '-' + pad2(dt.getUTCMonth() + 1) + '-' + pad2(dt.getUTCDate());
    }
    /* ── Dias ÚTEIS ────────────────────────────────────────────────────────
       Os arquivos-dia nascem de rotinas que rodam em dia útil, então pedir
       sábado, domingo e feriado é pedir vinte vezes o que não existe — e era
       isso que enchia a lista de "não consegui ler" com dias em que não havia
       nada a ler. O calendário é o ANBIMA (`static/data/anbima.json`), o mesmo
       que o resto do app usa; ele é carregado UMA vez e fica em memória.

       Sem o arquivo (fetch que falha), sobra o fim de semana: é a parte da
       regra que não depende de cadastro nenhum, e é melhor pedir um feriado a
       mais do que pular um dia útil em que houve movimento. */
    var _holidays = null, _holidayLoad = null;
    function loadHolidays() {
        if (_holidayLoad) return _holidayLoad;
        _holidayLoad = fetch('/static/data/anbima.json', { credentials: 'same-origin' })
            .then(function (r) { return r.ok ? r.json() : []; })
            .then(function (list) {
                _holidays = {};
                (list || []).forEach(function (h) {
                    var d = String((h && h.date) || h || '').slice(0, 10);
                    if (d) _holidays[d] = 1;
                });
                return _holidays;
            })
            .catch(function () { _holidays = {}; return _holidays; });
        return _holidayLoad;
    }
    function isBizDay(d) {
        var dow = new Date(d + 'T00:00:00Z').getUTCDay();
        if (dow === 0 || dow === 6) return false;
        return !(_holidays && _holidays[d]);
    }

    /* Os dias do intervalo, inclusive nas duas pontas. `onlyBiz` filtra pelo
       calendário; o teto conta os dias do CALENDÁRIO, para o limite não mudar
       conforme o mês tem mais ou menos feriado. */
    function dayList(a, b, onlyBiz) {
        var out = [];
        var cur = new Date(a + 'T00:00:00Z'), end = new Date(b + 'T00:00:00Z');
        if (isNaN(cur.getTime()) || isNaN(end.getTime())) return out;
        var span = 0;
        while (cur <= end && span <= MAX_DAYS) {
            var d = ymd(cur);
            if (!onlyBiz || isBizDay(d)) out.push(d);
            span++;
            cur.setUTCDate(cur.getUTCDate() + 1);
        }
        return out;
    }

    /* Lê os dias EM SÉRIE, um pedido por vez. Em paralelo, um intervalo de três
       meses abriria noventa requisições de uma vez sobre o mesmo processo — que
       é único e serve a mesa inteira (o app roda com threads, não com workers).
       Dia sem arquivo devolve zero linha e não é erro: é dia sem movimento. */
    function fetchDays(daily, dias, onStep) {
        var columns = [], rows = [], failed = [], empty = [], why = {};
        var chain = Promise.resolve();
        dias.forEach(function (d, i) {
            chain = chain.then(function () {
                if (onStep) onStep(i + 1, d);
                var sep = daily.url.indexOf('?') === -1 ? '?' : '&';
                // `exact=1`: o dia pedido ou nada. Sem ele, as telas de posição
                // andam para trás até achar arquivo — e um intervalo sairia com
                // o MESMO dia repetido sob datas diferentes. Endpoint que não
                // conhece o parâmetro simplesmente o ignora.
                var url = daily.url + sep + daily.param + '=' + encodeURIComponent(d) + '&exact=1';
                // Um dia que não responde não pode segurar os outros dezenove: o
                // pedido é abortado e o dia entra como falha. Era isso que
                // travava a exportação inteira no último dia do intervalo.
                var ctrl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
                var timer = setTimeout(function () { if (ctrl) ctrl.abort(); }, DAY_TIMEOUT_MS);
                var opts = { credentials: 'same-origin' };
                if (ctrl) opts.signal = ctrl.signal;
                return fetch(url, opts)
                    .then(function (r) {
                        clearTimeout(timer);
                        // O MOTIVO acompanha a falha. "Não consegui ler 20 dias"
                        // não diz se foi rota errada, sessão vencida ou erro do
                        // servidor — e sem isso não há o que investigar.
                        if (!r.ok) {
                            why['HTTP ' + r.status] = (why['HTTP ' + r.status] || 0) + 1;
                            failed.push(d);
                            return null;
                        }
                        return r.json().catch(function () {
                            // 200 com corpo que não é JSON é a assinatura do
                            // redirecionamento para o login: o pedido "deu
                            // certo" e voltou uma página HTML.
                            why['resposta não-JSON'] = (why['resposta não-JSON'] || 0) + 1;
                            failed.push(d);
                            return null;
                        });
                    })
                    .then(function (j) {
                        if (!j) return;
                        if (j.error) {
                            why[String(j.error).slice(0, 60)] =
                                (why[String(j.error).slice(0, 60)] || 0) + 1;
                            failed.push(d);
                            return;
                        }
                        var cs = j[daily.columns] || [];
                        var rs = j[daily.rows] || [];
                        if (!columns.length && cs.length) {
                            // A Reference Date é a primeira coluna e é a razão de
                            // ser deste export: sem ela o arquivo de vinte dias
                            // não diz de que dia é cada linha.
                            columns = [t('refDate')].concat(cs.map(String));
                        }
                        // O dia que a resposta diz ter lido. Quando ele não é o
                        // pedido, a tela substituiu o arquivo pelo do dia
                        // anterior (é o que ela faz para não abrir vazia) — e
                        // aqui isso é o MESMO dia entrando duas vezes, com duas
                        // datas. O dia é pulado como se não houvesse arquivo,
                        // que é o que de fato não há.
                        var src = String(j.source_date || '').slice(0, 10);
                        if (src && src !== d) { empty.push(d); return; }
                        // Dia que respondeu e não tem linha é dia SEM ARQUIVO, não
                        // é falha: com o intervalo em dias úteis ele é o feriado
                        // que a rotina não rodou, ou o dia anterior à primeira
                        // gravação. Contar isso como erro fazia o export inteiro
                        // morrer por causa do que não existe.
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
                    .catch(function (e) {
                        why[(e && e.message) ? String(e.message).slice(0, 60) : 'erro de rede'] = 1;
                        failed.push(d);
                    });
            });
        });
        return chain.then(function () {
            return { columns: columns, rows: rows, failed: failed, empty: empty,
                     why: Object.keys(why).join(' · ') };
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
        // `paging: false` desenhava TODAS as linhas do intervalo no DOM — dez
        // dias de Live Position são dezenas de milhares de linhas por cinquenta
        // colunas, e a aba congelava antes de chegar ao arquivo (era o
        // "Page Unresponsive" que nunca terminava). O export não lê o DOM:
        // `pick()` e o Buttons trabalham pela API (`cell().render()`,
        // `rows({page:'all'})`), que responde pelo dado em memória. Então a
        // tabela pagina em UMA linha: o dado está todo aqui, o desenho não.
        return jQuery('#xaDailyTable').DataTable({
            data: res.rows, searching: false, info: false, ordering: false,
            autoWidth: false, destroy: true,
            paging: true, pageLength: 1, lengthChange: false, deferRender: true
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

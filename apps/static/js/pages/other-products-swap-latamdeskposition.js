/**
 * Other Products › Latam Desk Position
 * Importa o FbiRptLatamDeskPostion-NY-* (server-side, no lugar da macro VBA) e
 * mostra as linhas filtradas em uma tabela larga com widgets, filtro por coluna,
 * Columns e Export.
 *
 * O relatório NÃO é diário. O campo de data nasce em HOJE, mas os dados vêm
 * sempre do ÚLTIMO arquivo disponível: a página chama /data SEM data e o servidor
 * escolhe. A data real da posição aparece ao lado do campo ("Dados de dd/mm/yyyy").
 * Escolher uma data no calendário passa a pedir aquele dia exato.
 */
(function () {
  'use strict';

  // ':gt(1)' NÃO serve aqui: o thead tem duas linhas (títulos + filtros), o jQuery
  // enumera 2×N <th> e os das colunas 0/1 da segunda linha caem em posição > 1,
  // devolvendo checkbox e Actions para a exportação. Índice de COLUNA, então.
  function exportFromData(idx) { return idx > 1; }

  var BASE = '/api/other-products-swap-latamdeskposition';
  var page = document.getElementById('ldp-page');
  if (!page) return;

  var dt = null;
  var COLS = [];               // colunas de dados atuais (para o modal Add/Edit)
  var CURRENT_ROWS = [];       // últimas linhas carregadas ([...dados, status, maker, checker, id])
  var EDIT_ID = null;          // id da linha em edição (null → modo Add)
  var LOADED_DATE = null;      // data efetivamente carregada (YYYY-MM-DD)
  var AVAILABLE = [];          // datas que têm arquivo, mais nova primeiro
  var PICKER = null;           // instância do calendário (flatpickr ou daterangepicker)

  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter…', ok: 'OK', pending: 'Pending', newst: 'New', importing: 'Importing…',
          noFile: 'No FbiRptLatamDeskPostion-NY-* file found in the Settlements folder.',
          ignored: 'Other reports in the folder (not read)', imported: 'Imported', rows: 'row(s)', updated: 'Updated', latest: 'latest available',
          noData: 'No data for this date', lastAvailable: 'Last available',
          dataFrom: 'Data from', loadErr: 'Could not load the data',
          need404: 'API not found (HTTP 404) — the server still runs the old routes.py: restart Flask after the pull.',
          edit: 'Edit', del: 'Delete', confirm: 'Confirm', addTitle: 'Add row', editTitle: 'Edit row',
          delTitle: 'Delete row?', delText: 'This row will be removed and the change saved.', yes: 'Yes, delete',
          cancel: 'Cancel', saved: 'Saved', deleted: 'Deleted', confirmed: 'Confirmed',
          missing: 'Columns not found in the file header', filtered: 'filtered out',
          read: 'read', cols: 'header columns', consumed: 'source file deleted',
          sameUser: 'A different user must confirm a row you changed.', err: 'Action failed.' },
    br: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendente', newst: 'Novo', importing: 'Importando…',
          noFile: 'Nenhum arquivo FbiRptLatamDeskPostion-NY-* na pasta Settlements.',
          ignored: 'Outros relatórios na pasta (não lidos)', imported: 'Importado', rows: 'linha(s)', updated: 'Atualizado', latest: 'último disponível',
          noData: 'Sem dados nesta data', lastAvailable: 'Último disponível',
          dataFrom: 'Dados de', loadErr: 'Não foi possível carregar os dados',
          need404: 'API não encontrada (HTTP 404) — o servidor ainda está com o routes.py antigo: reinicie o Flask depois do pull.',
          edit: 'Editar', del: 'Excluir', confirm: 'Confirmar', addTitle: 'Adicionar linha', editTitle: 'Editar linha',
          delTitle: 'Excluir linha?', delText: 'A linha será removida e a alteração salva.', yes: 'Sim, excluir',
          cancel: 'Cancelar', saved: 'Salvo', deleted: 'Excluído', confirmed: 'Confirmado',
          missing: 'Colunas não encontradas no header do arquivo', filtered: 'filtradas',
          read: 'lidas', cols: 'colunas no header', consumed: 'arquivo de origem apagado',
          sameUser: 'Outro usuário precisa confirmar uma linha que você alterou.', err: 'Falha na ação.' },
    es: { filterPh: 'Filtrar…', ok: 'OK', pending: 'Pendiente', newst: 'Nuevo', importing: 'Importando…',
          noFile: 'Ningún archivo FbiRptLatamDeskPostion-NY-* en la carpeta Settlements.',
          ignored: 'Otros informes en la carpeta (no leídos)', imported: 'Importado', rows: 'fila(s)', updated: 'Actualizado', latest: 'último disponible',
          noData: 'Sin datos en esta fecha', lastAvailable: 'Último disponible',
          dataFrom: 'Datos de', loadErr: 'No se pudieron cargar los datos',
          need404: 'API no encontrada (HTTP 404) — el servidor sigue con el routes.py anterior: reinicie Flask tras el pull.',
          edit: 'Editar', del: 'Eliminar', confirm: 'Confirmar', addTitle: 'Agregar fila', editTitle: 'Editar fila',
          delTitle: '¿Eliminar fila?', delText: 'La fila será eliminada y el cambio guardado.', yes: 'Sí, eliminar',
          cancel: 'Cancelar', saved: 'Guardado', deleted: 'Eliminado', confirmed: 'Confirmado',
          missing: 'Columnas no encontradas en el encabezado', filtered: 'filtradas',
          read: 'leídas', cols: 'columnas del encabezado', consumed: 'archivo de origen eliminado',
          sameUser: 'Otro usuario debe confirmar una fila que usted cambió.', err: 'Acción fallida.' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }
  function toDMY(iso) {
    var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? (m[3] + '/' + m[2] + '/' + m[1]) : '';
  }
  function toISO(dmy) {
    var m = String(dmy || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : '';
  }
  // Casas decimais fixas por coluna do relatório. O arquivo entrega o número
  // como o extrator gravou ('5.4321', '5.432100000000001', '281808'), então o
  // formato é decidido AQUI, na exibição — o JSON continua guardando o valor
  // cru (é ele que volta no modal de Edit e no que a linha grava de novo).
  var _LDP_DP = { 'FX Rate': 8, 'Strike': 8, 'TOTAL_PREMIUM': 2 };

  // Número em qualquer convenção que o relatório possa usar. Um `replace(/,/g,'')`
  // seco (o atalho comum) transformaria '5,4321' em 54321 — em coluna de FX é
  // erro de 4 ordens de grandeza, então cada formato é reconhecido pelo padrão.
  function toNumber(v) {
    var s = String(v == null ? '' : v).trim().replace(/\s| /g, '');
    if (!s) return NaN;
    var neg = /^\(.*\)$/.test(s);                       // (1,234.56) → negativo
    if (neg) s = s.slice(1, -1);
    if (/^[-+]?\d{1,3}(,\d{3})+(\.\d+)?$/.test(s)) s = s.replace(/,/g, '');            // 1,234.56
    else if (/^[-+]?\d{1,3}(\.\d{3})+(,\d+)?$/.test(s)) s = s.replace(/\./g, '').replace(',', '.'); // 1.234,56
    else if (/^[-+]?\d+,\d+$/.test(s)) s = s.replace(',', '.');                        // 5,4321
    if (!/^[-+]?\d*\.?\d+([eE][-+]?\d+)?$/.test(s)) return NaN;
    var n = Number(s);
    return isNaN(n) ? NaN : (neg ? -n : n);
  }

  // #,##0.00000000 (dp=8) e #,##0.00 (dp=2). Célula vazia continua vazia e o que
  // não for número sai como veio — a coluna pode trazer um texto ('N/A').
  function fmtNum(v, dp) {
    if (v == null || String(v).trim() === '') return '';
    var n = toNumber(v);
    if (isNaN(n)) return String(v);
    return n.toLocaleString('en-US', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  // O flatpickr só aceita string em defaultDate/setDate se ela estiver no
  // `dateFormat` configurado (aqui d/m/Y) ou terminar em Z/GMT — um ISO
  // '2026-07-30' ele tenta ler como dia 20, falha e LIMPA o campo. Date resolve.
  function isoToDate(iso) {
    var m = String(iso || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }

  // dateStr null/undefined → pede o ÚLTIMO arquivo disponível (o relatório não é diário).
  function load(dateStr) {
    var info = document.getElementById('ldp-import-info');
    fetch(BASE + '/data' + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : ''),
          { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (d) {
        if (!d || !d.success) throw new Error((d && d.error) || 'resposta sem success');
        var w = d.widgets || {};
        setVal('ldp-w-calls', w.calls || 0); setVal('ldp-w-puts', w.puts || 0);
        setVal('ldp-w-cptys', w.counterparties || 0); setVal('ldp-w-total', w.total || 0);
        LOADED_DATE = d.date || null;
        AVAILABLE = d.dates || [];
        // Nota do cabeçalho: DE QUE DATA são os dados (o campo fica em hoje, mas a
        // posição pode ser de outro dia), hora do import e arquivo de origem.
        var note = [];
        if (d.date) note.push(t('dataFrom') + ' ' + toDMY(d.date));
        if (d.updated) note.push(t('updated') + ' ' + d.updated);
        if (d.file) note.push(d.file);
        setVal('ldp-updated', note.join(' · '));
        buildTable(d.columns || [], d.rows || []);
        if (info) {
          info.classList.remove('text-danger');
          info.textContent = (d.rows || []).length ? ''
            : t('noData') + (AVAILABLE.length ? ' · ' + t('lastAvailable') + ': ' + toDMY(AVAILABLE[0]) : '');
        }
      })
      .catch(function (e) {
        // Falha silenciosa aqui significa "página vazia sem explicação" — mostra o erro.
        if (window.console && console.error) console.error('[latam-desk-position] load falhou:', e);
        // 404 = a rota da API não existe no servidor. Como o Flask do time roda com
        // o reloader desligado, isso é quase sempre "deu pull e não reiniciou": o
        // template novo já é servido (Jinja recarrega sozinho) mas o routes.py em
        // memória ainda é o antigo, sem o endpoint.
        var msg = e.message === 'HTTP 404' ? t('need404') : (t('loadErr') + ' (' + e.message + ')');
        if (info) { info.classList.add('text-danger'); info.textContent = msg; }
      });
  }

  // Status badge padrão do projeto: OK=success, Pending=warning, New=info.
  function statusBadge(status) {
    var s = String(status || 'OK').toLowerCase();
    if (s === 'pending') return '<span class="badge text-bg-warning bg-gradient">' + esc(t('pending')) + '</span>';
    if (s === 'new')     return '<span class="badge bg-info text-white bg-gradient">' + esc(t('newst')) + '</span>';
    return '<span class="badge text-bg-success bg-gradient">' + esc(t('ok')) + '</span>';
  }

  function metaOf(r) {
    var n = COLS.length;
    return { status: r[n], maker: r[n + 1], checker: r[n + 2], id: r[n + 3] };
  }

  function actionsHtml(id) {
    return '<div class="d-inline-flex gap-1">' +
      '<button class="btn btn-info btn-sm rounded-circle btn-row-edit" data-id="' + esc(id) + '" title="' + esc(t('edit')) + '"><i class="ti ti-pencil"></i></button>' +
      '<button class="btn btn-success btn-sm rounded-circle btn-row-confirm" data-id="' + esc(id) + '" title="' + esc(t('confirm')) + '"><i class="ti ti-check"></i></button>' +
      '<button class="btn btn-danger btn-sm rounded-circle btn-row-delete" data-id="' + esc(id) + '" title="' + esc(t('del')) + '"><i class="ti ti-trash"></i></button>' +
      '</div>';
  }

  function buildTable(columns, rows) {
    COLS = columns;
    CURRENT_ROWS = rows;
    var titleRow =
      '<tr id="ldp-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="ldpCheckAll" class="form-check-input"></th>' +
      '<th data-lang="ldp-actions">Actions</th>' +
      '<th data-lang="ldp-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="ldp-th-filter">' +
      '<th></th><th></th>' +
      '<th><input type="text" class="form-control form-control-sm ldp-col-filter" data-col="2" placeholder="Status" autocomplete="off"></th>' +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm ldp-col-filter" data-col="' +
          (i + 3) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#ldp-table thead').innerHTML = titleRow + filterRow;

    // Casas decimais por POSIÇÃO, resolvidas uma vez: o mapa é por nome de coluna
    // e as colunas vêm do servidor, então uma coluna a mais no relatório não
    // desloca o formato para a vizinha.
    var dps = columns.map(function (c) { return _LDP_DP[c]; });
    var data = rows.map(function (r) {
      var m = metaOf(r);
      return ['<input type="checkbox" class="form-check-input ldp-row-check">', actionsHtml(m.id), statusBadge(m.status)]
        .concat(r.slice(0, COLS.length).map(function (v, i) {
          return esc(dps[i] === undefined ? v : fmtNum(v, dps[i]));
        }));
    });

    if (dt) { dt.destroy(); }
    // Ordenação padrão: Counterparty A→Z e, dentro da contraparte, Deal_ID A→Z.
    // Índices pelo nome (+3 pelas colunas fixas checkbox/actions/status).
    var iCpty = columns.indexOf('Counterparty');
    var iDeal = columns.indexOf('Deal_ID');
    var defaultOrder = [];
    if (iCpty >= 0) defaultOrder.push([iCpty + 3, 'asc']);
    if (iDeal >= 0) defaultOrder.push([iDeal + 3, 'asc']);
    dt = jQuery('#ldp-table').DataTable({
      data: data,
      columns: [{}, {}, {}].concat(columns.map(function () { return {}; })),
      columnDefs: [
        { orderable: false, className: 'text-center', targets: 0 },
        { orderable: false, searchable: false, className: 'text-center', targets: 1 },
      ],
      // Sem scrollX: uma tabela só → header e corpo nunca desalinham; .table-responsive rola.
      scrollX: false, autoWidth: false, orderCellsTop: true, deferRender: true,
      pageLength: 200, order: defaultOrder,
      dom: "<'row'<'col-sm-12'tr>><'d-md-flex justify-content-between align-items-center mt-2'ip>",
      buttons: [{
        extend: 'collection',
        text: '<i class="ti ti-download me-1"></i> Export',
        className: 'btn btn-sm btn-info bg-gradient dropdown-toggle', autoClose: true,
        buttons: [
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
        ],
      }],
    });

    // Seleção de célula + Ctrl+C — o padrão do New Deals para qualquer tabela
    // (static/js/table-std.js). Fora da seleção: checkbox e Actions. O helper é
    // idempotente e delega no nó da tabela, então sobrevive aos redraws e ao
    // rebuild que este `buildTable` faz a cada carga.
    if (window.otcCellCopy) otcCellCopy('#ldp-table', { skip: [0, 1] });

    var expWrap = document.querySelector('.ldpExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    jQuery('#ldp-table thead').off('keyup.ldpcol change.ldpcol')
      .on('keyup.ldpcol change.ldpcol', '.ldp-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('ldp-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('ldp-count', rows.length);
    buildColumnsToggle();
    var sel = document.querySelector('.ldp-page-len');   // sincroniza "Show entries"
    if (sel) sel.value = String(dt.page.len());
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    var checkAll = document.getElementById('ldpCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#ldp-table tbody .ldp-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(2).map(function (th, index) {
      var label = th.textContent.trim() || 'Status';
      return '<li class="px-3 py-1"><div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + 2) + '" id="ldpCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="ldpCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="ldpColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('ldpColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  function wireClear() {
    var clr = document.getElementById('ldpClearFilters');
    if (clr) clr.addEventListener('click', function () {
      document.querySelectorAll('#ldp-table .ldp-col-filter').forEach(function (i) { i.value = ''; i.classList.remove('ldp-has-val'); });
      if (dt) { dt.columns().every(function () { this.search(''); }); dt.draw(); }
    });
  }

  // Data carregada (não a de hoje): é ela que as ações de linha precisam usar.
  function currentDate() {
    if (LOADED_DATE) return LOADED_DATE;
    var inp = document.getElementById('ldp-date');
    var m = (inp && inp.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
    return m ? (m[3] + '-' + m[2] + '-' + m[1]) : page.getAttribute('data-ref');
  }

  function setDateField(iso) {
    var inp = document.getElementById('ldp-date');
    if (!inp || !iso) return;
    try {
      if (PICKER && PICKER.setDate) PICKER.setDate(isoToDate(iso) || iso, false);  // flatpickr
      else if (PICKER && PICKER.setStartDate) PICKER.setStartDate(moment(iso, 'YYYY-MM-DD'));
    } catch (e) {}
    if (!inp.value) inp.value = toDMY(iso);      // sem calendário, ou se ele limpou
  }

  function openPicker() {
    try {
      if (PICKER && PICKER.open) { PICKER.open(); return; }                        // flatpickr
      if (window.jQuery) jQuery('#ldp-date').trigger('click');                     // daterangepicker
    } catch (e) {}
  }

  function wireImport() {
    var btn = document.getElementById('ldpImportBtn');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var info = document.getElementById('ldp-import-info');
      btn.disabled = true; if (info) info.textContent = t('importing');
      // Sem 'date' no corpo: o import grava na data de HOJE (o dia em que o
      // arquivo foi processado) e a página passa a mostrar esse arquivo.
      fetch(BASE + '/import', { method: 'POST', credentials: 'same-origin',
                                headers: { 'Content-Type': 'application/json' }, body: '{}' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          btn.disabled = false;
          if (d && d.success) {
            // Detalhamento sempre visível: sem ele, "0 linhas" não diz se o
            // arquivo veio vazio, se o filtro 62/63 descartou tudo ou se o
            // delimitador estava errado (header com 1 coluna).
            var txt = t('imported') + ': ' + d.rows + ' ' + t('rows') + ' · ' +
                      (d.read || 0) + ' ' + t('read') + ' · ' + (d.filtered || 0) + ' ' +
                      t('filtered') + ' · ' + (d.header_cols || 0) + ' ' + t('cols') +
                      ' · ' + (d.format || '?') + ' · ' + d.file +
                      (d.deleted ? ' · ' + t('consumed') : '');
            if (info) { info.classList.remove('text-danger'); info.textContent = txt; }
            load(d.date);
            if (window.Swal) {
              var warn = !d.rows || (d.missing && d.missing.length) || (d.ignored && d.ignored.length);
              var html = d.rows + ' ' + t('rows') + '<br><small>' + esc(d.read || 0) + ' ' + t('read') +
                         ' · ' + esc(d.filtered || 0) + ' ' + t('filtered') +
                         ' · ' + esc(d.header_cols || 0) + ' ' + t('cols') +
                         ' · ' + esc(d.format || '?') + '</small>' +
                         '<br><small>' + esc(d.file) +
                         (d.deleted ? ' — ' + esc(t('consumed')) : '') + '</small>';
              if (d.missing && d.missing.length) {
                html += '<br><br><small class="text-warning">' + esc(t('missing')) + ':<br>' +
                        esc(d.missing.join(', ')) + '</small>';
              }
              // Pasta com mais de um relatorio: foi lido o MAIS RECENTE, e os
              // outros ficaram onde estavam. Dizer qual sobrou e o que separa
              // "importei o arquivo certo" de "importei o de manha de novo".
              if (d.ignored && d.ignored.length) {
                html += '<br><br><small class="text-warning">' + esc(t('ignored')) + ':<br>' +
                        esc(d.ignored.join(', ')) + '</small>';
              }
              Swal.fire({ icon: warn ? 'warning' : 'success', title: t('imported'), html: html,
                          timer: warn ? undefined : 2200, showConfirmButton: !!warn });
            }
          } else {
            var msg = (d && d.error) || t('noFile');
            if (info) info.textContent = msg;
            if (window.Swal) Swal.fire({ icon: 'warning', title: 'Latam Desk Position', text: msg });
          }
          if (window.fetchNotifications) window.fetchNotifications();
        })
        .catch(function () { btn.disabled = false; });
    });
  }

  // O campo NASCE em hoje (dd/mm/yyyy) de forma síncrona, antes de qualquer
  // plugin: se o calendário falhar em carregar, o usuário ainda vê a data certa
  // em vez do placeholder. Os DADOS continuam vindo do último arquivo disponível
  // (load(null) no boot) — a data do arquivo aparece ao lado, em "Dados de …".
  function wireDatePicker() {
    var inp = document.getElementById('ldp-date');
    if (!inp) return;
    var today = page.getAttribute('data-today');
    inp.value = toDMY(today);

    function pick(iso) { if (iso && iso !== LOADED_DATE) load(iso); }

    // 1) flatpickr — já vem no vendors.js do projeto, sem depender dos plugins da página.
    if (window.flatpickr) {
      PICKER = flatpickr(inp, {
        dateFormat: 'd/m/Y', defaultDate: isoToDate(today) || undefined, allowInput: false,
        onChange: function (_sel, str) { pick(toISO(str)); },
      });
      if (!inp.value) inp.value = toDMY(today);   // garante hoje mesmo se o plugin limpar
    // 2) daterangepicker (mesmo componente das outras páginas de settlement).
    } else if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#ldp-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: today ? moment(today, 'YYYY-MM-DD') : moment(),
      }, function (start) { pick(start.format('YYYY-MM-DD')); });
      PICKER = $d.data('daterangepicker');
    // 3) Sem calendário: campo digitável em dd/mm/yyyy (nunca um campo morto).
    } else {
      inp.removeAttribute('readonly');
      inp.addEventListener('change', function () { pick(toISO(this.value)); });
    }
    // O ícone e o próprio campo abrem o calendário.
    var cal = document.querySelector('#ldpDateWrap .ldp-cal-btn');
    if (cal) cal.addEventListener('click', openPicker);
    if (PICKER) inp.addEventListener('click', openPicker);
  }

  function wirePageLen() {
    var sel = document.querySelector('.ldp-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  function postJSON(url, body) {
    return fetch(url, { method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, body: j }; }); });
  }

  // Modal glass do New Deals: um campo por coluna. editId=null → Add; senão Edit.
  function openModal(editId, prefillCells) {
    EDIT_ID = editId || null;
    var title = document.getElementById('ldpModalTitle');
    if (title) title.textContent = EDIT_ID ? t('editTitle') : t('addTitle');
    document.getElementById('ldpAddFields').innerHTML = COLS.map(function (c, i) {
      var val = (prefillCells && prefillCells[i] != null) ? prefillCells[i] : '';
      return '<div class="col-md-3"><label class="form-label fs-xs text-muted mb-1">' + esc(c) + '</label>' +
        '<input type="text" class="form-control form-control-sm ldp-add-fld" data-i="' + i + '" value="' + esc(val) + '"></div>';
    }).join('');
    if (window.bootstrap) bootstrap.Modal.getOrCreateInstance(document.getElementById('ldpAddModal')).show();
  }

  function afterMutation(titleKey) {
    if (window.bootstrap) {
      var inst = bootstrap.Modal.getInstance(document.getElementById('ldpAddModal'));
      if (inst) inst.hide();
    }
    load(currentDate());
    if (window.fetchNotifications) window.fetchNotifications();
    if (window.Swal) Swal.fire({ icon: 'success', title: t(titleKey), timer: 1200, showConfirmButton: false });
  }

  function wireAddRow() {
    var btn = document.getElementById('ldpAddBtn');
    if (btn) btn.addEventListener('click', function () { openModal(null, null); });
    var save = document.getElementById('ldpAddSave');
    if (save) save.addEventListener('click', function () {
      var cells = [];
      document.querySelectorAll('#ldpAddFields .ldp-add-fld').forEach(function (f) { cells[+f.getAttribute('data-i')] = f.value; });
      var url = BASE + (EDIT_ID ? '/row/edit' : '/row/add');
      var body = { date: currentDate(), cells: cells };
      if (EDIT_ID) body.id = EDIT_ID;
      save.disabled = true;
      postJSON(url, body).then(function (res) {
        save.disabled = false;
        if (res.ok && res.body && res.body.success) { afterMutation('saved'); }
        else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Latam Desk Position', text: (res.body && res.body.message) || t('err') }); }
      }).catch(function () { save.disabled = false; });
    });
  }

  // Edit / Confirm / Delete (delegado — sobrevive aos redraws do DataTables).
  function wireActions() {
    jQuery('#ldp-table').off('click.ldpact')
      .on('click.ldpact', '.btn-row-edit', function () {
        var id = this.getAttribute('data-id');
        var row = CURRENT_ROWS.filter(function (r) { return String(metaOf(r).id) === String(id); })[0];
        openModal(id, row ? row.slice(0, COLS.length) : null);
      })
      .on('click.ldpact', '.btn-row-confirm', function () {
        var id = this.getAttribute('data-id');
        postJSON(BASE + '/row/confirm', { date: currentDate(), id: id }).then(function (res) {
          if (res.ok && res.body && res.body.success) { afterMutation('confirmed'); }
          else if (window.Swal) {
            var msg = (res.body && res.body.error === 'same_user') ? t('sameUser') : ((res.body && res.body.message) || t('err'));
            Swal.fire({ icon: 'warning', title: 'Latam Desk Position', text: msg });
          }
        });
      })
      .on('click.ldpact', '.btn-row-delete', function () {
        var id = this.getAttribute('data-id');
        function doDelete() {
          postJSON(BASE + '/row/delete', { date: currentDate(), id: id }).then(function (res) {
            if (res.ok && res.body && res.body.success) { afterMutation('deleted'); }
            else if (window.Swal) { Swal.fire({ icon: 'error', title: 'Latam Desk Position', text: t('err') }); }
          });
        }
        if (window.Swal) {
          Swal.fire({ icon: 'warning', title: t('delTitle'), text: t('delText'), showCancelButton: true,
            confirmButtonText: t('yes'), cancelButtonText: t('cancel'), confirmButtonColor: '#dc3545' })
            .then(function (r) { if (r.isConfirmed) doDelete(); });
        } else { doDelete(); }
      });
  }

  // Cada wiring é isolado: um que falte (jQuery/plugin ausente, por exemplo) não
  // pode derrubar o calendário nem o carregamento dos dados, que é o que deixaria
  // a página com o campo vazio e a tabela sem cabeçalho.
  function boot() {
    [wireDatePicker, wireClear, wireImport, wirePageLen, wireAddRow, wireActions]
      .forEach(function (fn) {
        try { fn(); } catch (e) {
          if (window.console && console.error) console.error('[latam-desk-position] ' + (fn.name || 'wire') + ' falhou:', e);
        }
      });
    load(null);          // sem data → servidor devolve o último arquivo disponível
  }

  // Se o script entrar depois do DOMContentLoaded (defer, injeção, cache), o
  // listener nunca dispararia e a página ficaria inteiramente inerte.
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

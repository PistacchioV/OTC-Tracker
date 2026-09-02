/**
 * Live Position › Swap › Characteristics
 * Read-only view of the swap book in custody on a reference date (D-1 ANBIMA
 * default). Widgets + a wide DataTable whose header/columns come straight from
 * the backend (single source of truth). Smart filter + Columns/Export toolbar
 * follow the New Deals pattern; the date picker follows the Live Position one.
 */
(function () {
  'use strict';

  // ':gt(1)' NÃO serve aqui: o thead tem duas linhas (títulos + filtros), o jQuery
  // enumera 2×N <th> e os das colunas 0/1 da segunda linha caem em posição > 1,
  // devolvendo checkbox e Actions para a exportação. Índice de COLUNA, então.
  function exportFromData(idx) { return idx >= LEAD; }

  // dd/mm/yyyy chronological sort — DataTables orders strings by default, so date
  // columns were sorted as text (by day). This type detector makes any date column
  // sort oldest↔newest correctly on header click.
  if (jQuery.fn.dataTable && !jQuery.fn.dataTable.ext.type.order['date-dmy-pre']) {
    var _DMY = /^(\d{2})\/(\d{2})\/(\d{4})$/;
    jQuery.fn.dataTable.ext.type.detect.unshift(function (d) {
      if (d === null || d === '') return 'date-dmy';
      return (typeof d === 'string' && _DMY.test(d.trim())) ? 'date-dmy' : null;
    });
    jQuery.fn.dataTable.ext.type.order['date-dmy-pre'] = function (d) {
      var m = String(d == null ? '' : d).trim().match(_DMY);
      return m ? (+m[3]) * 10000 + (+m[2]) * 100 + (+m[1]) : 0;
    };
  }

  var page = document.getElementById('swapchar-page');
  if (!page) return;
  // Endpoint is per-page (data-api) so the same JS drives Characteristics,
  // Cashflow and Premium — all share this generic columns/rows table.
  var API = page.getAttribute('data-api') || '/api/live-position-swap-characteristics/data';
  // Colunas FIXAS à esquerda (fora dos dados): checkbox, Status e — só quando a
  // página pede — Actions. O deslocamento aparecia como o literal `2` em seis
  // lugares; esquecer um deles faz o filtro por coluna filtrar a coluna vizinha,
  // sem erro nenhum. LEAD é esse número, calculado UMA vez — e depois do `page`,
  // que é de onde a opção vem.
  var ACTIONS = !!page.getAttribute('data-actions');
  var LEAD = ACTIONS ? 3 : 2;

  var dt = null;               // jQuery DataTables instance
  var COLS = [];               // [{label, idx}]
  var activeField = null;      // smart-filter: column chosen, awaiting a value
  var chips = [];              // [{idx, value}]

  // Minimal i18n for the few JS-driven strings (rest via data-lang in app.js).
  var LANG = (localStorage.getItem('language') || 'en').toLowerCase();
  var _TRANS = {
    en: { filterPh: 'Filter by column…', valuePh: 'Type value for "{f}" + Enter',
          status: 'In Custody', pickCol: 'Pick a column',
          srcNote: 'No file for the selected date — showing the position of {src}',
          srcNone: 'No position file in the last 10 business days' },
    br: { filterPh: 'Filtrar por coluna…', valuePh: 'Digite o valor para "{f}" + Enter',
          status: 'Em Custódia', pickCol: 'Escolha uma coluna',
          srcNote: 'Sem arquivo para a data escolhida — exibindo a posição de {src}',
          srcNone: 'Sem arquivo de posição nos últimos 10 dias úteis' },
    es: { filterPh: 'Filtrar por columna…', valuePh: 'Escriba el valor para "{f}" + Enter',
          status: 'En Custodia', pickCol: 'Elija una columna',
          srcNote: 'Sin archivo para la fecha elegida — mostrando la posición de {src}',
          srcNone: 'Sin archivo de posición en los últimos 10 días hábiles' },
  };
  function t(k) { return (_TRANS[LANG] || _TRANS.en)[k] || _TRANS.en[k]; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ── Data load ─────────────────────────────────────────────────────────────
  function load(dateStr) {
    var url = API + (dateStr ? ('?date=' + encodeURIComponent(dateStr)) : '');
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success) return;
        renderWidgets(d.widgets, d.ref_date_fmt);
        buildTable(d.columns, d.rows, d.statuses);
        renderSrcNote(d);
        var asof = document.getElementById('sc-total-asof');
        if (asof) asof.textContent = d.ref_date_fmt || '—';
      })
      .catch(function () {});
  }

  // Aviso de "que dia estou vendo" — ADITIVO: só as páginas cujo payload manda
  // `source_date` (as três Live Position de Swap, cujos endpoints andam até dez
  // dias úteis para trás quando falta o arquivo do dia). As outras páginas
  // deste visualizador não mandam o campo e seguem exatamente como antes.
  function fmtBR(iso) {
    var p = String(iso || '').split('-');
    return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : '';
  }
  function renderSrcNote(d) {
    var wrap = document.getElementById('scDateWrap');
    if (!wrap || typeof d.source_date === 'undefined') return;
    var msg = '';
    if (!d.source_date) msg = t('srcNone');
    else if (d.ref_date && d.source_date !== d.ref_date) {
      msg = t('srcNote').replace('{src}', fmtBR(d.source_date));
    }
    var note = document.getElementById('sc-src-note');
    if (!msg) { if (note) note.remove(); return; }
    if (!note) {
      note = document.createElement('span');
      note.id = 'sc-src-note';
      note.className = 'badge bg-warning-subtle text-warning ms-2';
      wrap.parentNode.insertBefore(note, wrap.nextSibling);
    }
    note.textContent = msg;
  }

  // Exposto para a página recarregar a tabela depois de uma ação própria (o
  // Print Advice do Settlement Advice muda o status das linhas). Só isso: o
  // resto do visualizador segue fechado.
  window.scLoad = load;

  function setVal(id, v) { var el = document.getElementById(id); if (el) el.textContent = v; }

  function renderWidgets(w, refFmt) {
    if (!w) return;
    // Each group is optional — Cashflow/Premium pages only send { total }.
    if (w.tipo) { setVal('sc-w-tipo-total', w.tipo.total); setVal('sc-w-tipo-cashflow', w.tipo.cashflow); setVal('sc-w-tipo-bullet', w.tipo.bullet); }
    if (w.lob) {
      setVal('sc-w-lob-total', w.lob.total);
      ['CEM', 'EDG', 'COMM', 'HYB'].forEach(function (k) { setVal('sc-w-lob-' + k, w.lob[k]); });
    }
    if (w.index) { setVal('sc-w-index-total', w.index.total); setVal('sc-w-index-vcp', w.index.vcp); setVal('sc-w-index-calculado', w.index.calculado); }
    if (w.func) {
      setVal('sc-w-func-total', w.func.total);
      ['forward_start', 'notional', 'premio', 'arrependimento', 'sem'].forEach(function (k) { setVal('sc-w-func-' + k, w.func[k]); });
    }
    setVal('sc-w-total', w.total);
  }

  // ── Table ─────────────────────────────────────────────────────────────────
  // Status por LINHA (opcional). O payload pode mandar `statuses`, um array
  // paralelo a `rows`; quem não manda — Athena, Events, VCP, Characteristics —
  // segue com o badge fixo de sempre. Aditivo de propósito: este JS é
  // compartilhado por cinco páginas e não pode mudar de comportamento para as
  // que não pediram nada.
  var STATUS_PILL = {
    Sent:      'text-bg-primary',
    Generated: 'text-bg-success',
    New:       'text-bg-info',
  };
  function statusCell(st) {
    var cls = STATUS_PILL[st];
    if (!cls) return null;
    return '<span class="badge ' + cls + ' bg-gradient rounded-pill">' + esc(st) + '</span>';
  }

  function buildTable(columns, rows, statuses) {
    COLS = columns.map(function (label, i) { return { label: label, idx: i }; });

    // Header: title row (checkbox, status, columns) + per-column filter row.
    var titleRow =
      '<tr id="swapchar-head">' +
      '<th class="text-center" style="min-width:38px"><input type="checkbox" id="scCheckAll" class="form-check-input"></th>' +
      (ACTIONS ? '<th class="text-center" data-lang="sc-actions">Actions</th>' : '') +
      '<th data-lang="sc-status">Status</th>' +
      columns.map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('') + '</tr>';
    var filterRow =
      '<tr class="sc-th-filter">' +
      new Array(LEAD + 1).join('<th></th>') +
      columns.map(function (c, i) {
        return '<th><input type="text" class="form-control form-control-sm sc-col-filter" data-col="' +
          (i + LEAD) + '" placeholder="' + esc(c) + '" autocomplete="off"></th>';
      }).join('') + '</tr>';
    document.querySelector('#swapchar-table thead').innerHTML = titleRow + filterRow;

    var statusBadge = '<span class="badge bg-secondary-subtle text-secondary" data-lang="sc-status-custody">' + esc(t('status')) + '</span>';
    // Os botões carregam o índice da linha NO PAYLOAD (data-i), não a posição na
    // tela: a tabela ordena e pagina, e a posição visual não identifica nada.
    // `sc-row-act` e NAO `rounded-circle`: o circulo do Bootstrap so fica redondo
    // quando o botao ja e quadrado, e com o padding do .btn-sm ele sai OVAL. A
    // classe trava 32x32 e arredonda os cantos — mesmo padrao do .ops-row-act do
    // Other Products Summary.
    var actionsCell =
      '<div class="d-flex justify-content-center gap-1">' +
      '<a class="btn btn-info btn-sm sc-row-act sc-act" data-act="edit" href="#" title="Edit"><i class="ti ti-edit"></i></a>' +
      '<a class="btn btn-success btn-sm sc-row-act sc-act" data-act="confirm" href="#" title="Confirm"><i class="ti ti-check"></i></a>' +
      '<a class="btn btn-danger btn-sm sc-row-act sc-act" data-act="delete" href="#" title="Delete"><i class="ti ti-trash"></i></a>' +
      '</div>';
    var data = rows.map(function (r, i) {
      var st = (statuses && statuses[i] && statusCell(statuses[i])) || statusBadge;
      var lead = ['<input type="checkbox" class="form-check-input sc-row-check" data-i="' + i + '">'];
      if (ACTIONS) lead.push(actionsCell.replace(/class="btn /g, 'data-i="' + i + '" class="btn '));
      lead.push(st);
      return lead.concat(r.map(function (v) { return esc(v); }));
    });

    if (dt) { dt.destroy(); }
    var colDefs = [{ orderable: false, className: 'text-center',
                     targets: ACTIONS ? [0, 1] : [0] }];

    dt = jQuery('#swapchar-table').DataTable({
      data: data,
      columns: new Array(LEAD).join(',').split(',').map(function () { return {}; })
        .concat(columns.map(function () { return {}; })),
      columnDefs: colDefs,
      // No scrollX: the header + body stay in ONE table (never misaligns). The
      // wrapping .table-responsive (overflow-x) provides the horizontal scroll,
      // and the per-column widths come from the nth-child CSS block.
      scrollX: false,
      autoWidth: false,
      orderCellsTop: true,          // sort listeners on the title row, not the filter row
      deferRender: true,
      pageLength: 25,
      lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']],
      order: [],
      dom: "<'row'<'col-sm-12'tr>><'d-md-flex justify-content-between align-items-center mt-2'ip>",
      // Paginação no padrão New Deals: setas em caixinhas, sem texto
      language: { paginate: {
        first: '<i class="ti ti-chevrons-left"></i>',
        previous: '<i class="ti ti-chevron-left"></i>',
        next: '<i class="ti ti-chevron-right"></i>',
        last: '<i class="ti ti-chevrons-right"></i>'
      } },
      buttons: [{
        extend: 'collection',
        text: '<i class="ti ti-download me-1"></i> Export',
        className: 'btn btn-sm btn-info bg-gradient dropdown-toggle',
        autoClose: true,
        buttons: [
          { extend: 'copy',  text: '<i class="ti ti-copy me-1"></i> Copy',  className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'csv',   text: '<i class="ti ti-file-type-csv me-1"></i> CSV',   className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
          { extend: 'excel', text: '<i class="ti ti-file-spreadsheet me-1"></i> Excel', className: 'dropdown-item', exportOptions: { columns: exportFromData, modifier: { page: 'all' } } },
        ],
      }],
    });

    // Place export dropdown into its wrapper.
    var expWrap = document.querySelector('.scExportWrapper');
    if (expWrap) { expWrap.innerHTML = ''; dt.buttons().container().appendTo(expWrap); }

    // Seleção de célula + Ctrl+C — padrão New Deals. Opt-in e ADITIVO: só age
    // nas páginas que incluem o table-std.js; nas demais é um no-op.
    if (window.otcCellCopy) {
      window.otcCellCopy('#swapchar-table', { skip: ACTIONS ? [0, 1] : [0] });
    }
    // Item Advanced do menu Export — opt-in como o otcCellCopy: onde o
    // export-advanced.js não estiver carregado, é um no-op.
    if (window.otcExportAdvanced) window.otcExportAdvanced('#swapchar-table', { daily: API });

    // Per-column filter row → column search (debounced by keyup/change).
    jQuery('#swapchar-table thead').off('keyup.sccol change.sccol')
      .on('keyup.sccol change.sccol', '.sc-col-filter', function () {
        var col = +this.getAttribute('data-col');
        this.classList.toggle('sc-has-val', !!this.value);
        if (dt.column(col).search() !== this.value) dt.column(col).search(this.value).draw();
      });

    setVal('sc-count', rows.length);
    buildColumnsToggle();
    var pl = document.querySelector('.sc-page-len');      // sync "Show entries"
    if (pl) pl.value = String(dt.page.len());
    reapplyChips();
    if (window.lucide && lucide.createIcons) lucide.createIcons();
    applyTranslationsIfAny();

    // Os botões só existem se a página pediu; o que eles FAZEM é dela também
    // (window.scRowAction). Este arquivo serve cinco páginas — ele desenha e
    // entrega o clique, não sabe o que é confirmar ou apagar em cada uma.
    if (ACTIONS) {
      jQuery('#swapchar-table tbody').off('click.scact').on('click.scact', '.sc-act', function (e) {
        e.preventDefault();
        var i = parseInt(this.getAttribute('data-i'), 10);
        if (isNaN(i) || typeof window.scRowAction !== 'function') return;
        window.scRowAction(this.getAttribute('data-act'), i, rows[i], columns);
      });
    }

    // Select-all checkbox
    var checkAll = document.getElementById('scCheckAll');
    if (checkAll) checkAll.addEventListener('change', function () {
      document.querySelectorAll('#swapchar-table tbody .sc-row-check').forEach(function (c) { c.checked = checkAll.checked; });
    });
  }

  // ── Columns show/hide (New Deals ti-columns pattern) ───────────────────────
  function buildColumnsToggle() {
    var wrap = document.querySelector('.columnToggleWrapper');
    if (!wrap) return;
    var items = dt.columns().header().toArray().slice(LEAD).map(function (th, index) {
      var label = th.textContent.trim();
      return '<li class="px-3 py-1">' +
        '<div class="form-check">' +
        '<input class="form-check-input toggle-vis" type="checkbox" data-column="' + (index + LEAD) + '" id="scCol' + index + '" checked>' +
        '<label class="form-check-label fw-medium" for="scCol' + index + '">' + esc(label) + '</label>' +
        '</div></li>';
    }).join('');
    wrap.innerHTML =
      '<div class="dropdown">' +
      '<button class="btn btn-sm btn-soft-primary dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
      '<i class="ti ti-columns me-1"></i> Columns</button>' +
      '<ul class="dropdown-menu" id="scColMenu" style="max-height:340px; overflow-y:auto;">' + items + '</ul></div>';
    document.getElementById('scColMenu').addEventListener('change', function (e) {
      if (e.target.classList.contains('toggle-vis')) {
        dt.column(parseInt(e.target.dataset.column, 10)).visible(e.target.checked);
      }
    });
  }

  // ── Smart filter ───────────────────────────────────────────────────────────
  function reapplyChips() {
    if (!dt) return;
    dt.columns().every(function () { this.search(''); });
    // Keep the per-column filter row inputs alongside the smart-filter chips.
    document.querySelectorAll('#swapchar-table .sc-col-filter').forEach(function (inp) {
      if (inp.value) dt.column(+inp.getAttribute('data-col')).search(inp.value);
    });
    chips.forEach(function (c) { dt.column(c.idx + LEAD).search(c.value); });
    dt.draw();
  }

  function renderChips() {
    var box = document.getElementById('scChips');
    box.innerHTML = chips.map(function (c, i) {
      return '<span class="smart-filter-chip">' + esc(COLS[c.idx].label) + ': ' + esc(c.value) +
        '<span class="sf-chip-remove" data-i="' + i + '">&times;</span></span>';
    }).join('');
    box.querySelectorAll('.sf-chip-remove').forEach(function (x) {
      x.addEventListener('click', function () {
        chips.splice(parseInt(this.dataset.i, 10), 1);
        renderChips(); reapplyChips();
      });
    });
  }

  function colType(label) {
    var n = label.toLowerCase();
    if (n.indexOf('data') === 0) return 'date';
    if (/valor|saldo|percentual|taxa|pu |premio|prêmio|rebate|cota|aliquota|alíquota|fator/.test(n)) return 'value';
    return 'text';
  }

  function showDropdown(term) {
    var dd = document.getElementById('scDropdown');
    var lo = (term || '').toLowerCase();
    var matches = COLS.filter(function (c) { return c.label.toLowerCase().indexOf(lo) !== -1; }).slice(0, 40);
    if (!matches.length) { dd.style.display = 'none'; return; }
    dd.innerHTML = matches.map(function (c) {
      var ty = colType(c.label);
      return '<li data-idx="' + c.idx + '"><span class="sf-type-badge sf-type-' + ty + '">' + ty + '</span>' + esc(c.label) + '</li>';
    }).join('');
    dd.style.display = 'block';
    dd.querySelectorAll('li').forEach(function (li) {
      li.addEventListener('click', function () {
        activeField = COLS[parseInt(this.dataset.idx, 10)];
        var inp = document.getElementById('scInput');
        inp.value = '';
        inp.placeholder = t('valuePh').replace('{f}', activeField.label);
        dd.style.display = 'none';
        inp.focus();
      });
    });
  }

  function wireSmartFilter() {
    var inp = document.getElementById('scInput');
    var dd = document.getElementById('scDropdown');
    if (!inp) return;
    inp.addEventListener('focus', function () { if (!activeField) showDropdown(inp.value); });
    inp.addEventListener('input', function () { if (!activeField) showDropdown(inp.value); });
    // Commit the pending field+value as a chip (Enter or the Search button).
    function commit() {
      if (activeField && inp.value.trim()) {
        chips.push({ idx: activeField.idx, value: inp.value.trim() });
        activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
        renderChips(); reapplyChips(); dd.style.display = 'none';
      }
    }
    inp.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') { e.preventDefault(); commit(); }
      else if (e.key === 'Escape') {
        activeField = null; inp.value = ''; inp.placeholder = t('filterPh'); dd.style.display = 'none';
      }
    });
    document.addEventListener('click', function (e) {
      if (!document.getElementById('scSmartFilter').contains(e.target)) dd.style.display = 'none';
    });
    // Search button (New Deals style) — commits the smart filter.
    var searchBtn = document.getElementById('scSearchBtn');
    if (searchBtn) searchBtn.addEventListener('click', commit);
    // Clear filters button (in the table card) — clears chips + per-column inputs.
    var clr = document.getElementById('scClearFilters');
    if (clr) clr.addEventListener('click', function () {
      chips = []; activeField = null; inp.value = ''; inp.placeholder = t('filterPh');
      document.querySelectorAll('#swapchar-table .sc-col-filter').forEach(function (i) {
        i.value = ''; i.classList.remove('sc-has-val');
      });
      renderChips(); reapplyChips();
    });
    inp.placeholder = t('filterPh');
  }

  function applyTranslationsIfAny() {
    if (window.applyTranslations) { try { window.applyTranslations(); } catch (e) {} }
  }

  // ── Reference date picker (MANDATORY: jQuery daterangepicker, dd/mm/yyyy) ───
  function wireDatePicker(attempt) {
    var inp = document.getElementById('sc-date');
    if (!inp) return;
    var startISO = page.getAttribute('data-ref-date');
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      var $d = jQuery('#sc-date');
      $d.daterangepicker({
        singleDatePicker: true, autoApply: true, showDropdowns: true,
        locale: { format: 'DD/MM/YYYY' },
        startDate: startISO ? moment(startISO, 'YYYY-MM-DD') : moment(),
        maxDate: moment(),
      }, function (start) { load(start.format('YYYY-MM-DD')); });
      jQuery('#scDateWrap .sc-cal-btn').on('click', function () { $d.trigger('click'); });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDatePicker(attempt + 1); }, 50); return; }
    inp.removeAttribute('readonly');
    if (startISO) { var p = startISO.split('-'); inp.value = p[2] + '/' + p[1] + '/' + p[0]; }
    inp.addEventListener('change', function () {
      var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (m) load(m[3] + '-' + m[2] + '-' + m[1]);
    });
  }

  function wirePageLen() {
    var sel = document.querySelector('.sc-page-len');
    if (sel) sel.addEventListener('change', function () {
      if (dt) dt.page.len(parseInt(this.value, 10)).draw();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wireSmartFilter();
    wirePageLen();
    wireDatePicker();
    load(page.getAttribute('data-ref-date'));
  });
})();

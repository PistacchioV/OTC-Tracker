/* Tools (Apps › Tools) — o JS comum das cinco ferramentas.
 *
 * As páginas são renderizadas no servidor; o que mora aqui é o que só o
 * navegador faz: formatar número ao sair do campo, ligar o flatpickr nas
 * datas (dd/mm/aaaa na tela, ISO no value — CLAUDE.md §3), montar a toolbar
 * padrão nas tabelas, mostrar/esconder os campos de cada índice, e o
 * pré-preenchimento do Swap Calculator pelo B3 ID.
 *
 * i18n: o I18nManager traduz os [data-lang] UMA vez, no load; o que este
 * arquivo escreve depois passa pelo mapa local `_TRANS` (§2).
 */
(function () {
  'use strict';

  var page = document.querySelector('.tl-page');
  if (!page) return;

  // ── i18n dos textos montados em JS ────────────────────────────────────────
  var _TRANS = {
    en: { show: 'Show', entries: 'entries', all: 'All', columns: 'Columns', export: 'Export',
          clear: 'Clear Filters', blank: 'blank = empty cells',
          reading: 'Reading the file…', imported: 'quotes read', newDays: 'new dates',
          updated: 'updated', reloading: 'Reloading…', sendFail: 'could not send the file',
          syncing: 'Fetching the full history — this takes a while…',
          synced: 'History updated', syncFail: 'Could not update the history',
          days: 'days in the base', lookingUp: 'Looking up the swap position…',
          notFound: 'Not found', prefilled: 'Filled from the swap position of',
          missing: 'Could not pull from the position (left blank):',
          assumed: 'Assumed: with no Data operação termo, the trade date is the swap start date.',
          noIndexRule: 'No line in the tools-swap-index mapping for this curve — register it in Mapping. The position had:',
          noIndexCell: 'The position brings no index on this leg.',
          flow: 'flow', pickId: 'Type a B3 ID first.', fromBase: 'from the imported base of',
          ipcaAuto: 'fetched from IBGE on Calculate',
          fields: { counterparty: 'Counterparty', data_operacao: 'Trade date', inicio: 'Flow start',
                    fim: 'Flow end', vencimento: 'Swap maturity', nocional: 'Remaining notional',
                    nocional_original: 'Original notional', amortizacao: 'Amortisation',
                    base_amortizacao: 'Amortisation base', indexador: 'index', taxa: 'rate',
                    moeda: 'currency', tenor: 'tenor', percentual: '% of CDI',
                    base_ajuste: 'What settles', ptax_inicial: 'initial fixing',
                    ni_inicial: 'initial index number', preco_inicial: 'initial price',
                    ativa: 'Receiving leg', passiva: 'Paying leg' } },
    br: { show: 'Mostrar', entries: 'linhas', all: 'Todas', columns: 'Colunas', export: 'Exportar',
          clear: 'Limpar Filtros', blank: 'blank = células vazias',
          reading: 'Lendo o arquivo…', imported: 'cotações lidas', newDays: 'datas novas',
          updated: 'atualizadas', reloading: 'Recarregando…', sendFail: 'não foi possível enviar o arquivo',
          syncing: 'Buscando o histórico completo — isso demora…',
          synced: 'Histórico atualizado', syncFail: 'Não foi possível atualizar o histórico',
          days: 'dias na base', lookingUp: 'Consultando a posição de swap…',
          notFound: 'Não encontrado', prefilled: 'Preenchido pela posição de swap de',
          missing: 'Não foi possível puxar da posição (ficou em branco):',
          assumed: 'Assumido: sem Data operação termo, a data da operação é a data de início do swap.',
          noIndexRule: 'Nenhuma linha no cadastro tools-swap-index para esta curva — cadastre em Mapping. A posição trazia:',
          noIndexCell: 'A posição não traz índice nesta perna.',
          flow: 'fluxo', pickId: 'Digite um B3 ID primeiro.', fromBase: 'da base importada de',
          ipcaAuto: 'buscado no IBGE ao calcular',
          fields: { counterparty: 'Contraparte', data_operacao: 'Data da operação', inicio: 'Início do fluxo',
                    fim: 'Fim do fluxo', vencimento: 'Vencimento do swap', nocional: 'Notional remanescente',
                    nocional_original: 'Notional original', amortizacao: 'Amortização',
                    base_amortizacao: 'Base da amortização', indexador: 'índice', taxa: 'taxa',
                    moeda: 'moeda', tenor: 'prazo', percentual: '% do CDI',
                    base_ajuste: 'O que liquida', ptax_inicial: 'fixing inicial',
                    ni_inicial: 'número-índice inicial', preco_inicial: 'preço inicial',
                    ativa: 'Ponta ativa', passiva: 'Ponta passiva' } },
    es: { show: 'Mostrar', entries: 'filas', all: 'Todas', columns: 'Columnas', export: 'Exportar',
          clear: 'Limpiar Filtros', blank: 'blank = celdas vacías',
          reading: 'Leyendo el archivo…', imported: 'cotizaciones leídas', newDays: 'fechas nuevas',
          updated: 'actualizadas', reloading: 'Recargando…', sendFail: 'no se pudo enviar el archivo',
          syncing: 'Buscando el historial completo — tarda un poco…',
          synced: 'Historial actualizado', syncFail: 'No se pudo actualizar el historial',
          days: 'días en la base', lookingUp: 'Consultando la posición de swap…',
          notFound: 'No encontrado', prefilled: 'Completado desde la posición de swap de',
          missing: 'No se pudo traer de la posición (quedó en blanco):',
          assumed: 'Asumido: sin Data operação termo, la fecha de la operación es la de inicio del swap.',
          noIndexRule: 'Ninguna línea en el registro tools-swap-index para esta curva — regístrela en Mapping. La posición traía:',
          noIndexCell: 'La posición no trae índice en esta pata.',
          flow: 'flujo', pickId: 'Escriba un B3 ID primero.', fromBase: 'de la base importada de',
          ipcaAuto: 'traído del IBGE al calcular',
          fields: { counterparty: 'Contraparte', data_operacao: 'Fecha de la operación', inicio: 'Inicio del flujo',
                    fim: 'Fin del flujo', vencimento: 'Vencimiento del swap', nocional: 'Nocional remanente',
                    nocional_original: 'Nocional original', amortizacao: 'Amortización',
                    base_amortizacao: 'Base de la amortización', indexador: 'índice', taxa: 'tasa',
                    moeda: 'moneda', tenor: 'plazo', percentual: '% del CDI',
                    base_ajuste: 'Qué liquida', ptax_inicial: 'fixing inicial',
                    ni_inicial: 'número índice inicial', preco_inicial: 'precio inicial',
                    ativa: 'Pata activa', passiva: 'Pata pasiva' } }
  };
  function lang() {
    try { return localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) { return 'en'; }
  }
  function t(k) { var m = _TRANS[lang()] || _TRANS.en; return m[k] !== undefined ? m[k] : _TRANS.en[k]; }
  function tf(k) { var m = (_TRANS[lang()] || _TRANS.en).fields; return m[k] || _TRANS.en.fields[k] || k; }

  // ── números: en-US na tela (#,##0.00), leitura tolerante aos dois padrões ──
  // `fx` é o fixing de moeda: a PTAX sai com 4 casas, mas a mesa digita a
  // cotação com até 8 — e o blur não pode arredondar o que o cálculo vai
  // usar. Mínimo 4, máximo 8, sem zeros inventados (§439).
  var CASAS = { money: 2, pct: 4, rate: 8, price: 4, fx: { min: 4, max: 8 }, index: 6, int: 0 };
  function ler(texto) {
    var s = String(texto || '').replace(/%/g, '').replace(/\s/g, '').trim();
    if (!s) return null;
    var n;
    if (s.indexOf(',') >= 0 && s.indexOf('.') >= 0) {
      n = s.lastIndexOf(',') > s.lastIndexOf('.') ? s.replace(/\./g, '').replace(',', '.') : s.replace(/,/g, '');
    } else if (s.indexOf(',') >= 0) {
      n = s.replace(',', '.');
    } else if ((s.match(/\./g) || []).length > 1) {
      n = s.replace(/\./g, '');
    } else {
      n = s;
    }
    var v = Number(n);
    return isFinite(v) ? v : null;
  }
  function escrever(v, casas) {
    var min = typeof casas === 'number' ? casas : casas.min;
    var max = typeof casas === 'number' ? casas : casas.max;
    return v.toLocaleString('en-US', { minimumFractionDigits: min, maximumFractionDigits: max });
  }
  function formatar(el) {
    var casas = CASAS[el.getAttribute('data-format')];
    if (casas === undefined) return;
    var v = ler(el.value);
    if (v === null) return;                   // vazio ou ilegível: o servidor explica
    el.value = escrever(v, casas) + (el.getAttribute('data-format') === 'pct' ? ' %' : '');
  }
  page.querySelectorAll('[data-format]').forEach(function (el) {
    el.addEventListener('blur', function () { formatar(el); });
    el.addEventListener('focus', function () { el.value = el.value.replace(/\s*%\s*$/, ''); });
    formatar(el);
  });

  // ── clicar num campo seleciona o valor INTEIRO ───────────────────────────
  // Estes campos se digitam por cima, não se editam letra a letra: o valor vem
  // preenchido (da posição, ou da formatação de saída) e quem clica ali quer
  // trocá-lo. O `select()` no `focus` sozinho NÃO resolve o clique de mouse —
  // o navegador posiciona o cursor no `mouseup`, que vem DEPOIS, e desfaz a
  // seleção; funcionava só com Tab, e era isso que parecia "não seleciona".
  // Por isso a seleção é refeita no `mouseup`, e só quando o clique não
  // arrastou (senão o arrasto para escolher um trecho seria descartado).
  // Delegado no contêiner porque o campo de data que se VÊ é o `altInput` que
  // o flatpickr cria — ele nem existe quando esta linha roda.
  function selecionavel(el) {
    return el && el.tagName === 'INPUT' && !el.readOnly && !el.disabled &&
           ['text', 'search', 'tel', 'url', 'number', ''].indexOf(el.type) >= 0;
  }
  var focado = null;
  page.addEventListener('focusin', function (ev) {
    if (!selecionavel(ev.target)) return;
    focado = ev.target;
    try { ev.target.select(); } catch (e) { /* number em alguns navegadores */ }
  });
  page.addEventListener('mouseup', function (ev) {
    var el = focado;
    focado = null;
    if (!el || el !== ev.target) return;
    // `selectionStart` levanta em `input[type=number]` em parte dos
    // navegadores — ali não há trecho a preservar, e a seleção segue.
    try { if (el.selectionStart !== el.selectionEnd) return; } catch (e) { /* number */ }
    ev.preventDefault();
    try { el.select(); } catch (e) { /* idem */ }
  });

  // ── datas: flatpickr com altInput (o padrão da casa; nunca type=date visível) ──
  function wireDates() {
    page.querySelectorAll('input.tl-date').forEach(function (el) {
      if (el._flatpickr) return;
      var max = el.getAttribute('data-max') || null;
      if (window.otcDateField) {
        window.otcDateField(el, max ? { maxDate: max } : {});
      }
    });
  }
  wireDates();

  // ── tabelas: a toolbar padrão (Show · Columns · Export · Clear) + filtros ──
  var _dtSeq = 0;
  function initTable(table) {
    if (!window.jQuery || !jQuery.fn.dataTable || table.__tl) return;
    table.__tl = true;
    var $t = jQuery(table);
    var head = table.tHead && table.tHead.rows[0];
    if (!head) return;
    var id = table.id || ('tl-dt-' + (++_dtSeq));
    table.id = id;
    // A linha de filtro por coluna ANTES do .DataTable(), com orderCellsTop (§7).
    var filt = document.createElement('tr');
    Array.prototype.forEach.call(head.cells, function (th, i) {
      var tf_ = document.createElement('th');
      var inp = document.createElement('input');
      inp.type = 'text'; inp.className = 'form-control form-control-sm tl-col-filter';
      inp.setAttribute('data-col', String(i)); inp.placeholder = th.textContent.trim();
      inp.title = t('blank');
      tf_.appendChild(inp); filt.appendChild(tf_);
    });
    table.tHead.appendChild(filt);

    var dt = $t.DataTable({
      scrollX: false, autoWidth: true, orderCellsTop: true, deferRender: true,
      pageLength: 25, lengthMenu: [[10, 25, 50, 100, -1], [10, 25, 50, 100, 'All']], order: [],
      dom: "rt<'d-md-flex justify-content-between align-items-center mt-2'ip>",
      language: { paginate: { first: '<i class="ti ti-chevrons-left"></i>', previous: '<i class="ti ti-chevron-left"></i>',
                              next: '<i class="ti ti-chevron-right"></i>', last: '<i class="ti ti-chevrons-right"></i>' } }
    });
    var xo = { columns: ':visible', modifier: { search: 'applied', order: 'applied', page: 'all' } };
    new jQuery.fn.dataTable.Buttons(dt, { buttons: [
      { extend: 'copy', name: 'copy', exportOptions: xo },
      { extend: 'csv', name: 'csv', fieldSeparator: ';', bom: true, exportOptions: xo },
      { extend: 'excel', name: 'excel', exportOptions: xo },
      { extend: 'print', name: 'print', exportOptions: xo },
      { extend: 'pdfHtml5', name: 'pdf', orientation: 'landscape', pageSize: 'A4', exportOptions: xo }
    ] });
    if (window.otcCellCopy) window.otcCellCopy('#' + id, {});

    // a toolbar, montada acima do wrapper do DataTables
    var bar = document.createElement('div');
    bar.className = 'tl-toolbar';
    bar.innerHTML =
      '<div class="d-flex align-items-center gap-1">' +
        '<label class="form-label mb-0 fs-xs text-muted">' + t('show') + '</label>' +
        '<select class="form-select form-select-sm tl-len" style="width:84px">' +
          '<option>10</option><option selected>25</option><option>50</option><option>100</option><option value="-1">' + t('all') + '</option>' +
        '</select><label class="form-label mb-0 fs-xs text-muted">' + t('entries') + '</label></div>' +
      '<div class="dropdown"><button class="btn btn-sm btn-soft-primary btn-toolbar-all dropdown-toggle" type="button" data-bs-toggle="dropdown" data-bs-auto-close="outside">' +
        '<i class="ti ti-columns me-1"></i>' + t('columns') + '</button><div class="dropdown-menu p-2 tl-cols" style="min-width:220px"></div></div>' +
      '<div class="dropdown"><button class="btn btn-sm btn-info bg-gradient btn-toolbar-all dropdown-toggle" type="button" data-bs-toggle="dropdown">' +
        '<i class="ti ti-download me-1"></i>' + t('export') + '</button><div class="dropdown-menu">' +
        '<a class="dropdown-item" href="#" data-export="copy"><i class="ti ti-copy me-1"></i> Copy</a>' +
        '<a class="dropdown-item" href="#" data-export="csv"><i class="ti ti-file-type-csv me-1"></i> CSV</a>' +
        '<a class="dropdown-item" href="#" data-export="excel"><i class="ti ti-file-spreadsheet me-1"></i> Excel</a>' +
        '<a class="dropdown-item" href="#" data-export="print"><i class="ti ti-printer me-1"></i> Print</a>' +
        '<a class="dropdown-item" href="#" data-export="pdf"><i class="ti ti-file-type-pdf me-1"></i> PDF</a></div></div>' +
      '<button class="btn btn-sm btn-outline-secondary btn-toolbar-all tl-clear" type="button"><i class="ti ti-filter-off me-1"></i>' + t('clear') + '</button>';
    var wrapper = table.closest('.dataTables_wrapper, .dt-container') || table.parentNode;
    wrapper.parentNode.insertBefore(bar, wrapper);

    var cols = bar.querySelector('.tl-cols');
    Array.prototype.forEach.call(head.cells, function (th, i) {
      var row = document.createElement('div'); row.className = 'form-check';
      var cid = id + '-col-' + i;
      row.innerHTML = '<input class="form-check-input" type="checkbox" id="' + cid + '" checked><label class="form-check-label fs-xs" for="' + cid + '"></label>';
      row.querySelector('label').textContent = th.textContent.trim();
      row.querySelector('input').addEventListener('change', function () { dt.column(i).visible(this.checked); dt.columns.adjust(); });
      cols.appendChild(row);
    });
    bar.querySelector('.tl-len').addEventListener('change', function () { dt.page.len(parseInt(this.value, 10)).draw(); });
    bar.querySelector('.tl-clear').addEventListener('click', function () {
      table.querySelectorAll('.tl-col-filter').forEach(function (i) { i.value = ''; });
      dt.columns().search('').draw();
    });
    bar.querySelectorAll('[data-export]').forEach(function (a) {
      a.addEventListener('click', function (ev) { ev.preventDefault(); dt.button(a.getAttribute('data-export') + ':name').trigger(); });
    });
    $t.find('thead').on('keyup change', '.tl-col-filter', function () {
      var col = +this.getAttribute('data-col'), v = this.value || '';
      if (v.trim().toLowerCase() === 'blank') dt.column(col).search('^\\s*$', true, false).draw();
      else if (dt.column(col).search() !== v) dt.column(col).search(v).draw();
    });
    dt.columns.adjust();
    setTimeout(function () { dt.columns.adjust().draw(false); }, 150);
  }
  page.querySelectorAll('table.tl-dt').forEach(initTable);
  window.addEventListener('resize', function () {
    if (window.jQuery && jQuery.fn.dataTable) jQuery.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
  });

  // ── Fixed Income: o índice retroativo esconde a projeção e trava a data ──
  (function () {
    var idx = document.getElementById('indexador'), venc = document.getElementById('vencimento');
    if (!idx || !venc) return;
    var retro = (idx.getAttribute('data-retro') || '').split(',').filter(Boolean);
    var proj = document.getElementById('tl-proj'), aviso = document.getElementById('tl-realised');
    var hoje = venc.getAttribute('data-max-today');
    function aplicar() {
      var r = retro.indexOf(idx.value) >= 0;
      if (proj) proj.hidden = r;
      if (aviso) aviso.hidden = !r;
      if (venc._flatpickr) venc._flatpickr.set('maxDate', r && hoje ? hoje : null);
    }
    idx.addEventListener('change', aplicar);
    aplicar();
  })();

  // ── Swap Calculator: cada índice mostra só os campos dele ────────────────
  function aplicarLado(lado) {
    var sel = document.getElementById(lado + '_indexador');
    if (!sel) return;
    page.querySelectorAll('[data-leg="' + lado + '"][data-show-for]').forEach(function (b) {
      b.hidden = (b.getAttribute('data-show-for') || '').split(',').indexOf(sel.value) === -1;
    });
  }
  function convencaoPadrao(lado, sel) {
    var tabela;
    try { tabela = JSON.parse(sel.getAttribute('data-defaults') || '{}'); } catch (e) { return; }
    var p = tabela[sel.value];
    if (!p) return;
    var c = document.getElementById(lado + '_convencao'), r = document.getElementById(lado + '_regime');
    if (c) c.value = p[0];
    if (r) r.value = p[1];
  }
  page.querySelectorAll('select.tl-leg-index').forEach(function (sel) {
    var lado = sel.getAttribute('data-leg');
    aplicarLado(lado);
    sel.addEventListener('change', function () { aplicarLado(lado); convencaoPadrao(lado, sel); fixingPadrao(lado); });
  });

  // ── a data do fixing (Term SOFR / EURIBOR) é D-2 úteis do início do fluxo ──
  // O motor já assume D-2 quando o campo está em branco; o campo vem preenchido
  // para a mesa VER de que dia é a taxa. Feriados: o ANBIMA do app; sem o
  // arquivo, só o fim de semana conta.
  var _hol = null;
  function loadHolidays() {
    if (_hol) return Promise.resolve(_hol);
    return fetch('/static/data/anbima.json', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (l) { _hol = {}; (l || []).forEach(function (h) { var d = String((h && h.date) || h || '').slice(0, 10); if (d) _hol[d] = 1; }); return _hol; })
      .catch(function () { _hol = {}; return _hol; });
  }
  function isoOf(d) { return d.getUTCFullYear() + '-' + ('0' + (d.getUTCMonth() + 1)).slice(-2) + '-' + ('0' + d.getUTCDate()).slice(-2); }
  function minusBiz(iso, n, hol) {
    var d = new Date(iso + 'T00:00:00Z');
    if (isNaN(d.getTime())) return '';
    while (n > 0) {
      d.setUTCDate(d.getUTCDate() - 1);
      var w = d.getUTCDay(), k = isoOf(d);
      if (w !== 0 && w !== 6 && !hol[k]) n -= 1;
    }
    return isoOf(d);
  }
  function fixingPadrao(lado, force) {
    var sel = document.getElementById(lado + '_indexador');
    var fx = document.getElementById(lado + '_data_fixing');
    var ini = document.getElementById('inicio');
    if (!sel || !fx || !ini) return;
    if (['term_sofr', 'euribor'].indexOf(sel.value) === -1) return;
    if (fx.value && !force && !fx.hasAttribute('data-auto')) return;
    var start = ini.value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start)) return;
    loadHolidays().then(function (hol) {
      var v = minusBiz(start, 2, hol);
      if (!v) return;
      fx.value = v;
      fx.setAttribute('data-auto', '1');
      if (fx._flatpickr) fx._flatpickr.setDate(v, false);
    });
  }
  ['ativa', 'passiva'].forEach(function (lado) {
    fixingPadrao(lado);
    var fx = document.getElementById(lado + '_data_fixing');
    if (fx) fx.addEventListener('change', function () { fx.removeAttribute('data-auto'); });
  });
  var iniEl = document.getElementById('inicio');
  if (iniEl) iniEl.addEventListener('change', function () { fixingPadrao('ativa', true); fixingPadrao('passiva', true); });

  // ── a taxa do Term SOFR vem da BASE que o dropzone alimenta ──────────────
  // O motor já a buscava para calcular; sem preencher o campo, a tela parecia
  // pedir o número à mão. Refaz a busca quando o prazo ou a data do fixing
  // mudam, que são as duas coisas que a escolhem.
  function buscarFixing(lado) {
    var sel = document.getElementById(lado + '_indexador');
    var alvo = document.getElementById(lado + '_taxa_indice');
    var dt = document.getElementById(lado + '_data_fixing');
    var tn = document.getElementById(lado + '_tenor');
    var nota = document.getElementById(lado + '_fixing_nota');
    if (!sel || !alvo || ['term_sofr', 'euribor'].indexOf(sel.value) === -1) return;
    var quando = (dt && dt.value) || '';
    if (!/^\d{4}-\d{2}-\d{2}$/.test(quando)) return;
    // UM endpoint para os dois: é a mesma pergunta, e o prazo vai como texto —
    // a EURIBOR tem '1 week', que não cabe num número de meses.
    fetch('/api/tools/fixing-rate?index=' + encodeURIComponent(sel.value) +
          '&tenor=' + encodeURIComponent((tn && tn.value) || '3 month') +
          '&date=' + encodeURIComponent(quando), { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        if (!x.ok || !x.d.success) {
          if (nota) { nota.textContent = x.d.error || ''; nota.className = 'tl-help text-danger'; }
          return;
        }
        alvo.value = x.d.percent.toFixed(8);
        formatar(alvo);
        if (nota) {
          nota.textContent = t('fromBase') + ' ' + (x.d.date ? x.d.date.split('-').reverse().join('/') : '');
          nota.className = 'tl-help';
        }
      })
      .catch(function () { /* offline: fica o que estava no campo */ });
  }
  // ── IPCA: com M-1/M-2 os números-índice vêm do IBGE no Calculate ─────────
  // Os campos ficam só-leitura para a tela não sugerir que o digitado vale:
  // o motor ignora os dois quando o fixing está escolhido.
  function aplicarFixingIpca(lado) {
    var sel = document.getElementById(lado + '_ipca_fixing');
    if (!sel) return;
    var auto = !!sel.value;
    ['_ni_inicial', '_ni_final'].forEach(function (suf) {
      var el = document.getElementById(lado + suf);
      if (!el) return;
      el.readOnly = auto;
      el.placeholder = auto ? t('ipcaAuto') : '';
      el.classList.toggle('tl-readonly', auto);
    });
  }
  page.querySelectorAll('select.tl-ipca-fixing').forEach(function (sel) {
    var lado = sel.getAttribute('data-leg');
    aplicarFixingIpca(lado);
    sel.addEventListener('change', function () {
      aplicarFixingIpca(lado);
      var nota = document.getElementById(lado + '_ipca_nota');
      if (nota) { nota.hidden = true; nota.textContent = ''; }
    });
  });

  ['ativa', 'passiva'].forEach(function (lado) {
    ['_tenor', '_data_fixing'].forEach(function (suf) {
      var el = document.getElementById(lado + suf);
      if (el) el.addEventListener('change', function () { buscarFixing(lado); });
    });
    var sel = document.getElementById(lado + '_indexador');
    if (sel) sel.addEventListener('change', function () { buscarFixing(lado); });
  });

  // ── Swap Calculator: o pré-preenchimento pelo B3 ID ──────────────────────
  (function () {
    var inp = document.getElementById('b3_id'), btn = document.getElementById('tl-lookup');
    if (!inp || !btn) return;
    var status = document.getElementById('tl-lookup-status');
    var flows = document.getElementById('tl-flow');
    var lastData = null;

    function setVal(id, v) {
      var el = document.getElementById(id);
      if (!el) return;
      el.value = v == null ? '' : String(v);
      if (el._flatpickr) el._flatpickr.setDate(el.value || '', false);
      if (el.hasAttribute('data-format')) formatar(el);
    }
    function mark(id, cls) {
      var el = document.getElementById(id);
      var f = el && el.closest('.tl-field');
      if (!f) return;
      f.classList.remove('tl-missing', 'tl-assumed');
      if (cls) f.classList.add(cls);
    }
    function clearMarks() {
      page.querySelectorAll('.tl-missing, .tl-assumed').forEach(function (f) { f.classList.remove('tl-missing', 'tl-assumed'); });
    }
    function say(html, cls) {
      if (!status) return;
      status.className = 'tl-note mt-2 ' + (cls || '');
      status.innerHTML = html;
      status.hidden = false;
    }
    function label(key) {
      var p = key.split('.');
      return p.length === 2 ? tf(p[0]) + ' · ' + tf(p[1]) : tf(key);
    }
    function applyFlow(flow) {
      // O período e a amortização do evento vêm PRONTOS do servidor (`p_*`).
      // Montá-los aqui era ter a regra escrita duas vezes: trocar o evento no
      // seletor dava uma resposta e abrir nele dava outra.
      setVal('inicio', flow.p_inicio || '');
      setVal('fim', flow.p_fim || '');
      setVal('amortizacao', flow.p_amort || '');
      setVal('base_amortizacao', flow.p_base_amort || '');
      mark('inicio', flow.p_inicio ? (flow.p_assumido ? 'tl-assumed' : '') : 'tl-missing');
      mark('fim', flow.p_fim ? '' : 'tl-missing');
      mark('amortizacao', flow.p_amort ? '' : 'tl-missing');
      mark('base_amortizacao', flow.p_base_amort ? '' : 'tl-missing');
    }
    function fill(d) {
      lastData = d;
      clearMarks();
      var f = d.fields || {};
      ['counterparty', 'data_operacao', 'inicio', 'fim', 'vencimento', 'nocional', 'nocional_original',
       'amortizacao', 'base_amortizacao', 'base_ajuste'].forEach(function (k) { setVal(k, f[k] || ''); });
      ['ativa', 'passiva'].forEach(function (lado) {
        var p = d[lado] || {};
        var sel = document.getElementById(lado + '_indexador');
        if (sel) {
          sel.value = p.indexador || '';
          if (!p.indexador) sel.selectedIndex = -1;
          aplicarLado(lado);
        }
        ['taxa', 'percentual', 'convencao', 'regime', 'moeda', 'tenor', 'taxa_indice',
         'ptax_inicial', 'ptax_final', 'ptax_offset', 'ni_inicial', 'preco_inicial', 'ativo']
          .forEach(function (k) { if (p[k] !== undefined && (p[k] !== '' || k === 'taxa')) setVal(lado + '_' + k, p[k]); });
        // O spread do CDI tem input PRÓPRIO (mesmo `name`, id diferente): sem
        // isto o campo visível da perna de CDI ficava com o valor anterior.
        var spread = document.getElementById(lado + '_taxa_cdi');
        if (spread) { spread.value = p.taxa === undefined ? '' : String(p.taxa); formatar(spread); }
        // Índice que não resolveu não fica só em branco: a nota diz o que a
        // POSIÇÃO trazia (Código índice · curva do swap-index · Nome
        // Tipo/Classe) e manda cadastrar a curva. "Não identificou" e "a
        // posição veio sem índice" são coisas diferentes, e a diferença é
        // exatamente o que se corrige.
        var inota = document.getElementById(lado + '_indice_nota');
        if (inota) {
          var src = p.fonte || {};
          var trazia = [src.codigo, (src.curva && src.curva !== src.codigo) ? src.curva : '',
                        src.classe].filter(Boolean).join(' · ');
          inota.textContent = p.indexador ? '' : (trazia ? (t('noIndexRule') + ' ' + trazia)
                                                         : t('noIndexCell'));
          inota.hidden = !inota.textContent;
        }
        var mo = document.getElementById(lado + '_moeda_equity');
        if (mo && p.moeda) mo.value = p.moeda;
        // os campos que a ponta não usa voltam ao vazio
        ['ptax_inicial', 'ptax_final', 'ni_inicial', 'preco_inicial', 'ativo'].forEach(function (k) {
          if (!p[k]) setVal(lado + '_' + k, '');
        });
        // De que dia é a PTAX que entrou — ou por que ela não entrou. Sem isto
        // o campo de fixing é um número sem procedência.
        var nota = document.getElementById(lado + '_ptax_nota');
        if (nota) {
          nota.textContent = p.ptax_data ? ('PTAX ' + p.ptax_data.split('-').reverse().join('/'))
                                         : (p.ptax_erro || '');
          nota.className = 'tl-help' + (p.ptax_erro ? ' text-danger' : '');
        }
        var fn = document.getElementById(lado + '_fixing_nota');
        if (fn) {
          fn.textContent = p.fixing_data ? (t('fromBase') + ' ' + p.fixing_data.split('-').reverse().join('/'))
                                         : (p.fixing_erro || '');
          fn.className = 'tl-help' + (p.fixing_erro ? ' text-danger' : '');
        }
      });
      (d.missing || []).forEach(function (k) { mark(k.replace('.', '_'), 'tl-missing'); });
      (d.assumed || []).forEach(function (k) { mark(k, 'tl-assumed'); });
      // o seletor de fluxo
      if (flows) {
        flows.innerHTML = '';
        var wrap = flows.closest('.tl-field');
        if (d.flows && d.flows.length) {
          d.flows.forEach(function (fl, i) {
            var o = document.createElement('option');
            o.value = String(i);
            o.textContent = (fl.evento ? fl.evento.split('-').reverse().join('/') : '—') +
                            (fl.tipo_amort ? ' · ' + fl.tipo_amort : '') +
                            (fl.taxa_amort != null ? ' · ' + fl.taxa_amort + '%' : '');
            if (fl.evento === d.flow_event) o.selected = true;
            flows.appendChild(o);
          });
          if (wrap) wrap.hidden = false;
        } else if (wrap) {
          wrap.hidden = true;
        }
      }
      ['ativa', 'passiva'].forEach(function (l) { var p = d[l] || {}; if (p.data_fixing) setVal(l + '_data_fixing', p.data_fixing); else fixingPadrao(l, true); });
      var txt = '<strong>' + t('prefilled') + ' ' + (d.source_date ? d.source_date.split('-').reverse().join('/') : '—') + '</strong>';
      if (d.identificador || d.contrato) txt += ' — ' + [d.contrato, d.identificador].filter(Boolean).join(' · ');
      var miss = (d.missing || []).map(label);
      if (miss.length) txt += '<br>' + t('missing') + ' <em>' + miss.join(', ') + '</em>';
      if ((d.assumed || []).length) txt += '<br>' + t('assumed');
      say(txt, miss.length ? 'tl-note--warn' : 'tl-note--ok');
    }
    function lookup() {
      var id = (inp.value || '').trim();
      if (!id) { say(t('pickId'), 'tl-note--warn'); return; }
      btn.disabled = true;
      say(t('lookingUp'), '');
      fetch('/api/tools/swap-calculator/prefill?id=' + encodeURIComponent(id), { credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d || !res.d.success) {
            clearMarks();
            setVal('counterparty', '');
            say('<strong>' + t('notFound') + '</strong> — ' + ((res.d && res.d.error) || ''), 'tl-note--warn');
            return;
          }
          fill(res.d);
        })
        .catch(function (e) { say(String(e), 'tl-note--warn'); })
        .then(function () { btn.disabled = false; });
    }
    btn.addEventListener('click', lookup);
    inp.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); lookup(); } });
    if (flows) flows.addEventListener('change', function () {
      if (!lastData || !lastData.flows) return;
      var fl = lastData.flows[parseInt(this.value, 10)];
      if (fl) applyFlow(fl);
    });
  })();

  // ── Term SOFR: a dropzone do relatório da B3 ─────────────────────────────
  (function () {
    var zona = document.getElementById('tl-drop'), campo = document.getElementById('tl-file');
    if (!zona || !campo) return;
    var aviso = document.getElementById('tl-drop-msg'), url = zona.getAttribute('data-url');
    var ocupado = false;
    function mostrar(msg, cls) { if (!aviso) return; aviso.textContent = msg; aviso.className = 'tl-note mt-2 ' + (cls || ''); aviso.hidden = false; }
    function enviar(arquivo) {
      if (!arquivo || ocupado) return;
      ocupado = true;
      mostrar(t('reading'), '');
      var fd = new FormData(); fd.append('file', arquivo);
      fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok || !res.j.success) { mostrar(res.j.error || t('sendFail'), 'tl-note--warn'); ocupado = false; return; }
          var partes = [res.j.used + ' ' + t('imported')];
          if (res.j.new) partes.push(res.j.new + ' ' + t('newDays'));
          if (res.j.updated) partes.push(res.j.updated + ' ' + t('updated'));
          mostrar(partes.join(' · ') + '. ' + t('reloading'), 'tl-note--ok');
          window.location.reload();
        })
        .catch(function (e) { mostrar(t('sendFail') + ': ' + e, 'tl-note--warn'); ocupado = false; });
    }
    campo.addEventListener('change', function () { enviar(campo.files && campo.files[0]); });
    ['dragenter', 'dragover'].forEach(function (ev) { zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.add('is-over'); }); });
    ['dragleave', 'drop'].forEach(function (ev) { zona.addEventListener(ev, function (e) { e.preventDefault(); zona.classList.remove('is-over'); }); });
    zona.addEventListener('drop', function (e) { var fs = e.dataTransfer && e.dataTransfer.files; if (fs && fs.length) enviar(fs[0]); });
    // largar o arquivo fora da zona abriria o arquivo e sairia da página
    ['dragover', 'drop'].forEach(function (ev) { window.addEventListener(ev, function (e) { if (!zona.contains(e.target)) e.preventDefault(); }); });
  })();

  // ── botões de sincronização profunda (SOFR / EURIBOR) ────────────────────
  page.querySelectorAll('[data-sync]').forEach(function (b) {
    b.addEventListener('click', function () {
      b.disabled = true;
      if (window.Swal) Swal.fire({ title: t('syncing'), allowOutsideClick: false, didOpen: function () { Swal.showLoading(); } });
      fetch(b.getAttribute('data-sync'), { method: 'POST', credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok || !res.j.success) {
            if (window.Swal) Swal.fire({ icon: 'error', title: t('syncFail'), text: (res.j && res.j.error) || '' });
            return;
          }
          var txt = res.j.dias_depois + ' ' + t('days') + (res.j.erros && res.j.erros.length ? ' · ' + res.j.erros.join('; ') : '');
          if (window.Swal) Swal.fire({ icon: 'success', title: t('synced'), text: txt }).then(function () { window.location.reload(); });
          else window.location.reload();
        })
        .catch(function (e) { if (window.Swal) Swal.fire({ icon: 'error', title: t('syncFail'), text: String(e) }); })
        .then(function () { b.disabled = false; });
    });
  });
})();

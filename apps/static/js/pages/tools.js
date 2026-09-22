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
          exporting: 'Exporting…', exportFail: 'Could not build the calculation memo',
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
          closeOf: 'close of',
          posLooking: 'Looking up the position…',
          duCounted: 'counted, ANBIMA',
          n_parity_failed: 'the PTAX of the FX rate could not be fetched — {motivo}',
          n_quoted_in_cents: '{ativo} is quoted in CENTS in the B3 Index (conversion factor 0.01): the Quotes prices were multiplied by 0.01',
          n_parity_ptax: 'FX rate: PTAX {moeda} of {data} (BCB, ask)',
          f_paridade: 'FX rate',
          n_cpty_short_name: 'the account {conta} is not in the Reference Data — showing the position short name ({apelido})',
          n_fixing_ptax: 'fixing: PTAX {moeda} of {data} (BCB, ask)',
          n_fixing_failed: 'the PTAX of the fixing could not be fetched — {motivo}',
          f_fixing: 'fixing',
          posFilled: 'Filled from the position of',
          posMissing: 'Could not pull (left blank):',
          posAssumed: 'Filled by approximation — check:',
          n_unwound_before: 'already unwound in this contract: {valor} — the notional is what is still open',
          n_cpty_not_registered: 'the counterparty document {taxid} is not in the Reference Data — on the umbrella account the holder is the bank, so the client cannot be named',
          n_side_of_party: 'the side is the one of the PARTY of the record ({parte}) — confirm it is the bank',
          n_strike_in_percent: 'the strike is registered in PERCENT ({pct}) — type the strike in value',
          n_asian: 'Asian option: {n} verification dates',
          n_has_barrier: 'the contract has a barrier — barriers and rebates are not priced here',
          n_fixings_from_quotes: '{n} fixing price(s) from Quotes ({fonte}), {de} to {ate}',
          n_fixings_missing: '{n} verification date(s) without a price yet: {datas} {motivo}',
          e_not_in_position: '{id} is not in {fonte} of the last business day',
          e_position_unreadable: 'Could not read the position',
          f_nocional: 'notional',
          f_taxa_termo: 'forward rate',
          f_vencimento: 'maturity',
          f_posicao: 'bank position',
          f_moeda: 'currency',
          f_strike: 'strike',
          f_taxa_recompra: 'termination rate',
          f_taxa_pre: 'pre rate',
          f_tipo: 'type',
          f_lado: 'bank side',
          f_quantidade: 'quantity',
          f_exercicio: 'exercise date',
          f_fixings: 'fixing prices',
          closeNoDate: 'no close date in the description — type the price',
          ipcaAuto: 'fetched from IBGE on Calculate',
          descRead: 'From the curve description:', descNone: 'Nothing in the curve description changes the calculation.',
          descConfirms: 'confirms the position', descDiffers: 'the position had', descApplied: 'applied',
          descUnread: 'Not understood in the description — check by hand:',
          fields: { counterparty: 'Counterparty', data_operacao: 'Trade date', inicio: 'Flow start',
                    fim: 'Flow end', vencimento: 'Swap maturity', nocional: 'Remaining notional',
                    nocional_original: 'Original notional', amortizacao: 'Amortisation',
                    base_amortizacao: 'Amortisation base', indexador: 'index', taxa: 'rate',
                    moeda: 'currency', tenor: 'tenor', percentual: '% of CDI',
                    base_ajuste: 'What settles', ptax_inicial: 'initial fixing',
                    ni_inicial: 'initial index number', preco_inicial: 'initial price',
                    ativa: 'Receiving leg', passiva: 'Paying leg', multiplicador: 'rate multiplier',
                    convencao: 'day count', regime: 'compounding', ptax_offset: 'fixing offset',
                    lookback: 'lookback', shift: 'observation shift' } },
    br: { show: 'Mostrar', entries: 'linhas', all: 'Todas', columns: 'Colunas', export: 'Exportar',
          exporting: 'Exportando…', exportFail: 'Não foi possível gerar a memória de cálculo',
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
          closeOf: 'fechamento de',
          posLooking: 'Consultando a posição…',
          duCounted: 'contados, ANBIMA',
          n_parity_failed: 'não foi possível buscar a PTAX da paridade — {motivo}',
          n_quoted_in_cents: '{ativo} é cotado em CENTAVOS no Index B3 (fator de conversão 0,01): os preços do Quotes foram multiplicados por 0,01',
          n_parity_ptax: 'paridade: PTAX {moeda} de {data} (BCB, venda)',
          f_paridade: 'FX rate',
          n_cpty_short_name: 'a conta {conta} não está no Reference Data — mostrando o apelido da posição ({apelido})',
          n_fixing_ptax: 'fixing: PTAX {moeda} de {data} (BCB, venda)',
          n_fixing_failed: 'não foi possível buscar a PTAX do fixing — {motivo}',
          f_fixing: 'fixing',
          posFilled: 'Preenchido pela posição de',
          posMissing: 'Não deu para puxar (ficou em branco):',
          posAssumed: 'Preenchido por aproximação — confira:',
          n_unwound_before: 'já recomprado neste contrato: {valor} — o nocional é o que ainda está aberto',
          n_cpty_not_registered: 'o documento {taxid} da contraparte não está no Reference Data — na conta guarda-chuva o titular é o banco, então o cliente não pode ser nomeado',
          n_side_of_party: 'o lado é o da PARTE do registro ({parte}) — confirme que é o banco',
          n_strike_in_percent: 'o strike está registrado em PERCENTUAL ({pct}) — digite o strike em valor',
          n_asian: 'Opção asiática: {n} datas de verificação',
          n_has_barrier: 'o contrato tem barreira — barreiras e rebates não são apurados aqui',
          n_fixings_from_quotes: '{n} preço(s) de verificação do Quotes ({fonte}), de {de} a {ate}',
          n_fixings_missing: '{n} data(s) de verificação ainda sem preço: {datas} {motivo}',
          e_not_in_position: '{id} não está em {fonte} do último dia útil',
          e_position_unreadable: 'Não foi possível ler a posição',
          f_nocional: 'nocional',
          f_taxa_termo: 'taxa a termo',
          f_vencimento: 'vencimento',
          f_posicao: 'posição do banco',
          f_moeda: 'moeda',
          f_strike: 'strike',
          f_taxa_recompra: 'taxa da recompra',
          f_taxa_pre: 'taxa pré',
          f_tipo: 'tipo',
          f_lado: 'lado do banco',
          f_quantidade: 'quantidade',
          f_exercicio: 'data de exercício',
          f_fixings: 'preços de verificação',
          closeNoDate: 'a denominação não traz a data do fechamento — digite o preço',
          ipcaAuto: 'buscado no IBGE ao calcular',
          descRead: 'Da descrição da curva:', descNone: 'Nada na descrição da curva muda o cálculo.',
          descConfirms: 'confirma a posição', descDiffers: 'a posição trazia', descApplied: 'aplicado',
          descUnread: 'Não entendido na descrição — confira à mão:',
          fields: { counterparty: 'Contraparte', data_operacao: 'Data da operação', inicio: 'Início do fluxo',
                    fim: 'Fim do fluxo', vencimento: 'Vencimento do swap', nocional: 'Notional remanescente',
                    nocional_original: 'Notional original', amortizacao: 'Amortização',
                    base_amortizacao: 'Base da amortização', indexador: 'índice', taxa: 'taxa',
                    moeda: 'moeda', tenor: 'prazo', percentual: '% do CDI',
                    base_ajuste: 'O que liquida', ptax_inicial: 'fixing inicial',
                    ni_inicial: 'número-índice inicial', preco_inicial: 'preço inicial',
                    ativa: 'Ponta ativa', passiva: 'Ponta passiva', multiplicador: 'multiplicador da taxa',
                    convencao: 'contagem de dias', regime: 'capitalização', ptax_offset: 'deslocamento do fixing',
                    lookback: 'lookback', shift: 'observation shift' } },
    es: { show: 'Mostrar', entries: 'filas', all: 'Todas', columns: 'Columnas', export: 'Exportar',
          exporting: 'Exportando…', exportFail: 'No se pudo generar la memoria de cálculo',
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
          closeOf: 'cierre de',
          posLooking: 'Consultando la posición…',
          duCounted: 'contados, ANBIMA',
          n_parity_failed: 'no se pudo obtener la PTAX de la paridad — {motivo}',
          n_quoted_in_cents: '{ativo} cotiza en CENTAVOS en el Index B3 (factor de conversión 0,01): los precios de Quotes se multiplicaron por 0,01',
          n_parity_ptax: 'paridad: PTAX {moeda} del {data} (BCB, venta)',
          f_paridade: 'FX rate',
          n_cpty_short_name: 'la cuenta {conta} no está en el Reference Data — mostrando el apodo de la posición ({apelido})',
          n_fixing_ptax: 'fixing: PTAX {moeda} del {data} (BCB, venta)',
          n_fixing_failed: 'no se pudo obtener la PTAX del fixing — {motivo}',
          f_fixing: 'fixing',
          posFilled: 'Completado con la posición de',
          posMissing: 'No se pudo traer (quedó en blanco):',
          posAssumed: 'Completado por aproximación — verifique:',
          n_unwound_before: 'ya recomprado en este contrato: {valor} — el nocional es lo que sigue abierto',
          n_cpty_not_registered: 'el documento {taxid} de la contraparte no está en el Reference Data — en la cuenta paraguas el titular es el banco, así que el cliente no puede nombrarse',
          n_side_of_party: 'el lado es el de la PARTE del registro ({parte}) — confirme que es el banco',
          n_strike_in_percent: 'el strike está registrado en PORCENTAJE ({pct}) — escriba el strike en valor',
          n_asian: 'Opción asiática: {n} fechas de verificación',
          n_has_barrier: 'el contrato tiene barrera — barreras y rebates no se calculan aquí',
          n_fixings_from_quotes: '{n} precio(s) de verificación de Quotes ({fonte}), de {de} a {ate}',
          n_fixings_missing: '{n} fecha(s) de verificación aún sin precio: {datas} {motivo}',
          e_not_in_position: '{id} no está en {fonte} del último día hábil',
          e_position_unreadable: 'No se pudo leer la posición',
          f_nocional: 'nocional',
          f_taxa_termo: 'tasa forward',
          f_vencimento: 'vencimiento',
          f_posicao: 'posición del banco',
          f_moeda: 'moneda',
          f_strike: 'strike',
          f_taxa_recompra: 'tasa de la recompra',
          f_taxa_pre: 'tasa pre',
          f_tipo: 'tipo',
          f_lado: 'lado del banco',
          f_quantidade: 'cantidad',
          f_exercicio: 'fecha de ejercicio',
          f_fixings: 'precios de verificación',
          closeNoDate: 'la denominación no trae la fecha del cierre — escriba el precio',
          ipcaAuto: 'traído del IBGE al calcular',
          descRead: 'De la descripción de la curva:', descNone: 'Nada en la descripción de la curva cambia el cálculo.',
          descConfirms: 'confirma la posición', descDiffers: 'la posición traía', descApplied: 'aplicado',
          descUnread: 'No entendido en la descripción — revise a mano:',
          fields: { counterparty: 'Contraparte', data_operacao: 'Fecha de la operación', inicio: 'Inicio del flujo',
                    fim: 'Fin del flujo', vencimento: 'Vencimiento del swap', nocional: 'Nocional remanente',
                    nocional_original: 'Nocional original', amortizacao: 'Amortización',
                    base_amortizacao: 'Base de la amortización', indexador: 'índice', taxa: 'tasa',
                    moeda: 'moneda', tenor: 'plazo', percentual: '% del CDI',
                    base_ajuste: 'Qué liquida', ptax_inicial: 'fixing inicial',
                    ni_inicial: 'número índice inicial', preco_inicial: 'precio inicial',
                    ativa: 'Pata activa', passiva: 'Pata pasiva', multiplicador: 'multiplicador de la tasa',
                    convencao: 'conteo de días', regime: 'capitalización', ptax_offset: 'desplazamiento del fixing',
                    lookback: 'lookback', shift: 'observation shift' } }
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
  // `pct5` é a taxa de AMORTIZAÇÃO: ela multiplica um notional de centenas de
  // milhões e a 5ª casa vale dinheiro (num VBR de R$ 282,8 mi, `0,7246%` contra
  // `0,72464%` são R$ 113). Com o `pct` de 4 casas o blur arredondava de volta
  // o que o servidor mandava com 5 — o campo não é só exibição, é o que o
  // cálculo lê.
  // `mult` é o multiplicador da taxa (§479): `1.1765` como está no contrato,
  // sem zeros inventados e sem cortar casa.
  var CASAS = { money: 2, pct: 4, pct5: 5, rate: 8, price: 4,
                fx: { min: 4, max: 8 }, index: 6, int: 0, mult: { min: 0, max: 8 } };
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
    // O sufixo é de toda a família `pct*`, não do literal 'pct'.
    var pct = String(el.getAttribute('data-format') || '').indexOf('pct') === 0;
    el.value = escrever(v, casas) + (pct ? ' %' : '');
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
    if (typeof mostrarExtras === 'function') mostrarExtras(lado);
  }
  // ── O que só aparece quando EXISTE (mesa, 21/09/2026) ────────────────────
  // O multiplicador da taxa só tem campo quando há um multiplicador (≠ 1): um
  // campo vazio em toda perna VCP fazia a mesa procurar um num contrato que não
  // tem. E a perna de equity cujo preço inicial é um % de um fechamento
  // (`100.00% Close 20-Sep-24`) ganha o trio cupom · fechamento · preço.
  function mostrarExtras(lado) {
    var sel = document.getElementById(lado + '_indexador');
    var mult = document.getElementById(lado + '_multiplicador'), mbox = document.getElementById(lado + '_mult_box');
    if (mbox && mult) { var mv = ler(mult.value); mbox.hidden = (mv === null || mv === 1); }
    var cup = document.getElementById(lado + '_cupom_limpo'), cbox = document.getElementById(lado + '_cupom_box');
    if (cbox && cup) cbox.hidden = !(sel && sel.value === 'equity' && (cup.value || '').trim());
  }
  // Preço inicial = fechamento × cupom limpo / 100. `replicar` leva o resultado
  // ao Initial price — que é o campo que o cálculo lê. Sem uma das duas
  // parcelas o calculado fica vazio e o Initial price NÃO é tocado: a mesa pode
  // tê-lo digitado.
  function refazerCupom(lado, replicar) {
    var c = document.getElementById(lado + '_cupom_limpo'), f = document.getElementById(lado + '_preco_close'),
        out = document.getElementById(lado + '_preco_calc');
    if (!c || !f || !out) return;
    var cv = ler(c.value), fv = ler(f.value);
    if (cv === null || fv === null) { out.value = ''; return; }
    var preco = fv * cv / 100;
    out.value = String(preco); formatar(out);
    if (replicar) {
      var ini = document.getElementById(lado + '_preco_inicial');
      if (ini) { ini.value = String(preco); formatar(ini); }
    }
  }
  ['ativa', 'passiva'].forEach(function (lado) {
    page.querySelectorAll('input.tl-cupom[data-leg="' + lado + '"]').forEach(function (el) {
      el.addEventListener('input', function () { refazerCupom(lado, true); });
      el.addEventListener('change', function () { refazerCupom(lado, true); mostrarExtras(lado); });
    });
    var m = document.getElementById(lado + '_multiplicador');
    if (m) m.addEventListener('change', function () { mostrarExtras(lado); });
    // Tela que volta do Calculate: o trio já vem preenchido pelo formulário.
    refazerCupom(lado, false);
  });
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
  // para a mesa VER de que dia é a taxa. O calendário é o do ÍNDICE, e quem
  // conta é o servidor (`/api/tools/fixing-date`).
  function fixingPadrao(lado, force) {
    var sel = document.getElementById(lado + '_indexador');
    var fx = document.getElementById(lado + '_data_fixing');
    var ini = document.getElementById('inicio');
    if (!sel || !fx || !ini) return;
    if (['term_sofr', 'euribor'].indexOf(sel.value) === -1) return;
    if (fx.value && !force && !fx.hasAttribute('data-auto')) return;
    var start = ini.value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start)) return;
    // Quem conta é o SERVIDOR, no calendário do ÍNDICE (SOFR no Term SOFR,
    // TARGET2 na EURIBOR): a conta local usava o `anbima.json` e errava em todo
    // feriado americano que não é brasileiro — 19/06/2026 (Juneteenth) fazia o
    // D-2 de 22/06 sair 18/06 em vez de 17/06. Sem resposta o campo fica como
    // está: uma data pelo calendário errado é pior que nenhuma.
    fetch('/api/tools/fixing-date?index=' + encodeURIComponent(sel.value) +
          '&start=' + encodeURIComponent(start), { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d || !d.success || !d.date) return;
        fx.value = d.date;
        fx.setAttribute('data-auto', '1');
        if (fx._flatpickr) fx._flatpickr.setDate(d.date, false);
        // a data mudou: a taxa daquele dia vem junto (a base é a mesma pergunta)
        if (typeof buscarFixing === 'function') buscarFixing(lado);
      })
      .catch(function () { /* offline: fica o que está no campo */ });
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
      f.classList.remove('tl-missing', 'tl-assumed', 'tl-derived');
      if (cls) f.classList.add(cls);
    }
    function clearMarks() {
      page.querySelectorAll('.tl-missing, .tl-assumed, .tl-derived').forEach(function (f) { f.classList.remove('tl-missing', 'tl-assumed', 'tl-derived'); });
    }
    function esc(s) {
      return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; });
    }
    // ── a Denominação da curva: o que ela diz e as colunas não (§479) ──────
    // Cada achado do servidor vem com o TRECHO de onde saiu e o estado
    // (aplicado · confirma · divergente · info); o campo que a denominação
    // preencheu fica marcado, e o que ficou sem leitura sai em aviso.
    function notaDescricao(lado, p) {
      var nota = document.getElementById(lado + '_descricao_nota');
      if (!nota) return;
      var itens = p.leitura || [], sobras = p.nao_lido || [];
      itens.forEach(function (it) {
        if (it.campo && (it.estado === 'aplicado' || it.estado === 'divergente')) mark(lado + '_' + it.campo, 'tl-derived');
      });
      var partes = itens.map(function (it) {
        var s = esc(it.rotulo) + ' <strong>' + esc(it.valor) + '</strong>';
        if (it.estado === 'confirma') s += ' (' + t('descConfirms') + ')';
        else if (it.estado === 'divergente') s += ' (' + t('descDiffers') + ' ' + esc(it.anterior) + ')';
        else if (it.estado === 'aplicado') s += ' (' + t('descApplied') + ')';
        return s + ' <em>«' + esc(it.trecho) + '»</em>';
      });
      var html = '';
      if (partes.length) html += '<strong>' + t('descRead') + '</strong> ' + partes.join(' · ');
      else if (p.descricao) html += t('descNone');
      if (sobras.length) html += (html ? '<br>' : '') + '<span class="tl-help--warn">' + t('descUnread') + ' <em>' + sobras.map(esc).join(' · ') + '</em></span>';
      nota.innerHTML = html;
      nota.hidden = !html;
    }
    // O texto colado ou corrigido na tela passa pela MESMA leitura do servidor
    // que o pré-preenchimento usa — os campos atuais vão junto para a resposta
    // dizer se cada achado preenche, confirma ou diverge do que está na tela.
    var CAMPOS_DESC = ['indexador', 'taxa', 'percentual', 'convencao', 'regime', 'tenor', 'ptax_offset', 'multiplicador', 'lookback', 'shift',
                       'ativo', 'cupom_limpo', 'cupom_data'];
    // De que pregão é o fechamento que multiplica o cupom — ou por que não veio.
    function notaClose(lado, p) {
      var n = document.getElementById(lado + '_close_nota');
      if (!n) return;
      n.textContent = p.close_data ? (t('closeOf') + ' ' + p.close_data.split('-').reverse().join('/'))
                                   : (p.close_erro || (p.cupom_limpo && !p.cupom_data ? t('closeNoDate') : ''));
      n.className = 'tl-help' + (p.close_erro ? ' text-danger' : '');
    }
    // O fechamento e o preço inicial que o servidor apurou pelo cupom limpo.
    function aplicarCupom(lado, p) {
      if (p.preco_close) setVal(lado + '_preco_close', p.preco_close);
      if (p.cupom_limpo && p.preco_inicial !== undefined) setVal(lado + '_preco_inicial', p.preco_inicial);
      notaClose(lado, p);
      mostrarExtras(lado);
      refazerCupom(lado, false);
      if (p.cupom_limpo && !p.preco_inicial) mark(lado + '_preco_inicial', 'tl-missing');
    }
    function lerDescricao(lado) {
      var ta = document.getElementById(lado + '_descricao');
      if (!ta) return;
      var sel = document.getElementById(lado + '_indexador');
      var q = ['text=' + encodeURIComponent((ta.value || '').trim())];
      CAMPOS_DESC.forEach(function (k) {
        var el = document.getElementById(lado + '_' + k);
        if (k === 'taxa' && sel && sel.value === 'cdi') el = document.getElementById(lado + '_taxa_cdi') || el;
        q.push(k + '=' + encodeURIComponent(el ? (el.value || '') : ''));
      });
      fetch('/api/tools/swap-calculator/curve?' + q.join('&'), { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d || !d.success) return;
          (d.leitura || []).forEach(function (it) {
            if (!it.campo || it.estado === 'info' || it.estado === 'confirma') return;
            setVal(lado + '_' + it.campo, d[it.campo]);
            if (it.campo === 'taxa') { var sp = document.getElementById(lado + '_taxa_cdi'); if (sp) { sp.value = d.taxa; formatar(sp); } }
          });
          notaDescricao(lado, d);
          aplicarCupom(lado, d);
        })
        .catch(function () { /* offline: fica o que está nos campos */ });
    }
    ['ativa', 'passiva'].forEach(function (lado) {
      var ta = document.getElementById(lado + '_descricao');
      if (ta) ta.addEventListener('change', function () { lerDescricao(lado); });
    });
    // O bloco (descrição + multiplicador) só aparece na perna cuja curva É
    // VCP: o prefill decide; quem preenche à mão abre pelo link.
    function mostrarVcp(lado, on) {
      var bloco = document.getElementById(lado + '_vcp'), link = document.getElementById(lado + '_vcp_link');
      if (bloco) bloco.hidden = !on;
      if (link) link.hidden = !!on;
    }
    page.querySelectorAll('a.tl-vcp-toggle').forEach(function (a) {
      a.addEventListener('click', function (ev) {
        ev.preventDefault();
        var lado = a.getAttribute('data-leg');
        mostrarVcp(lado, true);
        var ta = document.getElementById(lado + '_descricao');
        if (ta) ta.focus();
      });
    });
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
      // A taxa contratada é do FLUXO (o DFLUXO traz uma por evento, e o spread
      // pode mudar de um para o outro): trocar o evento troca a taxa das duas
      // pontas, já com o sinal. Evento sem taxa deixa o campo como está.
      ['ativa', 'passiva'].forEach(function (lado, k) {
        var v = (flow.taxa_juros || [])[k];
        if (v === null || v === undefined || isNaN(v)) return;
        var txt = Number(v).toFixed(4);
        setVal(lado + '_taxa', txt);
        var sp = document.getElementById(lado + '_taxa_cdi');
        if (sp) { sp.value = txt; formatar(sp); }
      });
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
         'ptax_inicial', 'ptax_final', 'ptax_offset', 'ni_inicial', 'preco_inicial',
         'preco_final', 'ativo', 'multiplicador', 'descricao', 'lookback', 'shift',
         'cupom_limpo', 'cupom_data', 'preco_close']
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
        ['ptax_inicial', 'ptax_final', 'ni_inicial', 'preco_inicial', 'preco_final', 'ativo',
         'multiplicador', 'descricao', 'cupom_limpo', 'cupom_data', 'preco_close'].forEach(function (k) {
          if (!p[k]) setVal(lado + '_' + k, '');
        });
        notaDescricao(lado, p);
        mostrarVcp(lado, !!(p.vcp || p.descricao || p.multiplicador));
        aplicarCupom(lado, p);
        // De que dia é a PTAX que entrou — ou por que ela não entrou. Sem isto
        // o campo de fixing é um número sem procedência.
        var nota = document.getElementById(lado + '_ptax_nota');
        if (nota) {
          nota.textContent = p.ptax_data ? ('PTAX ' + p.ptax_data.split('-').reverse().join('/'))
                                         : (p.ptax_erro || '');
          nota.className = 'tl-help' + (p.ptax_erro ? ' text-danger' : '');
        }
        // De que pregão é o fechamento do equity — ou por que ele não veio.
        var pn = document.getElementById(lado + '_preco_nota');
        if (pn) {
          pn.textContent = p.preco_data ? (t('closeOf') + ' ' + p.preco_data.split('-').reverse().join('/'))
                                        : (p.preco_erro || '');
          pn.className = 'tl-help' + (p.preco_erro ? ' text-danger' : '');
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

  // ── Taxa que veio da PTAX: digitar no campo apaga a marca de automática ──
  // O Calculate REBUSCA a PTAX enquanto a marca estiver lá (trocar o vencimento
  // não pode deixar a cotação antiga no campo). Quem digita passa a mandar.
  page.querySelectorAll('input[data-tl-auto]').forEach(function (el) {
    el.addEventListener('input', function () {
      var marca = document.getElementById(el.getAttribute('data-tl-auto'));
      var nota = document.getElementById(el.getAttribute('data-tl-auto') + '_nota');
      if (marca) marca.value = '';
      if (nota) nota.textContent = '';
    });
  });

  // ── Recompra: os dias úteis aparecem assim que as duas datas existem ─────
  // Contados pelo SERVIDOR (ANBIMA), no campo em branco ou marcado como
  // automático; digitar apaga a marca (o bloco acima) e aí vale o digitado.
  // Dispara na carga, a cada troca de data e depois da busca pelo B3 ID.
  var contarDU = (function () {
    var du = page.querySelector('input[data-tl-du]');
    if (!du) return function () {};
    var marca = document.getElementById('du_auto'), nota = document.getElementById('du_auto_nota');
    var ini = document.getElementById('liquidacao'), fim = document.getElementById('vencimento');
    var pedido = 0;
    function contar() {
      if (!ini || !fim) return;
      var automatico = marca && marca.value === '1';
      if ((du.value || '').trim() && !automatico) return;      // o digitado manda
      var a = ini.value, b = fim.value;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(a) || !/^\d{4}-\d{2}-\d{2}$/.test(b)) return;
      var meu = ++pedido;
      fetch('/api/tools/business-days?start=' + encodeURIComponent(a) + '&end=' + encodeURIComponent(b),
            { credentials: 'same-origin' })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (meu !== pedido) return;                          // resposta de uma data antiga
          if (!d || !d.success) { du.value = ''; if (marca) marca.value = ''; if (nota) nota.textContent = (d && d.error) || ''; return; }
          du.value = String(d.days);
          if (marca) marca.value = '1';
          if (nota) nota.textContent = t('duCounted');
        })
        .catch(function () { /* offline: o Calculate conta */ });
    }
    [ini, fim].forEach(function (el) { if (el) el.addEventListener('change', contar); });
    contar();
    return contar;
  })();

  // ── NDF · Unwind NDF · Option: o B3 ID puxa a POSIÇÃO (o esquema do Swap) ──
  // Genérico: o bloco `[data-tl-prefill]` diz o endpoint, e o servidor devolve
  // `fields` pelo id/nome do campo. O que não veio fica em branco e marcado
  // (`tl-missing`); o que veio por aproximação, `tl-assumed`. As notas chegam
  // por CÓDIGO + params (§486) e a tela diz a frase no idioma de quem olha.
  (function () {
    var bloco = page.querySelector('[data-tl-prefill]');
    if (!bloco) return;
    var url = bloco.getAttribute('data-tl-prefill');
    var inp = document.getElementById('b3_id'), btn = document.getElementById('tl-pos-lookup');
    var status = document.getElementById('tl-pos-status');
    if (!inp || !btn) return;
    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
    function frase(chave, params, padrao) {
      var s = t(chave); if (s === undefined) s = padrao || '';
      return String(s).replace(/\{(\w+)\}/g, function (_m, k) { return params && params[k] != null ? params[k] : ''; }).trim();
    }
    function say(html, cls) { if (!status) return; status.className = 'tl-note mt-0 ' + (cls || ''); status.innerHTML = html; status.hidden = !html; }
    function campo(nome) { return document.getElementById(nome) || page.querySelector('[name="' + nome + '"]'); }
    function mark(nome, cls) {
      var el = campo(nome), f = el && (el.closest('.tl-field') || el.closest('.tl-check'));
      if (!f) return;
      f.classList.remove('tl-missing', 'tl-assumed');
      if (cls) f.classList.add(cls);
    }
    function setCampo(nome, v) {
      var el = campo(nome);
      if (!el) return;
      if (el.type === 'checkbox') { el.checked = !!v; return; }
      el.value = v == null ? '' : String(v);
      if (el._flatpickr) el._flatpickr.setDate(el.value || '', false);
      if (el.hasAttribute && el.hasAttribute('data-format')) formatar(el);
    }
    function emissao() {
      var iso = (document.getElementById('data_emissao') || {}).value || '';
      var out = document.getElementById('data_emissao_txt');
      if (out) out.value = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? iso.split('-').reverse().join('/') : iso;
    }
    emissao();                                  // a tela que volta do Calculate
    var marcados = [];
    function fill(d) {
      marcados.forEach(function (n) { mark(n, null); }); marcados = [];
      Object.keys(d.fields || {}).forEach(function (k) { setCampo(k, d.fields[k]); });
      setCampo('b3_id', d.b3_id || inp.value);
      emissao();
      contarDU();                                 // recompra: o DU das datas que acabaram de chegar
      // A procedência embaixo dos campos é da busca ANTERIOR: zera antes de
      // escrever a desta, senão um campo vazio ficaria com "PTAX USD …" embaixo.
      ['fixing_auto_nota', 'paridade_auto_nota'].forEach(function (id) {
        var el = document.getElementById(id); if (el) el.textContent = '';
      });
      // NDF: o bloco do termo de MERCADORIA (paridade + ativo) segue a classe
      var merc = document.getElementById('tl-ndf-commodity');
      if (merc) merc.hidden = !/commodit/i.test((d.fields || {}).classe || '');
      (d.notes || []).forEach(function (n) {
        if (n.code !== 'parity_ptax') return;
        var np = document.getElementById('paridade_auto_nota');
        if (np) np.textContent = 'PTAX ' + n.params.moeda + ' ' + n.params.data;
      });
      // a taxa que veio da PTAX diz de que dia é, embaixo do próprio campo
      (d.notes || []).forEach(function (n) {
        if (n.code !== 'fixing_ptax') return;
        var nota = document.getElementById('fixing_auto_nota');
        if (nota) nota.textContent = 'PTAX ' + n.params.moeda + ' ' + n.params.data;
      });
      (d.missing || []).forEach(function (n) { mark(n, 'tl-missing'); marcados.push(n); });
      (d.assumed || []).forEach(function (n) { mark(n, 'tl-assumed'); marcados.push(n); });
      var html = '<strong>' + t('posFilled') + ' ' + esc((d.source_date || '').split('-').reverse().join('/')) + '</strong>';
      var notas = (d.notes || []).map(function (n) { return frase('n_' + n.code, n.params, n.code); }).filter(Boolean);
      if (notas.length) html += '<br>' + notas.map(esc).join('<br>');
      if ((d.assumed || []).length) html += '<br>' + t('posAssumed') + ' ' + d.assumed.map(function (n) { return esc(frase('f_' + n, null, n)); }).join(' · ');
      if ((d.missing || []).length) html += '<br><span class="text-danger">' + t('posMissing') + ' ' + d.missing.map(function (n) { return esc(frase('f_' + n, null, n)); }).join(' · ') + '</span>';
      say(html, (d.missing || []).length ? 'tl-note--warn' : '');
    }
    function lookup() {
      var id = (inp.value || '').trim();
      if (!id) { say(esc(t('pickId')), 'tl-note--warn'); return; }
      btn.disabled = true;
      say(esc(t('posLooking')), '');
      fetch(url + '?id=' + encodeURIComponent(id), { credentials: 'same-origin' })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok || !res.d || !res.d.success) {
            var d = res.d || {};
            var msg = frase('e_' + (d.code || ''), d.params, d.error || '');
            if (d.code === 'position_unreadable' && d.error) msg += ' — ' + d.error.split('—').slice(1).join('—').trim();
            say('<strong>' + esc(t('notFound')) + '</strong> — ' + esc(msg || d.error || ''), 'tl-note--warn');
            return;
          }
          fill(res.d);
        })
        .catch(function (e) { say(esc(String(e)), 'tl-note--warn'); })
        .then(function () { btn.disabled = false; });
    }
    btn.addEventListener('click', lookup);
    inp.addEventListener('keydown', function (ev) { if (ev.key === 'Enter') { ev.preventDefault(); lookup(); } });
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
  // ── Export: a memória de cálculo em Excel ────────────────────────────────
  // O botão é um `submit` de verdade, com `formaction`: sem este bloco ele
  // baixa do mesmo jeito. O fetch existe por UM motivo — haver um fim. Uma
  // navegação que resulta em download não emite evento nenhum no documento,
  // então um spinner ligado no clique ficaria girando para sempre, e um
  // spinner que ninguém desliga é pior do que spinner nenhum. Com o corpo na
  // mão sabemos exatamente quando o arquivo terminou de chegar.
  (function () {
    var btn = document.getElementById('tl-export');
    if (!btn || !btn.form || !window.fetch || !window.URL || !URL.createObjectURL) return;
    var form = btn.form, ocupado = false;

    function nomeDoCabecalho(cd) {
      // O Werkzeug manda os dois: o RFC 5987 com os acentos e o ASCII de
      // reserva. Sem ler o cabeçalho o arquivo salvaria com o nome da ROTA.
      var m = /filename\*=UTF-8''([^;]+)/i.exec(cd || '');
      if (m) { try { return decodeURIComponent(m[1]); } catch (e) { /* cai no ASCII */ } }
      m = /filename="?([^";]+)"?/i.exec(cd || '');
      return m ? m[1] : 'memoria.xlsx';
    }

    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (ocupado) return;
      ocupado = true;
      var antes = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>'
        + t('exporting');
      function terminar() { ocupado = false; btn.disabled = false; btn.innerHTML = antes; }
      fetch(btn.getAttribute('formaction'), {
        method: 'POST', credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new FormData(form)
      })
        .then(function (r) {
          if (!r.ok) {
            return r.json().catch(function () { return {}; }).then(function (j) {
              throw new Error(j.error || ('HTTP ' + r.status));
            });
          }
          var cd = r.headers.get('Content-Disposition') || '';
          return r.blob().then(function (b) { return { blob: b, nome: nomeDoCabecalho(cd) }; });
        })
        .then(function (res) {
          var url = URL.createObjectURL(res.blob), a = document.createElement('a');
          a.href = url; a.download = res.nome;
          document.body.appendChild(a); a.click(); a.remove();
          // revogar na mesma volta cancela o download no Firefox
          setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
          terminar();
        })
        .catch(function (e) {
          terminar();
          var msg = String((e && e.message) || e);
          if (window.Swal) Swal.fire({ icon: 'error', title: t('exportFail'), text: msg });
          else alert(t('exportFail') + ': ' + msg);
        });
    });
  })();
})();

/* Quotes — PTAX · Equities · Commodities, numa página só.
 *
 * Dois combobox: o de cima escolhe o TIPO, o de baixo o instrumento e só
 * habilita depois — sem o tipo não há lista para oferecer, e um campo aberto
 * pedindo um código que ele ainda não conhece é convite a erro.
 *
 * Uma tabela só para os três tipos: as colunas vêm do servidor a cada busca e a
 * DataTable é destruída e remontada. Manter três tabelas escondidas duplicaria a
 * toolbar, o filtro por coluna e o cell-copy — três cópias da mesma coisa para
 * mostrar uma de cada vez.
 *
 * ⚠️ A linha de filtro por coluna é montada ANTES do `.DataTable()`, com
 * `orderCellsTop: true` (CLAUDE.md §7): montada no `initComplete`, ela ficaria
 * no DOM e invisível.
 */
(function () {
  'use strict';

  var page = document.getElementById('quotes-page');
  if (!page) return;

  var OPTIONS = window.QT_OPTIONS || {};
  var ENDPOINT = {
    ptax:      '/api/quotes/ptax',
    equity:    '/api/quotes/equity',
    commodity: '/api/quotes/commodity'
  };
  // O nome do parâmetro muda com a aba: a PTAX pede uma MOEDA, as outras duas um
  // instrumento do cadastro.
  var PARAM = { ptax: 'currency', equity: 'instrument', commodity: 'instrument' };

  var state = { kind: '', from: page.dataset.dateFrom, to: page.dataset.dateTo };
  var dt = null, columns = [], hidden = {};
  // [código, símbolo] do tipo escolhido — o símbolo entra no rótulo da lista e
  // na validação, para a tela dizer ANTES da busca o que não está cadastrado.
  var current = [];

  // ── i18n dos textos montados em JS ───────────────────────────────────────
  // O I18nManager traduz os [data-lang] UMA vez, no load: o que o JS insere
  // depois nunca passa por ele (CLAUDE.md §2). Daí o mapa local.
  var _TRANS = {
    br: { searching: 'Buscando…', norows: 'Nenhuma cotação no período.',
          failed: 'Não consegui buscar', pick: 'Escolha o instrumento.',
          empty: 'Escolha o tipo, o instrumento e o período.',
          kind: 'Escolha o tipo de cotação.',
          currency: 'Moeda', instrument: 'Instrumento',
          unknown: 'não está na lista do tipo escolhido.',
          nosymbol: 'sem símbolo cadastrado — cadastre em Mapping ›',
          registered: 'com símbolo cadastrado' },
    es: { searching: 'Buscando…', norows: 'Sin cotizaciones en el período.',
          failed: 'No pude buscar', pick: 'Elija el instrumento.',
          empty: 'Elija el tipo, el instrumento y el período.',
          kind: 'Elija el tipo de cotización.',
          currency: 'Moneda', instrument: 'Instrumento',
          unknown: 'no está en la lista del tipo elegido.',
          nosymbol: 'sin símbolo registrado — regístrelo en Mapping ›',
          registered: 'con símbolo registrado' },
    en: { searching: 'Searching…', norows: 'No quotes in the period.',
          failed: 'Could not fetch', pick: 'Pick the instrument.',
          empty: 'Pick the type, the instrument and the period.',
          kind: 'Pick the quote type.',
          currency: 'Currency', instrument: 'Instrument',
          unknown: 'is not in the list for the selected type.',
          nosymbol: 'has no symbol registered — add it in Mapping ›',
          registered: 'with a registered symbol' }
  };
  function t(k) {
    var lang = 'en';
    try { lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    return (_TRANS[lang] || _TRANS.en)[k] || _TRANS.en[k] || k;
  }

  function iso2br(s) {
    var p = String(s || '').split('-');
    return p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : '';
  }

  // ── Tipo → instrumento ───────────────────────────────────────────────────
  function selectKind(kind) {
    state.kind = kind;
    current = OPTIONS[kind] || [];
    var inp = document.getElementById('qt-instrument');
    var lbl = document.getElementById('qtInstrumentLabel');
    var list = document.getElementById('qtInstrumentList');
    var hint = document.getElementById('qtSymbolHint');

    inp.value = '';
    list.innerHTML = '';
    inp.disabled = !kind;
    document.getElementById('qtSearch').disabled = !kind;
    if (lbl) lbl.textContent = (kind === 'ptax') ? t('currency') : t('instrument');

    if (!kind) {
      inp.placeholder = '—';
      hint.textContent = '';
      clearTable(t('kind'));
      return;
    }
    current.forEach(function (pair) {
      var o = document.createElement('option');
      o.value = pair[0];
      // O símbolo aparece na própria lista: quem escolhe vê na hora o que está
      // cadastrado e o que vai pedir cadastro.
      if (pair[1] && pair[1] !== pair[0]) o.label = pair[0] + ' → ' + pair[1];
      list.appendChild(o);
    });
    inp.placeholder = current.length ? current[0][0] : '—';
    if (kind === 'ptax') inp.value = 'USD';
    var comSimbolo = current.filter(function (p) { return !!p[1]; }).length;
    hint.textContent = (kind === 'ptax') ? ''
      : current.length + ' — ' + comSimbolo + ' ' + t('registered');
    clearTable(t('empty'));
  }

  /* O código escolhido, validado contra a lista do tipo. Devolve
     {code, symbol} ou uma mensagem — o combobox é texto livre (é o preço do
     type-ahead nativo), então digitar qualquer coisa é possível. */
  function chosen() {
    var v = (document.getElementById('qt-instrument').value || '').trim();
    if (!v) return { error: t('pick') };
    var key = v.toUpperCase().replace(/\s+/g, ' ');
    var hit = null;
    for (var i = 0; i < current.length; i++) {
      if (current[i][0].toUpperCase().replace(/\s+/g, ' ') === key) { hit = current[i]; break; }
    }
    if (!hit) return { error: '“' + v + '” ' + t('unknown') };
    if (state.kind !== 'ptax' && !hit[1]) {
      return { error: '“' + hit[0] + '” ' + t('nosymbol') + ' Quotes.' };
    }
    return { code: hit[0], symbol: hit[1] };
  }

  // ── Tabela ───────────────────────────────────────────────────────────────
  function clearTable(msg) {
    if (dt) { dt.destroy(); dt = null; }
    document.getElementById('qtHead').innerHTML = '';
    document.getElementById('qtFilterRow').innerHTML = '';
    document.querySelector('#quotes-table tbody').innerHTML = '';
    document.getElementById('qtCount').textContent = '0';
    var empty = document.getElementById('qtEmpty');
    empty.style.display = '';
    empty.querySelector('span').textContent = msg;
    columns = [];
  }

  function buildTable(cols, rows) {
    if (dt) { dt.destroy(); dt = null; }
    columns = cols.slice();
    hidden = {};
    document.getElementById('qtEmpty').style.display = 'none';

    var head = document.getElementById('qtHead');
    var filt = document.getElementById('qtFilterRow');
    head.innerHTML = '';
    filt.innerHTML = '';
    cols.forEach(function (c, i) {
      var th = document.createElement('th');
      th.textContent = c;
      head.appendChild(th);
      // Filtro por coluna: input pequeno, centralizado, placeholder = o nome da
      // coluna. O CSS do centro vem do visual-refresh.css (regra estrutural).
      var tf = document.createElement('th');
      var inp = document.createElement('input');
      inp.type = 'text';
      inp.className = 'form-control form-control-sm qt-col-filter';
      inp.setAttribute('data-col', String(i));
      inp.placeholder = c;
      inp.title = 'blank = empty cells';
      inp.style.fontSize = '12px';
      inp.style.height = '28px';
      tf.appendChild(inp);
      filt.appendChild(tf);
    });

    var tbody = document.querySelector('#quotes-table tbody');
    tbody.innerHTML = '';

    dt = jQuery('#quotes-table').DataTable({
      data: rows,
      columns: cols.map(function () { return {}; }),
      scrollX: false, autoWidth: true, orderCellsTop: true, deferRender: true,
      pageLength: parseInt(document.getElementById('qtPageLen').value, 10) || 50,
      lengthMenu: [[25, 50, 100, -1], [25, 50, 100, 'All']],
      order: [],
      dom: "<'row'<'col-sm-12'tr>><'d-md-flex justify-content-between align-items-center mt-2'ip>",
      language: { paginate: {
        first: '<i class="ti ti-chevrons-left"></i>',
        previous: '<i class="ti ti-chevron-left"></i>',
        next: '<i class="ti ti-chevron-right"></i>',
        last: '<i class="ti ti-chevrons-right"></i>'
      } }
    });

    // Export completo (Copy · CSV · Excel · Print · PDF) disparado pelo dropdown
    // da toolbar: a tabela nasce sem `buttons:`, então os botões são criados
    // depois e acionados por nome (CLAUDE.md §3).
    new jQuery.fn.dataTable.Buttons(dt, {
      buttons: [
        { extend: 'copy',  name: 'copy',  exportOptions: exportOpts() },
        // ';' + BOM: é o que o Excel pt-BR precisa para separar colunas e manter
        // acento.
        { extend: 'csv',   name: 'csv',   fieldSeparator: ';', bom: true, exportOptions: exportOpts() },
        { extend: 'excel', name: 'excel', exportOptions: exportOpts() },
        { extend: 'print', name: 'print', exportOptions: exportOpts() },
        { extend: 'pdfHtml5', name: 'pdf', orientation: 'landscape',
          pageSize: 'A4', exportOptions: exportOpts() }
      ]
    });

    // Seleção de célula + Ctrl/Cmd+C (table-std.js). Sem `skip`: aqui não há
    // checkbox nem coluna de ações.
    if (window.otcCellCopy) window.otcCellCopy('#quotes-table', {});

    jQuery('#quotes-table thead').off('keyup.qt change.qt')
      .on('keyup.qt change.qt', '.qt-col-filter', function () {
        var col = +this.getAttribute('data-col');
        var v = this.value || '';
        // `blank` procura a célula VAZIA — é o único jeito de procurar a
        // ausência, e o smart search precisa sair para a regex casar.
        if (v.trim().toLowerCase() === 'blank') {
          dt.column(col).search('^\\s*$', true, false).draw();
        } else if (dt.column(col).search() !== v) {
          dt.column(col).search(v).draw();
        }
      });

    document.getElementById('qtCount').textContent = String(rows.length);
    buildColumnsMenu();
    adjust();
    if (window.lucide && lucide.createIcons) lucide.createIcons();
  }

  function exportOpts() {
    // Exporta o que está NA TELA: filtros e ordenação aplicados, só colunas
    // visíveis.
    return { columns: ':visible', modifier: { search: 'applied', order: 'applied', page: 'all' } };
  }

  function adjust() {
    if (!dt) return;
    dt.columns.adjust();
    setTimeout(function () { if (dt) dt.columns.adjust().draw(false); }, 150);
  }
  window.addEventListener('resize', adjust);

  function buildColumnsMenu() {
    var menu = document.getElementById('qtColumnsMenu');
    menu.innerHTML = '';
    columns.forEach(function (c, i) {
      var id = 'qtcol-' + i;
      var row = document.createElement('div');
      row.className = 'form-check';
      row.innerHTML = '<input class="form-check-input" type="checkbox" id="' + id + '" checked>' +
                      '<label class="form-check-label fs-xs" for="' + id + '"></label>';
      row.querySelector('label').textContent = c;
      row.querySelector('input').addEventListener('change', function () {
        hidden[i] = !this.checked;
        dt.column(i).visible(this.checked);
        adjust();
      });
      menu.appendChild(row);
    });
  }

  // ── Busca ────────────────────────────────────────────────────────────────
  function search() {
    if (!state.kind) { clearTable(t('kind')); return; }
    var pick = chosen();
    if (pick.error) {
      clearTable(pick.error);
      if (window.Swal) Swal.fire({ icon: 'info', text: pick.error });
      return;
    }
    var url = ENDPOINT[state.kind] + '?' + PARAM[state.kind] + '=' + encodeURIComponent(pick.code) +
              '&from=' + encodeURIComponent(state.from) + '&to=' + encodeURIComponent(state.to);
    var btn = document.getElementById('qtSearch');
    btn.disabled = true;
    clearTable(t('searching'));
    fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (!res.ok || !res.d || !res.d.success) {
          var msg = (res.d && res.d.error) || t('failed');
          clearTable(msg);
          if (window.Swal) Swal.fire({ icon: 'error', title: t('failed'), text: msg });
          return;
        }
        if (res.d.symbol) document.getElementById('qtSymbolHint').textContent = '→ ' + res.d.symbol;
        if (!res.d.rows.length) { clearTable(t('norows')); return; }
        buildTable(res.d.columns, res.d.rows);
      })
      .catch(function (e) { clearTable(t('failed') + ': ' + e); })
      .then(function () { btn.disabled = false; });
  }

  // ── Datas ────────────────────────────────────────────────────────────────
  function wireDates(attempt) {
    if (window.jQuery && jQuery.fn.daterangepicker && window.moment) {
      [['#qt-from', 'from'], ['#qt-to', 'to']].forEach(function (pair) {
        var $d = jQuery(pair[0]), key = pair[1];
        $d.daterangepicker({
          singleDatePicker: true, autoApply: true, showDropdowns: true,
          locale: { format: 'DD/MM/YYYY' },
          startDate: moment(state[key], 'YYYY-MM-DD'),
          maxDate: moment()
        }, function (start) { state[key] = start.format('YYYY-MM-DD'); });
        $d.closest('.qt-datewrap').find('.qt-cal-btn').on('click', function () { $d.trigger('click'); });
      });
      return;
    }
    attempt = attempt || 0;
    if (attempt < 40) { setTimeout(function () { wireDates(attempt + 1); }, 50); return; }
    // Sem o plugin, os campos viram texto editável em vez de ficarem inertes.
    ['from', 'to'].forEach(function (key) {
      var inp = document.getElementById('qt-' + key);
      inp.removeAttribute('readonly');
      inp.value = iso2br(state[key]);
      inp.addEventListener('change', function () {
        var m = (this.value || '').match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
        if (m) state[key] = m[3] + '-' + m[2] + '-' + m[1];
      });
    });
  }

  // ── Ligações ─────────────────────────────────────────────────────────────
  document.getElementById('qt-kind').addEventListener('change', function () {
    selectKind(this.value);
  });
  document.getElementById('qtSearch').addEventListener('click', search);
  document.getElementById('qt-instrument').addEventListener('keydown', function (ev) {
    if (ev.key === 'Enter') search();
  });
  document.getElementById('qtPageLen').addEventListener('change', function () {
    if (dt) { dt.page.len(parseInt(this.value, 10)).draw(); adjust(); }
  });
  document.getElementById('qtClearFilters').addEventListener('click', function () {
    page.querySelectorAll('.qt-col-filter').forEach(function (i) { i.value = ''; });
    if (dt) dt.columns().search('').draw();
  });
  page.querySelectorAll('[data-export]').forEach(function (a) {
    a.addEventListener('click', function (ev) {
      ev.preventDefault();
      if (dt) dt.button(this.getAttribute('data-export') + ':name').trigger();
    }.bind(a));
  });

  document.getElementById('qt-from').value = iso2br(state.from);
  document.getElementById('qt-to').value = iso2br(state.to);
  wireDates();
  // Nasce sem tipo escolhido: é o que deixa o segundo combobox desabilitado, que
  // foi o desenho pedido.
  selectKind('');
})();

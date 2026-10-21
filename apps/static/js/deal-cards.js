/* ============================================================================
 * deal-cards.js — as operações em CARDS, no lugar da tabela de dezenas de
 * colunas (mesa, 21/10/2026, §650): New Deals › Swap (Bullet, Cashflow,
 * Cetes). Um card por operação: a caixa de seleção, o status, o que identifica
 * a operação, os números que a mesa confere e os botões de ação da casa
 * (Confirm · Edit · Delete · Send, o squircle e as cores do §7). O duplo
 * clique abre o preview do arquivo da B3.
 *
 * Só DESENHA e AVISA: a página continua dona dos dados (a lista de operações,
 * o conjunto `selected`) e das ações — este arquivo chama as funções que ela
 * passa. A DataTable da página segue por baixo, escondida, como a fonte do
 * Export (Copy · CSV · Excel · Print · PDF · Advanced), que é o export da casa.
 *
 *   var cards = otcDealCards({
 *     el: '#swbCards', selected: selected, key: function (e) { return e._id; },
 *     title: fn(e) → texto, subtitle: fn(e) → texto, status: fn(e) → HTML,
 *     facts: [{label, value: fn(e) → texto, wide: bool}], meta: fn(e) → texto,
 *     canConfirm: fn(e), canSend: fn(e), t: fn(chave, padrão),
 *     onConfirm / onEdit / onDelete / onSend / onPreview: fn(chave),
 *     onSelect: fn()                       // a seleção mudou
 *   });
 *   cards.render(lista);  cards.selectAll(true|false);  cards.sync();
 * ========================================================================== */
(function () {
  'use strict';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function tr(o, k, d) { return (o.t && o.t(k, d)) || d; }

  function botao(cls, cor, icone, titulo, tipCls) {
    return '<a href="#" class="btn ' + cor + ' btn-sm rounded-circle ' + cls + '" data-bs-toggle="tooltip" ' +
      'data-bs-placement="auto" data-bs-title="' + esc(titulo) + '" data-bs-custom-class="' + tipCls + '" ' +
      'aria-label="' + esc(titulo) + '"><i class="ti ' + icone + '"></i></a>';
  }

  window.otcDealCards = function (o) {
    var el = typeof o.el === 'string' ? document.querySelector(o.el) : o.el;
    var sel = o.selected || new Set();
    var lista = [];
    el.classList.add('otc-deal-grid');

    function card(e) {
      var k = o.key(e), on = sel.has(k);
      var facts = (o.facts || []).map(function (f) {
        var v = f.value(e);
        return '<div' + (f.wide ? ' class="is-wide"' : '') + '><dt>' + esc(f.label) + '</dt><dd>' +
          (v === '' || v == null ? '<span class="otc-deal-card__none">—</span>' : esc(v)) + '</dd></div>';
      }).join('');
      var acoes =
        botao('btn-row-confirm' + (o.canConfirm && !o.canConfirm(e) ? ' d-none' : ''), 'btn-success', 'ti-check', tr(o, 'nd-card-confirm', 'Confirm'), 'tooltip-success') +
        botao('btn-row-edit', 'btn-info', 'ti-edit', tr(o, 'nd-card-edit', 'Edit'), 'tooltip-info') +
        botao('btn-row-delete', 'btn-danger', 'ti-trash', tr(o, 'nd-card-delete', 'Delete'), 'tooltip-danger') +
        botao('btn-row-send' + (o.canSend && !o.canSend(e) ? ' d-none' : ''), 'btn-primary', 'ti-brand-telegram', tr(o, 'nd-card-send', 'Send'), 'tooltip-primary');
      return '<div class="otc-deal-card' + (on ? ' is-selected' : '') + '" data-key="' + esc(k) + '" tabindex="0" ' +
        'title="' + esc(tr(o, 'nd-card-dblclick', 'Double-click to preview the B3 files')) + '">' +
        '<div class="otc-deal-card__head">' +
          '<input class="form-check-input form-check-input-light otc-deal-card__check" type="checkbox"' + (on ? ' checked' : '') +
          ' aria-label="' + esc(tr(o, 'nd-card-select', 'Select')) + '">' +
          '<div class="otc-deal-card__title"><b>' + esc(o.title(e)) + '</b>' +
            (o.subtitle ? '<small>' + esc(o.subtitle(e)) + '</small>' : '') + '</div>' +
          (o.status ? o.status(e) : '') +
        '</div>' +
        '<dl class="otc-deal-card__facts">' + facts + '</dl>' +
        '<div class="otc-deal-card__foot"><span class="otc-deal-card__meta">' + esc(o.meta ? o.meta(e) : '') + '</span>' +
          '<div class="otc-deal-card__actions">' + acoes + '</div></div>' +
      '</div>';
    }

    function render(novos) {
      lista = novos || [];
      el.innerHTML = lista.length ? lista.map(card).join('')
        : '<div class="otc-deal-empty"><i class="ti ti-inbox"></i><span>' +
          esc(tr(o, 'nd-card-empty', 'No operations for these filters.')) + '</span></div>';
    }

    // a seleção mudou fora daqui (Select all, Send, Delete): só os checks
    function sync() {
      el.querySelectorAll('.otc-deal-card').forEach(function (c) {
        var on = sel.has(c.getAttribute('data-key'));
        c.classList.toggle('is-selected', on);
        var cb = c.querySelector('.otc-deal-card__check');
        if (cb) cb.checked = on;
      });
    }

    function selectAll(on) {
      sel.clear();
      if (on) lista.forEach(function (e) { sel.add(o.key(e)); });
      sync();
      if (o.onSelect) o.onSelect();
    }

    function chaveDe(alvo) {
      var c = alvo.closest && alvo.closest('.otc-deal-card');
      return c ? c.getAttribute('data-key') : null;
    }

    el.addEventListener('change', function (ev) {
      if (!ev.target.classList.contains('otc-deal-card__check')) return;
      var k = chaveDe(ev.target);
      if (!k) return;
      if (ev.target.checked) sel.add(k); else sel.delete(k);
      ev.target.closest('.otc-deal-card').classList.toggle('is-selected', ev.target.checked);
      if (o.onSelect) o.onSelect();
    });
    el.addEventListener('click', function (ev) {
      var b = ev.target.closest('.btn-row-confirm, .btn-row-edit, .btn-row-delete, .btn-row-send');
      if (!b) return;
      ev.preventDefault();
      var k = chaveDe(b);
      if (!k) return;
      var tip = window.bootstrap && bootstrap.Tooltip.getInstance(b);
      if (tip) tip.hide();
      if (b.classList.contains('btn-row-confirm') && o.onConfirm) o.onConfirm(k);
      else if (b.classList.contains('btn-row-edit') && o.onEdit) o.onEdit(k);
      else if (b.classList.contains('btn-row-delete') && o.onDelete) o.onDelete(k);
      else if (b.classList.contains('btn-row-send') && o.onSend) o.onSend(k);
    });
    // duplo clique = o preview (fora da caixa e dos botões); sem selecionar texto
    el.addEventListener('mousedown', function (ev) {
      if (ev.detail > 1 && ev.target.closest('.otc-deal-card') && !ev.target.closest('input, a, button')) ev.preventDefault();
    });
    el.addEventListener('dblclick', function (ev) {
      if (ev.target.closest('input, a, button')) return;
      var k = chaveDe(ev.target);
      if (k && o.onPreview) o.onPreview(k);
    });
    el.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' || !ev.target.classList.contains('otc-deal-card')) return;
      var k = chaveDe(ev.target);
      if (k && o.onPreview) { ev.preventDefault(); o.onPreview(k); }
    });
    // tooltip colorido no primeiro hover (os cards são reescritos a cada busca)
    el.addEventListener('mouseover', function (ev) {
      var b = ev.target.closest && ev.target.closest('[data-bs-toggle="tooltip"]');
      if (b && window.bootstrap && !bootstrap.Tooltip.getInstance(b)) new bootstrap.Tooltip(b).show();
    });

    return { render: render, sync: sync, selectAll: selectAll, list: function () { return lista; } };
  };
})();

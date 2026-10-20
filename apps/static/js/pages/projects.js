/* projects.js — a lista das iniciativas (Intraday › Initiatives; a rota e a
   API seguem /projects): os contadores, os filtros por CATEGORIA e por
   status, os cartões e o "New initiative". O desenho das peças e as frases
   estão no projects-common.js (OtcPj). */
(function () {
  'use strict';
  var P = window.OtcPj;
  var t = P.t, esc = P.esc;
  // `cat`: '' = todas, '__none' = as de antes da categoria. Lembrada por quem
  // vê (conveniência; sem localStorage a tela abre em todas).
  var CAT_KEY = 'otc_pj_category';
  var state = { projects: [], filter: '', cat: '' };
  try { state.cat = localStorage.getItem(CAT_KEY) || ''; } catch (e) {}

  function $(id) { return document.getElementById(id); }

  function load() {
    return P.api('GET', '/api/projects').then(function (d) {
      P.setMeta(d);
      state.projects = d.projects || [];
      if (window.otcPins) window.otcPins.sync(state.projects, true);
      render();
    }).catch(function (e) {
      P.metaFailed();
      var box = $('pj-load-error');
      box.textContent = P.errText(e);
      box.classList.remove('d-none');
    });
  }

  function naCategoria(p) {
    if (!state.cat) return true;
    return state.cat === '__none' ? !p.category : p.category === state.cat;
  }

  // os contadores do topo acompanham a CATEGORIA escolhida (o status é o que
  // eles contam, então o filtro de status não entra)
  function counts() {
    var c = { 'On going': 0, 'On hold': 0, 'Concluded': 0, month: 0 };
    var hoje = P.isoToday().slice(0, 7);
    state.projects.filter(naCategoria).forEach(function (p) {
      c[p.status] = (c[p.status] || 0) + 1;
      if (p.status !== 'Concluded' && (p.due_date || '').slice(0, 7) === hoje) c.month++;
    });
    return c;
  }

  function render() {
    var c = counts();
    $('pj-n-ongoing').textContent = c['On going'];
    $('pj-n-onhold').textContent = c['On hold'];
    $('pj-n-concluded').textContent = c['Concluded'];
    $('pj-n-month').textContent = c.month;
    $('pj-sub').textContent = [
      c['On going'] + ' ' + P.tStatus('On going').toLowerCase(),
      c['On hold'] + ' ' + P.tStatus('On hold').toLowerCase(),
      c['Concluded'] + ' ' + P.tStatus('Concluded').toLowerCase()
    ].join(' · ');

    renderCatMenu();
    var lista = state.projects.filter(function (p) { return naCategoria(p) && (!state.filter || p.status === state.filter); });
    $('pj-grid').innerHTML = lista.map(card).join('');
    var vazio = !lista.length;
    $('pj-empty').classList.toggle('d-none', !vazio);
    if (vazio && state.projects.length) {
      $('pj-empty-title').textContent = t(state.cat ? 'none_filter' : 'none_status');
      $('pj-empty-sub').textContent = '';
    }
    P.icons($('pj-grid'));
    P.icons($('pj-f-cat'));
  }

  function renderCatMenu() {
    var n = {}, semCat = 0;
    state.projects.forEach(function (p) { if (p.category) n[p.category] = (n[p.category] || 0) + 1; else semCat++; });
    // categoria lembrada que não existe mais na lista (ou "sem categoria" sem nenhuma) volta a todas
    if (state.cat === '__none' && !semCat) state.cat = '';
    var cats = P.categories();
    if (state.cat && state.cat !== '__none' && cats.indexOf(state.cat) === -1) state.cat = '';
    function item(value, label, right, on) {
      return '<button type="button" class="dropdown-item' + (on ? ' is-on' : '') + '" data-value="' + esc(value) + '">' + label +
        '<small>' + esc(String(right)) + '</small><i data-lucide="check" class="tk-check"></i></button>';
    }
    function dot(hue) { return '<span class="pj-dot" style="--hue:' + hue + '"></span>'; }
    $('pj-menu-cat').innerHTML =
      item('', dot('var(--otc-accent-ink)') + esc(t('all_categories')), state.projects.length, !state.cat) +
      cats.map(function (c) { return item(c, dot(P.CATEGORY_HUE[c] || 'var(--otc-text-3)') + esc(P.tCat(c)), n[c] || 0, state.cat === c); }).join('') +
      (semCat ? item('__none', dot('var(--otc-text-3)') + esc(t('no_category')), semCat, state.cat === '__none') : '');
    $('pj-f-cat-label').textContent = !state.cat ? t('all_categories') : (state.cat === '__none' ? t('no_category') : P.tCat(state.cat));
    $('pj-f-cat').classList.toggle('is-on', !!state.cat);
    P.icons($('pj-menu-cat'));
  }

  function card(p) {
    var hue = P.colorVar(p.color);
    var pinned = window.otcPins && window.otcPins.has(p.id);
    var ms;
    if (p.status === 'Concluded') {
      ms = '<div class="pj-card__ms-label">' + esc(P.tStatus('Concluded')) + '</div>' +
           '<div class="pj-card__ms-title">' + esc(p.milestones_total ? t('all_ms') : t('done_proj')) + '</div>' +
           '<div class="pj-card__ms-date">' + esc(P.fmtDate(p.due_date)) + '</div>';
    } else if (p.next_milestone) {
      var quando = p.next_milestone.date ? P.fmtDate(p.next_milestone.date) + ' · ' + P.inDays(p.next_milestone.date) : t('no_date');
      ms = '<div class="pj-card__ms-label">' + esc(t('next_ms')) + '</div>' +
           '<div class="pj-card__ms-title">' + esc(p.next_milestone.title) + '</div>' +
           '<div class="pj-card__ms-date">' + esc(quando) + '</div>';
    } else {
      ms = '<div class="pj-card__ms-label">' + esc(t('next_ms')) + '</div>' +
           '<div class="pj-card__ms-title text-muted">' + esc(t('no_ms')) + '</div>';
    }
    return '<div class="pj-card-panel" data-href="/projects/' + esc(encodeURIComponent(p.id)) + '" style="--hue:' + hue + '">' +
      '<div class="pj-card__top">' +
        '<span class="otc-icon-tile pj-card__icon" style="--hue:' + hue + '"><i data-lucide="' + esc(p.icon) + '"></i></span>' +
        '<div class="pj-card__ttl"><a class="pj-card__name" href="/projects/' + esc(encodeURIComponent(p.id)) + '">' + esc(p.name) + '</a>' +
          '<span class="pj-card__chips">' + P.chip(P.tStatus(p.status), P.STATUS_HUE[p.status] || 'var(--otc-text-3)') + P.catChip(p.category) + '</span></div>' +
        '<button type="button" class="pj-star' + (pinned ? ' is-on' : '') + '" data-pin="' + esc(p.id) + '" aria-pressed="' + (pinned ? 'true' : 'false') + '" title="' + esc(t('pin')) + '"><i data-lucide="star"></i></button>' +
      '</div>' +
      '<p class="pj-card__desc">' + esc(p.description || '') + '</p>' +
      '<div class="pj-card__ms"><div class="pj-ring" style="--p:' + (+p.progress || 0) + ';--hue:' + hue + '"><span>' + (+p.progress || 0) + '%</span></div><div>' + ms + '</div></div>' +
      '<div class="pj-card__foot">' + P.avatars(p.people, 4) +
        '<span class="pj-meta">' + esc(t('n_tasks', { done: p.tasks_done, total: p.tasks_total })) + '</span>' +
        (p.due_date ? '<span class="pj-meta"><i data-lucide="calendar"></i>' + esc(P.fmtDate(p.due_date)) + '</span>' : '') +
      '</div>' +
    '</div>';
  }

  function wire() {
    $('pj-menu-cat').addEventListener('click', function (e) {
      var b = e.target.closest('[data-value]');
      if (!b) return;
      state.cat = b.getAttribute('data-value');
      try { if (state.cat) localStorage.setItem(CAT_KEY, state.cat); else localStorage.removeItem(CAT_KEY); } catch (er) {}
      render();
    });
    $('pj-filter').addEventListener('click', function (e) {
      var a = e.target.closest('[data-status]');
      if (!a) return;
      e.preventDefault();
      state.filter = a.getAttribute('data-status');
      Array.prototype.forEach.call(this.querySelectorAll('.nav-link'), function (x) { x.classList.toggle('active', x === a); });
      render();
    });
    $('pj-grid').addEventListener('click', function (e) {
      var star = e.target.closest('[data-pin]');
      if (star) {
        e.preventDefault(); e.stopPropagation();
        var p = state.projects.filter(function (x) { return x.id === star.getAttribute('data-pin'); })[0];
        if (p && window.otcPins) {
          var on = window.otcPins.toggle(p);
          star.classList.toggle('is-on', on);
          star.setAttribute('aria-pressed', on ? 'true' : 'false');
        }
        return;
      }
      if (e.target.closest('a')) return;
      var c = e.target.closest('[data-href]');
      if (c) window.location.href = c.getAttribute('data-href');
    });
    $('pj-new').addEventListener('click', function () {
      P.openProjectModal({
        mode: 'new',
        onSaved: function (d) { window.location.href = '/projects/' + encodeURIComponent(d.project.id); }
      });
    });
  }

  wire();
  load();
})();

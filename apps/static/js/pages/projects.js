/* projects.js — a lista de projetos (Intraday › Projects): os contadores, o
   filtro por status, os cartões e o "New project". O desenho das peças e as
   frases estão no projects-common.js (OtcPj). */
(function () {
  'use strict';
  var P = window.OtcPj;
  var t = P.t, esc = P.esc;
  var state = { projects: [], filter: '' };

  function $(id) { return document.getElementById(id); }

  function load() {
    return P.api('GET', '/api/projects').then(function (d) {
      P.setMeta(d);
      state.projects = d.projects || [];
      if (window.otcPins) window.otcPins.sync(state.projects, true);
      render();
    }).catch(function (e) {
      var box = $('pj-load-error');
      box.textContent = P.errText(e);
      box.classList.remove('d-none');
    });
  }

  function counts() {
    var c = { 'On going': 0, 'On hold': 0, 'Concluded': 0, month: 0 };
    var hoje = P.isoToday().slice(0, 7);
    state.projects.forEach(function (p) {
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

    var lista = state.projects.filter(function (p) { return !state.filter || p.status === state.filter; });
    $('pj-grid').innerHTML = lista.map(card).join('');
    var vazio = !lista.length;
    $('pj-empty').classList.toggle('d-none', !vazio);
    if (vazio && state.projects.length) {
      $('pj-empty-title').textContent = t('none_status');
      $('pj-empty-sub').textContent = '';
    }
    P.icons($('pj-grid'));
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
          P.chip(P.tStatus(p.status), P.STATUS_HUE[p.status] || 'var(--otc-text-3)') + '</div>' +
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

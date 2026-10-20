/* tasks.js — Intraday › Tasks: as tarefas de TODOS os projetos num quadro por
   status (arrastar o card de uma coluna para outra muda o status) ou numa lista
   agrupada, com os filtros de projeto, "só as minhas", prioridade e texto.
   Mover, abrir e criar passam pelas mesmas peças da página do projeto
   (projects-common.js); cada escrita devolve o projeto e a tela troca as
   tarefas DELE na lista. */
(function () {
  'use strict';
  var P = window.OtcPj;
  var t = P.t, esc = P.esc;
  var COLS = ['To do', 'In progress', 'In review', 'Done'];
  var VIEW_KEY = '__OTC_TASKS_VIEW__';
  var state = { tasks: [], projects: [], view: 'board', project: '', mine: false, prio: '', q: '', sort: 'due', closed: {} };

  function $(id) { return document.getElementById(id); }
  try { state.view = localStorage.getItem(VIEW_KEY) === 'list' ? 'list' : 'board'; } catch (e) {}

  function load() {
    return P.api('GET', '/api/tasks').then(function (d) {
      P.setMeta(d);
      state.tasks = d.tasks || [];
      state.projects = d.projects || [];
      renderAll();
    }).catch(function (e) {
      var box = $('tk-load-error');
      box.textContent = P.errText(e);
      box.classList.remove('d-none');
    });
  }

  // Uma escrita devolve o projeto inteiro: as tarefas dele na lista são
  // trocadas pelas que voltaram (e o projeto, se sumiu, sai junto).
  function applyProject(p) {
    if (!p) return;
    state.tasks = state.tasks.filter(function (x) { return x.project_id !== p.id; }).concat(
      (p.tasks || []).map(function (x) {
        var o = Object.assign({}, x);
        o.project_id = p.id; o.project_name = p.name; o.project_color = p.color; o.project_status = p.status;
        return o;
      }));
    state.projects.forEach(function (q) {
      if (q.id === p.id) {
        q.name = p.name; q.color = p.color; q.status = p.status;
        q.open = (p.tasks || []).filter(function (x) { return x.status !== 'Done'; }).length;
      }
    });
    renderAll();
  }

  // ── filtros ─────────────────────────────────────────────────────────────
  function visible() {
    var me = (P.meta.me && P.meta.me.sid) || '';
    var q = state.q.trim().toLowerCase();
    return state.tasks.filter(function (x) {
      if (state.project && x.project_id !== state.project) return false;
      if (state.mine && x.assignee_sid !== me) return false;
      if (state.prio && x.priority !== state.prio) return false;
      if (q) {
        var hay = [x.title, x.project_name, x.assignee_name].join(' ').toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
  }
  var PRIO_RANK = { Urgent: 0, High: 1, Medium: 2, Low: 3 };
  function sortTasks(list, by) {
    return list.slice().sort(function (a, b) {
      var da = a.due || '9999-12-31', db = b.due || '9999-12-31';
      var pa = PRIO_RANK[a.priority] == null ? 9 : PRIO_RANK[a.priority], pb = PRIO_RANK[b.priority] == null ? 9 : PRIO_RANK[b.priority];
      if (by === 'priority') return pa - pb || (da < db ? -1 : da > db ? 1 : 0);
      return (da < db ? -1 : da > db ? 1 : 0) || pa - pb;
    });
  }

  // ── contadores ──────────────────────────────────────────────────────────
  function weekBounds() {
    var h = P.parse(P.isoToday());
    var dow = (h.getDay() + 6) % 7;                    // segunda = 0
    var seg = new Date(h); seg.setDate(h.getDate() - dow);
    var dom = new Date(seg); dom.setDate(seg.getDate() + 6);
    var iso = function (d) { return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) + '-' + ('0' + d.getDate()).slice(-2); };
    return { mon: iso(seg), sun: iso(dom), today: iso(h) };
  }
  function renderStats() {
    var w = weekBounds();
    var open = 0, week = 0, late = 0, doneWeek = 0, projs = {};
    state.tasks.forEach(function (x) {
      if (x.status === 'Done') {
        if ((x.done_at || '').slice(0, 10) >= w.mon) doneWeek++;
        return;
      }
      open++;
      projs[x.project_id] = 1;
      if (x.due && x.due < w.today) late++;
      else if (x.due && x.due <= w.sun) week++;
    });
    $('tk-n-open').textContent = open;
    $('tk-n-week').textContent = week;
    $('tk-n-overdue').textContent = late;
    $('tk-n-overdue').closest('.otc-stat').classList.toggle('is-alert', late > 0);   // atraso em vermelho, como no Pane
    $('tk-n-doneweek').textContent = doneWeek;
    $('tk-sub').textContent = t('open_across', { n: open, m: Object.keys(projs).length });
    $('tk-no-projects').classList.toggle('d-none', state.projects.length > 0);
    $('tk-new').disabled = !state.projects.length;
  }

  function renderFilters() {
    var proj = state.projects.filter(function (p) { return p.id === state.project; })[0];
    $('tk-f-project-label').textContent = proj ? proj.name : t('all_projects');
    $('tk-f-project').classList.toggle('is-on', !!proj);
    var openAll = state.projects.reduce(function (s, p) { return s + (p.open || 0); }, 0);
    $('tk-menu-project').innerHTML =
      item('', '<span class="pj-dot" style="--hue:var(--otc-accent-ink)"></span>' + esc(t('all_projects')), t('n_open', { n: openAll }), !state.project) +
      state.projects.map(function (p) {
        return item(p.id, '<span class="pj-dot" style="--hue:' + P.colorVar(p.color) + '"></span>' + esc(p.name), t('n_open', { n: p.open || 0 }), state.project === p.id);
      }).join('');
    $('tk-f-prio-label').textContent = state.prio ? P.tPrio(state.prio) : t('any_priority');
    $('tk-f-prio').classList.toggle('is-on', !!state.prio);
    $('tk-menu-prio').innerHTML = item('', esc(t('any_priority')), '', !state.prio) +
      ['Urgent', 'High', 'Medium', 'Low'].map(function (p) { return item(p, esc(P.tPrio(p)), '', state.prio === p); }).join('');
    var me = P.meta.me || {};
    $('tk-f-mine-av').innerHTML = me.sid ? P.avatar(me.sid, me.name, 'sm') : '';
    $('tk-f-mine').classList.toggle('is-on', state.mine);
    $('tk-f-mine').setAttribute('aria-pressed', state.mine ? 'true' : 'false');
  }
  function item(value, label, right, on) {
    return '<button type="button" class="dropdown-item' + (on ? ' is-on' : '') + '" data-value="' + esc(value) + '">' + label +
      (right ? '<small>' + esc(right) + '</small>' : '') + '<i data-lucide="check" class="tk-check"></i></button>';
  }

  // ── quadro ──────────────────────────────────────────────────────────────
  function renderBoard(list) {
    $('tk-board').innerHTML = COLS.map(function (st) {
      var grp = sortTasks(list.filter(function (x) { return x.status === st; }), 'due');
      if (st === 'Done') grp.sort(function (a, b) { return (b.done_at || '') < (a.done_at || '') ? -1 : 1; });
      return '<div class="tk-col-panel" data-col="' + esc(st) + '">' +
        '<div class="tk-col__head"><span class="pj-dot" style="--hue:' + P.TASK_HUE[st] + '"></span>' + esc(P.tTask(st)) +
          ' <span class="otc-count">' + grp.length + '</span>' +
          '<button type="button" class="tk-col__add" data-add="' + esc(st) + '" title="' + esc(t('add_to', { col: P.tTask(st) })) + '"><i data-lucide="plus"></i></button></div>' +
        '<div class="tk-col__list">' + grp.map(cardHtml).join('') + '</div></div>';
    }).join('');
  }
  function cardHtml(x) {
    var done = x.status === 'Done';
    var hue = P.colorVar(x.project_color);
    var subs = x.subtasks || [], sd = subs.filter(function (s) { return s.done; }).length;
    var com = (x.comments || []).length;
    var d = done ? (x.done_at ? { text: P.fmtShort(x.done_at.slice(0, 10)), cls: '' } : null) : P.due(x.due, false);
    var menu = COLS.filter(function (c) { return c !== x.status; }).map(function (c) {
      return '<button type="button" class="dropdown-item" data-move="' + esc(c) + '"><span class="pj-dot" style="--hue:' + P.TASK_HUE[c] + '"></span>' + esc(t('move_to', { col: P.tTask(c) })) + '</button>';
    }).join('') + '<div class="dropdown-divider"></div><button type="button" class="dropdown-item" data-open-task><i data-lucide="panel-right-open"></i>' + esc(t('open_task')) + '</button>';
    return '<div class="tk-card" data-task="' + esc(x.id) + '" data-project="' + esc(x.project_id) + '" style="--hue:' + hue + '">' +
      '<div class="tk-card__top">' + P.chip(x.project_name, hue) + P.prioBadge(x.priority) +
        '<div class="dropdown ms-auto"><button type="button" class="tk-card__more" data-bs-toggle="dropdown" aria-expanded="false" aria-label="' + esc(t('move_or_open', { task: x.title })) + '"><i data-lucide="more-horizontal"></i></button>' +
        '<div class="dropdown-menu dropdown-menu-end tk-menu">' + menu + '</div></div></div>' +
      '<div class="tk-card__title">' + (done ? '<span class="pj-donecheck"><i data-lucide="check"></i></span>' : '') + '<span>' + esc(x.title) + '</span></div>' +
      (subs.length ? '<div class="tk-card__bar"><div><span style="width:' + Math.round(100 * sd / subs.length) + '%"></span></div>' + sd + '/' + subs.length + '</div>' : '') +
      '<div class="tk-card__foot">' +
        (d ? '<span class="pj-meta ' + d.cls + '"><i data-lucide="' + (done ? 'check' : (d.late ? 'flag' : 'calendar')) + '"></i>' + esc(d.text) + '</span>' : '') +
        (com ? '<span class="pj-meta"><i data-lucide="message-square"></i>' + com + '</span>' : '') +
        (x.assignee_sid ? P.avatar(x.assignee_sid, x.assignee_name, 'sm') : '') +
      '</div></div>';
  }

  // ── lista ───────────────────────────────────────────────────────────────
  function renderList(list) {
    $('tk-list-sub').textContent = t('n_on_board', { n: list.length });
    $('tk-list-body').innerHTML = COLS.map(function (st) {
      var grp = sortTasks(list.filter(function (x) { return x.status === st; }), state.sort);
      var closed = state.closed[st] !== undefined ? state.closed[st] : st === 'Done';
      return '<div class="tk-lgroup' + (closed ? ' is-closed' : '') + '" data-group="' + esc(st) + '">' +
        '<button type="button" class="tk-lgroup__head" data-fold="' + esc(st) + '"><i data-lucide="chevron-down"></i>' +
          '<span class="pj-dot" style="--hue:' + P.TASK_HUE[st] + '"></span>' + esc(P.tTask(st)) + ' <span class="otc-count">' + grp.length + '</span></button>' +
        '<div class="tk-lrows">' + grp.map(rowHtml).join('') + '</div></div>';
    }).join('');
  }
  function rowHtml(x) {
    var done = x.status === 'Done';
    var d = P.due(x.due, done);
    return '<div class="tk-lrow' + (done ? ' is-done' : '') + '" data-task="' + esc(x.id) + '" data-project="' + esc(x.project_id) + '">' +
      '<button type="button" class="tk-circle' + (done ? ' is-on' : '') + '" data-done-toggle aria-pressed="' + (done ? 'true' : 'false') + '" title="' + esc(done ? t('reopen') : t('mark_done')) + '"><i data-lucide="check"></i></button>' +
      '<span class="tk-lrow__title">' + esc(x.title) + '</span>' +
      P.chip(x.project_name, P.colorVar(x.project_color)) +
      '<span class="pj-meta ' + (d ? d.cls : '') + '">' + (d ? '<i data-lucide="calendar"></i>' + esc(d.text) : '') + '</span>' +
      '<span>' + P.prioBadge(x.priority, true) + '</span>' +
      '<span>' + (x.assignee_sid ? P.avatar(x.assignee_sid, x.assignee_name, 'sm') : '') + '</span>' +
    '</div>';
  }

  function renderAll() {
    renderStats();
    renderFilters();
    var list = visible();
    var board = state.view === 'board';
    $('tk-board').classList.toggle('d-none', !board);
    $('tk-list').classList.toggle('d-none', board);
    Array.prototype.forEach.call(document.querySelectorAll('#tk-view [data-view]'), function (a) {
      a.classList.toggle('active', a.getAttribute('data-view') === state.view);
    });
    if (board) renderBoard(list); else renderList(list);
    P.icons(document.getElementById('tk-page'));
  }

  // ── ações ───────────────────────────────────────────────────────────────
  function findTask(pid, tid) {
    return state.tasks.filter(function (x) { return x.project_id === pid && x.id === tid; })[0];
  }
  function move(pid, tid, status, quiet) {
    var x = findTask(pid, tid);
    if (!x || x.status === status) return;
    var antes = x.status, titulo = x.title;
    x.status = status;                                   // otimista: o card já está lá
    renderAll();
    P.api('PATCH', '/api/projects/' + encodeURIComponent(pid) + '/tasks/' + encodeURIComponent(tid), { status: status })
      .then(function (d) {
        applyProject(d.project);
        // o aviso do Pane: "Done: <tarefa>" com o Undo que devolve à coluna de antes
        if (!quiet && window.otcToast) window.otcToast(P.tTask(status) + ': ' + titulo, { undo: function () { move(pid, tid, antes, true); } });
      })
      .catch(function (e) { x.status = antes; renderAll(); P.fail(e); });
  }
  function openTask(pid, tid) {
    var x = findTask(pid, tid);
    if (!x) return;
    P.openTaskDrawer({ task: x, project: { id: pid, name: x.project_name, color: x.project_color }, onChange: applyProject });
  }
  function newTask(status) {
    if (!state.projects.length) return;
    var abertos = state.projects.filter(function (p) { return p.status !== 'Concluded'; });
    P.openTaskModal({ projects: abertos.length ? abertos : state.projects, projectId: state.project || '', status: status || 'To do', onSaved: applyProject });
  }

  // Arrastar e soltar — o do Pane, com o mouse (pointer events, não o drag
  // nativo): o card LEVANTA (inclinado, com sombra) e segue o ponteiro, e na
  // coluna embaixo dele ABRE-SE O ESPAÇO onde ele vai cair, empurrando os
  // vizinhos com animação. Soltar fora de uma coluna devolve o card. Dentro da
  // mesma coluna não há ordem manual — a ordem é a do prazo. No toque, o menu
  // "…" do card faz o mesmo.
  var drag = null;
  var GAP = 10;                                          // o `gap` da .tk-col__list
  function wireDnD() {
    var board = $('tk-board');
    board.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse' || e.button !== 0) return;
      var c = e.target.closest('.tk-card');
      if (!c || e.target.closest('button, a, input, .dropdown-menu')) return;
      var r = c.getBoundingClientRect();
      drag = { card: c, pid: c.getAttribute('data-project'), tid: c.getAttribute('data-task'),
        from: c.closest('[data-col]').getAttribute('data-col'),
        x0: e.clientX, y0: e.clientY, x: e.clientX, y: e.clientY,
        dx: e.clientX - r.left, dy: e.clientY - r.top, w: r.width, h: r.height, on: false };
    });
    document.addEventListener('pointermove', function (e) {
      if (!drag) return;
      drag.x = e.clientX; drag.y = e.clientY;
      if (!drag.on) {
        if (Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 6) return;
        liftCard();
      }
      e.preventDefault();
      follow();
      placeGap();
    });
    document.addEventListener('pointerup', function () { if (drag) dropCard(); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && drag && drag.on) { drag.cancel = true; dropCard(); } });
    // o clique que encerra um arrasto não abre o card
    board.addEventListener('click', function (e) {
      if (board._swallow) { board._swallow = false; e.stopPropagation(); e.preventDefault(); }
    }, true);
  }
  function liftCard() {
    drag.on = true;
    var f = drag.card.cloneNode(true);
    f.classList.add('tk-card--float');
    f.style.width = drag.w + 'px'; f.style.height = drag.h + 'px';
    document.body.appendChild(f);
    drag.float = f;
    // o espaço nasce NO LUGAR do card, com a altura dele: nada pula na origem
    var ph = document.createElement('div');
    ph.className = 'tk-drop-ghost';
    ph.style.height = drag.h + 'px';
    drag.card.after(ph);
    drag.card.classList.add('is-lifted');
    drag.ph = ph;
    document.body.classList.add('tk-is-dragging');
    autoScroll();
  }
  function follow() {
    drag.float.style.translate = (drag.x - drag.dx) + 'px ' + (drag.y - drag.dy) + 'px';
  }
  function colAt(x, y) {
    var el = document.elementFromPoint(x, y);
    return el ? el.closest('#tk-board [data-col]') : null;
  }
  // a posição de inserção: antes do primeiro card cujo MEIO está abaixo do ponteiro
  function placeGap() {
    var col = colAt(drag.x, drag.y);
    Array.prototype.forEach.call(document.querySelectorAll('.tk-col-panel.is-over'), function (c) { if (c !== col) c.classList.remove('is-over'); });
    if (!col) return;
    col.classList.add('is-over');
    var list = col.querySelector('.tk-col__list');
    var cards = Array.prototype.filter.call(list.children, function (n) { return n.classList.contains('tk-card') && !n.classList.contains('is-lifted'); });
    var before = null;
    for (var i = 0; i < cards.length; i++) {
      var r = cards[i].getBoundingClientRect();
      if (drag.y < r.top + r.height / 2) { before = cards[i]; break; }
    }
    var cur = drag.ph;
    if (cur.parentNode === list) {
      var nxt = cur.nextElementSibling;
      while (nxt && (nxt.classList.contains('is-lifted') || nxt.classList.contains('is-closing'))) nxt = nxt.nextElementSibling;
      if (nxt === before) return;                         // já está no lugar
    }
    // o espaço antigo FECHA e o novo ABRE — os vizinhos deslizam junto
    closeGap(cur);
    var ph = document.createElement('div');
    ph.className = 'tk-drop-ghost';
    ph.style.height = drag.h + 'px';
    list.insertBefore(ph, before);
    ph.animate([{ height: '0px', marginBottom: (-GAP) + 'px', opacity: 0 }, { height: drag.h + 'px', marginBottom: '0px', opacity: 1 }],
      { duration: 240, easing: 'cubic-bezier(.2,.9,.25,1)' });
    drag.ph = ph;
  }
  function closeGap(ph) {
    if (!ph || !ph.parentNode) return;
    ph.classList.add('is-closing');
    var h = ph.getBoundingClientRect().height;
    var an = ph.animate([{ height: h + 'px', marginBottom: '0px', opacity: 1 }, { height: '0px', marginBottom: (-GAP) + 'px', opacity: 0 }],
      { duration: 200, easing: 'cubic-bezier(.3,.7,.3,1)' });
    an.onfinish = function () { ph.remove(); };
  }
  function autoScroll() {
    if (!drag || !drag.on) return;
    var edge = 70, vh = window.innerHeight, v = 0;
    if (drag.y < edge) v = -Math.ceil((edge - drag.y) / 5);
    else if (drag.y > vh - edge) v = Math.ceil((drag.y - (vh - edge)) / 5);
    if (v) { window.scrollBy({ top: v, behavior: 'instant' }); placeGap(); }
    requestAnimationFrame(autoScroll);
  }
  function dropCard() {
    var d = drag;
    drag = null;
    if (!d.on) return;                                   // foi só um clique
    $('tk-board')._swallow = true;
    setTimeout(function () { $('tk-board')._swallow = false; }, 0);
    document.body.classList.remove('tk-is-dragging');
    var col = d.cancel ? null : colAt(d.x, d.y);
    var to = col ? col.getAttribute('data-col') : d.from;
    // o card POUSA no espaço aberto (ou volta para o lugar dele)
    var alvo = (col && d.ph && d.ph.parentNode) ? d.ph : d.card.nextElementSibling;
    if (!col) { closeGap(d.ph); alvo = d.card; d.card.classList.remove('is-lifted'); d.card.style.visibility = 'hidden'; }
    var r = (alvo && alvo.getBoundingClientRect) ? alvo.getBoundingClientRect() : d.card.getBoundingClientRect();
    d.float.classList.add('is-landing');
    d.float.style.translate = r.left + 'px ' + r.top + 'px';
    setTimeout(function () {
      d.float.remove();
      Array.prototype.forEach.call(document.querySelectorAll('.tk-col-panel.is-over'), function (c) { c.classList.remove('is-over'); });
      if (to !== d.from) move(d.pid, d.tid, to);
      else {
        Array.prototype.forEach.call(document.querySelectorAll('#tk-board .tk-drop-ghost'), function (g) { g.remove(); });
        d.card.classList.remove('is-lifted');
        d.card.style.visibility = '';
      }
    }, 210);
  }

  function wire() {
    $('tk-view').addEventListener('click', function (e) {
      var a = e.target.closest('[data-view]');
      if (!a) return;
      e.preventDefault();
      state.view = a.getAttribute('data-view');
      try { localStorage.setItem(VIEW_KEY, state.view); } catch (er) {}
      renderAll();
    });
    $('tk-sort').addEventListener('click', function (e) {
      var a = e.target.closest('[data-sort]');
      if (!a) return;
      e.preventDefault();
      state.sort = a.getAttribute('data-sort');
      Array.prototype.forEach.call(this.querySelectorAll('[data-sort]'), function (x) { x.classList.toggle('active', x === a); });
      renderAll();
    });
    $('tk-menu-project').addEventListener('click', function (e) {
      var b = e.target.closest('[data-value]'); if (!b) return;
      state.project = b.getAttribute('data-value'); renderAll();
    });
    $('tk-menu-prio').addEventListener('click', function (e) {
      var b = e.target.closest('[data-value]'); if (!b) return;
      state.prio = b.getAttribute('data-value'); renderAll();
    });
    $('tk-f-mine').addEventListener('click', function () { state.mine = !state.mine; renderAll(); });
    var qt;
    $('tk-q').addEventListener('input', function () {
      var v = this.value;
      clearTimeout(qt); qt = setTimeout(function () { state.q = v; renderAll(); }, 120);
    });
    $('tk-new').addEventListener('click', function () { newTask('To do'); });
    $('tk-board').addEventListener('click', function (e) {
      var add = e.target.closest('[data-add]');
      if (add) { newTask(add.getAttribute('data-add')); return; }
      var card = e.target.closest('.tk-card');
      if (!card) return;
      var pid = card.getAttribute('data-project'), tid = card.getAttribute('data-task');
      var mv = e.target.closest('[data-move]');
      if (mv) { move(pid, tid, mv.getAttribute('data-move')); return; }
      if (e.target.closest('[data-open-task]')) { openTask(pid, tid); return; }
      if (e.target.closest('.dropdown')) return;
      openTask(pid, tid);
    });
    $('tk-list-body').addEventListener('click', function (e) {
      var fold = e.target.closest('[data-fold]');
      if (fold) {
        var st = fold.getAttribute('data-fold');
        var g = fold.closest('.tk-lgroup');
        state.closed[st] = !g.classList.contains('is-closed');
        g.classList.toggle('is-closed', state.closed[st]);
        return;
      }
      var row = e.target.closest('[data-task]');
      if (!row) return;
      var pid = row.getAttribute('data-project'), tid = row.getAttribute('data-task');
      if (e.target.closest('[data-done-toggle]')) {
        var x = findTask(pid, tid);
        if (x) move(pid, tid, x.status === 'Done' ? 'To do' : 'Done');
        return;
      }
      openTask(pid, tid);
    });
    wireDnD();
  }

  wire();
  load();
})();

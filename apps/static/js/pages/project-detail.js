/* project-detail.js — a página de UM projeto: contadores, visão geral (Lead,
   status, linha do tempo, pessoas), marcos, atividade, burn-up e as tarefas por
   status. Toda escrita devolve o projeto inteiro e a página se redesenha dele.
   Os marcos são os EVENTOS da iniciativa: nascem do "New event" da barra, e o
   card só os mostra (§648). */
(function () {
  'use strict';
  var P = window.OtcPj;
  var t = P.t, esc = P.esc;
  var root = document.getElementById('pjd-page');
  var PID = root.getAttribute('data-project');
  var state = { p: null, canDelete: false, showDone: false, chart: null };

  function $(id) { return document.getElementById(id); }
  function url(extra) { return '/api/projects/' + encodeURIComponent(PID) + (extra || ''); }

  function load() {
    return P.api('GET', url()).then(function (d) {
      P.setMeta(d);
      state.canDelete = !!d.can_delete;
      render(d.project);
      // `?task=t3` (o clique na tarefa do Calendar): abre a tarefa na gaveta
      var tid = new URLSearchParams(window.location.search).get('task');
      if (tid && !state.openedFromLink) { state.openedFromLink = true; openTask(tid); }
    }).catch(function (e) {
      P.metaFailed();
      var box = $('pjd-load-error');
      box.textContent = P.errText(e);
      box.classList.remove('d-none');
    });
  }
  function apply(d) { render(d.project); return d; }
  function send(method, extra, body) { return P.api(method, url(extra), body).then(apply).catch(P.fail); }

  // ── desenho ─────────────────────────────────────────────────────────────
  function render(p) {
    state.p = p;
    var hue = P.colorVar(p.color);
    root.style.setProperty('--hue', hue);
    document.title = p.name + ' | OTC Tracker';
    $('pjd-name').textContent = p.name;
    $('pjd-crumb').textContent = p.name;
    $('pjd-desc').textContent = p.description || '';
    var icon = $('pjd-icon');
    icon.style.setProperty('--hue', hue);
    if (icon.getAttribute('data-icon') !== p.icon) {
      icon.setAttribute('data-icon', p.icon);
      icon.innerHTML = '<i data-lucide="' + esc(p.icon) + '"></i>';
    }
    if (window.otcPins) window.otcPins.sync([p], false);
    renderPin();

    $('pjd-n-progress').textContent = p.progress + '%';
    $('pjd-n-open').textContent = p.open_tasks;
    $('pjd-n-done').textContent = p.tasks_done;
    var dl = p.days_left;
    var late = dl !== null && dl < 0 && p.status !== 'Concluded';
    $('pjd-days-label').textContent = late ? t('overdue') : t('days_left');
    $('pjd-n-days').textContent = dl === null ? '—' : (late ? -dl : Math.max(dl, 0));
    $('pjd-days-tile').style.setProperty('--hue', late ? 'var(--otc-danger)' : 'var(--otc-orange)');

    $('pjd-lead').innerHTML = p.lead_sid ? P.avatar(p.lead_sid, p.lead_name, 'sm') + '<span>' + esc(p.lead_name || p.lead_sid) + '</span>' : '<span class="text-muted">—</span>';
    $('pjd-status').innerHTML = P.chip(P.tStatus(p.status), P.STATUS_HUE[p.status] || 'var(--otc-text-3)');
    $('pjd-category').innerHTML = p.category ? P.catChip(p.category) : '<span class="text-muted">' + esc(P.tCat('')) + '</span>';
    renderTimeline(p);
    renderPeople(p);
    renderMilestones(p);
    renderActivity(p);
    renderUpcoming(p);
    renderTasks(p);
    renderChart(p);
    P.icons(root);
  }

  function renderPin() {
    var on = window.otcPins && window.otcPins.has(PID);
    var b = $('pjd-pin');
    b.classList.toggle('is-pinned', !!on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
    $('pjd-pin-label').textContent = on ? t('pinned') : t('pin_short');
    var ic = b.querySelector('svg, i');
    if (ic) { ic.style.color = on ? 'var(--otc-yellow)' : ''; ic.style.fill = on ? 'currentColor' : 'none'; }
  }

  // Linha do tempo: do início à data-alvo, com os marcos e o "Today".
  function renderTimeline(p) {
    $('pjd-start').textContent = P.fmtDate(p.start_date) || '—';
    $('pjd-due').textContent = P.fmtDate(p.due_date) || '—';
    var a = P.parse(p.start_date), b = P.parse(p.due_date), h = P.parse(P.isoToday());
    var tl = $('pjd-timeline');
    if (!a || !b || b <= a) { tl.innerHTML = ''; tl.style.display = 'none'; return; }
    tl.style.display = '';
    var span = b - a;
    var pos = function (d) { return Math.max(0, Math.min(100, (d - a) / span * 100)); };
    var html = '<div class="pjd-timeline__bar" style="width:' + pos(h) + '%"></div>';
    (p.milestones || []).forEach(function (m) {
      var d = P.parse(m.date);
      if (!d) return;
      html += '<span class="pjd-timeline__dot' + (m.done ? ' is-done' : '') + '" style="left:' + pos(d) + '%" title="' + esc(m.title) + '"></span>';
    });
    if (h >= a && h <= b) html += '<span class="pjd-timeline__today" style="left:' + pos(h) + '%"><span>' + esc(t('today')) + '</span></span>';
    tl.innerHTML = html;
  }

  function renderPeople(p) {
    var ppl = p.people || [];
    $('pjd-people-n').textContent = ppl.length;
    $('pjd-people').innerHTML = ppl.map(function (x) {
      var sub = [x.is_lead ? t('lead') : '', x.position || '', x.open_tasks ? t('n_open', { n: x.open_tasks }) : '']
        .filter(Boolean).join(' · ');
      return '<div class="pjd-person">' + P.avatar(x.sid, x.name, 'lg') + '<div class="min-w-0"><b>' + esc(x.name) + '</b><small>' + esc(sub) + '</small></div></div>';
    }).join('') || '<div class="text-muted">—</div>';
  }

  // O card SÓ MOSTRA (mesa, 21/10/2026): quando, a hora e a duração, o tipo e
  // o local. Criar é o New event da barra; o clique abre o evento no modal.
  function renderMilestones(p) {
    var ms = p.milestones || [];
    var done = ms.filter(function (m) { return m.done; }).length;
    $('pjd-ms-sub').textContent = ms.length ? t('ms_reached_n', { n: done, total: ms.length }) : t('no_ms');
    $('pjd-ms').innerHTML = ms.map(function (m) {
      var when = [m.date ? P.fmtShort(m.date) : t('no_date')];
      if (m.time) when.push(m.time + (m.length ? ' (' + P.lengthLabel(m.length) + ')' : ''));
      when.push(m.done ? t('ms_done') : (m.date ? P.inDays(m.date) : ''));
      var extra = [P.tEvent(m.type), m.where || ''].filter(Boolean).join(' · ');
      var next = !m.done && m.id === p.next_milestone_id;
      return '<li class="' + (m.done ? 'is-done' : '') + '" data-ms="' + esc(m.id) + '" role="button" tabindex="0" title="' + esc(t('edit_event')) + '">' +
        '<span class="pjd-ms__check" aria-hidden="true"><i data-lucide="check"></i></span>' +
        '<div class="pjd-ms__body"><div class="pjd-ms__title">' + esc(m.title) + '</div>' +
          '<div class="pjd-ms__date">' + esc(when.filter(Boolean).join(' · ')) + '</div>' +
          '<div class="pjd-ms__date">' + esc(extra) + '</div></div>' +
        (next ? '<span class="otc-count">' + esc(t('next')) + '</span>' : '') +
      '</li>';
    }).join('');
  }

  function renderActivity(p) {
    var acts = (p.activity || []).slice(0, 12);
    $('pjd-activity').innerHTML = acts.map(function (a) {
      return '<li>' + P.avatar(a.sid, a.name, 'sm') + '<div><p>' + P.activityText(a) + '</p><small>' + esc(P.ago(a.at)) + '</small></div></li>';
    }).join('') || '<li class="text-muted">—</li>';
  }

  // Coming up: os marcos em aberto pela data (atrasado primeiro, em vermelho)
  // e a data-alvo do projeto no fim — os eventos do projeto, os mesmos do Calendar.
  function renderUpcoming(p) {
    var lang = 'en';
    try { lang = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
    var loc = { br: 'pt-BR', es: 'es-ES' }[lang] || 'en-US';
    var mes = function (d) { return new Intl.DateTimeFormat(loc, { month: 'short' }).format(d).replace('.', ''); };
    var itens = (p.milestones || []).filter(function (m) { return !m.done && m.date; })
      .map(function (m) { return { date: m.date, time: m.time || '', type: m.type, title: m.title, kind: 'milestone' }; });
    if (p.due_date && p.status !== 'Concluded') itens.push({ date: p.due_date, title: p.name, kind: 'target' });
    itens.sort(function (a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : 0; });
    $('pjd-up').innerHTML = itens.slice(0, 6).map(function (x) {
      var d = P.parse(x.date), n = P.diffDays(x.date), late = n !== null && n < 0;
      var quando = n === 0 ? t('today') : (n === 1 ? t('tomorrow') : t('wd')[d.getDay()] + ', ' + P.fmtShort(x.date));
      var resto = late ? (n === -1 ? t('day_late') : t('days_late', { n: -n })) : P.inDays(x.date);
      var tipo = x.kind === 'target' ? t('up_target') : P.tEvent(x.type);
      return '<li class="' + (late ? 'is-late' : '') + '">' +
        '<span class="pjd-up__date"><small>' + esc(mes(d)) + '</small><b>' + d.getDate() + '</b></span>' +
        '<span class="pjd-up__body"><b>' + esc((x.kind === 'target' ? '⚑ ' : '') + x.title) + '</b>' +
          '<small>' + esc(quando) + (x.time ? ' · ' + esc(x.time) : '') + (n > 1 ? ' · ' + esc(resto) : '') + (late ? ' · ' + esc(resto) : '') + ' · ' + esc(tipo) + '</small></span>' +
        (x.kind === 'target' && p.lead_sid ? P.avatar(p.lead_sid, p.lead_name, 'sm') : '') +
      '</li>';
    }).join('') || '<li class="text-muted">' + esc(t('up_empty')) + '</li>';
  }

  var ORDER = ['To do', 'In progress', 'In review', 'Done'];
  function renderTasks(p) {
    var tasks = p.tasks || [];
    $('pjd-tasks-sub').textContent = t('open_done', { open: p.open_tasks, done: p.tasks_done });
    if (!tasks.length) {
      $('pjd-tasks').innerHTML = '<div class="pj-empty py-4"><i data-lucide="list-checks"></i><p class="mb-0">' + esc(t('no_tasks')) + '</p></div>';
      return;
    }
    $('pjd-tasks').innerHTML = ORDER.map(function (st) {
      var grp = tasks.filter(function (x) { return x.status === st; });
      if (!grp.length) return '';
      var isDone = st === 'Done';
      var head = '<div class="pjd-tgroup__head"><span class="pj-dot" style="--hue:' + P.TASK_HUE[st] + '"></span>' + esc(P.tTask(st)) +
        ' <span class="otc-count">' + grp.length + '</span>' +
        (isDone ? '<a href="#" class="ms-auto small" data-toggle-done>' + esc(state.showDone ? t('hide') : t('show')) + '</a>' : '') + '</div>';
      if (isDone && !state.showDone) return '<div class="pjd-tgroup">' + head + '</div>';
      return '<div class="pjd-tgroup">' + head + '<div class="pjd-tlist">' + grp.map(taskRow).join('') + '</div></div>';
    }).join('');
  }
  function taskRow(x) {
    var d = P.due(x.due, x.status === 'Done');
    return '<button type="button" class="pjd-trow' + (x.status === 'Done' ? ' is-done' : '') + '" data-task="' + esc(x.id) + '">' +
      '<span class="pjd-trow__title">' + esc(x.title) + '</span>' +
      P.prioBadge(x.priority) +
      (d ? '<span class="pj-meta ' + d.cls + '">' + esc(d.text) + '</span>' : '') +
      (x.assignee_sid ? P.avatar(x.assignee_sid, x.assignee_name, 'sm') : '') +
    '</button>';
  }

  // Burn-up: as duas séries do servidor; as cores saem dos tokens na hora (o
  // tema escuro troca o --otc-text-2).
  function renderChart(p) {
    var cv = $('pjd-burnup');
    if (!window.Chart || !cv) return;
    var cs = getComputedStyle(document.documentElement);
    var hue = cs.getPropertyValue('--otc-' + (p.color || 'blue')).trim() || '#2f7cf6';
    var txt = cs.getPropertyValue('--otc-text-2').trim() || '#666';
    var sep = cs.getPropertyValue('--otc-sep').trim() || 'rgba(0,0,0,.1)';
    var b = p.burnup || { labels: [], done: [], total: [] };
    var labels = b.labels.map(P.fmtShort);
    if (state.chart) { state.chart.destroy(); state.chart = null; }
    state.chart = new Chart(cv, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: t('done'), data: b.done, borderColor: hue, backgroundColor: hue + '33', fill: true, tension: .35, pointRadius: 0, borderWidth: 2.5 },
          { label: t('total'), data: b.total, borderColor: txt, borderDash: [5, 5], fill: false, tension: .35, pointRadius: 0, borderWidth: 1.5 }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 600 },
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { position: 'top', align: 'start', labels: { color: txt, boxWidth: 14, boxHeight: 2, usePointStyle: false } } },
        scales: {
          x: { ticks: { color: txt, maxTicksLimit: 7, maxRotation: 0 }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { color: txt, precision: 0 }, grid: { color: sep } }
        }
      }
    });
  }

  // ── ações ───────────────────────────────────────────────────────────────
  function openTask(id) {
    var x = (state.p.tasks || []).filter(function (k) { return k.id === id; })[0];
    if (!x) return;
    P.openTaskDrawer({ task: x, project: { id: state.p.id, name: state.p.name, color: state.p.color, people: state.p.people }, onChange: render });
  }

  // Os botões leem a iniciativa CARREGADA (§648): no JP a página leva
  // segundos, e o Edit clicado antes disso guardava `state.p` ainda vazio — o
  // modal abria em branco, sem nada do que foi preenchido na criação. O clique
  // espera a carga; se ela falhou, não abre (a caixa de erro já diz o motivo).
  function carregada(fn) {
    return function () {
      if (state.p) { fn(); return; }
      document.documentElement.style.cursor = 'progress';
      state.loading.then(function () {
        document.documentElement.style.removeProperty('cursor');
        if (state.p) fn();
      });
    };
  }
  function openEvent(m) {
    P.openEventModal({ project: state.p, milestone: m || null, onSaved: function (p) { render(p); P.toast(t('saved')); } });
  }

  function wire() {
    $('pjd-edit').addEventListener('click', carregada(function () {
      P.openProjectModal({
        mode: 'edit', project: state.p, canDelete: state.canDelete,
        onSaved: function (d) { render(d.project); P.toast(t('saved')); },
        onDeleted: function () {
          if (window.otcPins && window.otcPins.has(PID)) window.otcPins.toggle({ id: PID });
          window.location.href = '/initiatives';
        }
      });
    }));
    $('pjd-new-event').addEventListener('click', carregada(function () { openEvent(null); }));
    $('pjd-pin').addEventListener('click', function () {
      if (window.otcPins && state.p) { window.otcPins.toggle(state.p); renderPin(); }
    });
    $('pjd-add-task').addEventListener('click', carregada(function () {
      P.openTaskModal({ projects: [state.p], projectId: PID, fixedProject: true, onSaved: render });
    }));
    $('pjd-tasks').addEventListener('click', function (e) {
      if (e.target.closest('[data-toggle-done]')) { e.preventDefault(); state.showDone = !state.showDone; renderTasks(state.p); P.icons(root); return; }
      var r = e.target.closest('[data-task]');
      if (r) openTask(r.getAttribute('data-task'));
    });
    // o clique num marco (ou Enter nele) abre o evento no modal
    var abreMarco = function (e) {
      var li = e.target.closest('[data-ms]');
      if (!li || !state.p) return;
      var id = li.getAttribute('data-ms');
      var m = (state.p.milestones || []).filter(function (k) { return k.id === id; })[0];
      if (m) { e.preventDefault(); openEvent(m); }
    };
    $('pjd-ms').addEventListener('click', abreMarco);
    $('pjd-ms').addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') abreMarco(e); });
    // o tema escuro/claro troca as cores do gráfico
    new MutationObserver(function () { if (state.p) renderChart(state.p); })
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-bs-theme', 'data-accent'] });
  }

  wire();
  state.loading = load();
})();

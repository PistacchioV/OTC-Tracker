/* ============================================================================
 * user-home.js — Intraday › User Home (§632): o dia de UMA pessoa, no desenho
 * da Home do Pane. Tudo sai de `GET /api/user-home` numa resposta; as ações
 * (marcar tarefa, foco, Sync) gravam e recarregam.
 *
 * Reaproveita o `OtcPj` (projects-common.js): API, datas, avatares, o modal
 * "New task" e a gaveta da tarefa. O timer é a ILHA do tema (`otcFocus`,
 * otc.js §3e) — esta tela só a comanda e desenha o anel grande.
 * ========================================================================== */
(function () {
  'use strict';
  var P = window.OtcPj;
  var esc = P.esc;

  var LANG = 'en';
  try { LANG = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}
  var LOCALE = { en: 'en-US', br: 'pt-BR', es: 'es-ES' }[LANG] || 'en-US';

  var _TRANS = {
    en: {
      morning: 'Good morning, {n}', afternoon: 'Good afternoon, {n}', evening: 'Good evening, {n}',
      sub: '{date} · {m} and {t} left today', m1: '1 meeting', mn: '{n} meetings', t1: '1 task', tn: '{n} tasks',
      next: 'Next: {t}', in_min: 'in {n} min', in_h: 'in {n} h', now: 'now', join: 'Join',
      rings_tasks: 'Tasks', rings_focus: 'Focus', rings_meet: 'Meetings',
      no_sync: 'Sync your Outlook calendar to see your meetings here.', no_more: 'No more meetings today.',
      synced: 'Outlook · synced {when}', never: 'Outlook · not synced yet', sync: 'Sync',
      sync_ok: 'Calendar synced: {n} events', sync_fail: 'Sync failed', outlook_unavailable: 'The Sync needs Outlook on this machine (Windows).', calendar_not_accessible: 'The Outlook on this machine belongs to someone else, and your calendar did not open through it. Sync from your own OTC Tracker.',
      ready: 'Ready', focusing: 'Focusing', paused: 'Paused', on_break: 'Break',
      just_focus: 'No task — just focus', start: 'Start focus', pause: 'Pause', resume: 'Resume', end: 'End',
      focused: '{h} · {n} sessions', focused1: '{h} · 1 session',
      no_tasks: 'Nothing due today. Nice.', no_access: 'Tasks and initiatives appear here for whoever has Initiatives or Tasks.',
      done_lbl: 'Done', reopened: 'Reopened',
      finished: 'finished so far', vs_last: 'vs last week',
      no_projects: 'You are not in any initiative yet.', due: 'due {d}', no_due: 'no target date',
      no_team: 'Nobody shares an initiative with you yet.', no_act: 'No activity yet.',
      in_focus: 'In focus · until {t}', in_meeting: 'In a meeting · until {t}', available: 'Available',
      e_title: 'Something went wrong'
    },
    br: {
      morning: 'Bom dia, {n}', afternoon: 'Boa tarde, {n}', evening: 'Boa noite, {n}',
      sub: '{date} · {m} e {t} restantes hoje', m1: '1 reunião', mn: '{n} reuniões', t1: '1 tarefa', tn: '{n} tarefas',
      next: 'Próxima: {t}', in_min: 'em {n} min', in_h: 'em {n} h', now: 'agora', join: 'Entrar',
      rings_tasks: 'Tarefas', rings_focus: 'Foco', rings_meet: 'Reuniões',
      no_sync: 'Sincronize o calendário do Outlook para ver suas reuniões aqui.', no_more: 'Sem mais reuniões hoje.',
      synced: 'Outlook · sincronizado {when}', never: 'Outlook · ainda não sincronizado', sync: 'Sincronizar',
      sync_ok: 'Calendário sincronizado: {n} eventos', sync_fail: 'Falha ao sincronizar', outlook_unavailable: 'O Sync precisa do Outlook desta máquina (Windows).', calendar_not_accessible: 'O Outlook desta máquina é de outra pessoa, e o seu calendário não abriu por ele. Sincronize pelo seu próprio OTC Tracker.',
      ready: 'Pronto', focusing: 'Focando', paused: 'Pausado', on_break: 'Pausa',
      just_focus: 'Sem tarefa — só foco', start: 'Iniciar foco', pause: 'Pausar', resume: 'Retomar', end: 'Encerrar',
      focused: '{h} · {n} sessões', focused1: '{h} · 1 sessão',
      no_tasks: 'Nada vence hoje. Ótimo.', no_access: 'Tarefas e iniciativas aparecem aqui para quem tem o Initiatives ou o Tasks.',
      done_lbl: 'Concluída', reopened: 'Reaberta',
      finished: 'concluídas até agora', vs_last: 'vs semana passada',
      no_projects: 'Você ainda não está em nenhuma iniciativa.', due: 'prazo {d}', no_due: 'sem data-alvo',
      no_team: 'Ninguém divide uma iniciativa com você ainda.', no_act: 'Nenhuma atividade ainda.',
      in_focus: 'Em foco · até {t}', in_meeting: 'Em reunião · até {t}', available: 'Disponível',
      e_title: 'Algo deu errado'
    },
    es: {
      morning: 'Buenos días, {n}', afternoon: 'Buenas tardes, {n}', evening: 'Buenas noches, {n}',
      sub: '{date} · {m} y {t} pendientes hoy', m1: '1 reunión', mn: '{n} reuniones', t1: '1 tarea', tn: '{n} tareas',
      next: 'Próxima: {t}', in_min: 'en {n} min', in_h: 'en {n} h', now: 'ahora', join: 'Unirse',
      rings_tasks: 'Tareas', rings_focus: 'Foco', rings_meet: 'Reuniones',
      no_sync: 'Sincronice el calendario de Outlook para ver sus reuniones aquí.', no_more: 'No hay más reuniones hoy.',
      synced: 'Outlook · sincronizado {when}', never: 'Outlook · aún no sincronizado', sync: 'Sincronizar',
      sync_ok: 'Calendario sincronizado: {n} eventos', sync_fail: 'Error al sincronizar', outlook_unavailable: 'El Sync necesita Outlook en esta máquina (Windows).', calendar_not_accessible: 'El Outlook de esta máquina es de otra persona, y su calendario no se abrió por él. Sincronice desde su propio OTC Tracker.',
      ready: 'Listo', focusing: 'Enfocado', paused: 'En pausa', on_break: 'Pausa',
      just_focus: 'Sin tarea — solo foco', start: 'Iniciar foco', pause: 'Pausar', resume: 'Reanudar', end: 'Terminar',
      focused: '{h} · {n} sesiones', focused1: '{h} · 1 sesión',
      no_tasks: 'Nada vence hoy. Bien.', no_access: 'Tareas e iniciativas aparecen aquí para quien tiene Initiatives o Tasks.',
      done_lbl: 'Hecha', reopened: 'Reabierta',
      finished: 'terminadas hasta ahora', vs_last: 'vs semana pasada',
      no_projects: 'Aún no está en ninguna iniciativa.', due: 'vence {d}', no_due: 'sin fecha objetivo',
      no_team: 'Nadie comparte una iniciativa con usted todavía.', no_act: 'Sin actividad todavía.',
      in_focus: 'En foco · hasta {t}', in_meeting: 'En reunión · hasta {t}', available: 'Disponible',
      e_title: 'Algo salió mal'
    }
  };
  function t(k, p) {
    var s = (_TRANS[LANG] && _TRANS[LANG][k]) || _TRANS.en[k] || k;
    if (p) Object.keys(p).forEach(function (x) { s = s.split('{' + x + '}').join(p[x]); });
    return s;
  }
  function $(id) { return document.getElementById(id); }

  var S = { d: null, preset: null, now: 'team', clockSkew: 0 };

  // ── Horas ───────────────────────────────────────────────────────────────
  function dt(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T?(\d{2})?:?(\d{2})?/.exec(String(iso || ''));
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)) : null;
  }
  function hm(iso) {
    var d = dt(iso);
    return d ? d.toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' }) : '';
  }
  // "agora" do SERVIDOR (o horário do Brasil), andando com o relógio da tela
  function nowMs() { return Date.now() + S.clockSkew; }
  function hours(min) {
    if (min < 60) return min + 'm';
    var h = min / 60;
    return (Math.round(h * 10) / 10).toLocaleString(LOCALE) + 'h';
  }

  // ── Carga ───────────────────────────────────────────────────────────────
  function load() {
    return P.api('GET', '/api/user-home').then(function (d) {
      S.d = d;
      var srv = new Date(d.now);                      // ISO sem fuso = hora local
      if (!isNaN(srv.getTime())) S.clockSkew = srv.getTime() - Date.now();
      if (d.meta) P.setMeta(d.meta);
      if (window.otcFocus) {
        window.otcFocus.prefs({ focus_minutes: d.settings.focus_minutes, break_minutes: d.settings.break_minutes, notify: d.settings.notify });
        var st = window.otcFocus.state();
        if (!(st && st.kind === 'break')) window.otcFocus.adopt(d.focus);
      }
      if (S.preset == null) S.preset = d.settings.focus_minutes;
      render();
    }).catch(P.fail);
  }

  function render() {
    var d = S.d;
    renderHead(d);
    renderRings(d);
    renderNext(d);
    renderFocus();
    renderTasks(d);
    renderWeek(d.week);
    renderProjects(d);
    renderNow(d);
    P.icons(document.getElementById('uh-page'));
  }

  function renderHead(d) {
    var h = (dt(d.now) || new Date()).getHours();
    var first = String(d.me.name || '').split(/\s+/)[0] || d.me.sid;
    $('uh-hello').textContent = t(h < 12 ? 'morning' : (h < 18 ? 'afternoon' : 'evening'), { n: first });
    var date = (dt(d.today) || new Date()).toLocaleDateString(LOCALE, { weekday: 'long', month: 'long', day: 'numeric' });
    date = date.charAt(0).toUpperCase() + date.slice(1);
    var nowIso = d.now;
    var meetLeft = (d.events_today || []).filter(function (e) { return !e.all_day && String(e.end) > nowIso; }).length;
    var tasksLeft = (d.my_tasks || []).filter(function (x) { return x.status !== 'Done'; }).length;
    $('uh-sub').textContent = t('sub', { date: date, m: meetLeft === 1 ? t('m1') : t('mn', { n: meetLeft }),
                                          t: tasksLeft === 1 ? t('t1') : t('tn', { n: tasksLeft }) });
    $('uh-n-done').textContent = d.stats.done_today;
    $('uh-n-done-of').textContent = '/ ' + d.stats.tasks_today;
    $('uh-n-focus').textContent = hours(d.stats.focus_minutes);
    $('uh-n-overdue').textContent = d.stats.overdue;
    $('uh-overdue-tile').classList.toggle('is-alert', d.stats.overdue > 0);
    $('uh-new-task').classList.toggle('d-none', !d.can_projects || !(d.projects_all || []).length);
    var nx = d.next_event;
    $('uh-next-btn').classList.toggle('d-none', !nx);
    if (nx) $('uh-next-label').textContent = t('next', { t: hm(nx.start) });
    $('uh-sync').title = d.synced_at ? t('synced', { when: P.ago(d.synced_at.replace('T', ' ')) }) : t('never');
  }

  // ── Today: os anéis ─────────────────────────────────────────────────────
  var RING_C = { tasks: '#ff375f', focus: '#30d158', meet: '#40c8e0' };
  function renderRings(d) {
    var r = d.rings;
    var rows = [
      { k: 'tasks', r: 74, v: r.tasks.total ? r.tasks.done / r.tasks.total : 0 },
      { k: 'focus', r: 58, v: r.focus.goal ? Math.min(1, r.focus.minutes / r.focus.goal) : 0 },
      { k: 'meet', r: 42, v: r.meetings.total ? r.meetings.done / r.meetings.total : 0 }
    ];
    var svg = '<svg viewBox="0 0 168 168">' + rows.map(function (x) {
      var c = 2 * Math.PI * x.r;
      return '<circle class="is-track" cx="84" cy="84" r="' + x.r + '" stroke="' + RING_C[x.k] + '"/>' +
        '<circle class="is-bar" cx="84" cy="84" r="' + x.r + '" stroke="' + RING_C[x.k] + '" stroke-dasharray="' + c.toFixed(2) +
        '" stroke-dashoffset="' + c.toFixed(2) + '" data-off="' + (c * (1 - Math.max(0.0001, x.v))).toFixed(2) + '"/>';
    }).join('') + '</svg>';
    var leg = '<div class="uh-legend">' +
      '<div style="--c:' + RING_C.tasks + '"><span>' + esc(t('rings_tasks')) + '</span><b>' + r.tasks.done + '</b><small> / ' + r.tasks.total + '</small></div>' +
      '<div style="--c:' + RING_C.focus + '"><span>' + esc(t('rings_focus')) + '</span><b>' + hours(r.focus.minutes) + '</b><small> / ' + hours(r.focus.goal) + '</small></div>' +
      '<div style="--c:' + RING_C.meet + '"><span>' + esc(t('rings_meet')) + '</span><b>' + r.meetings.done + '</b><small> / ' + r.meetings.total + '</small></div>' +
      '</div>';
    $('uh-rings').innerHTML = svg + leg;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call(document.querySelectorAll('#uh-rings .is-bar'), function (c) {
          c.setAttribute('stroke-dashoffset', c.getAttribute('data-off'));
        });
      });
    });
  }

  // ── Up next ─────────────────────────────────────────────────────────────
  function untilText(iso) {
    var d = dt(iso);
    if (!d) return '';
    var min = Math.round((d.getTime() - nowMs()) / 60000);
    if (min <= 0) return t('now');
    if (min < 60) return t('in_min', { n: min });
    return t('in_h', { n: Math.round(min / 60) });
  }
  var EV_HUES = ['var(--otc-pink)', 'var(--otc-purple)', 'var(--otc-indigo)', 'var(--otc-teal)', 'var(--otc-orange)'];
  function renderNext(d) {
    var box = $('uh-next'), evs = d.events_today || [], nx = d.next_event, html = '';
    if (!d.synced_at) {
      html = '<div class="uh-empty"><i data-lucide="calendar-sync"></i><div>' + esc(t('no_sync')) + '</div>' +
        '<button type="button" class="btn btn-primary rounded-pill btn-sm" data-sync>' + esc(t('sync')) + '</button></div>';
      box.innerHTML = html;
      return;
    }
    if (nx) {
      var who = (nx.attendees || []).slice(0, 5).map(function (n) { return { sid: n, name: n }; });
      html += '<div class="uh-next">' +
        '<div class="uh-next__when">' + esc(untilText(nx.start)).replace(/(\d+)/, '<b>$1</b>') + '</div>' +
        '<div class="uh-next__title" title="' + esc(nx.title) + '">' + esc(nx.title || '—') + '</div>' +
        '<div class="uh-next__meta">' + esc(hm(nx.start) + ' – ' + hm(nx.end)) + (nx.location ? ' · ' + esc(nx.location) : '') + '</div>' +
        '<div class="uh-next__foot">' + P.avatars(who, 4) +
        (nx.join_url ? '<a class="btn btn-primary rounded-pill btn-sm d-inline-flex align-items-center gap-1" data-join href="' + esc(nx.join_app || nx.join_url) + '"' +
          (nx.join_app ? '' : ' target="_blank" rel="noopener"') + '><i data-lucide="video"></i>' + esc(t('join')) + '</a>' : '') +
        '</div></div>';
    }
    var resto = evs.filter(function (e) { return !nx || e !== nx && e.id !== nx.id; });
    if (resto.length) {
      html += '<ul class="uh-evs">' + resto.slice(0, 5).map(function (e, i) {
        var past = !e.all_day && String(e.end) <= d.now;
        return '<li class="' + (past ? 'is-past' : '') + '" style="--c:' + EV_HUES[i % EV_HUES.length] + '"><b title="' + esc(e.title) + '">' + esc(e.title || '—') + '</b><span>' +
          (e.all_day ? '—' : esc(hm(e.start))) + '</span></li>';
      }).join('') + '</ul>';
    }
    if (!nx && !resto.length) html += '<div class="uh-empty"><i data-lucide="calendar-check"></i><div>' + esc(t('no_more')) + '</div></div>';
    html += '<div class="uh-sync-note"><i data-lucide="refresh-cw"></i>' + esc(t('synced', { when: P.ago(d.synced_at.replace('T', ' ')) })) + '</div>';
    box.innerHTML = html;
  }

  // ── Focus ───────────────────────────────────────────────────────────────
  function renderFocus() {
    var d = S.d, F = window.otcFocus, st = F ? F.state() : null;
    var running = st && st.kind === 'focus', paused = running && st.left != null, onBreak = st && st.kind === 'break';
    $('uh-presets').innerHTML = (d.focus_presets || [15, 25, 50]).map(function (m) {
      return '<button type="button" data-preset="' + m + '" class="' + (m === S.preset ? 'is-on' : '') + '"' + (running ? ' disabled' : '') + '>' + m + 'm</button>';
    }).join('');
    var sel = $('uh-focus-task');
    var cur = sel.value;
    sel.innerHTML = '<option value="">' + esc(t('just_focus')) + '</option>' + (d.open_tasks || []).map(function (x) {
      return '<option value="' + esc(x.project_id + '|' + x.task_id) + '">' + esc(x.title) + '</option>';
    }).join('');
    if (cur) sel.value = cur;
    if (running && d.focus && d.focus.task_id) sel.value = d.focus.project_id + '|' + d.focus.task_id;
    sel.disabled = !!running;
    var btns = '';
    if (!running) btns = '<button type="button" class="btn btn-primary rounded-pill" data-focus="start"><i data-lucide="play"></i>' + esc(t('start')) + '</button>';
    else btns = '<button type="button" class="btn btn-secondary rounded-pill" data-focus="' + (paused ? 'resume' : 'pause') + '"><i data-lucide="' + (paused ? 'play' : 'pause') + '"></i>' + esc(t(paused ? 'resume' : 'pause')) + '</button>' +
      '<button type="button" class="btn btn-secondary rounded-pill" data-focus="end"><i data-lucide="square"></i>' + esc(t('end')) + '</button>';
    $('uh-focus-btns').innerHTML = btns;
    tickFocus();
    var mins = d.stats.focus_minutes, n = d.stats.focus_sessions;
    $('uh-focused-txt').textContent = n === 1 ? t('focused1', { h: hours(mins) }) : t('focused', { h: hours(mins), n: n });
    $('uh-focused-bar').style.width = Math.min(100, Math.round(100 * mins / (d.settings.focus_goal_minutes || 120))) + '%';
    P.icons($('uh-focus-btns'));
  }
  function tickFocus() {
    var F = window.otcFocus, st = F ? F.state() : null;
    var running = st && st.kind === 'focus', onBreak = st && st.kind === 'break';
    var total = (running || onBreak) ? (st.total || 1) : S.preset * 60;
    var left = (running || onBreak) ? F.left() : S.preset * 60;
    $('uh-timer-txt').textContent = Math.floor(left / 60) + ':' + ('0' + (left % 60)).slice(-2);
    $('uh-timer-state').textContent = onBreak ? t('on_break') : (running ? (st.left != null ? t('paused') : t('focusing')) : t('ready'));
    var c = 2 * Math.PI * 47, bar = document.querySelector('#uh-timer .is-bar');
    bar.setAttribute('stroke-dasharray', c.toFixed(2));
    bar.setAttribute('stroke-dashoffset', (c * (1 - left / total)).toFixed(2));
    bar.style.stroke = onBreak ? 'var(--otc-green)' : '';
  }
  function focusAction(a) {
    var F = window.otcFocus;
    if (!F) return;
    var p;
    if (a === 'start') {
      var v = $('uh-focus-task').value.split('|');
      p = F.start(S.preset, v[1] ? { project_id: v[0], task_id: v[1] } : null);
    } else p = F[a]();
    p.then(function () { return load(); }).catch(function (e) { P.fail(e); });
  }

  // ── My tasks ────────────────────────────────────────────────────────────
  function renderTasks(d) {
    var ul = $('uh-tasks');
    if (!d.can_projects) { ul.innerHTML = '<li class="uh-empty" style="cursor:default"><i data-lucide="lock"></i><div>' + esc(t('no_access')) + '</div></li>'; return; }
    var rows = d.my_tasks || [];
    if (!rows.length) { ul.innerHTML = '<li class="uh-empty" style="cursor:default"><i data-lucide="party-popper"></i><div>' + esc(t('no_tasks')) + '</div></li>'; return; }
    ul.innerHTML = rows.map(function (x) {
      var done = x.status === 'Done';
      var due = done ? { text: P.fmtShort((x.done_at || '').slice(0, 10)), cls: '' } : P.due(x.due, false);
      return '<li class="' + (done ? 'is-done' : '') + '" data-pid="' + esc(x.project_id) + '" data-tid="' + esc(x.id) + '">' +
        '<button type="button" class="uh-check' + (done ? ' is-on' : '') + '" data-check aria-pressed="' + done + '" title="' + esc(done ? P.t('reopen') : P.t('mark_done')) + '"><i data-lucide="check"></i></button>' +
        '<div class="uh-tasks__body"><div class="uh-tasks__title">' + esc(x.title) + '</div>' +
        '<div class="uh-tasks__meta">' + P.chip(x.project_name, P.colorVar(x.project_color)) +
        (due ? '<span class="pj-meta ' + due.cls + '">' + esc(due.text) + '</span>' : '') + '</div></div>' +
        (done ? '' : P.prioBadge(x.priority)) + '</li>';
    }).join('');
  }
  function findTask(pid, tid) {
    return (S.d.my_tasks || []).filter(function (x) { return x.project_id === pid && x.id === tid; })[0];
  }
  function toggleDone(pid, tid) {
    var x = findTask(pid, tid);
    if (!x) return;
    var antes = x.status, novo = antes === 'Done' ? 'To do' : 'Done';
    var url = '/api/projects/' + encodeURIComponent(pid) + '/tasks/' + encodeURIComponent(tid);
    P.api('PATCH', url, { status: novo }).then(function () {
      load();
      if (window.otcToast) window.otcToast((novo === 'Done' ? t('done_lbl') : t('reopened')) + ': ' + x.title, {
        undo: function () { P.api('PATCH', url, { status: antes }).then(load).catch(P.fail); }
      });
    }).catch(P.fail);
  }
  function openTask(pid, tid) {
    var x = findTask(pid, tid);
    if (!x) return;
    P.openTaskDrawer({ project: { id: x.project_id, name: x.project_name, color: x.project_color }, task: x,
                       onChange: function () { load(); } });
  }

  // ── This week ───────────────────────────────────────────────────────────
  function renderWeek(w) {
    var dp = w.delta_pct;
    $('uh-week-sum').innerHTML = '<b>' + w.total + '</b><span>' + esc(t('finished')) + '</span>' +
      (dp == null ? '' : '<span class="uh-delta ' + (dp >= 0 ? 'is-up' : 'is-down') + '">' + (dp >= 0 ? '+' : '') + dp + '% ' + esc(t('vs_last')) + '</span>');
    var max = Math.max.apply(null, w.days.map(function (x) { return x.n; }).concat([1]));
    var wd = P.t('wd');
    $('uh-bars').innerHTML = w.days.map(function (x) {
      var d = dt(x.date), today = x.date === w.today, fut = x.date > w.today;
      var h = fut ? 0 : Math.round(100 * x.n / max);
      return '<div class="' + (today ? 'is-today' : '') + '"><div class="uh-track"><div class="uh-fill" style="height:0" data-h="' + h + '%">' +
        (x.n ? '<span class="uh-n">' + x.n + '</span>' : '') + '</div></div><label>' + esc(wd[d.getDay()]) + '</label></div>';
    }).join('');
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call(document.querySelectorAll('#uh-bars .uh-fill'), function (f) { f.style.height = f.getAttribute('data-h'); });
      });
    });
  }

  // ── Projects ────────────────────────────────────────────────────────────
  function renderProjects(d) {
    var ul = $('uh-projs'), rows = d.projects || [];
    if (!d.can_projects) { ul.innerHTML = '<li class="uh-empty"><i data-lucide="lock"></i><div>' + esc(t('no_access')) + '</div></li>'; return; }
    if (!rows.length) { ul.innerHTML = '<li class="uh-empty"><i data-lucide="folder-open"></i><div>' + esc(t('no_projects')) + '</div></li>'; return; }
    ul.innerHTML = rows.map(function (p) {
      var hue = P.colorVar(p.color);
      return '<li><a href="/projects/' + encodeURIComponent(p.id) + '">' +
        '<span class="otc-icon-tile" style="--hue:' + hue + '"><i data-lucide="' + esc(p.icon || 'folder') + '"></i></span>' +
        '<span class="min-w-0"><b>' + esc(p.name) + '</b><small>' + esc(P.tStatus(p.status)) + ' · ' +
        esc(p.due_date ? t('due', { d: P.fmtShort(p.due_date) }) : t('no_due')) + '</small></span>' +
        '<span class="uh-bar" style="--c:' + hue + '"><span style="width:' + p.progress + '%"></span></span>' +
        '<span class="uh-pct">' + p.progress + '%</span>' + P.avatars(p.people, 3) + '</a></li>';
    }).join('');
  }

  // ── Right now ───────────────────────────────────────────────────────────
  var DOT = { focus: 'var(--otc-purple)', meeting: 'var(--otc-orange)', free: 'var(--otc-green)' };
  function renderNow(d) {
    var box = $('uh-now');
    Array.prototype.forEach.call(document.querySelectorAll('#uh-now-seg [data-now]'), function (b) {
      b.classList.toggle('is-on', b.getAttribute('data-now') === S.now);
    });
    if (S.now === 'team') {
      var team = d.team || [];
      if (!team.length) { box.innerHTML = '<div class="uh-empty"><i data-lucide="users"></i><div>' + esc(t(d.can_projects ? 'no_team' : 'no_access')) + '</div></div>'; return; }
      box.innerHTML = '<ul class="uh-people">' + team.map(function (p) {
        var txt = p.state === 'focus' ? t('in_focus', { t: hm(p.until) }) : (p.state === 'meeting' ? t('in_meeting', { t: hm(p.until) }) : (p.position || t('available')));
        return '<li><span class="uh-av" style="--dot:' + DOT[p.state] + '">' + P.avatar(p.sid, p.name, 'lg') + '</span>' +
          '<span class="min-w-0"><b>' + esc(p.name) + '</b><small>' + esc(txt) + '</small></span></li>';
      }).join('') + '</ul>';
      return;
    }
    var acts = d.activity || [];
    if (!acts.length) { box.innerHTML = '<div class="uh-empty"><i data-lucide="activity"></i><div>' + esc(t('no_act')) + '</div></div>'; return; }
    box.innerHTML = '<ul class="uh-acts">' + acts.map(function (a) {
      return '<li>' + P.avatar(a.sid, a.name, 'sm') + '<div class="min-w-0"><p>' + P.activityText(a) + '</p><small>' +
        esc(a.project_name) + ' · ' + esc(P.ago(a.at)) + '</small></div></li>';
    }).join('') + '</ul>';
  }

  // ── Sync ────────────────────────────────────────────────────────────────
  function sync() {
    var b = $('uh-sync');
    b.disabled = true; b.classList.add('is-busy');
    P.api('POST', '/api/user-home/sync').then(function (d) {
      if (window.otcToast) window.otcToast(t('sync_ok', { n: d.events }));
      return load();
    }).catch(function (e) {
      if (window.Swal) Swal.fire({ icon: 'warning', title: t('sync_fail'), text: (e.code === 'outlook_unavailable' || e.code === 'calendar_not_accessible') ? t(e.code) : P.errText(e) });
    }).then(function () { b.disabled = false; b.classList.remove('is-busy'); });
  }

  function wire() {
    $('uh-sync').addEventListener('click', sync);
    $('uh-new-task').addEventListener('click', function () {
      P.openTaskModal({ projects: S.d.projects_all || [], onSaved: function () { load(); } });
    });
    $('uh-next-btn').addEventListener('click', function () {
      // a reunião é por ZOOM: o `zoommtg://` abre o aplicativo; sem ele, o https
      var nx = S.d && S.d.next_event;
      if (nx && nx.join_app) location.href = nx.join_app;
      else if (nx && nx.join_url) window.open(nx.join_url, '_blank', 'noopener');
      else $('uh-next').scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    document.getElementById('uh-page').addEventListener('click', function (e) {
      if (e.target.closest('[data-sync]')) { sync(); return; }
      var pr = e.target.closest('[data-preset]');
      if (pr) { S.preset = +pr.getAttribute('data-preset'); renderFocus(); return; }
      var fa = e.target.closest('[data-focus]');
      if (fa) { focusAction(fa.getAttribute('data-focus')); return; }
      var nw = e.target.closest('[data-now]');
      if (nw) { S.now = nw.getAttribute('data-now'); renderNow(S.d); P.icons($('uh-now')); return; }
      var li = e.target.closest('#uh-tasks li[data-tid]');
      if (li) {
        if (e.target.closest('[data-check]')) toggleDone(li.getAttribute('data-pid'), li.getAttribute('data-tid'));
        else openTask(li.getAttribute('data-pid'), li.getAttribute('data-tid'));
      }
    });
    if (window.otcFocus) window.otcFocus.on(function () { if (S.d) tickFocus(); });
    // a cada minuto: o "in 20 min", o próximo evento e a presença dos colegas
    setInterval(function () { if (!document.hidden) load(); }, 60000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden && S.d) load(); });
  }

  wire();
  load();
})();

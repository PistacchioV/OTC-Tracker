/* ============================================================================
 * settings.js — Settings (§632), a do Pane. A Aparência é a do tema (`otcUI`
 * e os `data-*-pick` que o otc.js já atende); avisos e foco gravam em
 * `/api/settings`, no documento do próprio usuário; o foco começa pela ilha
 * (`otcFocus`, otc.js §3e).
 * ========================================================================== */
(function () {
  'use strict';
  var P = window.OtcPj;
  var esc = P.esc;
  var LANG = 'en';
  try { LANG = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}

  var _TRANS = {
    en: {
      name: 'Name', email: 'Email', role: 'Desk', sid: 'SID',
      n_task_assigned: 'Task assigned', n_task_assigned_s: 'When a task is given to you',
      n_task_comment: 'Comments', n_task_comment_s: 'When someone comments on your task',
      n_project_lead: 'Initiative lead', n_project_lead_s: 'When you are made lead of an initiative',
      n_project_member: 'Initiative team', n_project_member_s: 'When you are added to the team of an initiative',
      n_due_dates: 'Due dates', n_due_dates_s: 'The morning a task of yours is due (08:00)',
      n_focus_finished: 'Focus finished', n_focus_finished_s: 'When a session ends',
      session: 'Session', break_: 'Break', goal: 'Daily goal', min: 'min', shorter: 'Shorter', longer: 'Longer',
      start_sub: '{s} minutes, then a {b}-minute break', started: 'Focus started — the island keeps the time',
      export_sub: '{n} tasks, one row each', export_none: 'No tasks of yours yet', saved: 'Saved',
      reset_q: 'Reset to defaults?', reset_txt: 'Theme, wallpaper, accent, glass, notifications and focus go back to the original.',
      reset_ok: 'Back to defaults', reset: 'Reset', cancel: 'Cancel',
      walls: { ash: 'Ash', sand: 'Sand', sage: 'Sage', aurora: 'Aurora', smoke: 'Smoke', tide: 'Tide', bloom: 'Bloom', ember: 'Ember', grove: 'Grove', dusk: 'Dusk', canyon: 'Canyon', fjord: 'Fjord', glacier: 'Glacier' },
      accents: { blue: 'Blue', purple: 'Purple', pink: 'Pink', orange: 'Orange', green: 'Green', graphite: 'Graphite' },
    },
    br: {
      name: 'Nome', email: 'E-mail', role: 'Mesa', sid: 'SID',
      n_task_assigned: 'Tarefa atribuída', n_task_assigned_s: 'Quando uma tarefa é passada para você',
      n_task_comment: 'Comentários', n_task_comment_s: 'Quando alguém comenta na sua tarefa',
      n_project_lead: 'Líder de iniciativa', n_project_lead_s: 'Quando você vira líder de uma iniciativa',
      n_project_member: 'Time de iniciativa', n_project_member_s: 'Quando você é incluído no time de uma iniciativa',
      n_due_dates: 'Prazos', n_due_dates_s: 'Na manhã em que uma tarefa sua vence (08:00)',
      n_focus_finished: 'Fim do foco', n_focus_finished_s: 'Quando uma sessão termina',
      session: 'Sessão', break_: 'Pausa', goal: 'Meta diária', min: 'min', shorter: 'Menos', longer: 'Mais',
      start_sub: '{s} minutos, depois uma pausa de {b} minutos', started: 'Foco iniciado — a ilha marca o tempo',
      export_sub: '{n} tarefas, uma linha cada', export_none: 'Nenhuma tarefa sua ainda', saved: 'Salvo',
      reset_q: 'Voltar ao padrão?', reset_txt: 'Tema, papel de parede, destaque, vidro, avisos e foco voltam ao original.',
      reset_ok: 'De volta ao padrão', reset: 'Voltar', cancel: 'Cancelar',
      walls: { ash: 'Cinza', sand: 'Areia', sage: 'Sálvia', aurora: 'Aurora', smoke: 'Fumaça', tide: 'Maré', bloom: 'Flor', ember: 'Brasa', grove: 'Bosque', dusk: 'Crepúsculo', canyon: 'Cânion', fjord: 'Fiorde', glacier: 'Geleira' },
      accents: { blue: 'Azul', purple: 'Roxo', pink: 'Rosa', orange: 'Laranja', green: 'Verde', graphite: 'Grafite' },
    },
    es: {
      name: 'Nombre', email: 'Correo', role: 'Mesa', sid: 'SID',
      n_task_assigned: 'Tarea asignada', n_task_assigned_s: 'Cuando le asignan una tarea',
      n_task_comment: 'Comentarios', n_task_comment_s: 'Cuando alguien comenta su tarea',
      n_project_lead: 'Líder de iniciativa', n_project_lead_s: 'Cuando lo nombran líder de una iniciativa',
      n_project_member: 'Equipo de iniciativa', n_project_member_s: 'Cuando lo incluyen en el equipo de una iniciativa',
      n_due_dates: 'Vencimientos', n_due_dates_s: 'La mañana en que vence una tarea suya (08:00)',
      n_focus_finished: 'Fin del foco', n_focus_finished_s: 'Cuando termina una sesión',
      session: 'Sesión', break_: 'Pausa', goal: 'Meta diaria', min: 'min', shorter: 'Menos', longer: 'Más',
      start_sub: '{s} minutos, luego una pausa de {b} minutos', started: 'Foco iniciado — la isla marca el tiempo',
      export_sub: '{n} tareas, una fila cada una', export_none: 'Aún no tiene tareas', saved: 'Guardado',
      reset_q: '¿Volver a los valores originales?', reset_txt: 'Tema, fondo, acento, vidrio, avisos y foco vuelven al original.',
      reset_ok: 'Valores originales restaurados', reset: 'Restaurar', cancel: 'Cancelar',
      walls: { ash: 'Ceniza', sand: 'Arena', sage: 'Salvia', aurora: 'Aurora', smoke: 'Humo', tide: 'Marea', bloom: 'Flor', ember: 'Brasa', grove: 'Bosque', dusk: 'Ocaso', canyon: 'Cañón', fjord: 'Fiordo', glacier: 'Glaciar' },
      accents: { blue: 'Azul', purple: 'Violeta', pink: 'Rosa', orange: 'Naranja', green: 'Verde', graphite: 'Grafito' },
    }
  };
  function t(k, p) {
    var s = (_TRANS[LANG] && _TRANS[LANG][k]) || _TRANS.en[k] || k;
    if (p && typeof s === 'string') Object.keys(p).forEach(function (x) { s = s.split('{' + x + '}').join(p[x]); });
    return s;
  }
  function $(id) { return document.getElementById(id); }

  var NOTIFY = [
    ['task_assigned', 'list-checks', 'var(--otc-blue)'],
    ['task_comment', 'message-square', 'var(--otc-teal)'],
    ['project_lead', 'folder-kanban', 'var(--otc-purple)'],
    ['project_member', 'users', 'var(--otc-indigo)'],
    ['due_dates', 'flag', 'var(--otc-orange)'],
    ['focus_finished', 'timer', 'var(--otc-pink)']
  ];
  var STEPS = [
    ['focus_minutes', 'session', 5, 5, 120],
    ['break_minutes', 'break_', 1, 1, 60],
    ['focus_goal_minutes', 'goal', 15, 15, 600]
  ];
  var S = { st: null, me: null, tasks: null };

  function load() {
    return P.api('GET', '/api/settings').then(function (d) {
      S.st = d.settings; S.me = d.me; S.can = d.can_projects;
      publishFocusPrefs();
      render();
    }).catch(P.fail);
  }
  function publishFocusPrefs() {
    if (window.otcFocus) window.otcFocus.prefs({ focus_minutes: S.st.focus_minutes, break_minutes: S.st.break_minutes, notify: S.st.notify });
  }

  function render() {
    var me = S.me;
    $('st-me').innerHTML = P.avatar(me.sid, me.name || me.sid, 'lg', me.photo) + '<div class="min-w-0"><b>' + esc(me.name || me.sid) + '</b><small>' + esc(me.email || '') + '</small></div>';
    $('st-profile-head').innerHTML = '<span class="st-avwrap">' + P.avatar(me.sid, me.name || me.sid, '', me.photo) + '</span><div class="min-w-0"><h3>' + esc(me.name || me.sid) +
      '</h3><div class="st-pos">' + esc(me.position || me.role || '') + '</div><div class="st-mail">' + esc(me.email || '') + '</div></div>';
    $('st-profile-rows').innerHTML = [
      ['user-round', 'var(--otc-blue)', 'name', me.name || '—'],
      ['mail', 'var(--otc-indigo)', 'email', me.email || '—'],
      ['badge-check', 'var(--otc-teal)', 'role', me.role || '—'],
      ['id-card', 'var(--otc-orange)', 'sid', me.sid]
    ].map(function (r) {
      return '<div class="st-row"><span class="st-ico" style="--hue:' + r[1] + '"><i data-lucide="' + r[0] + '"></i></span>' +
        '<div class="st-row__txt"><b>' + esc(t(r[2])) + '</b></div><div class="st-row__val" title="' + esc(r[3]) + '">' + esc(r[3]) + '</div></div>';
    }).join('');

    $('st-notify-rows').innerHTML = NOTIFY.map(function (n) {
      var on = S.st.notify[n[0]] !== false;
      return '<div class="st-row"><span class="st-ico" style="--hue:' + n[2] + '"><i data-lucide="' + n[1] + '"></i></span>' +
        '<div class="st-row__txt"><b>' + esc(t('n_' + n[0])) + '</b><small>' + esc(t('n_' + n[0] + '_s')) + '</small></div>' +
        '<div class="form-check form-switch m-0"><input class="form-check-input" type="checkbox" role="switch" data-notify="' + n[0] + '"' + (on ? ' checked' : '') +
        ' aria-label="' + esc(t('n_' + n[0])) + '"></div></div>';
    }).join('');

    var walls = (window.otcUI && otcUI.walls) || [];
    $('st-walls').innerHTML = walls.map(function (k) {
      return '<button type="button" class="st-wall" data-wall-pick="' + k + '"><span class="st-wall__art" data-art="' + k + '"><i></i><i></i><i></i></span>' +
        esc(t('walls')[k] || k) + '</button>';
    }).join('');

    $('st-steps').innerHTML = STEPS.map(function (s) {
      var v = S.st[s[0]];
      return '<div class="st-step"><button type="button" data-step="' + s[0] + '" data-dir="-1" aria-label="' + esc(t('shorter')) + '"' + (v <= s[3] ? ' disabled' : '') + '><i data-lucide="minus"></i></button>' +
        '<div class="text-center"><span class="pj-label">' + esc(t(s[1])) + '</span><b>' + v + '</b><small>' + esc(t('min')) + '</small></div>' +
        '<button type="button" data-step="' + s[0] + '" data-dir="1" aria-label="' + esc(t('longer')) + '"' + (v >= s[4] ? ' disabled' : '') + '><i data-lucide="plus"></i></button></div>';
    }).join('');
    $('st-start-sub').textContent = t('start_sub', { s: S.st.focus_minutes, b: S.st.break_minutes });

    if (S.tasks == null && S.can) {
      P.api('GET', '/api/tasks').then(function (d) {
        var sid = (S.me.sid || '').toUpperCase();
        S.tasks = (d.tasks || []).filter(function (x) { return String(x.assignee_sid || '').toUpperCase() === sid; }).length;
        exportSub();
      }).catch(function () { S.tasks = 0; exportSub(); });
    }
    exportSub();
    $('st-export').classList.toggle('d-none', !S.can);
    syncNames();
    if (window.otcUI) otcUI.set({}, false);              // marca o que está escolhido nas listas novas
    P.icons(document.getElementById('st-page'));
  }
  function exportSub() {
    $('st-export-sub').textContent = S.tasks == null ? '' : (S.tasks ? t('export_sub', { n: S.tasks }) : t('export_none'));
  }
  function syncNames() {
    var p = window.otcUI ? otcUI.get() : {};
    $('st-wall-name').textContent = t('walls')[p.wall] || p.wall || '';
    $('st-accent-name').textContent = t('accents')[p.accent] || p.accent || '';
  }

  function save(patch) {
    return P.api('POST', '/api/settings', patch).then(function (d) {
      S.st = d.settings;
      publishFocusPrefs();
      return d;
    });
  }

  function wire() {
    var page = $('st-page');
    page.addEventListener('change', function (e) {
      var n = e.target.closest('[data-notify]');
      if (!n) return;
      var k = n.getAttribute('data-notify'), body = { notify: {} };
      body.notify[k] = n.checked;
      save(body).then(function () { if (window.otcToast) window.otcToast(t('saved') + ': ' + t('n_' + k)); })
        .catch(function (err) { n.checked = !n.checked; P.fail(err); });
    });
    page.addEventListener('click', function (e) {
      var st = e.target.closest('[data-step]');
      if (st) {
        var k = st.getAttribute('data-step'), dir = +st.getAttribute('data-dir');
        var def = STEPS.filter(function (s) { return s[0] === k; })[0];
        var v = Math.min(def[4], Math.max(def[3], S.st[k] + dir * def[2]));
        if (v === S.st[k]) return;
        var body = {}; body[k] = v;
        S.st[k] = v; render();
        save(body).catch(function (err) { P.fail(err); load(); });
        return;
      }
      var nav = e.target.closest('#st-nav a');
      if (nav) {
        e.preventDefault();
        Array.prototype.forEach.call(document.querySelectorAll('#st-nav a'), function (a) { a.classList.toggle('is-on', a === nav); });
        var alvo = document.querySelector(nav.getAttribute('href'));
        if (alvo) alvo.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
    $('st-start').addEventListener('click', function () {
      if (!window.otcFocus) return;
      otcFocus.start(S.st.focus_minutes).then(function () {
        if (window.otcToast) window.otcToast(t('started'));
        if ('Notification' in window && Notification.permission === 'default' && S.st.notify.focus_finished) {
          try { Notification.requestPermission(); } catch (er) {}
        }
      }).catch(P.fail);
    });
    $('st-reset').addEventListener('click', function () {
      var go = function () {
        save({ reset: true }).then(function () {
          if (window.otcUI) { otcUI.set({ theme: 'light', accent: 'blue', wall: 'ash', glass: 'tinted' }, true); otcUI.fx('auto'); }
          render();
          if (window.otcToast) window.otcToast(t('reset_ok'));
        }).catch(P.fail);
      };
      if (!window.Swal) { if (window.confirm(t('reset_q'))) go(); return; }
      Swal.fire({ icon: 'warning', title: t('reset_q'), text: t('reset_txt'), showCancelButton: true,
                  confirmButtonText: t('reset'), cancelButtonText: t('cancel') })
        .then(function (r) { if (r.isConfirmed) go(); });
    });
    window.addEventListener('otc:appearance', syncNames);
    // a seção na tela marca o item do menu da esquerda
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (ents) {
        ents.forEach(function (en) {
          if (!en.isIntersecting) return;
          var id = '#' + en.target.id;
          Array.prototype.forEach.call(document.querySelectorAll('#st-nav a'), function (a) { a.classList.toggle('is-on', a.getAttribute('href') === id); });
        });
      }, { rootMargin: '-35% 0px -55% 0px' });
      ['st-profile', 'st-notify', 'st-look', 'st-focus', 'st-data'].forEach(function (id) { var el = $(id); if (el) io.observe(el); });
    }
  }

  wire();
  load();
})();

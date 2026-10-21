/* ============================================================================
 * projects-common.js — o que as três telas do Intraday compartilham (Projects,
 * a página do projeto e Tasks): os textos do JS nas três línguas, a API, as
 * datas, os avatares e as três peças de edição — o modal do projeto, o modal
 * "New task" e a gaveta da tarefa.
 *
 * Exposto como `window.OtcPj`. Toda escrita devolve o PROJETO inteiro já
 * gravado (`/api/projects/...` responde `{project}`), e as telas redesenham a
 * partir dele — nenhuma tela mantém uma cópia própria do que o servidor diz.
 * ========================================================================== */
(function () {
  'use strict';

  var LANG = 'en';
  try { LANG = localStorage.getItem('__OTC_TRACKER_LANG__') || 'en'; } catch (e) {}

  var _TRANS = {
    en: {
      'st_On going': 'On going', 'st_On hold': 'On hold', 'st_Concluded': 'Concluded',
      'ts_To do': 'To do', 'ts_In progress': 'In progress', 'ts_In review': 'In review', 'ts_Done': 'Done',
      'pr_Low': 'Low', 'pr_Medium': 'Medium', 'pr_High': 'High', 'pr_Urgent': 'Urgent',
      'co_blue': 'Blue', 'co_purple': 'Purple', 'co_pink': 'Pink', 'co_orange': 'Orange', 'co_green': 'Green',
      'co_teal': 'Teal', 'co_indigo': 'Indigo', 'co_yellow': 'Yellow',
      'ic_folder': 'Folder', 'ic_rocket': 'Rocket', 'ic_leaf': 'Leaf', 'ic_flame': 'Flame',
      'ic_layout-grid': 'Grid', 'ic_chart-column': 'Chart', 'ic_sparkles': 'Sparkle', 'ic_workflow': 'Workflow',
      today: 'Today', tomorrow: 'Tomorrow', yesterday: 'Yesterday',
      in_days: 'in {n} days', in_day: 'in 1 day', days_ago: '{n} days ago', day_ago: '1 day ago',
      days_late: '{n} days late', day_late: '1 day late',
      just_now: 'just now', min_ago: '{n} min ago', h_ago: '{n} h ago', d_ago: '{n} d ago',
      wd: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'],
      unassigned: 'Unassigned', no_date: 'No date', none: '—',
      new_project: 'New initiative', edit_project: 'Edit initiative', new_task: 'New task',
      saved: 'Saved', deleted: 'Deleted', undo: 'Undo', cancel: 'Cancel', del: 'Delete',
      del_task_q: 'Delete this task?', del_project_q: 'Delete this initiative?',
      del_project_txt: 'Its tasks, milestones and comments go with it. This cannot be undone.',
      del_task_txt: 'Its subtasks and comments go with it.',
      ms_reached: 'Milestone reached: {m}', mark_done: 'Mark done', reopen: 'Reopen',
      no_comments: 'No comments yet.', no_subtasks: 'No subtasks yet.',
      none_status: 'No initiatives with this status', none_filter: 'No initiatives match these filters', all_ms: 'Every milestone met', done_proj: 'Initiative concluded',
      next_ms: 'Next milestone', no_ms: 'No milestones yet', pin: 'Pin to the sidebar', pin_short: 'Pin', pinned: 'Pinned',
      n_tasks: '{done}/{total} tasks', overdue: 'Overdue', days_left: 'Days left', n_open: '{n} open',
      ms_reached_n: '{n} of {total} reached', ms_done: 'Done', complete: 'Complete', next: 'Next',
      open_done: '{open} open · {done} done', no_tasks: 'No tasks yet — add the first one.', hide: 'Hide', show: 'Show',
      done: 'Done', total: 'Total', open_across: '{n} open across {m} initiatives', all_projects: 'All initiatives',
      any_priority: 'Any priority', add_to: 'Add a task to {col}', move_to: 'Move to {col}', open_task: 'Open task',
      move_or_open: 'Move or open “{task}”', n_on_board: '{n} on the board', up_target: 'Target date', up_milestone: 'Milestone', up_empty: 'Nothing coming up.',
      lead: 'Lead',
      team_add: 'Add a person to the team…', team_all_in: 'Everyone eligible is already in', team_remove: 'Remove from the team',
      a_members_added: '{who} added {names} to the team',
      e_assignee_not_in_team: 'Add this person to the initiative team before giving them a task.',
      e_too_many_members: 'At most {max} people in the team.',
      'cat_Process Review': 'Process Review', 'cat_Tech Issue': 'Tech Issue', 'cat_Projects': 'Projects',
      'cat_B3 - Improvements': 'B3 - Improvements', 'cat_Stomp/Red': 'Stomp/Red',
      category: 'Category', all_categories: 'All categories', no_category: 'No category', choose_category: 'Choose…',
      a_created: '{who} created the initiative', a_status: '{who} set the status to {status}',
      a_edited: '{who} edited the initiative', a_task_added: '{who} added “{task}”',
      a_task_done: '{who} completed “{task}”', a_task_moved: '{who} moved “{task}” to {status}',
      a_task_deleted: '{who} deleted “{task}”', a_commented: '{who} commented on “{task}”',
      a_milestone_added: '{who} added the milestone “{milestone}”',
      a_milestone_done: '{who} reached “{milestone}”', a_milestone_reopened: '{who} reopened “{milestone}”',
      e_name_required: 'Give the initiative a name.', e_lead_required: 'Choose the lead.', e_category_required: 'Choose the category.',
      e_not_eligible: 'This person cannot be chosen.', e_bad_choice: 'Invalid value in {field}.', e_bad_number: 'Type a number.', e_out_of_range: 'Between {min} and {max}.', e_bad_action: 'Unknown action.',
      e_bad_date: 'Invalid date.', e_due_before_start: 'The target date is before the start date.',
      e_title_required: 'Give it a title.', e_bad_estimate: 'The estimate must be a number of hours.',
      e_comment_required: 'Write the comment first.', e_project_not_found: 'Initiative not found.',
      e_task_not_found: 'Task not found — it may have been deleted.', e_milestone_not_found: 'Milestone not found.',
      e_subtask_not_found: 'Subtask not found.', e_not_allowed: 'You are not allowed to do this.',
      new_event: 'New event', edit_event: 'Edit event', del_event_q: 'Delete this event?',
      del_event_txt: 'It leaves the Milestones card, Coming up and the Calendar.',
      ev_Milestone: 'Milestone', ev_Meeting: 'Meeting', ev_Deadline: 'Deadline', ev_Review: 'Review', 'ev_Go-live': 'Go-live',
      all_day: 'All day', len_min: '{n} min', len_h: '{h} h', len_hm: '{h} h {m}',
      e_bad_time: 'Invalid time — use hh:mm.',
      e_generic: 'Could not save. Try again.', e_title: 'Not saved'
    },
    br: {
      'st_On going': 'Em andamento', 'st_On hold': 'Em espera', 'st_Concluded': 'Concluído',
      'ts_To do': 'A fazer', 'ts_In progress': 'Em andamento', 'ts_In review': 'Em revisão', 'ts_Done': 'Concluída',
      'pr_Low': 'Baixa', 'pr_Medium': 'Média', 'pr_High': 'Alta', 'pr_Urgent': 'Urgente',
      'co_blue': 'Azul', 'co_purple': 'Roxo', 'co_pink': 'Rosa', 'co_orange': 'Laranja', 'co_green': 'Verde',
      'co_teal': 'Verde-água', 'co_indigo': 'Índigo', 'co_yellow': 'Amarelo',
      'ic_folder': 'Pasta', 'ic_rocket': 'Foguete', 'ic_leaf': 'Folha', 'ic_flame': 'Chama',
      'ic_layout-grid': 'Grade', 'ic_chart-column': 'Gráfico', 'ic_sparkles': 'Brilho', 'ic_workflow': 'Fluxo',
      today: 'Hoje', tomorrow: 'Amanhã', yesterday: 'Ontem',
      in_days: 'em {n} dias', in_day: 'em 1 dia', days_ago: 'há {n} dias', day_ago: 'há 1 dia',
      days_late: '{n} dias de atraso', day_late: '1 dia de atraso',
      just_now: 'agora', min_ago: 'há {n} min', h_ago: 'há {n} h', d_ago: 'há {n} d',
      wd: ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'],
      unassigned: 'Sem responsável', no_date: 'Sem data', none: '—',
      new_project: 'Nova iniciativa', edit_project: 'Editar iniciativa', new_task: 'Nova tarefa',
      saved: 'Salvo', deleted: 'Apagado', undo: 'Desfazer', cancel: 'Cancelar', del: 'Apagar',
      del_task_q: 'Apagar esta tarefa?', del_project_q: 'Apagar esta iniciativa?',
      del_project_txt: 'As tarefas, os marcos e os comentários vão junto. Não dá para desfazer.',
      del_task_txt: 'As subtarefas e os comentários vão junto.',
      ms_reached: 'Marco atingido: {m}', mark_done: 'Concluir', reopen: 'Reabrir',
      no_comments: 'Nenhum comentário ainda.', no_subtasks: 'Nenhuma subtarefa ainda.',
      none_status: 'Nenhuma iniciativa com este status', none_filter: 'Nenhuma iniciativa com estes filtros', all_ms: 'Todos os marcos atingidos', done_proj: 'Iniciativa concluída',
      next_ms: 'Próximo marco', no_ms: 'Nenhum marco ainda', pin: 'Fixar na barra lateral', pin_short: 'Fixar', pinned: 'Fixado',
      n_tasks: '{done}/{total} tarefas', overdue: 'Atrasado', days_left: 'Dias restantes', n_open: '{n} em aberto',
      ms_reached_n: '{n} de {total} atingidos', ms_done: 'Concluído', complete: 'Concluir', next: 'Próximo',
      open_done: '{open} em aberto · {done} concluídas', no_tasks: 'Nenhuma tarefa ainda — adicione a primeira.', hide: 'Ocultar', show: 'Mostrar',
      done: 'Concluídas', total: 'Total', open_across: '{n} em aberto em {m} iniciativas', all_projects: 'Todas as iniciativas',
      any_priority: 'Qualquer prioridade', add_to: 'Adicionar tarefa em {col}', move_to: 'Mover para {col}', open_task: 'Abrir tarefa',
      move_or_open: 'Mover ou abrir “{task}”', n_on_board: '{n} no quadro', up_target: 'Data-alvo', up_milestone: 'Marco', up_empty: 'Nada pela frente.',
      lead: 'Líder',
      team_add: 'Incluir uma pessoa no time…', team_all_in: 'Todos os elegíveis já estão no time', team_remove: 'Tirar do time',
      a_members_added: '{who} incluiu {names} no time',
      e_assignee_not_in_team: 'Inclua esta pessoa no time da iniciativa antes de lhe dar uma tarefa.',
      e_too_many_members: 'No máximo {max} pessoas no time.',
      'cat_Process Review': 'Revisão de Processo', 'cat_Tech Issue': 'Tech Issue', 'cat_Projects': 'Projects',
      'cat_B3 - Improvements': 'B3 - Improvements', 'cat_Stomp/Red': 'Stomp/Red',
      category: 'Categoria', all_categories: 'Todas as categorias', no_category: 'Sem categoria', choose_category: 'Escolha…',
      a_created: '{who} criou a iniciativa', a_status: '{who} mudou o status para {status}',
      a_edited: '{who} editou a iniciativa', a_task_added: '{who} adicionou “{task}”',
      a_task_done: '{who} concluiu “{task}”', a_task_moved: '{who} moveu “{task}” para {status}',
      a_task_deleted: '{who} apagou “{task}”', a_commented: '{who} comentou em “{task}”',
      a_milestone_added: '{who} adicionou o marco “{milestone}”',
      a_milestone_done: '{who} atingiu “{milestone}”', a_milestone_reopened: '{who} reabriu “{milestone}”',
      e_name_required: 'Dê um nome à iniciativa.', e_lead_required: 'Escolha o líder.', e_category_required: 'Escolha a categoria.',
      e_not_eligible: 'Esta pessoa não pode ser escolhida.', e_bad_choice: 'Valor inválido em {field}.', e_bad_number: 'Digite um número.', e_out_of_range: 'Entre {min} e {max}.', e_bad_action: 'Ação desconhecida.',
      e_bad_date: 'Data inválida.', e_due_before_start: 'A data-alvo é anterior ao início.',
      e_title_required: 'Dê um título.', e_bad_estimate: 'A estimativa deve ser um número de horas.',
      e_comment_required: 'Escreva o comentário primeiro.', e_project_not_found: 'Iniciativa não encontrada.',
      e_task_not_found: 'Tarefa não encontrada — pode ter sido apagada.', e_milestone_not_found: 'Marco não encontrado.',
      e_subtask_not_found: 'Subtarefa não encontrada.', e_not_allowed: 'Você não tem permissão para isso.',
      new_event: 'Novo evento', edit_event: 'Editar evento', del_event_q: 'Apagar este evento?',
      del_event_txt: 'Ele sai do card Marcos, do Próximos e do Calendar.',
      ev_Milestone: 'Marco', ev_Meeting: 'Reunião', ev_Deadline: 'Prazo', ev_Review: 'Revisão', 'ev_Go-live': 'Go-live',
      all_day: 'Dia inteiro', len_min: '{n} min', len_h: '{h} h', len_hm: '{h} h {m}',
      e_bad_time: 'Hora inválida — use hh:mm.',
      e_generic: 'Não foi possível salvar. Tente de novo.', e_title: 'Não salvo'
    },
    es: {
      'st_On going': 'En curso', 'st_On hold': 'En pausa', 'st_Concluded': 'Concluido',
      'ts_To do': 'Por hacer', 'ts_In progress': 'En curso', 'ts_In review': 'En revisión', 'ts_Done': 'Hecha',
      'pr_Low': 'Baja', 'pr_Medium': 'Media', 'pr_High': 'Alta', 'pr_Urgent': 'Urgente',
      'co_blue': 'Azul', 'co_purple': 'Morado', 'co_pink': 'Rosa', 'co_orange': 'Naranja', 'co_green': 'Verde',
      'co_teal': 'Turquesa', 'co_indigo': 'Índigo', 'co_yellow': 'Amarillo',
      'ic_folder': 'Carpeta', 'ic_rocket': 'Cohete', 'ic_leaf': 'Hoja', 'ic_flame': 'Llama',
      'ic_layout-grid': 'Cuadrícula', 'ic_chart-column': 'Gráfico', 'ic_sparkles': 'Destello', 'ic_workflow': 'Flujo',
      today: 'Hoy', tomorrow: 'Mañana', yesterday: 'Ayer',
      in_days: 'en {n} días', in_day: 'en 1 día', days_ago: 'hace {n} días', day_ago: 'hace 1 día',
      days_late: '{n} días de retraso', day_late: '1 día de retraso',
      just_now: 'ahora', min_ago: 'hace {n} min', h_ago: 'hace {n} h', d_ago: 'hace {n} d',
      wd: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'],
      unassigned: 'Sin responsable', no_date: 'Sin fecha', none: '—',
      new_project: 'Nueva iniciativa', edit_project: 'Editar iniciativa', new_task: 'Nueva tarea',
      saved: 'Guardado', deleted: 'Eliminado', undo: 'Deshacer', cancel: 'Cancelar', del: 'Eliminar',
      del_task_q: '¿Eliminar esta tarea?', del_project_q: '¿Eliminar esta iniciativa?',
      del_project_txt: 'Sus tareas, hitos y comentarios se van con ella. No se puede deshacer.',
      del_task_txt: 'Sus subtareas y comentarios se van con ella.',
      ms_reached: 'Hito alcanzado: {m}', mark_done: 'Marcar hecha', reopen: 'Reabrir',
      no_comments: 'Aún no hay comentarios.', no_subtasks: 'Aún no hay subtareas.',
      none_status: 'Ninguna iniciativa con este estado', none_filter: 'Ninguna iniciativa con estos filtros', all_ms: 'Todos los hitos alcanzados', done_proj: 'Iniciativa concluida',
      next_ms: 'Próximo hito', no_ms: 'Aún no hay hitos', pin: 'Fijar en la barra lateral', pin_short: 'Fijar', pinned: 'Fijado',
      n_tasks: '{done}/{total} tareas', overdue: 'Atrasado', days_left: 'Días restantes', n_open: '{n} abiertas',
      ms_reached_n: '{n} de {total} alcanzados', ms_done: 'Hecho', complete: 'Completar', next: 'Próximo',
      open_done: '{open} abiertas · {done} hechas', no_tasks: 'Aún no hay tareas — agrega la primera.', hide: 'Ocultar', show: 'Mostrar',
      done: 'Hechas', total: 'Total', open_across: '{n} abiertas en {m} iniciativas', all_projects: 'Todas las iniciativas',
      any_priority: 'Cualquier prioridad', add_to: 'Agregar tarea en {col}', move_to: 'Mover a {col}', open_task: 'Abrir tarea',
      move_or_open: 'Mover o abrir “{task}”', n_on_board: '{n} en el tablero', up_target: 'Fecha objetivo', up_milestone: 'Hito', up_empty: 'Nada por delante.',
      lead: 'Líder',
      team_add: 'Agregar una persona al equipo…', team_all_in: 'Todos los elegibles ya están en el equipo', team_remove: 'Quitar del equipo',
      a_members_added: '{who} agregó a {names} al equipo',
      e_assignee_not_in_team: 'Agregue a esta persona al equipo de la iniciativa antes de darle una tarea.',
      e_too_many_members: 'Como máximo {max} personas en el equipo.',
      'cat_Process Review': 'Revisión de Proceso', 'cat_Tech Issue': 'Tech Issue', 'cat_Projects': 'Projects',
      'cat_B3 - Improvements': 'B3 - Improvements', 'cat_Stomp/Red': 'Stomp/Red',
      category: 'Categoría', all_categories: 'Todas las categorías', no_category: 'Sin categoría', choose_category: 'Elija…',
      a_created: '{who} creó la iniciativa', a_status: '{who} cambió el estado a {status}',
      a_edited: '{who} editó la iniciativa', a_task_added: '{who} agregó “{task}”',
      a_task_done: '{who} completó “{task}”', a_task_moved: '{who} movió “{task}” a {status}',
      a_task_deleted: '{who} eliminó “{task}”', a_commented: '{who} comentó en “{task}”',
      a_milestone_added: '{who} agregó el hito “{milestone}”',
      a_milestone_done: '{who} alcanzó “{milestone}”', a_milestone_reopened: '{who} reabrió “{milestone}”',
      e_name_required: 'Ponle un nombre a la iniciativa.', e_lead_required: 'Elige el líder.', e_category_required: 'Elige la categoría.',
      e_not_eligible: 'Esta persona no se puede elegir.', e_bad_choice: 'Valor inválido en {field}.', e_bad_number: 'Escriba un número.', e_out_of_range: 'Entre {min} y {max}.', e_bad_action: 'Acción desconocida.',
      e_bad_date: 'Fecha inválida.', e_due_before_start: 'La fecha objetivo es anterior al inicio.',
      e_title_required: 'Ponle un título.', e_bad_estimate: 'La estimación debe ser un número de horas.',
      e_comment_required: 'Escribe el comentario primero.', e_project_not_found: 'Iniciativa no encontrada.',
      e_task_not_found: 'Tarea no encontrada — puede haber sido eliminada.', e_milestone_not_found: 'Hito no encontrado.',
      e_subtask_not_found: 'Subtarea no encontrada.', e_not_allowed: 'No tienes permiso para hacer esto.',
      new_event: 'Nuevo evento', edit_event: 'Editar evento', del_event_q: '¿Eliminar este evento?',
      del_event_txt: 'Sale de la tarjeta Hitos, de Próximos y del Calendar.',
      ev_Milestone: 'Hito', ev_Meeting: 'Reunión', ev_Deadline: 'Plazo', ev_Review: 'Revisión', 'ev_Go-live': 'Go-live',
      all_day: 'Todo el día', len_min: '{n} min', len_h: '{h} h', len_hm: '{h} h {m}',
      e_bad_time: 'Hora inválida — usa hh:mm.',
      e_generic: 'No se pudo guardar. Inténtalo de nuevo.', e_title: 'No guardado'
    }
  };

  function t(key, params) {
    var d = _TRANS[LANG] || _TRANS.en;
    var s = d[key] !== undefined ? d[key] : _TRANS.en[key];
    if (s === undefined) return key;
    if (params && typeof s === 'string') {
      Object.keys(params).forEach(function (k) { s = s.split('{' + k + '}').join(params[k]); });
    }
    return s;
  }
  function tStatus(v) { return t('st_' + v); }
  function tTask(v) { return t('ts_' + v); }
  function tPrio(v) { return t('pr_' + v); }
  function tCat(v) { return v ? t('cat_' + v) : t('no_category'); }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  var COLORS = ['blue', 'purple', 'pink', 'orange', 'green', 'teal', 'indigo', 'yellow'];
  function colorVar(c) { return 'var(--otc-' + (COLORS.indexOf(c) !== -1 ? c : 'blue') + ')'; }
  var STATUS_HUE = { 'On going': 'var(--otc-green)', 'On hold': 'var(--otc-orange)', 'Concluded': 'var(--otc-teal)' };
  // A categoria da iniciativa (lista fechada do servidor, `domain.CATEGORIES`)
  var CATEGORIES = ['Process Review', 'Tech Issue', 'Projects', 'B3 - Improvements', 'Stomp/Red'];
  var CATEGORY_HUE = { 'Process Review': 'var(--otc-blue)', 'Tech Issue': 'var(--otc-orange)', 'Projects': 'var(--otc-purple)',
                       'B3 - Improvements': 'var(--otc-teal)', 'Stomp/Red': 'var(--otc-danger)' };
  var TASK_HUE = { 'To do': 'var(--otc-text-3)', 'In progress': 'var(--otc-blue)', 'In review': 'var(--otc-purple)', 'Done': 'var(--otc-green)' };

  function icons(root) {
    if (window.lucide && lucide.createIcons) { try { lucide.createIcons(root ? { root: root } : undefined); } catch (e) { try { lucide.createIcons(); } catch (e2) {} } }
  }

  // ── API ──────────────────────────────────────────────────────────────────
  // Erro sai como objeto {code, text, params}: a frase é a do `_TRANS`.
  function api(method, url, body) {
    var opt = { method: method, credentials: 'same-origin', headers: { 'Accept': 'application/json' } };
    if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
    return fetch(url, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) {
        if (!r.ok || d.success === false) {
          var err = new Error(d.text || d.error || ('HTTP ' + r.status));
          err.code = d.code || ''; err.params = d.params || {}; err.status = r.status;
          throw err;
        }
        return d;
      });
    });
  }
  function errText(e) {
    if (e && e.code && (_TRANS.en['e_' + e.code] !== undefined)) return t('e_' + e.code, e.params || {});
    return (e && e.message) || t('e_generic');
  }
  function fail(e) {
    if (window.Swal) Swal.fire({ icon: 'error', title: t('e_title'), text: errText(e) });
  }
  function toast(msg, undo) {
    if (!window.Swal) return;
    Swal.fire({
      toast: true, position: 'top-end', timer: undo ? 5000 : 2200, timerProgressBar: !!undo,
      showConfirmButton: !!undo, confirmButtonText: t('undo'), icon: undo ? undefined : 'success', title: msg
    }).then(function (r) { if (r.isConfirmed && undo) undo(); });
  }
  function confirmDelete(title, text) {
    if (!window.Swal) return Promise.resolve(window.confirm(title));
    return Swal.fire({
      icon: 'warning', title: title, text: text, showCancelButton: true,
      confirmButtonText: t('del'), cancelButtonText: t('cancel'),
      customClass: { confirmButton: 'swal2-deny' }
    }).then(function (r) { return !!r.isConfirmed; });
  }

  // ── Datas ───────────────────────────────────────────────────────────────
  // `today` é o do SERVIDOR (o mesmo dia que ele usa no burn-up e nos dias
  // restantes); o relógio da máquina só vale enquanto ele não chegou.
  var meta = { today: null, people: [], me: {} };
  function setMeta(d) {
    ['today', 'people', 'me', 'statuses', 'task_statuses', 'priorities', 'colors', 'icons', 'categories'].forEach(function (k) {
      if (d && d[k] !== undefined) meta[k] = d[k];
    });
    metaArrived();
  }
  // Os modais só abrem com as listas CARREGADAS: Lead, responsável e ícone
  // saem da mesma resposta da página, e no JP (o banco no share) ela leva
  // segundos — o "New initiative" clicado antes dela abria o Lead e o Icon sem
  // opção nenhuma, e o menu deles não abria. O clique fica guardado (um por
  // modal) e o cursor diz que está esperando; a página que não conseguiu
  // carregar chama `metaFailed` e o modal abre com o que houver.
  var metaReady = false, metaWaiting = {};
  function metaArrived() {
    metaReady = true;
    var fila = metaWaiting;
    metaWaiting = {};
    document.documentElement.style.removeProperty('cursor');
    Object.keys(fila).forEach(function (k) { fila[k](); });
  }
  function afterMeta(key, fn) {
    if (metaReady) return false;
    metaWaiting[key] = fn;
    document.documentElement.style.cursor = 'progress';
    return true;
  }
  function isoToday() {
    if (meta.today) return meta.today;
    var n = new Date();
    return n.getFullYear() + '-' + ('0' + (n.getMonth() + 1)).slice(-2) + '-' + ('0' + n.getDate()).slice(-2);
  }
  function parse(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
    return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
  }
  function diffDays(iso) {
    var d = parse(iso), h = parse(isoToday());
    return d && h ? Math.round((d - h) / 86400000) : null;
  }
  function fmtDate(iso) {
    var d = parse(iso);
    if (!d) return '';
    return ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2) + '/' + d.getFullYear();
  }
  function fmtShort(iso) {
    var d = parse(iso), h = parse(isoToday());
    if (!d) return '';
    var s = ('0' + d.getDate()).slice(-2) + '/' + ('0' + (d.getMonth() + 1)).slice(-2);
    return h && d.getFullYear() === h.getFullYear() ? s : s + '/' + d.getFullYear();
  }
  // Prazo de tarefa: Today / Tomorrow / dia da semana até 6 dias / dd/mm;
  // passado e em aberto vira "n days late" em vermelho.
  function due(iso, done) {
    var n = diffDays(iso);
    if (n === null) return null;
    if (n < 0 && !done) return { text: n === -1 ? t('day_late') : t('days_late', { n: -n }), cls: 'is-late', late: true };
    if (n === 0) return { text: t('today'), cls: done ? '' : 'is-soon' };
    if (n === 1) return { text: t('tomorrow'), cls: '' };
    if (n === -1) return { text: t('yesterday'), cls: '' };
    if (n > 1 && n < 7) return { text: t('wd')[parse(iso).getDay()], cls: '' };
    return { text: fmtShort(iso), cls: '' };
  }
  function inDays(iso) {
    var n = diffDays(iso);
    if (n === null) return '';
    if (n === 0) return t('today');
    if (n === 1) return t('in_day');
    if (n > 1) return t('in_days', { n: n });
    return n === -1 ? t('day_ago') : t('days_ago', { n: -n });
  }
  function ago(stamp) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(stamp || ''));
    if (!m) return '';
    var d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
    var s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return t('just_now');
    if (s < 3600) return t('min_ago', { n: Math.floor(s / 60) });
    if (s < 86400) return t('h_ago', { n: Math.floor(s / 3600) });
    if (s < 86400 * 30) return t('d_ago', { n: Math.floor(s / 86400) });
    return fmtDate(stamp);
  }

  // ── Pessoas ─────────────────────────────────────────────────────────────
  var AV_HUES = ['blue', 'purple', 'pink', 'orange', 'green', 'teal', 'indigo'];
  function initials(name) {
    var p = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!p.length) return '?';
    return ((p[0][0] || '') + (p.length > 1 ? p[p.length - 1][0] : '')).toUpperCase();
  }
  // `photo`: a URL da foto (`images/users/<sid>.jpg`, que o servidor só manda
  // quando o arquivo existe) — vai POR CIMA das iniciais, que ficam de reserva.
  // Sem ela, a foto sai da lista de pessoas (`meta.people[].photo`): é assim que
  // Lead, responsáveis, comentários e atividade ganham a foto sem cada tela
  // pedir. O plano B é o NOME exato: os participantes da reunião (User Home)
  // vêm do Outlook por nome, sem SID
  function photoOf(sid, name) {
    sid = String(sid || '').toUpperCase();
    var nm = String(name || '').trim().toLowerCase();
    var people = meta.people || [];
    var p = people.filter(function (x) { return x.sid === sid; })[0] ||
      (nm ? people.filter(function (x) { return String(x.name || '').trim().toLowerCase() === nm; })[0] : null);
    return (p && p.photo) || '';
  }
  function avatar(sid, name, size, photo) {
    if (photo === undefined) photo = photoOf(sid, name);
    var h = 0, k = String(sid || name || '');
    for (var i = 0; i < k.length; i++) h = (h * 31 + k.charCodeAt(i)) >>> 0;
    var c = AV_HUES[h % AV_HUES.length];
    return '<span class="pj-av' + (size ? ' pj-av--' + size : '') + '" style="--av:var(--otc-' + c + ')" title="' +
      esc(name || sid) + '">' + esc(initials(name || sid)) +
      (photo ? '<img class="pj-av__img" alt="" src="' + esc(photo) + '" onerror="this.remove()">' : '') + '</span>';
  }
  function avatars(list, max) {
    max = max || 4;
    var shown = (list || []).slice(0, max).map(function (p) { return avatar(p.sid, p.name, 'sm'); }).join('');
    var more = (list || []).length - max;
    return '<span class="pj-avs">' + shown + (more > 0 ? '<span class="pj-avs__more">+' + more + '</span>' : '') + '</span>';
  }
  function personName(sid) {
    sid = String(sid || '').toUpperCase();
    var p = (meta.people || []).filter(function (x) { return x.sid === sid; })[0];
    return p ? p.name : sid;
  }
  function prioBadge(p, all) {
    if (!p || (!all && p !== 'High' && p !== 'Urgent')) return '';
    return '<span class="pj-prio pj-prio--' + esc(String(p).toLowerCase()) + '">' +
      (p === 'Urgent' ? '<i data-lucide="flag"></i>' : '') + esc(tPrio(p)) + '</span>';
  }
  function chip(text, hue, extra) {
    return '<span class="otc-chip' + (extra ? ' ' + extra : '') + '" style="--chip:' + hue + '"><span>' + esc(text) + '</span></span>';
  }
  function categories() { return meta.categories || CATEGORIES; }
  function catChip(v) {
    if (!v) return '';
    return '<span class="otc-chip pj-cat" style="--chip:' + (CATEGORY_HUE[v] || 'var(--otc-text-3)') + '"><i data-lucide="tag"></i><span>' + esc(tCat(v)) + '</span></span>';
  }

  // ── Selects ─────────────────────────────────────────────────────────────
  function fillSelect(sel, items, value, opts) {
    if (!sel) return;
    opts = opts || {};
    var html = opts.blank !== undefined ? '<option value="">' + esc(opts.blank) + '</option>' : '';
    html += (items || []).map(function (it) {
      var v = typeof it === 'string' ? it : it.value;
      var l = typeof it === 'string' ? it : it.label;
      return '<option value="' + esc(v) + '">' + esc(l) + '</option>';
    }).join('');
    sel.innerHTML = html;
    sel.value = value == null ? '' : value;
    if (sel.value !== String(value == null ? '' : value) && opts.keep) {
      // valor gravado que saiu da lista (Lead que deixou o BO): continua visível
      var o = document.createElement('option'); o.value = value; o.textContent = opts.keep; sel.appendChild(o); sel.value = value;
    }
  }
  function peopleItems() { return (meta.people || []).map(function (p) { return { value: p.sid, label: p.name }; }); }
  // Quem pode RECEBER tarefa numa iniciativa (§639): os envolvidos nela — o
  // Lead, o time e quem já tem tarefa —, entre os elegíveis. A página que não
  // mandou a lista oferece todos os elegíveis; quem confere é o servidor.
  function involvedOf(project) {
    if (!project) return null;
    if (Array.isArray(project.involved)) return project.involved;
    if (Array.isArray(project.people)) return project.people.map(function (x) { return x.sid; });
    return null;
  }
  function assigneeItems(project) {
    var dentro = involvedOf(project), lista = peopleItems();
    return dentro ? lista.filter(function (it) { return dentro.indexOf(it.value) !== -1; }) : lista;
  }
  function dateField(el) {
    if (!el) return null;
    if (window.otcDateField) window.otcDateField(el);
    return el;
  }
  function setDate(el, iso) {
    if (!el) return;
    el.value = iso || '';
    if (el._flatpickr) el._flatpickr.setDate(iso || '', false);
  }
  function readDate(el) {
    if (!el) return '';
    var v = String(el.value || '').trim();
    var m = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(v);
    return m ? m[3] + '-' + m[2] + '-' + m[1] : v;
  }
  function modal(el) { return bootstrap.Modal.getOrCreateInstance(el); }

  // ── Modal do projeto (novo e edição) ────────────────────────────────────
  var Pm = { el: null, opts: null };
  function openProjectModal(opts) {
    if (afterMeta('project', function () { openProjectModal(opts); })) return;
    var el = Pm.el || (Pm.el = document.getElementById('pj-project-modal'));
    if (!el) return;
    // Editar sem a iniciativa CARREGADA abria o modal em branco (§648): quem
    // chama espera a carga; aqui só não abre.
    if (opts.mode === 'edit' && !(opts.project && opts.project.id)) return;
    Pm.opts = opts;
    var p = opts.project || {};
    var edit = opts.mode === 'edit';
    el.querySelector('#pjm-title').textContent = edit ? t('edit_project') : t('new_project');
    el.querySelector('#pjm-name').value = p.name || '';
    el.querySelector('#pjm-desc').value = p.description || '';
    fillSelect(el.querySelector('#pjm-lead'), peopleItems(), p.lead_sid || (meta.me && meta.me.sid) || '',
               { keep: p.lead_name });
    Pm.team = (p.members || []).map(function (m) { return { sid: m.sid, name: m.name }; });
    renderTeam();
    fillSelect(el.querySelector('#pjm-category'), categories().map(function (c) { return { value: c, label: tCat(c) }; }), p.category || '',
               { blank: t('choose_category') });
    fillSelect(el.querySelector('#pjm-status'), (meta.statuses || []).map(function (s) { return { value: s, label: tStatus(s) }; }), p.status || 'On going');
    fillSelect(el.querySelector('#pjm-color'), (meta.colors || COLORS).map(function (c) { return { value: c, label: t('co_' + c) }; }), p.color || 'blue');
    fillSelect(el.querySelector('#pjm-icon'), (meta.icons || []).map(function (c) { return { value: c, label: t('ic_' + c) }; }), p.icon || 'folder');
    dateField(el.querySelector('#pjm-start')); dateField(el.querySelector('#pjm-due'));
    setDate(el.querySelector('#pjm-start'), p.start_date || (edit ? '' : isoToday()));
    setDate(el.querySelector('#pjm-due'), p.due_date || '');
    el.querySelector('#pjm-status-wrap').classList.toggle('d-none', !edit);
    el.querySelector('#pjm-delete').classList.toggle('d-none', !(edit && opts.canDelete));
    if (!el._pjWired) {
      el._pjWired = 1;
      el.querySelector('#pjm-save').addEventListener('click', saveProjectModal);
      el.querySelector('#pjm-delete').addEventListener('click', deleteFromModal);
      el.querySelector('#pjm-name').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); saveProjectModal(); } });
      el.addEventListener('shown.bs.modal', function () { el.querySelector('#pjm-name').focus(); });
      // escolher no menu INCLUI no time; o × da ficha tira
      el.querySelector('#pjm-team-add').addEventListener('change', function () {
        var sid = this.value;
        var pes = (meta.people || []).filter(function (x) { return x.sid === sid; })[0];
        if (pes && !Pm.team.some(function (m) { return m.sid === sid; })) Pm.team.push({ sid: pes.sid, name: pes.name });
        renderTeam();
      });
      el.querySelector('#pjm-team').addEventListener('click', function (e) {
        var b = e.target.closest('[data-team-rm]');
        if (!b) return;
        var sid = b.getAttribute('data-team-rm');
        Pm.team = Pm.team.filter(function (m) { return m.sid !== sid; });
        renderTeam();
      });
      // o Lead não é do time: ele já está na iniciativa como Lead
      el.querySelector('#pjm-lead').addEventListener('change', function () {
        var lead = this.value;
        Pm.team = Pm.team.filter(function (m) { return m.sid !== lead; });
        renderTeam();
      });
    }
    modal(el).show();
  }
  function renderTeam() {
    var el = Pm.el, lead = el.querySelector('#pjm-lead').value;
    el.querySelector('#pjm-team').innerHTML = Pm.team.map(function (m) {
      return '<span class="pj-team__chip">' + avatar(m.sid, m.name, 'sm') + '<span>' + esc(m.name || m.sid) + '</span>' +
        '<button type="button" class="pj-team__rm" data-team-rm="' + esc(m.sid) + '" aria-label="' + esc(t('team_remove')) + '" title="' + esc(t('team_remove')) + '">' +
        '<i data-lucide="x"></i></button></span>';
    }).join('');
    var fora = peopleItems().filter(function (it) {
      return it.value !== lead && !Pm.team.some(function (m) { return m.sid === it.value; });
    });
    fillSelect(el.querySelector('#pjm-team-add'), fora, '', { blank: t(fora.length ? 'team_add' : 'team_all_in') });
    icons(el.querySelector('#pjm-team'));
  }
  function saveProjectModal() {
    var el = Pm.el, o = Pm.opts, edit = o.mode === 'edit';
    var body = {
      name: el.querySelector('#pjm-name').value, description: el.querySelector('#pjm-desc').value,
      category: el.querySelector('#pjm-category').value,
      lead_sid: el.querySelector('#pjm-lead').value, color: el.querySelector('#pjm-color').value,
      icon: el.querySelector('#pjm-icon').value, start_date: readDate(el.querySelector('#pjm-start')),
      due_date: readDate(el.querySelector('#pjm-due')),
      member_sids: Pm.team.map(function (m) { return m.sid; })
    };
    if (edit) body.status = el.querySelector('#pjm-status').value;
    var btn = el.querySelector('#pjm-save'); btn.disabled = true;
    (edit ? api('PATCH', '/api/projects/' + encodeURIComponent(o.project.id), body) : api('POST', '/api/projects', body))
      .then(function (d) { modal(el).hide(); if (o.onSaved) o.onSaved(d); })
      .catch(fail)
      .then(function () { btn.disabled = false; });
  }
  function deleteFromModal() {
    var o = Pm.opts;
    confirmDelete(t('del_project_q'), t('del_project_txt')).then(function (ok) {
      if (!ok) return;
      api('DELETE', '/api/projects/' + encodeURIComponent(o.project.id))
        .then(function () { modal(Pm.el).hide(); if (o.onDeleted) o.onDeleted(); })
        .catch(fail);
    });
  }

  // ── Modal "New task" ────────────────────────────────────────────────────
  var Tm = { el: null, opts: null };
  function openTaskModal(opts) {
    if (afterMeta('task', function () { openTaskModal(opts); })) return;
    var el = Tm.el || (Tm.el = document.getElementById('pj-task-modal'));
    if (!el) return;
    Tm.opts = opts;
    el.querySelector('#pjtm-title').value = '';
    var projs = (opts.projects || []).map(function (p) { return { value: p.id, label: p.name }; });
    fillSelect(el.querySelector('#pjtm-project'), projs, opts.projectId || (projs[0] && projs[0].value) || '');
    el.querySelector('#pjtm-project-wrap').classList.toggle('d-none', !!opts.fixedProject);
    taskAssignees(opts.assignee || (meta.me && meta.me.sid) || '');
    fillSelect(el.querySelector('#pjtm-priority'), (meta.priorities || []).map(function (p) { return { value: p, label: tPrio(p) }; }), 'Medium');
    fillSelect(el.querySelector('#pjtm-status'), (meta.task_statuses || []).map(function (s) { return { value: s, label: tTask(s) }; }), opts.status || 'To do');
    dateField(el.querySelector('#pjtm-due'));
    setDate(el.querySelector('#pjtm-due'), '');
    el.querySelector('#pjtm-estimate').value = '';
    if (!el._pjWired) {
      el._pjWired = 1;
      el.querySelector('#pjtm-save').addEventListener('click', saveTaskModal);
      // outra iniciativa, outros envolvidos
      el.querySelector('#pjtm-project').addEventListener('change', function () {
        taskAssignees(el.querySelector('#pjtm-assignee').value);
      });
      el.querySelector('#pjtm-title').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); saveTaskModal(); } });
      el.addEventListener('shown.bs.modal', function () { el.querySelector('#pjtm-title').focus(); });
    }
    modal(el).show();
  }
  // O responsável da tarefa nova sai dos ENVOLVIDOS na iniciativa escolhida.
  function taskAssignees(quero) {
    var el = Tm.el, pid = el.querySelector('#pjtm-project').value;
    var pr = (Tm.opts.projects || []).filter(function (x) { return x.id === pid; })[0];
    fillSelect(el.querySelector('#pjtm-assignee'), assigneeItems(pr), quero || '', { blank: t('unassigned') });
  }
  function saveTaskModal() {
    var el = Tm.el, o = Tm.opts;
    var pid = el.querySelector('#pjtm-project').value;
    var body = {
      title: el.querySelector('#pjtm-title').value, assignee_sid: el.querySelector('#pjtm-assignee').value,
      priority: el.querySelector('#pjtm-priority').value, status: el.querySelector('#pjtm-status').value,
      due: readDate(el.querySelector('#pjtm-due')), estimate: el.querySelector('#pjtm-estimate').value
    };
    var btn = el.querySelector('#pjtm-save'); btn.disabled = true;
    api('POST', '/api/projects/' + encodeURIComponent(pid) + '/tasks', body)
      .then(function (d) { modal(el).hide(); if (o.onSaved) o.onSaved(d.project); })
      .catch(fail)
      .then(function () { btn.disabled = false; });
  }

  // ── Modal do evento (o MARCO da iniciativa) ─────────────────────────────
  // Novo pelo "New event" da página; o clique num marco abre o mesmo modal
  // para editar, dar por atingido ou apagar (o card só mostra, §648). Sem
  // hora o evento é do dia inteiro: a duração se desliga, e o servidor a
  // ignora.
  var Em = { el: null, opts: null };
  var EVENT_TYPES = ['Milestone', 'Meeting', 'Deadline', 'Review', 'Go-live'];
  var EVENT_LENGTHS = [15, 30, 45, 60, 90, 120, 180, 240];
  function tEvent(v) { return t('ev_' + (v || 'Milestone')); }
  function lengthLabel(n) {
    n = +n;
    if (!n) return '';
    if (n < 60) return t('len_min', { n: n });
    var h = Math.floor(n / 60), m = n % 60;
    return m ? t('len_hm', { h: h, m: m }) : t('len_h', { h: h });
  }
  // hh:mm digitando só os números: os dois-pontos se escrevem sozinhos
  function timeMask(inp) {
    var d = String(inp.value || '').replace(/\D/g, '').slice(0, 4);
    inp.value = d.length > 2 ? d.slice(0, 2) + ':' + d.slice(2) : d;
  }
  function eventLengthState() {
    var el = Em.el;
    el.querySelector('#pjem-length').disabled = !String(el.querySelector('#pjem-time').value || '').trim();
  }
  function openEventModal(opts) {
    if (afterMeta('event', function () { openEventModal(opts); })) return;
    var el = Em.el || (Em.el = document.getElementById('pj-event-modal'));
    if (!el || !(opts.project && opts.project.id)) return;
    Em.opts = opts;
    var m = opts.milestone || {}, edit = !!m.id;
    el.querySelector('#pjem-heading').textContent = edit ? t('edit_event') : t('new_event');
    el.querySelector('#pjem-title').value = m.title || '';
    dateField(el.querySelector('#pjem-date'));
    setDate(el.querySelector('#pjem-date'), edit ? (m.date || '') : isoToday());
    el.querySelector('#pjem-time').value = m.time || '';
    fillSelect(el.querySelector('#pjem-length'), (meta.event_lengths || EVENT_LENGTHS).map(function (n) {
      return { value: String(n), label: lengthLabel(n) }; }), String(m.length || 30));
    fillSelect(el.querySelector('#pjem-type'), (meta.event_types || EVENT_TYPES).map(function (v) {
      return { value: v, label: tEvent(v) }; }), m.type || 'Milestone');
    el.querySelector('#pjem-project').value = opts.project.name || '';
    el.querySelector('#pjem-where').value = m.where || '';
    el.querySelector('#pjem-done').checked = !!m.done;
    el.querySelector('#pjem-done-wrap').classList.toggle('d-none', !edit);
    el.querySelector('#pjem-delete').classList.toggle('d-none', !edit);
    eventLengthState();
    if (!el._pjWired) {
      el._pjWired = 1;
      el.querySelector('#pjem-save').addEventListener('click', saveEventModal);
      el.querySelector('#pjem-delete').addEventListener('click', deleteEventFromModal);
      var hora = el.querySelector('#pjem-time');
      hora.addEventListener('input', function () { timeMask(hora); eventLengthState(); });
      el.querySelector('#pjem-title').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); saveEventModal(); } });
      el.addEventListener('shown.bs.modal', function () { el.querySelector('#pjem-title').focus(); });
    }
    modal(el).show();
  }
  function eventUrl(o, m) {
    return '/api/projects/' + encodeURIComponent(o.project.id) + '/milestones' + (m && m.id ? '/' + encodeURIComponent(m.id) : '');
  }
  function saveEventModal() {
    var el = Em.el, o = Em.opts, m = o.milestone || {};
    var body = {
      title: el.querySelector('#pjem-title').value, date: readDate(el.querySelector('#pjem-date')),
      time: el.querySelector('#pjem-time').value, length: el.querySelector('#pjem-length').value,
      type: el.querySelector('#pjem-type').value, where: el.querySelector('#pjem-where').value
    };
    if (m.id) body.done = el.querySelector('#pjem-done').checked;
    var btn = el.querySelector('#pjem-save'); btn.disabled = true;
    api(m.id ? 'PATCH' : 'POST', eventUrl(o, m), body)
      .then(function (d) { modal(el).hide(); if (o.onSaved) o.onSaved(d.project); })
      .catch(fail)
      .then(function () { btn.disabled = false; });
  }
  function deleteEventFromModal() {
    var o = Em.opts, m = o.milestone;
    confirmDelete(t('del_event_q'), t('del_event_txt')).then(function (ok) {
      if (!ok) return;
      api('DELETE', eventUrl(o, m))
        .then(function (d) { modal(Em.el).hide(); if (o.onSaved) o.onSaved(d.project); toast(t('deleted')); })
        .catch(fail);
    });
  }

  // ── Gaveta da tarefa ────────────────────────────────────────────────────
  // Cada mudança vai ao servidor na hora (troca de select, saída do campo,
  // Enter) e a gaveta se redesenha com a tarefa que VOLTOU gravada.
  var Dr = { el: null, oc: null, project: null, task: null, onChange: null };
  function drawerEl() { return Dr.el || (Dr.el = document.getElementById('pj-task-drawer')); }
  function taskUrl(extra) {
    return '/api/projects/' + encodeURIComponent(Dr.project.id) + '/tasks/' + encodeURIComponent(Dr.task.id) + (extra || '');
  }
  function drawerApply(project) {
    var t2 = (project.tasks || []).filter(function (x) { return x.id === Dr.task.id; })[0];
    Dr.project = { id: project.id, name: project.name, color: project.color,
                   involved: involvedOf(project) || involvedOf(Dr.project) };
    if (Dr.onChange) Dr.onChange(project);
    if (!t2) { Dr.oc.hide(); return; }
    Dr.task = t2;
    renderDrawer();
  }
  function drawerSend(method, url, body) {
    return api(method, url, body).then(function (d) { drawerApply(d.project); return d; }).catch(function (e) { fail(e); renderDrawer(); });
  }
  function openTaskDrawer(opts) {
    if (afterMeta('drawer', function () { openTaskDrawer(opts); })) return;
    var el = drawerEl();
    if (!el) return;
    Dr.project = opts.project; Dr.task = opts.task; Dr.onChange = opts.onChange;
    Dr.oc = bootstrap.Offcanvas.getOrCreateInstance(el);
    if (!el._pjWired) { el._pjWired = 1; wireDrawer(el); }
    renderDrawer();
    Dr.oc.show();
  }
  function renderDrawer() {
    var el = drawerEl(), tk = Dr.task, pr = Dr.project;
    var chipEl = el.querySelector('#pjt-project');
    chipEl.style.setProperty('--chip', colorVar(pr.color));
    chipEl.href = '/initiatives/' + encodeURIComponent(pr.id);
    chipEl.innerHTML = '<span>' + esc(pr.name) + '</span>';
    el.querySelector('#pjt-prio-badge').innerHTML = prioBadge(tk.priority);
    var title = el.querySelector('#pjt-title');
    if (document.activeElement !== title) title.value = tk.title || '';
    $$('#pjt-status .nav-link', el).forEach(function (a) { a.classList.toggle('active', a.getAttribute('data-status') === tk.status); });
    $$('#pjt-status .nav-link', el).forEach(function (a) { a.textContent = tTask(a.getAttribute('data-status')); });
    fillSelect(el.querySelector('#pjt-assignee'), assigneeItems(pr), tk.assignee_sid || '', { blank: t('unassigned'), keep: tk.assignee_name });
    fillSelect(el.querySelector('#pjt-priority'), (meta.priorities || []).map(function (p) { return { value: p, label: tPrio(p) }; }), tk.priority);
    setDate(el.querySelector('#pjt-due'), tk.due || '');
    // o valor desenhado nas caixas (o Pane): avatar e nome, prazo relativo, prioridade
    el.querySelector('#pjt-assignee-view').innerHTML = tk.assignee_sid
      ? avatar(tk.assignee_sid, tk.assignee_name, 'sm') + '<span>' + esc(tk.assignee_name || personName(tk.assignee_sid)) + '</span>'
      : '<span class="is-muted">' + esc(t('unassigned')) + '</span>';
    var dd = due(tk.due, tk.status === 'Done');
    el.querySelector('#pjt-due-view').innerHTML = '<i data-lucide="calendar"></i>' + (tk.due
      ? '<span class="' + (dd && dd.late ? 'is-late' : '') + '">' + esc(dd ? dd.text : '') + ' · ' + esc(fmtShort(tk.due)) + '</span>'
      : '<span class="is-muted">' + esc(t('no_date')) + '</span>');
    el.querySelector('#pjt-priority-view').innerHTML = '<i data-lucide="flag"></i><span>' + esc(tPrio(tk.priority || 'Medium')) + '</span>';
    var est = el.querySelector('#pjt-estimate');
    if (document.activeElement !== est) est.value = tk.estimate == null ? '' : tk.estimate;
    var subs = tk.subtasks || [];
    el.querySelector('#pjt-sub-count').textContent = subs.filter(function (s) { return s.done; }).length + '/' + subs.length;
    el.querySelector('#pjt-subs').innerHTML = subs.length ? subs.map(function (s) {
      return '<li class="' + (s.done ? 'is-done' : '') + '" data-sub="' + esc(s.id) + '">' +
        '<button type="button" class="tk-circle' + (s.done ? ' is-on' : '') + '" data-sub-toggle aria-pressed="' + (s.done ? 'true' : 'false') + '"><i data-lucide="check"></i></button>' +
        '<span>' + esc(s.title) + '</span>' +
        '<button type="button" class="pjd-ms__del" data-sub-del aria-label="' + esc(t('del')) + '"><i data-lucide="x"></i></button></li>';
    }).join('') : '<li class="text-muted border-0">' + esc(t('no_subtasks')) + '</li>';
    var com = tk.comments || [];
    el.querySelector('#pjt-comments').innerHTML = com.length ? com.map(function (c) {
      return '<li>' + avatar(c.sid, c.name, 'sm') + '<div><b>' + esc(c.name || c.sid) + '</b> <small>' + esc(ago(c.at)) + '</small><p>' + esc(c.text) + '</p></div></li>';
    }).join('') : '<li class="text-muted">' + esc(t('no_comments')) + '</li>';
    var done = tk.status === 'Done';
    var bd = el.querySelector('#pjt-done');
    bd.innerHTML = '<i data-lucide="' + (done ? 'rotate-ccw' : 'check') + '"></i><span>' + esc(done ? t('reopen') : t('mark_done')) + '</span>';
    bd.classList.toggle('btn-primary', !done); bd.classList.toggle('btn-secondary', done);
    icons(el);
  }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function wireDrawer(el) {
    dateField(el.querySelector('#pjt-due'));
    el.querySelector('#pjt-status').addEventListener('click', function (e) {
      var a = e.target.closest('[data-status]');
      if (!a) return;
      e.preventDefault();
      if (a.getAttribute('data-status') !== Dr.task.status) drawerSend('PATCH', taskUrl(), { status: a.getAttribute('data-status') });
    });
    var title = el.querySelector('#pjt-title');
    title.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); title.blur(); } });
    title.addEventListener('blur', function () {
      if (title.value.trim() && title.value.trim() !== Dr.task.title) drawerSend('PATCH', taskUrl(), { title: title.value });
      else title.value = Dr.task.title;
    });
    el.querySelector('#pjt-assignee').addEventListener('change', function () { drawerSend('PATCH', taskUrl(), { assignee_sid: this.value }); });
    el.querySelector('#pjt-priority').addEventListener('change', function () { drawerSend('PATCH', taskUrl(), { priority: this.value }); });
    el.querySelector('#pjt-due').addEventListener('change', function () {
      var v = readDate(this);
      if (v !== (Dr.task.due || '')) drawerSend('PATCH', taskUrl(), { due: v });
    });
    var est = el.querySelector('#pjt-estimate');
    est.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); est.blur(); } });
    est.addEventListener('blur', function () {
      var cur = Dr.task.estimate == null ? '' : String(Dr.task.estimate);
      if (est.value.trim() !== cur) drawerSend('PATCH', taskUrl(), { estimate: est.value });
    });
    el.querySelector('#pjt-subs').addEventListener('click', function (e) {
      var li = e.target.closest('[data-sub]');
      if (!li) return;
      var sid = li.getAttribute('data-sub');
      if (e.target.closest('[data-sub-toggle]')) {
        var s = (Dr.task.subtasks || []).filter(function (x) { return x.id === sid; })[0];
        drawerSend('PATCH', taskUrl('/subtasks/' + encodeURIComponent(sid)), { done: !(s && s.done) });
      } else if (e.target.closest('[data-sub-del]')) {
        drawerSend('DELETE', taskUrl('/subtasks/' + encodeURIComponent(sid)));
      }
    });
    var subIn = el.querySelector('#pjt-sub-input');
    var addSub = function () {
      if (!subIn.value.trim()) return;
      var v = subIn.value; subIn.value = '';
      drawerSend('POST', taskUrl('/subtasks'), { title: v });
    };
    el.querySelector('#pjt-sub-add').addEventListener('click', addSub);
    subIn.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addSub(); } });
    var cIn = el.querySelector('#pjt-comment-input');
    var post = function () {
      if (!cIn.value.trim()) return;
      var v = cIn.value; cIn.value = '';
      drawerSend('POST', taskUrl('/comments'), { text: v });
    };
    el.querySelector('#pjt-comment-post').addEventListener('click', post);
    cIn.addEventListener('keydown', function (e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); post(); } });
    el.querySelector('#pjt-done').addEventListener('click', function () {
      var done = Dr.task.status === 'Done';
      drawerSend('PATCH', taskUrl(), { status: done ? 'To do' : 'Done' });
    });
    el.querySelector('#pjt-delete').addEventListener('click', function () {
      confirmDelete(t('del_task_q'), t('del_task_txt')).then(function (ok) {
        if (!ok) return;
        api('DELETE', taskUrl()).then(function (d) {
          Dr.oc.hide();
          if (Dr.onChange) Dr.onChange(d.project);
          toast(t('deleted'));
        }).catch(fail);
      });
    });
  }

  // ── Atividade ───────────────────────────────────────────────────────────
  function activityText(ev) {
    var p = ev.params || {};
    var params = { who: '<b>' + esc(ev.name || ev.sid) + '</b>', task: esc(p.task || ''), milestone: esc(p.milestone || ''),
                   names: '<b>' + esc(p.names || '') + '</b>',
                   status: esc(p.status ? (_TRANS.en['st_' + p.status] !== undefined ? tStatus(p.status) : tTask(p.status)) : '') };
    var key = 'a_' + ev.kind;
    return _TRANS.en[key] !== undefined ? t(key, params) : esc(ev.kind);
  }

  window.OtcPj = {
    t: t, tStatus: tStatus, tTask: tTask, tPrio: tPrio, tCat: tCat, categories: categories, catChip: catChip,
    CATEGORY_HUE: CATEGORY_HUE, esc: esc, colorVar: colorVar,
    STATUS_HUE: STATUS_HUE, TASK_HUE: TASK_HUE, icons: icons, api: api, fail: fail, toast: toast,
    errText: errText, confirmDelete: confirmDelete, meta: meta, setMeta: setMeta, metaFailed: metaArrived, isoToday: isoToday,
    parse: parse, diffDays: diffDays, fmtDate: fmtDate, fmtShort: fmtShort, due: due, inDays: inDays, ago: ago,
    avatar: avatar, avatars: avatars, personName: personName, prioBadge: prioBadge, chip: chip,
    openProjectModal: openProjectModal, openTaskModal: openTaskModal, openTaskDrawer: openTaskDrawer,
    openEventModal: openEventModal, tEvent: tEvent, lengthLabel: lengthLabel,
    activityText: activityText
  };
})();

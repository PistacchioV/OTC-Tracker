# -*- coding: utf-8 -*-
"""As rotas do Projects. Camada FINA: lê a sessão, confere o acesso à página,
chama a consulta ou o comando e devolve JSON (ou a página).

Toda API exige a página `/initiatives` liberada para a sessão (o
`enforce_page_access` não olha `/api/*`, CLAUDE.md §5). Erro de validação sai
ESTRUTURADO: `{code, params, text}` — a tela traduz pelo código.
"""
from datetime import date

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.projects import commands, domain, queries

# A página é `/initiatives` (mesa, 20/10/2026): a tela já se chamava assim e o
# navegador mostrava `/projects`. O `Page_Access` gravado com `/projects` vale
# para ela (`authz._renomeadas`), e o endereço antigo redireciona. A API segue
# `/api/projects` — não aparece no navegador.
PAGE_URL = '/initiatives'
TASKS_URL = '/tasks'


def _routes():
    from apps.pages import routes
    return routes


def _actor():
    return {'sid': (session.get('user_sid') or '').strip().upper(),
            'name': (session.get('user_name') or '').strip(),
            'role': str(session.get('user_role') or '').strip().upper()}


def _today():
    try:
        return _routes()._br_now().date()
    except Exception:                                    # noqa: BLE001
        return date.today()


def _is_admin():
    return bool(_routes()._session_is_admin())


def _err(code, text, status, **params):
    return jsonify({'success': False, 'code': code, 'params': params, 'text': text,
                    'error': text}), status


def _guard():
    """None quando pode seguir; senão a resposta de erro pronta."""
    if not session.get('authenticated'):
        return _err('not_authenticated', 'Not authenticated', 401)
    if not _can_see():
        return _err('not_allowed', 'You do not have access to Projects.', 403)
    return None


def _can_see():
    """Projects e Tasks mostram o MESMO trabalho (a Tasks move e edita as
    tarefas dos projetos): ter qualquer uma das duas páginas libera a API."""
    R = _routes()
    return bool(R._user_can_access_page(PAGE_URL) or R._user_can_access_page(TASKS_URL))


def _run(fn):
    """Executa o comando e traduz as exceções do domínio em status HTTP."""
    try:
        return fn()
    except domain.NotFound as e:
        return _err(e.code, e.text, 404, **e.params)
    except domain.ProjectError as e:
        return _err(e.code, e.text, 400, **e.params)
    except PermissionError:
        return _err('not_allowed', 'Only the lead, the creator or an admin can do this.', 403)


def _detail_json(project):
    return jsonify({'success': True, 'project': queries.detail(project, _today())})


def _body():
    return request.get_json(silent=True) or {}


def _meta(me, people):
    return {'statuses': domain.STATUSES, 'task_statuses': domain.TASK_STATUSES,
            'priorities': domain.PRIORITIES, 'colors': domain.COLORS, 'icons': domain.ICONS,
            'categories': domain.CATEGORIES,
            'event_types': domain.EVENT_TYPES, 'event_lengths': domain.EVENT_LENGTHS,
            'people': people, 'me': {'sid': me['sid'], 'name': me['name']},
            'today': _today().isoformat()}


# ── Páginas ───────────────────────────────────────────────────────────────────

@blueprint.route('/initiatives')
def projects_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/projects.html', segment='projects')


@blueprint.route('/projects')
@blueprint.route('/projects/<project_id>')
def projects_old_url(project_id=None):
    """O endereço antigo: favoritos, links de e-mail e avisos já enviados
    continuam chegando — à mesma iniciativa, com o `?task=` junto."""
    alvo = PAGE_URL + ('/' + project_id if project_id else '')
    qs = request.query_string.decode('utf-8', 'ignore')
    return redirect(alvo + ('?' + qs if qs else ''))


@blueprint.route('/initiatives/<project_id>')
def project_page(project_id):
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    # A página do projeto não está no menu, e o `enforce_page_access` só olha
    # quem está: quem não tem o Projects volta para ele (e de lá para a sua
    # página de entrada).
    if not _can_see():
        return redirect(PAGE_URL)
    p = queries.get(project_id)
    if p is None:
        return redirect(PAGE_URL)
    return render_template('pages/projects-detail.html', segment='projects', project_id=p['id'],
                           project_name=p.get('name', ''), project_color=p.get('color', 'blue'),
                           project_icon=p.get('icon', 'folder'))


@blueprint.route('/tasks')
def tasks_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/tasks.html', segment='tasks')


# ── API: projetos ─────────────────────────────────────────────────────────────

@blueprint.route('/api/projects', methods=['GET'])
def api_projects_list():
    g = _guard()
    if g:
        return g
    me = _actor()
    out = {'success': True, 'projects': queries.list_projects()}
    out.update(_meta(me, queries.eligible(me)))
    return jsonify(out)


@blueprint.route('/api/projects', methods=['POST'])
def api_projects_create():
    g = _guard()
    if g:
        return g
    me = _actor()

    def go():
        p = commands.create_project(me, _body(), queries.eligible(me))
        return jsonify({'success': True, 'project': domain.summary(p)})
    return _run(go)


@blueprint.route('/api/projects/<project_id>', methods=['GET'])
def api_project_get(project_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    p = queries.get(project_id)
    if p is None:
        return _err('project_not_found', 'Initiative not found.', 404)
    people = queries.eligible(me)
    out = {'success': True, 'project': queries.detail(p, _today()),
           'can_delete': domain.can_delete(p, me['sid'], _is_admin())}
    out.update(_meta(me, people))
    return jsonify(out)


@blueprint.route('/api/projects/<project_id>', methods=['PATCH'])
def api_project_update(project_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.update_project(me, project_id, _body(),
                                                             queries.eligible(me))))


@blueprint.route('/api/projects/<project_id>', methods=['DELETE'])
def api_project_delete(project_id):
    g = _guard()
    if g:
        return g
    me = _actor()

    def go():
        p = commands.delete_project(me, project_id, _is_admin())
        return jsonify({'success': True, 'id': p['id']})
    return _run(go)


# ── API: tarefas ─────────────────────────────────────────────────────────────

@blueprint.route('/api/tasks', methods=['GET'])
def api_tasks_list():
    """A Tasks reúne as tarefas de todos os projetos. A página `/tasks` tem
    entrada própria no menu (e no `Page_Access`); quem tem o Projects ou a Tasks
    lê — as duas mostram o mesmo trabalho."""
    if not session.get('authenticated'):
        return _err('not_authenticated', 'Not authenticated', 401)
    if not _can_see():
        return _err('not_allowed', 'You do not have access to Tasks.', 403)
    me = _actor()
    tarefas, projetos = queries.all_tasks()
    out = {'success': True, 'tasks': tarefas, 'projects': projetos}
    out.update(_meta(me, queries.eligible(me)))
    return jsonify(out)


@blueprint.route('/api/projects/calendar', methods=['GET'])
def api_projects_calendar():
    """As datas dos projetos, marcos e tarefas em aberto para o Calendar. Quem
    não tem Projects nem Tasks recebe a lista VAZIA (e não 403): o Calendar é
    dos feriados e abre do mesmo jeito para quem não vê projeto nenhum."""
    if not session.get('authenticated'):
        return _err('not_authenticated', 'Not authenticated', 401)
    if not _can_see():
        return jsonify({'success': True, 'events': []})
    return jsonify({'success': True, 'events': queries.calendar_events()})


# ── API: tarefas de um projeto ─────────────────────────────────────────────────────────────

@blueprint.route('/api/projects/<project_id>/tasks', methods=['POST'])
def api_project_task_add(project_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.add_task(me, project_id, _body(),
                                                       queries.eligible(me))))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>', methods=['PATCH'])
def api_project_task_update(project_id, task_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.update_task(me, project_id, task_id, _body(),
                                                          queries.eligible(me))))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>', methods=['DELETE'])
def api_project_task_delete(project_id, task_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.delete_task(me, project_id, task_id)))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>/subtasks', methods=['POST'])
def api_project_subtask_add(project_id, task_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.add_subtask(me, project_id, task_id, _body())))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>/subtasks/<sub_id>',
                 methods=['PATCH'])
def api_project_subtask_update(project_id, task_id, sub_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.update_subtask(me, project_id, task_id, sub_id,
                                                             _body())))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>/subtasks/<sub_id>',
                 methods=['DELETE'])
def api_project_subtask_delete(project_id, task_id, sub_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.delete_subtask(me, project_id, task_id, sub_id)))


@blueprint.route('/api/projects/<project_id>/tasks/<task_id>/comments', methods=['POST'])
def api_project_comment_add(project_id, task_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.add_comment(me, project_id, task_id, _body())))


# ── API: marcos ───────────────────────────────────────────────────────────────

@blueprint.route('/api/projects/<project_id>/milestones', methods=['POST'])
def api_project_milestone_add(project_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.add_milestone(me, project_id, _body())))


@blueprint.route('/api/projects/<project_id>/milestones/<ms_id>', methods=['PATCH'])
def api_project_milestone_update(project_id, ms_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.update_milestone(me, project_id, ms_id, _body())))


@blueprint.route('/api/projects/<project_id>/milestones/<ms_id>', methods=['DELETE'])
def api_project_milestone_delete(project_id, ms_id):
    g = _guard()
    if g:
        return g
    me = _actor()
    return _run(lambda: _detail_json(commands.delete_milestone(me, project_id, ms_id)))


# ── Os alertas das iniciativas no Control Panel (card `initiativealerts`, §701)
# O card guarda o TO (o box) e o CC; quem está na iniciativa entra sozinho no
# TO de cada e-mail. O acesso é o do card (`_CP_ENDPOINT_CARD`).
start_alerts_scheduler = commands.start_alerts_scheduler


@blueprint.route('/api/control-panel/initiative-alerts/recipients', methods=['GET', 'POST'])
def api_cp_initiative_alerts_recipients():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    from apps.pages.features.projects.infra import alerts as A
    if request.method == 'POST':
        body = request.get_json(silent=True) or {}
        A.save_recipients(body.get('to'), body.get('cc'))
    rec = A.load_recipients()
    return jsonify({'success': True, 'to': rec['to'], 'cc': rec['cc'], 'last': A.load_status(),
                    'hour': '%02d:00' % commands.ALERT_HOUR})


@blueprint.route('/api/control-panel/initiative-alerts/run', methods=['POST'])
def api_cp_initiative_alerts_run():
    """O Run do card: dispara AGORA o que é devido hoje e ainda não saiu (a
    mesma regra do automático — o que já saiu não sai de novo)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    body = request.get_json(silent=True) or {}
    hoje = _routes()._br_now().date().isoformat()
    res = commands.run_alerts(hoje, to_override=body.get('to'), cc_override=body.get('cc'))
    if res['failed'] and not res['initiatives']:
        return jsonify({'success': False, 'code': 'initiative_alerts_failed', 'failed': res['failed'],
                        'error': '; '.join('%s: %s' % f for f in res['failed'])}), 502
    return jsonify({'success': True, 'sent': res['initiatives'], 'alerts': res['alerts'],
                    'failed': res['failed']})

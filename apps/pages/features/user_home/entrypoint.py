# -*- coding: utf-8 -*-
"""As rotas da User Home (Intraday › User Home) e da Settings. Camada FINA.

As duas páginas são de TODO usuário logado (`_ALWAYS_ALLOWED_PATHS`): cada um
vê o próprio documento. As partes de tarefa e projeto só aparecem para quem
tem o Projects ou o Tasks.
"""
from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.platform import user_photos
from apps.pages.features.user_home import commands, domain, queries
from apps.pages.features.user_home.infra import outlook


def _routes():
    from apps.pages import routes
    return routes


def _me():
    return {'sid': (session.get('user_sid') or '').strip().upper(),
            'name': (session.get('user_name') or '').strip(),
            'email': (session.get('user_email') or '').strip(),
            'role': str(session.get('user_role') or '').strip().upper()}


def _now():
    try:
        n = _routes()._br_now()
    except Exception:                                    # noqa: BLE001
        from datetime import datetime
        n = datetime.now()
    return n.replace(microsecond=0, tzinfo=None).isoformat()


def _err(code, text, status, **params):
    return jsonify({'success': False, 'code': code, 'params': params, 'text': text, 'error': text}), status


def _can_projects():
    R = _routes()
    return bool(R._user_can_access_page('/initiatives') or R._user_can_access_page('/tasks'))


def _guard():
    if not session.get('authenticated'):
        return _err('not_authenticated', 'Not authenticated', 401)
    if not _me()['sid']:
        return _err('not_authenticated', 'Not authenticated', 401)
    return None


# ── Páginas ───────────────────────────────────────────────────────────────────

@blueprint.route('/user-home')
def user_home_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/user-home.html', segment='user-home')


@blueprint.route('/settings')
def settings_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/settings.html', segment='settings')


# ── API ───────────────────────────────────────────────────────────────────────

@blueprint.route('/api/user-home', methods=['GET'])
def api_user_home():
    g = _guard()
    if g:
        return g
    me = _me()
    can = _can_projects()
    out = {'success': True}
    out.update(queries.home(me, _now(), can))
    if can:
        R = _routes()
        out['meta'] = R._projects_meta(me)
    return jsonify(out)


@blueprint.route('/api/user-home/sync', methods=['POST'])
def api_user_home_sync():
    g = _guard()
    if g:
        return g
    try:
        n = commands.sync(_me(), _now())
    except outlook.OutlookUnavailable as e:
        return _err('outlook_unavailable', 'The Sync needs Outlook on this machine: %s' % e, 503)
    except outlook.CalendarNotAccessible:
        return _err('calendar_not_accessible',
                    "The Outlook on this machine belongs to someone else and your calendar did not open through it.", 409)
    return jsonify({'success': True, 'events': n})


@blueprint.route('/api/user-home/focus', methods=['POST'])
def api_user_home_focus():
    g = _guard()
    if g:
        return g
    body = request.get_json(silent=True) or {}
    now = _now()
    try:
        doc, sessao = commands.focus(_me(), str(body.get('action') or ''), body, now)
    except domain.HomeError as e:
        return _err(e.code, e.text, 400, **e.params)
    return jsonify({'success': True, 'focus': queries.focus_state(doc, now), 'session': sessao,
                    'today': domain.focus_today(doc.get('focus'), now[:10], now)})


@blueprint.route('/api/settings', methods=['GET'])
def api_settings_get():
    g = _guard()
    if g:
        return g
    me = _me()
    out = {'success': True, 'settings': queries.settings(me['sid']),
           'me': {'sid': me['sid'], 'name': me['name'], 'email': me['email'], 'role': me['role'],
                  'photo': user_photos.url(me['sid'])},
           'can_projects': _can_projects()}
    try:
        R = _routes()
        info = R._projects_directory().get(me['sid']) or {}
        out['me']['position'] = info.get('position', '')
    except Exception:                                    # noqa: BLE001
        out['me']['position'] = ''
    return jsonify(out)


@blueprint.route('/api/settings', methods=['POST'])
def api_settings_save():
    g = _guard()
    if g:
        return g
    body = request.get_json(silent=True) or {}
    try:
        if body.get('reset'):
            st = commands.reset_settings(_me())
        else:
            st = commands.save_settings(_me(), body)
    except domain.HomeError as e:
        return _err(e.code, e.text, 400, **e.params)
    return jsonify({'success': True, 'settings': st})


@blueprint.route('/api/settings/export-tasks', methods=['GET'])
def api_settings_export_tasks():
    """As MINHAS tarefas (responsável = eu) num CSV da casa: `;` e BOM, uma
    linha por tarefa."""
    g = _guard()
    if g:
        return g
    if not _can_projects():
        return _err('not_allowed', 'You do not have access to Projects.', 403)
    import csv
    import io
    from urllib.parse import quote
    from flask import Response
    me = _me()
    linhas = []
    for p in _routes()._projects_doc().get('projects') or []:
        for t in p.get('tasks') or []:
            if str(t.get('assignee_sid') or '').upper() == me['sid']:
                linhas.append((p, t))
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=';', lineterminator='\r\n')
    w.writerow(['Initiative', 'Task', 'Status', 'Priority', 'Due', 'Estimate (h)', 'Subtasks done',
                'Created', 'Done at'])

    def dmy(iso):
        iso = str(iso or '')[:10]
        return '%s/%s/%s' % (iso[8:10], iso[5:7], iso[:4]) if len(iso) == 10 else ''

    def texto(v):
        # Título e nome são digitados por QUALQUER um que cria a tarefa para
        # mim: começando por = + - @ o Excel os abre como FÓRMULA
        # (`=HYPERLINK(...)`). O apóstrofo os mantém texto (OWASP, CSV
        # injection).
        v = str(v or '')
        return "'" + v if v[:1] in ('=', '+', '-', '@', '\t', '\r') else v
    for p, t in linhas:
        subs = t.get('subtasks') or []
        # "1 of 3", não "1/3": o Excel lê `1/3` como DATA (3 de janeiro)
        w.writerow([texto(p.get('name', '')), texto(t.get('title', '')), t.get('status', ''), t.get('priority', ''),
                    dmy(t.get('due')), t.get('estimate') if t.get('estimate') is not None else '',
                    '%d of %d' % (sum(1 for s in subs if s.get('done')), len(subs)) if subs else '',
                    dmy(t.get('created_at')), dmy(t.get('done_at'))])
    nome = 'My Tasks - %s - %s.csv' % (me['name'] or me['sid'], _now()[:10].replace('-', ''))
    return Response('\ufeff' + buf.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': "attachment; filename*=UTF-8''" + quote(nome)})

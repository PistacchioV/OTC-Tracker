# -*- coding: utf-8 -*-
"""As rotas do Intraday Monitor (ex-New Deals Monitor): a página, o snapshot,
o card de pendências e o card da agenda das tarefas (§567)."""
import traceback
from datetime import datetime

from flask import jsonify, redirect, render_template, request, session, url_for

from apps.pages import blueprint
from apps.pages.features.deals_monitor import commands, domain, queries
from apps.pages.features.deals_monitor.infra import persistence

# O wiring do routes registra o scheduler com este nome.
start_scheduler = commands._ndm_pending_start_scheduler


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/api/new-deals/monitor')
def api_new_deals_monitor():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    cards, conf_cards = queries._ndm_monitor_snapshot(ref)
    return jsonify({'success': True, 'date': ref.strftime('%Y-%m-%d'),
                    'cards': cards, 'conf_cards': conf_cards})

@blueprint.route('/api/control-panel/deals-monitor/recipients', methods=['GET', 'POST'])
def api_cp_deals_monitor_recipients():
    """TO/CC do aviso diário, do card Deals Monitor. Salvar vazio nos dois
    campos volta ao default da mesa em vez de desligar a rotina em silêncio."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        return jsonify({'success': True, **persistence._load_ndm_pending_recipients(),
                        **queries._ndm_pending_status()})
    payload = request.get_json(silent=True) or {}
    try:
        persistence._save_ndm_pending_recipients((payload.get('to') or '').strip(),
                                     (payload.get('cc') or '').strip())
    except Exception as e:                                  # noqa: BLE001
        _R().log.error('[deals-monitor] save recipients failed:\n%s', traceback.format_exc())
        return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    return jsonify({'success': True})

@blueprint.route('/api/control-panel/deals-monitor/run', methods=['POST'])
def api_cp_deals_monitor_run():
    """Dispara o aviso na hora, sem esperar os horários agendados."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    payload = request.get_json(silent=True) or {}
    ds = (payload.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else datetime.now()
    except ValueError:
        ref = datetime.now()
    rec = persistence._load_ndm_pending_recipients()
    to_list, cc_list = _R()._parse_emails(rec['to']), _R()._parse_emails(rec['cc'])
    if not (to_list or cc_list):
        return jsonify({'success': False,
                        'error': 'Nenhum destinatário salvo. Preencha o TO antes de rodar.'}), 400
    result = commands._send_ndm_pending_email(ref, to_list, cc_list)
    if result == 'empty':
        return jsonify({'success': True,
                        'message': 'Nothing pending on the Intraday Monitor — no e-mail sent.'})
    if result is not True:
        return jsonify({'success': False, 'error': 'E-mail failed: {}'.format(result)}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Intraday Monitor Sent', 'Control Panel',
                         'Pending Action e-mailed ({})'.format(ref.strftime('%Y-%m-%d')))
    return jsonify({'success': True,
                    'message': 'Pending Action enviado para {} destinatário(s).'.format(
                        len(to_list) + len(cc_list))})


@blueprint.route('/intraday-monitor')
def intraday_monitor():
    """O Intraday Monitor — o New Deals Monitor repaginado como o painel das
    tarefas do dia (§567). A contagem por produto continua na página, como o
    DETALHE das tarefas de registro, confirmação e Intrag."""
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/intraday-monitor.html', segment='intraday-monitor',
                           today=_R()._br_now().strftime('%Y-%m-%d'))


@blueprint.route('/new-deals-monitor')
def new_deals_monitor():
    """O endereço antigo: favoritos, SOP e o link do e-mail continuam
    chegando. Quem tinha `/new-deals-monitor` na allowlist continua entrando
    (`authz._PAGE_ALIASES`)."""
    return redirect(url_for('pages_blueprint.intraday_monitor'))


def _ref_da(ds):
    try:
        return datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R()._br_now()
    except ValueError:
        return _R()._br_now()


@blueprint.route('/api/intraday-monitor')
def api_intraday_monitor():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    ref = _ref_da((request.args.get('date') or '').strip())
    snap = queries._intraday_snapshot(ref)
    try:
        snap['prev'] = queries._prev_items(ref)
    except Exception as e:                                  # noqa: BLE001
        # O D-1 é um card da página, não a página: ilegível, ele diz o motivo
        # e o resto continua.
        _R().log.warning('[intraday-monitor] pendências de D-1 falharam', exc_info=True)
        snap['prev'] = {'error': '{}: {}'.format(type(e).__name__, e)}
    # quem arrasta o quê (§632)
    snap['me'] = {'desk': str(session.get('user_role') or '').strip().upper(),
                  'is_admin': bool(_R()._session_is_admin()),
                  'sid': str(session.get('user_sid') or '').strip().upper()}
    # owner e backup de cada tarefa (§701): o card os mostra — nas tarefas de
    # zona, só os dos produtos com movimento no dia
    snap['assignments'] = domain.assignments_of_day(
        persistence._load_assignments(),
        domain.moving_products(snap.get('cards'), snap.get('conf_cards')))
    snap['assign_products'] = {k: l for lst in domain.assign_products().values() for k, l in lst}
    snap['people'] = {p['sid']: {'name': p['name'], 'photo': p['photo']}
                      for p in persistence._assignable_people()}
    snap['me']['can_assign'] = _pode_designar()
    return jsonify({'success': True, **snap})


def _pode_designar():
    """Quem designa owner/backup: a mesa das tarefas (BO) e admin/master — a
    mesma regra de quem move a tarefa no quadro."""
    return bool(_R()._session_is_admin()) or \
        str(session.get('user_role') or '').strip().upper() in _IM_DESK


@blueprint.route('/api/intraday-monitor/assignments', methods=['GET', 'POST'])
def api_intraday_assignments():
    """Owner e backup das tarefas (§701). GET: a lista, quem pode ser
    designado e se a sessão edita. POST: substitui a lista inteira (BO e
    admin); o designado NOVO é avisado no sino, só ele (`target_sid`)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    pessoas = persistence._assignable_people()
    if request.method == 'GET':
        return jsonify({'success': True, 'assignments': persistence._load_assignments(strict=True),
                        'people': pessoas, 'les': list(domain.ASSIGN_LES),
                        'products': {t: [{'key': k, 'label': l} for k, l in lst]
                                     for t, lst in domain.assign_products().items()},
                        'tasks': [{'id': t['id'], 'label': t['label'], 'icon': t['icon']} for t in domain.TASKS],
                        'can_edit': _pode_designar()})
    if not _pode_designar():
        return jsonify({'success': False, 'code': 'assign_not_allowed',
                        'message': 'Only OTC Ops (BO) and admins assign task owners.'}), 403
    lista = (request.get_json(silent=True) or {}).get('assignments')
    if not isinstance(lista, list):
        return jsonify({'success': False, 'code': 'bad_payload'}), 400
    sids = {p['sid'] for p in pessoas}
    antes = persistence._load_assignments(strict=True)
    limpa = domain.clean_assignments(lista, sids)
    persistence._save_assignments(limpa)
    R = _R()
    rotulo = {t['id']: t['label'] for t in domain.TASKS}
    rot_prod = {k: l for lst in domain.assign_products().values() for k, l in lst}
    for sid, papel, task, product, le in domain.assignment_news(antes, limpa):
        try:
            R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                                   'Task Assigned', 'Intraday Monitor',
                                   '{} · {}{}{}'.format('Owner' if papel == 'owner' else 'Backup',
                                                        rotulo.get(task, task),
                                                        ' · ' + rot_prod.get(product, product) if product else '',
                                                        ' (' + le + ')' if le else ''),
                                   target_sid=sid)
        except Exception:                                   # noqa: BLE001
            R.log.warning('[intraday-monitor] aviso de designação para %s falhou', sid, exc_info=True)
    return jsonify({'success': True, 'assignments': limpa})


# ── Arrastar o card de tarefa (§632) ───────────────────────────────────────────
# O estado de cada tarefa é CALCULADO (a recon rodou, o End process); soltar o
# card noutra coluna grava um ajuste manual do dia, com quem e quando, que vale
# por cima — inclusive na tarefa de ZONA (B3 Registration, Confirmations,
# Intrag), cujo estado é a contagem: travada, ela não arrastava e não dizia
# por quê, e a mesa lia o quadro como quebrado (20/10/2026). O ajuste é dela,
# com quem/quando no card e o "↺ auto" para voltar. As tarefas do Monitor são
# do OTC Ops (BO): a mesa anda um passo à frente e devolve ao cálculo
# (`auto`, o Undo da pílula e o "↺ auto") o ajuste que ELA fez; admin e master
# põem qualquer estado e desfazem o de qualquer um. O passo da mesa é conferido
# contra o estado REAL da tarefa, não contra o `from` da tela: o quadro se
# atualiza a cada minuto, e um card velho em `todo` de uma tarefa já `done`
# viraria `in_progress` — um ajuste que a mesa nem consegue desfazer.
_IM_NEXT = {'todo': ('in_progress',), 'in_progress': ('done',), 'late': ('done',)}
_IM_DESK = ('BO',)


@blueprint.route('/api/intraday-monitor/override', methods=['POST'])
def api_intraday_override():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    from apps.pages.features.deals_monitor import domain as _dom
    from apps.pages.platform import task_runs
    body = request.get_json(silent=True) or {}
    task = str(body.get('task') or '').strip()
    de = str(body.get('from') or '').strip()
    para = str(body.get('to') or '').strip()
    tdef = next((t for t in _dom.TASKS if t['id'] == task), None)
    if tdef is None:
        return jsonify({'success': False, 'code': 'unknown_task'}), 400
    if para not in task_runs.OVERRIDE_STATES + ('auto',):
        return jsonify({'success': False, 'code': 'bad_state'}), 400
    R = _R()
    ref = _ref_da((body.get('date') or '').strip())
    dia = ref.date() if hasattr(ref, 'date') else ref
    if not R._session_is_admin():
        desk = str(session.get('user_role') or '').strip().upper()
        nega = jsonify({'success': False, 'code': 'move_not_allowed',
                        'message': 'Your desk can only move a task one step forward.'}), 403
        if desk not in _IM_DESK:
            return nega
        if para == 'auto':
            meu = str(session.get('user_sid') or '').strip().upper()
            aj = task_runs.overrides_of(dia).get(task) or {}
            if not aj or str(aj.get('sid') or '').strip().upper() != meu:
                return nega
        else:
            if para not in _IM_NEXT.get(de, ()):
                return nega
            real = next((t.get('state') for t in queries._intraday_snapshot(ref)['tasks']
                         if t['id'] == task), None)
            if real != de:
                return jsonify({'success': False, 'code': 'stale_card', 'state': real,
                                'message': 'The board was out of date: the task is now {}.'.format(real)}), 409
    reg = task_runs.set_override(dia, task, para, session.get('user_sid', ''), session.get('user_name', ''))
    return jsonify({'success': True, 'override': reg})


@blueprint.route('/api/control-panel/intraday-tasks', methods=['GET', 'POST'])
def api_cp_intraday_tasks():
    """A agenda das tarefas (dias da semana + horário limite), do card
    Intraday Tasks. GET lê ESTRITO: banco ocupado responde 503 (o tratador
    global), nunca os padrões — senão o Save seguinte os gravaria por cima
    da agenda da mesa (§548)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if request.method == 'GET':
        cfg = domain.task_config(persistence._load_intraday_tasks(strict=True))
        return jsonify({'success': True, 'tasks': [
            {'id': t['id'], 'label': t['label'], 'icon': t['icon'], 'kind': t['kind'],
             'default_days': list(t['days']), 'default_deadline': domain.DEADLINE_PADRAO,
             'month': list(t['month']) if t.get('month') else None,
             **cfg[t['id']]} for t in domain.TASKS]})
    payload = request.get_json(silent=True) or {}
    salvo = payload.get('tasks')
    if not isinstance(salvo, dict) or not set(salvo) <= set(domain.TASK_IDS):
        return jsonify({'success': False, 'code': 'bad_payload'}), 400
    persistence._save_intraday_tasks(salvo)
    return jsonify({'success': True})

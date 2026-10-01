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
    return jsonify({'success': True, **snap})


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

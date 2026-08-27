# -*- coding: utf-8 -*-
"""As duas rotas do card Pending Confirmations Spreadsheet Metrics."""
import traceback
from datetime import timedelta

from flask import jsonify, request, session

from apps.pages import blueprint
from apps.pages.features.pcx import commands, domain, queries

# O wiring do routes registra o scheduler com este nome.
start_scheduler = commands.start_scheduler


def _routes():
    from apps.pages import routes
    return routes


@blueprint.route('/api/control-panel/pending-spreadsheet/run', methods=['POST'])
def api_cp_pcx_run():
    """Gera e grava a planilha AGORA (botão Run do card). Roda mesmo em feriado
    — quem clicou decidiu — e não consome o claim do disparo automático: o
    arquivo é sobrescrito de qualquer jeito, gravar duas vezes não machuca.

    O campo Reference date do card manda `date` (AAAA-MM-DD). Hoje (ou vazio) é
    a rotina de sempre; uma data anterior monta a planilha a partir do snapshot
    daquele dia e grava com o nome datado (ver `persistence.save_spreadsheet`)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401

    R = _routes()
    hoje = R._br_now().date()
    ref = None
    raw = str((request.get_json(silent=True) or {}).get('date') or '').strip()
    if raw:
        d = R._parse_date_any(raw)
        if d is None:
            return jsonify({'success': False,
                            'error': 'Invalid reference date: {}.'.format(raw)}), 400
        if d > hoje:
            # O snapshot é uma FOTO do passado; não há o que fotografar amanhã.
            return jsonify({'success': False,
                            'error': 'Reference date {} is in the future — the pending '
                                     'snapshot only exists for days that have already '
                                     'run.'.format(d.strftime('%d/%m/%Y'))}), 400
        if d < hoje:
            ref = d

    try:
        n, fp = commands.run_manual(ref)
    except domain.NoSnapshot as e:
        # 404 e não 500: o pedido está correto, o dia é que não tem foto (o
        # snapshot começou depois, ou o dia não foi útil). Dizer o caminho
        # procurado é o que separa "não tem" de "a data está errada".
        R.log.warning('[pending-spreadsheet] sem snapshot para %s (%s)',
                    e.ref.strftime('%Y-%m-%d'), e.path)
        return jsonify({'success': False,
                        'error': 'No pending snapshot for {} — nothing was written. '
                                 'Expected:<br><code>{}</code>'
                                 .format(e.ref.strftime('%d/%m/%Y'), e.path)}), 404
    except Exception as e:                                  # noqa: BLE001
        R.log.error('[pending-spreadsheet] run manual falhou:\n%s', traceback.format_exc())
        return jsonify({'success': False,
                        'error': 'Could not save the spreadsheet: {}: {}. Check that the '
                                 'share is reachable and the file is not open in Excel.'
                                 .format(type(e).__name__, e)}), 500

    # O status (gravado pelo run_manual) leva a data da foto: como o arquivo do
    # share é o mesmo, é o card que responde "o que está lá agora?". A próxima
    # corrida normal reescreve o status sem `ref` e a marca cai sozinha.
    R._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Pending Spreadsheet Saved', 'Control Panel',
                         '{} row(s){} → {}'.format(
                             n, ' ({})'.format(ref.strftime('%d/%m/%Y')) if ref else '',
                             domain.FILENAME))
    return jsonify({'success': True, 'rows': n, 'path': fp,
                    'ref_date': ref.strftime('%d/%m/%Y') if ref else '',
                    'source': 'snapshot' if ref else 'live',
                    'message': '{} row(s){} saved to<br><code>{}</code>'.format(
                        n,
                        ' from the {} snapshot'.format(ref.strftime('%d/%m/%Y')) if ref else '',
                        fp)})


@blueprint.route('/api/control-panel/pending-spreadsheet/status')
def api_cp_pcx_status():
    """Desfecho do último disparo + próximo horário, para o card responder
    "a planilha de hoje saiu?" sem ninguém abrir o log do servidor."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    last = queries.status()
    R = _routes()
    hh, mm = queries.send_time()
    now = R._br_now()
    nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    while nxt <= now or not R._pcx_is_bizday(nxt):
        nxt += timedelta(days=1)
        nxt = nxt.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return jsonify({'success': True, 'last': last,
                    'next': nxt.strftime('%d/%m/%Y %H:%M'),
                    'now_br': now.strftime('%d/%m/%Y %H:%M'),
                    'path': queries.share_path()})


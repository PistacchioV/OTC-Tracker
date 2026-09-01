# -*- coding: utf-8 -*-
"""As rotas de Live Positions.

Só a casca: os coletores por produto ficam — os Settlement Advices leem os mesmos payloads — o resto fica no routes até a fase platform/, alcançado por _R().
"""
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@blueprint.route('/live-position-swap-characteristics')
def live_position_swap_characteristics():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _R()._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-swap-characteristics.html',
                           segment='live-position-swap-characteristics', ref_date=ref_date)

@blueprint.route('/api/live-position-swap-characteristics/data')
def api_swapchar_data():
    """Swap Characteristics payload for a reference date (default D-1 ANBIMA)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d').date() if ds else \
            _R()._prev_anbima_bizday(datetime.now()).date()
    except ValueError:
        ref = _R()._prev_anbima_bizday(datetime.now()).date()
    # `exact=1` desliga a busca para trás (contrato do Advanced Export — ver o
    # comentário no endpoint do NDF); a TELA não manda nada e anda até dez dias
    # úteis, com o `source_date` dizendo de que dia é o arquivo lido.
    exact = str(request.args.get('exact', '')).strip() in ('1', 'true', 'yes')
    payload = _R()._swapchar_collect(ref, exact=exact)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/live-position-swap-cashflow')
def live_position_swap_cashflow():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _R()._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-swap-cashflow.html',
                           segment='live-position-swap-cashflow', ref_date=ref_date)

@blueprint.route('/api/live-position-swap-cashflow/data')
def api_swapcash_data():
    """Swap Cashflow payload (DFLUXO) for a reference date (default D-1 ANBIMA)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ref = _R()._swap_simple_ref(request.args)
    exact = str(request.args.get('exact', '')).strip() in ('1', 'true', 'yes')
    payload = _R()._swap_simple_collect(ref, '73760_{}_DFLUXO.json',
                                   _R()._SWAPFLUX_LABELS, _R()._SWAPFLUX_DISPLAY_IDX, _R()._SWAPFLUX_TYPES,
                                   exact=exact)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/live-position-swap-premium')
def live_position_swap_premium():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _R()._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-swap-premium.html',
                           segment='live-position-swap-premium', ref_date=ref_date)

@blueprint.route('/api/live-position-swap-premium/data')
def api_swapprem_data():
    """Swap Premium payload (DAGENDAPREMIOS) for a reference date (default D-1 ANBIMA)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ref = _R()._swap_simple_ref(request.args)
    exact = str(request.args.get('exact', '')).strip() in ('1', 'true', 'yes')
    payload = _R()._swapprem_collect(ref, exact=exact)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/live-position-ndf')
def live_position_ndf():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _R()._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-ndf.html', segment='live-position-ndf', ref_date=ref_date)

@blueprint.route('/api/live-position-ndf/data')
def api_lpndf_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R()._prev_anbima_bizday(datetime.now())
    except ValueError:
        ref = _R()._prev_anbima_bizday(datetime.now())
    # `exact=1` desliga a busca para trás: devolve o dia pedido ou nada. Quem
    # pede é o Advanced Export, montando um intervalo — sem isso, todo dia sem
    # arquivo devolveria o do dia anterior, e a planilha sairia com o mesmo dia
    # repetido sob datas diferentes. A TELA continua sem mandar nada e com o
    # fallback de sempre, que é o que a mantém populada.
    exact = str(request.args.get('exact', '')).strip() in ('1', 'true', 'yes')
    payload = _R()._lpndf_collect(ref, exact=exact)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

@blueprint.route('/live-position-option')
def live_position_option():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    ref_date = _R()._prev_anbima_bizday(datetime.now()).strftime('%Y-%m-%d')
    return render_template('pages/live-position-option.html', segment='live-position-option', ref_date=ref_date)

@blueprint.route('/api/live-position-option/data')
def api_lpopt_data():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    ds = (request.args.get('date') or '').strip()
    try:
        ref = datetime.strptime(ds[:10], '%Y-%m-%d') if ds else _R()._prev_anbima_bizday(datetime.now())
    except ValueError:
        ref = _R()._prev_anbima_bizday(datetime.now())
    # `exact=1` desliga a busca para trás: devolve o dia pedido ou nada. Quem
    # pede é o Advanced Export, montando um intervalo — sem isso, todo dia sem
    # arquivo devolveria o do dia anterior, e a planilha sairia com o mesmo dia
    # repetido sob datas diferentes. A TELA continua sem mandar nada e com o
    # fallback de sempre, que é o que a mantém populada.
    exact = str(request.args.get('exact', '')).strip() in ('1', 'true', 'yes')
    payload = _R()._lpopt_collect(ref, exact=exact)
    payload.update({'success': True, 'ref_date': ref.strftime('%Y-%m-%d'),
                    'ref_date_fmt': ref.strftime('%d/%m/%Y')})
    return jsonify(payload)

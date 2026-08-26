# -*- coding: utf-8 -*-
"""As três rotas de Cotações."""
from datetime import datetime, timedelta

from flask import (jsonify, redirect, render_template, request, session,
                   url_for)

from apps.pages import blueprint, quotes as motor
from apps.pages.features.quotes import domain, queries


@blueprint.route('/quotes')
def quotes_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    hoje = datetime.now()
    return render_template(
        'pages/quotes.html', segment='quotes',
        # Padrão de um mês para trás, como no app de desktop: quem abre a tela
        # quer o histórico recente, não um campo vazio pedindo duas datas.
        date_from=(hoje - timedelta(days=30)).strftime('%Y-%m-%d'),
        date_to=hoje.strftime('%Y-%m-%d'),
        currencies=queries.currencies(),
        equities=queries.underlyings('equity'),
        commodities=queries.underlyings('commodity'))


@blueprint.route('/api/quotes/ptax')
def api_quotes_ptax():
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    try:
        cols, rows = queries.ptax(request.args.get('currency', 'USD'),
                                  request.args.get('from', ''),
                                  request.args.get('to', ''))
    except motor.QuotesError as e:
        # 502 e não 500: o app está de pé, quem não respondeu foi a fonte — e a
        # tela mostra o motivo por extenso em vez de "erro interno", que mandaria
        # procurar o defeito aqui dentro.
        return jsonify({'success': False, 'error': str(e)}), 502
    return jsonify({'success': True, 'columns': cols, 'rows': rows})


@blueprint.route('/api/quotes/<kind>')
def api_quotes_symbol(kind):
    """Equities e Commodities: o mesmo endpoint, porque a diferença entre as
    duas é só o CADASTRO de onde o símbolo sai — a fonte, as colunas e o
    formato são idênticos. Duas funções seriam duas cópias da mesma coisa."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    if not domain.is_known(kind):
        return jsonify({'success': False, 'error': 'Unknown quotes kind.'}), 404
    cadastro = domain.registry_for(kind)
    label = str(request.args.get('instrument', '') or '').strip()
    symbol = queries.symbol_of(kind, label)
    if not symbol:
        # Pede cadastro em vez de tentar o código como símbolo: 'AAPL34' e
        # 'AA UN' não são tickers de mercado, e a resposta seria um 404 obscuro
        # da fonte em vez de "falta cadastrar".
        return jsonify({'success': False, 'mapping': cadastro,
                        'error': ('{} has no market symbol registered in '
                                  'Mapping > {}.'.format(label or '(empty)', cadastro))}), 404
    try:
        cols, rows = queries.ohlc(symbol, request.args.get('from', ''),
                                  request.args.get('to', ''))
    except motor.QuotesError as e:
        return jsonify({'success': False, 'error': str(e)}), 502
    return jsonify({'success': True, 'columns': cols, 'rows': rows, 'symbol': symbol})

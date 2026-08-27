# -*- coding: utf-8 -*-
"""As cinco rotas do Holidays Calendar."""
import traceback

from flask import (jsonify, redirect, render_template, request, session,
                   url_for)

from apps.pages import blueprint
from apps.pages.features.holidays import commands, domain, queries


def _nao_autenticado():
    return jsonify({'ok': False, 'error': 'Unauthorized'}), 401


@blueprint.route('/holidays-calendar')
def holidays_calendar():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/holidays-calendar.html', segment='holidays-calendar')


@blueprint.route('/api/fx-holiday-schedules')
def api_fx_holiday_schedules():
    if not session.get('authenticated'):
        return _nao_autenticado()
    try:
        return jsonify({'ok': True, 'schedules': queries.fx_schedules()})
    except Exception as e:                                  # noqa: BLE001
        return jsonify({'ok': False, 'error': str(e)})


@blueprint.route('/api/holidays/calendars', methods=['GET'])
def api_holidays_calendars():
    """Os calendários que a tela desenha: pills da barra lateral, opções do
    modal e o mapa de cores saem TODOS daqui."""
    if not session.get('authenticated'):
        return _nao_autenticado()
    return jsonify({'ok': True, 'calendars': queries.calendars()})


@blueprint.route('/api/holidays/save', methods=['POST'])
def api_holidays_save():
    if not session.get('authenticated'):
        return _nao_autenticado()
    payload = request.get_json(silent=True) or {}
    calendar_name = payload.get('calendar', '').strip()
    date = payload.get('date', '').strip()               # YYYY-MM-DD
    title = payload.get('title', '').strip()
    if not all([calendar_name, date, title]):
        return jsonify({'ok': False, 'error': 'Missing fields'})
    total, erro = commands.save_holiday(calendar_name, date, title)
    if erro:
        return jsonify({'ok': False, 'error': erro})
    return jsonify({'ok': True, 'total': total})


@blueprint.route('/api/holidays/calendars', methods=['POST'])
def api_holidays_calendar_create():
    """Cria um calendário a partir da planilha jogada na dropzone.

    O nome vira o arquivo (`<slug>.json`, ao lado dos demais) e a linha do
    registro, com uma cor sorteada da paleta. A partir daí ele é um calendário
    como qualquer outro: aparece na barra lateral, no `<select>` do modal e
    aceita feriado avulso pelo `/api/holidays/save`.
    """
    if not session.get('authenticated'):
        return _nao_autenticado()
    from apps.pages import routes

    nome = (request.form.get('name') or '').strip().upper()
    f = request.files.get('file')
    if not nome:
        return jsonify({'ok': False, 'error': 'Calendar name is required.'}), 400
    if not f or not f.filename:
        return jsonify({'ok': False, 'error': 'Please attach the holidays spreadsheet.'}), 400
    if not domain.slug(nome):
        return jsonify({'ok': False,
                        'error': 'Calendar name must have at least one letter or digit.'}), 400

    try:
        linhas = routes._cc_read_rows(f.filename, f.read())
    except ValueError as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    except Exception:                                       # noqa: BLE001
        routes.log.error('[holidays] leitura da planilha falhou:\n%s',
                         traceback.format_exc())
        return jsonify({'ok': False, 'error': 'Could not read the spreadsheet.'}), 400

    feriados = domain.rows_from_sheet(linhas, nome)
    if not feriados:
        # Calendário vazio é calendário que ninguém vê e que ninguém entende
        # por que não aparece. Melhor recusar dizendo o que se esperava ler.
        return jsonify({'ok': False,
                        'error': 'No holiday found. Column A must hold the dates '
                                 '(yyyy-mm-dd) and column B the description.'}), 400
    try:
        linha = commands.create_calendar(nome, feriados)
    except commands.CalendarConflict as e:
        # 409 e não 400: o pedido está bem formado, o ESTADO é que recusa.
        return jsonify({'ok': False, 'error': str(e)}), 409
    except Exception:                                       # noqa: BLE001
        return jsonify({'ok': False, 'error': 'Could not save the calendar.'}), 500

    routes._create_notification(
        session.get('user_sid', ''), session.get('user_name', ''),
        'Holiday Calendar', 'Holidays Calendar',
        '{} · {} holiday(s) imported'.format(nome, len(feriados)))
    return jsonify({'ok': True, 'calendar': linha, 'total': len(feriados)})

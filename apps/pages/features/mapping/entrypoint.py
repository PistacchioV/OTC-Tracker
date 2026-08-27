# -*- coding: utf-8 -*-
"""As rotas de Mapping (os 43 cadastros editáveis pela tela).

Só a casca: o REGISTRO `_MAPPING_DEFS`, o `_mapping_rows` e os upgrades são plataforma — meia aplicação os lê.
"""
import io
import json
import os
import re
import traceback
from datetime import datetime

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)

from apps.pages import blueprint


def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/api/reference-data/counterparties')
def api_refdata_counterparties():
    """Nome × SPN × Tax ID do Reference Data, para o autocompletar dos cadastros."""
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return _R().jsonify({'success': True, 'rows': _R()._refdata_triples()})

@_R().blueprint.route('/mapping')
def mapping_page():
    if not _R().session.get('authenticated'):
        return _R().redirect(_R().url_for('pages_blueprint.sign_in_page'))
    return _R().render_template('pages/mapping.html', segment='mapping')

@_R().blueprint.route('/api/mappings/<key>', methods=['GET', 'POST'])
def api_mappings(key):
    if not _R().session.get('authenticated'):
        return _R().jsonify({'success': False, 'error': 'Not authenticated'}), 401
    d = _R()._MAPPING_DEFS.get(key)
    if not d:
        return _R().jsonify({'success': False, 'error': 'Unknown mapping.'}), 404
    if _R().request.method == 'GET':
        return _R().jsonify({'success': True, 'label': d['label'], 'columns': d['columns'],
                        'rows': _R()._mapping_rows(key)})
    p = _R().request.get_json(silent=True) or {}
    rows = p.get('rows')
    if not isinstance(rows, list):
        return _R().jsonify({'success': False, 'error': 'rows must be a list.'}), 400
    keys = [c['key'] for c in d['columns']]
    # Valores NÃO são trimados de propósito: em códigos B3 como 'C ' o espaço
    # final faz parte do código.
    clean = [{k: str((r or {}).get(k, '') or '') for k in keys} for r in rows if isinstance(r, dict)]
    # Gravação + invalidação do cache sob o lock, para ninguém ler o arquivo novo
    # com o cache velho. ⚠️ Isto NÃO resolve dois usuários editando o mesmo
    # mapping em abas separadas: o POST manda a tabela inteira, então quem salvar
    # depois sobrescreve as linhas do outro. Resolver isso pede versionamento
    # (mtime que o front devolve) — não implementado.
    with _R()._cache_lock:
        try:
            _R()._atomic_write_json(_R()._mapping_path(key), clean)
            _R()._mapping_cache.pop(key, None)
        except Exception as e:
            _R().log.error('[mappings] save failed for %s:\n%s', key, _R().traceback.format_exc())
            return _R().jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    _R()._create_notification(_R().session.get('user_sid', ''), _R().session.get('user_name', ''),
                         'Mapping Updated', 'Mapping',
                         '{} ({} row(s))'.format(d['label'], len(clean)))
    return _R().jsonify({'success': True, 'rows': clean})

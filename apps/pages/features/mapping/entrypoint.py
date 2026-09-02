# -*- coding: utf-8 -*-
"""As rotas de Mapping (os 43 cadastros editáveis pela tela).

Só a casca: o REGISTRO `_MAPPING_DEFS`, o `_mapping_rows` e os upgrades são plataforma — meia aplicação os lê.
"""

from flask import (jsonify, redirect, render_template, request,
                   session, url_for)



def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


@_R().blueprint.route('/api/reference-data/counterparties')
def api_refdata_counterparties():
    """Nome × SPN × Tax ID do Reference Data, para o autocompletar dos cadastros."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True, 'rows': _R()._refdata_triples()})

@_R().blueprint.route('/mapping')
def mapping_page():
    if not session.get('authenticated'):
        return redirect(url_for('pages_blueprint.sign_in_page'))
    return render_template('pages/mapping.html', segment='mapping')

@_R().blueprint.route('/api/mappings', methods=['GET'])
def api_mappings_counts():
    """As CONTAGENS de todos os cadastros numa resposta só — é o que os badges
    do rail do /mapping precisam no load. Antes a página disparava 43 fetches
    de uma vez (um por cadastro, o maior com ~14 mil linhas) só para escrever
    43 números: contra as 16 threads do waitress isso enfileirava três rodadas
    e cada request pagava as idas ao share. Aqui é UM request, e o
    `_mapping_rows` por baixo é memoizado por request (§7)."""
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({'success': True,
                    'counts': {k: len(_R()._mapping_rows(k))
                               for k in _R()._MAPPING_DEFS}})


@_R().blueprint.route('/api/mappings/<key>', methods=['GET', 'POST'])
def api_mappings(key):
    if not session.get('authenticated'):
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    d = _R()._MAPPING_DEFS.get(key)
    if not d:
        return jsonify({'success': False, 'error': 'Unknown mapping.'}), 404
    if request.method == 'GET':
        return jsonify({'success': True, 'label': d['label'], 'columns': d['columns'],
                        'rows': _R()._mapping_rows(key)})
    p = request.get_json(silent=True) or {}
    rows = p.get('rows')
    if not isinstance(rows, list):
        return jsonify({'success': False, 'error': 'rows must be a list.'}), 400
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
            return jsonify({'success': False, 'error': '{}: {}'.format(type(e).__name__, e)}), 500
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                         'Mapping Updated', 'Mapping',
                         '{} ({} row(s))'.format(d['label'], len(clean)))
    return jsonify({'success': True, 'rows': clean})

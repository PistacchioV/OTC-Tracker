# -*- coding: utf-8 -*-
"""As rotas de Index B3 (o editor do SwapIndex.json).

Só a casca: o arquivo é o MESMO que o cadastro swap-index do /mapping edita.
"""

from flask import jsonify, request, session



def _R():
    """Busca ATRASADA no routes — plataforma (ver features/support/infra)."""
    from apps.pages import routes
    return routes


# O estado intermediário do delete com maker/checker. Vive como constante
# porque três lugares o comparam (pedir, aprovar e o badge da tela), e um
# literal repetido é uma grafia a divergir.
_PENDING_DELETE = 'PENDING DELETE'


def _pagina(table):
    """Reference Data e Index B3 compartilham o endpoint e são páginas
    DIFERENTES — o rótulo é o que o sino usa para levar a pessoa ao lugar
    certo (`_NOTIF_PAGE_URL`)."""
    return 'Reference Data' if table == 'refdata' else 'Index B3'


def _detalhe(table, rec):
    """O texto do aviso: no Reference Data ele identifica o CLIENTE (SPN +
    razão social), porque `refdata` sozinho não diz a quem a linha se refere."""
    rec = rec or {}
    if table != 'refdata':
        return table
    spn = str(rec.get('SPN', '') or '').strip()
    nome = str(rec.get('COUNTERPARTY', '') or '').strip()
    detalhe = ('SPN ' + spn) if spn else 'SPN —'
    return (detalhe + ' · ' + nome) if nome else detalhe


@_R().blueprint.route('/api/b3/update', methods=['POST'])
def api_b3_update():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')
    fields  = payload.get('fields', {})
    action  = payload.get('action', 'edit')   # 'edit' | 'approve'
    user    = session.get('user_sid', 'UNKNOWN')

    if table not in _R()._B3_FILE_MAP or idx is None:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return jsonify({'ok': False, 'error': 'bad_index'}), 400

    rec = records[int(idx)]

    if action == 'approve':
        if rec.get('MAKER') == user:
            return jsonify({'ok': False, 'error': 'same_user'}), 403
        if rec.get('STATUS') == _PENDING_DELETE:
            # Aprovar um PENDING DELETE **é** a exclusão: o registro sai do
            # arquivo aqui, e não vira um estado a mais. O maker/checker acima
            # vale igual — quem pediu a exclusão não a aprova.
            #
            # A resposta diz `removed`, e não um `new_status` qualquer: a tela
            # precisa RECARREGAR, não repintar a linha. Todo botão da grade
            # carrega o `data-idx`, que é a POSIÇÃO no array; remover o item i
            # desloca todos os seguintes, e uma tela que só apagasse a linha do
            # DOM ficaria com os vizinhos apontando para o registro errado —
            # a próxima edição gravaria em cima de outro cliente, sem erro
            # nenhum. É a mesma armadilha do Delete da Intrag (§430), pela
            # outra ponta.
            removido = records.pop(int(idx))
            _R()._b3_save(path, records)
            _R()._create_notification(user, session.get('user_name', ''),
                                      'Item Deleted', _pagina(table),
                                      _detalhe(table, removido))
            return jsonify({'ok': True, 'new_status': 'DELETED', 'removed': True})
        rec['CHECKER'] = user
        new_status = 'INACTIVE' if rec.get('STATUS') == 'PENDING INACTIVE' else 'ACTIVE'
        rec['STATUS']  = new_status
    elif action == 'request_delete':
        # Pedido de exclusão: nada sai do arquivo agora. O registro fica
        # visível, marcado, esperando o checker — que é o contrário do que a
        # tela fazia com o `/api/b3/delete`, que apaga no clique e sem revisão.
        rec['STATUS']  = _PENDING_DELETE
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = _PENDING_DELETE
    elif action == 'deactivate':
        rec['STATUS']  = 'PENDING INACTIVE'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING INACTIVE'
    else:
        for k, v in fields.items():
            rec[k] = v
        rec['STATUS']  = 'PENDING'
        rec['MAKER']   = user
        rec['CHECKER'] = None
        new_status     = 'PENDING'

    _R()._b3_save(path, records)
    # On checker approval of a Reference Data counterparty (→ ACTIVE), make sure
    # its Electronic Inventory folder tree exists. This touches a network share
    # (listdir + makedirs) and can be slow, so run it OFF the request path — the
    # response (and the on-screen status update + notification) must not wait.
    if table == 'refdata' and action == 'approve' and new_status == 'ACTIVE':
        try:
            _R().threading.Thread(target=_R()._ensure_counterparty_folders,
                             args=(rec.get('COUNTERPARTY', ''),), daemon=True).start()
        except Exception:
            pass
    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(rec.get('SPN', '') or '').strip()
        name = str(rec.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' — ' + action + ' → ' + new_status
    else:
        page = 'Index B3'
        detail = table + ' — ' + action + ' → ' + new_status
    _R()._create_notification(user, session.get('user_name', ''), 'Item Updated', page, detail)
    return jsonify({'ok': True, 'new_status': new_status})

@_R().blueprint.route('/api/b3/delete', methods=['POST'])
def api_b3_delete():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    idx     = payload.get('idx')

    if table not in _R()._B3_FILE_MAP or idx is None:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    if not (0 <= int(idx) < len(records)):
        return jsonify({'ok': False, 'error': 'bad_index'}), 400

    removed = records.pop(int(idx))
    _R()._b3_save(path, records)
    _R()._create_notification(session.get('user_sid', ''), session.get('user_name', ''),
                              'Item Deleted', _pagina(table), _detalhe(table, removed))
    return jsonify({'ok': True})

@_R().blueprint.route('/api/b3/add', methods=['POST'])
def api_b3_add():
    if not session.get('authenticated'):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401
    payload = request.get_json(silent=True) or {}
    table   = payload.get('table', '')
    fields  = payload.get('fields', {})
    user    = session.get('user_sid', 'UNKNOWN')

    if table not in _R()._B3_FILE_MAP:
        return jsonify({'ok': False, 'error': 'bad_request'}), 400

    if not _R()._user_can_access_page('/reference-data' if table == 'refdata' else '/index-b3'):
        return jsonify({'ok': False, 'error': 'forbidden'}), 403

    records, path = _R()._b3_load(table)
    fields['STATUS']  = 'PENDING'
    fields['MAKER']   = user
    fields['CHECKER'] = None
    records.append(fields)
    _R()._b3_save(path, records)

    # Reference Data shares this endpoint but is its own page — name it correctly
    # and carry SPN + counterparty so the bell deep-links to /reference-data?spn=.
    if table == 'refdata':
        page = 'Reference Data'
        spn  = str(fields.get('SPN', '') or '').strip()
        name = str(fields.get('COUNTERPARTY', '') or '').strip()
        detail = ('SPN ' + spn) if spn else 'SPN —'
        if name:
            detail += ' · ' + name
        detail += ' (Pending approval)'
    else:
        page = 'Index B3'
        detail = table + ': ' + str(fields.get('TICKER', fields.get('CODE', fields.get('NAME', ''))))
    _R()._create_notification(user, session.get('user_name', ''), 'New Item', page, detail)
    return jsonify({'ok': True, 'idx': len(records) - 1})

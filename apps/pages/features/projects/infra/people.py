# -*- coding: utf-8 -*-
"""O cadastro de usuários, do jeito que o Projects precisa dele: quem pode ser
Lead/responsável e o nome e o cargo de cada SID.

UMA consulta, memoizada por um minuto: a lista abre em todo GET das duas telas,
e o banco de usuários é o mesmo que o login e a autorização usam. O handle
fecha no `finally` (CLAUDE.md §4: sem ele o app inteiro trava). A busca do
`get_db_connection` é ATRASADA, pelo `routes`, para o teste poder trocá-la.
"""
import logging
import threading
import time

log = logging.getLogger('otc_tracker')

_TTL = 60.0
_lock = threading.Lock()
_memo = {'at': 0.0, 'rows': None}


def _routes():
    from apps.pages import routes
    return routes


def forget():
    with _lock:
        _memo['at'], _memo['rows'] = 0.0, None


def users():
    """[{sid, name, position, role, status}] de todo o cadastro. Falha de
    leitura devolve a última lista boa (ou vazia) e vai para o log — a tela
    abre sem a lista de pessoas em vez de cair."""
    with _lock:
        if _memo['rows'] is not None and time.time() - _memo['at'] < _TTL:
            return _memo['rows']
    try:
        conn = _routes().get_db_connection(readonly=True)
        try:
            linhas = conn.execute(
                'SELECT SID, Name, Position, Role_Description, Role, Status FROM users').fetchall()
        finally:
            conn.close()
    except Exception:                                    # noqa: BLE001
        log.warning('[projects] não li o cadastro de usuários', exc_info=True)
        with _lock:
            return _memo['rows'] or []
    rows = [{'sid': str(sid or '').strip().upper(), 'name': (name or '').strip(),
             'position': (pos or desc or '').strip(), 'role': str(role or '').strip().upper(),
             'status': str(st or '').strip().upper()}
            for sid, name, pos, desc, role, st in linhas if str(sid or '').strip()]
    with _lock:
        _memo['at'], _memo['rows'] = time.time(), rows
    return rows

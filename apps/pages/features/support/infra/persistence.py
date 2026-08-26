# -*- coding: utf-8 -*-
"""O papel (mesa) de cada requester, do cadastro de usuários.

Isto é infraestrutura e não regra: a REGRA — "mesmo papel, mesma mesa" — está
no `domain.py`, que recebe este mapa pronto e não sabe de onde ele veio.
"""
import threading
import time
import traceback

# ── A ponte com o `routes.py`, e por que ela é assim ────────────────────────
# O que esta feature precisa daqui — `get_db_connection`, `log` — são
# preocupações de PLATAFORMA, e o lugar delas é um `platform/infra/`. Elas ainda
# não foram extraídas (a de notificação sozinha tem 161 pontos de chamada), e
# extrair tudo de uma vez é a mudança que ninguém consegue revisar.
#
# Até lá, a busca é LATE: `_routes().get_db_connection`, resolvido na CHAMADA e
# nunca no import. Isso não é estilo — é o que mantém os testes funcionando.
# Sessenta e um dos setenta e nove scripts de `scripts/tests/` trocam atributos
# no módulo (`R.DB_PATH = tmp`, `R._create_notification = espiao`), e um
# `from apps.pages.routes import get_db_connection` no topo congelaria o valor
# do import: o teste trocaria o atributo, este módulo continuaria com o
# original, e o teste passaria a ler o dado de VERDADE sem erro nenhum.
#
# O import atrasado resolve, de quebra, a circularidade: o `routes.py` importa o
# entrypoint desta feature no fim do arquivo, então importar `routes` aqui em
# cima seria um ciclo.
def _routes():
    from apps.pages import routes
    return routes


_TTL = 300.0
_CACHE = {}
_LOCK = threading.Lock()


def roles_by_sid(sids):
    """{SID: papel} do cadastro de usuários, para os SIDs pedidos.

    Existe para os tickets ANTERIORES ao `requester_role` — sem ele, todos eles
    ficariam invisíveis para a mesa de quem os abriu, e um chamado que some é
    pior do que um chamado que aparece para gente demais.

    UMA consulta para o lote inteiro, e o handle fecha no `finally`: a conexão
    do DuckDB de usuários é singleton atrás de um lock global, e um `close()`
    que não acontece trava o app para todo mundo (CLAUDE.md §4).
    """
    faltam, agora = [], time.time()
    out = {}
    with _LOCK:
        for k in {str(x or '').strip().upper() for x in sids if str(x or '').strip()}:
            hit = _CACHE.get(k)
            if hit and (agora - hit[0]) < _TTL:
                out[k] = hit[1]
            else:
                faltam.append(k)
    if not faltam:
        return out
    R = _routes()
    try:
        conn = R.get_db_connection(readonly=True)
        try:
            ph = ', '.join('?' for _ in faltam)
            linhas = conn.execute(
                'SELECT SID, Role FROM users WHERE UPPER(SID) IN ({})'.format(ph),
                faltam).fetchall()
        finally:
            conn.close()
    except Exception:
        R.log.warning('[tickets] não consegui ler o papel dos requesters:\n%s',
                      traceback.format_exc())
        return out
    achados = {str(r[0] or '').strip().upper(): str(r[1] or '').strip().upper()
               for r in linhas}
    with _LOCK:
        for k in faltam:
            # O SID que não está no cadastro entra no cache como '' — senão cada
            # listagem pagaria a consulta de novo por um usuário que não existe.
            v = achados.get(k, '')
            _CACHE[k] = (agora, v)
            out[k] = v
    return out


def roles_for_tickets(tickets):
    """Os papéis que FALTAM para decidir a mesa de uma lista de chamados.

    Só os tickets sem `requester_role` gravado — os antigos — precisam de
    consulta, e todos eles saem numa consulta SÓ. Um `can_view` por ticket
    abriria o banco de usuários uma vez por linha da tela.
    """
    return roles_by_sid([t.get('requester_sid') for t in tickets
                         if not t.get('requester_role')])
